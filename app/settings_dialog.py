"""
settings_dialog.py — 设置对话框（升级版含镜像加速）
"""
import os, sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QTabWidget,
    QWidget, QGroupBox, QComboBox,
    QFileDialog, QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QThreadPool
from .mirror_manager import PIP_MIRRORS, GITHUB_MIRRORS, NPM_MIRRORS, get_best_pip_mirror
from .workers import Worker
from .utils import get_projects_dir, get_shared_dir, get_pip_cache_dir


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self._active_workers = set()
        self.setWindowTitle("⚙  设置")
        self.setModal(True)
        self.setMinimumSize(600, 520)
        self._setup_ui()
        self._load_config()

    def _start_worker(self, worker):
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda w=worker: self._active_workers.discard(w))
        QThreadPool.globalInstance().start(worker)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setStyleSheet("border-bottom: 1px solid #21262d;")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 8, 20, 8)
        title = QLabel("⚙  设置")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        hl.addWidget(title)
        layout.addWidget(header)

        tabs = QTabWidget()

        # ── Tab 1: 目录配置 ──
        tab_dirs = QWidget()
        d_layout = QVBoxLayout(tab_dirs)
        d_layout.setSpacing(14)
        d_layout.setContentsMargins(20, 20, 20, 20)

        grp_dirs = QGroupBox("存储目录")
        grp_dirs_layout = QVBoxLayout(grp_dirs)
        grp_dirs_layout.setSpacing(12)
        self.projects_dir_edit = self._make_dir_row(grp_dirs_layout, "项目存储目录",
            get_projects_dir(), "GitHub 项目将克隆/导入到此目录")
        self.shared_dir_edit   = self._make_dir_row(grp_dirs_layout, "共享依赖目录 (模式A)",
            get_shared_dir(), "所有项目的 pip 包共享安装到此目录")
        self.cache_dir_edit    = self._make_dir_row(grp_dirs_layout, "pip 缓存目录 (模式B)",
            get_pip_cache_dir(), "共享 pip 下载缓存，节省重复下载")
        d_layout.addWidget(grp_dirs)
        d_layout.addStretch()
        tabs.addTab(tab_dirs, "📁 目录")

        # ── Tab 2: 依赖策略 ──
        tab_dep = QWidget()
        dep_layout = QVBoxLayout(tab_dep)
        dep_layout.setSpacing(14)
        dep_layout.setContentsMargins(20, 20, 20, 20)

        grp_dep = QGroupBox("依赖安装策略")
        grp_dep_layout = QVBoxLayout(grp_dep)
        grp_dep_layout.addWidget(QLabel("安装模式:"))
        self.dep_mode_combo = QComboBox()
        self.dep_mode_combo.addItems([
            "模式A — 共享 target 目录（所有项目共用一个目录，不推荐）",
            "模式B — 独立虚拟环境 + uv 全局硬链接共享（强烈推荐）",
        ])
        grp_dep_layout.addWidget(self.dep_mode_combo)
        note = QLabel("📌 模式A: 会导致不同项目因需要同一个包的不同版本而发生冲突\n"
                      "📌 模式B: 使用 uv 极速管理，项目拥有独立环境，但底层文件使用硬链接共享同一份全局缓存。既完美隔离，又极限节省硬盘！")
        note.setStyleSheet("color: #7c85a6; font-size: 12px;")
        note.setWordWrap(True)
        grp_dep_layout.addWidget(note)
        dep_layout.addWidget(grp_dep)

        grp_py = QGroupBox("Python 解释器")
        grp_py_layout = QVBoxLayout(grp_py)
        self.python_exe_edit = self._make_dir_row(grp_py_layout, "Python 可执行文件",
            sys.executable, "留空则使用当前 Python", is_file=True)
        dep_layout.addWidget(grp_py)
        dep_layout.addStretch()
        tabs.addTab(tab_dep, "📦 依赖")

        # ── Tab 3: 镜像加速 ──
        tab_mirror = QWidget()
        m_layout = QVBoxLayout(tab_mirror)
        m_layout.setSpacing(14)
        m_layout.setContentsMargins(20, 20, 20, 20)

        note_top = QLabel("🚀 为网络受限用户配置国内镜像，大幅提升下载速度")
        note_top.setStyleSheet("color: #7c4dff; font-size: 12px;")
        m_layout.addWidget(note_top)

        # pip 镜像
        grp_pip_m = QGroupBox("pip 镜像源")
        gpm_layout = QVBoxLayout(grp_pip_m)
        gpm_layout.addWidget(QLabel("选择 pip 镜像:"))
        self.pip_mirror_combo = QComboBox()
        self.pip_mirror_combo.addItems(list(PIP_MIRRORS.keys()))
        gpm_layout.addWidget(self.pip_mirror_combo)

        auto_detect_row = QHBoxLayout()
        self.btn_auto_mirror = QPushButton("⚡ 自动选择最快镜像")
        self.btn_auto_mirror.setFixedHeight(32)
        self.btn_auto_mirror.setStyleSheet("""
            QPushButton { background: #1f6feb; color: white; border: none;
                          border-radius: 6px; padding: 0 12px; font-size: 12px; }
            QPushButton:hover { background: #388bfd; }
        """)
        self.btn_auto_mirror.clicked.connect(self._auto_select_mirror)
        auto_detect_row.addWidget(self.btn_auto_mirror)
        self.mirror_speed_label = QLabel("")
        self.mirror_speed_label.setStyleSheet("color: #00e676; font-size: 12px;")
        auto_detect_row.addWidget(self.mirror_speed_label)
        auto_detect_row.addStretch()
        gpm_layout.addLayout(auto_detect_row)
        m_layout.addWidget(grp_pip_m)

        # GitHub 镜像
        grp_gh_m = QGroupBox("GitHub 克隆加速")
        ggm_layout = QVBoxLayout(grp_gh_m)
        ggm_layout.addWidget(QLabel("选择 GitHub 镜像:"))
        self.gh_mirror_combo = QComboBox()
        self.gh_mirror_combo.addItems(list(GITHUB_MIRRORS.keys()))
        ggm_layout.addWidget(self.gh_mirror_combo)
        gh_note = QLabel(
            "• ghproxy.com — 代理访问 GitHub（国内推荐）\n"
            "• FastGit — 域名替换镜像\n"
            "• GitClone — 提前缓存的克隆加速\n"
            "• 直连 — 有 VPN 时使用"
        )
        gh_note.setStyleSheet("color: #7c85a6; font-size: 11px;")
        ggm_layout.addWidget(gh_note)
        m_layout.addWidget(grp_gh_m)

        # npm 镜像
        grp_npm_m = QGroupBox("npm 镜像（Node.js 项目）")
        gnm_layout = QVBoxLayout(grp_npm_m)
        gnm_layout.addWidget(QLabel("选择 npm 镜像:"))
        self.npm_mirror_combo = QComboBox()
        self.npm_mirror_combo.addItems(list(NPM_MIRRORS.keys()))
        gnm_layout.addWidget(self.npm_mirror_combo)
        m_layout.addWidget(grp_npm_m)
        m_layout.addStretch()
        tabs.addTab(tab_mirror, "🚀 镜像加速")

        # ── Tab 4: GitHub Token ──
        tab_gh = QWidget()
        gh_layout = QVBoxLayout(tab_gh)
        gh_layout.setSpacing(14)
        gh_layout.setContentsMargins(20, 20, 20, 20)

        grp_gh = QGroupBox("GitHub 认证")
        grp_gh_layout = QVBoxLayout(grp_gh)
        token_label = QLabel("GitHub Personal Access Token（可选）")
        token_label.setStyleSheet("color: #7c85a6; font-size: 12px;")
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("ghp_xxxxxxxxxxxx（留空有频率限制）")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setMinimumHeight(34)
        grp_gh_layout.addWidget(token_label)
        grp_gh_layout.addWidget(self.token_edit)
        note_gh = QLabel(
            "⚠ 匿名访问每小时限制 60 次，Token 可提升到 5000 次\n"
            "🔗 获取: GitHub → Settings → Developer settings → Tokens"
        )
        note_gh.setStyleSheet("color: #7c85a6; font-size: 12px;")
        note_gh.setWordWrap(True)
        grp_gh_layout.addWidget(note_gh)
        gh_layout.addWidget(grp_gh)
        gh_layout.addStretch()
        tabs.addTab(tab_gh, "🔑 GitHub")

        layout.addWidget(tabs)

        # 按钮栏
        btn_frame = QFrame()
        btn_frame.setStyleSheet("border-top: 1px solid #21262d;")
        btn_frame.setFixedHeight(56)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(20, 10, 20, 10)
        btn_layout.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedSize(80, 34)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("保存")
        btn_save.setFixedSize(80, 34)
        btn_save.setStyleSheet("font-weight: 600;")
        btn_save.clicked.connect(self._save)
        btn_layout.addWidget(btn_save)
        layout.addWidget(btn_frame)

    def _make_dir_row(self, parent_layout, label_text, default, hint="", is_file=False):
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #d0d4fc; font-size: 12px;")
        parent_layout.addWidget(lbl)
        row = QHBoxLayout()
        edit = QLineEdit()
        edit.setPlaceholderText(hint)
        edit.setMinimumHeight(32)
        row.addWidget(edit)
        btn = QPushButton("浏览")
        btn.setFixedSize(54, 32)
        btn.setStyleSheet("font-size: 11px;")
        if is_file:
            btn.clicked.connect(lambda: self._browse_file(edit))
        else:
            btn.clicked.connect(lambda: self._browse_dir(edit))
        row.addWidget(btn)
        parent_layout.addLayout(row)
        return edit

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "选择目录", edit.text())
        if d: edit.setText(d)

    def _browse_file(self, edit):
        f, _ = QFileDialog.getOpenFileName(self, "选择文件", edit.text(),
                                           "可执行文件 (*.exe);;所有文件 (*)")
        if f: edit.setText(f)

    def _auto_select_mirror(self):
        self.btn_auto_mirror.setEnabled(False)
        self.mirror_speed_label.setText("⏳ 检测中...")

        def _detect():
            return get_best_pip_mirror()

        worker = Worker(_detect)
        worker.signals.result.connect(self._on_mirror_detected)
        worker.signals.finished.connect(lambda: self.btn_auto_mirror.setEnabled(True))
        self._start_worker(worker)

    def _on_mirror_detected(self, mirror_name: str):
        idx = self.pip_mirror_combo.findText(mirror_name)
        if idx >= 0:
            self.pip_mirror_combo.setCurrentIndex(idx)
        self.mirror_speed_label.setText(f"✅ 已选择: {mirror_name}")

    def _load_config(self):
        cfg = self.config
        self.projects_dir_edit.setText(cfg.get("projects_dir", get_projects_dir()))
        self.shared_dir_edit.setText(cfg.get("shared_dir", get_shared_dir()))
        self.cache_dir_edit.setText(cfg.get("pip_cache_dir", get_pip_cache_dir()))
        self.dep_mode_combo.setCurrentIndex(cfg.get("dep_mode", 1))
        self.python_exe_edit.setText(cfg.get("python_exe", sys.executable))
        self.token_edit.setText(cfg.get("github_token", ""))

        pip_mirror = cfg.get("pip_mirror", "官方 PyPI (默认)")
        idx = self.pip_mirror_combo.findText(pip_mirror)
        if idx >= 0: self.pip_mirror_combo.setCurrentIndex(idx)

        gh_mirror = cfg.get("github_mirror", "直连 GitHub (默认)")
        idx = self.gh_mirror_combo.findText(gh_mirror)
        if idx >= 0: self.gh_mirror_combo.setCurrentIndex(idx)

        npm_mirror = cfg.get("npm_mirror", "官方 npm (默认)")
        idx = self.npm_mirror_combo.findText(npm_mirror)
        if idx >= 0: self.npm_mirror_combo.setCurrentIndex(idx)

    def _save(self):
        self.config["projects_dir"]  = self.projects_dir_edit.text().strip()
        self.config["shared_dir"]    = self.shared_dir_edit.text().strip()
        self.config["pip_cache_dir"] = self.cache_dir_edit.text().strip()
        self.config["dep_mode"]      = self.dep_mode_combo.currentIndex()
        self.config["python_exe"]    = self.python_exe_edit.text().strip()
        self.config["github_token"]  = self.token_edit.text().strip()
        self.config["pip_mirror"]    = self.pip_mirror_combo.currentText()
        self.config["github_mirror"] = self.gh_mirror_combo.currentText()
        self.config["npm_mirror"]    = self.npm_mirror_combo.currentText()
        self.accept()

    def get_config(self) -> dict:
        return self.config
