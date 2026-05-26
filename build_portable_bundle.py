#!/usr/bin/env python3
"""Build a Windows portable bundle with common project runtimes included."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
DIST_DIR = PROJECT / "dist"
BUNDLE_DIR = DIST_DIR / "GitHub Hub Portable"
ARCHIVE_BASE = DIST_DIR / "GitHub-Hub-Portable-Windows-x64"
GIT_RELEASE_API = "https://api.github.com/repos/git-for-windows/git/releases/latest"


def copy_tree(source: Path, destination: Path):
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
    )


def download_mingit(destination: Path):
    request = urllib.request.Request(GIT_RELEASE_API, headers={"User-Agent": "GitHub-Hub-Builder/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.loads(response.read().decode("utf-8"))
    asset = next(
        (
            item for item in release.get("assets", [])
            if item.get("name", "").startswith("MinGit-")
            and item.get("name", "").endswith("-64-bit.zip")
            and "busybox" not in item.get("name", "").lower()
        ),
        None,
    )
    if not asset:
        raise RuntimeError("The latest Git for Windows release does not contain a 64-bit MinGit ZIP.")
    print(f"Downloading {asset['name']}...")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset["name"]
        urllib.request.urlretrieve(asset["browser_download_url"], archive)
        with zipfile.ZipFile(archive) as source_zip:
            source_zip.extractall(destination)


def copy_first_existing(sources: list[Path], destination: Path):
    for source in sources:
        if source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return


def download_text(url: str, destination: Path):
    request = urllib.request.Request(url, headers={"User-Agent": "GitHub-Hub-Builder/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


def build_bundle(python_source: Path, node_source: Path):
    exe = DIST_DIR / "GitHub Hub.exe"
    if not exe.is_file():
        raise FileNotFoundError("dist/GitHub Hub.exe not found. Run build_exe.py onefile first.")
    if not (python_source / "python.exe").is_file():
        raise FileNotFoundError(f"Python runtime missing from {python_source}")
    if not (node_source / "node.exe").is_file():
        raise FileNotFoundError(f"Node runtime missing from {node_source}")

    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    BUNDLE_DIR.mkdir(parents=True)
    runtimes = BUNDLE_DIR / "runtimes"

    shutil.copy2(exe, BUNDLE_DIR / exe.name)
    copy_first_existing([PROJECT / "README.md"], BUNDLE_DIR / "README.md")
    (BUNDLE_DIR / "使用说明.txt").write_text(
        """GitHub Hub 离线增强版使用说明
===========================
1. 解压整个文件夹后，双击 "GitHub Hub.exe" 启动
2. 请勿只复制 EXE，runtimes 文件夹包含内置 Git、Python 与 Node.js/npm
3. 配置、日志与下载项目存储于 %LOCALAPPDATA%\\GitHub Hub
4. Docker Compose 项目仍需要安装并启动 Docker Desktop
5. Go、Rust、GPU/CUDA 项目仍需要相应外部环境

系统要求：Windows 10/11, 64位
""",
        encoding="utf-8",
    )

    print(f"Bundling Python from {python_source}...")
    copy_tree(python_source, runtimes / "python")
    print(f"Bundling Node.js from {node_source}...")
    copy_tree(node_source, runtimes / "node")
    download_mingit(runtimes / "git")

    licenses = BUNDLE_DIR / "licenses"
    copy_first_existing(
        [python_source / "LICENSE.txt", python_source / "LICENSE"],
        licenses / "PYTHON_LICENSE.txt",
    )
    node_version = subprocess.run(
        [str(node_source / "node.exe"), "--version"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    download_text(
        f"https://raw.githubusercontent.com/nodejs/node/{node_version}/LICENSE",
        licenses / "NODE_LICENSE.txt",
    )
    copy_first_existing(
        [runtimes / "git" / "LICENSE.txt",
         runtimes / "git" / "mingw64" / "share" / "licenses" / "git" / "COPYING",
         runtimes / "git" / "COPYING"],
        licenses / "GIT_LICENSE.txt",
    )
    shutil.copy2(PROJECT / "THIRD_PARTY_NOTICES.txt", BUNDLE_DIR / "THIRD_PARTY_NOTICES.txt")

    archive = Path(shutil.make_archive(str(ARCHIVE_BASE), "zip", DIST_DIR, BUNDLE_DIR.name))
    total_mb = sum(path.stat().st_size for path in BUNDLE_DIR.rglob("*") if path.is_file()) / 1024 / 1024
    archive_mb = archive.stat().st_size / 1024 / 1024
    print(f"Portable bundle ready: {BUNDLE_DIR} ({total_mb:.1f} MB)")
    print(f"Portable ZIP ready: {archive} ({archive_mb:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-exe-build", action="store_true")
    parser.add_argument("--python-source", default=str(Path(sys.executable).resolve().parent))
    node_default = shutil.which("node") or ""
    parser.add_argument("--node-source", default=str(Path(node_default).resolve().parent) if node_default else "")
    args = parser.parse_args()

    if not args.skip_exe_build:
        subprocess.run([sys.executable, str(PROJECT / "build_exe.py"), "--clean", "onefile"], check=True)
    build_bundle(Path(args.python_source), Path(args.node_source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
