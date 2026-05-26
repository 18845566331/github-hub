"""
dependency_panel.py - Per-project dependency management UI.
"""
import os

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QInputDialog,
)

from .dependency_manager import (
    get_project_dependency_status, install_python_package,
    install_node_package,
)
from .mirror_manager import (
    build_pip_args, build_npm_args, choose_pip_mirror, choose_npm_mirror,
)
from .workers import Worker


STATUS_TEXT = {
    "installed": "正常",
    "missing": "未安装",
    "conflict": "版本问题",
    "manual": "需手动",
    "skipped": "跳过",
    "unknown": "未知",
}

STATUS_COLOR = {
    "installed": "#00e676",
    "missing": "#ffd600",
    "conflict": "#ff1744",
    "manual": "#d2a8ff",
    "skipped": "#7c85a6",
    "unknown": "#7c85a6",
}

ACTION_BUTTON_STYLE = """
    QPushButton {
        min-height: 18px;
        max-height: 18px;
        padding: 0 4px;
        font-size: 10px;
        border-radius: 4px;
    }
"""


class DependencyPanel(QWidget):
    install_all_requested = Signal()
    log_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = {}
        self._config = {}
        self._items = []
        self._thread_pool = QThreadPool.globalInstance()
        self._active_workers = set()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("依赖管理")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #f8f9fa;")
        top.addWidget(title)
        top.addStretch()

        self.summary_label = QLabel("未选择项目")
        self.summary_label.setStyleSheet("color: #7c85a6; font-size: 12px;")
        top.addWidget(self.summary_label)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)

        self.btn_install_all = QPushButton("安装全部依赖")
        self.btn_install_all.clicked.connect(self.install_all_requested.emit)
        top.addWidget(self.btn_install_all)
        layout.addLayout(top)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["状态", "依赖", "要求版本", "当前版本", "说明", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 130)
        self.table.setColumnWidth(5, 230)
        self.table.setStyleSheet("""
            QTableWidget { border: 1px solid #191c2b; border-radius: 6px; }
            QTableWidget::item { padding: 3px 6px; }
            QTableWidget QPushButton {
                min-height: 18px;
                max-height: 18px;
                padding: 0 4px;
                font-size: 10px;
            }
        """)
        layout.addWidget(self.table, 1)

    def load_project(self, project: dict, config: dict):
        self._project = project or {}
        self._config = config or {}
        self.refresh()

    def _start_worker(self, worker):
        self._active_workers.add(worker)
        worker.signals.finished.connect(lambda w=worker: self._active_workers.discard(w))
        self._thread_pool.start(worker)

    def _runtime_info(self):
        local_dir = self._project.get("local_dir", "")
        dep_mode = self._config.get("dep_mode", 1)
        if dep_mode == 1:
            venv_dir = os.path.join(local_dir, ".venv")
            if os.name == "nt":
                python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
            else:
                python_exe = os.path.join(venv_dir, "bin", "python")
            extra_paths = None
        else:
            python_exe = self._config.get("python_exe") or ""
            shared_dir = self._config.get("shared_dir", "")
            extra_paths = [shared_dir] if shared_dir else None
        return local_dir, python_exe, extra_paths

    def refresh(self):
        local_dir, python_exe, extra_paths = self._runtime_info()
        self.table.setRowCount(0)
        if not local_dir or not os.path.isdir(local_dir):
            self.summary_label.setText("项目目录不存在")
            return
        self._items = get_project_dependency_status(local_dir, python_exe, extra_paths)
        installed = sum(1 for item in self._items if item.get("status") == "installed")
        missing = sum(1 for item in self._items if item.get("status") == "missing")
        conflict = sum(1 for item in self._items if item.get("status") == "conflict")
        self.summary_label.setText(f"{installed}/{len(self._items)} 正常，{missing} 未安装，{conflict} 版本问题")
        for item in self._items:
            self._add_row(item)

    def _add_row(self, dep: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)
        status = dep.get("status", "unknown")
        status_text = STATUS_TEXT.get(status, status)
        status_item = QTableWidgetItem(status_text)
        status_item.setForeground(QColor(STATUS_COLOR.get(status, "#7c85a6")))
        self.table.setItem(row, 0, status_item)
        self.table.setItem(row, 1, QTableWidgetItem(dep.get("name", "")))
        self.table.setItem(row, 2, QTableWidgetItem(dep.get("required", "")))
        self.table.setItem(row, 3, QTableWidgetItem(dep.get("installed", "")))
        self.table.setItem(row, 4, QTableWidgetItem(dep.get("message", "")))

        action_box = QWidget()
        action_layout = QHBoxLayout(action_box)
        action_layout.setContentsMargins(4, 1, 4, 1)
        action_layout.setSpacing(4)

        btn_install = QPushButton("安装")
        btn_install.setFixedSize(46, 20)
        btn_install.setStyleSheet(ACTION_BUTTON_STYLE)
        btn_install.setEnabled(status in ("missing", "conflict", "unknown", "manual"))
        btn_install.clicked.connect(lambda _, d=dep: self._run_action("install", d))
        action_layout.addWidget(btn_install)

        btn_upgrade = QPushButton("升级")
        btn_upgrade.setFixedSize(46, 20)
        btn_upgrade.setStyleSheet(ACTION_BUTTON_STYLE)
        btn_upgrade.clicked.connect(lambda _, d=dep: self._run_action("upgrade", d))
        action_layout.addWidget(btn_upgrade)

        btn_version = QPushButton("指定版本")
        btn_version.setFixedSize(68, 20)
        btn_version.setStyleSheet(ACTION_BUTTON_STYLE)
        btn_version.clicked.connect(lambda _, d=dep: self._ask_version(d))
        action_layout.addWidget(btn_version)
        action_layout.addStretch()

        self.table.setCellWidget(row, 5, action_box)
        self.table.setRowHeight(row, 28)

    def _package_spec(self, dep: dict, action: str, version: str = ""):
        name = dep.get("name", "").strip()
        if not name:
            return dep.get("raw", "")
        if dep.get("manager") == "npm":
            if action == "upgrade":
                return f"{name}@latest"
            if version:
                return f"{name}@{version}"
            return name
        if action == "upgrade":
            return name
        if version:
            if version.startswith(("==", ">=", "<=", "~=", ">", "<")):
                return f"{name}{version}"
            return f"{name}=={version}"
        return dep.get("raw") or name

    def _ask_version(self, dep: dict):
        version, ok = QInputDialog.getText(
            self, "指定版本",
            f"输入 {dep.get('name', '')} 的版本，例如 1.2.3 或 ==1.2.3"
        )
        if ok and version.strip():
            self._run_action("version", dep, version.strip())

    def _run_action(self, action: str, dep: dict, version: str = ""):
        local_dir, env_python, _ = self._runtime_info()
        if not local_dir:
            return
        spec = self._package_spec(dep, action, version)
        if not spec:
            return
        if dep.get("manager") != "npm" and not os.path.exists(env_python):
            self.log_requested.emit("[WARN] 项目虚拟环境尚未创建，请先点击“安装全部依赖”")
            self.install_all_requested.emit()
            return
        self.btn_refresh.setEnabled(False)
        self.btn_install_all.setEnabled(False)
        self.log_requested.emit(f"[INFO] 依赖操作: {spec}")

        def task():
            auto_network = self._config.get("auto_network_acceleration", False)
            if dep.get("manager") == "npm":
                npm_source = choose_npm_mirror(
                    self._config.get("npm_mirror", ""), auto_network, self.log_requested.emit
                )
                npm_args = build_npm_args(npm_source)
                return install_node_package(local_dir, spec, self.log_requested.emit, npm_args)
            pip_source = choose_pip_mirror(
                self._config.get("pip_mirror", ""), auto_network, self.log_requested.emit
            )
            pip_args = build_pip_args(pip_source)
            manager_python = self._config.get("python_exe") or None
            return install_python_package(
                spec, env_python, manager_python, self.log_requested.emit,
                pip_args, upgrade=(action == "upgrade"),
            )

        worker = Worker(task)
        worker.signals.result.connect(lambda ok: self._on_action_done(bool(ok)))
        worker.signals.error.connect(lambda err: self._on_action_error(err))
        self._start_worker(worker)

    def _on_action_done(self, ok: bool):
        self.log_requested.emit("[SUCCESS] 依赖操作完成" if ok else "[ERROR] 依赖操作失败")
        self.btn_refresh.setEnabled(True)
        self.btn_install_all.setEnabled(True)
        self.refresh()

    def _on_action_error(self, err: str):
        self.log_requested.emit(f"[ERROR] 依赖操作异常: {err}")
        self.btn_refresh.setEnabled(True)
        self.btn_install_all.setEnabled(True)
