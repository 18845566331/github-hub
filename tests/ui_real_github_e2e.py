"""Visible, real-network end-to-end run for GitHub clone/install/launch."""

from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.add_project_dialog import AddProjectDialog
from app.main_window import MainWindow


REPO_URL = "https://github.com/shekhargulati/python-flask-docker-hello-world"
TARGET = ROOT / "projects" / "python-flask-docker-hello-world"


def out(text: str):
    safe = text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
        sys.stdout.encoding or "utf-8", errors="replace"
    )
    print(safe, flush=True)


def wait_until(app: QApplication, predicate, timeout: float, label: str):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            out("PASS " + label)
            return True
        time.sleep(0.05)
    out("FAIL " + label)
    return False


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    failures = []

    fresh_clone = not TARGET.exists()
    if fresh_clone:
        toolbar_add = next(
            (button for button in window.findChildren(QPushButton) if "添加项目" in button.text()),
            None,
        )
        if not toolbar_add:
            out("FAIL add project toolbar button not found")
            return 2

        def fill_add_dialog():
            dialog = QApplication.activeModalWidget()
            if not isinstance(dialog, AddProjectDialog):
                failures.append("add dialog did not open")
                return
            dialog.url_edit.setText(REPO_URL)
            dialog.dir_edit.setText(str(TARGET))
            QTest.mouseClick(dialog.btn_ok, Qt.MouseButton.LeftButton)

        QTimer.singleShot(200, fill_add_dialog)
        QTest.mouseClick(toolbar_add, Qt.MouseButton.LeftButton)
        out("ACTION clicked Add Project and submitted real GitHub URL")
    else:
        project = next(
            (item for item in window.config.get("projects", []) if Path(item.get("local_dir", "")) == TARGET),
            None,
        )
        if not project:
            out("FAIL existing cloned target is absent from application project list")
            return 2
        window.project_list.select_project_by_id(project["id"])
        app.processEvents()
        out("ACTION selected real project already cloned in prior phase")

    accepted_install = {"done": False}
    timer = QTimer()

    def accept_install_prompt():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox) and "安装依赖" in dialog.windowTitle():
            button = dialog.button(QMessageBox.StandardButton.Yes)
            if button:
                accepted_install["done"] = True
                out("ACTION accepted dependency installation prompt")
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    timer.timeout.connect(accept_install_prompt)
    timer.start(100)

    cloned = wait_until(app, lambda: (TARGET / ".git").is_dir(), 90, "real git clone")
    if not fresh_clone:
        QTest.mouseClick(window.detail.btn_install, Qt.MouseButton.LeftButton)
        out("ACTION clicked real dependency installation button")
    installed = wait_until(
        app,
        lambda: bool(window._get_current_project() and window._get_current_project().get("status") == "ready"),
        180,
        "real dependency installation",
    )
    timer.stop()
    if fresh_clone and not accepted_install["done"]:
        failures.append("automatic install prompt was not accepted")
    if not cloned:
        failures.append("clone failed")
    if not installed:
        failures.append("dependency installation failed")

    install_log = window.detail.console.text_edit.toPlainText()
    out("INSTALL_LOG_BEGIN")
    out(install_log[-4000:])
    out("INSTALL_LOG_END")

    if installed:
        QTest.mouseClick(window.detail.btn_launch, Qt.MouseButton.LeftButton)
        launched = wait_until(
            app,
            lambda: bool(
                window._get_current_project()
                and window._get_current_project().get("id") in window._processes
                and window._processes[window._get_current_project().get("id")].is_running
            ),
            20,
            "real project process start",
        )
        detected = wait_until(app, lambda: bool(window.detail._current_url), 20, "local web URL detected")
        if launched and detected:
            url = window.detail._current_url
            try:
                with urllib.request.urlopen(url, timeout=10) as response:
                    body = response.read().decode("utf-8", errors="replace")
                if response.status == 200 and "Flask inside Docker" in body:
                    out("PASS real HTTP response " + url)
                else:
                    failures.append("unexpected HTTP response")
            except Exception as exc:
                failures.append("HTTP verification failed: " + str(exc))
        else:
            failures.append("launch or URL detection failed")
        launch_log = window.detail.console.text_edit.toPlainText()
        out("LAUNCH_LOG_BEGIN")
        out(launch_log[-4000:])
        out("LAUNCH_LOG_END")
        if window.detail.btn_launch.isEnabled():
            QTest.mouseClick(window.detail.btn_launch, Qt.MouseButton.LeftButton)
            wait_until(
                app,
                lambda: not window._processes.get(window._get_current_project().get("id")),
                10,
                "real project stop",
            )

    window.close()
    app.processEvents()
    for failure in failures:
        out("FAIL " + failure)
    out("REAL_E2E_RESULT " + ("PASS" if not failures else "FAIL"))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
