"""
auto_fixer.py — 自动错误修复
分析安装/运行错误并尝试自动修复
"""
import os
import sys
import re
import subprocess
from typing import Callable, Optional


# ──────────────────────────────────────────────
# 错误模式识别规则
# ──────────────────────────────────────────────
ERROR_PATTERNS = [
    # pip/包安装类
    {"pattern": r"Microsoft Visual C\+\+|LINK : fatal error|vcvarsall\.bat",
     "error_type": "missing_vc",
     "description": "缺少 Microsoft Visual C++ 编译器",
     "fix": "install_vc_runtime"},

    {"pattern": r"error: externally-managed-environment",
     "error_type": "externally_managed",
     "description": "系统 Python 受保护，不允许直接安装包",
     "fix": "use_break_system_packages"},

    {"pattern": r"pip.*is configured with locations that require TLS/SSL",
     "error_type": "ssl_error",
     "description": "SSL/TLS 证书错误",
     "fix": "fix_ssl"},

    {"pattern": r"Connection.*timed out|ConnectTimeout|Read timed out",
     "error_type": "timeout",
     "description": "网络连接超时（建议切换镜像源）",
     "fix": "switch_mirror"},

    {"pattern": r"No matching distribution found|Could not find a version",
     "error_type": "no_distribution",
     "description": "找不到匹配的包版本",
     "fix": "try_alternative_version"},

    {"pattern": r"upgrade pip|pip.*newer version|pip is configured.*outdated",
     "error_type": "pip_outdated",
     "description": "pip 版本过旧",
     "fix": "upgrade_pip"},

    {"pattern": r"git.*not.*found|'git' is not recognized",
     "error_type": "git_missing",
     "description": "Git 未安装或未在 PATH 中",
     "fix": "install_git_guide"},

    {"pattern": r"Permission denied|Access is denied|PermissionError",
     "error_type": "permission_denied",
     "description": "权限不足",
     "fix": "fix_permission"},

    {"pattern": r"ERROR: Could not build wheels|building wheel",
     "error_type": "wheel_build_failed",
     "description": "无法构建 wheel 包（缺少编译环境）",
     "fix": "install_build_tools"},

    {"pattern": r"DLL load failed|ImportError.*DLL",
     "error_type": "dll_error",
     "description": "DLL 加载失败（可能缺少 VC++ 运行时）",
     "fix": "install_vc_runtime"},

    {"pattern": r"CUDA out of memory|RuntimeError.*CUDA",
     "error_type": "cuda_oom",
     "description": "GPU 显存不足",
     "fix": "suggest_cpu_mode"},

    {"pattern": r"No module named|ModuleNotFoundError",
     "error_type": "module_missing",
     "description": "Python 模块缺失",
     "fix": "install_missing_module"},

    {"pattern": r"SyntaxError|IndentationError",
     "error_type": "syntax_error",
     "description": "Python 版本不兼容（语法错误）",
     "fix": "check_python_version"},

    {"pattern": r"charset-normalizer|chardet",
     "error_type": "charset_issue",
     "description": "字符编码库冲突",
     "fix": "reinstall_charset"},
]


def analyze_error(error_text: str) -> list:
    """分析错误文本，返回匹配的错误规则列表"""
    matched = []
    for rule in ERROR_PATTERNS:
        if re.search(rule["pattern"], error_text, re.IGNORECASE):
            matched.append(rule)
    return matched


def auto_fix(error_text: str, context: dict = None,
             callback: Callable = None) -> dict:
    """
    自动修复：分析错误并尝试修复
    context: {"python_exe": str, "project_dir": str, "pip_mirror": str, ...}
    返回: {"fixed": bool, "actions": list, "message": str}
    """
    if context is None:
        context = {}
    python_exe = context.get("python_exe", sys.executable)
    pip_mirror = context.get("pip_mirror", "")

    def log(msg):
        if callback: callback(msg)

    rules = analyze_error(error_text)
    if not rules:
        log("[INFO] 未识别到已知错误模式，无法自动修复")
        return {"fixed": False, "actions": [], "message": "未识别错误"}

    actions = []
    fixed = False

    for rule in rules:
        fix_name = rule["fix"]
        log(f"\n[INFO] 检测到问题: {rule['description']}")
        log(f"[INFO] 正在尝试修复: {fix_name}")

        result = _apply_fix(fix_name, python_exe, pip_mirror, context, callback)
        actions.append({
            "error_type": rule["error_type"],
            "fix": fix_name,
            "description": rule["description"],
            "result": result,
        })
        if result.get("ok"):
            fixed = True
            log(f"[SUCCESS] 修复成功: {result.get('message', '')}")
        else:
            log(f"[WARN] 修复未完全成功: {result.get('message', '')}")

    return {"fixed": fixed, "actions": actions,
            "message": f"尝试了 {len(actions)} 项修复"}


