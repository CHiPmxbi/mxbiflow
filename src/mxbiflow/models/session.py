import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    computed_field,
    field_serializer,
    model_validator,
)

from .animal import (
    Animal,
    AnimalConfig,
    AnimalSessionState,
    ContextState,
    StageSnapshot,
    StageState,
    validate_context_key,
)
from .reward import RewardEnum


class SessionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    experimenter: str = "auto"
    reward_type: RewardEnum = RewardEnum.AGUM_ONE_FIFTH
    send_email: bool = False
    sync_data: bool = False
    note: str = Field(default="", max_length=1000)

    default_scene: str = ""
    unknown_animal_as: str = ""
    fault_fallback: str = ""

    hide_cursor: bool = False
    fullscreen: bool = False

    animals: tuple[AnimalConfig, ...] = ()

    @model_validator(mode="after")
    def _validate_unknown_animal_as(self) -> SessionConfig:
        if not self.animals:
            return self

        if not self.unknown_animal_as:
            raise ValueError("unknown_animal_as must be set when animals are configured")

        animal_names = {animal.name for animal in self.animals}
        if self.unknown_animal_as not in animal_names:
            raise ValueError(
                "unknown_animal_as must match a configured animal name"
            )
        return self


class SessionState(ContextState):
    session_id: int = Field(default=0, ge=0)
    start_at: datetime | None = None
    end_at: datetime | None = None
    data_path: Path | None = None
    current_scene: str | None = None
    current_animal_name: str | None = None
    animals: dict[str, Animal] = Field(default_factory=dict)

    @field_serializer("start_at", "end_at", when_used="json")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone().isoformat(timespec="microseconds")


class DailySessionCounter(BaseModel):
    day: str = Field(default_factory=lambda: datetime.now(UTC).date().isoformat())
    last_session_id: int = Field(default=0, ge=0)


class EmailSendState(BaseModel):
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_id: str = ""


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=path.name,
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


@dataclass
class DailySessionIdStore:
    path: Path

    def _today_local(self) -> str:
        return datetime.now(UTC).date().isoformat()

    def _load(self) -> DailySessionCounter:
        if not self.path.exists():
            return DailySessionCounter()

        try:
            return DailySessionCounter.model_validate_json(self.path.read_text())
        except ValueError, ValidationError:
            return DailySessionCounter()

    @property
    def session_id(self) -> int:
        today = self._today_local()
        data = self._load()

        if data.day != today:
            data.day = today
            data.last_session_id = 0

        data.last_session_id += 1
        _atomic_write(self.path, data.model_dump_json())
        return data.last_session_id


@dataclass
class EmailSendStateStore:
    path: Path

    def _load(self) -> EmailSendState:
        if not self.path.exists():
            return EmailSendState()

        try:
            return EmailSendState.model_validate_json(self.path.read_text())
        except ValueError, ValidationError:
            return EmailSendState()

    def load(self) -> EmailSendState:
        return self._load()

    def save(self, message_id: str) -> None:
        _atomic_write(
            self.path,
            EmailSendState(message_id=message_id).model_dump_json(),
        )


@dataclass
class SessionSnapshotStore:
    path: Path

    def save(self, snapshot: Mapping[str, object]) -> None:
        text = json.dumps(snapshot, ensure_ascii=False, indent=2)
        _atomic_write(self.path, text)


