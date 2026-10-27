import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mxbiflow.core.path import (
    get_legacy_mxbi_config_path,
    get_mxbi_config_path,
    set_base_path,
)
from mxbiflow.infra.hardware_config import (
    HardwareConfigError,
    device_name,
    read_hardware_config,
    sync_hardware_config,
)

PRESET = {
    "screen_size": [1280, 800],
    "rewarders": [{"type": "rpi_gpio", "id": 0, "enabled": True, "pin": 13}],
    "detectors": [{"type": "mock", "id": 0, "enabled": True}],
}


def client(config: dict[str, object]) -> Mock:
    fake = Mock()
    fake.get_config.return_value = config
    return fake


def unreachable() -> Mock:
    fake = Mock()
    fake.get_config.side_effect = ConnectionError("refused")
    return fake


class HardwareConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self._temporary_directory.name)
        self._home_patch = patch.dict(os.environ, {"HOME": str(root / "home")})
        self._home_patch.start()
        set_base_path(root / "experiment")

    def tearDown(self) -> None:
        self._home_patch.stop()
        self._temporary_directory.cleanup()

    def write(self, path: Path, config: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config), encoding="utf-8")

    def test_cogmote_preset_replaces_the_cached_one(self) -> None:
        self.write(get_mxbi_config_path(), {"screen_size": [1024, 600]})

        sync_hardware_config(client({"hardware": PRESET}))

        config = read_hardware_config()
        self.assertEqual(config.screen_size, (1280, 800))
        self.assertEqual(config.rewarders[0].model_dump()["pin"], 13)

    def test_cache_is_used_without_a_preset_or_cogmote(self) -> None:
        self.write(get_mxbi_config_path(), PRESET)

        sync_hardware_config(client({"hardware": None}))
        self.assertEqual(read_hardware_config().screen_size, (1280, 800))
        sync_hardware_config(unreachable())
        self.assertEqual(read_hardware_config().screen_size, (1280, 800))

    def test_experiment_config_is_migrated_once(self) -> None:
        self.write(get_legacy_mxbi_config_path(), {"mxbi_id": "rig", **PRESET})

        sync_hardware_config(unreachable())
        self.assertEqual(read_hardware_config().screen_size, (1280, 800))

        self.write(get_legacy_mxbi_config_path(), {"screen_size": [800, 480]})
        sync_hardware_config(unreachable())
        self.assertEqual(read_hardware_config().screen_size, (1280, 800))

    def test_no_config_anywhere_is_an_error(self) -> None:
        sync_hardware_config(client({}))

        with self.assertRaisesRegex(HardwareConfigError, "hardware preset"):
            read_hardware_config()

    def test_invalid_preset_is_an_error(self) -> None:
        with self.assertRaisesRegex(HardwareConfigError, "invalid"):
            sync_hardware_config(client({"hardware": {"screen_size": "big"}}))

    def test_device_name_comes_from_cogmote(self) -> None:
        self.assertEqual(
            device_name(client({"device": {"code": "mxbi3", "name": "Rig 3"}})),
            "Rig 3",
        )
        with patch("mxbiflow.infra.hardware_config.socket.gethostname") as host:
            host.return_value = "raspberrypi"
            self.assertEqual(device_name(unreachable()), "raspberrypi")


if __name__ == "__main__":
    unittest.main()
