# pyright: reportPrivateUsage=false

import unittest
from threading import Thread
from unittest.mock import Mock, patch

from mxbiflow.driver.detector.detector import DetectionResult, DetectorEvent
from mxbiflow.driver.detector.fusion_continuous_detector import (
    FusionContinuousDetector,
    _Event,
)
from mxbiflow.driver.peripheral.rfid.dorset_lid665v42 import Result

MODULE = "mxbiflow.driver.detector.fusion_continuous_detector"


class FusionIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = Mock()
        self.reader.read.return_value = None
        self.sensor = Mock()
        self.sensor.read.return_value = True
        self.detector = FusionContinuousDetector(self.reader, self.sensor)
        self.events: list[tuple[DetectorEvent, DetectionResult]] = []
        for event in DetectorEvent:
            self.detector.register_event(
                event, lambda result, event=event: self.events.append((event, result))
            )
        self.poll(100.0)

    def poll(self, now: float, tag: Result | None = None, *, beam: bool = True) -> None:
        self.reader.read.return_value = tag
        self.sensor.read.return_value = beam
        with patch(f"{MODULE}.time", return_value=now):
            self.detector._poll_once()

    def test_identifies_within_window_and_locks_leave_identity(self) -> None:
        self.assertEqual(self.events, [])
        self.poll(101.0, Result(100.5, "A"))
        self.poll(102.0, Result(101.5, "A"))
        self.poll(103.0, Result(102.5, "B"))
        self.assertEqual(self.detector.current_animal, "A")
        self.poll(104.0, beam=False)
        self.assertEqual(
            [event for event, _ in self.events],
            [
                DetectorEvent.ANIMAL_ENTERED,
                DetectorEvent.ANIMAL_LEFT,
            ],
        )
        self.assertEqual([result.animal_id for _, result in self.events], ["A", "A"])
        self.assertIsNone(self.detector.current_animal)

    def test_identifies_after_timeout_without_second_enter_event(self) -> None:
        self.poll(111.0)
        self.poll(112.0)
        self.assertEqual(len(self.events), 1)
        self.assertTrue(self.events[0][1].error)
        self.poll(130.0, Result(129.5, "A"))
        self.poll(131.0, Result(130.5, "A"))
        self.assertEqual(
            [event for event, _ in self.events],
            [
                DetectorEvent.UNKNOWN_ANIMAL_ENTERED,
                DetectorEvent.ANIMAL_IDENTIFIED,
            ],
        )
        self.assertEqual(self.events[-1][1].animal_id, "A")
        self.assertFalse(self.events[-1][1].error)
        self.assertEqual(self.detector.current_animal, "A")

    def test_rejects_pre_entry_stale_and_future_tags(self) -> None:
        self.poll(101.0, Result(99.9, "old-entry"))
        self.poll(111.0)
        self.poll(130.0, Result(110.0, "stale"))
        self.poll(131.0, Result(132.0, "future"))
        self.assertEqual(
            [event for event, _ in self.events],
            [
                DetectorEvent.UNKNOWN_ANIMAL_ENTERED,
            ],
        )
        self.assertIsNone(self.detector.current_animal)

    def test_leave_wins_over_tag_and_timeout(self) -> None:
        self.poll(111.0, Result(110.5, "A"), beam=False)
        self.assertEqual(
            [event for event, _ in self.events], [DetectorEvent.ANIMAL_LEFT]
        )
        self.assertIsNone(self.events[0][1].animal_id)

    def test_unknown_leave_wins_over_late_tag_and_next_entry_starts_fresh(self) -> None:
        self.poll(111.0)
        self.poll(112.0, Result(111.5, "A"), beam=False)
        self.poll(120.0, Result(111.5, "A"))
        self.assertEqual(
            [event for event, _ in self.events],
            [
                DetectorEvent.UNKNOWN_ANIMAL_ENTERED,
                DetectorEvent.ANIMAL_LEFT,
            ],
        )
        self.poll(121.0, Result(120.5, "B"))
        self.assertEqual(self.events[-1][0], DetectorEvent.ANIMAL_ENTERED)
        self.assertEqual(self.detector.current_animal, "B")

    def test_valid_tag_wins_over_timeout_in_same_poll(self) -> None:
        self.poll(111.0, Result(110.5, "A"))
        self.assertEqual(
            [event for event, _ in self.events], [DetectorEvent.ANIMAL_ENTERED]
        )

    def test_callback_can_read_committed_identity_without_deadlock(self) -> None:
        observed = []
        self.detector.register_event(
            DetectorEvent.ANIMAL_ENTERED,
            lambda result: observed.append(self.detector.current_animal),
        )
        thread = Thread(
            target=lambda: self.poll(101.0, Result(100.5, "A")), daemon=True
        )
        thread.start()
        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(observed, ["A"])


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
