"""Live trial status and trial broadcasts through cogmoteGO.

Scenes call :meth:`mxbiflow.core.MXBIFlow.publish_trial` once per finished
trial. Requests run on a background thread, so a slow or missing cogmoteGO
never stalls the game loop; failures are logged and dropped.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from queue import SimpleQueue
from threading import Thread

from pydantic import JsonValue
from pymotego import Broadcast, Client, StatusPatch

from ..models.session import Session
from ..utils.logger import logger

#: Broadcast that receives one event per finished trial.
BROADCAST_NAME = "trials"

_CLOSE_TIMEOUT_S = 5.0

type _Job = Callable[[], object]


@dataclass
class _Tally:
    trials: int = 0
    judged: int = 0
    correct: int = 0

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.judged if self.judged else None


class TrialPublisher:
    """Patches the device status and broadcasts each finished trial."""

    def __init__(
        self,
        session: Session,
        *,
        client: Client | None = None,
        broadcast: Broadcast | None = None,
    ) -> None:
        self._session = session
        self._client = client if client is not None else Client()
        self._broadcast = broadcast if broadcast is not None else Broadcast()
        self._tallies: dict[str, _Tally] = {}
        self._jobs: SimpleQueue[_Job | None] = SimpleQueue()
        self._failing = False
        self._thread = Thread(target=self._run, name="trial-publisher", daemon=True)
        self._thread.start()

    def publish(self, record: Mapping[str, object], *, correct: bool | None) -> None:
        """Queue the status patch and broadcast for the current animal's trial.

        ``correct`` is ``None`` for trials that do not count toward accuracy,
        such as aborted ones.
        """
        animal = self._session.require_current_animal()
        stage = animal.current_stage
        tally = self._tallies.setdefault(animal.name, _Tally())
        tally.trials += 1
        if correct is not None:
            tally.judged += 1
            tally.correct += correct

        status: StatusPatch = {
            "state": "running",
            "subject": animal.name,
            "task": f"{stage.stage_name}@{stage.level}",
            "started_at": self._session.start_at,
            "extra": {
                "trials": tally.trials,
                "correct": tally.correct,
                "accuracy": tally.accuracy,
            },
        }
        event: JsonValue = {
            "session_id": self._session.session_id,
            "animal": animal.name,
            "stage": stage.stage_name,
            "level": stage.level,
            "trial_id": animal.trial_id,
            "correct": correct,
            "record": json.loads(json.dumps(record, default=str)),
        }
        self._jobs.put(lambda: self._client.patch_status(**status))
        self._jobs.put(lambda: self._broadcast.publish(BROADCAST_NAME, event))

    def close(self) -> None:
        """Mark the device idle, flush queued requests and release connections."""
        self._jobs.put(
            lambda: self._client.patch_status(
                state="idle", subject=None, task=None, started_at=None, extra=None
            )
        )
        self._jobs.put(None)
        self._thread.join(_CLOSE_TIMEOUT_S)
        if self._thread.is_alive():
            logger.warning(
                "trial publisher did not finish within %ss", _CLOSE_TIMEOUT_S
            )
            return
        self._client.close()
        self._broadcast.close()

    def _run(self) -> None:
        while (job := self._jobs.get()) is not None:
            try:
                job()
            except Exception:  # noqa: BLE001 - cogmoteGO may be absent
                if not self._failing:
                    logger.warning("failed to publish trial status", exc_info=True)
                self._failing = True
            else:
                if self._failing:
                    logger.info("trial status publishing recovered")
                self._failing = False
