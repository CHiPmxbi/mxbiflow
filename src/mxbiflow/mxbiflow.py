from .models.session import Session
from .timer import FrameTimer
from pymxbi import MXBI


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

    def update(self) -> None:
        self._timer.update()


_current_mxbiflow: MXBIFlow | None = None


def get_mxbiflow() -> MXBIFlow:
    global _current_mxbiflow
    if _current_mxbiflow is None:
        raise RuntimeError("MXBIFlow not initialized")
    return _current_mxbiflow


def set_mxbiflow(mxbiflow: MXBIFlow) -> None:
    global _current_mxbiflow
    if _current_mxbiflow is not None:
        raise RuntimeError("MXBIFlow already initialized")
    _current_mxbiflow = mxbiflow
