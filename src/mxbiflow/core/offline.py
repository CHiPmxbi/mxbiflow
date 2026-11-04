"""Offline mode: the wizard's choice to run without cogmoteGO, cogmote or CogMatrix.

It starts off and only the wizard sets it, so ``--from-cogmote`` never runs offline.
"""

_offline = False


def set_offline(offline: bool) -> None:
    global _offline
    _offline = offline


def is_offline() -> bool:
    return _offline
