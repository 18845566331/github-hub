"""
add_project_dialog.py — 添加 GitHub 项目对话框
"""
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QProgressBar,
    QCheckBox, QFileDialog, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QFont

from .workers import Worker
from .git_manager import parse_github_url, get_github_info
from .utils import get_projects_dir


class AddProjectDialog(QDialog):
    """添加 GitHub 项目对话框"""

    project_added = Signal(dict)  # 成功添加后发出项目信息

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("添加 GitHub 项目")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setFixedHeight(380)
        self._fetched_info = {}
        self._active_workers = set()
        self._setup_ui()

    def _start_worker(self, worker):
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda w=worker: self._active_workers.discard(w))
        QThreadPool.globalInstance().start(worker)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel("➕  添加 GitHub 项目")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #191c2b; margin: 0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # GitHub URL
        url_label = QLabel("GitHub 项目 URL")
        url_label.setStyleSheet("color: #7c85a6; font-size: 12px; font-weight: 600;")
        layout.addWidget(url_label)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://github.com/owner/repo")
        self.url_edit.setMinimumHeight(36)
        url_row.addWidget(self.url_edit)

        self.btn_fetch = QPushButton("获取信息")
        self.btn_fetch.setFixedSize(80, 36)
        self.btn_fetch.setStyleSheet("font-size: 12px;")
        self.btn_fetch.clicked.connect(self._fetch_info)
        url_row.addWidget(self.btn_fetch)
        layout.addLayout(url_row)

        # 项目名（预览）
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #00e676; font-size: 12px; min-height: 20px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # 本地存储目录
        dir_label = QLabel("本地存储目录")
        dir_label.setStyleSheet("color: #7c85a6; font-size: 12px; font-weight: 600;")
        layout.addWidget(dir_label)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        default_dir = self.config.get("projects_dir", get_projects_dir())
        self.dir_edit.setText(default_dir)
        self.dir_edit.setMinimumHeight(36)
        dir_row.addWidget(self.dir_edit)

        btn_browse = QPushButton("浏览")
        btn_browse.setFixedSize(60, 36)
        btn_browse.setStyleSheet("font-size: 12px;")
        btn_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(btn_browse)
        layout.addLayout(dir_row)

        # 标签
        tag_label = QLabel("标签 (可选，逗号分隔)")
        tag_label.setStyleSheet("color: #7c85a6; font-size: 12px; font-weight: 600;")
        layout.addWidget(tag_label)

        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("ai, tools, web")
        self.tag_edit.setMinimumHeight(32)
        self.tag_edit.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.tag_edit)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        layout.addStretch()

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedSize(80, 36)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self.btn_ok = QPushButton("克隆项目")
        self.btn_ok.setFixedSize(100, 36)
        self.btn_ok.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

    def _fetch_info(self):
        url = self.url_edit.text().strip()
        if not url:
            return
        parsed = parse_github_url(url)
        if not parsed:
            self.info_label.setText("❌ 无效的 GitHub URL")
            self.info_label.setStyleSheet("color: #ff1744; font-size: 12px;")
            return

        self.info_label.setText("⏳ 正在获取项目信息...")
        self.info_label.setStyleSheet("color: #ffd600; font-size: 12px;")
        self.btn_fetch.setEnabled(False)

        token = self.config.get("github_token", "")
        owner = parsed["owner"]
        repo = parsed["repo"]

        def _fetch():
            return get_github_info(owner, repo, token)

        worker = Worker(_fetch)
        worker.signals.result.connect(self._on_info_fetched)
        worker.signals.error.connect(self._on_fetch_error)
        worker.signals.finished.connect(self._on_fetch_finished)
        self._start_worker(worker)

        self._fetched_info = {"owner": owner, "repo": repo, **parsed}

    def _on_fetch_finished(self):
        try:
            self.btn_fetch.setEnabled(True)
        except Exception:
            pass

    def _on_info_fetched(self, info: dict):
        self._fetched_info.update(info)
        stars = info.get("stars", 0)
        lang = info.get("language", "Unknown")
        desc = info.get("description", "")
        self.info_label.setText(
            f"✅  {info.get('full_name', '')}  ⭐{stars}  [{lang}]"
            + (f"\n📝 {desc[:80]}..." if len(desc) > 80 else f"\n📝 {desc}")
        )
        self.info_label.setStyleSheet("color: #00e676; font-size: 12px;")

        # 自动设置目标目录
        base_dir = self.dir_edit.text().strip()
        repo_dir = os.path.join(base_dir, info.get("name", self._fetched_info.get("repo", "")))
        self.dir_edit.setText(repo_dir)

    def _on_fetch_error(self, err: str):
        try:
            self.info_label.setText(f"⚠ 获取信息失败（将使用基本克隆）: {err}")
            self.info_label.setStyleSheet("color: #ffd600; font-size: 12px;")
        except Exception:
            pass

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择存储目录",
                                             self.dir_edit.text())
        if d:
            url = self.url_edit.text().strip()
            parsed = parse_github_url(url)
            if parsed:
                self.dir_edit.setText(os.path.join(d, parsed["repo"]))
            else:
                self.dir_edit.setText(d)

    def _accept(self):
        url = self.url_edit.text().strip()
        target_dir = self.dir_edit.text().strip()

        if not url:
            QMessageBox.warning(self, "错误", "请输入 GitHub URL")
            return
        parsed = parse_github_url(url)
        if not parsed:
            QMessageBox.warning(self, "错误", "无效的 GitHub URL")
            return
        if not target_dir:
            QMessageBox.warning(self, "错误", "请选择本地目录")
            return
            
        # 自动补全：如果目标目录恰好等于全局根目录，自动加上仓库名
        default_dir = self.config.get("projects_dir", get_projects_dir())
        if os.path.abspath(target_dir) == os.path.abspath(default_dir):
            repo_name = parsed.get("repo", "unknown_repo")
            target_dir = os.path.join(target_dir, repo_name)
            self.dir_edit.setText(target_dir)

        tags = [t.strip() for t in self.tag_edit.text().split(",") if t.strip()]
        project_info = {
            **self._fetched_info,
            "clone_url": parsed["clone_url"],
            "owner": parsed["owner"],
            "repo": parsed.get("repo", ""),
            "branch": parsed.get("branch"),
            "local_dir": target_dir,
            "name": self._fetched_info.get("name") or parsed.get("repo", url),
            "tags": tags,
            "status": "not_installed",
        }
        self.project_added.emit(project_info)
        self.accept()
