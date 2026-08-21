# pyright: reportPrivateUsage=false

import unittest
from unittest.mock import Mock

from mxbiflow.driver.detector.detector import DetectorEvent
from mxbiflow.driver.detector.fusion_continuous_detector import (
    FusionContinuousDetector,
    _Event,
)


class FusionContinuousDetectorFilterTests(unittest.TestCase):
    def test_disabled_filter_emits_falling_edge_immediately(self) -> None:
        sensor = Mock()
        sensor.read.side_effect = [True, False]
        detector = FusionContinuousDetector(Mock(), sensor)

        self.assertEqual(detector._detect_edge(0.0), _Event.RISING_EDGE)
        self.assertEqual(detector._detect_edge(0.01), _Event.FALLING_EDGE)

    def test_enabled_filter_cancels_transient_clear_state(self) -> None:
        sensor = Mock()
        sensor.read.side_effect = [True, False, True, False, False, False]
        detector = FusionContinuousDetector(
            Mock(),
            sensor,
            beam_break_filter_enabled=True,
            beam_break_filter_duration=0.2,
        )

        self.assertEqual(detector._detect_edge(0.0), _Event.RISING_EDGE)
        self.assertIsNone(detector._detect_edge(0.01))
        self.assertIsNone(detector._detect_edge(0.1))
        self.assertIsNone(detector._detect_edge(0.2))
        self.assertIsNone(detector._detect_edge(0.39))
        self.assertEqual(detector._detect_edge(0.4), _Event.FALLING_EDGE)

    def test_filtered_falling_edge_emits_one_leave_event(self) -> None:
        sensor = Mock()
        sensor.read.side_effect = [True, False, False, False]
        detector = FusionContinuousDetector(
            Mock(),
            sensor,
            beam_break_filter_enabled=True,
            beam_break_filter_duration=0.2,
        )
        results = []
        detector.register_event(DetectorEvent.ANIMAL_LEFT, results.append)

        rising = detector._detect_edge(0.0)
        self.assertEqual(rising, _Event.RISING_EDGE)
        if rising is None:
            self.fail("Expected a rising edge")
        detector._dispatch(rising)
        detector._dispatch(_Event.TIMEOUT)

        self.assertIsNone(detector._detect_edge(0.1))
        falling = detector._detect_edge(0.31)
        self.assertEqual(falling, _Event.FALLING_EDGE)
        if falling is None:
            self.fail("Expected a falling edge")
        detector._dispatch(falling)
        self.assertIsNone(detector._detect_edge(0.5))

        self.assertEqual(len(results), 1)

    def test_rejects_non_positive_filter_duration(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than 0"):
            FusionContinuousDetector(Mock(), Mock(), beam_break_filter_duration=0)


if __name__ == "__main__":
    unittest.main()
