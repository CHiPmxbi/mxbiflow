import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pydantic import ValidationError
from PySide6.QtWidgets import QApplication

from mxbiflow.core.path import set_base_path
from mxbiflow.gameloop.detector_bridge import DetectorBridge
from mxbiflow.infra.cogmote_config import read_experiment_config
from mxbiflow.models.animal import AnimalConfig
from mxbiflow.models.experiment import ExperimentConfig
from mxbiflow.models.session import SessionConfig
from mxbiflow.scene import SceneManager
from mxbiflow.ui.experiment_panel import ExperimentPanel

EXPERIMENT = {
    "animals": [
        {"id": "a1", "name": "Mira", "rfid_tags": ["t1", "t2"], "stage": "idle"},
        {"id": "b2", "name": "Kiwi", "rfid_tags": [], "stage": "idle"},
    ]
}


def client(config: dict[str, object]) -> Mock:
    fake = Mock()
    fake.get_config.return_value = config
    return fake


class ReadExperimentConfigTests(unittest.TestCase):
    def test_reads_the_experiment_from_the_device_config(self) -> None:
        experiment = read_experiment_config(
            client(
                {"device": {"code": "mxbi3", "name": "mxbi3"}, "experiment": EXPERIMENT}
            )
        )

        assert experiment is not None
        self.assertEqual(experiment.animals[0].rfid_tags, ("t1", "t2"))

    def test_none_without_an_experiment(self) -> None:
        self.assertIsNone(read_experiment_config(client({})))
        self.assertIsNone(read_experiment_config(client({"experiment": None})))

    def test_rejects_an_unreadable_experiment(self) -> None:
        with self.assertRaises(ValidationError):
            read_experiment_config(client({"experiment": {"animals": []}}))


class DetectorBridgeTagTests(unittest.TestCase):
    def test_manual_index_counts_animals_not_tags(self) -> None:
        detector = Mock()
        bridge = DetectorBridge(detector, {"t1": "Mira", "t2": "Mira", "t3": "Kiwi"})

        with patch.object(bridge, "manual_emit") as manual_emit:
            bridge.manual_emit_by_index(1)
            bridge.manual_emit_by_index(2)

        manual_emit.assert_called_once_with("t3")


class WizardAnimalsTests(unittest.TestCase):
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
        self._home_patch.stop()
        self._temporary_directory.cleanup()

    def test_animals_and_tags_come_from_the_cogmote_config(self) -> None:
        with patch(
            "mxbiflow.ui.experiment_panel.read_experiment_config",
            return_value=ExperimentConfig.model_validate(EXPERIMENT),
        ):
            panel = ExperimentPanel(SceneManager())
        stale = AnimalConfig(name="Mira", rfid_tags=("old",))
        panel.group_animals.load_config(SessionConfig(animals=(stale,)))

        animal = panel.group_animals.result()[-1]
        self.assertEqual(animal.name, "Mira")
        self.assertEqual(animal.rfid_tags, ("t1", "t2"))
        panel.close()

    def test_wizard_opens_without_cogmote(self) -> None:
        with patch(
            "mxbiflow.ui.experiment_panel.read_experiment_config",
            side_effect=ConnectionError("cogmoteGO is not running"),
        ):
            panel = ExperimentPanel(SceneManager())
        stale = AnimalConfig(name="Mira", rfid_tags=("old",))
        panel.group_animals.load_config(SessionConfig(animals=(stale,)))

        self.assertEqual(panel.group_animals.result()[-1].rfid_tags, ())
        panel.close()


if __name__ == "__main__":
    unittest.main()
