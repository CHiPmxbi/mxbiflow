import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import BaseModel, ValidationError

from mxbiflow.bootstrap import init_session
from mxbiflow.models.animal import Animal, AnimalConfig, StageSnapshot, StageState
from mxbiflow.models.session import (
    Session,
    SessionConfig,
    SessionSnapshotStore,
    SessionState,
)


class ExampleContext(BaseModel):
    value: int


class RecordingSnapshotStore(SessionSnapshotStore):
    def __init__(self) -> None:
        super().__init__(Path("unused.json"))
        self.snapshots: list[dict[str, object]] = []

    def save(self, snapshot: Mapping[str, object]) -> None:
        self.snapshots.append(dict(snapshot))


def make_session() -> Session:
    animal_config = AnimalConfig(
        rfid_id="rfid-1",
        name="animal-1",
        stage="vocalization_discriminate",
        level=2,
    )
    stage = StageState(
        stage_name=animal_config.stage,
        initial_level=animal_config.level,
        level=animal_config.level,
    )
    animal = Animal(
        config=animal_config,
        current_stage_name=stage.stage_name,
        stages={stage.stage_name: stage},
    )
    config = SessionConfig(
        experimenter="tester",
        send_email=True,
        sync_data=True,
        animals=(animal_config,),
    )
    return Session(
        config=config,
        state=SessionState(animals={animal.name: animal}),
    )


