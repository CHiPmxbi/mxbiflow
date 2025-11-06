from typing import TYPE_CHECKING, Union

from mxbi.detector.dorset_lid665v42_detector import DorsetLID665v42Detector
from mxbi.detector.mock_detector import MockDetector
from dataclasses import dataclass

if TYPE_CHECKING:
    from mxbi.theater import Theater
    from mxbi.detector.detector import Detector


@dataclass
class DorsetLID665v42Config:
    baudrate: int
    port: str
    interval: int


DetectorConfig = Union[DorsetLID665v42Config, None]


class DetectorFactory:
    """Factory responsible for creating detector instances."""

    @classmethod
    def create(cls, config: DetectorConfig, theater: "Theater") -> "Detector":
        match config:
            case DorsetLID665v42Config():
                return DorsetLID665v42Detector(
                    theater=theater,
                    port=config.port,
                    baudrate=config.baudrate,
                    detection_interval=config.interval,
                )
            case None:
                return MockDetector(theater=theater)
            case _:
                raise ValueError(f"Unknown detector config type: {type(config)}")
