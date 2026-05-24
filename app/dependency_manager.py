"""
dependency_manager.py — 共享依赖管理（升级版）
支持：镜像加速 / 详细进度显示 / 错误自动修复
"""
import os
import sys
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional, List


SHARED_PACKAGES_META = "installed_packages.json"


def resolve_node_cli_command(cmd: list) -> list:
    """Resolve npm-family Windows command shims for subprocess execution."""
    if not cmd:
        return cmd
    manager = str(cmd[0])
    if os.name == "nt" and manager in {"npm", "pnpm", "yarn", "bun", "npx"}:
        resolved = shutil.which(manager + ".cmd") or shutil.which(manager)
        if resolved:
            return [resolved] + list(cmd[1:])
    return cmd


def detect_project_type(project_dir: str) -> dict:
    """检测项目类型和依赖文件"""
    info = {
        "type": "unknown", "dep_files": [], "entry_points": [],
        "has_requirements": False, "has_pyproject": False,
        "has_setup_py": False, "has_package_json": False,
        "has_docker": False, "runtime": "python",
    }
    p = Path(project_dir)
    if (p / "requirements.txt").exists():
        info["has_requirements"] = True
        info["dep_files"].append("requirements.txt")
    if (p / "requirements-dev.txt").exists():
        info["dep_files"].append("requirements-dev.txt")
    if (p / "pyproject.toml").exists():
        info["has_pyproject"] = True
        info["dep_files"].append("pyproject.toml")
    if (p / "setup.py").exists():
        info["has_setup_py"] = True
        info["dep_files"].append("setup.py")
    if (p / "setup.cfg").exists():
        info["dep_files"].append("setup.cfg")
    if (p / "package.json").exists():
        info["has_package_json"] = True
        info["dep_files"].append("package.json")
        info["runtime"] = "node"
    if (p / "go.mod").exists():
        info["dep_files"].append("go.mod")
        info["runtime"] = "go"
    if (p / "Cargo.toml").exists():
        info["dep_files"].append("Cargo.toml")
        info["runtime"] = "rust"
    if (p / "Dockerfile").exists() or (p / "docker-compose.yml").exists():
        info["has_docker"] = True

    for ep in ["main.py", "app.py", "run.py", "server.py",
               "start.py", "__main__.py", "manage.py", "launcher.py",
               "gradio_app.py", "webui.py", "demo.py", "inference.py", "train.py"]:
        if (p / ep).exists():
            info["entry_points"].append(ep)

    # 子目录入口
    sub_entries = ["app.py", "main.py", "run.py", "__main__.py"]
    try:
        subdirs = [d for d in p.iterdir() if d.is_dir()
                   and not d.name.startswith(".") and d.name != "__pycache__"]
        for subdir in sorted(subdirs):
            for entry in sub_entries:
                sub_entry = subdir / entry
                if sub_entry.exists():
                    rel = str(sub_entry.relative_to(p)).replace("\\", "/")
                    info["entry_points"].append(rel)
    except Exception:
        pass

    # bat/sh 启动脚本
    for script_name in ["start.bat", "run.bat", "launch.bat", "start_app.bat", "start.sh", "run.sh", "launch.sh"]:
        if (p / script_name).exists():
            info["entry_points"].append(script_name)

    if info["has_package_json"] and not info["has_requirements"]:
        info["type"] = "node"
        info["runtime"] = "node"
    elif info["has_requirements"] or info["has_pyproject"] or info["has_setup_py"]:
        info["type"] = "python"
        info["runtime"] = "python"
    if info["runtime"] == "go":
        info["type"] = "go"
    elif info["runtime"] == "rust":
        info["type"] = "rust"
    return info


