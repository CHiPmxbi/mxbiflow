import unittest

from mxbiflow.scene import Scene
from mxbiflow.scene.idle.idle import IDLE


class VocalizationDiscriminate(Scene):
    pass


class SceneTests(unittest.TestCase):
    def test_name_converts_class_name_to_snake_case(self) -> None:
        self.assertEqual(
            VocalizationDiscriminate.name(),
            "vocalization_discriminate",
        )

    def test_name_handles_uppercase_class_name(self) -> None:
        self.assertEqual(IDLE.name(), "idle")


if __name__ == "__main__":
    unittest.main()
