"""
self_updater.py - GitHub Hub 程序自更新模块
支持：检查更新 / 下载更新 / 应用更新 / 重启程序
"""
import os
import sys
import json
import shutil
import tempfile
import zipfile
import subprocess
from pathlib import Path
from typing import Callable, Optional

import requests

# GitHub Hub 的默认仓库地址（用户可在设置中修改）
DEFAULT_GITHUB_REPO = ""
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


def get_githug_repo_url(config: dict = None) -> str:
    """获取配置中的 githug 仓库 URL"""
    if config and config.get("githug_repo"):
        return config["githug_repo"]
    return DEFAULT_GITHUB_REPO


def get_current_version() -> str:
    """获取当前程序版本（从 config 或 main.py）"""
    try:
        config_path = CONFIG_FILE
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg.get("version"):
                return cfg["version"]
    except Exception:
        pass
    return "1.0.0"


def get_githug_root() -> str:
    """获取 githug 程序根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_githug_exe() -> str:
    """获取当前 Python 入口脚本路径"""
    return os.path.join(get_githug_root(), "main.py")


def check_for_updates(config: dict, callback: Callable = None) -> dict:
    """
    检查 GitHub Hub 自身更新
    返回: {"has_update": bool, "latest_version": str, "release_notes": str, "error": str}
    """
    result = {
        "has_update": False,
        "latest_version": "",
        "current_version": get_current_version(),
        "release_notes": "",
        "error": "",
    }

    repo_url = get_githug_repo_url(config)
    if not repo_url:
        if callback:
            callback("[INFO] 未配置 GitHub Hub 仓库地址，跳过自更新检查")
        result["error"] = "未配置仓库地址"
        return result

    from .git_manager import parse_github_url
    parsed_repo = parse_github_url(repo_url)
    owner = parsed_repo.get("owner", "")
    repo = parsed_repo.get("repo", "")

    if not owner or not repo:
        if callback:
            callback(f"[WARN] 无法解析仓库地址: {repo_url}")
        result["error"] = "无法解析仓库地址"
        return result

    # 1. 通过 GitHub API 获取最新 release 信息
    token = config.get("github_token", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        if callback:
            callback(f"[INFO] 正在检查更新: {owner}/{repo} ...")

        r = requests.get(api_url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            latest_tag = data.get("tag_name", "")
            result["latest_version"] = latest_tag.lstrip("v")
            result["release_notes"] = data.get("body", "")

            # 比较版本
            current = result["current_version"]
            latest = result["latest_version"]
            if latest and latest != current:
                # 简单比较版本号（后续可用 packaging 库做精确比较）
                try:
                    curr_parts = [int(x) for x in current.split(".")]
                    latest_parts = [int(x) for x in latest.split(".")]
                    # 补齐长度
                    while len(curr_parts) < len(latest_parts):
                        curr_parts.append(0)
                    while len(latest_parts) < len(curr_parts):
                        latest_parts.append(0)
                    result["has_update"] = latest_parts > curr_parts
                except ValueError:
                    result["has_update"] = latest != current

            if callback:
                if result["has_update"]:
                    callback(f"[SUCCESS] 发现新版本: v{latest} (当前: v{current})")
                else:
                    callback(f"[SUCCESS] 当前已是最新版本: v{current}")
            return result
        else:
            # API 失败时，回退到检查 default branch 的提交
            if callback:
                callback(f"[WARN] 获取 release 信息失败 (HTTP {r.status_code})，回退到检查代码更新...")
            return _check_via_git(owner, repo, config, callback, result)
    except requests.RequestException as e:
        if callback:
            callback(f"[WARN] 网络请求失败 ({e})，回退到 Git 检查...")
        return _check_via_git(owner, repo, config, callback, result)


def _check_via_git(owner: str, repo: str, config: dict,
                   callback: Callable, result: dict) -> dict:
    """备用方案：通过 git 命令检查更新"""
    githug_root = get_githug_root()
    git_dir = os.path.join(githug_root, ".git")

    # 如果 githug 本身就是 git 仓库
    if os.path.isdir(git_dir):
        try:
            if callback:
                callback("[INFO] 正在拉取最新代码信息...")
            # fetch
            subprocess.run(
                ["git", "fetch", "--quiet"],
                cwd=githug_root,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            # 检查是否有更新
            r = subprocess.run(
                ["git", "rev-list", "HEAD..origin/HEAD", "--count"],
                cwd=githug_root,
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            count = r.stdout.strip()
            if count and count.isdigit() and int(count) > 0:
                result["has_update"] = True
                result["latest_version"] = f"commit+{count} ahead"
                if callback:
                    callback(f"[SUCCESS] 发现 {count} 个新提交待更新")
            else:
                if callback:
                    callback("[SUCCESS] 当前已是最新代码")
            return result
        except Exception as e:
            if callback:
                callback(f"[ERROR] Git 检查失败: {e}")
            result["error"] = str(e)
            return result
    else:
        if callback:
            callback("[WARN] githug 不是 git 仓库，无法通过 git 检查更新")
        result["error"] = "githug 不是 git 仓库"
        return result


def apply_update(config: dict, callback: Callable = None) -> bool:
    """
    应用更新：从 GitHub 拉取最新代码
    返回 True 表示更新成功，需要重启
    """
    githug_root = get_githug_root()
    git_dir = os.path.join(githug_root, ".git")

    # 方式1：如果本身就是 git 仓库，直接 git pull
    if os.path.isdir(git_dir):
        if callback:
            callback("[INFO] 正在拉取最新代码 (git pull)...")
        try:
            process = subprocess.Popen(
                ["git", "pull", "--progress"],
                cwd=githug_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for line in process.stdout:
                line = line.rstrip()
                if callback:
                    callback(line)
            process.wait()
            if process.returncode == 0:
                if callback:
                    callback("[SUCCESS] 代码更新成功！请重启程序以应用更新。")
                return True
            else:
                if callback:
                    callback("[ERROR] Git pull 失败")
                return False
        except Exception as e:
            if callback:
                callback(f"[ERROR] Git pull 异常: {e}")
            return False

    # 方式2：非 git 仓库，下载 ZIP 包然后解压覆盖
    repo_url = get_githug_repo_url(config)
    from .git_manager import parse_github_url
    parsed_repo = parse_github_url(repo_url)
    if not parsed_repo:
        if callback:
            callback("[ERROR] 无法解析仓库地址下载更新")
        return False

    owner, repo = parsed_repo["owner"], parsed_repo["repo"]
    branch = config.get("githug_branch", "main")
    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"

    if callback:
        callback(f"[INFO] 正在从 {owner}/{repo} 下载更新包...")

    try:
        r = requests.get(zip_url, stream=True, timeout=60)
        if r.status_code != 200:
            if callback:
                callback(f"[ERROR] 下载失败 (HTTP {r.status_code})")
            return False

        # 解压到临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "update.zip")
            with open(zip_path, "wb") as f:
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0 and callback:
                            pct = int(downloaded * 100 / total)
                            callback(f"[INFO] 下载进度: {pct}% ({downloaded//1024}KB / {total//1024}KB)")

            if callback:
                callback("[INFO] 正在解压更新包...")

            with zipfile.ZipFile(zip_path, "r") as zf:
                # 检查 ZIP 内部目录结构（通常是 repo-branch/）
                top_dirs = set()
                for name in zf.namelist():
                    parts = name.split("/")
                    if len(parts) > 1:
                        top_dirs.add(parts[0])

                if len(top_dirs) == 1:
                    inner_dir = list(top_dirs)[0]
                    extract_to = os.path.join(tmpdir, "extracted")
                    zf.extractall(extract_to)
                    src = os.path.join(extract_to, inner_dir)
                else:
                    src = tmpdir
                    zf.extractall(src)

                # 备份并覆盖
                backup_dir = os.path.join(githug_root, ".backup_update")
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir)

                if callback:
                    callback("[INFO] 正在应用更新（备份当前文件）...")

                # 排除备份和临时文件
                exclude = {".backup_update", "__pycache__", ".git", ".venv",
                           "venv", "node_modules", "projects", "shared_packages",
                           "pip_cache", "config.json"}

                # 复制新文件到 githug 根目录
                for item in os.listdir(src):
                    s = os.path.join(src, item)
                    d = os.path.join(githug_root, item)
                    if item in exclude:
                        if callback:
                            callback(f"[INFO] 跳过: {item}")
                        continue
                    if os.path.exists(d):
                        # 备份
                        backup_item = os.path.join(backup_dir, item)
                        os.makedirs(os.path.dirname(backup_item), exist_ok=True)
                        if os.path.isfile(d):
                            shutil.copy2(d, backup_item)
                        elif os.path.isdir(d):
                            if os.path.exists(backup_item):
                                shutil.rmtree(backup_item)
                            shutil.copytree(d, backup_item)
                    if os.path.isdir(s):
                        if os.path.exists(d):
                            shutil.rmtree(d)
                        shutil.copytree(s, d)
                    else:
                        shutil.copy2(s, d)

                if callback:
                    callback("[SUCCESS] 更新应用完成！请重启程序。")
                return True

    except Exception as e:
        if callback:
            callback(f"[ERROR] 更新失败: {e}")
        return False


def restart_program():
    """重启当前程序"""
    python = sys.executable
    script = get_githug_exe()
    try:
        subprocess.Popen(
            [python, script],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        sys.exit(0)
    except Exception as e:
        print(f"重启失败: {e}")
        sys.exit(1)
