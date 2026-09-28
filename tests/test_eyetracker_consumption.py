# pyright: reportPrivateUsage=false

import unittest
from unittest.mock import Mock, patch

from pygame import Event, Surface

from mxbiflow.core import context as context_module
from mxbiflow.core.context import MXBIFlow
from mxbiflow.driver.eyetracker import EyeSample, MockEyetracker
from mxbiflow.driver.eyetracker.eyetracker import Eyetracker
from mxbiflow.driver.mxbi.mxbi import MXBI
from mxbiflow.models.session import Session
from mxbiflow.scene import Scene, SceneManager


def _context(eyetracker: Eyetracker | None = None) -> MXBIFlow:
    mxbi = MXBI((1024, 600), Mock(), Mock(), eyetracker)
    return MXBIFlow(Mock(spec=Session), mxbi)


class _RecordingScene(Scene):
    """Scene that records the gaze it sees in each frame."""

    def __init__(self) -> None:
        super().__init__()
        self._mxbiflow = context_module.get_mxbiflow()
        self.samples: list[EyeSample | None] = []

    def start(self) -> None:
        self._running = True

    def quit(self) -> None:
        self._running = False

    def handle_event(self, event: Event) -> None: ...

    def update(self, dt_s: float) -> None:
        self.samples.append(self._mxbiflow.eye_sample)

    def draw(self, screen: Surface) -> None: ...


class EyeSamplePropertyTests(unittest.TestCase):
    def test_returns_latest_sample_when_configured(self) -> None:
        eyetracker = MockEyetracker()
        eyetracker.set_sample(12.0, 34.0)
        context = _context(eyetracker)

        sample = context.eye_sample

        self.assertIsInstance(sample, EyeSample)
        assert isinstance(sample, EyeSample)
        self.assertEqual(sample.x, 12.0)
        self.assertEqual(sample.y, 34.0)

    def test_is_none_without_eyetracker(self) -> None:
        self.assertIsNone(_context().eye_sample)

    def test_is_none_when_no_usable_sample(self) -> None:
        self.assertIsNone(_context(MockEyetracker()).eye_sample)

    def test_is_none_when_sample_disappears(self) -> None:
        eyetracker = MockEyetracker()
        eyetracker.set_sample(1.0, 2.0)
        context = _context(eyetracker)

        eyetracker.clear()

        self.assertIsNone(context.eye_sample)


class SceneGazeConsumptionTests(unittest.TestCase):
    def test_scene_reads_gaze_per_frame(self) -> None:
        eyetracker = MockEyetracker()
        eyetracker.set_sample(5.0, 6.0)
        context = _context(eyetracker)
        manager = SceneManager()

        with patch.object(context_module, "_current_mxbiflow", context):
            manager.switch(_RecordingScene, defer=False)
            scene = manager.current
            assert isinstance(scene, _RecordingScene)

            manager.update(1 / 60)
            eyetracker.clear()
            manager.update(1 / 60)

        self.assertEqual(len(scene.samples), 2)
        first = scene.samples[0]
        self.assertIsInstance(first, EyeSample)
        assert isinstance(first, EyeSample)
        self.assertEqual((first.x, first.y), (5.0, 6.0))
        self.assertIsNone(scene.samples[1])


class FrameUpdateTests(unittest.TestCase):
    def test_context_update_does_not_sample_the_tracker(self) -> None:
        eyetracker = Mock()
        context = _context(eyetracker)

        context.update()

        eyetracker.sample.assert_not_called()


if __name__ == "__main__":
    unittest.main()
