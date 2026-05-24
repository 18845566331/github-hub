"""
diagnostics.py — 系统环境诊断
检测 Python/pip/git/npm/CUDA/网络等环境状态
"""
import os
import sys
import re
import shutil
import subprocess
import platform
from typing import Callable, Optional
from pathlib import Path


def _run(cmd: list, timeout: int = 15) -> tuple:
    """运行命令，返回 (returncode, output)"""
    try:
        if os.name == "nt" and cmd and cmd[0] in {"npm", "pnpm", "yarn", "bun", "npx"}:
            shim = shutil.which(cmd[0] + ".cmd") or shutil.which(cmd[0])
            if shim:
                cmd = [shim] + list(cmd[1:])
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "超时"
    except FileNotFoundError:
        return -1, "未找到命令"
    except Exception as e:
        return -1, str(e)


def _check_network(url: str = "https://pypi.org", timeout: int = 8) -> tuple:
    import time, requests
    try:
        start = time.time()
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        elapsed = round(time.time() - start, 3)
        return r.status_code < 400, elapsed
    except Exception:
        return False, -1.0


def run_full_diagnostics(callback: Callable = None) -> dict:
    """运行全面的环境诊断，返回结构化结果"""
    results = {}

    def log(msg):
        if callback:
            callback(msg)

    log("\n[INFO] ══════════════════════════════")
    log("[INFO] 系统环境诊断 — GitHub Hub")
    log("[INFO] ══════════════════════════════")
    log(f"[INFO] 操作系统: {platform.system()} {platform.release()} ({platform.machine()})")
    log(f"[INFO] 主机名:   {platform.node()}")
    results["os"] = platform.system()

    # 内存/磁盘
    try:
        import psutil
        mem = psutil.virtual_memory()
        log(f"[INFO] 内存: {mem.total // 1024**3}GB / 可用 {mem.available // 1024**3}GB")
        disk = psutil.disk_usage(os.path.splitdrive(sys.executable)[0] or "/")
        log(f"[INFO] 磁盘: {disk.free // 1024**3}GB 空闲 / {disk.total // 1024**3}GB")
    except ImportError:
        log("[WARN] psutil 未安装，跳过内存/磁盘检测")

    # Python
    log("\n[INFO] 【Python 环境】")
    log(f"[INFO] 版本: {sys.version}")
    log(f"[INFO] 路径: {sys.executable}")
    results["python_ok"] = sys.version_info >= (3, 8)
    if results["python_ok"]:
        log(f"[SUCCESS] Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} ✓")
    else:
        log("[ERROR] Python 版本过低，需要 >= 3.8")

    # pip
    log("\n[INFO] 【pip】")
    code, out = _run([sys.executable, "-m", "pip", "--version"])
    results["pip_ok"] = code == 0
    log(f"[{'SUCCESS' if code==0 else 'ERROR'}] pip: {out}")

    # Git
    log("\n[INFO] 【Git】")
    git_path = shutil.which("git")
    if git_path:
        code, out = _run(["git", "--version"])
        log(f"[SUCCESS] {out}  路径: {git_path} ✓")
        results["git_ok"] = True
    else:
        log("[ERROR] Git 未安装或未加入 PATH")
        log("[INFO] 建议: 下载 https://git-scm.com/download/win")
        results["git_ok"] = False

    # Node / npm
    log("\n[INFO] 【Node.js / npm】")
    node_path = shutil.which("node")
    npm_path  = shutil.which("npm")
    results["node_ok"] = bool(node_path)
    results["npm_ok"]  = bool(npm_path)
    if node_path:
        _, out = _run(["node", "--version"])
        log(f"[SUCCESS] Node.js: {out} ✓")
    else:
        log("[WARN] Node.js 未安装（仅 Node 项目需要）")
    if npm_path:
        _, out = _run(["npm", "--version"])
        log(f"[SUCCESS] npm: {out} ✓")

    # GPU / CUDA
    log("\n[INFO] 【GPU / CUDA】")
    nvidia = shutil.which("nvidia-smi")
    results["gpu_ok"] = False
    if nvidia:
        code, out = _run(["nvidia-smi",
                          "--query-gpu=name,driver_version,memory.total",
                          "--format=csv,noheader,nounits"])
        if code == 0:
            for line in out.splitlines():
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 3:
                    log(f"[SUCCESS] GPU: {parts[0]}  驱动:{parts[1]}  显存:{parts[2]}MB ✓")
            results["gpu_ok"] = True
    else:
        log("[INFO] 未检测到 NVIDIA GPU")
    code, out = _run(["nvcc", "--version"])
    results["cuda_ok"] = code == 0
    if code == 0:
        log(f"[SUCCESS] CUDA: {out.splitlines()[-1]} ✓")
    else:
        log("[INFO] nvcc 未找到（AI 项目可能需要）")

    # 关键 Python 包
    log("\n[INFO] 【常用 Python 包检测】")
    KEY_PACKAGES = [
        ("torch",           "PyTorch"),
        ("torchvision",     "torchvision"),
        ("transformers",    "HuggingFace Transformers"),
        ("numpy",           "NumPy"),
        ("opencv-python",   "OpenCV"),
        ("Pillow",          "Pillow"),
        ("PySide6",         "PySide6 (GUI)"),
        ("requests",        "requests"),
        ("tqdm",            "tqdm"),
        ("gradio",          "Gradio"),
        ("fastapi",         "FastAPI"),
        ("uvicorn",         "uvicorn"),
        ("scipy",           "SciPy"),
        ("matplotlib",      "Matplotlib"),
        ("pandas",          "Pandas"),
        ("scikit-learn",    "scikit-learn"),
        ("diffusers",       "Diffusers"),
        ("accelerate",      "Accelerate"),
        ("onnxruntime",     "ONNX Runtime"),
        ("GitPython",       "GitPython"),
    ]
    package_status = {}
    import importlib.metadata as metadata
    for distribution, pkg_label in KEY_PACKAGES:
        try:
            ver = metadata.version(distribution)
            log(f"[SUCCESS]   {pkg_label:<28} {ver} ✓")
            package_status[distribution] = {"ok": True, "version": ver}
        except metadata.PackageNotFoundError:
            log(f"[WARN]      {pkg_label:<28} 未安装")
            package_status[distribution] = {"ok": False, "version": None}
    results["packages"] = package_status

    # 网络连通性
    log("\n[INFO] 【网络连通性测试】")
    network_tests = [
        ("PyPI 官方",    "https://pypi.org"),
        ("GitHub",       "https://github.com"),
        ("清华镜像",     "https://pypi.tuna.tsinghua.edu.cn"),
        ("阿里云镜像",   "https://mirrors.aliyun.com"),
        ("Hugging Face", "https://huggingface.co"),
    ]
    network_status = {}
    for name, url in network_tests:
        ok, elapsed = _check_network(url)
        if ok:
            log(f"[SUCCESS] {name:<16} ✓  延迟: {elapsed:.3f}s")
        else:
            log(f"[ERROR]   {name:<16} ✗  无法访问")
        network_status[name] = {"ok": ok, "latency": elapsed}
    results["network"] = network_status

    # 磁盘写入权限
    log("\n[INFO] 【磁盘写入权限】")
    for d in [os.path.expanduser("~"), str(Path(__file__).resolve().parents[1])]:
        if os.path.isdir(d):
            test_f = os.path.join(d, "._write_test_")
            try:
                with open(test_f, "w") as f: f.write("t")
                os.remove(test_f)
                log(f"[SUCCESS] {d} ✓")
            except Exception as e:
                log(f"[ERROR]   {d} ✗ ({e})")

    # 汇总问题
    issues = []
    if not results.get("python_ok"):      issues.append("Python 版本过低（需 >=3.8）")
    if not results.get("pip_ok"):         issues.append("pip 未正常工作")
    if not results.get("git_ok"):         issues.append("Git 未安装")
    if not network_status.get("PyPI 官方", {}).get("ok"):
        issues.append("PyPI 无法访问（建议启用镜像加速）")
    if not network_status.get("GitHub", {}).get("ok"):
        issues.append("GitHub 无法访问（建议启用 GitHub 镜像）")

    log("\n[INFO] ══════════════════════════════")
    if issues:
        log(f"[WARN] 发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            log(f"[WARN]   {i}. {issue}")
    else:
        log("[SUCCESS] 环境诊断通过，一切正常 ✓")
    log("[INFO] ══════════════════════════════\n")
    results["issues"] = issues
    return results


def check_project_requirements(project_dir: str, callback: Callable = None, python_exe: str = None) -> dict:
    """诊断指定项目的依赖缺失"""
    import sys
    python_exe = python_exe or sys.executable
    results = {"missing": [], "installed": [], "req_file": None}

    def log(msg):
        if callback: callback(msg)

    req_file = os.path.join(project_dir, "requirements.txt")
    if not os.path.exists(req_file):
        log("[WARN] 未找到 requirements.txt")
        return results
    results["req_file"] = req_file
    log(f"[INFO] 检查: {req_file} (使用解析器: {python_exe})")

    packages = read_project_requirements(project_dir)
    for pkg_name in packages:
        import_name = _import_name_for_package(pkg_name)
        code, out = _run([
            python_exe,
            "-c",
            f"import importlib.util, sys; sys.exit(0 if importlib.util.find_spec({import_name!r}) else 1)",
        ], timeout=20)
        if code == 0:
            results["installed"].append(pkg_name)
            log(f"[SUCCESS] {pkg_name} ✓")
        else:
            results["missing"].append(pkg_name)
            log(f"[ERROR]   {pkg_name} ✗ 未安装")

    log(f"[INFO] 已安装: {len(results['installed'])}  缺失: {len(results['missing'])}")
    return results


IMPORT_NAME_OVERRIDES = {
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "opencv-contrib-python": "cv2",
    "opencv-contrib-python-headless": "cv2",
    "pyyaml": "yaml",
    "pillow": "PIL",
    "pyqt5": "PyQt5",
    "pyqtwebengine": "PyQt5",
    # ↑ PyQtWebEngine 包里的实际 import 名是 PyQt5 (QtWebEngine 装在 PyQt5 命名空间下)
    "qimage2ndarray": "qimage2ndarray",
    "scikit-learn": "sklearn",
    "python-dateutil": "dateutil",
    "lapx": "lap",
}


def _requirement_package_name(line: str) -> str:
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("-"):
        return ""
    line = line.split("#", 1)[0].strip()
    line = re.split(r"[<>=!~;\\[]", line, maxsplit=1)[0].strip()
    return line


def _import_name_for_package(package: str) -> str:
    key = package.lower().replace("_", "-")
    return IMPORT_NAME_OVERRIDES.get(key, package.replace("-", "_"))


def read_project_requirements(project_dir: str) -> list:
    req_file = Path(project_dir) / "requirements.txt"
    if not req_file.exists():
        return []
    packages = []
    for raw in req_file.read_text(encoding="utf-8", errors="replace").splitlines():
        name = _requirement_package_name(raw)
        if name:
            packages.append(name)
    return packages


def check_project_dependencies(project_dir: str, python_exe: str = None,
                               callback: Callable = None) -> dict:
    """Check project requirements against the interpreter used to launch it."""
    python_exe = python_exe or sys.executable
    packages = read_project_requirements(project_dir)
    results = {
        "python_exe": python_exe,
        "packages": packages,
        "installed": [],
        "missing": [],
        "errors": {},
    }

    def log(msg):
        if callback:
            callback(msg)

    if not packages:
        log("[INFO] 未发现 requirements.txt，跳过依赖检测")
        return results

    log(f"[INFO] 正在检测 {len(packages)} 个依赖: {python_exe}")
    for package in packages:
        import_name = _import_name_for_package(package)
        code, out = _run([
            python_exe,
            "-c",
            f"import importlib.util, sys; sys.exit(0 if importlib.util.find_spec({import_name!r}) else 1)",
        ], timeout=20)
        if code == 0:
            results["installed"].append(package)
        else:
            results["missing"].append(package)
            if out:
                results["errors"][package] = out

    if results["missing"]:
        log(f"[WARN] 缺失依赖: {', '.join(results['missing'])}")
    else:
        log("[SUCCESS] 项目依赖检测通过")
    return results


def generate_project_diagnostic_report(project_dir: str, config: dict = None,
                                       recent_log: str = None) -> str:
    """Generate a compact report for clone/install/launch failures."""
    from .dependency_manager import detect_project_type, detect_node_package_manager
    from .project_launcher import detect_launch_candidates

    config = config or {}
    proj_info = detect_project_type(project_dir)
    lines = [
        "GitHub Hub 项目诊断报告",
        f"项目目录: {project_dir}",
        f"项目类型: {proj_info.get('type', 'unknown')}",
        f"运行时: {proj_info.get('runtime', 'unknown')}",
        f"依赖文件: {', '.join(proj_info.get('dep_files') or []) or '未检测到'}",
        f"入口文件: {', '.join(proj_info.get('entry_points') or []) or '未检测到'}",
        "",
        "环境版本:",
    ]

    for name, cmd in [
        ("Git", ["git", "--version"]),
        ("Python", [sys.executable, "--version"]),
        ("Node", ["node", "--version"]),
        ("npm", ["npm", "--version"]),
        ("pnpm", ["pnpm", "--version"]),
        ("yarn", ["yarn", "--version"]),
    ]:
        code, out = _run(cmd, timeout=8)
        status = out.splitlines()[0] if out else "不可用"
        lines.append(f"- {name}: {status if code == 0 else '不可用'}")

    if proj_info.get("has_package_json"):
        lines.append(f"- Node 包管理器: {detect_node_package_manager(project_dir)}")

    lines.extend([
        "",
        "镜像配置:",
        f"- GitHub: {config.get('github_mirror', '未配置')}",
        f"- PyPI: {config.get('pip_mirror', '未配置')}",
        f"- npm: {config.get('npm_mirror', '未配置')}",
        "",
        "启动候选:",
    ])
    candidates = detect_launch_candidates(project_dir, config)
    if candidates:
        for item in candidates[:8]:
            lines.append(f"- {item.get('description')}: {' '.join(item.get('cmd') or [])}")
    else:
        lines.append("- 未检测到启动命令")

    if recent_log:
        lines.extend(["", "最近日志:", recent_log.strip()[-4000:]])

    return "\n".join(lines)
