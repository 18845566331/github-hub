"""
local_import_dialog.py — 导入本地项目对话框
支持直接将本地已有项目目录加载到 GitHub Hub
"""
import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QFileDialog,
    QMessageBox, QTreeWidget, QTreeWidgetItem,
    QSplitter, QTextEdit, QGroupBox
)
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont

from .dependency_manager import detect_project_type
from .project_launcher import detect_launch_command
from .git_manager import get_repo_status, parse_github_url


class LocalImportDialog(QDialog):
    """导入本地项目目录对话框"""

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.setWindowTitle("📂  导入本地项目")
        self.setModal(True)
        self.setMinimumSize(680, 520)
        self._selected_dir = ""
        self._project_info = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题栏
        header = QFrame()
        header.setStyleSheet("border-bottom: 1px solid #21262d;")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 8, 20, 8)
        title = QLabel("📂  导入本地项目")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        hl.addWidget(title)
        layout.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(14)

        # 目录选择
        dir_label = QLabel("选择本地项目目录")
        dir_label.setStyleSheet("color: #7c85a6; font-size: 12px; font-weight: 600;")
        body.addWidget(dir_label)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("例如 C:\\Projects\\my_project 或 C:\\Projects\\ComfyUI")
        self.dir_edit.setMinimumHeight(36)
        self.dir_edit.textChanged.connect(self._on_dir_changed)
        dir_row.addWidget(self.dir_edit)

        btn_browse = QPushButton("浏览目录")
        btn_browse.setFixedSize(88, 36)
        btn_browse.setStyleSheet("font-size: 12px;")
        btn_browse.clicked.connect(self._browse)
        dir_row.addWidget(btn_browse)

        btn_batch = QPushButton("批量扫描")
        btn_batch.setFixedSize(88, 36)
        btn_batch.setStyleSheet("font-size: 12px;")
        btn_batch.clicked.connect(self._batch_scan)
        dir_row.addWidget(btn_batch)
        body.addLayout(dir_row)

        # 检测结果显示
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左：文件树
        left = QGroupBox("目录内容")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setMaximumWidth(240)
        left_layout.addWidget(self.file_tree)
        splitter.addWidget(left)

        # 右：检测信息
        right = QGroupBox("项目检测信息")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet("""
            QTextEdit { font-family: Consolas, monospace; font-size: 12px;
                        border: none; }
        """)
        right_layout.addWidget(self.info_text)
        splitter.addWidget(right)
        splitter.setSizes([220, 400])
        body.addWidget(splitter)

        # 自定义名称
        name_row = QHBoxLayout()
        name_lbl = QLabel("项目名称:")
        name_lbl.setStyleSheet("color: #7c85a6; font-size: 12px;")
        name_lbl.setFixedWidth(70)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("自动从目录名获取")
        self.name_edit.setMinimumHeight(32)
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.name_edit)
        body.addLayout(name_row)

        # GitHub URL（可选）
        gh_row = QHBoxLayout()
        gh_lbl = QLabel("GitHub URL:")
        gh_lbl.setStyleSheet("color: #7c85a6; font-size: 12px;")
        gh_lbl.setFixedWidth(70)
        self.gh_edit = QLineEdit()
        self.gh_edit.setPlaceholderText("可选: https://github.com/owner/repo（用于更新功能）")
        self.gh_edit.setMinimumHeight(32)
        gh_row.addWidget(gh_lbl)
        gh_row.addWidget(self.gh_edit)
        body.addLayout(gh_row)

        layout.addLayout(body)

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

        self.btn_import = QPushButton("导入项目")
        self.btn_import.setFixedSize(100, 34)
        self.btn_import.setEnabled(False)
        self.btn_import.setStyleSheet("font-weight: 600;")
        self.btn_import.clicked.connect(self._do_import)
        btn_layout.addWidget(self.btn_import)
        layout.addWidget(btn_frame)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择项目目录")
        if d:
            self.dir_edit.setText(d)

    def _batch_scan(self):
        """扫描一个父目录下的所有子目录作为项目"""
        parent = QFileDialog.getExistingDirectory(self, "选择包含多个项目的父目录")
        if not parent:
            return
        subdirs = [
            os.path.join(parent, d) for d in os.listdir(parent)
            if os.path.isdir(os.path.join(parent, d))
            and not d.startswith(".")
        ]
        if not subdirs:
            QMessageBox.information(self, "提示", "未找到子目录")
            return
        msg = f"发现 {len(subdirs)} 个子目录:\n"
        msg += "\n".join(f"  • {os.path.basename(d)}" for d in subdirs[:20])
        if len(subdirs) > 20:
            msg += f"\n  ... 还有 {len(subdirs)-20} 个"
        ret = QMessageBox.question(self, "批量导入", msg + "\n\n确认全部导入？",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            self._batch_dirs = subdirs
            self._project_info["batch_dirs"] = subdirs
            self.accept()

    def _on_dir_changed(self, text: str):
        text = text.strip()
        self._selected_dir = text
        self.file_tree.clear()
        self.info_text.clear()
        self.btn_import.setEnabled(False)

        if not text or not os.path.isdir(text):
            return

        # 自动填充名称
        name = Path(text).name
        if not self.name_edit.text():
            self.name_edit.setText(name)

        # 扫描文件树（只显示根级别）
        root_item = QTreeWidgetItem(self.file_tree)
        root_item.setText(0, f"📁 {name}")
        root_item.setExpanded(True)
        try:
            entries = sorted(os.scandir(text), key=lambda e: (not e.is_dir(), e.name))
            shown = 0
            for entry in entries:
                if shown >= 30:
                    more = QTreeWidgetItem(root_item)
                    more.setText(0, "... 更多文件")
                    break
                item = QTreeWidgetItem(root_item)
                icon = "📁" if entry.is_dir() else "📄"
                item.setText(0, f"{icon} {entry.name}")
                shown += 1
        except PermissionError:
            pass

        # 检测项目信息
        self._detect_and_show(text)
        self.btn_import.setEnabled(True)

    def _detect_and_show(self, project_dir: str):
        info_lines = []
        proj_info = detect_project_type(project_dir)

        info_lines.append(f"[INFO] 项目目录: {project_dir}")
        info_lines.append(f"[INFO] 项目类型: {proj_info['type'].upper()}")
        info_lines.append(f"[INFO] 运行时:   {proj_info['runtime']}")

        if proj_info["dep_files"]:
            info_lines.append(f"[SUCCESS] 依赖文件: {', '.join(proj_info['dep_files'])}")
        else:
            info_lines.append("[WARN] 未检测到依赖文件")

        if proj_info["entry_points"]:
            info_lines.append(f"[SUCCESS] 入口文件: {', '.join(proj_info['entry_points'])}")
        else:
            info_lines.append("[WARN] 未检测到入口文件")

        # Git 信息
        git_status = get_repo_status(project_dir)
        if git_status["is_git_repo"]:
            info_lines.append(f"[SUCCESS] Git 仓库: ✓")
            info_lines.append(f"[INFO] 分支: {git_status['current_branch']}")
            info_lines.append(f"[INFO] 最新提交: {git_status['last_commit']}")
            if git_status.get("remote_url"):
                remote = git_status["remote_url"]
                info_lines.append(f"[INFO] 远程: {remote}")
                # 自动填充 GitHub URL
                if "github.com" in remote and not self.gh_edit.text():
                    self.gh_edit.setText(
                        remote.replace(".git", "").replace("git@github.com:", "https://github.com/")
                    )
        else:
            info_lines.append("[WARN] 非 Git 仓库（无法使用更新功能）")

        # 启动命令
        launch = detect_launch_command(project_dir)
        if launch.get("cmd"):
            info_lines.append(f"[SUCCESS] 启动命令: {' '.join(launch['cmd'])}")
        else:
            info_lines.append("[WARN] 未检测到启动命令，需手动配置")

        self.info_text.setPlainText("\n".join(info_lines))
        self._project_info.update({
            "type": proj_info["type"],
            "dep_files": proj_info["dep_files"],
            "entry_points": proj_info["entry_points"],
            "is_git_repo": git_status["is_git_repo"],
            "remote_url": git_status.get("remote_url", ""),
        })

    def _do_import(self):
        d = self._selected_dir.strip()
        if not d or not os.path.isdir(d):
            QMessageBox.warning(self, "错误", "请选择有效的目录")
            return

        name = self.name_edit.text().strip() or Path(d).name
        gh_url = self.gh_edit.text().strip()

        owner, repo = "", ""
        clone_url = ""
        if gh_url:
            parsed = parse_github_url(gh_url)
            if parsed:
                owner = parsed.get("owner", "")
                repo = parsed.get("repo", "")
                clone_url = parsed.get("clone_url", "")

        if not clone_url and self._project_info.get("remote_url"):
            remote = self._project_info["remote_url"]
            clone_url = remote if remote.endswith(".git") else remote + ".git"

        self._project_info.update({
            "name": name,
            "local_dir": d,
            "owner": owner,
            "repo": repo,
            "clone_url": clone_url,
            "html_url": gh_url,
            "status": "not_installed",
            "description": f"本地导入项目: {d}",
        })
        self.accept()

    def get_project_info(self) -> dict:
        return self._project_info

    def get_batch_dirs(self) -> list:
        return self._project_info.get("batch_dirs", [])
