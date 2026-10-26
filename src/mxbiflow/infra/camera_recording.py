"""Record the rig camera during a session (#195), with trial subtitles (#197).

MediaMTX serves the Pi camera on path ``mystream`` and already encodes it for
live viewing, so recording only remuxes to disk. Recording is switched on for
the session through MediaMTX's local API and off at its end; the fMP4 segments
it wrote and one WebVTT subtitle file per segment are then uploaded as session
data and deleted (:class:`~mxbiflow.infra.cogmatrix_sync.CogMatrixRecorder`).

Segment names carry the segment start (``recordPath`` ends in
``%Y-%m-%d_%H-%M-%S-%f``, local time) and trials are stamped when they are
published, both from the rig's clock, so no cross-device sync is needed. The
start is when MediaMTX received the first frame, which the camera captured
``capture_latency`` earlier: a trial at ``t`` is at ``t - (start - latency)``
in the video.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from ..utils.logger import logger

#: MediaMTX's API, enabled on loopback only by CHiPmxbi/setup.
MEDIAMTX_API = "http://127.0.0.1:9997"
#: The MediaMTX path of the Pi camera.
CAMERA_PATH = "mystream"
#: MediaMTX runs in the desktop account's home with ``recordPath: ./recordings/%path/...``.
RECORDINGS_DIR = Path.home() / "recordings" / CAMERA_PATH

_SEGMENT_NAME_FORMAT = "%Y-%m-%d_%H-%M-%S-%f"
# MediaMTX starts a segment at the first frame after recording is switched on.
_START_TOLERANCE = timedelta(seconds=5)
_CUE_DURATION = timedelta(seconds=5)


@dataclass(frozen=True)
class TrialMark:
    """A finished trial for the subtitles, stamped with the rig's clock."""

    at: datetime
    animal: str
    stage: str
    level: int
    trial_id: int
    correct: bool | None

    @property
    def text(self) -> str:
        result = {True: "correct", False: "incorrect", None: "-"}[self.correct]
        return (
            f"trial {self.trial_id} | {self.animal} | "
            f"{self.stage}@{self.level} | {result}"
        )


class CameraRecording:
    """Records the camera path between :meth:`start` and :meth:`stop`."""

    def __init__(
        self,
        *,
        api_url: str = MEDIAMTX_API,
        path: str = CAMERA_PATH,
        directory: Path = RECORDINGS_DIR,
        http: httpx.Client | None = None,
        settle_s: float = 2.0,
    ) -> None:
        self._url = f"{api_url}/v3/config/paths/patch/{path}"
        self._directory = directory
        self._http = http if http is not None else httpx.Client(timeout=5.0)
        self._settle_s = settle_s
        self._started: datetime | None = None

    def start(self) -> None:
        """Switch recording on; a failure leaves the session unrecorded."""
        started = datetime.now(UTC)
        try:
            self._set_record(True)
        except httpx.HTTPError as error:
            logger.warning("camera not recorded: %s", error)
            return
        self._started = started
        logger.info("camera recording started")

    def stop(
        self, trials: Sequence[TrialMark], *, capture_latency: timedelta
    ) -> list[Path]:
        """Switch recording off and return the segments, each followed by its subtitles."""
        started, self._started = self._started, None
        if started is None:
            return []
        try:
            self._set_record(False)
        except httpx.HTTPError as error:
            # mxbi-run.service switches it off again when the run stops.
            logger.warning("cannot stop the camera recording: %s", error)
        finally:
            self._http.close()
        # MediaMTX writes the last part of the segment after recording is off.
        time.sleep(self._settle_s)
        segments = [
            path
            for path in sorted(self._directory.glob("*.mp4"))
            if (start := segment_start(path)) is not None
            and start >= started - _START_TOLERANCE
        ]
        subtitles = write_subtitles(segments, trials, capture_latency=capture_latency)
        logger.info("camera recording stopped: %d segments", len(segments))
        return [file for pair in zip(segments, subtitles) for file in pair]

    def _set_record(self, record: bool) -> None:
        self._http.patch(self._url, json={"record": record}).raise_for_status()


def segment_start(segment: Path) -> datetime | None:
    """Return the start time in a MediaMTX segment name, or ``None``."""
    try:
        local = datetime.strptime(segment.stem, _SEGMENT_NAME_FORMAT)
    except ValueError:
        return None
    return local.astimezone()


def write_subtitles(
    segments: Sequence[Path],
    trials: Sequence[TrialMark],
    *,
    capture_latency: timedelta,
) -> list[Path]:
    """Write ``<segment>.vtt`` next to each segment with a cue per trial.

    A cue shows a trial from its end until the next trial, at most
    ``_CUE_DURATION``. A segment holds the trials until the next one starts.
    """
    origins = [_start(segment) - capture_latency for segment in segments]
    written: list[Path] = []
    for index, segment in enumerate(segments):
        origin = origins[index]
        until = origins[index + 1] if index + 1 < len(origins) else None
        marks = [
            mark
            for mark in trials
            if mark.at >= origin and (until is None or mark.at < until)
        ]
        cues: list[str] = []
        for position, mark in enumerate(marks):
            begin = mark.at - origin
            end = begin + _CUE_DURATION
            if position + 1 < len(marks):
                end = min(end, marks[position + 1].at - origin)
            cues.append(f"{_timestamp(begin)} --> {_timestamp(end)}\n{mark.text}\n")
        subtitles = segment.with_suffix(".vtt")
        subtitles.write_text("\n".join(["WEBVTT\n", *cues]), encoding="utf-8")
        written.append(subtitles)
    return written


def _start(segment: Path) -> datetime:
    start = segment_start(segment)
    if start is None:
        raise ValueError(f"not a MediaMTX segment name: {segment.name}")
    return start


def _timestamp(offset: timedelta) -> str:
    milliseconds = offset // timedelta(milliseconds=1)
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, milliseconds = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