def _apply_fix(fix_name: str, python_exe: str, pip_mirror: str,
               context: dict, callback: Callable) -> dict:
    """执行具体修复动作"""
    def log(msg):
        if callback: callback(msg)

    def pip_run(args: list) -> bool:
        cmd = [python_exe, "-m", "pip"] + args
        if pip_mirror:
            cmd += ["-i", pip_mirror]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for line in proc.stdout:
                log(line.rstrip())
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            log(f"[ERROR] {e}")
            return False

    if fix_name == "upgrade_pip":
        log("[INFO] 升级 pip...")
        ok = pip_run(["install", "--upgrade", "pip"])
        return {"ok": ok, "message": "pip 已升级" if ok else "pip 升级失败"}

    elif fix_name == "use_break_system_packages":
        log("[INFO] 重试安装（添加 --break-system-packages 或 --user）...")
        req_file = context.get("req_file", "")
        if req_file and os.path.exists(req_file):
            cmd = [python_exe, "-m", "pip", "install", "-r", req_file, "--user"]
            ok = pip_run(["install", "-r", req_file, "--user"])
        else:
            ok = False
        return {"ok": ok, "message": "已使用 --user 模式重试"}

    elif fix_name == "fix_ssl":
        log("[INFO] 尝试跳过 SSL 验证安装（仅作为临时解决方案）...")
        req_file = context.get("req_file", "")
        args = ["install"]
        if req_file:
            args += ["-r", req_file]
        args += ["--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org"]
        ok = pip_run(args)
        return {"ok": ok, "message": "已跳过 SSL 验证"}

    elif fix_name == "switch_mirror":
        log("[INFO] 建议切换到国内镜像源（清华大学）")
        log("[INFO] 可在设置 → 镜像加速 中配置")
        return {"ok": False, "message": "请手动切换镜像源后重试"}

    elif fix_name == "install_vc_runtime":
        log("[INFO] 检测到需要 Visual C++ 运行时")
        log("[INFO] 请下载安装: https://aka.ms/vs/17/release/vc_redist.x64.exe")
        log("[INFO] 或尝试安装预编译的 wheel 包...")
        # 尝试安装 pipwin 来获取预编译包
        ok = pip_run(["install", "pipwin"])
        return {"ok": False,
                "message": "请安装 Visual C++ 运行时: https://aka.ms/vs/17/release/vc_redist.x64.exe"}

    elif fix_name == "install_build_tools":
        log("[INFO] 尝试安装构建工具...")
        ok = pip_run(["install", "wheel", "setuptools", "--upgrade"])
        log("[INFO] 建议安装 Visual Studio Build Tools:")
        log("[INFO] https://visualstudio.microsoft.com/visual-cpp-build-tools/")
        return {"ok": ok, "message": "已安装 wheel/setuptools，可能需要 Build Tools"}

    elif fix_name == "try_alternative_version":
        log("[INFO] 尝试不指定版本号安装...")
        missing = context.get("missing_packages", [])
        if missing:
            ok = pip_run(["install"] + missing)
            return {"ok": ok, "message": f"尝试安装: {missing}"}
        return {"ok": False, "message": "无法确定缺失的包"}

    elif fix_name == "install_missing_module":
        # 从错误信息中提取模块名
        module_match = re.search(
            r"No module named ['\"]([^'\"]+)['\"]",
            context.get("error_text", "")
        )
        if module_match:
            module = module_match.group(1).replace("_", "-")
            log(f"[INFO] 尝试安装缺失模块: {module}")
            ok = pip_run(["install", module])
            return {"ok": ok, "message": f"安装 {module} {'成功' if ok else '失败'}"}
        return {"ok": False, "message": "无法确定缺失模块名"}

    elif fix_name == "reinstall_charset":
        log("[INFO] 修复字符编码库冲突...")
        ok = pip_run(["install", "--force-reinstall", "charset-normalizer"])
        return {"ok": ok, "message": "重装 charset-normalizer"}

    elif fix_name == "check_python_version":
        log(f"[INFO] 当前 Python: {sys.version}")
        log("[INFO] 如果是语法错误，可能是代码需要更高版本的 Python")
        return {"ok": False, "message": "请检查项目要求的 Python 版本"}

    elif fix_name == "fix_permission":
        log("[INFO] 尝试使用用户级安装（--user）...")
        req_file = context.get("req_file", "")
        if req_file and os.path.exists(req_file):
            ok = pip_run(["install", "-r", req_file, "--user"])
            return {"ok": ok, "message": "已切换到 --user 安装模式"}
        return {"ok": False, "message": "权限不足，建议以管理员身份运行"}

    elif fix_name == "suggest_cpu_mode":
        log("[INFO] GPU 显存不足，建议:")
        log("[INFO]   1. 关闭其他占用 GPU 的程序")
        log("[INFO]   2. 减少 batch_size 参数")
        log("[INFO]   3. 使用 CPU 模式运行（速度较慢）")
        return {"ok": False, "message": "请减少 GPU 显存使用"}

    elif fix_name == "install_git_guide":
        log("[INFO] Git 未安装，请下载: https://git-scm.com/download/win")
        log("[INFO] 安装后请重启程序")
        return {"ok": False, "message": "请安装 Git 后重启"}

    return {"ok": False, "message": f"未知修复动作: {fix_name}"}


def collect_error_context(output_lines: list) -> str:
    """从输出行中提取最近的错误内容（最后50行）"""
    return "\n".join(output_lines[-50:]) if output_lines else ""
