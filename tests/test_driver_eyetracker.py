# pyright: reportPrivateUsage=false

import logging
import threading
import time
import unittest
from collections.abc import Callable
from threading import Event
from typing import cast

import zmq
from mx_eye_protocol.data_frame import DataFrame
from py_mx_eye import MxEye, MxEyeConfig, Sample

from mxbiflow.driver.detector.detector import DetectionResult, DetectorEvent
from mxbiflow.driver.eyetracker import (
    EyeSample,
    MockEyetracker,
    MxEyeEyetracker,
)
from mxbiflow.driver.mxbi.mxbi import MXBI

_LOGGER_NAME = "mxbiflow"


def _make_frame(
    *,
    pupil_x: float = 100.0,
    pupil_y: float = 50.0,
    acquisition_ns: int | None = None,
    sequence: int = 1,
) -> DataFrame:
    """Build one real py-mx-eye tracking frame carrying the given pupil centre.

    ``flags`` stays at ``NONE``: the driver reads the pupil centre and passes
    ``require_valid=False``, so an uncalibrated tracker still reports.
    """
    now = time.time_ns() if acquisition_ns is None else acquisition_ns
    return DataFrame(
        session=1,
        sequence=sequence,
        frame=sequence,
        acquisition_ns=now,
        tracking_start_ns=now,
        tracking_end_ns=now,
        send_ns=now,
        media_ns=-1,
        x=pupil_x,
        y=pupil_y,
        pupil_x=pupil_x,
        pupil_y=pupil_y,
        cr_x=float("nan"),
        cr_y=float("nan"),
        pupil_area=1000.0,
        template_ncc=float("nan"),
    )


def _make_sample(
    *,
    pupil_x: float = 100.0,
    pupil_y: float = 50.0,
    acquisition_ns: int | None = None,
    sequence: int = 1,
) -> Sample:
    """Build a real py-mx-eye sample carrying the given pupil centre."""
    return Sample(
        frame=_make_frame(
            pupil_x=pupil_x,
            pupil_y=pupil_y,
            acquisition_ns=acquisition_ns,
            sequence=sequence,
        ),
        receive_ns=time.time_ns(),
    )


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.005) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class _WarningCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _FakeMxEye:
    """Stand-in for ``py_mx_eye.MxEye``.

    ``read`` replays queued batches and then waits on ``timeout``, mirroring
    the SDK contract of blocking the caller. It deliberately has no ``stop``
    method: a backend that stopped acquisition would fail loudly here.
    """

    def __init__(self, batches: list[list[Sample]] | None = None) -> None:
        self.batches: list[list[Sample]] = list(batches or [])
        self.read_error: Exception | None = None
        self.connect_error: Exception | None = None
        self.calls: list[str] = []
        self.read_kwargs: list[dict[str, object]] = []
        self._wake = Event()

    def connect(self) -> _FakeMxEye:
        self.calls.append("connect")
        if self.connect_error is not None:
            raise self.connect_error
        return self

    def start(self) -> None:
        self.calls.append("start")

    def close(self) -> None:
        self.calls.append("close")

    def read(self, timeout=None, max_age_ms=50.0, require_valid=True):
        self.read_kwargs.append(
            {
                "timeout": timeout,
                "max_age_ms": max_age_ms,
                "require_valid": require_valid,
            }
        )
        if self.batches:
            yield from self.batches.pop(0)
            return
        if self.read_error is not None:
            raise self.read_error
        self._wake.wait(timeout)


def _client(fake: _FakeMxEye) -> MxEye:
    """Present the fake as the SDK handle it stands in for."""
    return cast("MxEye", fake)


class MxEyeEyetrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.warnings = _WarningCapture()
        logging.getLogger(_LOGGER_NAME).addHandler(self.warnings)
        self.addCleanup(logging.getLogger(_LOGGER_NAME).removeHandler, self.warnings)

    def _start(self, fake: _FakeMxEye, **kwargs) -> MxEyeEyetracker:
        kwargs.setdefault("poll_timeout", 0.01)
        # Tests care about freshness guards of their own, not the 50 ms default.
        kwargs.setdefault("max_age_ms", 10_000.0)
        tracker = MxEyeEyetracker(_client(fake), **kwargs)
        self.addCleanup(tracker.quit)
        tracker.begin()
        return tracker

    def test_reports_pupil_coordinates_of_received_sample(self) -> None:
        sample = _make_sample(pupil_x=321.5, pupil_y=123.25)
        fake = _FakeMxEye([[sample]])

        tracker = self._start(fake)

        self.assertIn("connect", fake.calls)
        self.assertTrue(_wait_until(lambda: tracker.sample() is not None))
        result = tracker.sample()
        assert result is not None
        self.assertEqual(result.x, 321.5)
        self.assertEqual(result.y, 123.25)
        self.assertEqual(result.timestamp_ns, sample.frame.acquisition_ns)

    def test_read_uses_configured_filters(self) -> None:
        fake = _FakeMxEye()
        tracker = MxEyeEyetracker(
            _client(fake), poll_timeout=0.02, max_age_ms=42.0, start_acquisition=False
        )
        self.addCleanup(tracker.quit)

        tracker.begin()

        self.assertTrue(_wait_until(lambda: bool(fake.read_kwargs)))
        self.assertEqual(
            fake.read_kwargs[0],
            {"timeout": 0.02, "max_age_ms": 42.0, "require_valid": False},
        )

    def test_begin_starts_acquisition_before_connecting(self) -> None:
        fake = _FakeMxEye()

        self._start(fake, start_acquisition=True)

        self.assertEqual(fake.calls[:2], ["start", "connect"])

    def test_begin_does_not_start_acquisition_by_default(self) -> None:
        fake = _FakeMxEye()

        self._start(fake)

        self.assertNotIn("start", fake.calls)

    def test_quit_closes_stream_and_drops_sample(self) -> None:
        fake = _FakeMxEye([[_make_sample()]])
        tracker = self._start(fake)
        self.assertTrue(_wait_until(lambda: tracker.sample() is not None))

        tracker.quit()

        self.assertIn("close", fake.calls)
        self.assertIsNone(tracker.sample())
        self.assertTrue(
            _wait_until(
                lambda: (
                    not any(
                        thread.name == "mx-eye-reader"
                        for thread in threading.enumerate()
                    )
                )
            )
        )

    def test_quit_without_begin_is_a_noop(self) -> None:
        fake = _FakeMxEye()
        tracker = MxEyeEyetracker(_client(fake))

        tracker.quit()

        self.assertIsNone(tracker.sample())

    def test_begin_is_idempotent(self) -> None:
        fake = _FakeMxEye()

        tracker = self._start(fake)
        tracker.begin()

        self.assertEqual(fake.calls.count("connect"), 1)

    def test_begin_succeeds_without_a_publisher(self) -> None:
        fake = _FakeMxEye()

        tracker = self._start(fake)

        self.assertIn("connect", fake.calls)
        # The reader thread drains the stream while the tracker is silent.
        self.assertTrue(_wait_until(lambda: bool(fake.read_kwargs)))
        self.assertIsNone(tracker.sample())

    def test_begin_propagates_socket_setup_failure(self) -> None:
        fake = _FakeMxEye()
        fake.connect_error = RuntimeError("cannot set up the sample socket")
        tracker = MxEyeEyetracker(_client(fake), poll_timeout=0.01)
        self.addCleanup(tracker.quit)

        with self.assertRaises(RuntimeError):
            tracker.begin()

        self.assertIsNone(tracker.sample())
        self.assertFalse(
            any(thread.name == "mx-eye-reader" for thread in threading.enumerate())
        )

    def test_non_finite_pupil_is_not_reported(self) -> None:
        fake = _FakeMxEye([[_make_sample()]])
        tracker = self._start(fake)
        self.assertTrue(_wait_until(lambda: tracker.sample() is not None))

        fake.batches.append([_make_sample(pupil_x=float("nan"))])

        self.assertTrue(_wait_until(lambda: tracker.sample() is None))

    def test_stale_sample_is_not_reported(self) -> None:
        fake = _FakeMxEye([[_make_sample()]])
        tracker = self._start(fake)
        self.assertTrue(_wait_until(lambda: tracker.sample() is not None))

        # The fake replays samples verbatim, so this reaches the backend even
        # though py-mx-eye itself would have filtered it out. ``_start`` uses a
        # generous max_age_ms, so the sample has to be genuinely old.
        fake.batches.append([_make_sample(acquisition_ns=time.time_ns() - 20 * 10**9)])

        self.assertTrue(_wait_until(lambda: tracker.sample() is None))

    def test_stream_failure_logs_and_drops_sample(self) -> None:
        fake = _FakeMxEye([[_make_sample()]])
        tracker = self._start(fake)
        self.assertTrue(_wait_until(lambda: tracker.sample() is not None))

        fake.read_error = ConnectionError("tracker went away")

        self.assertTrue(_wait_until(lambda: bool(self.warnings.records)))
        self.assertTrue(_wait_until(lambda: tracker.sample() is None))
        self.assertIn("tracker went away", self.warnings.records[0].getMessage())
        self.assertGreaterEqual(self.warnings.records[0].levelno, logging.WARNING)


