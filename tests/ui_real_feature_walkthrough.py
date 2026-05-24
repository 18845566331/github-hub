"""Mouse-driven feature verification against the real cloned Flask project."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QLineEdit, QListWidget, QMessageBox, QPushButton


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.diagnostics_dialog import DiagnosticsDialog
from app.main_window import MainWindow


TARGET = ROOT / "projects" / "python-flask-docker-hello-world"


def out(text: str):
    encoding = sys.stdout.encoding or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"), flush=True)


def wait(app, predicate, timeout, name):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            out("PASS " + name)
            return True
        time.sleep(0.05)
    out("FAIL " + name)
    return False


def toolbar_button(window, text):
    return next((b for b in window.findChildren(QPushButton) if text in b.text()), None)


def close_message_boxes():
    dialog = QApplication.activeModalWidget()
    if isinstance(dialog, QMessageBox):
        button = dialog.button(QMessageBox.StandardButton.Ok)
        if button:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    failures = []
    project = next(
        (item for item in window.config.get("projects", []) if Path(item.get("local_dir", "")) == TARGET),
        None,
    )
    if not project:
        out("FAIL real test project missing from project list")
        return 2
    window.project_list.select_project_by_id(project["id"])
    app.processEvents()

    # Dependency table initially reflects the deliberately removed flask package.
    dep_index = window.detail.tabs.indexOf(window.detail.dep_panel)
    QTest.mouseClick(window.detail.tabs.tabBar(), Qt.MouseButton.LeftButton,
                     pos=window.detail.tabs.tabBar().tabRect(dep_index).center())
    QTest.mouseClick(window.detail.dep_panel.btn_refresh, Qt.MouseButton.LeftButton)
    if not wait(app, lambda: window.detail.dep_panel.table.rowCount() >= 1, 10, "dependency panel refresh"):
        failures.append("dependency table did not populate")

    # Diagnostics: flask was removed before this script; detect and genuinely reinstall it.
    diag_button = toolbar_button(window, "诊断工具")
    if diag_button:
        QTest.mouseClick(diag_button, Qt.MouseButton.LeftButton)
        diag = next((w for w in QApplication.topLevelWidgets() if isinstance(w, DiagnosticsDialog) and w.isVisible()), None)
        if diag:
            QTest.mouseClick(diag.tabs.tabBar(), Qt.MouseButton.LeftButton,
                             pos=diag.tabs.tabBar().tabRect(1).center())
            QTest.mouseClick(diag.btn_check_proj, Qt.MouseButton.LeftButton)
            found_missing = wait(
                app, lambda: "flask" in [x.lower() for x in getattr(diag, "_proj_check_results", {}).get("missing", [])],
                30, "diagnostics detect removed flask",
            )
            if found_missing:
                QTest.mouseClick(diag.btn_install_missing, Qt.MouseButton.LeftButton)
                wait(app, lambda: diag.btn_install_missing.isEnabled(), 120, "diagnostics install missing package")
                QTest.mouseClick(diag.btn_check_proj, Qt.MouseButton.LeftButton)
                restored = wait(
                    app,
                    lambda: hasattr(diag, "_proj_check_results") and not diag._proj_check_results.get("missing"),
                    30,
                    "diagnostics restored project environment",
                )
                if not restored:
                    failures.append("diagnostic repair did not restore venv")
            else:
                failures.append("diagnostics did not identify removed flask")
            diag.close()
        else:
            failures.append("diagnostics dialog did not open")

    # Once diagnostics restored the package, run real per-row package operations.
    window.detail.dep_panel.refresh()
    row_actions = window.detail.dep_panel.table.cellWidget(0, 5)
    operation_logs = []
    window.detail.dep_panel.log_requested.connect(operation_logs.append)
    if row_actions:
        upgrade = next((b for b in row_actions.findChildren(QPushButton) if "升级" in b.text()), None)
        if upgrade:
            operation_logs.clear()
            QTest.mouseClick(upgrade, Qt.MouseButton.LeftButton)
            completed = wait(
                app,
                lambda: any("[SUCCESS] 依赖操作完成" in line for line in operation_logs),
                120, "dependency row real upgrade",
            )
            if not completed:
                failures.append("dependency upgrade did not complete")
        row_actions = window.detail.dep_panel.table.cellWidget(0, 5)
        version = next((b for b in row_actions.findChildren(QPushButton) if "指定版本" in b.text()), None)
        if version:
            def enter_version():
                dialog = QApplication.activeModalWidget()
                if isinstance(dialog, QInputDialog):
                    edit = dialog.findChild(QLineEdit)
                    edit.setText("3.1.3")
                    dialog.accept()
            operation_logs.clear()
            QTimer.singleShot(150, enter_version)
            QTest.mouseClick(version, Qt.MouseButton.LeftButton)
            completed = wait(
                app,
                lambda: any("[SUCCESS] 依赖操作完成" in line for line in operation_logs),
                120, "dependency row real pinned version",
            )
            if not completed:
                failures.append("pinned dependency install did not complete")
    else:
        failures.append("dependency action buttons unavailable after repair")

    # Update performs a real git pull from GitHub.
    QTest.mouseClick(window.detail.btn_update, Qt.MouseButton.LeftButton)
    if not wait(app, lambda: window._get_current_project().get("status") == "ready", 90, "real git update"):
        failures.append("git update failed")
    update_log = window.detail.console.text_edit.toPlainText()
    out("UPDATE_LOG_BEGIN")
    out(update_log[-1500:])
    out("UPDATE_LOG_END")

    # Mirror detection performs real network checks; dismiss its information popup by mouse.
    mirror = toolbar_button(window, "自动镜像")
    timer = QTimer()
    timer.timeout.connect(close_message_boxes)
    timer.start(100)
    if mirror:
        QTest.mouseClick(mirror, Qt.MouseButton.LeftButton)
        out("PASS real mirror network check")
    timer.stop()

    # Online GitHub explorers fetch their real result lists and have no install action.
    for button_text, name in (("热门项目", "trending browser"), ("分类浏览", "category browser")):
        button = toolbar_button(window, button_text)
        seen = {"ok": False}
        opened_at = time.time()
        poll = QTimer()

        def inspect_and_close(seen=seen):
            dialogs = [w for w in QApplication.topLevelWidgets()
                       if isinstance(w, QDialog) and w.isVisible() and w is not window]
            for dialog in dialogs:
                lists = dialog.findChildren(QListWidget)
                buttons = dialog.findChildren(QPushButton)
                if lists and lists[0].count() > 0:
                    seen["ok"] = not any("拉取镜像并安装" in b.text() for b in buttons)
                    dialog.accept()
                elif time.time() - opened_at > 25:
                    dialog.reject()

        poll.timeout.connect(inspect_and_close)
        poll.start(200)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        poll.stop()
        if seen["ok"]:
            out("PASS real " + name + " fetch and removed install action")
        else:
            failures.append(name + " did not return live results")

    window.close()
    app.processEvents()
    for failure in failures:
        out("FAIL " + failure)
    out("REAL_FEATURE_RESULT " + ("PASS" if not failures else "FAIL"))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
