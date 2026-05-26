import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import mirror_manager as mirrors


class NetworkAccelerationTests(unittest.TestCase):
    def test_pip_preflight_switches_to_reachable_faster_source(self):
        speeds = {
            "https://pypi.org/simple/": -1.0,
            mirrors.PIP_MIRRORS["清华大学 TUNA"]: 0.22,
            mirrors.PIP_MIRRORS["阿里云"]: 0.51,
        }
        with patch.object(mirrors, "test_mirror_speed", side_effect=lambda url: speeds.get(url, -1.0)):
            chosen = mirrors.choose_pip_mirror("官方 PyPI (默认)", True)
        self.assertEqual(chosen, "清华大学 TUNA")

    def test_automatic_check_can_be_disabled(self):
        with patch.object(mirrors, "test_mirror_speed") as test_speed:
            chosen = mirrors.choose_npm_mirror("淘宝 npmmirror", False)
        self.assertEqual(chosen, "淘宝 npmmirror")
        test_speed.assert_not_called()

    def test_npm_preflight_changes_registry_and_reports_selection(self):
        logs = []
        with patch.object(
            mirrors, "test_mirror_speed",
            side_effect=lambda url: 0.1 if "npmmirror" in url else -1.0,
        ):
            chosen = mirrors.choose_npm_mirror("官方 npm (默认)", True, logs.append)
        self.assertEqual(chosen, "淘宝 npmmirror")
        self.assertIn("自动切换 npm 源 淘宝 npmmirror", "\n".join(logs))

    def test_git_clone_uses_direct_when_direct_transport_is_reachable(self):
        repo = "https://github.com/example/demo.git"

        def probe(url):
            return 0.5 if url == repo else 0.1

        with patch.object(mirrors, "test_git_remote", side_effect=probe):
            candidates = mirrors.get_git_clone_candidates(repo, auto_select=True)
        self.assertEqual(candidates[0], ("直连 GitHub (默认)", repo))

    def test_git_clone_falls_back_to_tested_relay_when_direct_fails(self):
        repo = "https://github.com/example/demo.git"
        logs = []

        def probe(url):
            return 0.18 if "gitclone.com" in url else -1.0

        with patch.object(mirrors, "test_git_remote", side_effect=probe):
            candidates = mirrors.get_git_clone_candidates(
                repo, "直连 GitHub (默认)", True, logs.append
            )
        self.assertEqual(candidates[0][0], "GitClone 代理")
        self.assertIn("第三方克隆链路", "\n".join(logs))


if __name__ == "__main__":
    unittest.main()