class MxEyeEyetrackerStreamTests(unittest.TestCase):
    """End-to-end test against the real SDK and a local ZeroMQ publisher.

    The fake client replays hand-built samples, so only this test covers the
    wire format, the SDK's subscription path and its session/sequence policy.
    """

    def setUp(self) -> None:
        self.context = zmq.Context()
        self.addCleanup(self.context.term)
        self.publisher = self.context.socket(zmq.PUB)
        self.addCleanup(self.publisher.close, 0)
        self.port = self.publisher.bind_to_random_port("tcp://127.0.0.1")

    def test_reports_sample_published_over_the_wire(self) -> None:
        tracker = MxEyeEyetracker(
            MxEye(MxEyeConfig(host="127.0.0.1", data_port=self.port)),
            poll_timeout=0.05,
            max_age_ms=1000.0,
        )
        self.addCleanup(tracker.quit)

        tracker.begin()

        # ZeroMQ PUB drops messages until the SUB subscription has propagated
        # and the receiver keeps only strictly newer sequence numbers, so keep
        # publishing fresh frames until the backend reports one.
        published: list[int] = []
        sample = None
        sequence = 0
        deadline = time.monotonic() + 5.0
        while sample is None and time.monotonic() < deadline:
            sequence += 1
            frame = _make_frame(pupil_x=321.5, pupil_y=123.25, sequence=sequence)
            published.append(frame.acquisition_ns)
            self.publisher.send(frame.encode())
            sample = tracker.sample()
            time.sleep(0.02)

        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual((sample.x, sample.y), (321.5, 123.25))
        self.assertIn(sample.timestamp_ns, published)


class MockEyetrackerTests(unittest.TestCase):
    def test_reports_nothing_before_a_sample_is_set(self) -> None:
        tracker = MockEyetracker()

        tracker.begin()

        self.assertIsNone(tracker.sample())

    def test_reports_sample_until_cleared_or_quit(self) -> None:
        tracker = MockEyetracker()
        tracker.begin()

        tracker.set_sample(10.0, 20.0, timestamp_ns=1234)

        self.assertEqual(tracker.sample(), EyeSample(timestamp_ns=1234, x=10.0, y=20.0))

        tracker.clear()
        self.assertIsNone(tracker.sample())

        tracker.set_sample(1.0, 2.0)
        tracker.quit()
        self.assertIsNone(tracker.sample())


class _SpyRewarder:
    """Minimal :class:`Rewarder` that records lifecycle calls."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    def open(self) -> None:
        self._events.append("rewarder.open")

    def give_reward(self, duration_ms: int) -> None: ...

    def give_reward_by_volume(self, volume_ul: int) -> None: ...

    def give_reward_by_count(self, count: int) -> None: ...

    def stop_reward(self) -> None: ...

    def close(self) -> None:
        self._events.append("rewarder.close")


class _SpyDetector:
    """Minimal :class:`Detector` that records lifecycle calls."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    def register_event(
        self, event: DetectorEvent, callback: Callable[[DetectionResult], None]
    ) -> None: ...

    def begin(self) -> None:
        self._events.append("detector.begin")

    def quit(self) -> None:
        self._events.append("detector.quit")

    @property
    def current_animal(self) -> str | None:
        return None


class _SpyEyetracker:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def begin(self) -> None:
        self._events.append("eyetracker.begin")

    def quit(self) -> None:
        self._events.append("eyetracker.quit")

    def sample(self) -> EyeSample | None:
        return None


class MXBIEyetrackerTests(unittest.TestCase):
    def test_eyetracker_is_absent_when_not_configured(self) -> None:
        mxbi = MXBI((1024, 600), _SpyRewarder([]), _SpyDetector([]))

        self.assertIsNone(mxbi.eyetracker)

        with self.assertRaises(RuntimeError):
            mxbi.get_eyetracker(0)

    def test_lifecycle_drives_configured_eyetracker(self) -> None:
        events: list[str] = []
        eyetracker = _SpyEyetracker(events)
        mxbi = MXBI((1024, 600), _SpyRewarder(events), _SpyDetector(events), eyetracker)

        mxbi.begin()
        mxbi.quit()

        self.assertIs(mxbi.eyetracker, eyetracker)
        self.assertIs(mxbi.get_eyetracker(0), eyetracker)
        self.assertEqual(events[-3], "eyetracker.quit")
        self.assertEqual(events[-2], "detector.quit")
        with self.assertRaises(RuntimeError):
            mxbi.get_eyetracker(1)


if __name__ == "__main__":
    unittest.main()
