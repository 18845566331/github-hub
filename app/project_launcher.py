"""
project_launcher.py — 项目启动逻辑
自动检测入口文件，构建启动命令，管理子进程
"""
import os
import sys
import json
import site
import subprocess
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse

from .dependency_manager import (
    detect_project_type, get_venv_python, is_venv_ready,
    detect_node_package_manager, resolve_node_cli_command
)


def _load_package_json(project_dir: str) -> dict:
    try:
        with open(Path(project_dir) / "package.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _node_run_command(project_dir: str, script: str) -> list:
    manager = detect_node_package_manager(project_dir)
    if manager == "npm" and script == "start":
        return resolve_node_cli_command(["npm", "run", "start"])
    return resolve_node_cli_command([manager, "run", script])


def detect_launch_candidates(project_dir: str, config: dict = None) -> list:
    """Return ordered launch command candidates instead of only the first match."""
    p = Path(project_dir)
    if config is None:
        config = {}
    proj_info = detect_project_type(project_dir)
    candidates = []

    if config.get("custom_command"):
        candidates.append({
            "cmd": config["custom_command"],
            "cwd": project_dir,
            "env": None,
            "description": f"自定义: {config['custom_command']}",
        })
        return candidates

    if proj_info["has_package_json"]:
        pkg = _load_package_json(project_dir)
        scripts = pkg.get("scripts", {})
        for script in ["start", "dev", "serve", "preview", "tools-dev"]:
            if script in scripts:
                cmd = _node_run_command(project_dir, script)
                candidates.append({
                    "cmd": cmd,
                    "cwd": project_dir,
                    "env": None,
                    "description": " ".join(cmd),
                })
        main = pkg.get("main")
        if main:
            candidates.append({
                "cmd": ["node", main],
                "cwd": project_dir,
                "env": None,
                "description": f"node {main}",
            })
        return candidates

    if (p / "go.mod").exists():
        return [{"cmd": ["go", "run", "."], "cwd": project_dir, "env": None, "description": "go run ."}]

    if (p / "Cargo.toml").exists():
        return [{"cmd": ["cargo", "run"], "cwd": project_dir, "env": None, "description": "cargo run"}]

    python_exe = config.get("python_exe") or sys.executable
    dep_mode = config.get("dep_mode", 1)
    if dep_mode == 1:
        venv_dir = os.path.join(project_dir, ".venv")
        if is_venv_ready(venv_dir):
            python_exe = get_venv_python(venv_dir)

    entry_priority = [
        ("__main__.py",   [python_exe, "-m", p.name]),
        ("main.py",       [python_exe, "main.py"]),
        ("app.py",        [python_exe, "app.py"]),
        ("manage.py",     [python_exe, "manage.py", "runserver"]),
        ("run.py",        [python_exe, "run.py"]),
        ("server.py",     [python_exe, "server.py"]),
        ("start.py",      [python_exe, "start.py"]),
        ("launcher.py",   [python_exe, "launcher.py"]),
        ("gradio_app.py", [python_exe, "gradio_app.py"]),
        ("webui.py",      [python_exe, "webui.py"]),
        ("demo.py",       [python_exe, "demo.py"]),
        ("inference.py",  [python_exe, "inference.py"]),
        ("train.py",      [python_exe, "train.py"]),
    ]
    for filename, cmd in entry_priority:
        if (p / filename).exists():
            candidates.append({"cmd": cmd, "cwd": project_dir, "env": None, "description": f"python {filename}"})

    sub_entries = ["app.py", "main.py", "run.py", "__main__.py"]
    try:
        subdirs = [d for d in p.iterdir() if d.is_dir()
                   and not d.name.startswith(".") and d.name != "__pycache__"]
        for subdir in sorted(subdirs):
            for entry in sub_entries:
                sub_entry = subdir / entry
                if sub_entry.exists():
                    if entry == "__main__.py":
                        module_name = subdir.name.replace("-", "_")
                        candidates.append({
                            "cmd": [python_exe, "-m", module_name],
                            "cwd": project_dir,
                            "env": None,
                            "description": f"python -m {module_name}",
                        })
                    else:
                        rel = str(sub_entry.relative_to(p)).replace("\\", "/")
                        candidates.append({
                            "cmd": [python_exe, rel],
                            "cwd": project_dir,
                            "env": None,
                            "description": f"python {rel}",
                        })
    except Exception:
        pass

    for bat_name in ["start.bat", "run.bat", "launch.bat", "start_app.bat"]:
        if (p / bat_name).exists():
            candidates.append({
                "cmd": [str(p / bat_name)],
                "cwd": project_dir,
                "env": None,
                "description": f"批处理: {bat_name}",
            })
    for sh_name in ["start.sh", "run.sh", "launch.sh"]:
        if (p / sh_name).exists():
            candidates.append({
                "cmd": ["bash", sh_name],
                "cwd": project_dir,
                "env": None,
                "description": f"Shell: {sh_name}",
            })

    if (p / "pyproject.toml").exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                tomllib = None
        if tomllib:
            try:
                with open(p / "pyproject.toml", "rb") as f:
                    data = tomllib.load(f)
                scripts = data.get("project", {}).get("scripts", {})
                for script, entry_point in scripts.items():
                    module_name = str(entry_point).split(":", 1)[0].strip()
                    if not module_name:
                        continue
                    candidates.append({
                        "cmd": [python_exe, "-m", module_name],
                        "cwd": project_dir,
                        "env": None,
                        "description": f"pyproject script: {script}",
                    })
            except Exception:
                pass

    return candidates


def detect_launch_command(project_dir: str, config: dict = None) -> dict:
    """
    自动检测最佳启动命令
    返回: {"cmd": [...], "cwd": str, "env": dict, "description": str}
    """
    candidates = detect_launch_candidates(project_dir, config)
    if candidates:
        return candidates[0]
    proj_info = detect_project_type(project_dir)
    if proj_info.get("has_package_json"):
        description = "项目根目录未提供可启动的 start/dev/serve/preview 脚本，请选择可运行的应用目录或手动配置启动命令"
    else:
        description = "项目未提供可自动启动的程序入口；文档、资源列表或库项目通常不能直接点击启动"
    return {
        "cmd": None, "cwd": project_dir,
        "env": None, "description": description,
    }


def build_env(project_dir: str, shared_dir: str = None,
              venv_dir: str = None, extra_env: dict = None) -> dict:
    """
    构建项目运行环境变量
    - 共享模式：将 shared_dir 加入 PYTHONPATH
    - venv 模式：不需要修改 PYTHONPATH（venv 内部已隔离）
    """
    env = os.environ.copy()

    python_paths = []
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runtime_packages = os.path.join(base_dir, ".runtime_packages")
    if os.path.isdir(runtime_packages):
        python_paths.append(runtime_packages)
    try:
        user_site = site.getusersitepackages()
        if os.path.isdir(user_site):
            python_paths.append(user_site)
    except Exception:
        pass

    if shared_dir and os.path.isdir(shared_dir):
        python_paths.append(shared_dir)

    current_path = env.get("PYTHONPATH", "")
    existing_parts = [p for p in current_path.split(os.pathsep) if p]
    merged = []
    for p in python_paths + existing_parts:
        if p and p not in merged:
            merged.append(p)
    if merged:
        env["PYTHONPATH"] = os.pathsep.join(merged)

    if extra_env:
        env.update(extra_env)

    return env


class ProjectProcess:
    """管理单个项目的运行进程"""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._project_dir = ""
        self._detected_urls: set[str] = set()
        self._reported_pids: set[int] = set()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, cmd: list, cwd: str, env: dict = None,
              output_callback: Callable = None,
              url_detected_callback: Callable = None,
              exit_callback: Callable = None) -> bool:
        """启动项目，output_callback 会在新线程中被调用"""
        if self.is_running:
            return False
        try:
            self._project_dir = os.path.realpath(cwd)
            self._detected_urls.clear()
            self._reported_pids.clear()
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._process = process
            if output_callback:
                import threading
                import re
                def _reader():
                    # 匹配常见的本地开发端口
                    url_pattern = re.compile(r"(https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d+)")
                    pid_pattern = re.compile(r"\bpid\s+(\d+)\b", re.IGNORECASE)
                    for line in process.stdout:
                        line_str = line.rstrip()
                        output_callback(line_str)
                        for pid_match in pid_pattern.finditer(line_str):
                            self._reported_pids.add(int(pid_match.group(1)))
                        if url_detected_callback:
                            m = url_pattern.search(line_str)
                            if m:
                                url = m.group(1).replace("0.0.0.0", "127.0.0.1")
                                self._detected_urls.add(url)
                                url_detected_callback(url)
                    returncode = process.wait()
                    output_callback("[进程已退出]")
                    if exit_callback:
                        exit_callback(returncode)
                threading.Thread(target=_reader, daemon=True).start()
            elif exit_callback:
                import threading
                def _waiter():
                    returncode = process.wait()
                    exit_callback(returncode)
                threading.Thread(target=_waiter, daemon=True).start()
            return True
        except Exception as e:
            if output_callback:
                output_callback(f"[ERROR] 启动失败: {e}")
            return False

    def _stop_detached_project_services(self):
        """Stop local services launched by this project after a wrapper detaches them."""
        if os.name != "nt" or not self._project_dir:
            return
        try:
            import psutil
        except ImportError:
            return
        pids = set(self._reported_pids)
        ports = {urlparse(url).port for url in self._detected_urls if urlparse(url).port}
        if ports:
            try:
                for conn in psutil.net_connections(kind="tcp"):
                    if conn.pid and conn.laddr and conn.laddr.port in ports:
                        pids.add(conn.pid)
            except Exception:
                pass
        project_key = os.path.normcase(self._project_dir)
        for pid in pids:
            try:
                proc = psutil.Process(pid)
                command = os.path.normcase(" ".join(proc.cmdline()))
                if project_key not in command:
                    continue
                for child in proc.children(recursive=True):
                    child.kill()
                proc.kill()
            except (psutil.Error, OSError):
                pass

    def stop(self):
        """停止进程"""
        if self._process and self._process.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(self._process.pid), "/T", "/F"],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            except Exception:
                pass
        self._stop_detached_project_services()
        self._process = None

    def send_input(self, text: str):
        """向进程发送标准输入"""
        if self._process and self._process.poll() is None and self._process.stdin:
            try:
                self._process.stdin.write(text + "\n")
                self._process.stdin.flush()
            except Exception:
                pass

    def get_pid(self) -> Optional[int]:
        return self._process.pid if self._process else None
# === MULTI-LANGUAGE LAUNCH SUPPORT ===

def detect_launch_command_multi(local_dir: str, config: dict = None) -> dict:
    """Detect launch command for any language project."""
    from .dependency_manager import detect_project_language
    lang = detect_project_language(local_dir)
    if lang == "python":
        return detect_launch_command(local_dir, config)
    elif lang == "node":
        launch = detect_launch_command(local_dir, config)
        if launch.get("cmd"):
            return launch
        return {"cmd": [], "description": "No start script found in package.json"}
    elif lang == "go":
        main_go = os.path.join(local_dir, "main.go")
        if os.path.exists(main_go):
            return {"cmd": ["go", "run", "."], "cwd": local_dir, "description": "go run ."}
        return {"cmd": [], "description": "No main.go found"}
    elif lang == "rust":
        return {"cmd": ["cargo", "run"], "cwd": local_dir, "description": "cargo run"}
    return {"cmd": [], "description": f"Unknown language: {lang}"}

def save_launch_log(project_id: str, log_text: str):
    """Save launch log to file."""
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f"{project_id}_{timestamp}.log")
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_text)
        return log_file
    except:
        return None
