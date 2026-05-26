#!/usr/bin/env python3
"""
GitHub Hub - PyInstaller 打包脚本
"""
import os, sys, subprocess, shutil

PROJECT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT, "dist")
BUILD_DIR = os.path.join(PROJECT, "build")

def clean():
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d); print(f"Cleaned: {d}")
    generated_spec = os.path.join(PROJECT, "GitHub Hub.spec")
    if os.path.exists(generated_spec):
        os.remove(generated_spec); print(f"Cleaned: {generated_spec}")

def build(mode="onefile"):
    print(f"Building GitHub Hub ({mode})...")
    os.chdir(PROJECT)
    
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", "GitHub Hub",
        "--windowed",
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtNetwork",
        "--hidden-import", "git",
        "--hidden-import", "github",
        "--hidden-import", "requests",
        "--hidden-import", "yaml",
        "--hidden-import", "psutil",
        "--exclude-module", "PySide6.QtBluetooth",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.Qt3DRender",
        "--exclude-module", "PySide6.Qt3DInput",
        "--exclude-module", "PySide6.Qt3DLogic",
        "--exclude-module", "PySide6.Qt3DAnimation",
        "--exclude-module", "PySide6.Qt3DExtras",
        "--exclude-module", "PySide6.QtCharts",
        "--exclude-module", "PySide6.QtDataVisualization",
        "--exclude-module", "PySide6.QtGraphs",
        "--exclude-module", "PySide6.QtHttpServer",
        "--exclude-module", "PySide6.QtLocation",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "PySide6.QtMultimediaWidgets",
        "--exclude-module", "PySide6.QtNfc",
        "--exclude-module", "PySide6.QtOpenGL",
        "--exclude-module", "PySide6.QtOpenGLWidgets",
        "--exclude-module", "PySide6.QtPositioning",
        "--exclude-module", "PySide6.QtPrintSupport",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtQuick3D",
        "--exclude-module", "PySide6.QtRemoteObjects",
        "--exclude-module", "PySide6.QtSensors",
        "--exclude-module", "PySide6.QtSerialPort",
        "--exclude-module", "PySide6.QtShaderTools",
        "--exclude-module", "PySide6.QtSpatialAudio",
        "--exclude-module", "PySide6.QtSpeech",
        "--exclude-module", "PySide6.QtSql",
        "--exclude-module", "PySide6.QtSvgWidgets",
        "--exclude-module", "PySide6.QtTest",
        "--exclude-module", "PySide6.QtTextToSpeech",
        "--exclude-module", "PySide6.QtUiTools",
        "--exclude-module", "PySide6.QtWebChannel",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtWebEngineQuick",
        "--exclude-module", "PySide6.QtWebSockets",
        "main.py"
    ]

    support_assets = [
        os.path.join(PROJECT, "assets", "support", "alipay_qr.jpg"),
        os.path.join(PROJECT, "assets", "support", "wechat_pay_qr.png"),
    ]
    add_data = []
    for support_asset in support_assets:
        if os.path.isfile(support_asset):
            add_data.extend(["--add-data", f"{support_asset};assets/support"])
    if add_data:
        entry_index = cmd.index("main.py")
        cmd[entry_index:entry_index] = add_data
    
    if mode == "onefile":
        cmd.insert(cmd.index("--windowed") + 1, "--onefile")
    
    print("Running PyInstaller...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("Build failed!")
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        return False
    
    # Report size
    if mode == "onefile":
        exe_path = os.path.join(DIST_DIR, "GitHub Hub.exe")
        if os.path.exists(exe_path):
            mb = os.path.getsize(exe_path) / 1024 / 1024
            print(f"Build successful! Single EXE: {mb:.1f} MB")
    else:
        folder = os.path.join(DIST_DIR, "GitHub Hub")
        total = sum(f.stat().st_size for f in os.scandir(folder) if f.is_file())
        total += sum(f.stat().st_size for d in os.scandir(folder) if d.is_dir() for f in os.scandir(d.path) if f.is_file())
        print(f"Build successful! Folder: {total / 1024 / 1024:.1f} MB")
    
    # Copy helper files. User config is deliberately never bundled.
    dst = os.path.join(DIST_DIR, "GitHub Hub") if mode == "onedir" else DIST_DIR
    if mode == "onedir":
        for fn in ["README.md"]:
            shutil.copy2(os.path.join(PROJECT, fn), dst)
    with open(os.path.join(dst, "使用说明.txt"), "w", encoding="utf-8") as f:
        f.write("""GitHub Hub 使用说明
===================
1. 双击 "GitHub Hub.exe" 启动
2. 程序配置与下载项目存储于 %LOCALAPPDATA%\\GitHub Hub
3. 克隆 GitHub 项目需要系统已安装 Git: https://git-scm.com/downloads
4. Docker Compose 项目需要 Docker Desktop 已安装并启动
5. Node/Go/Rust 项目仍需要对应运行时

系统要求：Windows 10/11, 64位
""")

    return True

if __name__ == "__main__":
    mode = "onefile"
    for arg in sys.argv[1:]:
        if arg == "--clean":
            clean()
        elif arg in ("onefile", "onedir"):
            mode = arg
    build(mode)
