from .detector import Detector, DetectorEnum
from .mock_detector import MockDetector
from .standard_gate_detector import StandardGateDetector
from .rfid_continuous_detector import RFIDContinuousDetector
from .beambreak_continuous_detector import BeambreakContinuousDetector
from .fusion_continuous_detector import FusionContinuousDetector

detectors: dict[str, type[Detector]] = {
    DetectorEnum.MOCK: MockDetector,
    DetectorEnum.STANDARD_GATE: StandardGateDetector,
    DetectorEnum.RFID_CONTINUOUS: RFIDContinuousDetector,
    DetectorEnum.BEAMBREAK_CONTINUOUS: BeambreakContinuousDetector,
    DetectorEnum.FUSION_CONTINUOUS: FusionContinuousDetector,
}


__all__ = [
    "Detector",
    "MockDetector",
    "StandardGateDetector",
    "RFIDContinuousDetector",
    "BeambreakContinuousDetector",
    "FusionContinuousDetector",
    "DetectorEnum",
    "detectors"
]
