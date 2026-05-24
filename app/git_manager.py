"""
git_manager.py — Git 操作封装
负责克隆、拉取更新、获取状态等 Git 相关操作
"""
import os
import re
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

try:
    import git
    from git import Repo, InvalidGitRepositoryError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


def sanitize_git_url(url: str) -> str:
    """清洗 Git URL，移除无效字符（如 # ）"""
    import re
    url = url.strip()
    # 移除 # 和其后所有内容
    url = re.sub(r'#.*', '', url)
    # 确保 .git 后缀
    if url.startswith("https://github.com/") and not url.endswith('.git'):
        url = url.rstrip('/') + '.git'
    return url


@dataclass
class GitCommandResult:
    output: str
    returncode: int


class GitCommandError(RuntimeError):
    def __init__(self, args: list, output: str, returncode: int):
        self.args_list = args
        self.output = output
        self.returncode = returncode
        tail = "\n".join(output.splitlines()[-8:]) if output else ""
        super().__init__(tail or f"git exited with code {returncode}")


def _run_git(args: list, cwd: str = None, callback: Callable = None,
             check: bool = True, timeout: int = 1800) -> GitCommandResult:
    """运行 git 命令，支持实时输出回调，带超时机制"""
    import threading as _threading
    cmd = ["git"] + args
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        env=env,
    )
    output_lines = []
    stopped = _threading.Event()

    def _git_reader():
        try:
            for line in iter(process.stdout.readline, ""):
                if stopped.is_set():
                    break
                line = line.rstrip("\r\n")
                output_lines.append(line)
                if callback and line:
                    try:
                        callback(line)
                    except RuntimeError:
                        pass
        except (ValueError, OSError):
            pass

    reader = _threading.Thread(target=_git_reader, daemon=True)
    reader.start()

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        stopped.set()
        process.kill()
        if callback:
            try:
                callback("[ERROR] Git operation timed out, process killed")
            except RuntimeError:
                pass

    reader.join(timeout=5)
    stopped.set()
    returncode = process.wait()
    output = "\n".join(output_lines)
    if check and returncode != 0:
        raise GitCommandError(args, output, returncode)
    return GitCommandResult(output=output, returncode=returncode)


def parse_github_url(url: str) -> dict:
    """解析 GitHub URL，返回 owner/repo/branch 信息"""
    url = url.strip().rstrip("/")
    owner, repo, branch = "", "", None
    if url.startswith("git@github.com:"):
        parts = url[len("git@github.com:"):].split("/")
        if len(parts) == 2:
            owner, repo = parts
    else:
        parsed = urllib.parse.urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc.lower() == "github.com" and len(parts) >= 2:
            owner, repo = parts[:2]
            if len(parts) >= 4 and parts[2] == "tree":
                branch = "/".join(parts[3:])
            elif len(parts) != 2:
                return {}
        elif parsed.netloc.lower() == "api.github.com" and len(parts) == 3 and parts[0] == "repos":
            owner, repo = parts[1:]
    if owner and repo:
        repo = repo[:-4] if repo.endswith(".git") else repo
        if not repo:
            return {}
        return {
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "clone_url": f"https://github.com/{owner}/{repo}.git",
            "api_url": f"https://api.github.com/repos/{owner}/{repo}",
        }
    return {}



def get_github_info(owner: str, repo: str, token: str = None) -> dict:
    """通过 GitHub API 获取项目信息"""
    import requests
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers, timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            return {
                "name": data.get("name", repo),
                "full_name": data.get("full_name", f"{owner}/{repo}"),
                "description": data.get("description", ""),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "language": data.get("language", "Unknown"),
                "default_branch": data.get("default_branch", "main"),
                "homepage": data.get("homepage", ""),
                "topics": data.get("topics", []),
                "updated_at": data.get("updated_at", ""),
                "clone_url": data.get("clone_url", ""),
                "html_url": data.get("html_url", ""),
            }
    except Exception:
        pass
    return {
        "name": repo, "full_name": f"{owner}/{repo}",
        "description": "", "stars": 0, "forks": 0,
        "language": "Unknown", "default_branch": "main",
        "clone_url": f"https://github.com/{owner}/{repo}.git",
        "html_url": f"https://github.com/{owner}/{repo}",
    }


