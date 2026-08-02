import subprocess
import sys
import unittest

import mxbiflow
from mxbiflow.bootstrap import init_gameloop
from mxbiflow.core.context import MXBIFlow, get_mxbiflow
from mxbiflow.core.path import get_base_path, set_base_path
from mxbiflow.scene import Scene, SceneManager


class PublicApiTests(unittest.TestCase):
    def test_top_level_exports_are_explicit(self) -> None:
        expected_exports = {
            "MXBIFlow",
            "Scene",
            "SceneManager",
            "get_base_path",
            "get_mxbiflow",
            "init_gameloop",
            "set_base_path",
        }

        self.assertEqual(set(mxbiflow.__all__), expected_exports)
        self.assertIs(mxbiflow.MXBIFlow, MXBIFlow)
        self.assertIs(mxbiflow.Scene, Scene)
        self.assertIs(mxbiflow.SceneManager, SceneManager)
        self.assertIs(mxbiflow.get_base_path, get_base_path)
        self.assertIs(mxbiflow.get_mxbiflow, get_mxbiflow)
        self.assertIs(mxbiflow.init_gameloop, init_gameloop)
        self.assertIs(mxbiflow.set_base_path, set_base_path)

    def test_top_level_api_imports_in_fresh_process_without_ui(self) -> None:
        code = """
import sys
from mxbiflow import (
    MXBIFlow,
    Scene,
    SceneManager,
    get_base_path,
    get_mxbiflow,
    init_gameloop,
    set_base_path,
)
assert "mxbiflow.ui" not in sys.modules
"""

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
