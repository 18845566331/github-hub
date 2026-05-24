"""
main_window.py - GitHub Hub Main Window (优化版)
修复问题：
1. 硬编码路径 → 动态路径
2. 对话框标题错误
3. 代码重复 → 抽取公共代码
4. 异常处理改进
"""
import os
import sys
import json
import uuid
import logging
import shutil
import tempfile
from pathlib import Path
from .bootstrap import ensure_user_site_packages
ensure_user_site_packages()

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QStatusBar, QMessageBox, QApplication,
    QLabel, QProgressBar, QFrame, QPushButton, QScrollArea,
    QDialog, QTextEdit, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QInputDialog
)
from PySide6.QtCore import Qt, QThreadPool, QSize, QTimer, Signal, QThread
from PySide6.QtGui import QIcon, QFont, QAction, QKeySequence, QColor, QDesktopServices
from PySide6.QtCore import QUrl

from .project_list import ProjectListPanel
from .project_detail import ProjectDetailPanel
from .dependency_panel import DependencyPanel
from .add_project_dialog import AddProjectDialog
from .settings_dialog import SettingsDialog
from .local_import_dialog import LocalImportDialog
from .diagnostics_dialog import DiagnosticsDialog
from .diagnostics import generate_project_diagnostic_report, check_project_dependencies
from .workers import ProgressWorker, Worker
from .mirror_manager import get_best_pip_mirror, PIP_MIRRORS
from .new_features import *
from .git_manager import clone_repo, pull_repo, check_for_updates, sanitize_git_url, is_complete_git_repo, get_repo_status
from .dependency_manager import (
    install_to_shared_dir, install_with_venv,
    detect_project_type, check_shared_dir_ready, is_venv_ready,
    get_venv_python
)
from .project_launcher import (
    detect_launch_command, detect_launch_candidates, build_env, ProjectProcess
)
from .self_updater import check_for_updates, apply_update, restart_program, get_current_version
from .github_explorer import (
    fetch_trending, TrendingProject, SearchResult,
    search_repos, fetch_by_category, CATEGORIES,
    get_language_color, get_category_for_language,
    translate_description
)
from .mirror_manager import (
    transform_clone_url, build_pip_args, build_npm_args
)
from .config_manager import migrate_config_values
from .project_recipes import get_verified_recipe, recipe_summary
from .utils import (
    get_base_dir, get_projects_dir, get_shared_dir, get_pip_cache_dir,
    get_config_path, setup_logger, sanitize_path, escape_shell_arg,
    TranslationEngine
)

# ══════════════════════════════════════════════════════
# 日志记录器
# ══════════════════════════════════════════════════════
logger = setup_logger("main_window", os.path.join(get_base_dir(), "logs"))

# ══════════════════════════════════════════════════════
# 默认配置（使用动态路径）
# ══════════════════════════════════════════════════════
def _get_default_config() -> dict:
    """获取默认配置（动态计算路径）"""
    base = get_base_dir()
    return {
        "projects_dir": get_projects_dir(base),
        "shared_dir": get_shared_dir(base),
        "pip_cache_dir": get_pip_cache_dir(base),
        "dep_mode": 1,
        "python_exe": sys.executable,
        "github_token": "",
        "pip_mirror": "阿里云",
        "github_mirror": "直连 GitHub (默认)",
        "npm_mirror": "官方 npm (默认)",
        "githug_repo": "",
        "githug_branch": "main",
        "version": "1.0.0",
        "projects": [],
    }

DEFAULT_CONFIG = _get_default_config()
CONFIG_FILE = get_config_path()


def load_config() -> dict:
    """加载配置（向后兼容）"""
    for config_path in (CONFIG_FILE, CONFIG_FILE + ".bak"):
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 合并默认配置（确保新增字段有默认值）
            defaults = _get_default_config()
            for k, v in defaults.items():
                cfg.setdefault(k, v)
            if config_path != CONFIG_FILE:
                logger.warning("主配置损坏或不可读，已从备份配置恢复")
            return migrate_config_values(cfg)
        except Exception as e:
            logger.warning(f"加载配置失败 ({config_path}): {e}")
    return migrate_config_values(_get_default_config())


def save_config(cfg: dict):
    """原子保存配置，并保留上一份可恢复备份。"""
    tmp_path = ""
    try:
        config_dir = os.path.dirname(CONFIG_FILE)
        os.makedirs(config_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="config_", suffix=".tmp", dir=config_dir)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as current:
                    json.load(current)
                shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
            except (OSError, ValueError, json.JSONDecodeError):
                logger.warning("当前主配置不可读，保留现有备份不覆盖")
        os.replace(tmp_path, CONFIG_FILE)
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


