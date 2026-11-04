import unittest
from unittest.mock import patch

from mxbiflow.driver.detector.cli_test import prompt_detector_config
from mxbiflow.driver.peripheral.beam_break_sensor.cli_test import prompt_sensor_config


class HardwarePromptTests(unittest.TestCase):
    def test_detector_prompts_default(self) -> None:
        with patch("builtins.input", return_value=""):
            self.assertEqual(
                prompt_detector_config(), ("/dev/ttyUSB0", 9600, 17, 0.05, 10.0)
            )

    def test_detector_rejects_a_bad_baudrate(self) -> None:
        with (
            patch("builtins.input", side_effect=["/dev/ttyUSB1", "0"]),
            self.assertRaisesRegex(SystemExit, "baudrate must be > 0"),
        ):
            prompt_detector_config()

    def test_sensor_prompts_default(self) -> None:
        with patch("builtins.input", return_value=""):
            self.assertEqual(prompt_sensor_config(), (17, 0.05, True))

    def test_sensor_answers(self) -> None:
        with patch("builtins.input", side_effect=["4", "0.1", "n"]):
            self.assertEqual(prompt_sensor_config(), (4, 0.1, False))


if __name__ == "__main__":
    unittest.main()
