"""Visible UI mouse-click smoke test for GitHub Hub.

The test uses a temporary project and replaces network/install operations with
deterministic stubs so no repository or package environment is changed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from app import main_window as mw
from app.github_explorer import SearchResult


class Smoke:
    def __init__(self, window):
        self.window = window
        self.results = []

    def record(self, name, passed, detail=""):
        self.results.append((name, bool(passed), detail))
        output = ("PASS " if passed else "FAIL ") + name + (f": {detail}" if detail else "")
        print(output.encode("gbk", errors="replace").decode("gbk"), flush=True)

    def find_button(self, root, text):
        return next((button for button in root.findChildren(QPushButton) if text in button.text()), None)

    def click(self, button):
        if button is None:
            return False
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QTest.qWait(100)
        return True

    def wait_until(self, predicate, timeout_ms=5000):
        elapsed = 0
        while elapsed < timeout_ms:
            if predicate():
                return True
            QTest.qWait(100)
            elapsed += 100
        return bool(predicate())

    def close_modal_after_click(self, name, button, title_text="", inspect=None):
        state = {"ok": False, "detail": ""}

        def close_dialog():
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                tops = [w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()]
                dialog = tops[-1] if tops else None
            if dialog is None:
                state["detail"] = "dialog not shown"
                return
            title_ok = not title_text or title_text in dialog.windowTitle()
            inspect_ok, detail = (True, "") if inspect is None else inspect(dialog)
            state["ok"] = title_ok and inspect_ok
            state["detail"] = detail or dialog.windowTitle()
            reject = self.find_button(dialog, "取消") or self.find_button(dialog, "关闭")
            if reject:
                self.click(reject)
            else:
                dialog.reject()

        QTimer.singleShot(250, close_dialog)
        self.click(button)
        self.record(name, state["ok"], state["detail"])


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / "fixture_project"
        project.mkdir()
        (project / "requirements.txt").write_text("pip\n", encoding="utf-8")
        (project / "main.py").write_text(
            "import time\nprint('http://127.0.0.1:8765', flush=True)\ntime.sleep(8)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(["git", "config", "user.email", "smoke@example.invalid"], cwd=project, check=True)
        subprocess.run(["git", "config", "user.name", "Smoke Test"], cwd=project, check=True)
        subprocess.run(["git", "add", "."], cwd=project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=project, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(project)], cwd=project, check=True)
        shared = base / "shared"
        shared.mkdir()
        (shared / ".ready").write_text("", encoding="utf-8")
        config_path = base / "config.json"
        config = {
            "projects_dir": str(base / "projects"),
            "shared_dir": str(shared),
            "pip_cache_dir": str(base / "cache"),
            "dep_mode": 0,
            "python_exe": sys.executable,
            "github_token": "",
            "pip_mirror": "官方 PyPI (默认)",
            "github_mirror": "直连 GitHub (默认)",
            "npm_mirror": "官方 npm (默认)",
            "githug_repo": "",
            "githug_branch": "main",
            "version": "1.0.0",
            "projects": [{
                "id": "fixture",
                "name": "fixture_project",
                "local_dir": str(project),
                "html_url": "",
                "description": "UI smoke fixture",
            }],
        }
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        mw.CONFIG_FILE = str(config_path)
        mw.fetch_trending = lambda *args, **kwargs: []
        mw.fetch_by_category = lambda *args, **kwargs: SearchResult()
        mw.get_best_pip_mirror = lambda: "官方 PyPI (默认)"
        mw.pull_repo = lambda *args, **kwargs: True
        mw.install_to_shared_dir = lambda *args, **kwargs: True
        mw.check_for_updates = lambda *args, **kwargs: {
            "has_update": False, "current_version": "1.0.0", "latest_version": "1.0.0", "error": ""
        }

        window = mw.MainWindow()
        window.show()
        QTest.qWait(250)
        window.project_list.select_project_by_id("fixture")
        QTest.qWait(150)
        smoke = Smoke(window)

        smoke.record("main window", window.isVisible() and "GitHub Hub" in window.windowTitle())
        smoke.record("project selected", window.detail.overview_tab.lbl_name.text() == "fixture_project")

        smoke.close_modal_after_click("add project dialog", smoke.find_button(window, "添加项目"), "添加 GitHub 项目")
        smoke.close_modal_after_click("import dialog", smoke.find_button(window, "导入本地项目"), "导入本地项目")

        diag_button = smoke.find_button(window, "诊断工具")
        smoke.click(diag_button)
        QTest.qWait(250)
        diag = next((w for w in QApplication.topLevelWidgets() if "环境诊断" in w.windowTitle()), None)
        smoke.record("diagnostics dialog", bool(diag))
        if diag:
            diag.close()

        smoke.close_modal_after_click("mirror check", smoke.find_button(window, "自动镜像"), "镜像测试结果")
        smoke.close_modal_after_click("settings dialog", smoke.find_button(window, "设置"), "设置")

        def explorer_check(dialog):
            has_removed = any("拉取镜像并安装" in b.text() for b in dialog.findChildren(QPushButton))
            return (not has_removed, "clone/install action absent" if not has_removed else "action still visible")

        smoke.close_modal_after_click("trending dialog", smoke.find_button(window, "热门项目"), "热门项目", explorer_check)
        smoke.close_modal_after_click("category dialog", smoke.find_button(window, "分类浏览"), "分类浏览项目", explorer_check)
        smoke.close_modal_after_click("export import dialog", smoke.find_button(window, "导入/导出"), "导入/导出项目配置")

        window.detail.tabs.setCurrentIndex(1)
        QTest.qWait(100)
        smoke.click(window.detail.dep_panel.btn_refresh)
        smoke.record("dependency refresh", window.detail.dep_panel.table.rowCount() == 1)
        smoke.click(window.detail.dep_panel.btn_install_all)
        install_done = smoke.wait_until(
            lambda: "依赖安装完成" in window.detail.console.text_edit.toPlainText(),
            timeout_ms=8000,
        )
        smoke.record("one click dependencies", install_done)

        window.detail.tabs.setCurrentIndex(2)
        QTest.qWait(100)
        smoke.record("code browser loaded", window.detail.code_tab.tree.topLevelItemCount() == 1)

        smoke.click(window.detail.btn_update)
        update_done = smoke.wait_until(
            lambda: "更新完成" in window.detail.console.text_edit.toPlainText(),
            timeout_ms=8000,
        )
        smoke.record("project update", update_done)

        smoke.click(window.detail.btn_launch)
        QTest.qWait(600)
        smoke.record("project launch", window.detail.btn_launch.text().find("停止") >= 0)
        smoke.record("web url detection", window.detail.btn_browser.isVisible())
        smoke.click(window.detail.btn_launch)
        QTest.qWait(150)
        smoke.record("project stop", window.detail.btn_launch.text().find("启动") >= 0)
        smoke.record("stopped web url hidden", not window.detail.btn_browser.isVisible())
        smoke.record("user stop is not an error", "进程退出码" not in window.detail.console.text_edit.toPlainText())

        def cancel_delete(dialog):
            return (any("删除全部文件" in b.text() for b in dialog.findChildren(QPushButton)), "delete confirmation shown")

        smoke.close_modal_after_click("delete confirmation", window.detail.btn_delete, "删除项目", cancel_delete)

        window.close()
        QTest.qWait(100)
        failures = [(name, detail) for name, passed, detail in smoke.results if not passed]
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
