"""
diagnostics_dialog.py — 诊断 UI 对话框
"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTabWidget, QWidget,
    QProgressBar, QTextEdit, QSplitter,
    QTreeWidget, QTreeWidgetItem, QGroupBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QTextCursor, QTextCharFormat

from .workers import ProgressWorker
from .diagnostics import run_full_diagnostics, check_project_requirements
from .auto_fixer import auto_fix
from .utils import get_default_python_executable


class DiagnosticsDialog(QDialog):
    """环境诊断与自动修复对话框"""

    append_requested = Signal(int, str)

    def __init__(self, config: dict = None, project: dict = None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.project = project
        self._diag_results = {}
        self._output_lines = []
        self._active_workers = set()
        self.setWindowTitle("🔍  环境诊断与自动修复")
        self.setModal(False)
        self.setMinimumSize(820, 640)
        self._setup_ui()
        self.append_requested.connect(self._do_append, Qt.ConnectionType.QueuedConnection)

    def _start_worker(self, worker):
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda w=worker: self._active_workers.discard(w))
        QThreadPool.globalInstance().start(worker)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题栏
        header = QFrame()
        header.setStyleSheet("border-bottom: 1px solid #21262d;")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 8, 20, 8)
        title = QLabel("🔍  系统环境诊断与自动修复")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        hl.addWidget(title)
        hl.addStretch()
        if self.project:
            proj_lbl = QLabel(f"项目: {self.project.get('name', '')}")
            proj_lbl.setStyleSheet("color: #7c4dff; font-size: 12px;")
            hl.addWidget(proj_lbl)
        layout.addWidget(header)

        # Tab
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ── Tab 1: 全系统诊断 ──
        tab1 = QWidget()
        t1_layout = QVBoxLayout(tab1)
        t1_layout.setContentsMargins(12, 12, 12, 12)
        t1_layout.setSpacing(10)

        btn_row1 = QHBoxLayout()
        self.btn_run_diag = QPushButton("▶  开始全系统诊断")
        self.btn_run_diag.setFixedHeight(36)
        self.btn_run_diag.setStyleSheet("font-weight: 600; padding: 0 16px;")
        self.btn_run_diag.clicked.connect(self._run_system_diag)
        btn_row1.addWidget(self.btn_run_diag)

        self.btn_auto_fix = QPushButton("🔧  自动修复问题")
        self.btn_auto_fix.setFixedHeight(36)
        self.btn_auto_fix.setEnabled(False)
        self.btn_auto_fix.setStyleSheet("font-weight: 600; padding: 0 16px;")
        self.btn_auto_fix.clicked.connect(self._auto_fix_issues)
        btn_row1.addWidget(self.btn_auto_fix)
        btn_row1.addStretch()

        self.progress1 = QProgressBar()
        self.progress1.setRange(0, 0)
        self.progress1.setFixedHeight(4)
        self.progress1.setVisible(False)
        t1_layout.addWidget(self.progress1)

        t1_layout.addLayout(btn_row1)
        self.diag_output = self._make_console()
        t1_layout.addWidget(self.diag_output)
        self.tabs.addTab(tab1, "🔍 系统诊断")

        # ── Tab 2: 项目依赖检测 ──
        tab2 = QWidget()
        t2_layout = QVBoxLayout(tab2)
        t2_layout.setContentsMargins(12, 12, 12, 12)
        t2_layout.setSpacing(10)

        btn_row2 = QHBoxLayout()
        self.btn_check_proj = QPushButton("▶  检测项目依赖")
        self.btn_check_proj.setFixedHeight(36)
        self.btn_check_proj.setEnabled(bool(self.project))
        self.btn_check_proj.setStyleSheet("font-weight: 600; padding: 0 16px;")
        self.btn_check_proj.clicked.connect(self._check_project_deps)
        btn_row2.addWidget(self.btn_check_proj)

        self.btn_install_missing = QPushButton("📦  安装缺失包")
        self.btn_install_missing.setFixedHeight(36)
        self.btn_install_missing.setEnabled(False)
        self.btn_install_missing.setStyleSheet("""
            QPushButton { background: #166534; color: white; border: none;
                          border-radius: 6px; font-weight: 600; padding: 0 16px; }
            QPushButton:hover { background: #16a34a; }
            QPushButton:disabled { background: #21262d; color: #484f58; }
        """)
        self.btn_install_missing.clicked.connect(self._install_missing)
        btn_row2.addWidget(self.btn_install_missing)
        btn_row2.addStretch()
        t2_layout.addLayout(btn_row2)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.pkg_tree = QTreeWidget()
        self.pkg_tree.setHeaderLabels(["包名", "状态"])
        self.pkg_tree.setColumnWidth(0, 200)
        self.pkg_tree.setMaximumWidth(300)
        splitter.addWidget(self.pkg_tree)
        self.proj_output = self._make_console()
        splitter.addWidget(self.proj_output)
        splitter.setSizes([280, 400])
        t2_layout.addWidget(splitter)
        self.tabs.addTab(tab2, "📦 项目依赖")

        # ── Tab 3: 安装常用包 ──
        tab3 = QWidget()
        t3_layout = QVBoxLayout(tab3)
        t3_layout.setContentsMargins(12, 12, 12, 12)
        t3_layout.setSpacing(10)

        note = QLabel("预先安装常用依赖包，加速后续项目初始化（首次安装可能较慢）")
        note.setStyleSheet("color: #7c85a6; font-size: 12px;")
        note.setWordWrap(True)
        t3_layout.addWidget(note)

        self.common_pkg_tree = QTreeWidget()
        self.common_pkg_tree.setHeaderLabels(["包名", "描述", "是否已安装"])
        self.common_pkg_tree.setColumnWidth(0, 160)
        self.common_pkg_tree.setColumnWidth(1, 260)
        self._populate_common_packages()
        t3_layout.addWidget(self.common_pkg_tree)

        btn_row3 = QHBoxLayout()
        btn_refresh = QPushButton("🔄  刷新状态")
        btn_refresh.setFixedHeight(34)
        btn_refresh.clicked.connect(self._refresh_common_pkg_status)
        btn_row3.addWidget(btn_refresh)

        self.btn_install_common = QPushButton("📦  安装选中的包")
        self.btn_install_common.setFixedHeight(34)
        self.btn_install_common.setStyleSheet("""
            QPushButton { background: #166534; color: white; border: none;
                          border-radius: 6px; font-weight: 600; padding: 0 12px; }
            QPushButton:hover { background: #16a34a; }
        """)
        self.btn_install_common.clicked.connect(self._install_common_selected)
        btn_row3.addWidget(self.btn_install_common)

        btn_install_all = QPushButton("⚡  一键安装全部常用包")
        btn_install_all.setFixedHeight(34)
        btn_install_all.setStyleSheet("""
            QPushButton { background: #7c3aed; color: white; border: none;
                          border-radius: 6px; font-weight: 600; padding: 0 12px; }
            QPushButton:hover { background: #8b5cf6; }
        """)
        btn_install_all.clicked.connect(self._install_all_common)
        btn_row3.addWidget(btn_install_all)
        btn_row3.addStretch()
        t3_layout.addLayout(btn_row3)

        self.common_output = self._make_console(height=160)
        t3_layout.addWidget(self.common_output)
        self.tabs.addTab(tab3, "⚡ 预安装常用包")

        # 底部关闭按钮
        footer = QFrame()
        footer.setStyleSheet("border-top: 1px solid #21262d;")
        footer.setFixedHeight(48)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 8, 16, 8)
        footer_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.setFixedSize(80, 32)
        btn_close.clicked.connect(self.accept)
        footer_layout.addWidget(btn_close)
        layout.addWidget(footer)

    def _make_console(self, height: int = 0) -> QTextEdit:
        te = QTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Consolas", 11))
        te.setStyleSheet("""
            QTextEdit { background: #010409; color: #7ee787;
                        font-family: Consolas, 'Courier New', monospace;
                        font-size: 12px; border: 1px solid #21262d; border-radius: 4px; }
        """)
        if height:
            te.setFixedHeight(height)
        return te

    def _append(self, te_id: int, line: str):
        self.append_requested.emit(te_id, line)

    def _do_append(self, te_id: int, line: str):
        if te_id == 1:
            te = self.diag_output
        elif te_id == 2:
            te = self.proj_output
        elif te_id == 3:
            te = self.common_output
        else:
            return
            
        colors = {
            "[ERROR]": "#f85149", "[WARN]": "#e3b341",
            "[SUCCESS]": "#7ee787", "[INFO]": "#58a6ff",
        }
        color = "#7ee787"
        for k, c in colors.items():
            if k in line:
                color = c
                break
        cursor = te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(line + "\n")
        te.setTextCursor(cursor)
        te.ensureCursorVisible()
        self._output_lines.append(line)

    # ── 全系统诊断 ──────────────────────────

    def _run_system_diag(self):
        self.diag_output.clear()
        self._output_lines.clear()
        self.btn_run_diag.setEnabled(False)
        self.btn_auto_fix.setEnabled(False)
        self.progress1.setVisible(True)

        def _do(progress_callback):
            return run_full_diagnostics(progress_callback)

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self._append(1, l))
        worker.signals.result.connect(self._on_diag_done)
        worker.signals.finished.connect(lambda: (
            self.btn_run_diag.setEnabled(True),
            self.progress1.setVisible(False)
        ))
        self._start_worker(worker)

    def _on_diag_done(self, results: dict):
        self._diag_results = results
        issues = results.get("issues", [])
        if issues:
            self.btn_auto_fix.setEnabled(True)
        self._append(1,
                     f"\n[INFO] 诊断完成，发现 {len(issues)} 个问题")

    def _auto_fix_issues(self):
        self.btn_auto_fix.setEnabled(False)
        error_text = "\n".join(self._output_lines)
        ctx = {
            "python_exe": self.config.get("python_exe", ""),
            "pip_mirror": "",
            "error_text": error_text,
        }
        pip_mirror_key = self.config.get("pip_mirror", "")
        from .mirror_manager import PIP_MIRRORS
        pip_url = PIP_MIRRORS.get(pip_mirror_key, "")
        if pip_url:
            ctx["pip_mirror"] = pip_url

        self._append(1, "\n[INFO] 开始自动修复...")

        def _do(progress_callback):
            return auto_fix(error_text, ctx, progress_callback)

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self._append(1, l))
        worker.signals.result.connect(lambda r: self._append(
            1,
            f"[{'SUCCESS' if r.get('fixed') else 'WARN'}] {r.get('message', '')}"
        ))
        worker.signals.finished.connect(lambda: self.btn_auto_fix.setEnabled(True))
        self._start_worker(worker)

    # ── 项目依赖检测 ──────────────────────────

    def _check_project_deps(self):
        if not self.project:
            return
        self.proj_output.clear()
        self.pkg_tree.clear()
        self.btn_check_proj.setEnabled(False)
        local_dir = self.project.get("local_dir", "")

        from .dependency_manager import is_venv_ready, get_venv_python
        venv_dir = os.path.join(local_dir, ".venv")
        if is_venv_ready(venv_dir):
            python_exe = get_venv_python(venv_dir)
        else:
            python_exe = self.config.get("python_exe", "") or get_default_python_executable()

        def _do(progress_callback):
            return check_project_requirements(local_dir, callback=progress_callback, python_exe=python_exe)

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self._append(2, l))
        worker.signals.result.connect(self._on_proj_check_done)
        worker.signals.finished.connect(lambda: self.btn_check_proj.setEnabled(True))
        self._start_worker(worker)

    def _on_proj_check_done(self, results: dict):
        self._proj_check_results = results
        installed = results.get("installed", [])
        missing = results.get("missing", [])

        cat_ok = QTreeWidgetItem(self.pkg_tree)
        cat_ok.setText(0, f"✅ 已安装 ({len(installed)})")
        cat_ok.setExpanded(True)
        for pkg in installed:
            item = QTreeWidgetItem(cat_ok)
            item.setText(0, pkg)
            item.setText(1, "✓")
            item.setForeground(1, QColor("#7ee787"))

        cat_miss = QTreeWidgetItem(self.pkg_tree)
        cat_miss.setText(0, f"❌ 缺失 ({len(missing)})")
        cat_miss.setExpanded(True)
        for pkg in missing:
            item = QTreeWidgetItem(cat_miss)
            item.setText(0, pkg)
            item.setText(1, "✗ 未安装")
            item.setForeground(1, QColor("#f85149"))

        if missing:
            self.btn_install_missing.setEnabled(True)

    def _install_missing(self):
        missing = getattr(self, "_proj_check_results", {}).get("missing", [])
        if not missing:
            return
        self.btn_install_missing.setEnabled(False)
        local_dir = self.project.get("local_dir", "") if self.project else ""
        from .dependency_manager import is_venv_ready, get_venv_python, install_python_package
        venv_dir = os.path.join(local_dir, ".venv")
        if is_venv_ready(venv_dir):
            python_exe = get_venv_python(venv_dir)
        else:
            python_exe = self.config.get("python_exe", "") or get_default_python_executable()
        from .mirror_manager import build_pip_args, choose_pip_mirror
        manager_python = self.config.get("python_exe", "") or get_default_python_executable()

        def _do(progress_callback):
            pip_source = choose_pip_mirror(
                self.config.get("pip_mirror", ""),
                self.config.get("auto_network_acceleration", True),
                progress_callback,
            )
            pip_args = build_pip_args(pip_source)
            ok = True
            for package in missing:
                ok = install_python_package(
                    package, python_exe, manager_python, progress_callback, pip_args
                ) and ok
            return ok

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self._append(2, l))
        worker.signals.result.connect(lambda ok: self._append(
            2, "[SUCCESS] 安装完成！" if ok else "[ERROR] 安装部分失败"
        ))
        worker.signals.finished.connect(lambda: self.btn_install_missing.setEnabled(True))
        self._start_worker(worker)

    # ── 常用包管理 ──────────────────────────

    COMMON_PACKAGES = [
        ("numpy",           "数值计算基础库",          True),
        ("requests",        "HTTP 请求库",             True),
        ("tqdm",            "进度条",                  True),
        ("Pillow",          "图像处理",                True),
        ("matplotlib",      "数据可视化",              True),
        ("pandas",          "数据分析",                True),
        ("scipy",           "科学计算",                False),
        ("opencv-python",   "OpenCV 计算机视觉",       False),
        ("torch",           "PyTorch 深度学习",        False),
        ("torchvision",     "PyTorch 视觉工具",        False),
        ("transformers",    "HuggingFace Transformers",False),
        ("accelerate",      "HuggingFace 加速库",      False),
        ("diffusers",       "扩散模型库",              False),
        ("gradio",          "快速 Web Demo 框架",      False),
        ("fastapi",         "高性能 API 框架",         False),
        ("uvicorn",         "ASGI 服务器",             False),
        ("pydantic",        "数据验证",                False),
        ("sqlalchemy",      "数据库 ORM",              False),
        ("click",           "命令行工具",              True),
        ("rich",            "终端美化",                True),
        ("loguru",          "日志库",                  True),
        ("python-dotenv",   "环境变量管理",            True),
        ("PyYAML",          "YAML 解析",               True),
        ("toml",            "TOML 解析",               True),
        ("gitpython",       "Git 操作",                True),
        ("pyinstaller",     "打包为可执行文件",        False),
        ("black",           "代码格式化",              False),
        ("pytest",          "单元测试",                False),
        ("onnxruntime",     "ONNX 推理运行时",         False),
        ("scikit-learn",    "机器学习",                False),
        ("xgboost",         "梯度提升树",              False),
    ]

    def _populate_common_packages(self):
        self.common_pkg_tree.clear()
        for pkg_name, desc, recommended in self.COMMON_PACKAGES:
            item = QTreeWidgetItem(self.common_pkg_tree)
            item.setText(0, pkg_name)
            item.setText(1, desc + (" ⭐" if recommended else ""))
            item.setCheckState(0, Qt.CheckState.Checked if recommended else Qt.CheckState.Unchecked)
            item.setText(2, "检测中...")
            item.setForeground(2, QColor("#8b949e"))
            
        def _detect():
            results = []
            import importlib.metadata as metadata
            for pkg_name, _, _ in self.COMMON_PACKAGES:
                try:
                    ver = metadata.version(pkg_name)
                    results.append((pkg_name, True, ver))
                except metadata.PackageNotFoundError:
                    results.append((pkg_name, False, None))
                except Exception:
                    results.append((pkg_name, False, None))
            return results

        from .workers import Worker
        worker = Worker(_detect)
        worker.signals.result.connect(self._update_common_pkg_status)
        self._start_worker(worker)

    def _update_common_pkg_status(self, results):
        status_map = {name: (ok, ver) for name, ok, ver in results}
        for i in range(self.common_pkg_tree.topLevelItemCount()):
            item = self.common_pkg_tree.topLevelItem(i)
            pkg_name = item.text(0)
            if pkg_name in status_map:
                ok, ver = status_map[pkg_name]
                if ok:
                    item.setText(2, f"✓ {ver}")
                    item.setForeground(2, QColor("#7ee787"))
                else:
                    item.setText(2, "未安装")
                    item.setForeground(2, QColor("#f85149"))

    def _refresh_common_pkg_status(self):
        self._populate_common_packages()

    def _install_common_selected(self):
        selected = []
        for i in range(self.common_pkg_tree.topLevelItemCount()):
            item = self.common_pkg_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                selected.append(item.text(0))
        if selected:
            self._install_packages_list(selected)

    def _install_all_common(self):
        pkgs = [p[0] for p in self.COMMON_PACKAGES]
        self._install_packages_list(pkgs)

    def _install_packages_list(self, packages: list):
        self.common_output.clear()
        python_exe = self.config.get("python_exe", "") or get_default_python_executable()
        from .mirror_manager import build_pip_args, choose_pip_mirror

        self._append(3, f"[INFO] 开始安装 {len(packages)} 个包...")
        self._append(3, f"[INFO] 包列表: {', '.join(packages)}")

        def _do(progress_callback):
            import subprocess
            pip_source = choose_pip_mirror(
                self.config.get("pip_mirror", ""),
                self.config.get("auto_network_acceleration", True),
                progress_callback,
            )
            pip_args = build_pip_args(pip_source)
            cmd = [python_exe, "-m", "pip", "install"] + packages + pip_args
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for line in proc.stdout:
                progress_callback(line.rstrip())
            proc.wait()
            return proc.returncode == 0

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self._append(3, l))
        worker.signals.result.connect(lambda ok: (
            self._append(3,
                         "[SUCCESS] 安装完成！" if ok else "[ERROR] 部分安装失败"),
            self._refresh_common_pkg_status()
        ))
        self._start_worker(worker)
