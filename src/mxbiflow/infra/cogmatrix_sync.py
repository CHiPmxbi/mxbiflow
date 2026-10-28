"""Record each run in CogMatrix: a session at start, its data assets at the end (#172).

The node writes as itself with the CogMatrix token cogmoteGO serves on loopback
(``cogmatrix.auth.CogmoteTokenAuth``). The cogmote ``mxbi`` config names the
endpoint, the protocol, the storage repository and the operator; all its
animals are the subjects. Every step is kept in a local record under
``.mxbiflow/state/cogmatrix/`` until CogMatrix has it, so a run that started
offline or whose uploads failed is completed at the next start.

The node registers as an uploader of the session when it creates it and
uploads with ``sessions.upload_data`` (#216): the results with the list kept
open, then the camera recordings (#195), closing it. CogMatrix skips what it
already has, so a retry uploads only the rest, and marks the session's data
complete once every file arrived. Recordings are deleted locally once
CogMatrix has them; a recording that MediaMTX's retention already removed is
skipped.

A run that never ended, because the rig lost power or the process died (#193),
is ended as ``aborted`` at the next start, at its last result write, with the
results it has.

:meth:`CogMatrixRecorder.finish` reports its progress as run end steps
(:class:`~mxbiflow.infra.run_end.RunEnd`), recordings in bytes.
"""

import json
import shutil
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from uuid import UUID

import httpx
from cogmatrix import (
    CodeVersion,
    CogMatrixClient,
    EndExperimentSessionInput,
    ExperimentSessionStatus,
)
from cogmatrix.auth import CogmoteTokenAuth
from cogmatrix.git import code_version
from cogmatrix.transfer import STORAGE_TIMEOUT
from pydantic import BaseModel, Field, JsonValue
from pymotego import Client

from ..core.path import get_base_path, get_internal_state_path
from ..models.session import Session
from ..utils.logger import logger
from .run_end import (
    COGMATRIX_STEPS,
    END_SESSION,
    UPLOAD_RECORDING,
    UPLOAD_RESULTS,
    RunEnd,
)

type ClientFactory = Callable[[str, httpx.Client], CogMatrixClient]
"""Builds a client for the endpoint that sends file bytes with the given storage client."""


def cogmote_client(endpoint: str, storage: httpx.Client) -> CogMatrixClient:
    return CogMatrixClient(
        endpoint, auth=CogmoteTokenAuth(endpoint), storage_client=storage
    )


def session_url(endpoint: str, session_id: str) -> str:
    """The session in the CogMatrix web app, served next to its GraphQL endpoint."""
    return urljoin(endpoint, f"/sessions?session={session_id}")


class PendingRun(BaseModel):
    """What CogMatrix still lacks of one run."""

    endpoint: str
    config: dict[str, JsonValue]
    code: CodeVersion
    started_at: datetime
    title: str
    notes: str | None = None
    data_root: str | None = None
    data_path: str | None = None
    session_id: str | None = None
    ended_at: datetime | None = None
    status: ExperimentSessionStatus = ExperimentSessionStatus.completed
    ended: bool = False
    registered: bool = False
    """The node is an uploader of the session, so CogMatrix waits for its files."""
    files: list[str] = Field(default_factory=list)
    recordings: list[str] = Field(default_factory=list)


def get_cogmatrix_state_path() -> Path:
    return get_internal_state_path() / "cogmatrix"


