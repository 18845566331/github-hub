"""
mirror_manager.py - network preflight and mirror acceleration.

The operation path calls this module immediately before downloading.  Python
and npm registries may be selected automatically; GitHub remains direct-first
and only falls back to a configured/tested relay when direct Git access fails.
"""
import concurrent.futures
import os
import re
import subprocess
import time
from typing import Callable, Optional

# ──────────────────────────────────────────────
# pip 镜像源
# ──────────────────────────────────────────────
PIP_MIRRORS = {
    "官方 PyPI (默认)": "",
    "清华大学 TUNA":    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "阿里云":           "https://mirrors.aliyun.com/pypi/simple/",
    "中科大 USTC":      "https://pypi.mirrors.ustc.edu.cn/simple/",
    "豆瓣":             "https://pypi.doubanio.com/simple/",
    "腾讯云":           "https://mirrors.cloud.tencent.com/pypi/simple/",
    "华为云":           "https://repo.huaweicloud.com/repository/pypi/simple/",
}

# ──────────────────────────────────────────────
# GitHub 镜像/代理
# ──────────────────────────────────────────────
GITHUB_MIRRORS = {
    "直连 GitHub (默认)":  "",
    "ghproxy.com 代理":   "https://ghproxy.com/",
    "GitClone 代理":      "https://gitclone.com/github.com/",
    "FastGit 镜像":       "https://hub.fastgit.xyz/",
    "Gitee 镜像":         "gitee",   # 特殊处理：需要手动同步
    "镜像站 kkgithub":    "https://kkgithub.com/",
}

# ──────────────────────────────────────────────
# npm 镜像
# ──────────────────────────────────────────────
NPM_MIRRORS = {
    "官方 npm (默认)":  "",
    "淘宝 npmmirror":  "https://registry.npmmirror.com",
    "腾讯云":          "https://mirrors.cloud.tencent.com/npm/",
    "华为云":          "https://repo.huaweicloud.com/repository/npm/",
}


def transform_clone_url(original_url: str, mirror_key: str) -> str:
    """
    将 GitHub clone URL 转换为镜像 URL
    original_url: https://github.com/owner/repo.git
    """
    if not mirror_key or mirror_key == "直连 GitHub (默认)":
        return original_url

    prefix = GITHUB_MIRRORS.get(mirror_key, "")
    if not prefix:
        return original_url

    if prefix == "gitee":
        # Gitee 需要提前 fork/同步，无法自动转换
        return original_url

    if "ghproxy.com" in prefix:
        # https://ghproxy.com/https://github.com/...
        return prefix + original_url

    if "gitclone.com" in prefix:
        # https://gitclone.com/github.com/owner/repo.git
        return original_url.replace("https://github.com/", prefix)

    if "fastgit" in prefix or "kkgithub" in prefix:
        # 直接替换域名
        return original_url.replace("github.com", prefix.rstrip("/").split("//")[-1])

    return original_url


def build_pip_args(mirror_key: str) -> list:
    """
    构建 pip 镜像参数
    返回类似 ["-i", "https://...", "--trusted-host", "..."] 的参数列表
    """
    if not mirror_key or mirror_key == "官方 PyPI (默认)":
        return []

    url = PIP_MIRRORS.get(mirror_key, "")
    if not url:
        return []

    # 提取 host 用于 --trusted-host
    host_match = re.match(r"https?://([^/]+)", url)
    host = host_match.group(1) if host_match else ""

    args = ["-i", url]
    if host:
        args += ["--trusted-host", host]
    return args


def build_npm_args(mirror_key: str) -> list:
    """构建 npm registry 参数"""
    if not mirror_key or mirror_key == "官方 npm (默认)":
        return []
    url = NPM_MIRRORS.get(mirror_key, "")
    if not url:
        return []
    return ["--registry", url]


def test_mirror_speed(url: str, timeout: int = 5) -> float:
    """
    测试镜像速度（返回响应时间秒，失败返回 -1）
    """
    import requests
    try:
        start = time.time()
        response = requests.get(url, timeout=timeout, stream=True)
        try:
            if response.status_code >= 400:
                return -1.0
            return round(time.time() - start, 3)
        finally:
            response.close()
    except Exception:
        return -1.0


def get_best_pip_mirror() -> str:
    """Auto-detect the quickest reachable pip registry."""
    return choose_pip_mirror("官方 PyPI (默认)", True)


