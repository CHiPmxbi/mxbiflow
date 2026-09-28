from pathlib import Path

from mxbiflow.driver import MXBI
from mxbiflow.driver.eyetracker.eyetracker import EyeSample

from ..infra.timer import FrameTimer
from ..models.session import Session
from .path import get_data_dir_path


class MXBIFlow:
    def __init__(self, session: Session, mxbi: MXBI) -> None:
        self._session = session
        self._timer = FrameTimer()
        self._mxbi = mxbi

    @property
    def session(self) -> Session:
        return self._session

    @property
    def timer(self) -> FrameTimer:
        return self._timer

    @property
    def mxbi(self) -> MXBI:
        return self._mxbi

    @property
    def eye_sample(self) -> EyeSample | None:
        """Return the eye-tracking sample available for this frame.

        ``None`` when no eyetracker is configured, or when no usable sample is
        available: none measured yet, aged out, or the sample stream stopped.

        Scenes read this from ``update(dt_s)``, so gaze is consumed once per
        frame without blocking the game loop. See ``docs/eyetracking.md``.
        """
        eyetracker = self._mxbi.eyetracker
        return None if eyetracker is None else eyetracker.sample()

    @property
    def data_dir(self) -> Path:
        return get_data_dir_path()

    def update(self) -> None:
        self._timer.update()


_current_mxbiflow: MXBIFlow | None = None


def get_mxbiflow() -> MXBIFlow:
    if _current_mxbiflow is None:
        raise RuntimeError("MXBIFlow not initialized")
    return _current_mxbiflow


def set_mxbiflow(mxbiflow: MXBIFlow) -> None:
    global _current_mxbiflow
    if _current_mxbiflow is not None:
        raise RuntimeError("MXBIFlow already initialized")
    _current_mxbiflow = mxbiflow
