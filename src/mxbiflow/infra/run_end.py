"""What happens after a run, reported to cogmote (cagelab/cogmote#424).

Once the game loop quits, the run summary goes to the ``run-summary``
broadcast and the steps after the run (ending the CogMatrix session, uploads,
the report) to the device status: ``state`` is ``finishing`` while they run,
then ``failed`` when one failed, else ``idle``. The steps stay in the status
until the next run starts (:func:`begin_run`), so cogmote shows them after the
rig has gone quiet. Status requests are best effort: an absent cogmoteGO never
stops the run from finishing.
"""

import time
from collections.abc import Iterable, Sequence
from datetime import datetime
from threading import Lock

from pydantic import BaseModel
from pymotego import Broadcast, Client, State, Step
from pymotego.errors import ProblemError

from ..models.session import Session
from ..utils.logger import logger
from .camera_recording import TrialMark
from .post_processing import StageSummary, summarize

#: Broadcast that receives one summary per run.
SUMMARY_BROADCAST = "run-summary"

END_SESSION = "end_session"
UPLOAD_RESULTS = "upload_results"
UPLOAD_RECORDING = "upload_recording"
SEND_REPORT = "send_report"

LABELS = {
    END_SESSION: "End the CogMatrix session",
    UPLOAD_RESULTS: "Upload the results",
    UPLOAD_RECORDING: "Upload the camera recording",
    SEND_REPORT: "Send the report",
}

#: Steps that a CogMatrix sync retries at the next start.
COGMATRIX_STEPS = (END_SESSION, UPLOAD_RESULTS, UPLOAD_RECORDING)


class AnimalRun(BaseModel):
    name: str
    trials: int
    accuracy: float | None
    """Correct among the trials that count, as the trial status reports it."""
    duration_seconds: float
    stages: list[StageSummary]


class RunSummary(BaseModel):
    """What the old post-processing panel showed, per animal."""

    session_id: int
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float
    animals: list[AnimalRun]


def run_summary(session: Session, trials: Sequence[TrialMark]) -> RunSummary:
    summary = summarize(session)

    def accuracy(animal: str) -> float | None:
        judged = [
            t.correct for t in trials if t.animal == animal and t.correct is not None
        ]
        return sum(judged) / len(judged) if judged else None

    return RunSummary(
        session_id=summary.session_id,
        started_at=summary.start_at,
        ended_at=summary.end_at,
        duration_seconds=summary.duration_seconds,
        animals=[
            AnimalRun(
                name=animal.name,
                trials=animal.total_trials,
                accuracy=accuracy(animal.name),
                duration_seconds=animal.total_duration_seconds,
                stages=animal.stages,
            )
            for animal in summary.animals
        ],
    )


def begin_run(session: Session) -> None:
    """Mark the device running and drop the last run's steps and summary."""
    try:
        with Client() as client:
            client.patch_status(
                state="running", started_at=session.start_at, steps=None
            )
    except Exception as error:  # noqa: BLE001 - cogmoteGO may be absent
        logger.warning("cannot reset the device status: %s", error)
    try:
        with Broadcast() as broadcast:
            broadcast.delete(SUMMARY_BROADCAST)
    except ProblemError as error:
        if error.status != 404:
            logger.warning("cannot clear the run summary: %s", error)
    except Exception as error:  # noqa: BLE001 - cogmoteGO may be absent
        logger.warning("cannot clear the run summary: %s", error)


def publish_summary(summary: RunSummary) -> None:
    try:
        with Broadcast() as broadcast:
            broadcast.publish(SUMMARY_BROADCAST, summary.model_dump(mode="json"))
    except Exception as error:  # noqa: BLE001 - the rig screen still shows it
        logger.warning("cannot publish the run summary: %s", error)


class RunEnd:
    """The steps after one run, in order, mirrored to the device status.

    Steps are updated from the thread that runs them; :attr:`steps` may be
    read from any thread. Byte progress is sent at most every
    ``interval_s``; every other change is sent at once.
    """

    def __init__(
        self,
        names: Iterable[str],
        *,
        client: Client | None = None,
        interval_s: float = 1.0,
    ) -> None:
        self._lock = Lock()
        self._steps = [
            Step(name=n, label=LABELS.get(n), state="waiting") for n in names
        ]
        self._client = client if client is not None else Client()
        self._interval_s = interval_s
        self._sent_at = 0.0
        self._failing = False
        self._closed = False
        self._send("finishing")

    @property
    def steps(self) -> tuple[Step, ...]:
        with self._lock:
            return tuple(self._steps)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def failed(self) -> bool:
        return any(step.state == "failed" for step in self.steps)

    def has(self, name: str) -> bool:
        return any(step.name == name for step in self.steps)

    def start(
        self,
        name: str,
        *,
        done: float | None = None,
        total: float | None = None,
        unit: bool = False,
    ) -> None:
        """Mark ``name`` running; ``unit`` says ``done`` and ``total`` are bytes."""
        self._update(
            name,
            state="running",
            done=done,
            total=total,
            unit="bytes" if unit else None,
        )

    def progress(self, name: str, done: float) -> None:
        if (
            self._update(name, done=done, send=False)
            and time.monotonic() - self._sent_at >= self._interval_s
        ):
            self._send("finishing")

    def done(self, name: str, *, url: str | None = None) -> None:
        self._update(name, state="done", url=url)

    def fail(self, names: Iterable[str], reason: str, *, retry: bool) -> None:
        """Mark every step of ``names`` that is not done as failed."""
        wanted = set(names)
        with self._lock:
            self._steps = [
                step.model_copy(
                    update={"state": "failed", "reason": reason, "retry": retry}
                )
                if step.name in wanted and step.state != "done"
                else step
                for step in self._steps
            ]
        self._send("finishing")

    def close(self) -> None:
        """Send the final state and release the connection."""
        self._send("failed" if self.failed else "idle")
        self._closed = True
        self._client.close()

    def _update(self, name: str, *, send: bool = True, **changes: object) -> bool:
        with self._lock:
            index = next((i for i, s in enumerate(self._steps) if s.name == name), None)
            if index is None:
                return False
            self._steps[index] = self._steps[index].model_copy(update=changes)
        if send:
            self._send("finishing")
        return True

    def _send(self, state: State) -> None:
        self._sent_at = time.monotonic()
        try:
            self._client.patch_status(state=state, steps=self.steps)
        except Exception:  # noqa: BLE001 - cogmoteGO may be absent
            if not self._failing:
                logger.warning("cannot report the run end steps", exc_info=True)
            self._failing = True
        else:
            self._failing = False
