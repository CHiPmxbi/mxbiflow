# pyright: reportPrivateUsage=false

import logging
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
from mxbiflow.driver.eyetracker import (
    EyetrackerEnum,
    EyetrackerModel,
    MockEyetracker,
    MockEyetrackerModel,
    MxEyeEyetrackerModel,
)
from mxbiflow.driver.mxbi.factory import (
    MXBIModel,
    _make_detector,
    _make_eyetracker,
    build_mxbi,
)
from mxbiflow.driver.rewarder import MockRewarderModel


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

        self.assertEqual(model.poll_interval, 0.05)
        self.assertEqual(model.rfid_timeout, 10.0)
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


class EyetrackerModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = TypeAdapter(EyetrackerModel)

    def test_supported_eyetracker_types_are_valid(self) -> None:
        cases = [
            ("mx_eye", MxEyeEyetrackerModel),
            ("mock", MockEyetrackerModel),
        ]

        for eyetracker_type, model_type in cases:
            with self.subTest(eyetracker_type=eyetracker_type):
                model = self.adapter.validate_python({"type": eyetracker_type})
                self.assertIsInstance(model, model_type)

    def test_unknown_eyetracker_type_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.adapter.validate_python({"type": "tobii"})

    def test_mx_eye_defaults(self) -> None:
        model = MxEyeEyetrackerModel()

        self.assertFalse(model.enabled)
        self.assertEqual(model.id, 0)
        self.assertEqual(model.host, "127.0.0.1")
        self.assertEqual(model.data_port, 5556)
        self.assertEqual(model.control_port, 5557)
        self.assertEqual(model.timeout, 3.0)
        self.assertEqual(model.poll_timeout, 0.1)
        self.assertEqual(model.max_age_ms, 50.0)
        self.assertFalse(model.start_acquisition)
        self.assertEqual(model.device_type, str(EyetrackerEnum.MX_EYE))

    def test_mx_eye_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValidationError):
            MxEyeEyetrackerModel(data_port=0)
        with self.assertRaises(ValidationError):
            MxEyeEyetrackerModel(max_age_ms=0)


class EyetrackerFactoryTests(unittest.TestCase):
    def test_builds_mock_eyetracker(self) -> None:
        eyetracker = _make_eyetracker(MockEyetrackerModel())

        self.assertIsInstance(eyetracker, MockEyetracker)

    @patch("mxbiflow.driver.mxbi.factory.MxEyeEyetracker")
    @patch("mxbiflow.driver.mxbi.factory.MxEye")
    @patch("mxbiflow.driver.mxbi.factory.MxEyeConfig")
    def test_builds_mx_eye_eyetracker(
        self,
        config_type,
        client_type,
        eyetracker_type,
    ) -> None:
        config = MxEyeEyetrackerModel(
            host="10.0.0.5",
            data_port=6000,
            control_port=6001,
            timeout=5.0,
            poll_timeout=0.25,
            max_age_ms=25.0,
            start_acquisition=True,
        )

        result = _make_eyetracker(config)

        config_type.assert_called_once_with(
            host="10.0.0.5",
            data_port=6000,
            control_port=6001,
            timeout=5.0,
        )
        client_type.assert_called_once_with(config_type.return_value)
        eyetracker_type.assert_called_once_with(
            client_type.return_value,
            poll_timeout=0.25,
            max_age_ms=25.0,
            start_acquisition=True,
        )
        self.assertIs(result, eyetracker_type.return_value)


class MXBIModelEyetrackerTests(unittest.TestCase):
    def test_defaults_to_no_eyetrackers(self) -> None:
        self.assertEqual(MXBIModel().eyetrackers, [])

    def test_legacy_config_without_eyetrackers_is_accepted(self) -> None:
        model = MXBIModel.model_validate_json(
            '{"mxbi_id": "rig", "rewarders": [], "detectors": []}'
        )

        self.assertEqual(model.eyetrackers, [])

    def test_build_mxbi_wires_mock_eyetracker(self) -> None:
        config = MXBIModel(
            rewarders=[MockRewarderModel(enabled=True)],
            detectors=[MockDetectorModel(enabled=True)],
            eyetrackers=[MockEyetrackerModel(enabled=True)],
        )

        mxbi = build_mxbi(config, logging.getLogger(__name__))
        try:
            eyetracker = mxbi.eyetracker
            self.assertIsInstance(eyetracker, MockEyetracker)
            assert isinstance(eyetracker, MockEyetracker)

            eyetracker.set_sample(1.0, 2.0)

            self.assertIsNotNone(eyetracker.sample())
        finally:
            mxbi.quit()

    def test_build_mxbi_without_eyetrackers_leaves_none(self) -> None:
        config = MXBIModel(
            rewarders=[MockRewarderModel(enabled=True)],
            detectors=[MockDetectorModel(enabled=True)],
        )

        mxbi = build_mxbi(config, logging.getLogger(__name__))
        try:
            self.assertIsNone(mxbi.eyetracker)
        finally:
            mxbi.quit()


if __name__ == "__main__":
    unittest.main()
