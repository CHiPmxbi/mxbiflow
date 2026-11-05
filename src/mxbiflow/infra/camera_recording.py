"""Record the rig camera during a session (#195), with trial subtitles (#197).

MediaMTX serves the camera on path ``live`` and already encodes it for
live viewing, so recording only remuxes to disk. Recording is switched on for
the session through MediaMTX's local API and off at its end. MediaMTX writes
fragmented MP4, which keeps all but the last second after a crash but has no
index, so a browser walks every fragment to open it. After the session
:func:`export_recording` asks MediaMTX's playback server for standard MP4,
without re-encoding, one file per recorded timespan with its WebVTT subtitles
(#245). The exports are uploaded as session data and the segments deleted
(:class:`~mxbiflow.infra.cogmatrix_sync.CogMatrixRecorder`).

Segment names carry the segment start (``recordPath`` ends in
``%Y-%m-%d_%H-%M-%S-%f``, local time) and trials are stamped when they are
published, both from the rig's clock, so no cross-device sync is needed. The
start is when MediaMTX received the first frame, which the camera captured
``capture_latency`` earlier: a trial at ``t`` is at ``t - (start - latency)``
in the video. An export starts at the first frame of its timespan and is named
like a segment, by its own start.

MediaMTX writes MP4 sizes and offsets in 32 bits, so a file over 4 GiB comes out
corrupt while the request succeeds. A long timespan is split by its bitrate into
files below ``_MP4_LIMIT``, and every export is checked before it gets its name.
"""

import os
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import BaseModel

from ..utils.logger import logger

#: MediaMTX's API, enabled on loopback only by ``cagelab.cogmote``.
MEDIAMTX_API = "http://127.0.0.1:9997"
#: MediaMTX's playback server, enabled on loopback only by ``cagelab.cogmote``.
MEDIAMTX_PLAYBACK = "http://127.0.0.1:9996"
#: The MediaMTX path of the camera.
CAMERA_PATH = "live"
#: MediaMTX runs in the desktop account's home with ``recordPath: ./recordings/%path/...``.
RECORDINGS_DIR = Path.home() / "recordings" / CAMERA_PATH

_SEGMENT_NAME_FORMAT = "%Y-%m-%d_%H-%M-%S-%f"
# MediaMTX starts a segment at the first frame after recording is switched on.
_START_TOLERANCE = timedelta(seconds=5)
_CUE_DURATION = timedelta(seconds=5)
# Well below 4 GiB, because the split assumes an even bitrate.
_MP4_LIMIT = 3 * 2**30
# MediaMTX reads every fragment's header before the first byte of a response.
_EXPORT_TIMEOUT = httpx.Timeout(30.0, read=600.0)


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


class RecordedCamera(BaseModel):
    """A session's recording, kept in the run's record until it is exported."""

    segments: list[Path]
    stopped: datetime
    trials: list[TrialMark]
    capture_latency: timedelta


class ExportError(Exception):
    """The recording cannot be exported now; its segments are kept for a retry."""


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
    ) -> RecordedCamera | None:
        """Switch recording off and return what it wrote, if anything."""
        started, self._started = self._started, None
        if started is None:
            return None
        try:
            self._set_record(False)
        except httpx.HTTPError as error:
            # experiment.service switches it off again when the run stops.
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
        logger.info("camera recording stopped: %d segments", len(segments))
        if not segments:
            return None
        return RecordedCamera(
            segments=segments,
            stopped=datetime.now(UTC),
            trials=list(trials),
            capture_latency=capture_latency,
        )

    def _set_record(self, record: bool) -> None:
        self._http.patch(self._url, json={"record": record}).raise_for_status()


