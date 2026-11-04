import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mxbiflow.core.offline import set_offline
from mxbiflow.core.path import (
    get_mxbi_config_path,
    get_offline_mxbi_config_path,
    set_base_path,
)
from mxbiflow.driver import MXBIModel, build_mxbi
from mxbiflow.driver.audioplayer import AudioPlayer, PlayStatus, PureToneUnit
from mxbiflow.infra.hardware_config import (
    HardwareConfigError,
    read_hardware_config,
    sync_hardware_config,
)
from mxbiflow.models.experiment import inlined_json_schema
from mxbiflow.ui.mxbi_panel import MXBIPanel

DEVICES = {
    "rewarders": [{"type": "mock", "enabled": True}],
    "detectors": [{"type": "mock", "enabled": True}],
}
PRESET = {**DEVICES, "frequency_response_table": {"1000": 60, "2000": 40}}
FILE_PATH = (
    "mxbiflow.driver.audioplayer.frequency_response_table."
    "frequency_response_table.FREQUENCY_RESPONSE_TABLE"
)


class PresetTableTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        home = patch.dict(os.environ, {"HOME": str(self.root / "home")})
        home.start()
        self.addCleanup(home.stop)
        set_base_path(self.root / "experiment")
        self.addCleanup(set_offline, False)
        table_file = patch(FILE_PATH, self.root / "table.json")
        table_file.start()
        self.addCleanup(table_file.stop)

    @staticmethod
    def write(path: Path, config: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config), encoding="utf-8")

    def test_the_preset_table_reaches_the_next_run(self) -> None:
        client = Mock()
        client.get_config.return_value = {"hardware": PRESET}

        sync_hardware_config(client)
        table = build_mxbi(read_hardware_config()).aplayer.frequency_response_table

        assert table is not None
        self.assertEqual(table.root, {1000: 60, 2000: 40})
        self.assertEqual(table.get_volume_by_freq(1000), 60)
        self.assertEqual(table.get_volume_by_freq(1900), 40)

    def test_online_ignores_the_file(self) -> None:
        self.write(self.root / "table.json", {"500": 10})
        self.write(get_mxbi_config_path(), PRESET)

        self.assertEqual(
            read_hardware_config().frequency_response_table, {1000: 60, 2000: 40}
        )

    def test_offline_the_file_replaces_the_table(self) -> None:
        set_offline(True)
        self.write(self.root / "table.json", {"500": 10})
        self.write(get_offline_mxbi_config_path(), PRESET)

        self.assertEqual(read_hardware_config().frequency_response_table, {500: 10})

    def test_offline_without_the_file_there_is_no_table(self) -> None:
        set_offline(True)
        self.write(get_offline_mxbi_config_path(), PRESET)

        config = read_hardware_config()

        self.assertIsNone(build_mxbi(config).aplayer.frequency_response_table)

    def test_offline_an_invalid_file_refuses_to_start(self) -> None:
        set_offline(True)
        self.write(self.root / "table.json", {"500": "loud"})
        self.write(get_offline_mxbi_config_path(), PRESET)

        with self.assertRaisesRegex(HardwareConfigError, "frequency response table"):
            read_hardware_config()

    def test_the_wizard_panel_keeps_the_table(self) -> None:
        application = QApplication.instance() or QApplication([])
        self.write(get_mxbi_config_path(), PRESET)
        panel = MXBIPanel()

        panel.save_button.click()

        self.assertEqual(
            read_hardware_config().frequency_response_table, {1000: 60, 2000: 40}
        )
        panel.close()
        application.processEvents()

    def test_the_schema_describes_a_table_for_the_form(self) -> None:
        field = inlined_json_schema(MXBIModel)["properties"]["frequency_response_table"]

        self.assertEqual(field["title"], "Frequency response table")
        self.assertEqual(field["additionalProperties"]["maximum"], 100)
        self.assertEqual(
            field["x-mxbi-columns"], ["Frequency (Hz)", "Master volume (%)"]
        )

    def test_a_volume_out_of_range_is_invalid(self) -> None:
        with self.assertRaises(ValueError):
            MXBIModel.model_validate({"frequency_response_table": {"1000": 101}})


class NoTableTests(unittest.TestCase):
    """What playback does without a table, and has to keep doing."""

    def test_an_empty_table_is_no_table(self) -> None:
        config = MXBIModel.model_validate(DEVICES)

        self.assertIsNone(build_mxbi(config).aplayer.frequency_response_table)

    def test_a_tone_plays_at_the_volume_of_its_unit(self) -> None:
        player = AudioPlayer()
        tone = np.full(4, 1000, dtype=np.int16)
        played: list[bytes] = []

        def play(_task: object, pcm: bytes, **_kwargs: object) -> PlayStatus:
            played.append(pcm)
            return PlayStatus.FINISHED

        unit = PureToneUnit(frequency_hz=1000, duration_ms=1, stimulus=tone)
        with patch.object(player, "_play_pcm_bytes_with_callback", play):
            task = player.play_puretone_sequence([unit])
            for _ in range(200):
                player.update()
                if task.done():
                    break
                time.sleep(0.01)

        self.assertTrue(task.done())
        self.assertEqual(played, [tone.tobytes()])


if __name__ == "__main__":
    unittest.main()
