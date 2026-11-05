import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx

from mxbiflow.infra.camera_recording import (
    CameraRecording,
    ExportError,
    RecordedCamera,
    TrialMark,
    export_recording,
    segment_start,
    write_subtitles,
)


def local(*args: int) -> datetime:
    return datetime(*args).astimezone()  # type: ignore[arg-type]


def mark(at: datetime, trial_id: int, correct: bool | None = True) -> TrialMark:
    return TrialMark(
        at=at, animal="a1", stage="detect", level=2, trial_id=trial_id, correct=correct
    )


class MediaMTX:
    """MediaMTX's path patch API, recording what it was sent."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[tuple[str, str, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(
            (request.method, request.url.path, json.loads(request.content))
        )
        return httpx.Response(self.status)


class CameraRecordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.directory = Path(self._temporary_directory.name)

    def recording(self, mediamtx: MediaMTX) -> CameraRecording:
        return CameraRecording(
            api_url="http://mediamtx",
            directory=self.directory,
            http=httpx.Client(transport=httpx.MockTransport(mediamtx)),
            settle_s=0,
        )

    def segment(self, start: datetime) -> Path:
        path = self.directory / f"{start.strftime('%Y-%m-%d_%H-%M-%S-%f')}.mp4"
        path.write_bytes(b"fmp4")
        return path

    def test_switches_recording_and_returns_the_session_segments(self) -> None:
        mediamtx = MediaMTX()
        old = self.segment(datetime.now() - timedelta(hours=2))
        recording = self.recording(mediamtx)

        recording.start()
        new = self.segment(datetime.now())
        recorded = recording.stop(
            [mark(datetime.now().astimezone(), 1)],
            capture_latency=timedelta(milliseconds=40),
        )

        self.assertEqual(
            mediamtx.requests,
            [
                ("PATCH", "/v3/config/paths/patch/live", {"record": True}),
                ("PATCH", "/v3/config/paths/patch/live", {"record": False}),
            ],
        )
        assert recorded is not None
        self.assertEqual(recorded.segments, [new])
        self.assertEqual(len(recorded.trials), 1)
        self.assertEqual(recorded.capture_latency, timedelta(milliseconds=40))
        self.assertTrue(old.is_file())

    def test_an_unreachable_api_leaves_the_session_unrecorded(self) -> None:
        mediamtx = MediaMTX(status=500)
        recording = self.recording(mediamtx)

        recording.start()
        self.segment(datetime.now())

        self.assertIsNone(recording.stop([], capture_latency=timedelta()))
        self.assertEqual(len(mediamtx.requests), 1)


def mp4(payload: bytes = b"video") -> bytes:
    ftyp = (12).to_bytes(4) + b"ftypisom"
    moov = (8).to_bytes(4) + b"moov"
    return ftyp + moov + (8 + len(payload)).to_bytes(4) + b"mdat" + payload


class Playback:
    """MediaMTX's playback server: timespans from /list, the same MP4 from /get."""

    def __init__(self, spans: list[tuple[str, float]], body: bytes = mp4()) -> None:
        self.spans = spans
        self.body = body
        self.requests: list[httpx.QueryParams] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.params)
        if request.url.path == "/list":
            return httpx.Response(
                200, json=[{"start": s, "duration": d} for s, d in self.spans]
            )
        return httpx.Response(200, content=self.body)


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        root = Path(self._temporary_directory.name)
        self.segment = root / "2026-10-27_09-00-00-000000.mp4"
        self.segment.write_bytes(b"x" * 100)
        self.exports = root / "exports"
        self.start = local(2026, 10, 27, 9).isoformat()

    def recorded(self, trials: list[TrialMark] | None = None) -> RecordedCamera:
        return RecordedCamera(
            segments=[self.segment],
            stopped=local(2026, 10, 27, 10),
            trials=trials or [],
            capture_latency=timedelta(),
        )

    def export(self, playback: Playback) -> None:
        export_recording(
            self.recorded(
                [
                    mark(local(2026, 10, 27, 9, 0, 1), 1),
                    mark(local(2026, 10, 27, 9, 30, 2), 2),
                ]
            ),
            self.exports,
            http=httpx.Client(
                base_url="http://playback", transport=httpx.MockTransport(playback)
            ),
        )

    def names(self) -> list[str]:
        return sorted(file.name for file in self.exports.iterdir())

    def test_each_timespan_becomes_an_mp4_with_subtitles(self) -> None:
        second = local(2026, 10, 27, 9, 30).isoformat()
        playback = Playback([(self.start, 60.0), (second, 30.5)])

        self.export(playback)

        listing, first, last = playback.requests
        self.assertEqual(listing["start"], self.start)
        self.assertEqual(listing["end"], local(2026, 10, 27, 10).isoformat())
        self.assertEqual(
            (first["path"], first["start"], first["duration"], first["format"]),
            ("live", self.start, "60.0", "mp4"),
        )
        self.assertEqual(last["start"], second)
        self.assertEqual(
            self.names(),
            [
                "2026-10-27_09-00-00-000000.mp4",
                "2026-10-27_09-00-00-000000.vtt",
                "2026-10-27_09-30-00-000000.mp4",
                "2026-10-27_09-30-00-000000.vtt",
            ],
        )
        self.assertEqual(
            (self.exports / "2026-10-27_09-30-00-000000.vtt").read_text(),
            "WEBVTT\n\n00:00:02.000 --> 00:00:07.000\n"
            "trial 2 | a1 | detect@2 | correct\n",
        )
        self.assertTrue(self.segment.is_file())

    def test_a_timespan_over_the_limit_is_split(self) -> None:
        # 7.5 GiB in an hour: 3 GiB is 1440 seconds.
        with open(self.segment, "wb") as file:
            file.truncate(int(7.5 * 2**30))
        playback = Playback([(self.start, 3600.0)])

        self.export(playback)

        parts = [(r["start"], float(r["duration"])) for r in playback.requests[1:]]
        self.assertEqual(
            parts,
            [
                (self.start, 1440.0),
                (local(2026, 10, 27, 9, 24).isoformat(), 1440.0),
                (local(2026, 10, 27, 9, 48).isoformat(), 720.0),
            ],
        )
        self.assertEqual(len(self.names()), 6)
        self.assertIn(
            "00:06:02.000",
            (self.exports / "2026-10-27_09-24-00-000000.vtt").read_text(),
        )

    def test_a_response_that_is_no_whole_mp4_leaves_nothing(self) -> None:
        whole = mp4(b"video")
        for body in (
            whole[:-1],  # a clean response cut short
            whole + b"more",  # sizes wrapped at 4 GiB
            whole[20:],  # moov not first
        ):
            with self.subTest(body=body), self.assertRaises(ExportError):
                self.export(Playback([(self.start, 60.0)], body))
            self.assertFalse(self.exports.exists())
            self.assertTrue(self.segment.is_file())

    def test_a_retry_starts_over(self) -> None:
        self.exports.mkdir()
        (self.exports / "2026-10-27_09-00-00-000000.mp4.part").write_bytes(b"half")

        self.export(Playback([(self.start, 60.0)]))

        self.assertEqual(
            self.names(),
            ["2026-10-27_09-00-00-000000.mp4", "2026-10-27_09-00-00-000000.vtt"],
        )

    def test_a_playback_server_that_is_off_fails_with_the_reason(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with self.assertRaisesRegex(ExportError, "playback.*connection refused"):
            export_recording(
                self.recorded(),
                self.exports,
                http=httpx.Client(
                    base_url="http://playback", transport=httpx.MockTransport(refuse)
                ),
            )
        self.assertTrue(self.segment.is_file())

    def test_a_full_disk_fails_before_any_request(self) -> None:
        playback = Playback([(self.start, 60.0)])
        usage = shutil.disk_usage(self.segment.parent)._replace(free=99)

        with patch("shutil.disk_usage", return_value=usage):
            with self.assertRaisesRegex(ExportError, "disk space"):
                self.export(playback)

        self.assertEqual(playback.requests, [])
        self.assertTrue(self.segment.is_file())

    def test_a_disk_that_fills_during_the_export_leaves_nothing(self) -> None:
        with (
            patch("os.fsync", side_effect=OSError(28, "No space left on device")),
            self.assertRaisesRegex(OSError, "No space left"),
        ):
            self.export(Playback([(self.start, 60.0)]))

        self.assertFalse(self.exports.exists())
        self.assertTrue(self.segment.is_file())

    def test_a_recording_removed_by_retention_exports_nothing(self) -> None:
        self.segment.unlink()
        playback = Playback([])

        self.export(playback)

        self.assertEqual(playback.requests, [])
        self.assertEqual(self.names(), [])


class SubtitleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.directory = Path(self._temporary_directory.name)

    def test_segment_start_is_read_from_the_name(self) -> None:
        self.assertEqual(
            segment_start(Path("2026-10-27_09-30-05-250000.mp4")),
            local(2026, 10, 27, 9, 30, 5, 250000),
        )
        self.assertIsNone(segment_start(Path("notes.mp4")))

    def test_cues_are_relative_to_the_capture_of_the_first_frame(self) -> None:
        first = self.directory / "2026-10-27_09-00-00-000000.mp4"
        second = self.directory / "2026-10-27_10-00-00-000000.mp4"
        trials = [
            mark(local(2026, 10, 27, 8, 59, 59), 0),
            mark(local(2026, 10, 27, 9, 0, 1, 500000), 1),
            mark(local(2026, 10, 27, 9, 0, 3), 2, correct=False),
            mark(local(2026, 10, 27, 9, 59, 59), 3, correct=None),
            mark(local(2026, 10, 27, 10, 0, 2), 4),
        ]

        written = write_subtitles(
            [first, second], trials, capture_latency=timedelta(milliseconds=40)
        )

        self.assertEqual(
            written, [first.with_suffix(".vtt"), second.with_suffix(".vtt")]
        )
        self.assertEqual(
            written[0].read_text(),
            "WEBVTT\n\n"
            "00:00:01.540 --> 00:00:03.040\n"
            "trial 1 | a1 | detect@2 | correct\n\n"
            "00:00:03.040 --> 00:00:08.040\n"
            "trial 2 | a1 | detect@2 | incorrect\n\n"
            "00:59:59.040 --> 01:00:04.040\n"
            "trial 3 | a1 | detect@2 | -\n",
        )
        self.assertEqual(
            written[1].read_text(),
            "WEBVTT\n\n00:00:02.040 --> 00:00:07.040\ntrial 4 | a1 | detect@2 | correct\n",
        )


if __name__ == "__main__":
    unittest.main()