def read_requirements(req_file: str) -> list:
    reqs = []
    try:
        with open(req_file, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    reqs.append(line)
    except Exception:
        pass
    return reqs


def get_python_executable() -> str:
    return sys.executable


def _run_pip_with_progress(cmd: list, cwd: str = None,
                            callback: Callable = None,
                            auto_fix_ctx: dict = None) -> bool:
    """
    运行 pip 命令，解析进度信息并回调
    自动识别错误并尝试修复
    """
    error_lines = []
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PIP_PROGRESS_BAR"] = "on"
    try:
        process = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            env=env
        )
        buf = bytearray()
        def flush_line():
            try:
                line = buf.decode('utf-8', errors='replace').strip()
            except Exception:
                line = ""
            if not line:
                return
            enhanced = _enhance_pip_line(line)
            if callback:
                callback(enhanced)
            if any(kw in line for kw in ["ERROR", "error", "Error", "FAILED", "failed"]):
                error_lines.append(line)
            buf.clear()

        while True:
            b = process.stdout.read(1)
            if not b:
                break
            if b in (b'\r', b'\n'):
                flush_line()
            else:
                buf.extend(b)
        flush_line()

        process.wait()
        ok = process.returncode == 0

        # 若失败且有 auto_fix 上下文，尝试修复
        if not ok and auto_fix_ctx and error_lines:
            error_text = "\n".join(error_lines)
            if callback:
                callback(f"\n[WARN] 安装出错，尝试自动修复...")
            from .auto_fixer import auto_fix, analyze_error
            rules = analyze_error(error_text)
            if rules:
                ctx = {**auto_fix_ctx, "error_text": error_text}
                result = auto_fix(error_text, ctx, callback)
                if result.get("fixed"):
                    if callback:
                        callback("[SUCCESS] 已自动修复，重新尝试安装...")
                    # 重试一次
                    retry_proc = subprocess.Popen(
                        cmd, cwd=cwd,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace",
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    for line in retry_proc.stdout:
                        line = line.rstrip()
                        if line and callback:
                            callback(_enhance_pip_line(line))
                    retry_proc.wait()
                    return retry_proc.returncode == 0
        return ok
    except Exception as e:
        if callback:
            callback(f"[ERROR] pip 执行失败: {e}")
        return False


def _enhance_pip_line(line: str) -> str:
    """增强 pip 输出行，添加更友好的进度显示"""
    # 下载进度: "Downloading xxx.whl (123.4 MB)"
    dl_match = re.match(r"  Downloading (.+\.whl)\s+\((.+)\)", line)
    if dl_match:
        return f"[INFO] 📥 下载: {dl_match.group(1)}  大小: {dl_match.group(2)}"

    # 进度条: "━━━━ 45.2/123.4 MB 2.3 MB/s eta 0:00:35"
    prog_match = re.search(r"(\d+\.?\d*)/(\d+\.?\d*)\s+(MB|KB|GB)\s+([\d.]+)\s+(MB|KB)/s\s+eta\s+(\S+)", line)
    if prog_match:
        downloaded = prog_match.group(1)
        total = prog_match.group(2)
        unit = prog_match.group(3)
        speed = prog_match.group(4)
        speed_unit = prog_match.group(5)
        eta = prog_match.group(6)
        pct = min(100, int(float(downloaded) / float(total) * 100)) if float(total) > 0 else 0
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        return f"[INFO]  [{bar}] {pct:3d}%  {downloaded}/{total}{unit}  🚀 {speed}{speed_unit}/s  ⏱ {eta}"

    # 安装: "Installing collected packages: xxx"
    if "Installing collected packages:" in line:
        pkgs = line.split("Installing collected packages:")[-1].strip()
        return f"[INFO] 📦 正在安装: {pkgs}"

    # 已存在
    if "Requirement already satisfied:" in line:
        pkg = line.split("Requirement already satisfied:")[-1].split()[0]
        return f"[SUCCESS] ✓ {pkg} 已安装"

    # 成功
    if "Successfully installed" in line:
        return f"[SUCCESS] ✅ {line}"

    return line


def _go_mod_download(project_dir: str, callback=None) -> bool:
    import subprocess
    if callback:
        callback("[INFO] Running go mod download...")
    try:
        result = subprocess.run(["go", "mod", "download"], cwd=project_dir,
            capture_output=True, text=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode == 0:
            if callback:
                callback("[SUCCESS] Go dependencies installed")
            return True
        if callback:
            callback(f"[ERROR] go mod download failed: {result.stderr[:200]}")
        return False
    except FileNotFoundError:
        if callback:
            callback("[WARN] Go not found - install from https://go.dev")
        return False
    except Exception as e:
        if callback:
            callback(f"[ERROR] Go install: {e}")
        return False


def _cargo_build(project_dir: str, callback=None) -> bool:
    import subprocess
    if callback:
        callback("[INFO] Running cargo build...")
    try:
        result = subprocess.run(["cargo", "build"], cwd=project_dir,
            capture_output=True, text=True, timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode == 0:
            if callback:
                callback("[SUCCESS] Rust dependencies built")
            return True
        if callback:
            callback(f"[ERROR] cargo build failed: {result.stderr[-200:]}")
        return False
    except FileNotFoundError:
        if callback:
            callback("[WARN] Rust not found - install from https://rustup.rs")
        return False
    except Exception as e:
        if callback:
            callback(f"[ERROR] Rust install: {e}")
        return False


def install_to_shared_dir(project_dir: str, shared_dir: str,
                           python_exe: str = None,
                           callback: Callable = None,
                           pip_mirror_args: list = None,
                           npm_registry_args: list = None,
                           recipe: dict = None) -> bool:
    if python_exe is None:
        python_exe = get_python_executable()
    if pip_mirror_args is None:
        pip_mirror_args = []
    if npm_registry_args is None:
        npm_registry_args = []

    proj_info = detect_project_type(project_dir)
    install_recipe = (recipe or {}).get("install", {})
    p = Path(project_dir)
    has_python_deps = (
        install_recipe.get("runtime") == "python"
        or proj_info["has_requirements"]
        or (p / "requirements-dev.txt").exists()
        or proj_info["has_pyproject"]
        or proj_info.get("has_setup_py")
        or (p / "setup.cfg").exists()
    )
    if has_python_deps:
        os.makedirs(shared_dir, exist_ok=True)
    success = True
    auto_fix_ctx = {"python_exe": python_exe, "project_dir": project_dir}

    requirement_files = install_recipe.get("requirements") or [
        name for name in ("requirements.txt", "requirements-dev.txt")
        if (p / name).exists()
    ]
    for requirement_name in requirement_files:
        if not (p / requirement_name).is_file():
            if callback:
                callback(f"[ERROR] Verified recipe requirement missing: {requirement_name}")
            return False
        req_file = str(p / requirement_name)
        if callback:
            callback(f"[INFO] 从 {requirement_name} 安装到共享目录: {shared_dir}")
        cmd = ([python_exe, "-m", "pip", "install",
                "--target", shared_dir, "-r", req_file]
               + pip_mirror_args)
        success &= _run_pip_with_progress(cmd, callback=callback, auto_fix_ctx=auto_fix_ctx)

    has_installable_project = (
        bool(install_recipe.get("install_project"))
        if install_recipe else (
            proj_info.get("has_setup_py")
            or (p / "setup.cfg").exists()
            or (proj_info["has_pyproject"] and _should_install_python_project(project_dir, callback))
        )
    )
    if has_installable_project:
        if callback:
            callback("[INFO] 安装项目声明的 Python 包...")
        cmd = ([python_exe, "-m", "pip", "install",
                "--target", shared_dir, "."]
               + pip_mirror_args)
        success &= _run_pip_with_progress(cmd, cwd=project_dir, callback=callback,
                                          auto_fix_ctx=auto_fix_ctx)

    if proj_info["has_package_json"]:
        if callback:
            callback(f"[INFO] 运行 npm install...")
        success &= _npm_install(project_dir, callback, npm_registry_args)

    if proj_info["runtime"] == "go":
        success &= _go_mod_download(project_dir, callback)

    if proj_info["runtime"] == "rust":
        success &= _cargo_build(project_dir, callback)

    return success


def _ensure_uv_installed(python_exe: str, callback: Callable = None) -> bool:
    """Use uv only when it is already available; dependency setup must not alter the manager."""
    try:
        subprocess.run([python_exe, "-m", "uv", "--version"], check=True, capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return True
    except Exception:
        if callback:
            callback("[INFO] 未检测到 uv，使用内置 pip 安装流程")
        return False


def _should_install_python_project(project_dir: str, callback: Callable = None) -> bool:
    """Return False when the project explicitly disables building itself with uv."""
    pyproject = Path(project_dir) / "pyproject.toml"
    if not pyproject.exists():
        return True
    try:
        import tomllib
        with open(pyproject, "rb") as file:
            data = tomllib.load(file)
        if data.get("tool", {}).get("uv", {}).get("no-build") is True:
            if callback:
                callback("[INFO] pyproject.toml 禁止构建项目包，跳过安装项目本身")
            return False
    except (OSError, ValueError):
        pass
    return True


def install_with_venv(project_dir: str, venv_dir: str,
                      pip_cache_dir: str = None,
                      python_exe: str = None,
                      callback: Callable = None,
                      pip_mirror_args: list = None,
                      npm_registry_args: list = None,
                      recipe: dict = None) -> bool:
    if python_exe is None:
        python_exe = get_python_executable()
    if pip_mirror_args is None:
        pip_mirror_args = []
    if npm_registry_args is None:
        npm_registry_args = []

    proj_info = detect_project_type(project_dir)
    install_recipe = (recipe or {}).get("install", {})
    p = Path(project_dir)
    has_python_deps = (
        install_recipe.get("runtime") == "python"
        or proj_info["has_requirements"]
        or (p / "requirements-dev.txt").exists()
        or proj_info["has_pyproject"]
        or proj_info.get("has_setup_py")
        or (p / "setup.cfg").exists()
    )
    if not has_python_deps:
        success = True
        if proj_info["has_package_json"]:
            success &= _npm_install(project_dir, callback, npm_registry_args)
        if proj_info["runtime"] == "go":
            success &= _go_mod_download(project_dir, callback)
        if proj_info["runtime"] == "rust":
            success &= _cargo_build(project_dir, callback)
        return success

    has_uv = _ensure_uv_installed(python_exe, callback)

    # 创建 venv
    if not os.path.isdir(venv_dir):
        if callback:
            callback(f"[INFO] ⚡ 创建虚拟环境 (隔离且多项目共享包数据): {venv_dir}")
        try:
            cmd = [python_exe, "-m", "uv", "venv", venv_dir] if has_uv else [python_exe, "-m", "venv", venv_dir]
            subprocess.run(
                cmd, check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
        except subprocess.CalledProcessError as e:
            if callback:
                callback(f"[ERROR] 创建虚拟环境失败: {e}")
            return False

    if os.name == "nt":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        venv_pip    = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")
        venv_pip    = os.path.join(venv_dir, "bin", "pip")

    success = True
    auto_fix_ctx = {"python_exe": venv_python, "project_dir": project_dir}

    # Build cache dir args
    cache_args = []
    if pip_cache_dir and not has_uv:
        os.makedirs(pip_cache_dir, exist_ok=True)
        cache_args = ["--cache-dir", pip_cache_dir]

    # 基础安装命令
    if has_uv:
        base_cmd = [python_exe, "-m", "uv", "pip", "install", "--python", venv_python]
    else:
        base_cmd = [venv_python, "-m", "pip", "install"] + cache_args
        if callback:
            callback("[INFO] 升级 pip...")
        subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip"] + cache_args,
                       capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    requirement_files = install_recipe.get("requirements") or [
        name for name in ("requirements.txt", "requirements-dev.txt")
        if (p / name).exists()
    ]
    for requirement_name in requirement_files:
        if not (p / requirement_name).is_file():
            if callback:
                callback(f"[ERROR] Verified recipe requirement missing: {requirement_name}")
            return False
        req_file = str(p / requirement_name)
        if callback:
            callback(f"[INFO] 正在{'使用 uv ' if has_uv else ''}安装 {requirement_name} ...")
        cmd = base_cmd + ["-r", req_file] + pip_mirror_args
        success &= _run_pip_with_progress(cmd, callback=callback, auto_fix_ctx=auto_fix_ctx)

    has_installable_project = (
        bool(install_recipe.get("install_project"))
        if install_recipe else (
            proj_info.get("has_setup_py")
            or (p / "setup.cfg").exists()
            or (proj_info["has_pyproject"] and _should_install_python_project(project_dir, callback))
        )
    )
    if has_installable_project:
        if callback:
            callback(f"[INFO] 正在{'使用 uv ' if has_uv else ''}安装项目声明的 Python 包 ...")
        cmd = base_cmd + ["."] + pip_mirror_args
        success &= _run_pip_with_progress(cmd, cwd=project_dir, callback=callback,
                                          auto_fix_ctx=auto_fix_ctx)

    if proj_info["has_package_json"]:
        if callback:
            callback(f"[INFO] 运行 npm install...")
        success &= _npm_install(project_dir, callback, npm_registry_args)

    if proj_info["runtime"] == "go":
        success &= _go_mod_download(project_dir, callback)

    if proj_info["runtime"] == "rust":
        success &= _cargo_build(project_dir, callback)

    return success


def _npm_install(project_dir: str, callback: Callable = None,
                 npm_registry_args: list = None) -> bool:
    cmd = build_node_install_command(project_dir, npm_registry_args)
    exec_cmd = resolve_node_cli_command(cmd)
    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    if callback:
        callback(f"[INFO] 运行 {' '.join(cmd)}...")
    try:
        process = subprocess.Popen(
            exec_cmd, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            env=env
        )
        buf = bytearray()
        while True:
            b = process.stdout.read(1)
            if not b:
                break
            if b in (b'\r', b'\n'):
                try:
                    line = buf.decode('utf-8', errors='replace').strip()
                except Exception:
                    line = ""
                if line and callback:
                    callback(line)
                buf.clear()
            else:
                buf.extend(b)
        try:
            line = buf.decode('utf-8', errors='replace').strip()
        except Exception:
            line = ""
        if line and callback:
            callback(line)
        process.wait()
        return process.returncode == 0
    except FileNotFoundError:
        if callback:
            callback(f"[WARN] 未找到 {cmd[0]}，请先安装对应的 Node.js 包管理器")
        return False
    except Exception as e:
        if callback:
            callback(f"[ERROR] {cmd[0]} install 失败: {e}")
        return False


def get_venv_python(venv_dir: str) -> str:
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        return os.path.join(venv_dir, "bin", "python")


def is_venv_ready(venv_dir: str) -> bool:
    return os.path.isfile(get_venv_python(venv_dir))


def check_shared_dir_ready(shared_dir: str) -> bool:
    return os.path.isdir(shared_dir) and bool(os.listdir(shared_dir))
# === MULTI-LANGUAGE SUPPORT ===

def _emit_progress(progress_callback, message: str):
    if not progress_callback:
        return
    emit = getattr(progress_callback, "emit", None)
    if callable(emit):
        emit(message)
    else:
        progress_callback(message)


def detect_node_package_manager(project_dir: str) -> str:
    """Detect the preferred Node package manager from lockfiles."""
    p = Path(project_dir)
    if (p / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (p / "yarn.lock").exists():
        return "yarn"
    if (p / "bun.lockb").exists() or (p / "bun.lock").exists():
        return "bun"
    return "npm"


def build_node_install_command(project_dir: str, npm_registry_args: list = None) -> list:
    manager = detect_node_package_manager(project_dir)
    p = Path(project_dir)
    if manager == "npm" and (p / "package-lock.json").exists():
        cmd = [manager, "ci"]
    elif manager in {"pnpm", "yarn", "bun"}:
        cmd = [manager, "install", "--frozen-lockfile"]
    else:
        cmd = [manager, "install"]
    if npm_registry_args and manager in {"npm", "pnpm", "yarn"}:
        cmd += npm_registry_args
    return cmd


def detect_project_language(local_dir: str) -> str:
    """Detect project language from project files."""
    files = os.listdir(local_dir) if os.path.isdir(local_dir) else []
    if "Cargo.toml" in files: return "rust"
    if "go.mod" in files: return "go"
    if "package.json" in files: return "node"
    if "pyproject.toml" in files: return "python"
    if "setup.py" in files: return "python"
    if "requirements.txt" in files: return "python"
    if "CMakeLists.txt" in files: return "cpp"
    if "Gemfile" in files: return "ruby"
    return "unknown"

def install_node_deps(local_dir: str, progress_callback=None, npm_mirror_args=None):
    """Install Node.js dependencies."""
    registry_args = ["--registry", npm_mirror_args] if isinstance(npm_mirror_args, str) and npm_mirror_args else npm_mirror_args
    return _npm_install(local_dir, lambda m: _emit_progress(progress_callback, m), registry_args)

def install_go_deps(local_dir: str, progress_callback=None):
    """Install Go dependencies."""
    import subprocess
    env = os.environ.copy()
    if progress_callback:
        progress_callback.emit("[INFO] Running go mod download...")
    p = subprocess.Popen(["go", "mod", "download"], cwd=local_dir,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    for line in iter(p.stdout.readline, b""):
        text = line.decode("utf-8", errors="replace").rstrip()
        if progress_callback and text:
            progress_callback.emit(text)
    p.wait()
    return p.returncode == 0

def install_rust_deps(local_dir: str, progress_callback=None):
    """Install Rust dependencies."""
    import subprocess
    env = os.environ.copy()
    if progress_callback:
        progress_callback.emit("[INFO] Running cargo build...")
    p = subprocess.Popen(["cargo", "build"], cwd=local_dir,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    for line in iter(p.stdout.readline, b""):
        text = line.decode("utf-8", errors="replace").rstrip()
        if progress_callback and text:
            progress_callback.emit(text)
    p.wait()
    return p.returncode == 0

# === Dependency Status & Single Package Install (used by dependency_panel.py) ===

def _collect_python_requirements(project_dir: str, include_dev: bool = True, include_setup: bool = True) -> list:
    """Collect raw requirements lines from requirements files."""
    reqs = []
    p = Path(project_dir)
    files = ["requirements.txt"]
    if include_dev:
        files.append("requirements-dev.txt")
    for f in files:
        fp = p / f
        if fp.exists():
            try:
                with open(fp, "r", encoding="utf-8-sig", errors="replace") as file:
                    for line in file:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            reqs.append(line)
            except Exception:
                pass
    return reqs


def _collect_node_dependency_status(project_dir: str) -> list:
    package_file = Path(project_dir) / "package.json"
    if not package_file.exists():
        return []
    try:
        import json
        with open(package_file, "r", encoding="utf-8") as file:
            package_data = json.load(file)
    except Exception:
        return []
    declared = {}
    declared.update(package_data.get("dependencies") or {})
    declared.update(package_data.get("devDependencies") or {})
    items = []
    for name, required in sorted(declared.items()):
        installed_file = Path(project_dir) / "node_modules" / Path(name) / "package.json"
        installed = ""
        if installed_file.exists():
            try:
                with open(installed_file, "r", encoding="utf-8") as file:
                    installed = str((json.load(file) or {}).get("version", ""))
            except Exception:
                installed = ""
        items.append({
            "raw": name,
            "name": name,
            "required": str(required),
            "installed": installed,
            "manager": "npm",
            "status": "installed" if installed else "missing",
            "message": "Satisfied" if installed else "Not installed",
        })
    return items


def get_project_dependency_status(project_dir: str, python_exe: str = None,
                                  extra_paths: list = None) -> list:
    """Return per-package dependency status for UI display (dependency panel)."""
    import json, subprocess, sys
    reqs = _collect_python_requirements(project_dir, True, True)
    node_items = _collect_node_dependency_status(project_dir)
    if not reqs:
        return node_items
    python_exe = python_exe or sys.executable
    checker = r"""
import importlib.metadata as md, json, re, sys
reqs = json.loads(sys.stdin.read())
items = []
try:
    from packaging.requirements import Requirement
except Exception:
    Requirement = None
for raw in reqs:
    s = str(raw).strip()
    if not s or s.startswith(("-", "#")):
        continue
    item = {"raw": s, "name": s, "required": "", "installed": "", "status": "unknown", "message": ""}
    if "://" in s or s.startswith(("git+", "hg+", "svn+")):
        item.update({"status": "manual", "message": "URL/VCS dependency, use full install"})
        items.append(item)
        continue
    if Requirement:
        try:
            req = Requirement(s)
            if req.marker and not req.marker.evaluate():
                item.update({"name": req.name, "required": str(req.specifier), "status": "skipped", "message": "Not needed in current env"})
                items.append(item)
                continue
            item["name"] = req.name
            item["required"] = str(req.specifier)
            spec = req.specifier
        except Exception as exc:
            item.update({"status": "manual", "message": str(exc)})
            items.append(item)
            continue
    else:
        item["name"] = re.split(r"[<>=!~;\[\s]", s, 1)[0].strip()
        spec = None
    try:
        version = md.version(item["name"])
        item["installed"] = version
        if spec and str(spec) and not spec.contains(version, prereleases=True):
            item.update({"status": "conflict", "message": "Version mismatch"})
        else:
            item.update({"status": "installed", "message": "Satisfied"})
    except md.PackageNotFoundError:
        item.update({"status": "missing", "message": "Not installed"})
    except Exception as exc:
        item.update({"status": "unknown", "message": str(exc)})
    items.append(item)
print(json.dumps(items, ensure_ascii=True))
"""
    env = os.environ.copy()
    if extra_paths:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(extra_paths + ([existing] if existing else []))
    try:
        result = subprocess.run(
            [python_exe, "-c", checker],
            input=json.dumps(reqs, ensure_ascii=False),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode == 0:
            return json.loads(result.stdout or "[]") + node_items
    except Exception:
        pass
    return [{"raw": r, "name": r, "required": "", "installed": "", "status": "unknown", "message": "Status check failed"} for r in reqs] + node_items


def install_python_package(package_spec: str, env_python: str,
                           manager_python: str = None,
                           callback = None,
                           pip_mirror_args: list = None,
                           upgrade: bool = False) -> bool:
    """Install one Python package into a target Python environment."""
    manager_python = manager_python or sys.executable
    has_uv = _ensure_uv_installed(manager_python, callback)
    if has_uv:
        cmd = [manager_python, "-m", "uv", "pip", "install", "--python", env_python]
        if upgrade:
            cmd.append("--upgrade")
    else:
        cmd = [env_python, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
    cmd.append(package_spec)
    if pip_mirror_args:
        cmd += pip_mirror_args
    return _run_pip_with_progress(
        cmd,
        callback=callback,
        auto_fix_ctx={"python_exe": env_python},
    )


def install_node_package(project_dir: str, package_spec: str,
                         callback = None,
                         npm_registry_args: list = None) -> bool:
    """Install a single Node.js package."""
    manager = detect_node_package_manager(project_dir)
    action = "install" if manager == "npm" else "add"
    cmd = [manager, action, package_spec]
    if manager == "pnpm" and (Path(project_dir) / "pnpm-workspace.yaml").exists():
        cmd.append("--workspace-root")
    if npm_registry_args and manager in {"npm", "pnpm", "yarn"}:
        cmd += npm_registry_args
    exec_cmd = resolve_node_cli_command(cmd)
    try:
        process = subprocess.Popen(
            exec_cmd, cwd=project_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for line in process.stdout:
            if callback and line.rstrip():
                callback(line.rstrip())
        process.wait()
        return process.returncode == 0
    except Exception as e:
        if callback:
            callback(f"[ERROR] {manager} {action} failed: {e}")
        return False



def install_deps_auto(local_dir: str, progress_callback=None, pip_mirror_args=None,
                      npm_mirror=None, shared_dir: str = None):
    """Auto-detect and install dependencies."""
    lang = detect_project_language(local_dir)
    if lang == "python":
        if not shared_dir:
            shared_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared_packages")
        return install_to_shared_dir(local_dir, shared_dir, sys.executable, progress_callback, pip_mirror_args)
    elif lang == "node":
        return install_node_deps(local_dir, progress_callback, npm_mirror)
    elif lang == "go":
        return install_go_deps(local_dir, progress_callback)
    elif lang == "rust":
        return install_rust_deps(local_dir, progress_callback)
    else:
        if progress_callback:
            progress_callback.emit(f"[WARN] Unknown project type: {lang}")
        return False
