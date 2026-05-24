"""
mirror_manager.py — 镜像加速管理
为无法访问 GitHub/PyPI 的用户提供国内镜像源
"""
import re
from typing import Optional

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
    import time
    import requests
    try:
        start = time.time()
        requests.get(url, timeout=timeout, stream=True)
        return round(time.time() - start, 3)
    except Exception:
        return -1.0


def get_best_pip_mirror() -> str:
    """自动检测最快的 pip 镜像"""
    import concurrent.futures
    candidates = {
        k: v for k, v in PIP_MIRRORS.items() if v
    }
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(test_mirror_speed, url): name
                   for name, url in candidates.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                t = future.result()
                results[name] = t
            except Exception:
                results[name] = -1.0
    # 选出响应最快的
    valid = {k: v for k, v in results.items() if v >= 0}
    if valid:
        return min(valid, key=valid.get)
    return "清华大学 TUNA"
