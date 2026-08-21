# pyright: reportPrivateUsage=false

import unittest
from unittest.mock import patch

from pydantic import TypeAdapter, ValidationError

from mxbiflow.driver.detector import (
    BeamBreakContinuousDetectorModel,
    DetectorModel,
    FusionContinuousDetectorModel,
    MockDetector,
    MockDetectorModel,
    RFIDContinuousDetectorModel,
)
from mxbiflow.driver.mxbi.factory import _make_detector


class DetectorModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = TypeAdapter(DetectorModel)

    def test_supported_detector_types_are_valid(self) -> None:
        cases = [
            ("mock", MockDetectorModel),
            ("rfid_continuous", RFIDContinuousDetectorModel),
            ("beambreak_continuous", BeamBreakContinuousDetectorModel),
            ("fusion_continuous", FusionContinuousDetectorModel),
        ]

        for detector_type, model_type in cases:
            with self.subTest(detector_type=detector_type):
                model = self.adapter.validate_python({"type": detector_type})
                self.assertIsInstance(model, model_type)

    def test_removed_standard_gate_type_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.adapter.validate_python({"type": "standard_gate"})

    def test_fusion_filter_defaults_and_validation(self) -> None:
        model = FusionContinuousDetectorModel()

        self.assertFalse(model.beam_break_filter_enabled)
        self.assertEqual(model.beam_break_filter_duration, 0.2)

        with self.assertRaises(ValidationError):
            FusionContinuousDetectorModel(beam_break_filter_duration=0)


class DetectorFactoryTests(unittest.TestCase):
    def test_builds_mock_detector(self) -> None:
        detector = _make_detector(MockDetectorModel())

        self.assertIsInstance(detector, MockDetector)

    @patch("mxbiflow.driver.mxbi.factory.RFIDContinuousDetector")
    @patch("mxbiflow.driver.mxbi.factory.DorsetLID665v42")
    def test_builds_rfid_detector(self, reader_type, detector_type) -> None:
        config = RFIDContinuousDetectorModel(port="/dev/rfid", baudrate=115200)

        result = _make_detector(config)

        reader_type.assert_called_once_with("/dev/rfid", 115200)
        detector_type.assert_called_once_with(reader_type.return_value)
        self.assertIs(result, detector_type.return_value)

    @patch("mxbiflow.driver.mxbi.factory.BeambreakContinuousDetector")
    @patch("mxbiflow.driver.mxbi.factory.RPIIRBreakBeamSensor")
    def test_builds_beambreak_detector(self, sensor_type, detector_type) -> None:
        config = BeamBreakContinuousDetectorModel(pin=17)

        result = _make_detector(config)

        sensor_type.assert_called_once_with(17)
        detector_type.assert_called_once_with(sensor_type.return_value)
        self.assertIs(result, detector_type.return_value)

    @patch("mxbiflow.driver.mxbi.factory.FusionContinuousDetector")
    @patch("mxbiflow.driver.mxbi.factory.RPIIRBreakBeamSensor")
    @patch("mxbiflow.driver.mxbi.factory.DorsetLID665v42")
    def test_builds_fusion_detector(
        self,
        reader_type,
        sensor_type,
        detector_type,
    ) -> None:
        config = FusionContinuousDetectorModel(
            port="/dev/rfid",
            baudrate=115200,
            pin=17,
            poll_interval=0.5,
            rfid_timeout=0.1,
            beam_break_filter_enabled=True,
            beam_break_filter_duration=0.3,
        )

        result = _make_detector(config)

        reader_type.assert_called_once_with("/dev/rfid", 115200)
        sensor_type.assert_called_once_with(17)
        detector_type.assert_called_once_with(
            reader_type.return_value,
            sensor_type.return_value,
            poll_interval=0.5,
            rfid_timeout=0.1,
            beam_break_filter_enabled=True,
            beam_break_filter_duration=0.3,
        )
        self.assertIs(result, detector_type.return_value)


if __name__ == "__main__":
    unittest.main()