def get_readme(owner: str, repo: str, token: str = None) -> str:
    """获取项目 README 内容"""
    import requests
    headers = {"Accept": "application/vnd.github.raw+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for filename in ["README.md", "README.rst", "README.txt", "README"]:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{filename}",
                headers=headers, timeout=15
            )
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    return "暂无 README 内容"


def is_complete_git_repo(repo_dir: str) -> bool:
    """Return True only when repo_dir is a usable checkout with a HEAD commit."""
    git_dir = os.path.join(repo_dir, ".git")
    if not os.path.isdir(git_dir):
        return False
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if inside.returncode != 0 or inside.stdout.strip().lower() != "true":
            return False
        head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return head.returncode == 0
    except Exception:
        return False


def clone_repo(clone_url: str, target_dir: str,
               branch: str = None, callback: Callable = None) -> bool:
    """克隆仓库到目标目录"""
    target_path = Path(target_dir)
    parent_dir = target_path.parent
    try:
        parent_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        if callback:
            callback(f"[ERROR] 创建目标目录失败: {e}")
        return False

    if target_path.exists() and not target_path.is_dir():
        if callback:
            callback(f"[ERROR] 目标路径已存在且不是目录: {target_dir}")
        return False
    target_was_empty = not target_path.exists() or not any(target_path.iterdir())
    if target_path.exists() and not target_was_empty:
        if (target_path / ".git").is_dir():
            if not is_complete_git_repo(target_dir):
                if callback:
                    callback(f"[ERROR] 目标目录已包含未完成提交的 Git 仓库，已拒绝覆盖: {target_dir}")
                return False
            else:
                if callback:
                    callback(f"[INFO] 仓库已存在: {target_dir}")
                return True
        else:
            if callback:
                callback(f"[ERROR] 目标目录已存在且不是 Git 仓库: {target_dir}")
            return False

    args = ["-c", "core.longpaths=true", "clone", "--progress", "--recurse-submodules"]
    if branch:
        args += ["-b", branch]
    args += [clone_url, target_dir]
    try:
        _run_git(args, callback=callback, check=True)
        return os.path.isdir(os.path.join(target_dir, ".git"))
    except GitCommandError as e:
        if callback:
            callback(f"[ERROR] 克隆失败 (git exit {e.returncode}): {e}")
        if target_was_empty and target_path.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False
    except Exception as e:
        if callback:
            callback(f"[ERROR] 克隆失败: {e}")
        return False


def pull_repo(repo_dir: str, callback: Callable = None) -> bool:
    """拉取最新代码"""
    try:
        _run_git(["-c", "core.longpaths=true", "pull", "--progress", "--recurse-submodules"],
                 cwd=repo_dir, callback=callback, check=True)
        return True
    except Exception as e:
        if callback:
            callback(f"[ERROR] 更新失败: {e}")
        return False


def get_repo_status(repo_dir: str) -> dict:
    """获取仓库状态"""
    result = {
        "is_git_repo": False,
        "current_branch": "",
        "last_commit": "",
        "last_commit_msg": "",
        "has_updates": False,
        "remote_url": "",
    }
    git_dir = os.path.join(repo_dir, ".git")
    if not os.path.isdir(git_dir):
        return result
    result["is_git_repo"] = True
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        ).strip()
        result["current_branch"] = branch

        commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%h %s %cr"],
            cwd=repo_dir, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        ).strip()
        result["last_commit"] = commit

        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_dir, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        ).strip()
        result["remote_url"] = remote
    except Exception:
        pass
    return result


def check_for_updates(repo_dir: str, callback: Callable = None) -> bool:
    """检查是否有更新可用（fetch remote）"""
    try:
        _run_git(["fetch", "--dry-run"], cwd=repo_dir, callback=callback, check=True)
        result = subprocess.check_output(
            ["git", "rev-list", "HEAD..origin/HEAD", "--count"],
            cwd=repo_dir, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        ).strip()
        return int(result) > 0
    except Exception:
        return False
