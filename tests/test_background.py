import unittest

from mxbiflow.assets import create_background


class CreateBackgroundTests(unittest.TestCase):
    def test_default_colors_are_white_border_and_black_background(self) -> None:
        background = create_background((100, 100), border_width=10)

        self.assertEqual(background.get_at((0, 0))[:3], (255, 255, 255))
        self.assertEqual(background.get_at((50, 50))[:3], (0, 0, 0))

    def test_custom_border_and_background_colors(self) -> None:
        background = create_background(
            (100, 100),
            border_width=10,
            border_color=(1, 2, 3),
            background_color=(4, 5, 6),
        )

        self.assertEqual(background.get_at((0, 0))[:3], (1, 2, 3))
        self.assertEqual(background.get_at((50, 50))[:3], (4, 5, 6))


if __name__ == "__main__":
    unittest.main()
