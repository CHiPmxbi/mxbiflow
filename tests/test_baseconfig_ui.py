import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mxbiflow.core.path import get_mxbi_config_path, set_base_path
from mxbiflow.driver import MXBIModel
from mxbiflow.models.database import MXBIDatabase
from mxbiflow.ui.mxbi_panel import MXBIPanel


class BaseConfigTests(unittest.TestCase):
    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        application = QApplication.instance()
        cls.application = (
            application if isinstance(application, QApplication) else QApplication([])
        )

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._home_patch = patch.dict(
            os.environ, {"HOME": self._temporary_directory.name}
        )
        self._home_patch.start()
        set_base_path(Path(self._temporary_directory.name))

    def tearDown(self) -> None:
        self.application.processEvents()
        self._home_patch.stop()
        self._temporary_directory.cleanup()

    def test_panel_edits_the_device_global_config(self) -> None:
        config_path = get_mxbi_config_path()
        self.assertEqual(
            config_path,
            Path(self._temporary_directory.name) / ".config" / "mxbi" / "mxbi.json",
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '{"mxbi_id": "outdated", "screen_size": [1024, 600]}', encoding="utf-8"
        )

        panel = MXBIPanel()
        QTest.mouseClick(panel.save_button, Qt.MouseButton.LeftButton)

        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertNotIn("mxbi_id", saved)
        panel.close()

    def test_missing_mxbi_config_creates_default(self) -> None:
        # Regression: on a fresh machine without config/mxbi.json, the
        # wizard must be able to generate a default config instead of
        # crashing on required fields.
        panel = MXBIPanel()
        config_path = get_mxbi_config_path()
        self.assertTrue(config_path.is_file())
        MXBIModel.model_validate_json(config_path.read_text(encoding="utf-8"))
        panel.close()

    def test_legacy_database_options_are_ignored_and_not_exported(self) -> None:
        database = MXBIDatabase.model_validate(
            {
                "mxbis": ["mxbi1"],
                "experimenter": ["tester"],
                "animals": {"abcd": "mouse"},
            }
        )

        exported = database.model_dump()
        self.assertNotIn("mxbis", exported)
        # Animals come from the cogmote configuration now (#173).
        self.assertNotIn("animals", exported)
        self.assertEqual(exported["experimenter"], ["tester"])


if __name__ == "__main__":
    unittest.main()
