from typing import TYPE_CHECKING

from mxbi.detector.detector import Detector
from mxbi.detector.dorset_lid665v42_detector_legacy import DorsetLID665v42DetectorLegacy
from mxbi.detector.mock_detector import MockDetector
from mxbi.models.detector import DetectorEnum

if TYPE_CHECKING:
    from mxbi.theater import Theater


class DetectorFactory:
    """Factory responsible for creating detector instances."""

    detectors: dict[DetectorEnum, type[Detector]] = {
        DetectorEnum.MOCK: MockDetector,
        DetectorEnum.DORSET_LID665V42: DorsetLID665v42DetectorLegacy,
    }

    @classmethod
    def create(
        cls, detector_type: DetectorEnum, theater: "Theater", baudrate: int, port: str
    ) -> Detector:
        detector_cls = cls.detectors[detector_type]
        return detector_cls(theater, port, baudrate)
