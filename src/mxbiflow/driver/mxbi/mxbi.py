from collections.abc import Mapping
from typing import Any

from ..audioplayer import AudioPlayer
from ..detector.detector import Detector
from ..eyetracker.eyetracker import Eyetracker
from ..rewarder.rewarder import Rewarder
from ..screen import Screen


class MXBI:
    def __init__(
        self,
        screen_size: Screen | tuple[int, int],
        rewarder: Rewarder | dict[int, Rewarder],
        detector: Detector | dict[int, Detector],
        eyetracker: Eyetracker | dict[int, Eyetracker] | None = None,
    ):
        if not isinstance(screen_size, Screen):
            screen_size = Screen(width=screen_size[0], height=screen_size[1])
        self._screen_size = screen_size
        self._rewarder: dict[int, Rewarder] = self._normalize(rewarder, "rewarder")
        self._detector: dict[int, Detector] = self._normalize(detector, "detector")
        self._eyetracker: dict[int, Eyetracker] = self._normalize_optional(
            eyetracker, "eyetracker"
        )
        self._aplayer = AudioPlayer()

    @staticmethod
    def _normalize(obj, name: str) -> dict[int, Any]:
        if isinstance(obj, Mapping):
            if not obj:
                raise ValueError(f"{name} mapping cannot be empty")
            return dict(obj)
        return {0: obj}

    @staticmethod
    def _normalize_optional(obj, name: str) -> dict[int, Any]:
        """Normalize an optional device, where ``None``/empty means absent."""
        if obj is None:
            return {}
        if isinstance(obj, Mapping) and not obj:
            return {}
        return MXBI._normalize(obj, name)

    @property
    def rewarder(self) -> Rewarder:
        rewarder = self._rewarder.get(0)
        if rewarder is None:
            raise RuntimeError("No rewarder with id 0 found")
        return rewarder

    def get_rewarder(self, rewarder_id: int) -> Rewarder:
        rewarder = self._rewarder.get(rewarder_id)
        if rewarder is None:
            raise RuntimeError(f"No rewarder with id {rewarder_id} found")
        return rewarder

    @property
    def detector(self) -> Detector:
        detector = self._detector.get(0)
        if detector is None:
            raise RuntimeError("No detector with id 0 found")
        return detector

    def get_detector(self, detector_id: int) -> Detector:
        detector = self._detector.get(detector_id)
        if detector is None:
            raise RuntimeError(f"No detector with id {detector_id} found")
        return detector

    @property
    def eyetracker(self) -> Eyetracker | None:
        """Return the eyetracker with id 0, or ``None`` when not configured."""
        return self._eyetracker.get(0)

    def get_eyetracker(self, eyetracker_id: int) -> Eyetracker:
        eyetracker = self._eyetracker.get(eyetracker_id)
        if eyetracker is None:
            raise RuntimeError(f"No eyetracker with id {eyetracker_id} found")
        return eyetracker

    def begin(self) -> None:
        """Start all detectors and eyetrackers, and open all rewarders."""
        for rewarder in self._rewarder.values():
            rewarder.open()
        for detector in self._detector.values():
            detector.begin()
        for eyetracker in self._eyetracker.values():
            eyetracker.begin()

    def quit(self) -> None:
        """Stop all eyetrackers and detectors, and close all rewarders."""
        for eyetracker in self._eyetracker.values():
            eyetracker.quit()
        for detector in self._detector.values():
            detector.quit()
        for rewarder in self._rewarder.values():
            rewarder.close()

    @property
    def screen_size(self):
        return self._screen_size

    @property
    def aplayer(self) -> AudioPlayer:
        return self._aplayer