def _emit(callback: Optional[Callable], message: str):
    if callback:
        callback(message)


def _select_http_source(
    sources: dict, official_name: str, official_url: str, preferred: str,
    auto_select: bool, callback: Optional[Callable], label: str,
) -> str:
    preferred = preferred if preferred in sources else official_name
    if not auto_select:
        return preferred
    candidates = {name: (url or official_url) for name, url in sources.items()}
    _emit(callback, f"[INFO] 网络预检: 正在检测 {label} 下载链路...")
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(candidates))) as ex:
        futures = {
            ex.submit(test_mirror_speed, url): name for name, url in candidates.items()
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception:
                results[name] = -1.0
    valid = {name: seconds for name, seconds in results.items() if seconds >= 0}
    if not valid:
        _emit(callback, f"[WARN] 网络预检: {label} 链路均不可达，继续使用设置源 {preferred}")
        return preferred
    selected = min(valid, key=valid.get)
    seconds = valid[selected]
    action = "自动切换" if selected != preferred else "使用"
    _emit(callback, f"[INFO] 网络预检: {action} {label} 源 {selected} ({seconds:.3f}s)")
    return selected


def choose_pip_mirror(
    preferred: str = "官方 PyPI (默认)", auto_select: bool = True,
    callback: Optional[Callable] = None,
) -> str:
    """Return a reachable pip source for the upcoming operation."""
    return _select_http_source(
        PIP_MIRRORS, "官方 PyPI (默认)", "https://pypi.org/simple/",
        preferred, auto_select, callback, "PyPI",
    )


def choose_npm_mirror(
    preferred: str = "官方 npm (默认)", auto_select: bool = True,
    callback: Optional[Callable] = None,
) -> str:
    """Return a reachable npm registry for the upcoming operation."""
    return _select_http_source(
        NPM_MIRRORS, "官方 npm (默认)", "https://registry.npmjs.org/",
        preferred, auto_select, callback, "npm",
    )


def test_git_remote(url: str, timeout: int = 8) -> float:
    """Test the actual Git transport for a repository URL."""
    try:
        started = time.time()
        result = subprocess.run(
            ["git", "ls-remote", url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            return -1.0
        return round(time.time() - started, 3)
    except Exception:
        return -1.0


def get_git_clone_candidates(
    original_url: str, preferred: str = "直连 GitHub (默认)",
    auto_select: bool = True, callback: Optional[Callable] = None,
) -> list[tuple[str, str]]:
    """Build tested clone URLs, preserving direct GitHub as the first choice."""
    preferred = preferred if preferred in GITHUB_MIRRORS else "直连 GitHub (默认)"
    names = [preferred, "直连 GitHub (默认)"]
    if auto_select:
        names += [
            name for name in GITHUB_MIRRORS
            if name not in names and name != "Gitee 镜像"
        ]
    ordered = []
    for name in names:
        url = transform_clone_url(original_url, name)
        if not any(existing_url == url for _, existing_url in ordered):
            ordered.append((name, url))
    if not auto_select:
        return ordered[:1]
    _emit(callback, "[INFO] 网络预检: 正在检测 Git 克隆链路...")
    scores = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(ordered))) as ex:
        futures = {ex.submit(test_git_remote, url): (name, url) for name, url in ordered}
        for future in concurrent.futures.as_completed(futures):
            name, url = futures[future]
            try:
                scores[url] = future.result()
            except Exception:
                scores[url] = -1.0
    direct_url = transform_clone_url(original_url, "直连 GitHub (默认)")
    reachable = [(name, url) for name, url in ordered if scores.get(url, -1) >= 0]
    if scores.get(direct_url, -1) >= 0:
        reachable.sort(key=lambda pair: (pair[1] != direct_url, scores[pair[1]]))
        _emit(callback, f"[INFO] 网络预检: GitHub 直连可用 ({scores[direct_url]:.3f}s)")
        return reachable
    if reachable:
        reachable.sort(key=lambda pair: scores[pair[1]])
        name, url = reachable[0]
        _emit(callback, f"[WARN] GitHub 直连不可达，将回退到第三方克隆链路: {name}")
        _emit(callback, f"[WARN] 回退地址: {url}")
        return reachable
    _emit(callback, "[WARN] 网络预检: 未发现可达 Git 链路，仍将尝试设置源并保留错误日志")
    return ordered
