import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

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

    @patch("mxbiflow.ui.components.baseconfig.socket.gethostname")
    def test_hostname_is_read_only_and_saved_as_mxbi_id(
        self, gethostname: Mock
    ) -> None:
        gethostname.return_value = "mxbi-host"
        config_path = get_mxbi_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            MXBIModel(
                mxbi_id="outdated",
                backup_source_root_id="original-source",
                backup_destination_root_id="original-destination",
            ).model_dump_json(indent=4),
            encoding="utf-8",
        )

        panel = MXBIPanel()
        labels = [label.text() for label in panel.findChildren(QLabel)]
        self.assertIn("mxbi-host", labels)

        QTest.mouseClick(panel.save_button, Qt.MouseButton.LeftButton)

        saved = MXBIModel.model_validate_json(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved.mxbi_id, "mxbi-host")
        panel.close()

    def test_backup_root_ids_are_loaded_and_saved(self) -> None:
        config_path = get_mxbi_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            MXBIModel(
                backup_source_root_id="original-source",
                backup_destination_root_id="original-destination",
            ).model_dump_json(indent=4),
            encoding="utf-8",
        )

        panel = MXBIPanel()
        self.assertEqual(panel.base_config.backup_source_root_id, "original-source")
        self.assertEqual(
            panel.base_config.backup_destination_root_id,
            "original-destination",
        )

        panel.base_config.input_backup_source_root_id.setText("updated-source")
        panel.base_config.input_backup_destination_root_id.setText(
            "updated-destination"
        )
        QTest.mouseClick(panel.save_button, Qt.MouseButton.LeftButton)

        saved = MXBIModel.model_validate_json(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved.backup_source_root_id, "updated-source")
        self.assertEqual(saved.backup_destination_root_id, "updated-destination")
        panel.close()

    def test_backup_root_ids_are_required(self) -> None:
        with self.assertRaises(ValidationError):
            MXBIModel.model_validate({})

    def test_legacy_mxbis_option_is_ignored_and_not_exported(self) -> None:
        database = MXBIDatabase.model_validate(
            {
                "mxbis": ["mxbi1"],
                "experimenter": ["tester"],
                "animals": {"abcd": "mouse"},
            }
        )

        exported = database.model_dump()
        self.assertNotIn("mxbis", exported)
        self.assertEqual(exported["experimenter"], ["tester"])
        self.assertEqual(exported["animals"], {"abcd": "mouse"})


if __name__ == "__main__":
    unittest.main()
