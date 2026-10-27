import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pydantic import ValidationError
from PySide6.QtWidgets import QApplication

from mxbiflow.core.path import (
    get_applied_cogmote_config_path,
    get_config_session_path,
    set_base_path,
)
from mxbiflow.gameloop.detector_bridge import DetectorBridge
from mxbiflow.infra.cogmote_config import (
    CogmoteConfigError,
    apply_cogmote_config,
    read_experiment_config,
    session_config_from_experiment,
)
from mxbiflow.models.animal import AnimalConfig
from mxbiflow.models.experiment import ExperimentConfig, RecordingConfig
from mxbiflow.models.session import SessionConfig
from mxbiflow.scene import SceneManager
from mxbiflow.ui.experiment_panel import ExperimentPanel

EXPERIMENT = {
    "protocol": {"id": "p1"},
    "repository": {"id": "r1"},
    "animals": [
        {"id": "a1", "name": "Mira", "rfid_tags": ["t1", "t2"], "stage": "idle"},
        {"id": "b2", "name": "Kiwi", "rfid_tags": [], "stage": "idle"},
    ],
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
            read_experiment_config(
                client({"experiment": {**EXPERIMENT, "animals": []}})
            )


def experiment(stage: str = "detect", level: int = 1) -> ExperimentConfig:
    return ExperimentConfig.model_validate(
        {
            "protocol": {"id": "p1"},
            "repository": {"id": "r1"},
            "animals": [
                {
                    "id": "a1",
                    "name": "Mira",
                    "rfid_tags": ["t1"],
                    "stage": stage,
                    "level": level,
                }
            ],
            "parameters": {"reward_type": "m_juice", "fullscreen": False},
        }
    )


class SessionConfigFromExperimentTests(unittest.TestCase):
    stages = ("idle", "detect", "discriminate")

    def test_maps_animals_and_parameters(self) -> None:
        config = session_config_from_experiment(experiment(), stages=self.stages)

        [animal] = config.animals
        self.assertEqual(
            (
                animal.cogmatrix_id,
                animal.name,
                animal.rfid_tags,
                animal.stage,
                animal.level,
            ),
            ("a1", "Mira", ("t1",), "detect", 1),
        )
        self.assertEqual(config.reward_type, "m_juice")
        self.assertFalse(config.fullscreen)
        self.assertFalse(config.record_camera)

    def test_maps_the_recording_switch(self) -> None:
        recorded = experiment().model_copy(
            update={
                "recording": RecordingConfig(record_camera=True, capture_latency_ms=40)
            }
        )

        config = session_config_from_experiment(recorded, stages=self.stages)

        self.assertTrue(config.record_camera)
        self.assertEqual(config.capture_latency_ms, 40)
        self.assertTrue(config.with_animals(()).record_camera)

    def test_unknown_stages_are_rejected(self) -> None:
        with self.assertRaisesRegex(CogmoteConfigError, "unknown stages typo"):
            session_config_from_experiment(experiment("typo"), stages=self.stages)
        bad_scene = experiment().model_copy(
            update={
                "parameters": experiment().parameters.model_copy(
                    update={"default_scene": "nope"}
                )
            }
        )
        with self.assertRaisesRegex(CogmoteConfigError, "nope"):
            session_config_from_experiment(bad_scene, stages=self.stages)
        bad_config = experiment().model_copy(update={"stages": {"gone": {}}})
        with self.assertRaisesRegex(CogmoteConfigError, "gone"):
            session_config_from_experiment(bad_config, stages=self.stages)

    def test_maps_the_stage_configurations(self) -> None:
        document = {"default": {"levels": {}}, "Mira": {"reward_ms": 5}}
        configured = experiment().model_copy(update={"stages": {"detect": document}})

        config = session_config_from_experiment(configured, stages=self.stages)

        self.assertEqual(config.stage_configs, {"detect": document})
        self.assertEqual(config.with_animals(()).stage_configs, {"detect": document})
        self.assertEqual(
            session_config_from_experiment(
                experiment(), stages=self.stages
            ).stage_configs,
            {},
        )

    def test_local_progress_survives_until_the_operator_changes_it(self) -> None:
        progressed = SessionConfig(
            animals=(
                AnimalConfig(
                    cogmatrix_id="a1", name="Mira", stage="discriminate", level=4
                ),
            )
        )

        kept = session_config_from_experiment(
            experiment(), stages=self.stages, previous=progressed, applied=experiment()
        )
        changed = session_config_from_experiment(
            experiment(level=2),
            stages=self.stages,
            previous=progressed,
            applied=experiment(),
        )
        first = session_config_from_experiment(
            experiment(), stages=self.stages, previous=progressed
        )

        self.assertEqual(
            (kept.animals[0].stage, kept.animals[0].level), ("discriminate", 4)
        )
        self.assertEqual(
            (changed.animals[0].stage, changed.animals[0].level), ("detect", 2)
        )
        self.assertEqual(
            (first.animals[0].stage, first.animals[0].level), ("detect", 1)
        )


class ApplyCogmoteConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        set_base_path(Path(self._temporary_directory.name))

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_writes_the_session_config_and_remembers_the_applied_one(self) -> None:
        fake = client({"experiment": experiment().model_dump(mode="json")})

        apply_cogmote_config(("idle", "detect"), fake)

        saved = SessionConfig.model_validate_json(
            get_config_session_path().read_text(encoding="utf-8")
        )
        self.assertEqual(saved.animals[0].rfid_tags, ("t1",))
        self.assertTrue(get_applied_cogmote_config_path().is_file())

    def test_missing_or_unreachable_config_is_an_error(self) -> None:
        with self.assertRaisesRegex(CogmoteConfigError, "no experiment"):
            apply_cogmote_config(("idle",), client({}))
        broken = Mock()
        broken.get_config.side_effect = ConnectionError("refused")
        with self.assertRaisesRegex(CogmoteConfigError, "refused"):
            apply_cogmote_config(("idle",), broken)


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