def export_recording(
    recorded: RecordedCamera,
    directory: Path,
    *,
    http: httpx.Client | None = None,
    path: str = CAMERA_PATH,
    on_bytes: Callable[[int], None] = lambda _: None,
) -> None:
    """Fill ``directory`` with the recording's standard MP4 files and their subtitles.

    Raises :class:`ExportError` or :class:`OSError` with the segments untouched; a
    retry starts over, so what an earlier attempt left in ``directory`` is removed.
    """
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    segments = [segment for segment in recorded.segments if segment.is_file()]
    for gone in set(recorded.segments) - set(segments):
        logger.warning("camera recording %s is gone", gone)
    if not segments:
        return
    size = sum(segment.stat().st_size for segment in segments)
    free = shutil.disk_usage(directory).free
    if free < size:
        raise ExportError(
            f"not enough disk space to export the camera recording: "
            f"{size} bytes needed, {free} free"
        )
    if http is None:
        http = httpx.Client(base_url=MEDIAMTX_PLAYBACK, timeout=_EXPORT_TIMEOUT)
    try:
        with http as client:
            spans = _timespans(
                client, path, min(map(_start, segments)), recorded.stopped
            )
            files = [
                _export_part(client, path, start, duration, directory, on_bytes)
                for start, duration in _split(spans, size)
            ]
    except httpx.HTTPError as error:
        shutil.rmtree(directory, ignore_errors=True)
        raise ExportError(f"MediaMTX playback at {http.base_url}: {error}") from error
    except ExportError, OSError:
        # Two copies must not stay on a disk that may be full.
        shutil.rmtree(directory, ignore_errors=True)
        raise
    write_subtitles(files, recorded.trials, capture_latency=recorded.capture_latency)
    # The caller records that the export is done, which must not outlive these names.
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _timespans(
    http: httpx.Client, path: str, start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    response = http.get(
        "/list",
        params={"path": path, "start": start.isoformat(), "end": end.isoformat()},
    )
    response.raise_for_status()
    return [
        (datetime.fromisoformat(span["start"]), span["duration"])
        for span in response.json()
    ]


def _split(
    spans: Sequence[tuple[datetime, float]], size: int
) -> list[tuple[datetime, float]]:
    """Cut the timespans into pieces that stay below ``_MP4_LIMIT`` at their bitrate."""
    longest = _MP4_LIMIT * sum(duration for _, duration in spans) / size
    parts: list[tuple[datetime, float]] = []
    for start, duration in spans:
        offset = 0.0
        while duration - offset > longest:
            parts.append((start + timedelta(seconds=offset), longest))
            offset += longest
        parts.append((start + timedelta(seconds=offset), duration - offset))
    return parts


def _export_part(
    http: httpx.Client,
    path: str,
    start: datetime,
    duration: float,
    directory: Path,
    on_bytes: Callable[[int], None],
) -> Path:
    """Download one MP4; it appears under its name only once it is whole."""
    name = start.astimezone().strftime(_SEGMENT_NAME_FORMAT)
    target = directory / f"{name}.mp4"
    partial = directory / f"{name}.mp4.part"
    params = {
        "path": path,
        "start": start.isoformat(),
        "duration": duration,
        "format": "mp4",
    }
    with (
        http.stream("GET", "/get", params=params) as response,
        partial.open("wb") as file,
    ):
        response.raise_for_status()
        for chunk in response.iter_bytes():
            file.write(chunk)
            on_bytes(len(chunk))
        file.flush()
        os.fsync(file.fileno())
    _check_standard_mp4(partial)
    partial.replace(target)
    return target


def _check_standard_mp4(file: Path) -> None:
    """Refuse anything but a whole ``ftyp``, ``moov``, ``mdat`` file.

    MediaMTX ends a response normally when reading a segment fails midway, and
    wraps sizes over 4 GiB, so a clean response proves nothing.
    """
    size = file.stat().st_size
    kinds: list[bytes] = []
    offset = 0
    with file.open("rb") as content:
        while offset < size and len(kinds) < 4:
            content.seek(offset)
            header = content.read(8)
            kinds.append(header[4:8])
            offset += max(int.from_bytes(header[:4]), 8)
    if kinds != [b"ftyp", b"moov", b"mdat"] or offset != size:
        raise ExportError(
            f"MediaMTX gave no whole standard MP4 for {file.stem}: "
            f"boxes {kinds}, {offset} bytes of {size}"
        )


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
    """Write ``<segment>.vtt`` next to each MP4 named by its start, with a cue per trial.

    A cue shows a trial from its end until the next trial, at most
    ``_CUE_DURATION``. A file holds the trials until the next one starts.
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
