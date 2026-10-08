"""py-mx-eye backed eye-tracker implementation.

This module provides :class:`MxEyeEyetracker`, the concrete
:class:`~mxbiflow.driver.eyetracker.eyetracker.Eyetracker`
implementation that consumes the sample stream of a running mx-eye tracker
through the ``py_mx_eye`` SDK.

Coordinates
-----------
The SDK frame's ``x``/``y`` fields are the gaze coordinates intended for
behavioral use. Raw pupil and corneal-reflection coordinates remain available
separately on the frame for diagnostics and offline calibration.
"""

import math
import time
from threading import Event, Lock, Thread

from py_mx_eye import MxEye, Sample

from mxbiflow.utils.logger import logger

from .eyetracker import EyeSample


class MxEyeEyetracker:
    """Read the sample stream of one mx-eye tracker.

    Implements the :class:`Eyetracker` protocol.

    The ``py_mx_eye`` SDK owns no thread and blocks the caller while waiting
    for samples, so this implementation runs a background reader thread: the
    game loop keeps calling :meth:`sample` without ever waiting on the tracker.
    Samples older than ``max_age_ms`` are reported as unavailable, so a stream
    that goes silent never looks like a frozen gaze position.

    Parameters
    ----------
    client : MxEye
        Connected-capable SDK handle for the tracker. Constructing it is the
        caller's (factory's) responsibility, which keeps this class testable
        without a tracker.
    poll_timeout : float, default=0.1
        Per-wait timeout in seconds handed to :meth:`MxEye.read`. It bounds how
        long the reader thread may block, so it also bounds how quickly
        :meth:`quit` returns.
    max_age_ms : float, default=50.0
        Maximum sample age in milliseconds. Older samples are dropped by the
        SDK and reported as unavailable by :meth:`sample`.
    start_acquisition : bool, default=False
        When ``True``, :meth:`begin` asks the tracker to start acquisition
        before connecting. The default leaves the tracker's acquisition state
        untouched, so the operator stays in control of it.

    Notes
    -----
    ``quit`` only releases the sample stream; it never stops the tracker's
    acquisition, which keeps running for the operator.
    """

    def __init__(
        self,
        client: MxEye,
        *,
        poll_timeout: float = 0.1,
        max_age_ms: float = 50.0,
        start_acquisition: bool = False,
    ) -> None:
        self._client = client
        self._poll_timeout = poll_timeout
        self._max_age_ms = max_age_ms
        self._start_acquisition = start_acquisition

        self._lock = Lock()
        self._stop_event = Event()
        self._latest: Sample | None = None
        self._thread: Thread | None = None

    def begin(self) -> None:
        """Connect to the tracker and start the background reader thread.

        The SDK subscribes asynchronously, so an offline or not-yet-publishing
        tracker is not an error here: :meth:`sample` keeps returning ``None``
        until samples arrive. Only a local socket-setup failure propagates, and
        in that case no reader thread is started.
        """
        if self._thread is not None:
            return

        if self._start_acquisition:
            self._client.start()
        self._client.connect()

        self._stop_event.clear()
        self._thread = Thread(target=self._read_loop, name="mx-eye-reader", daemon=True)
        self._thread.start()

    def quit(self) -> None:
        """Stop the reader thread and release the sample stream."""
        self._stop_event.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)
        self._client.close()
        with self._lock:
            self._latest = None

    def sample(self) -> EyeSample | None:
        """Return the latest fresh sample, or ``None`` when there is none.

        The returned coordinates are the gaze output supplied by mx-eye.
        """
        with self._lock:
            sample = self._latest
        if sample is None:
            return None
        if not sample.is_fresh_at(
            time.time_ns(), self._max_age_ms, require_valid=False
        ):
            return None

        frame = sample.frame
        x, y = frame.x, frame.y
        if not (math.isfinite(x) and math.isfinite(y)):
            return None

        return EyeSample(timestamp_ns=frame.acquisition_ns, x=x, y=y)

    def _read_loop(self) -> None:
        """Drain the sample stream until stopped or the stream breaks."""
        try:
            while not self._stop_event.is_set():
                for sample in self._client.read(
                    timeout=self._poll_timeout,
                    max_age_ms=self._max_age_ms,
                    require_valid=False,
                ):
                    if self._stop_event.is_set():
                        return
                    with self._lock:
                        self._latest = sample
        except Exception as exc:  # noqa: BLE001 - a broken stream must not kill the game
            logger.warning("mx-eye sample stream stopped: %s", exc)
            with self._lock:
                self._latest = None
