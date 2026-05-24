"""
project_detail.py — 项目详情面板
包含：简介标签页 / 代码浏览标签页 / 控制台标签页
"""
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QFrame, QPushButton, QTextBrowser, QLineEdit,
    QSizePolicy, QScrollArea, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QDesktopServices
from PySide6.QtCore import QUrl

from .code_viewer import CodeViewer
from .console_widget import ConsoleWidget
from .dependency_manager import detect_project_type
from .project_launcher import detect_launch_command


class InfoCard(QFrame):
    """信息卡片"""
    def __init__(self, icon: str, label: str, value: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame { background: #171926; border: 1px solid #191c2b;
                     border-radius: 8px; }
            QFrame:hover { border-color: #262b40; background: #212438; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        lbl = QLabel(f"{icon}  {label}")
        lbl.setStyleSheet("color: #7c85a6; font-size: 11px; border: none;")
        layout.addWidget(lbl)

        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet("color: #f8f9fa; font-size: 14px; font-weight: 600; border: none;")
        layout.addWidget(self.value_lbl)

    def set_value(self, v: str):
        self.value_lbl.setText(v)


class OverviewTab(QWidget):
    """简介标签页"""

    open_url = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 项目标题行
        title_row = QHBoxLayout()
        self.lbl_name = QLabel("—")
        self.lbl_name.setStyleSheet("font-size: 22px; font-weight: 700; color: #7c4dff;")
        title_row.addWidget(self.lbl_name)
        title_row.addStretch()

        self.btn_open_github = QPushButton("🔗 GitHub")
        self.btn_open_github.setFixedHeight(28)
        self.btn_open_github.setStyleSheet("""
            QPushButton { font-size: 12px; padding: 0 10px; }
        """)
        self.btn_open_github.clicked.connect(self._on_open_github)
        title_row.addWidget(self.btn_open_github)
        layout.addLayout(title_row)

        # 描述
        self.lbl_desc = QLabel("—")
        self.lbl_desc.setStyleSheet("color: #7c85a6; font-size: 13px;")
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc)

        # 标签（topics）
        self.topics_row = QHBoxLayout()
        self.topics_row.setSpacing(6)
        layout.addLayout(self.topics_row)

        # 信息卡片网格
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self.card_stars  = InfoCard("⭐", "星标")
        self.card_forks  = InfoCard("🔀", "复刻")
        self.card_lang   = InfoCard("💻", "语言")
        self.card_branch = InfoCard("🌿", "分支")
        for c in [self.card_stars, self.card_forks, self.card_lang, self.card_branch]:
            cards_row.addWidget(c)
        cards_row.addStretch()
        layout.addLayout(cards_row)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #191c2b; margin: 8px 0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # 项目检测信息
        detect_label = QLabel("🔍  项目检测信息")
        detect_label.setStyleSheet("color: #7c85a6; font-size: 12px; font-weight: 600;")
        layout.addWidget(detect_label)

        self.lbl_type      = QLabel("类型: —")
        self.lbl_deps      = QLabel("依赖文件: —")
        self.lbl_entry     = QLabel("入口文件: —")
        self.lbl_launch    = QLabel("启动命令: —")
        self.lbl_local_dir = QLabel("本地路径: —")
        self.lbl_git_info  = QLabel("Git 信息: —")

        for lbl in [self.lbl_type, self.lbl_deps, self.lbl_entry,
                    self.lbl_launch, self.lbl_local_dir, self.lbl_git_info]:
            lbl.setStyleSheet("color: #d0d4fc; font-size: 12px;")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        layout.addStretch()
        self._html_url = ""

    def load_project(self, project: dict):
        """加载项目信息"""
        self.lbl_name.setText(project.get("name", "—"))
        self.lbl_desc.setText(project.get("description", "暂无描述"))
        self._html_url = project.get("html_url", "")

        stars = project.get("stars", 0)
        self.card_stars.set_value(f"{stars:,}" if stars else "—")
        forks = project.get("forks", 0)
        self.card_forks.set_value(f"{forks:,}" if forks else "—")
        self.card_lang.set_value(project.get("language", "—") or "—")
        self.card_branch.set_value(project.get("default_branch", "main"))

        # 清空 topics
        while self.topics_row.count():
            item = self.topics_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for topic in project.get("topics", [])[:8]:
            tag = QLabel(topic)
            tag.setStyleSheet("""
                background: #1f3a5f; color: #7c4dff; border-radius: 10px;
                padding: 2px 8px; font-size: 11px; border: none;
            """)
            self.topics_row.addWidget(tag)
        self.topics_row.addStretch()

        # 本地目录检测
        local_dir = project.get("local_dir", "")
        self.lbl_local_dir.setText(f"📁 本地路径: {local_dir}")

        if local_dir and os.path.isdir(local_dir):
            proj_info = detect_project_type(local_dir)
            self.lbl_type.setText(f"🏷 类型: {proj_info['type'].upper()}")
            self.lbl_deps.setText(f"📦 依赖文件: {', '.join(proj_info['dep_files']) or '未检测到'}")
            self.lbl_entry.setText(f"🚀 入口文件: {', '.join(proj_info['entry_points']) or '未检测到'}")

            launch = detect_launch_command(local_dir, project.get("config"))
            cmd_str = " ".join(launch["cmd"]) if launch.get("cmd") else "未检测到"
            self.lbl_launch.setText(f"▶  启动命令: {cmd_str}")

            from .git_manager import get_repo_status
            status = get_repo_status(local_dir)
            if status["is_git_repo"]:
                self.lbl_git_info.setText(
                    f"🔀 Git: {status['current_branch']}  |  {status['last_commit']}"
                )
            else:
                self.lbl_git_info.setText("🔀 Git: 不是 Git 仓库")
        else:
            self.lbl_type.setText("🏷 类型: 项目尚未克隆")
            self.lbl_deps.setText("📦 依赖文件: —")
            self.lbl_entry.setText("🚀 入口文件: —")
            self.lbl_launch.setText("▶  启动命令: —")
            self.lbl_git_info.setText("🔀 Git: —")

    def _on_open_github(self):
        if self._html_url:
            QDesktopServices.openUrl(QUrl(self._html_url))


class ProjectDetailPanel(QWidget):
    """项目详情主面板（含三个标签页）"""

    # 信号转发
    launch_requested = Signal()
    stop_requested = Signal()
    install_requested = Signal()
    update_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_project = None
        self._is_running = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ─ 顶部操作栏 ─
        action_bar = QFrame()
        action_bar.setObjectName("panel_header")
        action_bar.setFixedHeight(72)
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(16, 8, 16, 8)
        action_layout.setSpacing(6)

        # == 分组1: 启停控制 (绿色/红色) ==
        self.btn_launch = QPushButton("🚀  启动项目")
        self.btn_launch.setObjectName("btn_launch")
        self.btn_launch.setFixedHeight(38)
        self.btn_launch.setMinimumWidth(120)
        self.btn_launch.setEnabled(False)
        self.btn_launch.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2ea043, stop:1 #238636); color: #ffffff; border: none;
                border-radius: 6px; font-weight: 700; font-size: 13px; padding: 0 20px; }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3fb950, stop:1 #2ea043); }
            QPushButton:disabled { background: #191c2b; color: #393d54; font-weight: normal; }
            QPushButton:pressed { background: #1a7f37; }
        """)
        self.btn_launch.clicked.connect(self._on_primary_action)

        self.btn_stop = QPushButton("⏹  停止")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setFixedHeight(38)
        self.btn_stop.setMinimumWidth(100)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setVisible(False)
        self.btn_stop.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #da3633, stop:1 #b62323); color: #ffffff; border: none;
                border-radius: 6px; font-weight: 700; font-size: 13px; padding: 0 20px; }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #ff1744, stop:1 #da3633); }
            QPushButton:disabled { background: #191c2b; color: #393d54; font-weight: normal; }
            QPushButton:pressed { background: #a0111f; }
        """)
        self.btn_stop.clicked.connect(self.stop_requested.emit)

        # 分组分隔线
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("background: #262b40; margin: 4px 6px;")
        sep1.setFixedWidth(1)

        # == 分组2: 项目操作 (蓝色/中性) ==
        self.btn_install = QPushButton("📦  安装依赖")
        self.btn_install.setObjectName("btn_install")
        self.btn_install.setFixedHeight(38)
        self.btn_install.setMinimumWidth(100)
        self.btn_install.setEnabled(False)
        self.btn_install.setStyleSheet("""
            QPushButton { background: #191c2b; border: 1px solid #262b40; 
                border-radius: 6px; font-size: 12px; padding: 0 14px; }
            QPushButton:hover { background: #262b40; border-color: #7c4dff; color: #e6edf3; }
            QPushButton:disabled { color: #393d54; border-color: #191c2b; }
            QPushButton:pressed { border-color: #ffffff; }
        """)
        self.btn_install.clicked.connect(self.install_requested.emit)

        self.btn_update = QPushButton("🔄  更新项目")
        self.btn_update.setObjectName("btn_update")
        self.btn_update.setFixedHeight(38)
        self.btn_update.setMinimumWidth(100)
        self.btn_update.setEnabled(False)
        self.btn_update.setStyleSheet("""
            QPushButton { background: #191c2b; border: 1px solid #262b40; 
                border-radius: 6px; font-size: 12px; padding: 0 14px; }
            QPushButton:hover { background: #262b40; border-color: #d500f9; color: #e6edf3; }
            QPushButton:disabled { color: #393d54; border-color: #191c2b; }
            QPushButton:pressed { background: #8957e5; border-color: #8957e5; color: #ffffff; }
        """)
        self.btn_update.clicked.connect(self.update_requested.emit)

        # 分组分隔线
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("background: #262b40; margin: 4px 6px;")
        sep2.setFixedWidth(1)

        # == 分组3: 浏览器/删除 ==
        self.btn_browser = QPushButton("🌐  WebUI")
        self.btn_browser.setFixedHeight(38)
        self.btn_browser.setVisible(False)
        self.btn_browser.setStyleSheet("""
            QPushButton { color: #ffffff; border: none;
                font-weight: 600; border-radius: 6px; font-size: 12px; padding: 0 16px; }
            QPushButton:hover { background: #1f6feb; }
        """)
        self._current_url = ""
        self.btn_browser.clicked.connect(self._on_open_browser)

        self.btn_delete = QPushButton("🗑  删除")
        self.btn_delete.setObjectName("btn_delete")
        self.btn_delete.setFixedHeight(38)
        self.btn_delete.setStyleSheet("""
            QPushButton { background: #191c2b; border: 1px solid #262b40; color: #ff1744;
                border-radius: 6px; font-size: 12px; padding: 0 14px; }
            QPushButton:hover { background: #da3633; border-color: #da3633; color: #ffffff; }
            QPushButton:pressed { background: #a0111f; }
        """)
        self.btn_delete.clicked.connect(self.delete_requested.emit)

        self.launch_args_label = QLabel("参数:")
        self.launch_args_label.setStyleSheet("color: #7c85a6; font-size: 11px;")
        self.launch_args_label.setFixedWidth(35)
        action_layout.addWidget(self.launch_args_label)

        self.launch_args_edit = QLineEdit()
        self.launch_args_edit.setPlaceholderText("test.mp3 --language zh")
        self.launch_args_edit.setFixedHeight(30)
        self.launch_args_edit.setFixedWidth(220)
        self.launch_args_edit.setStyleSheet("""
            QLineEdit {
                 border: 1px solid #262b40;
                color: #e6edf3; border-radius: 5px; padding: 0 8px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #7c4dff; }
        """)
        action_layout.addWidget(self.launch_args_edit)

        self.lbl_status = QLabel("— 未选择项目 —")
        self.lbl_status.setStyleSheet("color: #5c6280; font-size: 12px; padding: 0 8px;")

        # 排列按钮
        action_layout.addWidget(self.btn_launch)
        action_layout.addWidget(self.btn_stop)
        action_layout.addWidget(sep1)
        action_layout.addWidget(self.btn_install)
        action_layout.addWidget(self.btn_update)
        action_layout.addWidget(sep2)
        action_layout.addWidget(self.btn_browser)
        action_layout.addWidget(self.btn_delete)
        action_layout.addStretch()
        action_layout.addWidget(self.lbl_status)
        layout.addWidget(action_bar)


        # ─ Tab 区域 ─
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; border-top: 1px solid #191c2b; }
            QTabBar::tab { border: none;
                border-right: 1px solid #191c2b; padding: 8px 16px; font-size: 12px; }
        """)
        layout.addWidget(self.tabs)

        # 简介标签页
        self.overview_tab = OverviewTab()
        self.tabs.addTab(self.overview_tab, "📋  简介")

        # 依赖管理标签页
        from .dependency_panel import DependencyPanel
        self.dep_panel = DependencyPanel()
        self.dep_panel.install_all_requested.connect(self.install_requested.emit)
        self.dep_panel.log_requested.connect(self.append_console)
        self.tabs.addTab(self.dep_panel, "📦  依赖管理")

        # 代码浏览标签页
        self.code_tab = CodeViewer()
        self.tabs.addTab(self.code_tab, "📄  代码浏览")

        # 控制台标签页
        self.console = ConsoleWidget()
        self.tabs.addTab(self.console, "📟  控制台")

    def load_project(self, project: dict, config: dict = None):
        self._current_project = project
        self._config = config or {}
        self.overview_tab.load_project(project)
        if hasattr(self, "dep_panel"):
            self.dep_panel.load_project(project, self._config)
        local_dir = project.get("local_dir", "")
        has_local_dir = bool(local_dir and os.path.isdir(local_dir))
        if has_local_dir:
            self.code_tab.load_project(local_dir)
        else:
            self.code_tab.load_project("")
        is_running = project.get("status") == "running"
        self._is_running = is_running
        self.btn_launch.setEnabled(has_local_dir and not is_running)
        self.btn_install.setEnabled(has_local_dir and not is_running)
        self.btn_update.setEnabled(
            has_local_dir and os.path.isdir(os.path.join(local_dir, ".git")) and not is_running
        )
        self.btn_delete.setEnabled(True)
        self.btn_stop.setEnabled(is_running)
        if hasattr(self, 'branch_combo'):
            self._refresh_branches(project)
        if hasattr(self, 'readme_view'):
            self._refresh_readme(project)
        if hasattr(self, 'snapshot_list'):
            self._refresh_snapshots(project)


    def _on_open_browser(self):
        import webbrowser
        if self._current_url:
            webbrowser.open(self._current_url)

    def show_browser_button(self, url: str):
        self._current_url = url
        self.btn_browser.setVisible(True)

    def set_running_state(self, running: bool):
        """Update button states based on running status."""
        self._is_running = running
        self.btn_launch.setEnabled(True)
        self.btn_install.setEnabled(not running and bool(self._current_project and os.path.isdir(self._current_project.get("local_dir", ""))))
        self.btn_stop.setEnabled(running)
        if running:
            self.btn_launch.setText("⏹  停止程序")
            self.tabs.setCurrentIndex(3)  # Switch to console tab (index 3: Overview/Deps/Code/Console)
        else:
            self.btn_launch.setText("🚀  启动项目")
            self._current_url = ""
            self.btn_browser.setVisible(False)

    def _on_primary_action(self):
        if self._is_running:
            self.stop_requested.emit()
        else:
            self.launch_requested.emit()

    def switch_to_console(self):
        """Switch to the console/log tab."""
        # Tab order: 0=Overview, 1=Dependencies, 2=Code, 3=Console
        self.tabs.setCurrentIndex(3)

    def clear_console(self):
        """Clear the console output."""
        self.console.clear()

    def append_console(self, line: str):
        """Append a line to the console."""
        self.console.append_line(line)

    def set_busy(self, busy: bool, label: str = ""):
        """Show/hide busy state on the detail panel."""
        pass

    def add_branch_tab(self):
        """Add branch management tab."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QTextEdit
        tab = QWidget()
        layout = QVBoxLayout(tab)
        top = QHBoxLayout()
        top.addWidget(QLabel("分支名:"))
        self.branch_combo = QComboBox()
        top.addWidget(self.branch_combo)
        btn_switch = QPushButton("切换")
        btn_switch.clicked.connect(self._on_switch_branch)
        top.addWidget(btn_switch)
        btn_new = QPushButton("添加分支")
        btn_new.clicked.connect(self._on_new_branch)
        top.addWidget(btn_new)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(lambda: self._refresh_branches())
        top.addWidget(btn_refresh)
        layout.addLayout(top)
        self.branch_info = QTextEdit()
        self.branch_info.setReadOnly(True)
        self.branch_info.setStyleSheet("  border: 1px solid #262b40; border-radius: 4px;")
        layout.addWidget(self.branch_info)
        self.tabs.addTab(tab, "快照管理")

    def _on_switch_branch(self):
        name = self.branch_combo.currentText()
        if name and self._current_project:
            local_dir = self._current_project.get("local_dir", "")
            from .new_features import switch_branch
            switch_branch(local_dir, name)
            self._refresh_branches()

    def _on_new_branch(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "创建快照", "快照名称:")
        if ok and name and self._current_project:
            local_dir = self._current_project.get("local_dir", "")
            from .new_features import create_branch
            create_branch(local_dir, name)
            self._refresh_branches()

    def _refresh_branches(self, project):
        if not project:
            return
        if not hasattr(self, 'branch_combo'):
            return
        local_dir = project.get("local_dir", "")
        if not os.path.isdir(os.path.join(local_dir, ".git")):
            return
        from .new_features import list_branches, get_current_branch, get_branch_graph, get_commit_log
        branches = list_branches(local_dir)
        self.branch_combo.clear()
        cur = get_current_branch(local_dir)
        for b in branches:
            self.branch_combo.addItem(b["name"])
            if b["is_current"]:
                self.branch_combo.setCurrentText(b["name"])
        graph = get_branch_graph(local_dir)
        commits = get_commit_log(local_dir, 20)
        info = "Current branch: " + str(cur) + "\n\n=== Branch Graph ===\n"
        for g in graph:
            info += g + "\n"
        info += "\n\n=== Recent Commits ===\n"
        for c in commits[:15]:
            short = c["hash"][:8]
            info += f"{short} {c['date'][:10]} {c['author']}: {c['message'][:60]}\n"
        self.branch_info.setText(info)

    def add_readme_tab(self):
        """添加 README 预览标签页"""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.readme_view = QTextEdit()
        self.readme_view.setReadOnly(True)
        self.readme_view.setStyleSheet("  border: 1px solid #262b40; border-radius: 4px; font-size: 13px;")
        layout.addWidget(self.readme_view)
        self.tabs.addTab(tab, "README")

    def _refresh_readme(self, project):
        if not project:
            return
        if not hasattr(self, 'readme_view'):
            self.add_readme_tab()
        from .new_features import get_local_readme, render_markdown
        readme = get_local_readme(project.get("local_dir", ""))
        if readme:
            html = render_markdown(readme)
            self.readme_view.setHtml(html)
        else:
            self.readme_view.setPlainText("未找到 README 文件")
    def add_snapshots_tab(self):
        """Add snapshot management tab."""
        from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                        QListWidget, QInputDialog, QMessageBox)
        tab = QWidget()
        layout = QVBoxLayout(tab)
        top = QHBoxLayout()
        btn_create = QPushButton("创建快照")
        btn_create.clicked.connect(self._on_create_snapshot)
        top.addWidget(btn_create)
        btn_restore = QPushButton("恢复")
        btn_restore.clicked.connect(self._on_restore_snapshot)
        top.addWidget(btn_restore)
        btn_delete_snap = QPushButton("删除")
        btn_delete_snap.clicked.connect(self._on_delete_snapshot)
        top.addWidget(btn_delete_snap)
        btn_refresh_snap = QPushButton("刷新")
        btn_refresh_snap.clicked.connect(lambda: self._refresh_snapshots(self._current_project))
        top.addWidget(btn_refresh_snap)
        layout.addLayout(top)
        self.snapshot_list = QListWidget()

        layout.addWidget(self.snapshot_list)
        self.tabs.addTab(tab, "快照管理")

    def _refresh_snapshots(self, project):
        if not hasattr(self, 'snapshot_list'):
            self.add_snapshots_tab()
        self.snapshot_list.clear()
        if not project: return
        from .new_features import list_snapshots
        snaps = list_snapshots(project.get("local_dir", ""))
        for s in snaps:
            self.snapshot_list.addItem(f"{s['name']} - {s.get('date', '')}")

    def _on_create_snapshot(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "创建快照", "快照名称:")
        if ok and name and self._current_project:
            from .new_features import create_snapshot
            ok = create_snapshot(self._current_project.get("local_dir", ""), name)
            if ok:
                self._refresh_snapshots(self._current_project)

    def _on_restore_snapshot(self):
        item = self.snapshot_list.currentItem()
        if not item: return
        name = item.text().split(" -")[0]
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(self, "恢复快照",
            f"确认恢复快照 {name}? 此操作将丢弃未提交的更改。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            from .new_features import restore_snapshot
            restore_snapshot(self._current_project.get("local_dir", ""), name)

    def _on_delete_snapshot(self):
        item = self.snapshot_list.currentItem()
        if not item: return
        name = item.text().split(" -")[0]
        from .new_features import delete_snapshot
        delete_snapshot(self._current_project.get("local_dir", ""), name)
        self._refresh_snapshots(self._current_project)

    def add_actions_tab(self):
        """Add GitHub CI/CD status tab."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QHBoxLayout
        tab = QWidget()
        layout = QVBoxLayout(tab)
        top = QHBoxLayout()
        btn_refresh_actions = QPushButton("刷新")
        btn_refresh_actions.clicked.connect(self._on_refresh_actions)
        top.addWidget(btn_refresh_actions)
        layout.addLayout(top)
        self.actions_view = QTextEdit()
        self.actions_view.setReadOnly(True)

        layout.addWidget(self.actions_view)
        self.tabs.addTab(tab, "CI/CD 状态")

    def _on_refresh_actions(self):
        if not self._current_project:
            return
        from .new_features import get_github_actions_status, get_commit_log
        clone_url = self._current_project.get("clone_url", "")
        actions = get_github_actions_status(clone_url)
        local_dir = self._current_project.get("local_dir", "")
        commits = get_commit_log(local_dir, 3)
        text = ""
        if actions:
            text += "=== GitHub CI/CD 状态 ===\n\n"
            for a in actions[:20]:
                status_icon = {"completed": "\u2705", "in_progress": "\u23F3", "failure": "\u274C"}
                icon = status_icon.get(a.get("status", ""), "\u2753")
                text += f"{icon} {a.get('name','')} ({a.get('status','')})\n"
        else:
            text += "无 CI/CD 状态数据（需要 GITHUB_TOKEN）"
        text += "\n\n=== 最新提交 ===\n"
        for c in commits[:5]:
            text += f"  {c['hash'][:8]} {c['message'][:60]}\n"
        self.actions_view.setText(text)
