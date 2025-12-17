from enum import StrEnum, auto
from typing import TypeAlias

Feedback: TypeAlias = bool


class TaskEnum(StrEnum):
    IDEL = auto()
    ERROR = auto()
    HABITUATION = auto()
    GNGSiD_SIZE_REDUCTION_STAGE = auto()
    GNGSiD_DETECT_STAGE = auto()
    GNGSiD_DISCRIMINATE_STAGE = auto()
    TWOAC_SIZE_REDUCTION_STAGE = auto()
    CROSS_MODAL = auto()
