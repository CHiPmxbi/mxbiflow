import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from pygame import Event, Surface
from PySide6.QtWidgets import QApplication

from mxbiflow import core, run
from mxbiflow.core.config_store import ConfigStore
from mxbiflow.core.context import get_mxbiflow
from mxbiflow.core.offline import set_offline
from mxbiflow.core.path import (
    get_config_session_path,
    get_data_dir_path,
    get_database_path,
    get_mxbi_config_path,
    get_mxbi_panel_config_path,
    get_offline_mxbi_config_path,
    set_base_path,
)
from mxbiflow.infra.data_logger import DataLogger
from mxbiflow.models.animal import AnimalConfig
from mxbiflow.models.session import SessionConfig
from mxbiflow.scene import SceneManager
from mxbiflow.scene.idle.idle import IDLE
from mxbiflow.scene.scene import Scene
from mxbiflow.ui.experiment_panel import ExperimentPanel
from mxbiflow.ui.mxbi_panel import MXBIPanel
from mxbiflow.ui.wizard import run_wizard

MIRA = AnimalConfig(cogmatrix_id="a1", name="Mira", rfid_tags=("t1",), stage="train")
SESSION = SessionConfig(unknown_animal_as="Mira", animals=(MIRA,))
HARDWARE: dict[str, Any] = {
    "screen_size": [320, 240],
    "rewarders": [{"type": "mock", "enabled": True}],
    "detectors": [{"type": "mock", "enabled": True}],
}


