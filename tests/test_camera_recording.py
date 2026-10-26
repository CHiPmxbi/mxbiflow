import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from mxbiflow.infra.camera_recording import (
    CameraRecording,
    TrialMark,
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
        files = recording.stop([], capture_latency=timedelta())

        self.assertEqual(
            mediamtx.requests,
            [
                ("PATCH", "/v3/config/paths/patch/mystream", {"record": True}),
                ("PATCH", "/v3/config/paths/patch/mystream", {"record": False}),
            ],
        )
        self.assertEqual(files, [new, new.with_suffix(".vtt")])
        self.assertTrue(files[1].is_file())
        self.assertTrue(old.is_file())

    def test_an_unreachable_api_leaves_the_session_unrecorded(self) -> None:
        mediamtx = MediaMTX(status=500)
        recording = self.recording(mediamtx)

        recording.start()
        self.segment(datetime.now())

        self.assertEqual(recording.stop([], capture_latency=timedelta()), [])
        self.assertEqual(len(mediamtx.requests), 1)


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
