from .mxbi import MXBI

_current_mxbi: MXBI | None = None


def get_mxbi() -> MXBI:
    global _current_mxbi
    if _current_mxbi is None:
        raise RuntimeError("MXBI not initialized")
    return _current_mxbi


def set_mxbi(mxbi: MXBI) -> None:
    global _current_mxbi
    if _current_mxbi is not None:
        raise RuntimeError("MXBI already initialized")
    _current_mxbi = mxbi
