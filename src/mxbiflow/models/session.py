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
    field_serializer,
    model_validator,
)
from pymxbi import MXBIModel

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

    mxbi: MXBIModel = Field(default_factory=MXBIModel)

    @model_validator(mode="after")
    def _validate_unknown_animal_as(self) -> SessionConfig:
        if not self.animals:
            return self

        if not self.unknown_animal_as:
            raise ValueError(
                "unknown_animal_as must be set when animals are configured"
            )

        animal_names = {animal.name for animal in self.animals}
        if self.unknown_animal_as not in animal_names:
            raise ValueError("unknown_animal_as must match a configured animal name")
        return self


class SessionState(ContextState):
    session_id: int = Field(default=0, ge=0)
    start_at: datetime | None = None
    end_at: datetime | None = None
    data_path: Path | None = None
    current_scene: str | None = None
    current_animal_name: str | None = None
    animals: dict[str, Animal] = Field(default_factory=dict)
    stage_data_paths: dict[str, dict[str, Path]] = Field(default_factory=dict)

    @field_serializer("start_at", "end_at", when_used="json")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone().isoformat(timespec="microseconds")


class SessionRuntimeState(BaseModel):
    day: str = Field(default_factory=lambda: datetime.now(UTC).date().isoformat())
    last_session_id: int = Field(default=0, ge=0)


class EmailRuntimeState(BaseModel):
    message_id: str = ""


class RuntimeState(BaseModel):
    session: SessionRuntimeState = Field(default_factory=SessionRuntimeState)
    email: EmailRuntimeState = Field(default_factory=EmailRuntimeState)


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
class RuntimeStateStore:
    path: Path

    def _today(self) -> str:
        return datetime.now(UTC).date().isoformat()

    def _load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()

        try:
            return RuntimeState.model_validate_json(self.path.read_text())
        except ValueError, ValidationError:
            return RuntimeState()

    def _save(self, state: RuntimeState) -> None:
        _atomic_write(self.path, state.model_dump_json())

    @property
    def session_id(self) -> int:
        today = self._today()
        state = self._load()

        if state.session.day != today:
            state.session.day = today
            state.session.last_session_id = 0

        state.session.last_session_id += 1
        self._save(state)
        return state.session.last_session_id

    @property
    def email_message_id(self) -> str:
        return self._load().email.message_id

    def save_email_message_id(self, message_id: str) -> None:
        state = self._load()
        state.email.message_id = message_id
        self._save(state)


@dataclass
class SessionSnapshotStore:
    path: Path

    def save(self, snapshot: Mapping[str, object]) -> None:
        text = json.dumps(snapshot, ensure_ascii=False, indent=2)
        _atomic_write(self.path, text)


class Session(BaseModel):
    config: SessionConfig
    state: SessionState

    _session_store: RuntimeStateStore | None = PrivateAttr(default=None)
    _snapshot_store: SessionSnapshotStore | None = PrivateAttr(default=None)
    _animal_snapshot_stores: dict[str, SessionSnapshotStore] = PrivateAttr(
        default_factory=dict
    )
    _data_root: Path | None = PrivateAttr(default=None)

    @property
    def experimenter(self) -> str:
        return self.config.experimenter

    @property
    def reward_type(self) -> RewardEnum:
        return self.config.reward_type

    @property
    def send_email(self) -> bool:
        return self.config.send_email

    @property
    def sync_data(self) -> bool:
        return self.config.sync_data

    @property
    def note(self) -> str:
        return self.config.note

    @property
    def default_scene(self) -> str:
        return self.config.default_scene

    @property
    def unknown_animal_as(self) -> str:
        return self.config.unknown_animal_as

    @property
    def fault_fallback(self) -> str:
        return self.config.fault_fallback

    @property
    def hide_cursor(self) -> bool:
        return self.config.hide_cursor

    @property
    def fullscreen(self) -> bool:
        return self.config.fullscreen

    @property
    def session_id(self) -> int:
        return self.state.session_id

    @property
    def start_at(self) -> datetime | None:
        return self.state.start_at

    @property
    def end_at(self) -> datetime | None:
        return self.state.end_at

    @property
    def data_path(self) -> Path | None:
        return self.state.data_path

    @property
    def current_scene(self) -> str | None:
        return self.state.current_scene

    @property
    def animals(self) -> Mapping[str, Animal]:
        return self.state.animals

    @property
    def mxbi_config(self) -> MXBIModel:
        return self.config.mxbi

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

    @property
    def data_root(self) -> Path | None:
        return self._data_root

    def animal_data_path(self, animal: str) -> Path:
        if self.state.data_path is None:
            raise RuntimeError("Session is not started")
        if animal not in self.state.animals:
            raise ValueError(f"animal {animal} not found")
        return Path(animal) / self.state.data_path

    def absolute_animal_data_path(self, animal: str) -> Path:
        if self._data_root is None:
            raise RuntimeError("Session is not started")
        return self._data_root / self.animal_data_path(animal)

    @property
    def screenshot_data_path(self) -> Path:
        if self.state.data_path is None:
            raise RuntimeError("Session is not started")
        return Path("screenshot") / self.state.data_path

    @property
    def absolute_screenshot_data_path(self) -> Path:
        if self._data_root is None:
            raise RuntimeError("Session is not started")
        return self._data_root / self.screenshot_data_path

    @property
    def participant_data_paths(self) -> tuple[Path, ...]:
        return tuple(
            self.animal_data_path(animal) for animal in self._animal_snapshot_stores
        )

    @property
    def stage_data_paths(self) -> Mapping[str, Mapping[str, Path]]:
        return self.state.stage_data_paths

    def register_stage_data_path(self, *, animal: str, stage: str) -> Path:
        path = self.animal_data_path(animal) / stage
        paths_by_animal = self.state.stage_data_paths.setdefault(stage, {})
        if paths_by_animal.get(animal) == path:
            return path

        paths_by_animal[animal] = path
        self.checkpoint()
        return path

    def set_session_store(self, store: RuntimeStateStore) -> None:
        self._session_store = store

    def set_snapshot_store(self, store: SessionSnapshotStore) -> None:
        self._snapshot_store = store

    def snapshot(self) -> dict[str, object]:
        return self.model_dump(mode="json")

    def checkpoint(self) -> None:
        snapshot = self.snapshot()
        if self._snapshot_store is not None:
            self._snapshot_store.save(snapshot)
        for store in self._animal_snapshot_stores.values():
            store.save(snapshot)

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
        if self._data_root is not None:
            self._ensure_animal_snapshot_store(animal)
        self.checkpoint()

    def _ensure_animal_snapshot_store(self, animal: str) -> None:
        if animal in self._animal_snapshot_stores:
            return
        self._animal_snapshot_stores[animal] = SessionSnapshotStore(
            self.absolute_animal_data_path(animal) / "session.json"
        )

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
