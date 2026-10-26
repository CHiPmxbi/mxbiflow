import json
import tempfile
import unittest
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from unittest.mock import patch
from uuid import UUID, uuid4

from cogmatrix import CodeVersion, ExperimentSessionStatus
from pydantic import JsonValue
from test_session import make_session

from mxbiflow.core.path import set_base_path
from mxbiflow.infra.cogmatrix_sync import CogMatrixRecorder, PendingRun
from mxbiflow.models.session import Session

PROTOCOL = "44444444-4444-4444-8444-444444444444"
REPOSITORY = "55555555-5555-4555-8555-555555555555"
CONFIG: dict[str, JsonValue] = {
    "device": {"code": "mxbi3", "name": "mxbi3", "kind": "mxbi"},
    "animal": None,
    "experiment": {
        "protocol": {"id": PROTOCOL, "name": "Habituation"},
        "repository": {"id": REPOSITORY, "name": "Lab S3"},
        "animals": [{"id": str(uuid4()), "name": "animal-1", "stage": "s", "level": 0}],
    },
    "operator": {"issuer": "https://id.example", "subject": "s-1", "name": "R"},
    "cogmatrix": {"url": "https://matrix.example/api/graphql"},
}
CODE = CodeVersion(
    repository="https://git.example/task.git", revision="0" * 40, dirty=False
)


class FakeCogMatrix:
    """Records calls; `fail` names the calls that raise once, `offline` fails all."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail: set[str] = set()
        self.offline = False
        self.endpoints: list[str] = []
        self.sessions = self
        self.data_assets = self

    def __call__(self, endpoint: str) -> Self:
        self.endpoints.append(endpoint)
        return self

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass

    def _record(self, name: str, value: Any) -> None:
        if self.offline:
            raise ConnectionError("CogMatrix is unreachable")
        if name in self.fail:
            self.fail.discard(name)
            raise ConnectionError(f"{name} failed")
        self.calls.append((name, value))

    def create_from_device(self, config: Any, **kwargs: Any) -> Any:
        self._record("create", {"config": config, **kwargs})
        return type("Created", (), {"id": UUID(int=7)})()

    def end(self, input: Any) -> None:
        self._record("end", input)

    def upload(self, path: str, **kwargs: Any) -> None:
        self._record("upload", {"path": path, **kwargs})


class CogMatrixRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        set_base_path(self.root)
        self.state = self.root / "state"
        self.fake = FakeCogMatrix()
        code = patch("mxbiflow.infra.cogmatrix_sync.code_version", return_value=CODE)
        code.start()
        self.addCleanup(code.stop)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def recorder(self, config: dict[str, JsonValue] = CONFIG) -> CogMatrixRecorder:
        return CogMatrixRecorder(
            state_dir=self.state,
            client_factory=self.fake,  # type: ignore[arg-type]
            read_config=lambda: config,
        )

    def run_session(self, recorder: CogMatrixRecorder) -> Session:
        session = make_session()
        session.start(self.root / "data")
        recorder.start(session)
        session.set_current_animal("animal-1")
        path = session.register_stage_data_path(animal="animal-1", stage="s")
        assert session.data_root is not None
        result = session.data_root / path / "result.jsonl"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text('{"trial": 1}\n', encoding="utf-8")
        session.end()
        recorder.finish(session)
        return session

    def names(self) -> list[str]:
        return [name for name, _ in self.fake.calls]

    def test_records_a_run_and_forgets_it(self) -> None:
        self.run_session(self.recorder())

        self.assertEqual(self.names(), ["create", "end", "upload", "upload"])
        create = self.fake.calls[0][1]
        self.assertEqual(create["protocol_id"], UUID(PROTOCOL))
        self.assertEqual(create["config"], CONFIG)
        self.assertEqual(create["code"], CODE)
        self.assertEqual(self.fake.endpoints[0], "https://matrix.example/api/graphql")
        end = self.fake.calls[1][1]
        self.assertEqual(
            (end.id, end.status), (UUID(int=7), ExperimentSessionStatus.completed)
        )
        uploads = [value for name, value in self.fake.calls if name == "upload"]
        self.assertEqual(
            {Path(u["path"]).name for u in uploads}, {"result.jsonl", "session.json"}
        )
        self.assertTrue(all(u["session_id"] == UUID(int=7) for u in uploads))
        self.assertTrue(all(u["repository_id"] == UUID(REPOSITORY) for u in uploads))
        self.assertEqual(
            {u["name"] for u in uploads}, {"animal-1-s-result.jsonl", "session.json"}
        )
        self.assertEqual(list(self.state.iterdir()), [])

    def test_an_offline_run_is_completed_at_the_next_start(self) -> None:
        self.fake.offline = True
        self.run_session(self.recorder())

        self.assertEqual(self.names(), [])
        [run_dir] = list(self.state.iterdir())
        pending = PendingRun.model_validate_json((run_dir / "run.json").read_text())
        self.assertIsNone(pending.session_id)
        self.assertIsNotNone(pending.ended_at)

        self.fake.offline = False
        self.recorder().retry_pending()

        self.assertEqual(self.names(), ["create", "end", "upload", "upload"])
        self.assertEqual(list(self.state.iterdir()), [])

    def test_failed_uploads_are_retried_without_repeating_done_steps(self) -> None:
        self.fake.fail = {"upload"}
        self.run_session(self.recorder())

        self.assertEqual(self.names(), ["create", "end"])
        [run_dir] = list(self.state.iterdir())

        self.recorder().retry_pending()

        self.assertEqual(self.names(), ["create", "end", "upload", "upload"])
        self.assertFalse(run_dir.exists())

    def test_aborted_runs_end_as_aborted(self) -> None:
        recorder = self.recorder()
        session = make_session()
        session.start(self.root / "data")
        recorder.start(session)
        session.end()
        recorder.finish(session, aborted=True)

        end = self.fake.calls[1][1]
        self.assertEqual(end.status, ExperimentSessionStatus.aborted)

    def test_without_an_experiment_config_nothing_is_recorded(self) -> None:
        config = {**CONFIG, "experiment": None}
        self.run_session(self.recorder(config))

        self.assertEqual(self.names(), [])
        self.assertFalse(self.state.exists())

    def test_the_snapshot_is_the_session_at_the_end(self) -> None:
        self.fake.fail = {"upload"}
        session = self.run_session(self.recorder())

        [run_dir] = list(self.state.iterdir())
        snapshot = json.loads((run_dir / "session.json").read_text())
        self.assertEqual(snapshot, json.loads(json.dumps(session.snapshot())))


if __name__ == "__main__":
    unittest.main()
