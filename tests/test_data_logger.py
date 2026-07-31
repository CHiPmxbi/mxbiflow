import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mxbiflow.infra.data_logger import DataLogger, DataLoggerType
from mxbiflow.models.session import DailySessionIdStore, Session


def make_session(*, session_id: int = 7) -> Session:
    return Session(session_id=session_id, note="")


class SessionDataPathTests(unittest.TestCase):
    def test_start_sets_relative_session_data_path(self) -> None:
        with TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            session = make_session(session_id=0)
            session.set_session_store(
                DailySessionIdStore(Path(directory) / "state" / "counter.json")
            )

            session.start(data_root)

            assert session.start_at is not None
            self.assertEqual(session.session_id, 1)
            self.assertEqual(
                session.data_path,
                Path(session.start_at.strftime("%Y%m%d"))
                / str(session.session_id),
            )
            assert session.data_path is not None
            self.assertFalse(session.data_path.is_absolute())
            self.assertEqual(
                session.absolute_data_path,
                data_root.resolve() / session.data_path,
            )

    def test_json_dump_contains_session_data_path_as_string(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")

            payload = session.model_dump(mode="json")

            assert session.data_path is not None
            self.assertEqual(payload["data_path"], str(session.data_path))


class DataLoggerTests(unittest.TestCase):
    def test_loggers_share_the_session_data_path(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")
            assert session.data_path is not None

            session_logger = DataLogger(
                session=session,
                filename="session",
                type=DataLoggerType.JSON,
            )
            animal_logger = DataLogger(
                session=session,
                filename="trials",
                monkey="animal-1",
            )

            self.assertEqual(
                session_logger.path,
                session.absolute_data_path / "session.json",
            )
            self.assertEqual(
                animal_logger.path,
                session.absolute_data_path / "animal-1" / "trials.jsonl",
            )

            session_logger.save({"session_id": session.session_id})
            animal_logger.save({"trial_id": 1})

            self.assertEqual(
                json.loads(session_logger.path.read_text(encoding="utf-8")),
                {"session_id": session.session_id},
            )
            self.assertEqual(
                animal_logger.path.read_text(encoding="utf-8"),
                '{"trial_id": 1}\n',
            )

    def test_unstarted_session_is_rejected_without_creating_directories(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            session = make_session()

            with self.assertRaisesRegex(RuntimeError, "Session.start"):
                DataLogger(session=session, filename="session")

            self.assertFalse(data_root.exists())


if __name__ == "__main__":
    unittest.main()
