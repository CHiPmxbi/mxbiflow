from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from mxbiflow.driver import MXBI
from mxbiflow.driver.eyetracker.eyetracker import EyeSample

from ..infra.camera_recording import TrialMark
from ..infra.timer import FrameTimer
from ..infra.trial_status import TrialPublisher
from ..models.session import Session
from ..models.trial import split_record
from .offline import is_offline
from .path import get_data_dir_path


class MXBIFlow:
    def __init__(self, session: Session, mxbi: MXBI) -> None:
        self._session = session
        self._timer = FrameTimer()
        self._mxbi = mxbi
        self._trial_publisher: TrialPublisher | None = None
        self._trials: list[TrialMark] = []

    @property
    def session(self) -> Session:
        return self._session

    @property
    def timer(self) -> FrameTimer:
        return self._timer

    @property
    def mxbi(self) -> MXBI:
        return self._mxbi

    @property
    def eye_sample(self) -> EyeSample | None:
        """Return the eye-tracking sample available for this frame.

        ``None`` when no eyetracker is configured, or when no usable sample is
        available: none measured yet, aged out, or the sample stream stopped.

        Scenes read this from ``update(dt_s)``, so gaze is consumed once per
        frame without blocking the game loop. See ``docs/eyetracking.md``.
        """
        eyetracker = self._mxbi.eyetracker
        return None if eyetracker is None else eyetracker.sample()

    @property
    def trials(self) -> Sequence[TrialMark]:
        """The session's published trials, for the camera recording's subtitles."""
        return self._trials

    @property
    def data_dir(self) -> Path:
        return get_data_dir_path()

    def publish_trial(
        self, record: BaseModel | Mapping[str, object], *, correct: bool | None
    ) -> None:
        """Report a finished trial of the current animal to cogmoteGO.

        Patches the device status (animal, ``stage@level``, trial count and
        accuracy) and publishes ``record`` to the ``trials`` broadcast. Call it
        once per trial; ``correct=None`` leaves the trial out of accuracy.
        Offline, nothing is sent; the trial still counts in the run summary.
        Pass the record model, not its dump: its ``AnimalBaseInfo`` becomes the
        event's context and its fields the table's schema hint
        (:mod:`mxbiflow.models.trial`). It also gives the subtitle's level and
        trial, so a level-up trial shows the level it started with; without it
        they come from the session.
        """
        animal = self._session.require_current_animal()
        stage = animal.current_stage
        base_info = split_record(record)[0] if isinstance(record, BaseModel) else None
        self._trials.append(
            TrialMark(
                at=datetime.now(UTC),
                animal=animal.name,
                stage=stage.stage_name,
                level=base_info.level if base_info else stage.level,
                trial_id=base_info.trial_id if base_info else animal.trial_id,
                correct=correct,
            )
        )
        if is_offline():
            return
        if self._trial_publisher is None:
            self._trial_publisher = TrialPublisher(self._session)
        self._trial_publisher.publish(record, correct=correct)

    def upload_file(self, path: Path | str) -> None:
        """Upload a file with the current run's results.

        The file is under the run's data directory, and is read when the run
        uploads, so it can still grow. It is kept in the run's local record at
        once, so a retry or a crashed run uploads it too; a file gone by then
        logs a warning. Its asset name drops the date and session number from
        the path: ``<animal>-<stage>-<file>``. Raises ``ValueError`` for a path
        outside the data directory and for two files with the same asset name.
        :class:`~mxbiflow.infra.data_logger.DataLogger` names its own file.
        """
        self._session.add_upload(path)

    def update(self) -> None:
        self._timer.update()

    def close(self) -> None:
        if self._trial_publisher is not None:
            self._trial_publisher.close()
            self._trial_publisher = None


_current_mxbiflow: MXBIFlow | None = None


def get_mxbiflow() -> MXBIFlow:
    if _current_mxbiflow is None:
        raise RuntimeError("MXBIFlow not initialized")
    return _current_mxbiflow


def set_mxbiflow(mxbiflow: MXBIFlow) -> None:
    global _current_mxbiflow
    if _current_mxbiflow is not None:
        raise RuntimeError("MXBIFlow already initialized")
    _current_mxbiflow = mxbiflow