class TemporaryHome(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        home = patch.dict(os.environ, {"HOME": directory.name})
        home.start()
        self.addCleanup(home.stop)
        set_base_path(Path(directory.name) / "experiment")
        self.addCleanup(set_offline, False)

    @staticmethod
    def write(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


class Idle(IDLE):
    """Sends the first animal to the device once; no assets, no MXBIFlow lookups."""

    def __init__(self) -> None:
        Scene.__init__(self)
        self._frames = 0

    def start(self) -> None:
        self._running = True

    def quit(self) -> None:
        self._running = False

    def handle_event(self, event: Event) -> None:
        pass

    def update(self, dt_s: float) -> None:
        self._frames += 1
        if self._frames > 1000:
            raise TimeoutError("the animal never reached its task")
        if self._frames == 1:
            pygame.event.post(Event(pygame.KEYDOWN, key=pygame.K_0, mod=0, unicode="0"))

    def draw(self, screen: Surface) -> None:
        pass


class Train(Scene):
    """One trial: writes a record, publishes it and ends the run."""

    level_table = {"default": [0]}

    def start(self) -> None:
        self._running = True
        self._trial_done = False

    def quit(self) -> None:
        self._running = False

    def handle_event(self, event: Event) -> None:
        pass

    def update(self, dt_s: float) -> None:
        if self._trial_done:
            return
        self._trial_done = True
        flow = get_mxbiflow()
        animal = flow.session.require_current_animal()
        DataLogger(flow.session, animal=animal.name, stage="train").save({"trial": 1})
        flow.session.add_trial()
        flow.publish_trial({"trial": 1}, correct=True)
        pygame.event.post(Event(pygame.QUIT))

    def draw(self, screen: Surface) -> None:
        pass


class OfflineRunTests(TemporaryHome):
    def test_a_session_completes_without_any_request(self) -> None:
        self.write(get_offline_mxbi_config_path(), HARDWARE)
        self.write(get_config_session_path(), SESSION.model_dump(mode="json"))
        manager = SceneManager()
        manager.register({"idle": Idle, "train": Train})
        manager.default_scene = "idle"

        def wizard(_manager: SceneManager) -> bool:
            set_offline(True)
            return True

        connections: list[object] = []

        def refuse(_socket: socket.socket, address: object) -> None:
            connections.append(address)
            raise OSError("offline runs make no request")

        show_run_end = run.show_run_end
        summaries: list[Any] = []

        def show(summary: Any, steps: run.RunEnd, work: Any, **kwargs: Any) -> None:
            summaries.append(summary)
            show_run_end(summary, steps, work, **{**kwargs, "hold_s": 0.0})

        recorder = Mock()
        with (
            patch.object(run, "run_wizard", wizard),
            patch.object(run, "show_run_end", show),
            patch.object(socket.socket, "connect", refuse),
            patch.object(socket.socket, "connect_ex", refuse),
            patch.object(core.context, "_current_mxbiflow", None),
        ):
            run.run_experiment(manager, argv=[], recorder=recorder)

        self.assertEqual(connections, [])
        recorder.start.assert_not_called()
        recorder.retry_pending.assert_not_called()
        self.assertEqual(
            [
                json.loads(line)["trial"]
                for result in get_data_dir_path().rglob("result.jsonl")
                for line in result.read_text().splitlines()
            ],
            [1],
        )
        self.assertEqual(summaries[0].animals[0].trials, 1)

    def test_a_crash_is_raised_without_a_notification(self) -> None:
        def wizard(_manager: SceneManager) -> bool:
            set_offline(True)
            return True

        with (
            patch.object(run, "run_wizard", wizard),
            patch.object(run, "init_gameloop", side_effect=ValueError("boom")),
            patch.object(run, "send_crash_report") as send_crash_report,
            self.assertRaisesRegex(ValueError, "boom"),
        ):
            run.run_experiment(SceneManager(), argv=[], recorder=Mock())

        send_crash_report.assert_not_called()

    def test_the_wizard_makes_no_request_when_offline_is_remembered(self) -> None:
        self.write(get_mxbi_panel_config_path(), {"offline": True})
        with (
            patch("mxbiflow.ui.wizard.require_application"),
            patch("mxbiflow.ui.wizard.sync_hardware_config") as sync,
            patch("mxbiflow.ui.wizard.MXBIPanel") as panel,
        ):
            panel.return_value.exec.return_value = 0
            run_wizard(Mock())

        sync.assert_not_called()


class Panels(TemporaryHome):
    application: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        application = QApplication.instance()
        cls.application = (
            application if isinstance(application, QApplication) else QApplication([])
        )

    def tearDown(self) -> None:
        self.application.processEvents()


class HardwareToggleTests(Panels):
    def setUp(self) -> None:
        super().setUp()
        self.write(get_mxbi_config_path(), {**HARDWARE, "screen_size": [800, 480]})
        self.write(get_offline_mxbi_config_path(), HARDWARE)

    def files(self) -> tuple[str, str]:
        return (
            get_mxbi_config_path().read_text(encoding="utf-8"),
            get_offline_mxbi_config_path().read_text(encoding="utf-8"),
        )

    def test_toggling_reloads_the_panel_and_touches_neither_file(self) -> None:
        before = self.files()
        panel = MXBIPanel()
        rewarders = len(panel.rewarders_group.cards)

        for offline in (True, False, True):
            panel.base_config.check_offline.setChecked(offline)
            self.assertEqual(len(panel.rewarders_group.cards), rewarders)

        self.assertEqual(self.files(), before)
        panel.close()

    def test_toggling_creates_no_missing_file(self) -> None:
        get_offline_mxbi_config_path().unlink()
        panel = MXBIPanel()

        panel.base_config.check_offline.setChecked(True)

        self.assertFalse(get_offline_mxbi_config_path().exists())
        panel.close()

    def test_save_writes_only_the_chosen_mode_and_remembers_it(self) -> None:
        online, _ = self.files()
        panel = MXBIPanel()
        panel.base_config.check_offline.setChecked(True)

        panel.save_button.click()

        self.assertEqual(self.files()[0], online)
        self.assertTrue(
            json.loads(get_mxbi_panel_config_path().read_text(encoding="utf-8"))[
                "offline"
            ]
        )
        reopened = MXBIPanel()
        self.assertTrue(reopened.offline)
        panel.close()
        reopened.close()


class SessionLoadingTests(Panels):
    def setUp(self) -> None:
        super().setUp()
        self.write(get_config_session_path(), SESSION.model_dump(mode="json"))

    def saved(self) -> SessionConfig:
        return ConfigStore(get_config_session_path(), SessionConfig).value

    def assert_survives_continue(self, panel: ExperimentPanel) -> None:
        panel.button_continue.click()
        [animal] = self.saved().animals
        self.assertEqual(animal.name, "Mira")
        self.assertEqual(animal.rfid_tags, ("t1",))
        self.assertEqual(self.saved().unknown_animal_as, "Mira")
        panel.close()

    def test_offline_animals_come_from_the_database_with_every_tag(self) -> None:
        set_offline(True)
        self.write(
            get_database_path(),
            {
                "experimenter": ["me"],
                "animals": {"t1": "Mira", "t2": "Kiwi", "t3": "Kiwi"},
            },
        )
        with patch("mxbiflow.ui.experiment_panel.read_experiment_config") as read:
            panel = ExperimentPanel(SceneManager())
        read.assert_not_called()

        combo = panel.group_scene.combo_unknown_animal_as
        self.assertEqual(
            [combo.itemText(i) for i in range(combo.count())], ["Mira", "Kiwi"]
        )
        self.assert_survives_continue(panel)

    def test_offline_a_saved_animal_missing_from_the_database_survives(self) -> None:
        set_offline(True)
        self.assert_survives_continue(ExperimentPanel(SceneManager()))

    def test_online_names_and_tags_survive_continue(self) -> None:
        experiment = Mock(subjects=(Mock(id="a1", rfid_tags=("t1",)),))
        experiment.subjects[0].name = "Mira"
        with patch(
            "mxbiflow.ui.experiment_panel.read_experiment_config",
            return_value=experiment,
        ):
            panel = ExperimentPanel(SceneManager())
        self.assert_survives_continue(panel)

    def test_online_without_animals_refuses_and_points_at_the_checkbox(self) -> None:
        before = get_config_session_path().read_text(encoding="utf-8")
        with patch(
            "mxbiflow.ui.experiment_panel.read_experiment_config",
            side_effect=ConnectionError("cogmoteGO is not running"),
        ):
            panel = ExperimentPanel(SceneManager())

        panel.button_continue.click()

        self.assertIn("Offline", panel.label_error.text())
        self.assertEqual(panel.result(), 0)
        self.assertEqual(get_config_session_path().read_text(encoding="utf-8"), before)
        panel.close()

    def test_an_animal_card_without_an_animal_is_refused(self) -> None:
        set_offline(True)
        get_config_session_path().unlink()
        panel = ExperimentPanel(SceneManager())
        panel.group_animals._on_add_animal()  # pyright: ignore[reportPrivateUsage]

        panel.button_continue.click()

        self.assertEqual(panel.result(), 0)
        self.assertFalse(get_config_session_path().exists())
        self.assertTrue(panel.label_error.text())
        panel.close()


if __name__ == "__main__":
    unittest.main()
