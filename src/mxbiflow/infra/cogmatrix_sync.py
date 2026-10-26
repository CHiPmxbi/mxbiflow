"""Record each run in CogMatrix: a session at start, its data assets at the end (#172).

The node writes as itself with the CogMatrix token cogmoteGO serves on loopback
(``cogmatrix.auth.CogmoteTokenAuth``). The cogmote ``mxbi`` config names the
endpoint, the protocol, the storage repository and the operator; all its
animals are the subjects. Every step is kept in a local record under
``.mxbiflow/state/cogmatrix/`` until CogMatrix has it, so a run that started
offline or whose uploads failed is completed at the next start.
"""

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from cogmatrix import (
    CodeVersion,
    CogMatrixClient,
    EndExperimentSessionInput,
    ExperimentSessionStatus,
)
from cogmatrix.auth import CogmoteTokenAuth
from cogmatrix.git import code_version
from pydantic import BaseModel, Field, JsonValue
from pymotego import Client

from ..core.path import get_base_path, get_internal_state_path
from ..models.session import Session
from ..utils.logger import logger

type ClientFactory = Callable[[str], CogMatrixClient]


def cogmote_client(endpoint: str) -> CogMatrixClient:
    return CogMatrixClient(endpoint, auth=CogmoteTokenAuth(endpoint))


class PendingRun(BaseModel):
    """What CogMatrix still lacks of one run."""

    endpoint: str
    config: dict[str, JsonValue]
    code: CodeVersion
    started_at: datetime
    title: str
    notes: str | None = None
    session_id: str | None = None
    ended_at: datetime | None = None
    status: ExperimentSessionStatus = ExperimentSessionStatus.completed
    ended: bool = False
    files: list[str] = Field(default_factory=list)
    uploaded: list[str] = Field(default_factory=list)


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

    def retry_pending(self) -> None:
        """Complete the runs that earlier starts left unfinished."""
        if not self._state_dir.is_dir():
            return
        for run_dir in sorted(self._state_dir.iterdir()):
            if run_dir.is_dir() and run_dir != self._current:
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
            title=f"{session.mxbi_config.mxbi_id} session {session.session_id}",
            notes=session.note or None,
        )
        run_dir = self._state_dir / str(session.data_path).replace("/", "-")
        _save(run_dir, run)
        self._current = run_dir
        self._sync(run_dir)

    def finish(self, session: Session, *, aborted: bool = False) -> None:
        """End the run's CogMatrix session and upload its results."""
        run_dir = self._current
        if run_dir is None:
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
        _save(run_dir, run)
        self._sync(run_dir)
        self._current = None

    def _sync(self, run_dir: Path) -> bool:
        """Push what CogMatrix lacks; True when the run is complete and forgotten."""
        try:
            run = _load(run_dir)
        except (OSError, ValueError) as error:
            logger.warning("unreadable CogMatrix record %s: %s", run_dir, error)
            return False
        try:
            with self._client_factory(run.endpoint) as client:
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
                if run.ended_at is None:
                    return False
                if not run.ended:
                    client.sessions.end(
                        EndExperimentSessionInput(
                            id=UUID(run.session_id),
                            status=run.status,
                            ended_at=run.ended_at,
                        )
                    )
                    run.ended = True
                    _save(run_dir, run)
                for file in run.files:
                    if file in run.uploaded:
                        continue
                    client.data_assets.upload(
                        file,
                        repository_id=_repository_id(run.config),
                        session_id=UUID(run.session_id),
                        name=_asset_name(file, run_dir),
                    )
                    run.uploaded.append(file)
                    _save(run_dir, run)
        except Exception as error:  # noqa: BLE001 - kept for the next start
            logger.warning("CogMatrix sync of %s deferred: %s", run_dir.name, error)
            return False
        shutil.rmtree(run_dir)
        logger.info("CogMatrix session %s complete", run.session_id)
        return True


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
    # <data root>/<animal>/<date>/<session>/<stage>/result.jsonl
    return "/".join(path.parts[-5:])


def _save(run_dir: Path, run: PendingRun) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(run_dir / "run.json")


def _load(run_dir: Path) -> PendingRun:
    return PendingRun.model_validate_json(
        (run_dir / "run.json").read_text(encoding="utf-8")
    )
