import unittest

from mxbiflow.assets import CLICKER_PATH
from mxbiflow.driver.audioplayer import AudioPlayer


class ClickerTest(unittest.TestCase):
    def test_bundled_clicker_loads(self) -> None:
        loaded = AudioPlayer().load_wav(CLICKER_PATH)

        self.assertEqual(loaded.sample_dtype, "int16")
        self.assertEqual(loaded.channels, 2)
        self.assertEqual(loaded.sample_rate, 44100)
        self.assertEqual(len(loaded.pcm_bytes), 22050 * 2 * 2)


if __name__ == "__main__":
    unittest.main()
