from copy import deepcopy
from datetime import UTC, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    computed_field,
    field_serializer,
)

type ContextMap = dict[str, SerializeAsAny[BaseModel]]


def validate_context_key(key: str) -> None:
    if not key.strip():
        raise ValueError("context key must not be empty")


class ContextState(BaseModel):
    contexts: ContextMap = Field(default_factory=dict)

    def get_context[T: BaseModel](self, key: str, context_type: type[T]) -> T | None:
        validate_context_key(key)
        context = self.contexts.get(key)
        if context is None:
            return None
        if not isinstance(context, context_type):
            raise TypeError(
                f"Expected {context_type.__name__}, got {type(context).__name__}"
            )
        return context


class AnimalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    rfid_id: str = ""
    name: str = "mock"
    stage: str = "idle"
    level: int = Field(default=0, ge=0)


class AnimalBaseInfo(BaseModel):
    animal: str
    trial_id: int
    level: int
    level_trial_id: int
    animal_session_id: int
    animal_session_trial_id: int


class StageState(ContextState):
    stage_name: str
    stage_trial_id: int = Field(default=0, ge=0)

    initial_level: int = Field(default=0, ge=0)
    level: int = Field(default=0, ge=0)
    level_trial_id: int = Field(default=0, ge=0)


class StageSnapshot(ContextState):
    model_config = ConfigDict(frozen=True)

    stage_name: str
    stage_trial_id: int = Field(ge=0)
    initial_level: int = Field(ge=0)
    level: int = Field(ge=0)
    level_trial_id: int = Field(ge=0)

    @classmethod
    def from_state(cls, state: StageState) -> StageSnapshot:
        return cls(
            contexts=deepcopy(state.contexts),
            stage_name=state.stage_name,
            stage_trial_id=state.stage_trial_id,
            initial_level=state.initial_level,
            level=state.level,
            level_trial_id=state.level_trial_id,
        )


class AnimalSessionState(BaseModel):
    session_id: int = Field(ge=0)
    start_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_at: datetime | None = None
    trial_id: int = Field(default=0, ge=0)

    @field_serializer("start_at", "end_at", when_used="json")
    def _serialize_timestamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone().isoformat(timespec="microseconds")


class Animal(ContextState):
    config: AnimalConfig = Field(frozen=True, exclude=True)

    trial_id: int = Field(default=0, ge=0)
    current_stage_name: str = "idle"
    stages: dict[str, StageState] = Field(default_factory=dict)
    initial_stage: StageSnapshot | None = None
    final_stage: StageSnapshot | None = None
    current_animal_session: AnimalSessionState | None = None
    animal_sessions: list[AnimalSessionState] = Field(default_factory=list)

    @computed_field
    @property
    def rfid_id(self) -> str:
        return self.config.rfid_id

    @computed_field
    @property
    def name(self) -> str:
        return self.config.name

    @property
    def current_stage(self) -> StageState:
        state = self.stages.get(self.current_stage_name)
        if state is None:
            raise ValueError(f"Unknown stage: {self.current_stage_name}")
        return state

    @property
    def base_info(self) -> AnimalBaseInfo:
        current_session = self.current_animal_session
        if current_session is None:
            raise ValueError("Animal session is not started")

        return AnimalBaseInfo(
            animal=self.config.name,
            trial_id=self.trial_id,
            level=self.current_stage.level,
            level_trial_id=self.current_stage.level_trial_id,
            animal_session_id=current_session.session_id,
            animal_session_trial_id=current_session.trial_id,
        )