class CogMatrixRecorder:
    """Creates the run's CogMatrix session, ends it and uploads its results."""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        client_factory: ClientFactory = cogmote_client,
        read_config: Callable[[], dict[str, JsonValue]] = lambda: Client().get_config(),
    ) -> None:
        self._state_dir = state_dir or get_cogmatrix_state_path()
        self._client_factory = client_factory
        self._read_config = read_config
        self._current: Path | None = None

    @property
    def recording(self) -> bool:
        """The current run is in CogMatrix, so :meth:`finish` has steps to report."""
        return self._current is not None

    def retry_pending(self) -> None:
        """Complete the runs that earlier starts left unfinished.

        Runs that never ended are ended as aborted first (#193).
        """
        if not self._state_dir.is_dir():
            return
        for run_dir in sorted(self._state_dir.iterdir()):
            if run_dir.is_dir() and run_dir != self._current:
                _end_abandoned(run_dir)
                self._sync(run_dir)

    def start(self, session: Session) -> None:
        """Record the started run and create its CogMatrix session."""
        try:
            config = self._read_config()
        except Exception as error:  # noqa: BLE001 - the run goes on without CogMatrix
            logger.warning("not recorded in CogMatrix: no cogmote config (%s)", error)
            return
        experiment = config.get("experiment")
        cogmatrix = config.get("cogmatrix")
        if not isinstance(experiment, dict) or not isinstance(cogmatrix, dict):
            logger.warning("not recorded in CogMatrix: no cogmote experiment config")
            return
        try:
            code = code_version(get_base_path())
        except Exception as error:  # noqa: BLE001 - CogMatrix needs the code version
            logger.warning("not recorded in CogMatrix: no git version (%s)", error)
            return
        if session.start_at is None or session.data_path is None:
            raise RuntimeError("Session is not started")

        run = PendingRun(
            endpoint=str(cogmatrix["url"]),
            config=config,
            code=code,
            started_at=_milliseconds(session.start_at),
            title=f"{session.device_name} session {session.session_id}",
            notes=session.note or None,
            data_root=str(session.data_root) if session.data_root else None,
            data_path=str(session.data_path) if session.data_path else None,
        )
        run_dir = self._state_dir / str(session.data_path).replace("/", "-")
        _save(run_dir, run)
        self._current = run_dir
        self._sync(run_dir)

    def finish(
        self,
        session: Session,
        *,
        aborted: bool = False,
        recordings: Sequence[Path] = (),
        steps: RunEnd | None = None,
    ) -> None:
        """End the run's CogMatrix session and upload its results and recordings.

        ``recordings`` are deleted once uploaded. ``steps`` receives the progress.
        """
        run_dir = self._current
        if run_dir is None:
            if recordings:
                logger.warning(
                    "camera recordings kept, the run is not in CogMatrix: %s",
                    ", ".join(str(p) for p in recordings),
                )
            return
        run = _load(run_dir)
        snapshot = run_dir / "session.json"
        snapshot.write_text(
            json.dumps(session.snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        results = [
            root / path / "result.jsonl"
            for root in [session.data_root]
            if root is not None
            for paths in session.stage_data_paths.values()
            for path in paths.values()
        ]
        run.ended_at = _milliseconds(session.end_at or datetime.now(UTC))
        run.status = (
            ExperimentSessionStatus.aborted
            if aborted
            else ExperimentSessionStatus.completed
        )
        run.files = [str(p) for p in results if p.is_file()] + [str(snapshot)]
        run.recordings = [str(p) for p in recordings]
        _save(run_dir, run)
        self._sync(run_dir, steps)
        self._current = None

    def _sync(self, run_dir: Path, steps: RunEnd | None = None) -> bool:
        """Push what CogMatrix lacks; True when the run is complete and forgotten."""
        try:
            run = _load(run_dir)
        except (OSError, ValueError) as error:
            logger.warning("unreadable CogMatrix record %s: %s", run_dir, error)
            return False
        sent: int | None = None  # recording bytes, counted once the recordings start

        def count_sent(response: httpx.Response) -> None:
            nonlocal sent
            if sent is None or response.request.method != "PUT":
                return
            if response.is_success and steps is not None:
                sent += int(response.request.headers.get("Content-Length", 0))
                steps.progress(UPLOAD_RECORDING, sent)

        try:
            with (
                httpx.Client(
                    timeout=STORAGE_TIMEOUT, event_hooks={"response": [count_sent]}
                ) as storage,
                self._client_factory(run.endpoint, storage) as client,
            ):
                if steps is not None:
                    steps.start(END_SESSION)
                if run.session_id is None:
                    created = client.sessions.create_from_device(
                        run.config,
                        protocol_id=_protocol_id(run.config),
                        code=run.code,
                        started_at=run.started_at,
                        title=run.title,
                        notes=run.notes,
                        device_kind="mxbi",
                    )
                    run.session_id = str(created.id)
                    _save(run_dir, run)
                    logger.info("CogMatrix session %s created", run.session_id)
                session_id = UUID(run.session_id)
                if not run.registered:
                    client.sessions.upload_data(session_id, [], complete=False)
                    run.registered = True
                    _save(run_dir, run)
                if run.ended_at is None:
                    return False
                if not run.ended:
                    client.sessions.end(
                        EndExperimentSessionInput(
                            id=session_id,
                            status=run.status,
                            # CogMatrix needs the end strictly after the start; a run
                            # that died before writing anything ends at its start.
                            ended_at=max(
                                run.ended_at, run.started_at + timedelta(milliseconds=1)
                            ),
                        )
                    )
                    run.ended = True
                    _save(run_dir, run)
                if steps is not None:
                    steps.done(
                        END_SESSION, url=session_url(run.endpoint, run.session_id)
                    )
                    steps.start(UPLOAD_RESULTS, done=0, total=len(run.files))
                repository_id = _repository_id(run.config)
                client.sessions.upload_data(
                    session_id,
                    {_asset_name(file, run_dir): Path(file) for file in run.files},
                    repository_id=repository_id,
                    complete=False,
                )
                recordings = [Path(f) for f in run.recordings]
                for gone in [f for f in recordings if not f.is_file()]:
                    logger.warning("camera recording %s is gone", gone)
                recordings = [f for f in recordings if f.is_file()]
                if steps is not None:
                    steps.progress(UPLOAD_RESULTS, len(run.files))
                    steps.done(UPLOAD_RESULTS)
                    total = sum(f.stat().st_size for f in recordings)
                    steps.start(UPLOAD_RECORDING, done=0, total=total, unit=True)
                    sent = 0
                client.sessions.upload_data(
                    session_id,
                    {f"camera-{f.name}": f for f in recordings},
                    repository_id=repository_id,
                )
                for recording in recordings:
                    recording.unlink()
                if steps is not None:
                    steps.done(UPLOAD_RECORDING)
        except Exception as error:  # noqa: BLE001 - kept for the next start
            logger.warning("CogMatrix sync of %s deferred: %s", run_dir.name, error)
            if steps is not None:
                steps.fail(COGMATRIX_STEPS, _reason(error), retry=True)
            return False
        shutil.rmtree(run_dir)
        logger.info("CogMatrix session %s complete", run.session_id)
        return True


def _end_abandoned(run_dir: Path) -> None:
    """End a run that no process ended as aborted, with the results it wrote."""
    try:
        run = _load(run_dir)
    except OSError, ValueError:
        return
    if run.ended_at is not None:
        return
    results: list[Path] = []
    if run.data_root is not None and run.data_path is not None:
        # <data root>/<animal>/<data path>/<stage>/result.jsonl
        results = sorted(Path(run.data_root).glob(f"*/{run.data_path}/*/result.jsonl"))
    last = max((p.stat().st_mtime for p in results), default=None)
    ended = datetime.fromtimestamp(last, UTC) if last else run.started_at
    run.ended_at = _milliseconds(max(ended, run.started_at))
    run.status = ExperimentSessionStatus.aborted
    run.files = [str(p) for p in results]
    _save(run_dir, run)
    logger.info("run %s never ended; ending it as aborted", run_dir.name)


def _reason(error: Exception) -> str:
    return str(error) or type(error).__name__


def _milliseconds(moment: datetime) -> datetime:
    # CogMatrix timestamps have millisecond precision.
    return moment.replace(microsecond=moment.microsecond // 1000 * 1000)


def _experiment(config: dict[str, JsonValue]) -> dict[str, Any]:
    experiment = config["experiment"]
    assert isinstance(experiment, dict)
    return experiment


def _protocol_id(config: dict[str, JsonValue]) -> UUID:
    return UUID(str(_experiment(config)["protocol"]["id"]))


def _repository_id(config: dict[str, JsonValue]) -> UUID:
    return UUID(str(_experiment(config)["repository"]["id"]))


def _asset_name(file: str, run_dir: Path) -> str:
    path = Path(file)
    if path.parent == run_dir:
        return path.name
    # <data root>/<animal>/<date>/<session>/<stage>/result.jsonl; CogMatrix names are
    # file names without slashes, and the session already fixes date and session.
    animal, _date, _session, stage, name = path.parts[-5:]
    return f"{animal}-{stage}-{name}"


def _save(run_dir: Path, run: PendingRun) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(run_dir / "run.json")


def _load(run_dir: Path) -> PendingRun:
    return PendingRun.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
