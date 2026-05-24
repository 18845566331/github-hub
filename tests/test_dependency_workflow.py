import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app import dependency_manager as dm
from app.dependency_panel import DependencyPanel
from app.project_launcher import detect_launch_candidates
from app.project_recipes import get_verified_recipe


class DependencyWorkflowTests(unittest.TestCase):
    def test_verified_recipe_selected_by_repository_url(self):
        recipe = get_verified_recipe({
            "clone_url": "https://github.com/shekhargulati/python-flask-docker-hello-world.git"
        })
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe["install"]["requirements"], ["requirements.txt"])

    def test_verified_node_recipe_uses_tools_dev_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text("{}", encoding="utf-8")
            recipe = get_verified_recipe({"full_name": "nexu-io/open-design"})
            with patch("app.project_launcher.resolve_node_cli_command", side_effect=lambda cmd: cmd):
                candidate = detect_launch_candidates(str(project), {}, recipe)[0]
            self.assertEqual(candidate["cmd"], ["pnpm", "run", "tools-dev"])
            self.assertTrue(candidate["verified_recipe"])

    def test_verified_recipe_controls_install_and_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "requirements.txt").write_text("flask\n", encoding="utf-8")
            (project / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
            (project / "app.py").write_text("print('ready')\n", encoding="utf-8")
            recipe = get_verified_recipe({
                "owner": "shekhargulati",
                "repo": "python-flask-docker-hello-world",
            })
            commands = []

            def fake_pip(cmd, cwd=None, callback=None, auto_fix_ctx=None):
                commands.append(cmd)
                return True

            def fake_run(cmd, **kwargs):
                if cmd[1:3] == ["-m", "venv"]:
                    python_path = project / ".venv" / (
                        "Scripts/python.exe" if os.name == "nt" else "bin/python"
                    )
                    python_path.parent.mkdir(parents=True, exist_ok=True)
                    python_path.write_text("", encoding="utf-8")
                return type("Result", (), {"returncode": 0})()

            with patch.object(dm, "_ensure_uv_installed", return_value=False), \
                 patch.object(dm, "_run_pip_with_progress", side_effect=fake_pip), \
                 patch.object(dm.subprocess, "run", side_effect=fake_run):
                ok = dm.install_with_venv(
                    str(project), str(project / ".venv"),
                    python_exe=sys.executable, recipe=recipe,
                )

            self.assertTrue(ok)
            command_text = [" ".join(command) for command in commands]
            self.assertTrue(any("requirements.txt" in command for command in command_text))
            self.assertFalse(any("requirements-dev.txt" in command for command in command_text))
            candidates = detect_launch_candidates(
                str(project), {"dep_mode": 1, "python_exe": sys.executable}, recipe
            )
            self.assertEqual(candidates[0]["cmd"][-1], "app.py")
            self.assertTrue(candidates[0]["verified_recipe"])

    def test_python_one_click_installs_all_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "python_project"
            project.mkdir()
            (project / "requirements.txt").write_text("alpha==1\n", encoding="utf-8")
            (project / "requirements-dev.txt").write_text("beta==2\n", encoding="utf-8")
            (project / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
            commands = []

            def fake_pip(cmd, cwd=None, callback=None, auto_fix_ctx=None):
                commands.append((cmd, cwd))
                return True

            def fake_run(cmd, **kwargs):
                if cmd[1:3] == ["-m", "venv"]:
                    venv_python = Path(cmd[-1]) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                    venv_python.parent.mkdir(parents=True, exist_ok=True)
                    venv_python.write_text("", encoding="utf-8")
                return type("Result", (), {"returncode": 0})()

            with patch.object(dm, "_ensure_uv_installed", return_value=False), \
                 patch.object(dm, "_run_pip_with_progress", side_effect=fake_pip), \
                 patch.object(dm.subprocess, "run", side_effect=fake_run):
                ok = dm.install_with_venv(
                    str(project), str(project / ".venv"),
                    python_exe=sys.executable,
                )

            self.assertTrue(ok)
            flattened = [" ".join(command) for command, _ in commands]
            self.assertTrue(any("requirements.txt" in command for command in flattened))
            self.assertTrue(any("requirements-dev.txt" in command for command in flattened))
            self.assertTrue(any(command.endswith(" .") for command in flattened))

    def test_node_project_does_not_create_python_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text('{"dependencies":{"left-pad":"^1.3.0"}}', encoding="utf-8")
            with patch.object(dm, "_ensure_uv_installed") as uv, \
                 patch.object(dm, "_npm_install", return_value=True) as npm:
                ok = dm.install_with_venv(str(project), str(project / ".venv"))
            self.assertTrue(ok)
            uv.assert_not_called()
            npm.assert_called_once()
            self.assertFalse((project / ".venv").exists())

    def test_node_status_and_locked_install_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text(
                json.dumps({"dependencies": {"present": "^1.0.0", "missing": "^2.0.0"}}),
                encoding="utf-8",
            )
            installed = project / "node_modules" / "present"
            installed.mkdir(parents=True)
            (installed / "package.json").write_text('{"version":"1.2.0"}', encoding="utf-8")
            items = {item["name"]: item for item in dm.get_project_dependency_status(str(project))}
            self.assertEqual(items["present"]["status"], "installed")
            self.assertEqual(items["missing"]["status"], "missing")

            (project / "package-lock.json").write_text("{}", encoding="utf-8")
            self.assertEqual(dm.build_node_install_command(str(project)), ["npm", "ci"])
            (project / "pnpm-lock.yaml").write_text("", encoding="utf-8")
            self.assertEqual(
                dm.build_node_install_command(str(project)),
                ["pnpm", "install", "--frozen-lockfile"],
            )

    def test_windows_node_cli_uses_cmd_shim_for_subprocess(self):
        with patch.object(dm.os, "name", "nt"), \
             patch.object(dm.shutil, "which", side_effect=lambda value: "C:/tools/pnpm.cmd" if value == "pnpm.cmd" else None):
            self.assertEqual(
                dm.resolve_node_cli_command(["pnpm", "install"]),
                ["C:/tools/pnpm.cmd", "install"],
            )

    def test_node_tools_dev_script_is_launchable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "package.json").write_text(
                '{"scripts":{"tools-dev":"node server.js"}}', encoding="utf-8"
            )
            candidates = detect_launch_candidates(str(project))
            self.assertTrue(any(candidate["cmd"][-1] == "tools-dev" for candidate in candidates))

    def test_pnpm_workspace_single_package_action_targets_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "pnpm-lock.yaml").write_text("", encoding="utf-8")
            (project / "pnpm-workspace.yaml").write_text("packages: []\n", encoding="utf-8")
            launched = []

            class FakeProcess:
                stdout = []
                returncode = 0

                def wait(self):
                    return 0

            def fake_popen(cmd, **kwargs):
                launched.append(cmd)
                return FakeProcess()

            with patch.object(dm, "resolve_node_cli_command", side_effect=lambda cmd: cmd), \
                 patch.object(dm.subprocess, "Popen", side_effect=fake_popen):
                self.assertTrue(dm.install_node_package(str(project), "tsx@4.22.3"))
            self.assertEqual(launched[0], ["pnpm", "add", "tsx@4.22.3", "--workspace-root"])

    def test_non_python_projects_only_run_their_native_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "go.mod").write_text("module smoke\n", encoding="utf-8")
            with patch.object(dm, "_go_mod_download", return_value=True) as go, \
                 patch.object(dm, "_ensure_uv_installed") as uv:
                self.assertTrue(dm.install_with_venv(str(project), str(project / ".venv")))
            go.assert_called_once()
            uv.assert_not_called()

    def test_pyproject_uv_no_build_skips_self_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "pyproject.toml").write_text(
                "[project]\nname='resource-index'\ndependencies=[]\n\n[tool.uv]\nno-build=true\n",
                encoding="utf-8",
            )
            logs = []
            with patch.object(dm, "_ensure_uv_installed", return_value=True), \
                 patch.object(dm, "_run_pip_with_progress") as installer, \
                 patch.object(dm.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()):
                ok = dm.install_with_venv(
                    str(project), str(project / ".venv"),
                    python_exe=sys.executable, callback=logs.append,
                )
            self.assertTrue(ok)
            installer.assert_not_called()
            self.assertTrue(any("跳过安装项目本身" in line for line in logs))

    def test_status_fallback_does_not_truncate_package_names_without_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            (project / "requirements.txt").write_text("flask\n", encoding="utf-8")
            venv = Path(tmp) / "venv"
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
            python_exe = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            items = dm.get_project_dependency_status(str(project), str(python_exe))
            self.assertEqual(items[0]["name"], "flask")
            self.assertEqual(items[0]["status"], "missing")


class DependencyPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_workers(self, panel):
        panel._thread_pool.waitForDone(3000)
        self.app.processEvents()

    def test_package_spec_variants(self):
        panel = DependencyPanel()
        python_dep = {"name": "requests", "raw": "requests>=2"}
        node_dep = {"name": "react", "manager": "npm"}
        self.assertEqual(panel._package_spec(python_dep, "install"), "requests>=2")
        self.assertEqual(panel._package_spec(python_dep, "upgrade"), "requests")
        self.assertEqual(panel._package_spec(python_dep, "version", "2.32.0"), "requests==2.32.0")
        self.assertEqual(panel._package_spec(node_dep, "upgrade"), "react@latest")
        self.assertEqual(panel._package_spec(node_dep, "version", "18.3.0"), "react@18.3.0")

    def test_python_row_upgrade_routes_to_target_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            env_python = project / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
            env_python.parent.mkdir(parents=True)
            env_python.write_text("", encoding="utf-8")
            panel = DependencyPanel()
            panel._project = {"local_dir": str(project)}
            panel._config = {"dep_mode": 1, "python_exe": sys.executable, "pip_mirror": "官方 PyPI (默认)"}
            with patch("app.dependency_panel.install_python_package", return_value=True) as installer:
                panel._run_action("upgrade", {"name": "requests", "raw": "requests>=2"})
                self.wait_workers(panel)
            installer.assert_called_once()
            self.assertEqual(installer.call_args.args[0], "requests")
            self.assertEqual(installer.call_args.args[1], str(env_python))
            self.assertTrue(installer.call_args.kwargs.get("upgrade", installer.call_args.args[-1]))

    def test_node_row_install_uses_node_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = DependencyPanel()
            panel._project = {"local_dir": tmp}
            panel._config = {"dep_mode": 1, "npm_mirror": "官方 npm (默认)"}
            with patch("app.dependency_panel.install_node_package", return_value=True) as installer:
                panel._run_action("version", {"name": "react", "manager": "npm"}, "18.3.0")
                self.wait_workers(panel)
            installer.assert_called_once()
            self.assertEqual(installer.call_args.args[1], "react@18.3.0")

    def test_missing_python_environment_requests_full_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = DependencyPanel()
            panel._project = {"local_dir": tmp}
            panel._config = {"dep_mode": 1}
            requested = []
            panel.install_all_requested.connect(lambda: requested.append(True))
            panel._run_action("install", {"name": "requests", "raw": "requests"})
            self.assertEqual(requested, [True])


if __name__ == "__main__":
    unittest.main()
