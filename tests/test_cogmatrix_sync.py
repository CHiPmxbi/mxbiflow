import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import Any, Self
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import httpx
from cogmatrix import (
    CodeVersion,
    ExperimentSessionStatus,
    SessionDataMismatch,
    SessionFileOutcome,
)
from pydantic import JsonValue
from test_session import make_session

from mxbiflow.core.path import set_base_path
from mxbiflow.infra.cogmatrix_sync import CogMatrixRecorder, PendingRun
from mxbiflow.infra.run_end import (
    END_SESSION,
    UPLOAD_RECORDING,
    UPLOAD_RESULTS,
    RunEnd,
)
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
    """Records calls; `fail` names the calls that raise once, `offline` fails all.

    ``upload_data`` keeps what the session has, so a repeated call uploads only
    the rest; ``uploads`` lists every file it sent. ``mismatch`` names assets
    CogMatrix holds with other content.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail: set[str] = set()
        self.offline = False
        self.endpoints: list[str] = []
        self.sessions = self
        self.arrived: set[str] = set()
        self.mismatch: set[str] = set()
        self.uploads: list[dict[str, Any]] = []

    def __call__(self, endpoint: str, storage: Any = None) -> Self:
        self.storage = storage
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

    def upload_data(
        self,
        session_id: UUID,
        files: Any,
        *,
        repository_id: UUID | None = None,
        complete: bool = True,
    ) -> None:
        named: dict[str, Path] = dict(files)
        self._record(
            "upload_data",
            {
                "session_id": session_id,
                "names": list(named),
                "repository_id": repository_id,
                "complete": complete,
            },
        )
        for name, path in named.items():
            if name in self.arrived or name in self.mismatch:
                continue
            if "upload" in self.fail:
                self.fail.discard("upload")
                raise ConnectionError("upload failed")
            # Sends the file in one storage PUT, as small CogMatrix uploads do.
            request = httpx.Request(
                "PUT", "https://s3.example/x", content=path.read_bytes()
            )
            for hook in self.storage.event_hooks["response"]:
                hook(httpx.Response(200, request=request))
            self.arrived.add(name)
            self.uploads.append({"name": name, "path": path})
        if self.mismatch & set(named):
            files = [
                SimpleNamespace(name=n, outcome=SessionFileOutcome.MISMATCH)
                for n in sorted(self.mismatch & set(named))
            ]
            raise SessionDataMismatch(SimpleNamespace(files=files))  # type: ignore[arg-type]


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

    def run_session(
        self,
        recorder: CogMatrixRecorder,
        recordings: list[Path] | None = None,
        steps: RunEnd | None = None,
    ) -> Session:
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
        recorder.finish(session, recordings=recordings or [], steps=steps)
        return session

    def recordings(self) -> list[Path]:
        files = [self.root / "2026-10-27_09-00-00-000000.mp4"]
        files.append(files[0].with_suffix(".vtt"))
        for file in files:
            file.write_bytes(b"x")
        return files

    def names(self) -> list[str]:
        return [name for name, _ in self.fake.calls]

    def data_calls(self) -> list[dict[str, Any]]:
        return [value for name, value in self.fake.calls if name == "upload_data"]

    def test_records_a_run_and_forgets_it(self) -> None:
        self.run_session(self.recorder())

        self.assertEqual(
            self.names(), ["create", "upload_data", "end", "upload_data", "upload_data"]
        )
        create = self.fake.calls[0][1]
        self.assertEqual(create["protocol_id"], UUID(PROTOCOL))
        self.assertEqual(create["config"], CONFIG)
        self.assertEqual(create["code"], CODE)
        self.assertEqual(self.fake.endpoints[0], "https://matrix.example/api/graphql")
        end = self.fake.calls[2][1]
        self.assertEqual(
            (end.id, end.status), (UUID(int=7), ExperimentSessionStatus.completed)
        )
        register, results, recordings = self.data_calls()
        self.assertEqual(
            register,
            {
                "session_id": UUID(int=7),
                "names": [],
                "repository_id": None,
                "complete": False,
            },
        )
        self.assertEqual(
            results,
            {
                "session_id": UUID(int=7),
                "names": ["animal-1-s-result.jsonl", "session.json"],
                "repository_id": UUID(REPOSITORY),
                "complete": False,
            },
        )
        self.assertEqual((recordings["names"], recordings["complete"]), ([], True))
        self.assertEqual(
            [Path(u["path"]).name for u in self.fake.uploads],
            ["result.jsonl", "session.json"],
        )
        self.assertEqual(list(self.state.iterdir()), [])

    def test_registers_as_uploader_when_the_run_starts(self) -> None:
        session = make_session()
        session.start(self.root / "data")
        self.recorder().start(session)

        self.assertEqual(self.names(), ["create", "upload_data"])
        self.assertEqual(self.data_calls()[0]["complete"], False)

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

        self.assertEqual(
            self.names(), ["create", "upload_data", "end", "upload_data", "upload_data"]
        )
        self.assertEqual(len(self.fake.uploads), 2)
        self.assertEqual(list(self.state.iterdir()), [])

    def test_failed_uploads_are_retried_without_repeating_done_steps(self) -> None:
        self.fake.fail = {"upload"}
        self.run_session(self.recorder())

        self.assertEqual(self.names(), ["create", "upload_data", "end", "upload_data"])
        self.assertEqual(self.fake.uploads, [])
        [run_dir] = list(self.state.iterdir())

        self.recorder().retry_pending()

        self.assertEqual(
            self.names()[4:], ["upload_data", "upload_data"], "end is not repeated"
        )
        self.assertEqual(
            [u["name"] for u in self.fake.uploads],
            ["animal-1-s-result.jsonl", "session.json"],
        )
        self.assertFalse(run_dir.exists())

    def test_a_mismatch_keeps_the_run_and_its_recordings(self) -> None:
        steps = self.steps(Mock())
        recordings = self.recordings()
        self.fake.mismatch = {"session.json"}

        self.run_session(self.recorder(), recordings, steps)

        [run_dir] = list(self.state.iterdir())
        self.assertTrue(all(file.is_file() for file in recordings))
        _, results, _ = steps.steps
        self.assertEqual((results.state, results.retry), ("failed", True))
        self.assertIn("session.json", results.reason or "")

        self.fake.mismatch = set()  # someone invalidated the wrong asset
        self.recorder().retry_pending()

        self.assertFalse(run_dir.exists())
        self.assertFalse(any(file.exists() for file in recordings))

    def test_recordings_are_uploaded_last_and_deleted(self) -> None:
        recordings = self.recordings()
        self.fake.fail = {"upload"}
        self.run_session(self.recorder(), recordings)

        self.assertTrue(all(file.is_file() for file in recordings))

        self.recorder().retry_pending()

        self.assertEqual(
            [u["name"] for u in self.fake.uploads[2:]],
            [
                "camera-2026-10-27_09-00-00-000000.mp4",
                "camera-2026-10-27_09-00-00-000000.vtt",
            ],
        )
        self.assertFalse(any(file.exists() for file in recordings))
        self.assertEqual(list(self.state.iterdir()), [])

    def test_a_recording_removed_by_retention_is_skipped(self) -> None:
        recordings = self.recordings()
        recordings[0].unlink()

        self.run_session(self.recorder(), recordings)

        self.assertEqual(len(self.fake.uploads), 3)
        self.assertEqual(list(self.state.iterdir()), [])

    def test_recordings_of_a_run_not_in_cogmatrix_are_kept(self) -> None:
        recordings = self.recordings()

        self.run_session(self.recorder({**CONFIG, "experiment": None}), recordings)

        self.assertTrue(all(file.is_file() for file in recordings))

    def test_aborted_runs_end_as_aborted(self) -> None:
        recorder = self.recorder()
        session = make_session()
        session.start(self.root / "data")
        recorder.start(session)
        session.end()
        recorder.finish(session, aborted=True)

        end = self.fake.calls[2][1]
        self.assertEqual(end.status, ExperimentSessionStatus.aborted)

    def steps(self, client: Mock) -> RunEnd:
        return RunEnd([END_SESSION, UPLOAD_RESULTS, UPLOAD_RECORDING], client=client)

    def test_finish_reports_each_step(self) -> None:
        client = Mock()
        steps = self.steps(client)
        recordings = self.recordings()
        recordings[0].write_bytes(b"x" * 1000)

        self.run_session(self.recorder(), recordings, steps)

        end, results, recording = steps.steps
        self.assertEqual(end.state, "done")
        self.assertEqual(
            end.url, f"https://matrix.example/sessions?session={UUID(int=7)}"
        )
        self.assertEqual((results.state, results.done, results.total), ("done", 2, 2))
        self.assertEqual(
            (recording.state, recording.done, recording.total, recording.unit),
            ("done", 1001, 1001, "bytes"),
        )
        sent = [call.kwargs for call in client.patch_status.call_args_list]
        self.assertEqual(sent[0]["state"], "finishing")
        self.assertEqual(sent[-1]["steps"][-1].state, "done")

    def test_a_failed_upload_fails_the_steps_left_for_the_next_start(self) -> None:
        steps = self.steps(Mock())
        self.fake.fail = {"upload"}

        self.run_session(self.recorder(), self.recordings(), steps)

        end, results, recording = steps.steps
        self.assertEqual(end.state, "done")
        self.assertEqual(
            (results.state, results.reason, results.retry),
            ("failed", "upload failed", True),
        )
        self.assertEqual(recording.state, "failed")

    def test_a_run_that_never_ended_is_ended_as_aborted_at_the_next_start(self) -> None:
        session = make_session()
        session.start(self.root / "data")
        self.recorder().start(session)
        session.set_current_animal("animal-1")
        path = session.register_stage_data_path(animal="animal-1", stage="s")
        assert session.data_root is not None
        result = session.data_root / path / "result.jsonl"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text('{"trial": 1}\n', encoding="utf-8")
        # The process dies here; the next start completes the run.

        self.recorder().retry_pending()

        self.assertEqual(
            self.names(), ["create", "upload_data", "end", "upload_data", "upload_data"]
        )
        end = self.fake.calls[2][1]
        self.assertEqual(end.status, ExperimentSessionStatus.aborted)
        assert session.start_at is not None
        self.assertGreaterEqual(end.ended_at, session.start_at.replace(microsecond=0))
        self.assertEqual(self.data_calls()[1]["names"], ["animal-1-s-result.jsonl"])
        self.assertEqual(list(self.state.iterdir()), [])

    def test_a_run_that_died_before_any_result_ends_after_its_start(self) -> None:
        session = make_session()
        session.start(self.root / "data")
        self.recorder().start(session)
        # The process dies before any trial; the next start ends it as aborted.

        self.recorder().retry_pending()

        self.assertEqual(
            self.names(), ["create", "upload_data", "end", "upload_data", "upload_data"]
        )
        self.assertEqual(self.data_calls()[-1]["complete"], True)
        end = self.fake.calls[2][1]
        self.assertEqual(end.status, ExperimentSessionStatus.aborted)
        create = self.fake.calls[0][1]
        self.assertGreater(end.ended_at, create["started_at"])
        self.assertEqual(list(self.state.iterdir()), [])

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