class SessionModelTests(unittest.TestCase):
    def test_bootstrap_reuses_animal_config(self) -> None:
        animal_config = AnimalConfig(
            rfid_id="rfid-1",
            name="animal-1",
            stage="vocalization_discriminate",
            level=2,
        )

        with patch(
            "mxbiflow.bootstrap.get_session_counter_path",
            return_value=Path("unused-session-counter.json"),
        ):
            session = init_session(SessionConfig(animals=(animal_config,)))
        animal = session.animals["animal-1"]

        self.assertIs(animal.config, session.config.animals[0])
        self.assertEqual(animal.rfid_id, "rfid-1")
        self.assertEqual(animal.name, "animal-1")

    def test_only_session_exposes_state_mutation_methods(self) -> None:
        session = make_session()
        animal = session.animals["animal-1"]
        stage = animal.current_stage

        for method in (
            "start_animal_session",
            "end_animal_session",
            "set_current_stage",
            "add_trial",
            "level_up",
            "level_down",
            "set_context",
        ):
            self.assertFalse(hasattr(animal, method), method)

        for method in ("add_trial", "level_up", "level_down", "set_context"):
            self.assertFalse(hasattr(stage, method), method)

        self.assertTrue(callable(session.add_trial))
        self.assertTrue(callable(session.level_up))
        self.assertTrue(callable(session.set_stage_context))

    def test_computed_fields_expose_config_and_state(self) -> None:
        session = make_session()
        animal = session.animals["animal-1"]

        self.assertEqual(session.experimenter, "tester")
        self.assertTrue(session.send_email)
        self.assertTrue(session.sync_data)
        self.assertEqual(list(session.animals), ["animal-1"])
        self.assertIsNone(session.current_animal)
        with self.assertRaisesRegex(RuntimeError, "set_current_animal"):
            session.require_current_animal()

        session.set_current_animal("animal-1")
        self.assertIs(session.require_current_animal(), animal)
        self.assertEqual(animal.rfid_id, animal.config.rfid_id)
        self.assertEqual(animal.name, animal.config.name)
        self.assertNotIn("rfid_id", Animal.model_fields)
        self.assertNotIn("name", Animal.model_fields)

        with self.assertRaises(ValidationError):
            session.config.experimenter = "changed"  # type: ignore[misc]
        with self.assertRaises(ValidationError):
            animal.config = AnimalConfig()  # type: ignore[misc]
        with self.assertRaises(ValidationError):
            animal.config.name = "changed"  # type: ignore[misc]

    def test_snapshot_has_only_config_and_state_at_the_top_level(self) -> None:
        session = make_session()

        snapshot = session.snapshot()

        self.assertEqual(set(snapshot), {"config", "state"})
        state = snapshot["state"]
        assert isinstance(state, dict)
        animal = state["animals"]["animal-1"]
        config = snapshot["config"]
        assert isinstance(config, dict)
        self.assertEqual(
            config["animals"][0],
            {
                "rfid_id": "rfid-1",
                "name": "animal-1",
                "stage": "vocalization_discriminate",
                "level": 2,
            },
        )
        self.assertEqual(animal["rfid_id"], "rfid-1")
        self.assertEqual(animal["name"], "animal-1")
        self.assertNotIn("config", animal)
        self.assertIn("stages", animal)
        self.assertNotIn("stages_by_name", animal)
        self.assertIsNone(animal["initial_stage"])
        self.assertIsNone(animal["final_stage"])
        self.assertIn("current_animal_session", animal)
        self.assertNotIn("current_animal_session_state", animal)
        self.assertIn("animal_sessions", animal)
        self.assertNotIn("current_stage", animal)
        self.assertNotIn("sessions", animal)

    def test_stage_snapshots_capture_animal_session_boundaries(self) -> None:
        session = make_session()
        animal = session.animals["animal-1"]
        stage = animal.current_stage
        stage.contexts["stage.before"] = ExampleContext(value=1)

        session.set_current_animal("animal-1")

        initial_stage = animal.initial_stage
        assert initial_stage is not None
        self.assertEqual(initial_stage.stage_name, stage.stage_name)
        self.assertEqual(initial_stage.stage_trial_id, 0)
        self.assertEqual(initial_stage.level, 2)
        self.assertEqual(
            initial_stage.get_context("stage.before", ExampleContext),
            ExampleContext(value=1),
        )
        with self.assertRaises(ValidationError):
            initial_stage.level = 3  # type: ignore[misc]

        context = stage.get_context("stage.before", ExampleContext)
        assert context is not None
        context.value = 2
        session.add_trial()
        session.level_up()
        session.clear_current_animal()

        self.assertIs(animal.initial_stage, initial_stage)
        self.assertEqual(initial_stage.level, 2)
        self.assertEqual(
            initial_stage.get_context("stage.before", ExampleContext),
            ExampleContext(value=1),
        )

        final_stage = animal.final_stage
        assert final_stage is not None
        self.assertEqual(final_stage.stage_trial_id, 1)
        self.assertEqual(final_stage.level, 3)
        self.assertEqual(
            final_stage.get_context("stage.before", ExampleContext),
            ExampleContext(value=2),
        )

        session.level_up(animal="animal-1", stage=stage.stage_name)
        self.assertEqual(final_stage.level, 3)

        session.set_current_animal("animal-1")
        self.assertIsNone(animal.final_stage)
        session.set_current_stage(
            StageState(stage_name="second", initial_level=5, level=5)
        )
        session.clear_current_animal()

        self.assertIs(animal.initial_stage, initial_stage)
        assert animal.final_stage is not None
        self.assertEqual(animal.final_stage.stage_name, "second")
        self.assertEqual(animal.final_stage.level, 5)

        snapshot = session.snapshot()
        snapshot_state = snapshot["state"]
        assert isinstance(snapshot_state, dict)
        snapshot_animal = snapshot_state["animals"]["animal-1"]
        self.assertEqual(snapshot_animal["initial_stage"]["level"], 2)
        self.assertEqual(snapshot_animal["final_stage"]["stage_name"], "second")

    def test_stage_snapshot_requires_complete_stage_data(self) -> None:
        with self.assertRaises(ValidationError):
            StageSnapshot(stage_name="stage")  # type: ignore[call-arg]

    def test_lifecycle_and_context_changes_are_checkpointed(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            store = RecordingSnapshotStore()
            session.set_snapshot_store(store)

            session.start(Path(directory) / "data")
            session.set_current_scene("idle")
            session.set_current_animal("animal-1")
            session.add_trial()
            session.set_context("session.summary", ExampleContext(value=1))
            session.set_animal_context("animal.summary", ExampleContext(value=2))
            session.set_stage_context("stage.result", ExampleContext(value=3))
            session.level_up()
            session.clear_current_animal()
            session.end()

            self.assertEqual(len(store.snapshots), 10)
            self.assertIsNone(session.current_animal)
            self.assertIsNotNone(session.end_at)

            animal = session.animals["animal-1"]
            self.assertEqual(animal.trial_id, 1)
            self.assertEqual(animal.current_stage.level, 3)
            self.assertEqual(animal.current_stage.level_trial_id, 0)
            self.assertEqual(len(animal.animal_sessions), 1)
            self.assertIsNotNone(animal.animal_sessions[0].end_at)

            self.assertEqual(
                session.get_context("session.summary", ExampleContext),
                ExampleContext(value=1),
            )
            self.assertEqual(
                animal.get_context("animal.summary", ExampleContext),
                ExampleContext(value=2),
            )
            self.assertEqual(
                animal.current_stage.get_context("stage.result", ExampleContext),
                ExampleContext(value=3),
            )

            stage_context = store.snapshots[-1]["state"]
            assert isinstance(stage_context, dict)
            self.assertEqual(
                stage_context["animals"]["animal-1"]["stages"][
                    "vocalization_discriminate"
                ]["contexts"]["stage.result"],
                {"value": 3},
            )

    def test_default_snapshot_store_writes_session_json(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            session.start(Path(directory) / "data")
            session.set_current_animal("animal-1")
            session.add_trial()

            data_path = session.absolute_data_path
            assert data_path is not None
            payload = json.loads(
                (data_path / "session.json").read_text(encoding="utf-8")
            )

            self.assertEqual(set(payload), {"config", "state"})
            self.assertEqual(payload["state"]["current_animal_name"], "animal-1")
            self.assertEqual(payload["state"]["animals"]["animal-1"]["trial_id"], 1)

    def test_invalid_context_access_and_state_transitions_fail_explicitly(self) -> None:
        session = make_session()

        with self.assertRaisesRegex(ValueError, "context key"):
            session.set_context("", ExampleContext(value=1))
        with self.assertRaisesRegex(RuntimeError, "set_current_animal"):
            session.add_trial()
        with self.assertRaisesRegex(ValueError, "not found"):
            session.set_current_animal("unknown")

    def test_failed_and_unchanged_mutations_do_not_checkpoint(self) -> None:
        session = make_session()
        store = RecordingSnapshotStore()
        session.set_snapshot_store(store)

        session.set_current_scene("idle")
        session.set_current_scene("idle")
        self.assertEqual(len(store.snapshots), 1)

        with self.assertRaisesRegex(RuntimeError, "set_current_animal"):
            session.add_trial()
        with self.assertRaisesRegex(ValueError, "not found"):
            session.set_stage_context(
                "stage.result",
                ExampleContext(value=1),
                animal="unknown",
            )
        self.assertEqual(len(store.snapshots), 1)

        session.set_current_animal("animal-1")
        stage = session.require_current_animal().current_stage
        stage.level = 0
        stage.level_trial_id = 4
        checkpoint_count = len(store.snapshots)

        with self.assertRaisesRegex(ValueError, "less than 0"):
            session.level_down()

        self.assertEqual(stage.level, 0)
        self.assertEqual(stage.level_trial_id, 4)
        self.assertEqual(len(store.snapshots), checkpoint_count)

    def test_departed_animal_can_still_be_settled_explicitly(self) -> None:
        session = make_session()
        session.set_current_animal("animal-1")
        session.clear_current_animal()

        session.set_stage_context(
            "stage.result",
            ExampleContext(value=4),
            animal="animal-1",
            stage="vocalization_discriminate",
        )
        level = session.level_up(
            animal="animal-1",
            stage="vocalization_discriminate",
        )

        self.assertEqual(level, 3)
        self.assertEqual(
            session.animals["animal-1"].current_stage.get_context(
                "stage.result",
                ExampleContext,
            ),
            ExampleContext(value=4),
        )


if __name__ == "__main__":
    unittest.main()
