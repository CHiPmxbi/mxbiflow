import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from mxbiflow.driver import MXBIModel
from mxbiflow.infra.data_logger import DataLogger, DataLoggerType
from mxbiflow.models.animal import Animal, AnimalConfig, StageState
from mxbiflow.models.session import (
    RuntimeStateStore,
    Session,
    SessionConfig,
    SessionState,
)


def make_session(*, session_id: int = 7) -> Session:
    animal_config = AnimalConfig(
        rfid_id="rfid-1",
        name="animal-1",
        stage="stage-1",
    )
    stage = StageState(stage_name="stage-1")
    return Session(
        config=SessionConfig(
            unknown_animal_as=animal_config.name,
            animals=(animal_config,),
        ),
        mxbi_config=MXBIModel(
            backup_source_root_id="source",
            backup_destination_root_id="destination",
        ),
        state=SessionState(
            session_id=session_id,
            animals={
                animal_config.name: Animal(
                    config=animal_config,
                    current_stage_name=stage.stage_name,
                    stages={stage.stage_name: stage},
                )
            },
        ),
    )


class SessionDataPathTests(unittest.TestCase):
    def test_start_sets_relative_session_data_path(self) -> None:
        with TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            session = make_session(session_id=0)
            session.set_session_store(
                RuntimeStateStore(Path(directory) / "state" / "runtime.json")
            )

            session.start(data_root)

            assert session.start_at is not None
            self.assertEqual(session.session_id, 1)
            self.assertEqual(
                session.data_path,
                Path(session.start_at.strftime("%Y%m%d")) / str(session.session_id),
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

            payload = session.snapshot()

            assert session.data_path is not None
            state = payload["state"]
            assert isinstance(state, dict)
            self.assertEqual(state["data_path"], str(session.data_path))

    def test_derived_paths_keep_the_path_created_at_session_start(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")
            animal_path = session.animal_data_path("animal-1")
            screenshot_path = session.screenshot_data_path

            session.state.session_id += 1

            self.assertEqual(session.animal_data_path("animal-1"), animal_path)
            self.assertEqual(session.screenshot_data_path, screenshot_path)


class DataLoggerTests(unittest.TestCase):
    def test_logger_uses_animal_session_and_stage_path(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")

            json_logger = DataLogger(
                session=session,
                animal="animal-1",
                stage="stage-1",
                filename="summary",
                type=DataLoggerType.JSON,
            )
            jsonl_logger = DataLogger(
                session=session,
                animal="animal-1",
                stage="stage-1",
            )

            self.assertEqual(session.stage_data_paths, {})

            self.assertEqual(
                json_logger.path,
                session.absolute_animal_data_path("animal-1")
                / "stage-1"
                / "summary.json",
            )
            self.assertEqual(
                jsonl_logger.path,
                session.absolute_animal_data_path("animal-1")
                / "stage-1"
                / "result.jsonl",
            )

            json_logger.save({"session_id": session.session_id})
            jsonl_logger.save({"trial_id": 1})

            self.assertEqual(
                json.loads(json_logger.path.read_text(encoding="utf-8")),
                {"session_id": session.session_id},
            )
            self.assertEqual(
                jsonl_logger.path.read_text(encoding="utf-8"),
                '{"trial_id": 1}\n',
            )
            self.assertEqual(
                session.stage_data_paths,
                {
                    "stage-1": {
                        "animal-1": session.animal_data_path("animal-1") / "stage-1"
                    }
                },
            )

    def test_stage_path_is_registered_once_after_successful_save(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")
            logger = DataLogger(
                session=session,
                animal="animal-1",
                stage="stage-1",
            )
            snapshot_store = Mock()
            session.set_snapshot_store(snapshot_store)

            logger.save({"trial_id": 1})
            logger.save({"trial_id": 2})

            snapshot_store.save.assert_called_once()

    def test_failed_save_does_not_register_stage_path(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")
            logger = DataLogger(
                session=session,
                animal="animal-1",
                stage="stage-1",
            )

            with self.assertRaises(TypeError):
                logger.save({"invalid": object()})

            self.assertEqual(session.stage_data_paths, {})

    def test_csv_direct_save_registers_stage_path(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")
            logger = DataLogger(
                session=session,
                animal="animal-1",
                stage="stage-2",
                type=DataLoggerType.CSV,
            )

            logger.save_csv_row({"trial_id": 1})

            self.assertEqual(
                session.stage_data_paths["stage-2"]["animal-1"],
                session.animal_data_path("animal-1") / "stage-2",
            )

    def test_stage_paths_are_serialized_as_relative_strings(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")
            DataLogger(
                session=session,
                animal="animal-1",
                stage="stage-1",
            ).save({"trial_id": 1})

            state = session.snapshot()["state"]
            assert isinstance(state, dict)
            self.assertEqual(
                state["stage_data_paths"],
                {
                    "stage-1": {
                        "animal-1": str(
                            session.animal_data_path("animal-1") / "stage-1"
                        )
                    }
                },
            )

    def test_unstarted_session_is_rejected_without_creating_directories(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            session = make_session()

            with self.assertRaisesRegex(RuntimeError, "Session.start"):
                DataLogger(session=session, animal="animal-1", stage="stage-1")

            self.assertFalse(data_root.exists())


if __name__ == "__main__":
    unittest.main()