class Session(BaseModel):
    config: SessionConfig
    state: SessionState

    _session_store: DailySessionIdStore | None = PrivateAttr(default=None)
    _snapshot_store: SessionSnapshotStore | None = PrivateAttr(default=None)
    _data_root: Path | None = PrivateAttr(default=None)

    @computed_field
    @property
    def experimenter(self) -> str:
        return self.config.experimenter

    @computed_field
    @property
    def reward_type(self) -> RewardEnum:
        return self.config.reward_type

    @computed_field
    @property
    def send_email(self) -> bool:
        return self.config.send_email

    @computed_field
    @property
    def sync_data(self) -> bool:
        return self.config.sync_data

    @computed_field
    @property
    def note(self) -> str:
        return self.config.note

    @computed_field
    @property
    def default_scene(self) -> str:
        return self.config.default_scene

    @computed_field
    @property
    def unknown_animal_as(self) -> str:
        return self.config.unknown_animal_as

    @computed_field
    @property
    def fault_fallback(self) -> str:
        return self.config.fault_fallback

    @computed_field
    @property
    def hide_cursor(self) -> bool:
        return self.config.hide_cursor

    @computed_field
    @property
    def fullscreen(self) -> bool:
        return self.config.fullscreen

    @computed_field
    @property
    def session_id(self) -> int:
        return self.state.session_id

    @computed_field
    @property
    def start_at(self) -> datetime | None:
        return self.state.start_at

    @computed_field
    @property
    def end_at(self) -> datetime | None:
        return self.state.end_at

    @computed_field
    @property
    def data_path(self) -> Path | None:
        return self.state.data_path

    @computed_field
    @property
    def current_scene(self) -> str | None:
        return self.state.current_scene

    @computed_field
    @property
    def animals(self) -> Mapping[str, Animal]:
        return self.state.animals

    @computed_field
    @property
    def current_animal(self) -> Animal | None:
        key = self.state.current_animal_name
        if key is None:
            return None
        return self.state.animals[key]

    def require_current_animal(self) -> Animal:
        animal = self.current_animal
        if animal is None:
            raise RuntimeError(
                "Animal is not set. Please call set_current_animal() first"
            )
        return animal

    @property
    def absolute_data_path(self) -> Path | None:
        if self.state.data_path is None or self._data_root is None:
            return None
        return self._data_root / self.state.data_path

    def set_session_store(self, store: DailySessionIdStore) -> None:
        self._session_store = store

    def set_snapshot_store(self, store: SessionSnapshotStore) -> None:
        self._snapshot_store = store

    def snapshot(self) -> dict[str, object]:
        computed_fields = set(type(self).model_computed_fields)
        return self.model_dump(mode="json", exclude=computed_fields)

    def checkpoint(self) -> None:
        if self._snapshot_store is not None:
            self._snapshot_store.save(self.snapshot())

    def start(self, data_root: Path) -> None:
        if self.state.start_at is not None:
            raise RuntimeError("Session is already started")

        if self._session_store is not None and self.state.session_id == 0:
            self.state.session_id = self._session_store.session_id

        self.state.start_at = datetime.now(UTC)
        self._data_root = data_root.resolve()
        self.state.data_path = Path(self.state.start_at.strftime("%Y%m%d")) / str(
            self.state.session_id
        )

        absolute_data_path = self.absolute_data_path
        assert absolute_data_path is not None
        if self._snapshot_store is None:
            self._snapshot_store = SessionSnapshotStore(
                absolute_data_path / "session.json"
            )
        self.checkpoint()

    def end(self) -> None:
        if self.state.start_at is None:
            raise RuntimeError("Session is not started")
        if self.state.end_at is not None:
            return

        animal = self.current_animal
        if animal is not None:
            self._end_animal_session(animal)
            self.state.current_animal_name = None
        self.state.end_at = datetime.now(UTC)
        self.checkpoint()

    def set_current_scene(self, scene: str | None) -> None:
        if self.state.current_scene == scene:
            return
        self.state.current_scene = scene
        self.checkpoint()

    def clear_current_animal(self) -> None:
        animal = self.current_animal
        if animal is None:
            return

        self._end_animal_session(animal)
        self.state.current_animal_name = None
        self.checkpoint()

    def set_current_animal(self, animal: str) -> None:
        try:
            next_animal = self.state.animals[animal]
        except KeyError as error:
            raise ValueError(f"animal {animal} not found") from error

        current = self.current_animal
        if (
            next_animal is not current
            and next_animal.current_animal_session is not None
        ):
            raise ValueError(f"animal {animal} session is already started")
        if current is not None:
            self._end_animal_session(current)

        self.state.current_animal_name = animal
        self._start_animal_session(next_animal)
        self.checkpoint()

    def set_current_stage(self, stage: StageState | str) -> None:
        animal = self.require_current_animal()
        if isinstance(stage, str):
            stage = StageState(stage_name=stage)

        animal.current_stage_name = stage.stage_name
        animal.stages.setdefault(stage.stage_name, stage)
        self.checkpoint()

    def add_trial(self) -> None:
        animal = self.require_current_animal()
        animal_session = animal.current_animal_session
        if animal_session is None:
            raise RuntimeError("Animal session is not started")
        stage = animal.current_stage

        animal.trial_id += 1
        stage.stage_trial_id += 1
        stage.level_trial_id += 1
        animal_session.trial_id += 1
        self.checkpoint()

    def level_up(
        self,
        *,
        animal: str | None = None,
        stage: str | None = None,
    ) -> int:
        stage_state = self._resolve_stage(animal=animal, stage=stage)
        stage_state.level_trial_id = 0
        stage_state.level += 1
        self.checkpoint()
        return stage_state.level

    def level_down(
        self,
        *,
        animal: str | None = None,
        stage: str | None = None,
    ) -> int:
        stage_state = self._resolve_stage(animal=animal, stage=stage)
        if stage_state.level == 0:
            raise ValueError("level cannot be less than 0")

        stage_state.level_trial_id = 0
        stage_state.level -= 1
        self.checkpoint()
        return stage_state.level

    def get_context[T: BaseModel](self, key: str, context_type: type[T]) -> T | None:
        return self.state.get_context(key, context_type)

    def set_context(self, key: str, context: BaseModel) -> None:
        validate_context_key(key)
        self.state.contexts[key] = context
        self.checkpoint()

    def _resolve_animal(self, animal: str | None) -> Animal:
        if animal is None:
            return self.require_current_animal()
        try:
            return self.state.animals[animal]
        except KeyError as error:
            raise ValueError(f"animal {animal} not found") from error

    def set_animal_context(
        self,
        key: str,
        context: BaseModel,
        *,
        animal: str | None = None,
    ) -> None:
        validate_context_key(key)
        self._resolve_animal(animal).contexts[key] = context
        self.checkpoint()

    def set_stage_context(
        self,
        key: str,
        context: BaseModel,
        *,
        animal: str | None = None,
        stage: str | None = None,
    ) -> None:
        stage_state = self._resolve_stage(animal=animal, stage=stage)
        validate_context_key(key)
        stage_state.contexts[key] = context
        self.checkpoint()

    def _start_animal_session(self, animal: Animal) -> None:
        if animal.current_animal_session is not None:
            raise ValueError("Animal session is already started")

        if animal.initial_stage is None:
            animal.initial_stage = StageSnapshot.from_state(animal.current_stage)
        animal.final_stage = None

        animal_session = AnimalSessionState(session_id=len(animal.animal_sessions) + 1)
        animal.current_animal_session = animal_session
        animal.animal_sessions.append(animal_session)

    def _end_animal_session(self, animal: Animal) -> None:
        animal_session = animal.current_animal_session
        if animal_session is None:
            raise ValueError("Animal session is not started")

        animal_session.end_at = datetime.now(UTC)
        animal.current_animal_session = None
        animal.final_stage = StageSnapshot.from_state(animal.current_stage)

    def _resolve_stage(
        self,
        *,
        animal: str | None,
        stage: str | None,
    ) -> StageState:
        animal_state = self._resolve_animal(animal)
        if stage is None:
            return animal_state.current_stage
        try:
            return animal_state.stages[stage]
        except KeyError as error:
            raise ValueError(f"stage {stage} not found") from error


class Options(BaseModel):
    mxbis: list[str] = Field(default_factory=list, frozen=True)
    experimenter: list[str] = Field(default_factory=list, frozen=True)
    animals: dict[str, str] = Field(default_factory=dict, frozen=True)