class MainWindow(QMainWindow):
    """GitHub Hub 主窗口"""

    sig_set_busy = Signal(bool, str)
    sig_install_done = Signal(dict, bool)
    sig_clone_done = Signal(dict, bool)
    sig_update_done = Signal(dict, bool)
    sig_log = Signal(dict, str)
    sig_url_detected = Signal(dict, str)
    sig_process_exited = Signal(dict, int)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self._processes: dict[str, ProjectProcess] = {}
        self._stopped_processes: set[str] = set()
        self._active_workers = set()
        self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.setMaxThreadCount(4)

        # 信号连接
        self.sig_set_busy.connect(self._set_busy, Qt.ConnectionType.QueuedConnection)
        self.sig_install_done.connect(self._on_install_done, Qt.ConnectionType.QueuedConnection)
        self.sig_clone_done.connect(self._on_clone_done, Qt.ConnectionType.QueuedConnection)
        self.sig_update_done.connect(self._on_update_done, Qt.ConnectionType.QueuedConnection)
        self.sig_log.connect(self._log, Qt.ConnectionType.QueuedConnection)
        self.sig_url_detected.connect(self._on_url_detected, Qt.ConnectionType.QueuedConnection)
        self.sig_process_exited.connect(self._on_process_exited, Qt.ConnectionType.QueuedConnection)

        self._setup_ui()
        self._setup_menu()
        self._load_projects()
        self._init_enhanced_features()

        logger.info("主窗口初始化完成")

    def _set_busy_false(self):
        self._set_busy(False, "")

    def _start_worker(self, worker):
        """Keep runnable signal objects alive until the task completes."""
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda w=worker: self._active_workers.discard(w))
        self._thread_pool.start(worker)

    def _setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("GitHub Hub - 开源项目管理器")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)

        # 状态栏
        status = QStatusBar()
        self._status_label = QLabel("就绪")
        status.addWidget(self._status_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumSize(160, 14)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #30363d; border-radius: 4px; background: #0d1117;
                height: 8px; text-align: center; font-size: 9px; color: #58a6ff; }
            QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #58a6ff, stop:1 #1f6feb); border-radius: 3px; }
        """)
        status.addPermanentWidget(self._progress_bar)
        self.setStatusBar(status)

        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧：工具栏
        left_toolbar = self._build_left_toolbar()
        main_layout.addWidget(left_toolbar)

        # 中间：项目列表
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("""
            QSplitter::handle { background: #21262d; }
            QSplitter::handle:hover { background: #58a6ff; }
        """)

        # Middle pane: project details
        self.detail = ProjectDetailPanel()
        self.detail.launch_requested.connect(self._on_launch)
        self.detail.stop_requested.connect(self._on_stop)
        self.detail.install_requested.connect(self._on_install)
        self.detail.update_requested.connect(self._on_update)
        self.detail.delete_requested.connect(self._on_delete_project)
        splitter.addWidget(self.detail)

        # Right pane: project list
        self.project_list = ProjectListPanel()
        self.project_list.project_selected.connect(self._on_project_selected)
        self.project_list.add_project_clicked.connect(self._on_add_project)
        self.project_list.projects_reordered.connect(lambda _projects: self._save_projects())
        splitter.addWidget(self.project_list)

        splitter.setSizes([880, 320])
        main_layout.addWidget(splitter, 1)

    def _build_left_toolbar(self):
        """构建左侧工具栏"""
        widget = QWidget()
        widget.setObjectName("left_toolbar")
        widget.setFixedWidth(240)
        widget.setStyleSheet("""
            QWidget#left_toolbar { background: #0f111a; border-right: 1px solid #191c2b; }
        """)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo 头部
        header = QWidget()
        header.setStyleSheet("border-bottom: 1px solid #191c2b;")
        header.setFixedHeight(132)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(16, 16, 16, 12)
        hl.setSpacing(4)

        logo_row = QHBoxLayout()
        logo = QLabel("GH")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("""
            font-size: 20px; font-weight: bold; color: white;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7c4dff, stop:1 #536dfe);
            border-radius: 12px;
            min-width: 38px; min-height: 38px; max-width: 38px; max-height: 38px;
        """)
        logo_row.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("GitHub Hub")
        title.setStyleSheet("font-size: 15px; font-weight: 700; border: none;")
        title_col.addWidget(title)

        sub = QLabel("开源项目管理器")
        sub.setStyleSheet("font-size: 11px; border: none;")
        title_col.addWidget(sub)
        logo_row.addLayout(title_col)
        logo_row.addStretch()
        hl.addLayout(logo_row)

        badge_row = QHBoxLayout()
        badge = QLabel("v" + get_current_version())
        badge.setStyleSheet("""
            color: #7c85a6; font-size: 10px; border: none;
            background: #171926; border: 1px solid #262b40; border-radius: 6px;
            padding: 2px 8px; font-weight: 600;
        """)
        badge_row.addWidget(badge)
        badge_row.addStretch()
        hl.addLayout(badge_row)

        layout.addWidget(header)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: #212438; border-radius: 2px; }
            QScrollBar::handle:vertical:hover { background: #7c85a6; }
        """)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(12, 10, 12, 10)
        scroll_layout.setSpacing(6)

        # 样式定义
        _group_style = "color: #7c85a6; font-size: 11px; font-weight: 700; padding: 2px 4px 6px; letter-spacing: 0.5px; border: none; background: transparent;"
        _btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: #d0d4fc;
                border-radius: 6px;
                font-size: 13px;
                padding: 6px 12px;
                text-align: left;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #212438;
                color: #f8f9fa;
            }
            QPushButton:pressed {
                background: #536dfe;
                color: white;
            }
        """

        def _mk(text, slot):
            btn = QPushButton(text)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_btn_style)
            btn.clicked.connect(slot)
            return btn

        def _create_card(title_text, buttons):
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background: #171926;
                    border: 1px solid #262b40;
                    border-radius: 10px;
                }
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 8, 8, 8)
            cl.setSpacing(1)

            lbl = QLabel(title_text)
            lbl.setStyleSheet(_group_style)
            cl.addWidget(lbl)

            for b in buttons:
                cl.addWidget(b)
            return card

        # 项目管理组
        scroll_layout.addWidget(_create_card("📁 项目管理", [
            _mk("➕ 添加项目", self._on_add_project),
            _mk("📥 导入本地项目", self._on_import_local)
        ]))

        # 工具组
        scroll_layout.addWidget(_create_card("🛠 工具", [
            _mk("🔍 诊断工具 (F12)", self._on_diagnostics),
            _mk("⚡ 自动镜像", self._on_auto_mirror)
        ]))

        # 系统组
        scroll_layout.addWidget(_create_card("⚙ 系统", [
            _mk("🔧 设置", self._on_settings)
        ]))

        # GitHub 探索组
        scroll_layout.addWidget(_create_card("🌐 GitHub 探索", [
            _mk("🔥 热门项目", self._on_github_trending),
            _mk("📂 分类浏览", self._on_github_categories)
        ]))

        # 高级功能组
        scroll_layout.addWidget(_create_card("💎 高级功能", [
            _mk("📤 导入/导出", self._on_export_import)
        ]))

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        return widget

    def _setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        act_add = QAction("添加项目 (&A)", self)
        act_add.setShortcut(QKeySequence("Ctrl+N"))
        act_add.triggered.connect(self._on_add_project)
        file_menu.addAction(act_add)

        act_import = QAction("导入本地项目 (&I)", self)
        act_import.setShortcut(QKeySequence("Ctrl+O"))
        act_import.triggered.connect(self._on_import_local)
        file_menu.addAction(act_import)

        file_menu.addSeparator()
        act_settings = QAction("设置 (&S)", self)
        act_settings.triggered.connect(self._on_settings)
        file_menu.addAction(act_settings)

        file_menu.addSeparator()
        act_quit = QAction("退出(&Q)", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 项目菜单
        proj_menu = menubar.addMenu("项目(&P)")
        act_launch = QAction("启动项目", self)
        act_launch.setShortcut(QKeySequence("F5"))
        act_launch.triggered.connect(self._on_launch)
        proj_menu.addAction(act_launch)

        act_install = QAction("安装依赖", self)
        act_install.triggered.connect(self._on_install)
        proj_menu.addAction(act_install)

        act_update_proj = QAction("更新项目", self)
        act_update_proj.triggered.connect(self._on_update)
        proj_menu.addAction(act_update_proj)

        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")
        act_diag = QAction("诊断工具", self)
        act_diag.setShortcut(QKeySequence("F12"))
        act_diag.triggered.connect(self._on_diagnostics)
        tools_menu.addAction(act_diag)

        act_check_mirror = QAction("检查镜像", self)
        act_check_mirror.triggered.connect(self._on_auto_mirror)
        tools_menu.addAction(act_check_mirror)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        act_about = QAction("关于 GitHub Hub", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

        help_menu.addSeparator()
        act_update = QAction("检查更新(&U)", self)
        act_update.triggered.connect(self._on_check_update)
        help_menu.addAction(act_update)

        act_shortcuts = QAction("快捷键(&K)", self)
        act_shortcuts.setShortcut(QKeySequence("Ctrl+K"))
        act_shortcuts.triggered.connect(self._on_shortcuts)
        help_menu.addAction(act_shortcuts)

    def _load_projects(self):
        """加载项目列表"""
        projects = self.config.get("projects", [])
        for p in projects:
            p["status"] = self._compute_status(p)
        self.project_list.load_projects(projects)
        self._set_status(f"已加载 {len(projects)} 个项目")

    def _compute_status(self, project: dict) -> str:
        """计算项目状态"""
        pid = project.get("id")
        if pid and pid in self._processes and self._processes[pid].is_running:
            return "running"
        local_dir = project.get("local_dir", "")
        if not local_dir or not os.path.isdir(local_dir):
            return "not_installed"
        dep_mode = self.config.get("dep_mode", 1)
        if dep_mode == 0:
            shared_dir = self.config.get("shared_dir", "")
            if check_shared_dir_ready(shared_dir):
                return "ready"
        else:
            venv_dir = self._get_venv_dir(project)
            if is_venv_ready(venv_dir):
                return "ready"
        return "not_installed"

    def _get_venv_dir(self, project: dict) -> str:
        """获取虚拟环境目录"""
        local_dir = project.get("local_dir", "")
        return os.path.join(local_dir, ".venv")

    def _save_projects(self):
        """保存项目列表"""
        self.config["projects"] = [
            {k: v for k, v in p.items() if k != "status"}
            for p in (self.project_list._all_projects or [])
        ]
        save_config(self.config)

    def _get_current_project(self) -> dict | None:
        """获取当前选中的项目"""
        return self.project_list.get_selected_project()

    def _on_project_selected(self, project: dict):
        """项目选中事件"""
        self.detail.load_project(project, self.config)
        pid = project.get("id")
        if pid and pid in self._processes and self._processes[pid].is_running:
            self.detail.set_running_state(True)
        else:
            self.detail.set_running_state(False)
        self._auto_check_dependencies(project)

    def _python_for_project(self, project: dict) -> str:
        local_dir = project.get("local_dir", "")
        venv_dir = self._get_venv_dir(project)
        if is_venv_ready(venv_dir):
            return get_venv_python(venv_dir)
        return self.config.get("python_exe", sys.executable) or sys.executable

    def _auto_check_dependencies(self, project: dict):
        local_dir = project.get("local_dir", "")
        if not local_dir or not os.path.isdir(local_dir):
            return
        proj_info = detect_project_type(local_dir)
        if not proj_info.get("has_requirements"):
            return

        def _do(progress_callback):
            return check_project_dependencies(
                local_dir,
                python_exe=self._python_for_project(project),
                callback=progress_callback,
            )

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self.sig_log.emit(project, l))
        worker.signals.result.connect(lambda r: self._on_dependency_check_done(project, r, quiet=True))
        self._start_worker(worker)

    def _on_dependency_check_done(self, project: dict, result: dict, quiet: bool = False):
        missing = result.get("missing", [])
        if missing:
            self._log(project, f"[WARN] 依赖缺失 {len(missing)} 个: {', '.join(missing[:12])}")
            self.detail.btn_install.setEnabled(True)
        elif not quiet:
            self._log(project, "[SUCCESS] 项目依赖完整，可以启动")

    def _check_dependencies_before_launch(self, project: dict) -> bool:
        local_dir = project.get("local_dir", "")
        proj_info = detect_project_type(local_dir)
        if not proj_info.get("has_requirements"):
            return True
        result = check_project_dependencies(local_dir, python_exe=self._python_for_project(project))
        missing = result.get("missing", [])
        if not missing:
            return True

        self.detail.switch_to_console()
        self._log(project, f"[WARN] 启动前检测到缺失依赖: {', '.join(missing[:20])}")
        choices = ["安装全部依赖"] + missing
        choice, ok = QInputDialog.getItem(
            self,
            "修复依赖",
            "检测到依赖缺失。请选择要修复的依赖，或安装全部依赖:",
            choices,
            0,
            False,
        )
        if not ok:
            return False
        if choice == "安装全部依赖":
            self._install_deps(project)
        else:
            self._install_single_dependency(project, choice)
        return False

    def _install_single_dependency(self, project: dict, package: str):
        local_dir = project.get("local_dir", "")
        python_exe = self._python_for_project(project)
        self.detail.switch_to_console()
        self._set_busy(True, f"正在修复依赖 {package}...")
        self._log(project, f"[INFO] 正在安装单个依赖: {package}")

        def _do(progress_callback):
            from .dependency_manager import _run_pip_with_progress
            return _run_pip_with_progress(
                [python_exe, "-m", "pip", "install", package],
                cwd=local_dir,
                callback=progress_callback,
                auto_fix_ctx={"python_exe": python_exe, "project_dir": local_dir},
            )

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self.sig_log.emit(project, l))
        worker.signals.result.connect(lambda ok: self._log(project, "[SUCCESS] 单个依赖修复完成" if ok else "[ERROR] 单个依赖修复失败"))
        worker.signals.finished.connect(self._set_busy_false)
        self._start_worker(worker)

    # ══════════════════════════════════════════════════════
    # 项目操作方法
    # ══════════════════════════════════════════════════════

    def _on_add_project(self):
        """添加项目"""
        dlg = AddProjectDialog(self.config, self)
        dlg.project_added.connect(self._on_project_info_received)
        dlg.exec()

    def _on_project_info_received(self, project: dict):
        """处理添加的项目信息"""
        if "id" not in project:
            project["id"] = str(uuid.uuid4())[:8]
        recipe = get_verified_recipe(project)
        if recipe:
            project["verified_recipe"] = recipe_summary(recipe)
        projects = self.config.get("projects", [])
        existing_ids = {p.get("id") for p in projects}
        if project["id"] not in existing_ids:
            projects.append(project)
            self.config["projects"] = projects
            self._load_projects()
            self.project_list.select_project_by_id(project["id"])
            self._clone_project(project)

    def _clone_project(self, project: dict):
        """克隆项目"""
        clone_url = sanitize_git_url(project.get("clone_url", ""))
        target_dir = project.get("local_dir", "")
        branch = project.get("branch")

        if is_complete_git_repo(target_dir):
            self._log(project, f"[INFO] 已克隆: {target_dir}")
            status = self._compute_status(project)
            self.project_list.update_project_status(project["id"], status)
            self.detail.load_project(project)
            if status != "ready":
                QTimer.singleShot(500, lambda: self._ask_install(project))
            return
        if os.path.isdir(os.path.join(target_dir, ".git")):
            self._log(project, f"[WARN] 检测到不完整克隆，将重新拉取: {target_dir}")

        gh_mirror = self.config.get("github_mirror", "")
        actual_url = transform_clone_url(clone_url, gh_mirror)
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        self.project_list.update_project_status(project["id"], "installing")
        self.detail.switch_to_console()
        self._log(project, f"[INFO] 正在克隆: {clone_url}")
        self._set_busy(True, "正在克隆...")

        def _do_clone(progress_callback):
            return clone_repo(actual_url, target_dir, branch, progress_callback)

        worker = ProgressWorker(_do_clone)
        worker.signals.progress.connect(lambda l: self.sig_log.emit(project, l))
        worker.signals.error.connect(lambda e: self.sig_log.emit(project, f"[ERROR] 克隆失败: {e}"))
        worker.signals.result.connect(lambda ok: self.sig_clone_done.emit(project, ok))
        worker.signals.finished.connect(self._set_busy_false)
        self._start_worker(worker)

    def _on_clone_done(self, project: dict, success: bool):
        """克隆完成回调"""
        logger.debug(f"克隆完成回调: project={project.get('name')}, success={success}")
        try:
            if success:
                self._log(project, "[SUCCESS] 克隆完成！")
                self.project_list.update_project_status(project["id"], "not_installed")
                self.detail.load_project(project)
                QTimer.singleShot(500, lambda: self._ask_install(project))
            else:
                self._log(project, "[ERROR] 克隆失败！")
                self.project_list.update_project_status(project["id"], "unknown")
            self._save_projects()
        except Exception as e:
            logger.exception(f"克隆完成回调异常: {e}")
        finally:
            self._set_busy(False, "")

    def _ask_install(self, project: dict):
        """询问是否安装依赖"""
        ret = QMessageBox.question(self, "安装依赖",
            f"项目 [{project['name']}] 克隆成功！\n是否现在安装依赖？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            self._install_deps(project)

    def _on_install(self):
        """安装依赖"""
        project = self._get_current_project()
        if project:
            self._install_deps(project)

    def _install_deps(self, project: dict):
        """执行依赖安装"""
        local_dir = project.get("local_dir", "")
        if not local_dir or not os.path.isdir(local_dir):
            QMessageBox.warning(self, "错误", "项目目录未找到，请先克隆")
            return
        proj_info = detect_project_type(local_dir)
        recipe = get_verified_recipe(project)
        if not proj_info.get("dep_files") and not recipe:
            QMessageBox.information(self, "安装依赖", "未检测到可安装的依赖声明文件")
            return

        dep_mode = self.config.get("dep_mode", 1)
        shared_dir = self.config.get("shared_dir", "")
        cache_dir = self.config.get("pip_cache_dir", "")
        python_exe = self.config.get("python_exe", sys.executable) or sys.executable
        has_python_deps = any(
            name in proj_info.get("dep_files", [])
            for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py", "setup.cfg")
        )
        if has_python_deps and not os.path.isfile(python_exe):
            QMessageBox.warning(self, "安装依赖", f"配置的 Python 解释器不存在:\n{python_exe}")
            return
        if dep_mode == 0 and has_python_deps and not shared_dir:
            QMessageBox.warning(self, "安装依赖", "共享依赖目录未配置，请先在设置中指定目录")
            return
        venv_dir = self._get_venv_dir(project)
        pip_mirror_args = build_pip_args(self.config.get("pip_mirror", ""))
        npm_registry_args = build_npm_args(self.config.get("npm_mirror", ""))

        self.project_list.update_project_status(project["id"], "installing")
        self.detail.switch_to_console()
        self.detail.clear_console()
        self._set_busy(True, "正在安装依赖...")
        self._log(project, f"[INFO] 正在安装依赖 (模式 {'A' if dep_mode == 0 else 'B'})...")
        if recipe:
            self._log(
                project,
                f"[INFO] Using verified recipe: {recipe['title']} (verified {recipe['verified_on']})",
            )

        if dep_mode == 0:
            def _do(progress_callback):
                return install_to_shared_dir(
                    local_dir, shared_dir, python_exe, progress_callback,
                    pip_mirror_args, npm_registry_args, recipe
                )
        else:
            def _do(progress_callback):
                return install_with_venv(
                    local_dir, venv_dir, cache_dir, python_exe, progress_callback,
                    pip_mirror_args, npm_registry_args, recipe
                )

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self.sig_log.emit(project, l))
        worker.signals.error.connect(lambda e: self.sig_log.emit(project, f"[ERROR] 安装失败: {e}"))
        worker.signals.result.connect(lambda ok: self.sig_install_done.emit(project, ok))
        worker.signals.finished.connect(self._set_busy_false)
        self._start_worker(worker)

    def _on_install_done(self, project: dict, success: bool):
        """安装完成回调"""
        logger.debug(f"安装完成回调: project={project.get('name')}, success={success}")
        try:
            if success:
                self._log(project, "[SUCCESS] 依赖安装完成！")
                self.project_list.update_project_status(project["id"], "ready")
            else:
                self._log(project, "[ERROR] 安装失败！")
                self.project_list.update_project_status(project["id"], "not_installed")
            self.detail.load_project(project)
            self._save_projects()
        except Exception as e:
            logger.exception(f"安装完成回调异常: {e}")
        finally:
            self._set_busy(False, "")

    def _on_update(self):
        """更新项目"""
        project = self._get_current_project()
        if not project:
            return
        local_dir = project.get("local_dir", "")
        if not local_dir or not os.path.isdir(local_dir):
            QMessageBox.warning(self, "错误", "项目目录未找到，请先克隆")
            return
        if not os.path.isdir(os.path.join(local_dir, ".git")):
            QMessageBox.warning(self, "错误", "不是 Git 仓库，无法更新")
            return

        self.detail.switch_to_console()
        self.detail.clear_console()
        self._set_busy(True, "正在更新项目...")
        self._log(project, "[INFO] 正在拉取最新代码...")
        self.project_list.update_project_status(project["id"], "updating")

        def _do(progress_callback):
            return pull_repo(local_dir, progress_callback)

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(lambda l: self.sig_log.emit(project, l))
        worker.signals.error.connect(lambda e: self.sig_log.emit(project, f"[ERROR] 更新失败: {e}"))
        worker.signals.result.connect(lambda ok: self.sig_update_done.emit(project, ok))
        worker.signals.finished.connect(self._set_busy_false)
        self._start_worker(worker)

    def _on_update_done(self, project: dict, success: bool):
        """更新完成回调"""
        if success:
            self._log(project, "[SUCCESS] 更新完成！")
            self.project_list.update_project_status(project["id"], "ready")
        else:
            self._log(project, "[ERROR] 更新失败！")
            self.project_list.update_project_status(project["id"], "unknown")
        self._save_projects()

    def _on_launch(self):
        """启动项目"""
        project = self._get_current_project()
        if not project:
            return
        local_dir = project.get("local_dir", "")
        if not local_dir or not os.path.isdir(local_dir):
            QMessageBox.warning(self, "错误", "项目目录未找到，请先克隆")
            return
        if not self._check_dependencies_before_launch(project):
            return

        recipe = get_verified_recipe(project)
        launch_info = detect_launch_command(local_dir, self.config, recipe)
        if not launch_info.get("cmd"):
            report = generate_project_diagnostic_report(local_dir, self.config)
            self.detail.switch_to_console()
            self._log(project, report)
            QMessageBox.warning(self, "错误", launch_info.get("description", "未检测到启动命令"))
            return

        pid = project["id"]
        if pid in self._processes and self._processes[pid].is_running:
            QMessageBox.warning(self, "错误", "该项目正在运行中")
            return

        env = build_env(local_dir, self.config.get("shared_dir"))
        cmd = launch_info["cmd"]

        # 处理启动参数（安全的参数解析）
        args_text = self.detail.launch_args_edit.text().strip()
        if args_text:
            import shlex
            try:
                # 安全解析参数
                extra_args = shlex.split(args_text)
                cmd = cmd + extra_args
            except ValueError:
                # 如果解析失败，尝试简单拼接
                cmd = cmd + [args_text]

        self.detail.switch_to_console()
        self.detail.clear_console()
        candidates = detect_launch_candidates(local_dir, self.config, recipe)
        if recipe:
            self._log(
                project,
                f"[INFO] Using verified launch recipe: {recipe['title']} (verified {recipe['verified_on']})",
            )
        if len(candidates) > 1:
            desc = " | ".join(c.get("description", "") for c in candidates[:5])
            self._log(project, f"[INFO] 启动候选: {desc}")
        self._log(project, f"[INFO] 启动命令: {' '.join(cmd)}")
        self.project_list.update_project_status(pid, "running")
        self.detail.set_running_state(True)

        proc = ProjectProcess()
        self._processes[pid] = proc
        started = proc.start(cmd, local_dir, env,
            output_callback=lambda l: self.sig_log.emit(project, l),
            url_detected_callback=lambda u: self.sig_url_detected.emit(project, u),
            exit_callback=lambda code: self.sig_process_exited.emit(project, code))
        if not started:
            self.project_list.update_project_status(pid, "ready")
            self.detail.set_running_state(False)
            self._log(project, generate_project_diagnostic_report(local_dir, self.config))
            return
        self.detail.console.set_interactive(True)
        self.detail.console.command_sent.connect(
            lambda text: self._on_process_input(pid, text))

    def _on_process_exited(self, project: dict, returncode: int):
        """Restore UI state when a launched project process exits."""
        pid = project.get("id")
        stopped_by_user = pid in self._stopped_processes
        self._stopped_processes.discard(pid)
        if pid in self._processes and not self._processes[pid].is_running:
            del self._processes[pid]
        status = self._compute_status(project)
        self.project_list.update_project_status(pid, status)
        current = self._get_current_project()
        if current and current.get("id") == pid:
            self.detail.set_running_state(False)
        if returncode and not stopped_by_user:
            self._log(project, f"[ERROR] 进程退出码: {returncode}")
            self._log(project, "[HINT] 如果错误是 No module named，请先点击“安装依赖”，或在诊断工具中安装缺失包。")

    def _on_process_input(self, pid: str, text: str):
        """向运行中的进程发送输入"""
        proc = self._processes.get(pid)
        if proc and proc.is_running:
            # 安全处理输入 - 只发送非危险的文本
            safe_text = text.strip()
            if safe_text:
                proc.send_input(safe_text)

    def _on_stop(self):
        """停止项目"""
        project = self._get_current_project()
        if not project:
            return
        pid = project.get("id")
        if pid and pid in self._processes:
            self._stopped_processes.add(pid)
            self._processes[pid].stop()
            del self._processes[pid]
            self.project_list.update_project_status(pid, "ready")
            self.detail.set_running_state(False)
            self._log(project, "[INFO] 项目已停止")

    def _on_url_detected(self, project: dict, url: str):
        """检测到 WebURL"""
        pid = project.get("id")
        proc = self._processes.get(pid)
        if not proc or not proc.is_running:
            return
        self._log(project, f"[SUCCESS] 检测到 WebUI: {url}")
        current = self._get_current_project()
        if current and current.get("id") == project.get("id"):
            self.detail.show_browser_button(url)

    def _on_delete_project(self):
        """删除项目 - 修复对话框标题"""
        project = self._get_current_project()
        if not project:
            return

        # 修复：使用正确的对话框标题
        dlg = QMessageBox(self)
        dlg.setWindowTitle("删除项目")  # 修复：之前错误地显示"检查更新"
        dlg.setText(f"确定要从列表中移除项目 [{project.get('name', '')}] 吗？")
        dlg.setInformativeText("本地文件和 .venv 文件夹将保留在磁盘上")
        dlg.setIcon(QMessageBox.Icon.Question)

        btn_remove = dlg.addButton("仅从列表移除", QMessageBox.ButtonRole.ActionRole)
        btn_delete_all = dlg.addButton("删除全部文件", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = dlg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        dlg.exec()

        clicked = dlg.clickedButton()
        if clicked == btn_cancel:
            return

        pid = project["id"]
        if pid in self._processes:
            self._processes[pid].stop()
            del self._processes[pid]

        if clicked == btn_delete_all:
            local_dir = project.get("local_dir", "")
            if not self._can_delete_project_files(local_dir):
                QMessageBox.warning(
                    self,
                    "拒绝删除",
                    "出于数据安全考虑，只允许删除项目存储目录内的子目录。\n"
                    f"当前路径: {local_dir}\n"
                    "可改用“仅从列表移除”。",
                )
                return
            if local_dir and os.path.exists(local_dir):
                try:
                    def remove_readonly(func, path, _):
                        import stat
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    shutil.rmtree(local_dir, onerror=remove_readonly)
                    self._set_status(f"已删除项目文件: {local_dir}")
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"删除失败: {e}\n请手动删除")

        projects = self.config.get("projects", [])
        self.config["projects"] = [p for p in projects if p.get("id") != pid]
        save_config(self.config)
        self._load_projects()

        if self.project_list.list_widget.count() > 0:
            self.project_list.list_widget.setCurrentRow(0)
        else:
            self.detail.load_project({})

    def _can_delete_project_files(self, local_dir: str) -> bool:
        """Only allow recursive deletion below the configured projects root."""
        projects_dir = self.config.get("projects_dir", "")
        if not local_dir or not projects_dir:
            return False
        target = os.path.realpath(os.path.abspath(local_dir))
        root = os.path.realpath(os.path.abspath(projects_dir))
        try:
            return target != root and os.path.commonpath([target, root]) == root
        except ValueError:
            return False

    def _on_import_local(self):
        """导入本地项目"""
        dlg = LocalImportDialog(config=self.config, parent=self)
        if dlg.exec():
            batch_dirs = dlg.get_batch_dirs()
            if batch_dirs:
                projects = self.config.get("projects", [])
                existing = {os.path.normcase(os.path.abspath(p.get("local_dir", ""))) for p in projects}
                for local_dir in batch_dirs:
                    normalized = os.path.normcase(os.path.abspath(local_dir))
                    if normalized in existing:
                        continue
                    proj_info = detect_project_type(local_dir)
                    git_status = get_repo_status(local_dir)
                    projects.append({
                        "id": str(uuid.uuid4())[:8],
                        "name": Path(local_dir).name,
                        "local_dir": local_dir,
                        "type": proj_info.get("type", "unknown"),
                        "dep_files": proj_info.get("dep_files", []),
                        "entry_points": proj_info.get("entry_points", []),
                        "is_git_repo": git_status.get("is_git_repo", False),
                        "remote_url": git_status.get("remote_url", ""),
                        "clone_url": git_status.get("remote_url", ""),
                        "description": f"本地导入项目: {local_dir}",
                        "status": "not_installed",
                    })
                    existing.add(normalized)
                self.config["projects"] = projects
                save_config(self.config)
                self._load_projects()
                return
            info = dlg.get_project_info()
            if info and info.get("local_dir"):
                if "id" not in info:
                    info["id"] = str(uuid.uuid4())[:8]
                projects = self.config.get("projects", [])
                existing = {p.get("local_dir") for p in projects}
                if info["local_dir"] not in existing:
                    projects.append(info)
                    self.config["projects"] = projects
                    save_config(self.config)
                    self._load_projects()
                    self.project_list.select_project_by_id(info["id"])

    # ══════════════════════════════════════════════════════
    # 工具和系统方法
    # ══════════════════════════════════════════════════════

    def _on_diagnostics(self):
        """诊断工具"""
        project = self._get_current_project()
        dlg = DiagnosticsDialog(self.config, project, self)
        dlg.show()

    def _on_auto_mirror(self):
        """自动检测最佳镜像"""
        self._set_busy(True, "正在检测最佳镜像...")
        QApplication.processEvents()

        try:
            best = get_best_pip_mirror()
            self.config["pip_mirror"] = best
            save_config(self.config)
            url = PIP_MIRRORS.get(best, "")

            self._set_busy(False)
            if url:
                msg = f"找到最佳镜像:\n{best}\n{url}"
            else:
                msg = f"找到最佳镜像:\n{best}"
            QMessageBox.information(self, "镜像测试结果", msg)
            self._set_status(f"最佳镜像: {best}")
        except Exception as e:
            self._set_busy(False)
            QMessageBox.warning(self, "错误", f"检测失败: {e}")

    def _on_check_update(self):
        """异步检查程序自身更新。"""
        self._set_busy(True, "正在检查更新...")

        def _do(progress_callback):
            return check_for_updates(self.config, progress_callback)

        worker = ProgressWorker(_do)
        worker.signals.progress.connect(self._set_status)
        worker.signals.result.connect(self._on_check_update_done)
        worker.signals.error.connect(lambda e: QMessageBox.warning(self, "检查更新", e))
        worker.signals.finished.connect(self._set_busy_false)
        self._start_worker(worker)

    def _on_check_update_done(self, result: dict):
        if result.get("error"):
            QMessageBox.warning(self, "检查更新", result["error"])
        elif result.get("has_update"):
            QMessageBox.information(
                self,
                "发现更新",
                f"发现新版本 v{result.get('latest_version', '')}，当前版本 v{result.get('current_version', '')}。",
            )
        else:
            QMessageBox.information(self, "检查更新", "当前已是最新版本")

    def _on_settings(self):
        """设置对话框"""
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.config.update(dlg.get_config())
            save_config(self.config)
            self._set_status("设置已保存")
            self.project_list.load_projects(self.config.get("projects", []))

    def _log(self, project: dict, line: str):
        """记录日志"""
        current = self._get_current_project()
        if current and current.get("id") == project.get("id"):
            self.detail.append_console(line)
        try:
            print(line)
        except UnicodeEncodeError:
            pass

    def _set_status(self, text: str):
        """设置状态栏文本"""
        self._status_label.setText(text)

    def _set_busy(self, busy: bool, label: str = ""):
        """设置忙碌状态"""
        self._progress_bar.setVisible(busy)
        if label:
            self._set_status(label)
        else:
            self._set_status("就绪")
        self.detail.set_busy(busy, label)

    def closeEvent(self, event):
        """关闭事件"""
        running = [pid for pid, proc in self._processes.items() if proc.is_running]
        if running:
            ret = QMessageBox.question(self, "确认退出",
                f"{len(running)} 个项目正在运行。确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ret == QMessageBox.StandardButton.No:
                event.ignore()
                return
        for proc in self._processes.values():
            proc.stop()
        self._save_projects()
        logger.info("应用程序关闭")
        event.accept()

    def _on_about(self):
        """关于对话框"""
        ver = get_current_version()
        QMessageBox.about(self, "关于 GitHub Hub",
            f"<h3>GitHub Hub</h3><p>版本: v{ver}</p>"
            "<p>开源项目管理器 - 轻松管理您的 GitHub 项目</p>")

    def _on_shortcuts(self):
        """快捷键对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("快捷键")
        dlg.setMinimumSize(420, 380)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(4)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("快捷键列表")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #e6edf3; padding-bottom: 8px;")
        layout.addWidget(title)

        shortcuts = [
            ("Ctrl+N", "添加项目"),
            ("Ctrl+O", "导入本地项目"),
            ("F5", "启动项目"),
            ("F12", "诊断工具"),
            ("Ctrl+K", "快捷键"),
            ("Ctrl+Q", "退出"),
        ]

        for key, desc in shortcuts:
            row = QFrame()
            row.setStyleSheet("background: #161b22; border: 1px solid #21262d; border-radius: 6px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 6, 12, 6)

            k = QLabel(f"  {key}  ")
            k.setStyleSheet("background: #21262d; color: #58a6ff; font-weight: 700; font-size: 13px; "
                "border: 1px solid #30363d; border-radius: 4px; padding: 2px 8px;")

            d = QLabel(desc)
            d.setStyleSheet("color: #c9d1d9; font-size: 13px; border: none;")

            rl.addWidget(k)
            rl.addWidget(d)
            rl.addStretch()
            layout.addWidget(row)

        layout.addStretch()
        dlg.exec()

    # ══════════════════════════════════════════════════════
    # 增强功能
    # ══════════════════════════════════════════════════════

    _dark_theme = True

    def _init_enhanced_features(self):
        """初始化增强功能"""
        if hasattr(self.project_list, "enable_drag_drop"):
            self.project_list.enable_drag_drop()
        if hasattr(self.project_list, "add_search_bar"):
            self.project_list.add_search_bar()

    def _on_toggle_theme(self):
        """切换主题"""
        self._dark_theme = not self._dark_theme
        if self._dark_theme:
            self.setStyleSheet("")
            from .theme import APP_STYLESHEET
            self.setStyleSheet(APP_STYLESHEET)
        else:
            light_style = """
                QMainWindow { background: #ffffff; color: #24292f; }
                QWidget#left_toolbar { background: #f6f8fa; border-right: 1px solid #d0d7de; }
                QStatusBar { background: #f6f8fa; color: #57606a; }
                QPushButton { background: #f6f8fa; border: 1px solid #d0d7de; color: #24292f; border-radius: 6px; }
                QPushButton:hover { background: #eaeef2; border-color: #0969da; }
                QListWidget { background: #ffffff; color: #24292f; border: 1px solid #d0d7de; }
                QListWidget::item:selected { background: #ddf4ff; }
                QListWidget::item:hover { background: #f6f8fa; }
            """
            self.setStyleSheet(light_style)
        theme_name = "浅色主题" if not self._dark_theme else "深色主题"
        self._set_status(f"已切换到{theme_name}")

    def _on_manage_tags(self):
        """管理项目标签"""
        project = self._get_current_project()
        if not project:
            QMessageBox.information(self, "管理标签", "请先选择一个项目")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("管理标签")
        dlg.setMinimumSize(400, 300)

        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(f"项目: {project.get('name', '')}"))

        tag_input = QLineEdit()
        tag_input.setPlaceholderText("输入新标签...")
        layout.addWidget(tag_input)

        current_tags = project.get("tags", [])
        tag_list = QListWidget()
        for t in current_tags:
            tag_list.addItem(t)
        layout.addWidget(tag_list)

        btn_row = QHBoxLayout()

        def add_tag():
            t = tag_input.text().strip()
            if t and t not in current_tags:
                current_tags.append(t)
                tag_list.addItem(t)
                tag_input.clear()
                project["tags"] = current_tags
                self._save_projects()
                self.project_list.load_projects(self.config.get("projects", []))

        btn_add = QPushButton("添加")
        btn_add.clicked.connect(add_tag)
        btn_row.addWidget(btn_add)

        def remove_tag():
            item = tag_list.currentItem()
            if item:
                t = item.text()
                if t in current_tags:
                    current_tags.remove(t)
                    tag_list.takeItem(tag_list.row(item))
                    project["tags"] = current_tags
                    self._save_projects()
                    self.project_list.load_projects(self.config.get("projects", []))

        btn_remove = QPushButton("删除选中")
        btn_remove.clicked.connect(remove_tag)
        btn_row.addWidget(btn_remove)

        layout.addLayout(btn_row)
        dlg.exec()

    def _on_ai_assist(self):
        """AI 助手"""
        project = self._get_current_project()
        if not project:
            return
        local_dir = project.get("local_dir", "")
        if not os.path.isdir(local_dir):
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("AI 助手")
        dlg.setMinimumSize(600, 500)

        layout = QVBoxLayout(dlg)

        mode_combo = QComboBox()
        mode_combo.addItems(["生成提交信息", "代码审查", "变量命名建议"])
        layout.addWidget(mode_combo)

        ai_input = QTextEdit()
        ai_input.setPlaceholderText("输入上下文或要分析的代码...")
        layout.addWidget(ai_input)

        ai_output = QTextEdit()
        ai_output.setReadOnly(True)
        layout.addWidget(ai_output)

        def run_ai():
            mode = mode_combo.currentIndex()
            context = ai_input.toPlainText()
            try:
                if mode == 0:
                    diff = get_git_diff(local_dir) or context
                    result = AIAssistant.generate_commit_message(diff)
                elif mode == 1:
                    result = AIAssistant.review_code(context or local_dir)
                else:
                    result = AIAssistant.suggest_variable_name(context)
                ai_output.setPlainText(str(result))
            except Exception as e:
                ai_output.setPlainText(f"错误: {e}")

        btn_run = QPushButton("执行")
        btn_run.clicked.connect(run_ai)
        layout.addWidget(btn_run)

        dlg.exec()

    def _on_dashboard(self):
        """仪表盘"""
        dlg = QDialog(self)
        dlg.setWindowTitle("项目概览")
        dlg.setMinimumSize(700, 500)

        layout = QVBoxLayout(dlg)

        title = QLabel("项目概览")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #e6edf3; padding: 10px;")
        layout.addWidget(title)

        projects = self.config.get("projects", [])
        status_counts = {"running": 0, "ready": 0, "installing": 0, "not_installed": 0, "unknown": 0}

        for p in projects:
            pid = p.get("id")
            if pid and pid in self._processes and self._processes[pid].is_running:
                status_counts["running"] += 1
            else:
                local_dir = p.get("local_dir", "")
                if not local_dir or not os.path.isdir(local_dir):
                    status_counts["not_installed"] += 1
                else:
                    status_counts["ready"] += 1

        from PySide6.QtWidgets import QGridLayout
        grid = QGridLayout()
        colors = {"running": "#2ea043", "ready": "#58a6ff", "installing": "#d29922",
                   "not_installed": "#8b949e", "unknown": "#f85149"}

        row = 0
        for status, count in status_counts.items():
            if count > 0:
                card = QFrame()
                card.setStyleSheet(f"background: #161b22; border: 1px solid {colors[status]}; border-radius: 8px; padding: 12px;")
                cl = QVBoxLayout(card)
                cl.addWidget(QLabel(f"<h1>{count}</h1>"))
                status_display = {"running": "运行中", "ready": "已就绪", "installing": "安装中",
                                   "not_installed": "未安装", "unknown": "未知"}
                cl.addWidget(QLabel(status_display.get(status, status)))
                grid.addWidget(card, row // 2, row % 2)
                row += 1

        layout.addLayout(grid)

        # 修复：使用清晰的中文字符串
        layout.addWidget(QLabel(f"项目总数: {len(projects)} 个 | 运行中: {status_counts['running']} 个"))

        dlg.exec()

    def _on_branches(self):
        """分支管理"""
        project = self._get_current_project()
        if not project:
            QMessageBox.information(self, "提示", "请先选择一个项目")
            return
        local_dir = project.get("local_dir", "")
        if not os.path.isdir(local_dir) or not os.path.isdir(os.path.join(local_dir, ".git")):
            QMessageBox.warning(self, "错误", "该项目不是 Git 仓库")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("分支管理 - " + project.get("name", ""))
        dlg.setMinimumSize(700, 500)

        layout = QVBoxLayout(dlg)

        current = get_current_branch(local_dir)
        info = QLabel(f"当前分支: <b style='color:#58a6ff'>{current}</b>")
        info.setStyleSheet("font-size:14px; padding:8px;")
        layout.addWidget(info)

        graph_text = QTextEdit()
        graph_text.setReadOnly(True)
        graph_text.setStyleSheet("background:#161b22; color:#7ee787; font-family:Consolas; font-size:11px; border:1px solid #30363d; border-radius:4px;")
        graph = get_branch_graph(local_dir)
        graph_text.setPlainText(graph or "无提交历史")
        layout.addWidget(graph_text)

        branch_list = QListWidget()
        branches = list_branches(local_dir)
        for b in branches:
            marker = "⭐" if b["is_current"] else "  "
            msg = b.get("message", "")[:50]
            branch_list.addItem(f"{marker} {b['name']}  {msg}")
        layout.addWidget(QLabel("所有分支:"))
        layout.addWidget(branch_list)

        btn_row = QHBoxLayout()

        def do_switch():
            item = branch_list.currentItem()
            if not item:
                return
            name = item.text().strip().lstrip("⭐ ")
            parts = name.split()
            branch_name = parts[0] if parts else ""
            if switch_branch(local_dir, branch_name):
                QMessageBox.information(dlg, "成功", f"已切换到 {branch_name}")
                dlg.accept()
            else:
                QMessageBox.warning(dlg, "失败", "切换分支失败")

        btn_switch = QPushButton("切换分支")
        btn_switch.clicked.connect(do_switch)
        btn_row.addWidget(btn_switch)

        def do_create():
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(dlg, "创建分支", "分支名称:")
            if ok and name:
                if create_branch(local_dir, name):
                    QMessageBox.information(dlg, "成功", f"已创建分支 {name}")
                    dlg.accept()
                else:
                    QMessageBox.warning(dlg, "失败", "创建分支失败")

        btn_create = QPushButton("创建分支")
        btn_create.clicked.connect(do_create)
        btn_row.addWidget(btn_create)

        layout.addLayout(btn_row)
        dlg.exec()

    def _on_plugin_market(self):
        """插件市场"""
        dlg = QDialog(self)
        dlg.setWindowTitle("插件市场")
        dlg.setMinimumSize(600, 450)

        layout = QVBoxLayout(dlg)

        plugin_list = QListWidget()
        plugins = fetch_plugin_registry()
        if plugins:
            for p in plugins:
                plugin_list.addItem(f"{p.name} v{p.version} - {p.description[:60]}")
        else:
            plugin_list.addItem("(暂无在线插件 - 请检查网络连接)")
        layout.addWidget(plugin_list)

        info = QLabel("插件可以扩展 GitHub Hub 的功能，如代码格式化、测试运行等。")
        info.setStyleSheet("color:#8b949e; padding:8px;")
        layout.addWidget(info)

        dlg.exec()

    def _on_resource_monitor(self):
        """资源监控"""
        self._on_system_monitor()

    def _on_system_monitor(self):
        """系统监控"""
        from .system_monitor import SystemMonitorWidget
        dlg = QDialog(self)
        dlg.setWindowTitle("系统监控")
        dlg.setMinimumSize(500, 400)

        layout = QVBoxLayout(dlg)
        monitor = SystemMonitorWidget()
        layout.addWidget(monitor)

        dlg.exec()

    def _on_export_import(self):
        """导入/导出项目配置"""
        dlg = QDialog(self)
        dlg.setWindowTitle("导入/导出项目配置")
        dlg.setMinimumSize(500, 400)

        layout = QVBoxLayout(dlg)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        projects_json = json.dumps(self.config.get("projects", []), indent=2, ensure_ascii=False)
        text_edit.setPlainText(projects_json)
        layout.addWidget(QLabel("当前项目配置 (JSON):"))
        layout.addWidget(text_edit)

        btn_row = QHBoxLayout()

        def do_export():
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(dlg, "导出配置", "projects.json", "JSON (*.json)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.config.get("projects", []), f, indent=2, ensure_ascii=False)
                QMessageBox.information(dlg, "成功", f"已导出到 {path}")

        btn_export = QPushButton("导出")
        btn_export.clicked.connect(do_export)
        btn_row.addWidget(btn_export)

        def do_import():
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(dlg, "导入配置", "", "JSON (*.json)")
            if path:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        imported = json.load(f)
                except (OSError, json.JSONDecodeError) as e:
                    QMessageBox.warning(dlg, "导入失败", f"无法读取配置: {e}")
                    return
                if not isinstance(imported, list) or not all(
                    isinstance(item, dict) and item.get("local_dir") for item in imported
                ):
                    QMessageBox.warning(dlg, "导入失败", "配置必须是包含项目路径的项目列表")
                    return
                self.config["projects"] = imported
                save_config(self.config)
                self._load_projects()
                QMessageBox.information(dlg, "成功", f"已导入 {len(imported)} 个项目")
                dlg.accept()

        btn_import = QPushButton("导入")
        btn_import.clicked.connect(do_import)
        btn_row.addWidget(btn_import)

        layout.addLayout(btn_row)
        dlg.exec()

    # ══════════════════════════════════════════════════════
    # 批量操作
    # ══════════════════════════════════════════════════════

    def _on_update_all(self):
        """批量更新所有项目"""
        projects = self.config.get("projects", [])
        if not projects:
            QMessageBox.information(self, "提示", "暂无项目")
            return

        self._set_busy(True, "正在批量更新...")

        def _do(progress_callback):
            return update_all_projects(projects, progress_callback)

        worker = ProgressWorker(_do)
        worker.signals.result.connect(lambda r: self._on_update_all_done(r))
        worker.signals.finished.connect(lambda: self._set_busy(False, "更新完成"))
        self._start_worker(worker)

    def _on_update_all_done(self, results):
        """批量更新完成"""
        success = sum(1 for r in results if r.get("success"))
        total = len(results)
        QMessageBox.information(self, "批量更新",
            f"成功更新 {success}/{total} 个项目")
        self._load_projects()

    def _on_clean_all(self):
        """清理所有 venv"""
        ret = QMessageBox.question(self, "确认清理",
            "确定要清理所有 .venv 文件夹和 pip 缓存吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return

        import shutil
        projects = self.config.get("projects", [])
        cleaned = 0
        for p in projects:
            venv = os.path.join(p.get("local_dir", ""), ".venv")
            if os.path.isdir(venv):
                try:
                    shutil.rmtree(venv, ignore_errors=True)
                    cleaned += 1
                except Exception as e:
                    logger.warning(f"清理 venv 失败: {e}")

        cache = self.config.get("pip_cache_dir", "")
        if cache and os.path.isdir(cache):
            try:
                shutil.rmtree(cache, ignore_errors=True)
            except Exception as e:
                logger.warning(f"清理缓存失败: {e}")

        self._set_status(f"已清理 {cleaned} 个 venv 和缓存")
        self._load_projects()

    # ══════════════════════════════════════════════════════
    # GitHub 探索功能（优化版：抽取公共代码）
    # ══════════════════════════════════════════════════════

    def _format_stars(self, n):
        return f"{n / 1000:.1f}k" if n >= 1000 else str(n or 0)

    def _add_github_project_card(self, lw: QListWidget, project, index: int = 0):
        """Add a rich card row for a GitHub project result."""
        full_name = getattr(project, "full_name", "") or getattr(project, "name", "未知项目")
        language = getattr(project, "language", "") or "Unknown"
        stars = getattr(project, "stars", 0)
        description = getattr(project, "description", "") or "暂无项目介绍"
        translated = translate_description(description, 130) if description else "暂无项目介绍"
        url = getattr(project, "html_url", "") or getattr(project, "url", "")

        item = QListWidgetItem()
        item.setData(32, url)
        item.setSizeHint(QSize(0, 118))
        lw.addItem(item)

        card = QFrame()
        card.setObjectName("github_card")
        card.setStyleSheet("""
            QFrame#github_card {
                background: #111522;
                border: 1px solid #262b40;
                border-radius: 8px;
            }
            QFrame#github_card:hover {
                border-color: #536dfe;
                background: #151a2a;
            }
            QLabel { background: transparent; border: none; }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        name = QLabel(f"#{index + 1}  {full_name}")
        name.setStyleSheet("font-size: 15px; font-weight: 700; color: #e6edf3;")
        top.addWidget(name, 1)
        meta = QLabel(f"{language}   ★ {self._format_stars(stars)}")
        meta.setStyleSheet("color: #7c85a6; font-size: 12px; font-weight: 600;")
        top.addWidget(meta)
        layout.addLayout(top)

        desc = QLabel(translated)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #c9d1d9; font-size: 12px; line-height: 1.35;")
        layout.addWidget(desc)

        raw = QLabel(description if description != translated else "")
        raw.setWordWrap(True)
        raw.setStyleSheet("color: #656d8a; font-size: 11px;")
        raw.setVisible(bool(description and description != translated))
        layout.addWidget(raw)

        lw.setItemWidget(item, card)

    def _selected_github_url(self, lw: QListWidget) -> str:
        item = lw.currentItem()
        return item.data(32) if item else ""

    def _on_github_trending(self):
        """热门项目浏览"""
        self._show_github_browser(
            title="热门项目",
            initial_load=True,
            fetch_func=lambda since, lang: fetch_trending(
                since=since,
                language=lang,
                token=self.config.get("github_token", "")
            )
        )

    def _on_github_search(self):
        """搜索 GitHub 项目"""
        self._show_github_search_dialog()

    def _on_github_categories(self):
        """分类浏览"""
        self._show_github_browser(
            title="分类浏览项目",
            initial_load=True,
            fetch_func=lambda since, lang: fetch_by_category(
                category=lang or "全部",
                sort="stars",
                token=self.config.get("github_token", "")
            )
        )

    def _show_github_browser(self, title: str, initial_load: bool = False,
                              fetch_func: callable = None):
        """GitHub 项目浏览器（公共实现）"""
        from PySide6.QtWidgets import QComboBox

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(980, 680)
        dlg._threads = []

        layout = QVBoxLayout(dlg)

        # 顶部筛选栏
        top = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700;")
        top.addWidget(title_lbl)
        top.addStretch()

        is_category_browser = "分类" in title

        # 时间范围选择
        top.addWidget(QLabel("时间范围:"))
        time_combo = QComboBox()
        time_combo.addItems(["今日", "本周", "本月"])
        time_combo.setFixedWidth(100)
        top.addWidget(time_combo)

        # 语言/分类选择
        top.addWidget(QLabel("项目分类:" if is_category_browser else "编程语言:"))
        lang_combo = QComboBox()
        if is_category_browser:
            lang_combo.addItems(list(CATEGORIES.keys()))
        else:
            lang_combo.addItems(["全部", "Python", "JavaScript", "TypeScript", "Go", "Rust", "C++", "Java"])
        lang_combo.setFixedWidth(150 if is_category_browser else 120)
        top.addWidget(lang_combo)

        # 刷新按钮
        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet("background: #238636; color: white; border-radius: 6px; padding: 6px 16px;")
        top.addWidget(btn_refresh)

        layout.addLayout(top)

        # 状态栏
        status = QLabel("正在加载...")
        status.setStyleSheet("color: #8b949e;")
        layout.addWidget(status)

        # 项目列表
        lw = QListWidget()
        lw.setStyleSheet("""
            QListWidget { background: #0d1117; border: 1px solid #21262d; border-radius: 8px; padding: 8px; }
            QListWidget::item { margin: 6px 4px; border: none; }
            QListWidget::item:selected { background: transparent; }
        """)
        layout.addWidget(lw)

        # 底部操作栏
        btm = QHBoxLayout()
        btn_open = QPushButton("在浏览器中打开")
        btn_open.setStyleSheet("background: #1f6feb; color: white; border-radius: 6px; padding: 6px 16px;")
        btm.addWidget(btn_open)
        btm.addStretch()

        btn_cls = QPushButton("关闭")
        btn_cls.clicked.connect(dlg.accept)
        btn_cls.setStyleSheet("background: #21262d; color: #c9d1d9; border-radius: 6px; padding: 6px 16px;")
        btm.addWidget(btn_cls)

        layout.addLayout(btm)

        def load_projects(since="daily", lang=""):
            """加载项目列表"""
            lw.clear()
            status.setText("正在加载...")
            btn_refresh.setEnabled(False)

            token = self.config.get("github_token", "")

            class LoadThread(QThread):
                done = Signal(list)
                err = Signal(str)

                def run(s):
                    try:
                        results = fetch_func(since, lang) if fetch_func else fetch_trending(since, lang, token)
                        if hasattr(results, "items"):
                            results = results.items
                        s.done.emit(results)
                    except Exception as e:
                        s.err.emit(str(e))

            def on_done(results):
                btn_refresh.setEnabled(True)
                if not results:
                    status.setText("没有找到项目")
                    return

                status.setText(f"共 {len(results)} 个项目，项目介绍已自动翻译为中文")
                for i, p in enumerate(results):
                    self._add_github_project_card(lw, p, i)

            def on_err(msg):
                btn_refresh.setEnabled(True)
                status.setText(f"错误: {msg}")

            thread = LoadThread()
            thread.done.connect(on_done)
            thread.err.connect(on_err)
            thread.finished.connect(lambda t=thread: dlg._threads.remove(t) if t in dlg._threads else None)
            thread.finished.connect(thread.deleteLater)
            dlg._threads.append(thread)
            thread.start()

        # 事件连接
        def op():
            url = self._selected_github_url(lw)
            if url:
                QDesktopServices.openUrl(QUrl(url))

        btn_open.clicked.connect(op)
        lw.itemDoubleClicked.connect(op)

        time_map = {"今日": "daily", "本周": "weekly", "本月": "monthly"}

        def on_time_changed(text):
            lang = lang_combo.currentText()
            if lang == "全部":
                lang = ""
            since = time_map.get(text, "daily")
            load_projects(since, lang)

        def on_lang_changed(text):
            since = time_map.get(time_combo.currentText(), "daily")
            lang = text if text != "全部" else ""
            load_projects(since, lang)

        time_combo.currentTextChanged.connect(on_time_changed)
        lang_combo.currentTextChanged.connect(on_lang_changed)

        btn_refresh.clicked.connect(
            lambda: load_projects(time_map.get(time_combo.currentText(), "daily"),
                                   lang_combo.currentText() if lang_combo.currentText() != "全部" else ""))

        # 自动加载
        QTimer.singleShot(100, lambda: load_projects("daily", ""))

        dlg.exec()

    def _show_github_search_dialog(self):
        """GitHub 搜索对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("搜索 GitHub 项目")
        dlg.setMinimumSize(980, 680)
        dlg._threads = []

        layout = QVBoxLayout(dlg)

        # 搜索栏
        top = QHBoxLayout()
        inp = QLineEdit()
        inp.setPlaceholderText("输入搜索关键词（支持中文）...")
        top.addWidget(inp, 1)

        top.addWidget(QLabel("排序:"))
        sort_combo = QComboBox()
        sort_combo.addItems(["星标数", "Fork数", "更新时间"])
        sort_combo.setFixedWidth(100)
        top.addWidget(sort_combo)

        top.addWidget(QLabel("语言:"))
        lang_combo = QComboBox()
        lang_combo.addItems(["全部", "Python", "JavaScript", "TypeScript", "Go", "Rust", "C++", "Java"])
        lang_combo.setFixedWidth(100)
        top.addWidget(lang_combo)

        btn_search = QPushButton("搜索")
        btn_search.setStyleSheet("background: #238636; color: white; border-radius: 6px; padding: 8px 20px;")
        top.addWidget(btn_search)

        layout.addLayout(top)

        status = QLabel("输入关键词并点击搜索")
        status.setStyleSheet("color: #8b949e;")
        layout.addWidget(status)

        lw = QListWidget()
        lw.setStyleSheet("""
            QListWidget { background: #0d1117; border: 1px solid #21262d; border-radius: 8px; padding: 8px; }
            QListWidget::item { margin: 6px 4px; border: none; }
            QListWidget::item:selected { background: transparent; }
        """)
        layout.addWidget(lw)

        btm = QHBoxLayout()
        btn_open = QPushButton("在浏览器中打开")
        btn_open.setStyleSheet("background: #1f6feb; color: white; border-radius: 6px; padding: 6px 16px;")
        btm.addWidget(btn_open)
        btm.addStretch()

        btn_cls = QPushButton("关闭")
        btn_cls.clicked.connect(dlg.accept)
        btn_cls.setStyleSheet("background: #21262d; border-radius: 6px; padding: 6px 16px;")
        btm.addWidget(btn_cls)

        layout.addLayout(btm)

        def do_search(page=1):
            q = inp.text().strip()
            if not q:
                status.setText("请输入搜索关键词")
                return

            lw.clear()
            status.setText("正在搜索...")
            btn_search.setEnabled(False)

            token = self.config.get("github_token", "")
            sort_map = {"星标数": "stars", "Fork数": "forks", "更新时间": "updated"}
            sort = sort_map.get(sort_combo.currentText(), "stars")
            lang = lang_combo.currentText() if lang_combo.currentText() != "全部" else ""

            class SearchThread(QThread):
                done = Signal(object)
                err = Signal(str)

                def run(s):
                    try:
                        result = search_repos(q, lang, sort, "desc", page, 20, token)
                        s.done.emit(result)
                    except Exception as e:
                        s.err.emit(str(e))

            def on_done(result):
                btn_search.setEnabled(True)
                if not result.items:
                    status.setText("没有找到项目")
                    return

                status.setText(f"找到 {result.total_count} 个结果，项目介绍已自动翻译为中文")
                for proj in result.items:
                    self._add_github_project_card(lw, proj, lw.count())

            def on_err(msg):
                btn_search.setEnabled(True)
                status.setText(f"错误: {msg}")

            thread = SearchThread()
            thread.done.connect(on_done)
            thread.err.connect(on_err)
            thread.finished.connect(lambda t=thread: dlg._threads.remove(t) if t in dlg._threads else None)
            thread.finished.connect(thread.deleteLater)
            dlg._threads.append(thread)
            thread.start()

        btn_search.clicked.connect(lambda: do_search(1))
        inp.returnPressed.connect(lambda: do_search(1))

        def op():
            url = self._selected_github_url(lw)
            if url:
                QDesktopServices.openUrl(QUrl(url))

        btn_open.clicked.connect(op)
        lw.itemDoubleClicked.connect(op)

        dlg.exec()


print("Main window module loaded (optimized)")
