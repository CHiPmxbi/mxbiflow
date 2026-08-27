import json
import unittest
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import BaseModel, ValidationError

from mxbiflow.bootstrap import init_session
from mxbiflow.core.config_store import ConfigStore
from mxbiflow.driver import MXBIModel
from mxbiflow.models.animal import Animal, AnimalConfig, StageSnapshot, StageState
from mxbiflow.models.session import (
    EmailRuntimeState,
    RuntimeState,
    RuntimeStateStore,
    Session,
    SessionConfig,
    SessionRuntimeState,
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


class RecordingConfigStore:
    def __init__(self, config: SessionConfig) -> None:
        self.value = config
        self.saved: list[SessionConfig] = []

    def save(self, data: SessionConfig | None = None) -> None:
        if data is None:
            return
        self.value = data
        self.saved.append(data)


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
        unknown_animal_as=animal_config.name,
        animals=(animal_config,),
    )
    return Session(
        config=config,
        mxbi_config=MXBIModel(
            backup_source_root_id="source",
            backup_destination_root_id="destination",
        ),
        state=SessionState(animals={animal.name: animal}),
    )


class RuntimeStateStoreTests(unittest.TestCase):
    def test_domains_share_one_file_without_overwriting_each_other(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "runtime.json"
            store = RuntimeStateStore(path)

            self.assertEqual(store.session_id, 1)
            store.save_email_message_id("message-1")
            self.assertEqual(store.session_id, 2)

            state = RuntimeState.model_validate_json(path.read_text(encoding="utf-8"))
            self.assertEqual(state.session.last_session_id, 2)
            self.assertEqual(state.email.message_id, "message-1")
            self.assertEqual(RuntimeStateStore(path).email_message_id, "message-1")

    def test_session_counter_resets_on_a_new_day(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            path.write_text(
                RuntimeState(
                    session=SessionRuntimeState(
                        day="2000-01-01",
                        last_session_id=9,
                    ),
                    email=EmailRuntimeState(message_id="message-1"),
                ).model_dump_json(),
                encoding="utf-8",
            )

            store = RuntimeStateStore(path)

            self.assertEqual(store.session_id, 1)
            self.assertEqual(store.email_message_id, "message-1")

    def test_missing_or_invalid_file_uses_default_state(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            store = RuntimeStateStore(path)

            self.assertEqual(store.email_message_id, "")

            path.write_text("invalid", encoding="utf-8")
            self.assertEqual(store.email_message_id, "")
            self.assertEqual(store.session_id, 1)

    def test_legacy_state_files_are_ignored(self) -> None:
        with TemporaryDirectory() as directory:
            state_dir = Path(directory) / "state"
            state_dir.mkdir()
            (state_dir / "session_counter.json").write_text(
                '{"day":"2099-01-01","last_session_id":99}',
                encoding="utf-8",
            )
            (state_dir / "email_state.json").write_text(
                '{"message_id":"legacy-message"}',
                encoding="utf-8",
            )
            runtime_path = state_dir / "runtime.json"
            store = RuntimeStateStore(runtime_path)

            self.assertEqual(store.email_message_id, "")
            self.assertEqual(store.session_id, 1)

            state = RuntimeState.model_validate_json(
                runtime_path.read_text(encoding="utf-8")
            )
            self.assertEqual(state.session.last_session_id, 1)
            self.assertEqual(state.email.message_id, "")


class SessionModelTests(unittest.TestCase):
    def test_session_config_without_animals_allows_empty_unknown_mapping(
        self,
    ) -> None:
        config = SessionConfig()

        self.assertEqual(config.unknown_animal_as, "")

    def test_session_config_requires_valid_unknown_animal_mapping(self) -> None:
        animal = AnimalConfig(name="animal-1")

        with self.assertRaisesRegex(ValidationError, "unknown_animal_as must be set"):
            SessionConfig(animals=(animal,))
        with self.assertRaisesRegex(
            ValidationError,
            "unknown_animal_as must match a configured animal name",
        ):
            SessionConfig(unknown_animal_as="missing", animals=(animal,))

        config = SessionConfig(
            unknown_animal_as=animal.name,
            animals=(animal,),
        )
        self.assertEqual(config.unknown_animal_as, animal.name)

    def test_session_config_with_animals_returns_validated_copy(self) -> None:
        animal = AnimalConfig(name="animal-1")
        replacement = animal.with_progress(stage="stage_b", level=3)
        config = SessionConfig(
            experimenter="tester",
            send_email=True,
            sync_data=True,
            note="note",
            default_scene="default",
            unknown_animal_as=animal.name,
            fault_fallback="fallback",
            hide_cursor=True,
            fullscreen=True,
            animals=(animal,),
        )

        updated = config.with_animals((replacement,))

        self.assertEqual(updated.animals, (replacement,))
        self.assertEqual(updated.experimenter, config.experimenter)
        self.assertEqual(updated.reward_type, config.reward_type)
        self.assertEqual(updated.send_email, config.send_email)
        self.assertEqual(updated.sync_data, config.sync_data)
        self.assertEqual(updated.note, config.note)
        self.assertEqual(updated.default_scene, config.default_scene)
        self.assertEqual(updated.unknown_animal_as, config.unknown_animal_as)
        self.assertEqual(updated.fault_fallback, config.fault_fallback)
        self.assertEqual(updated.hide_cursor, config.hide_cursor)
        self.assertEqual(updated.fullscreen, config.fullscreen)
        self.assertEqual(config.animals, (animal,))

        with self.assertRaisesRegex(
            ValidationError,
            "unknown_animal_as must match",
        ):
            config.with_animals((AnimalConfig(name="animal-2"),))

    def test_legacy_unknown_animal_field_does_not_configure_mapping(self) -> None:
        animal = AnimalConfig(name="animal-1")

        with self.assertRaisesRegex(ValidationError, "unknown_animal_as must be set"):
            SessionConfig.model_validate(
                {
                    "unknown_animal_fallback_animal": animal.name,
                    "animals": [animal],
                }
            )

    def test_animal_config_stage_order_roundtrip(self) -> None:
        config = AnimalConfig(
            name="animal-1",
            stage="stage_a",
            stage_order=("stage_a", "stage_b"),
        )

        parsed = AnimalConfig.model_validate_json(config.model_dump_json())

        self.assertEqual(parsed.stage_order, ("stage_a", "stage_b"))
        self.assertEqual(AnimalConfig().stage_order, ())

    def test_animal_config_with_progress_returns_validated_copy(self) -> None:
        config = AnimalConfig(
            rfid_id="rfid-1",
            name="animal-1",
            stage="stage_a",
            level=2,
            stage_order=("stage_a", "stage_b"),
        )

        updated = config.with_progress(stage="stage_b", level=3)

        self.assertEqual(updated.stage, "stage_b")
        self.assertEqual(updated.level, 3)
        self.assertEqual(updated.rfid_id, config.rfid_id)
        self.assertEqual(updated.name, config.name)
        self.assertEqual(updated.stage_order, config.stage_order)
        self.assertEqual(config.stage, "stage_a")
        self.assertEqual(config.level, 2)

        with self.assertRaises(ValidationError):
            config.with_progress(stage="stage_b", level=-1)

    def test_bootstrap_reuses_animal_config(self) -> None:
        animal_config = AnimalConfig(
            rfid_id="rfid-1",
            name="animal-1",
            stage="vocalization_discriminate",
            level=2,
        )
        mxbi_config = MXBIModel(
            backup_source_root_id="source",
            backup_destination_root_id="destination",
        )

        with patch(
            "mxbiflow.bootstrap.get_runtime_state_path",
            return_value=Path("unused-runtime.json"),
        ):
            session = init_session(
                SessionConfig(
                    unknown_animal_as=animal_config.name,
                    animals=(animal_config,),
                ),
                mxbi_config,
            )
        animal = session.animals["animal-1"]

        self.assertIs(animal.config, session.config.animals[0])
        self.assertIs(session.mxbi_config, mxbi_config)
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

    def test_properties_expose_config_and_state(self) -> None:
        session = make_session()
        animal = session.animals["animal-1"]

        self.assertFalse(Session.model_computed_fields)
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

        self.assertEqual(set(session.model_dump()), {"config", "state"})
        snapshot = session.snapshot()

        self.assertEqual(set(snapshot), {"config", "state"})
        state = snapshot["state"]
        assert isinstance(state, dict)
        animal = state["animals"]["animal-1"]
        config = snapshot["config"]
        assert isinstance(config, dict)
        self.assertEqual(config["unknown_animal_as"], "animal-1")
        self.assertNotIn("unknown_animal_fallback", config)
        self.assertNotIn("unknown_animal_fallback_animal", config)
        self.assertEqual(
            config["animals"][0],
            {
                "rfid_id": "rfid-1",
                "name": "animal-1",
                "stage": "vocalization_discriminate",
                "level": 2,
                "stage_order": [],
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

            data_path = session.absolute_animal_data_path("animal-1")
            payload = json.loads(
                (data_path / "session.json").read_text(encoding="utf-8")
            )

            self.assertEqual(set(payload), {"config", "state"})
            self.assertEqual(payload["state"]["current_animal_name"], "animal-1")
            self.assertEqual(payload["state"]["animals"]["animal-1"]["trial_id"], 1)
            self.assertEqual(
                session.participant_data_paths,
                (session.animal_data_path("animal-1"),),
            )
            absolute_data_path = session.absolute_data_path
            assert absolute_data_path is not None
            self.assertFalse((absolute_data_path / "session.json").exists())

    def test_participant_snapshots_are_synchronized(self) -> None:
        with TemporaryDirectory() as directory:
            session = make_session()
            second_config = AnimalConfig(
                rfid_id="rfid-2",
                name="animal-2",
                stage="vocalization_discriminate",
            )
            second_stage = StageState(
                stage_name=second_config.stage,
                initial_level=second_config.level,
                level=second_config.level,
            )
            session.config = session.config.model_copy(
                update={"animals": (*session.config.animals, second_config)}
            )
            session.state.animals[second_config.name] = Animal(
                config=second_config,
                current_stage_name=second_stage.stage_name,
                stages={second_stage.stage_name: second_stage},
            )
            session.start(Path(directory) / "data")

            session.set_current_animal("animal-1")
            session.add_trial()
            session.set_current_animal("animal-2")
            session.add_trial()
            session.end()

            first_path = session.absolute_animal_data_path("animal-1")
            second_path = session.absolute_animal_data_path("animal-2")
            first = json.loads((first_path / "session.json").read_text())
            second = json.loads((second_path / "session.json").read_text())

            self.assertEqual(first, second)
            self.assertEqual(first["state"]["animals"]["animal-1"]["trial_id"], 1)
            self.assertEqual(first["state"]["animals"]["animal-2"]["trial_id"], 1)
            self.assertEqual(
                session.participant_data_paths,
                (
                    session.animal_data_path("animal-1"),
                    session.animal_data_path("animal-2"),
                ),
            )

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

    def test_current_stage_progress_is_persisted_across_sessions(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "config" / "session.json"
            animal_config = AnimalConfig(
                rfid_id="rfid-1",
                name="animal-1",
                stage="stage_a",
                level=2,
                stage_order=("stage_a", "stage_b"),
            )
            other_config = AnimalConfig(name="animal-2", stage="other", level=4)
            config = SessionConfig(
                unknown_animal_as=animal_config.name,
                animals=(animal_config, other_config),
            )
            config_store = ConfigStore(config_path, SessionConfig)
            config_store.save(config)
            mxbi_config = MXBIModel(
                backup_source_root_id="source",
                backup_destination_root_id="destination",
            )

            with patch(
                "mxbiflow.bootstrap.get_runtime_state_path",
                return_value=Path(directory) / "runtime.json",
            ):
                session = init_session(
                    config_store.value,
                    mxbi_config,
                    config_store=config_store,
                )
                session.set_current_animal("animal-1")
                session.level_up()

                persisted = ConfigStore(config_path, SessionConfig).value
                self.assertEqual(persisted.animals[0].stage, "stage_a")
                self.assertEqual(persisted.animals[0].level, 3)
                self.assertEqual(persisted.animals[0].rfid_id, "rfid-1")
                self.assertEqual(persisted.animals[0].stage_order, ("stage_a", "stage_b"))
                self.assertEqual(persisted.animals[1], other_config)

                session.go_next_stage()
                session.level_up()

                reloaded_store = ConfigStore(config_path, SessionConfig)
                restarted = init_session(
                    reloaded_store.value,
                    mxbi_config,
                    config_store=reloaded_store,
                )

            restarted_animal = restarted.animals["animal-1"]
            self.assertEqual(restarted_animal.current_stage_name, "stage_b")
            self.assertEqual(restarted_animal.current_stage.level, 1)

    def test_only_successful_current_progress_changes_are_persisted(self) -> None:
        session = make_session()
        store = RecordingConfigStore(session.config)
        session.set_config_store(store)
        session.set_current_animal("animal-1")
        animal = session.require_current_animal()
        animal.stages["historical"] = StageState(
            stage_name="historical",
            initial_level=4,
            level=4,
        )

        session.level_up(animal="animal-1", stage="historical")
        self.assertEqual(store.saved, [])

        animal.current_stage.level = 0
        with self.assertRaisesRegex(ValueError, "less than 0"):
            session.level_down()
        self.assertEqual(store.saved, [])

        session.level_up()
        self.assertEqual(len(store.saved), 1)
        self.assertEqual(store.value.animals[0].stage, animal.current_stage_name)
        self.assertEqual(store.value.animals[0].level, 1)


class StageNavigationTests(unittest.TestCase):
    @staticmethod
    def _make_session(
        *,
        stage: str = "stage_a",
        stage_order: tuple[str, ...] = (),
    ) -> tuple[Session, Animal]:
        animal_config = AnimalConfig(
            name="animal-1",
            stage=stage,
            stage_order=stage_order,
        )
        animal = Animal(
            config=animal_config,
            current_stage_name=stage,
            stages={stage: StageState(stage_name=stage)},
        )
        session = Session(
            config=SessionConfig(
                unknown_animal_as=animal_config.name,
                animals=(animal_config,),
            ),
            mxbi_config=MXBIModel(
                backup_source_root_id="source",
                backup_destination_root_id="destination",
            ),
            state=SessionState(animals={animal.name: animal}),
        )
        return session, animal

    def test_adjacent_stages_are_none_without_current_animal(self) -> None:
        session, _animal = self._make_session(
            stage_order=("stage_a", "stage_b"),
        )

        self.assertIsNone(session.next_stage)
        self.assertIsNone(session.prev_stage)
        self.assertIsNone(session.go_next_stage())
        self.assertIsNone(session.go_prev_stage())

    def test_adjacent_stages_are_none_when_stage_order_is_empty(self) -> None:
        session, animal = self._make_session()
        session.set_current_animal("animal-1")

        self.assertIsNone(session.next_stage)
        self.assertIsNone(session.prev_stage)
        self.assertIsNone(session.go_next_stage())
        self.assertIsNone(session.go_prev_stage())
        self.assertEqual(animal.current_stage_name, "stage_a")

    def test_adjacent_stages_are_none_when_current_stage_not_in_order(self) -> None:
        session, animal = self._make_session(
            stage="other",
            stage_order=("stage_a", "stage_b"),
        )
        session.set_current_animal("animal-1")

        self.assertIsNone(session.next_stage)
        self.assertIsNone(session.prev_stage)
        self.assertIsNone(session.go_next_stage())
        self.assertIsNone(session.go_prev_stage())
        self.assertEqual(animal.current_stage_name, "other")

    def test_adjacent_stages_clamp_at_ends(self) -> None:
        first_session, first_animal = self._make_session(
            stage="stage_a",
            stage_order=("stage_a", "stage_b", "stage_c"),
        )
        first_session.set_current_animal("animal-1")

        self.assertEqual(first_session.next_stage, "stage_b")
        self.assertIsNone(first_session.prev_stage)
        self.assertIsNone(first_session.go_prev_stage())
        self.assertEqual(first_animal.current_stage_name, "stage_a")

        last_session, last_animal = self._make_session(
            stage="stage_c",
            stage_order=("stage_a", "stage_b", "stage_c"),
        )
        last_session.set_current_animal("animal-1")

        self.assertEqual(last_session.prev_stage, "stage_b")
        self.assertIsNone(last_session.next_stage)
        self.assertIsNone(last_session.go_next_stage())
        self.assertEqual(last_animal.current_stage_name, "stage_c")

    def test_go_next_stage_moves_to_next_configured_stage(self) -> None:
        session, animal = self._make_session(
            stage="stage_a",
            stage_order=("stage_a", "stage_b", "stage_c"),
        )
        session.set_current_animal("animal-1")

        self.assertEqual(session.next_stage, "stage_b")
        result = session.go_next_stage()

        self.assertEqual(result, "stage_b")
        self.assertEqual(animal.current_stage_name, "stage_b")
        self.assertIn("stage_b", animal.stages)

    def test_go_prev_stage_moves_to_previous_configured_stage(self) -> None:
        session, animal = self._make_session(
            stage="stage_b",
            stage_order=("stage_a", "stage_b", "stage_c"),
        )
        session.set_current_animal("animal-1")

        self.assertEqual(session.prev_stage, "stage_a")
        result = session.go_prev_stage()

        self.assertEqual(result, "stage_a")
        self.assertEqual(animal.current_stage_name, "stage_a")
        self.assertIn("stage_a", animal.stages)


if __name__ == "__main__":
    unittest.main()
