import unittest

from mxbiflow.assets import CLICKER_PATH
from mxbiflow.driver.audioplayer import AudioFormat, read_sound


class ClickerTest(unittest.TestCase):
    def test_bundled_clicker_loads(self) -> None:
        sound = read_sound(CLICKER_PATH)

        self.assertEqual(sound.format, AudioFormat(sample_rate_hz=44100, channels=2))
        self.assertEqual(sound.frames, 22050)
        self.assertEqual(sound.duration_ms, 500)


if __name__ == "__main__":
    unittest.main()
