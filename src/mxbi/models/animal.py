"""
Animal models split into:
- Config (identity/static)
- State (persistable)

No runtime-only fields.
All timestamps are timezone-aware UTC datetimes.
"""

from datetime import datetime, timezone
from typing import Dict, List

from pydantic import BaseModel, Field, RootModel, computed_field, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -------------------- TrainState --------------------


class TrainState(BaseModel):
    stage: str
    stage_trial_id: int = Field(default=0, ge=0)

    level: int = Field(default=0, ge=0)
    total_levels: int = Field(default=0, ge=0)
    level_trial_id: int = Field(default=0, ge=0)

    def record_trial(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError("n must be >= 0")
        self.stage_trial_id += n
        self.level_trial_id += n

    def reset_trial_counters(self) -> None:
        self.stage_trial_id = 0
        self.level_trial_id = 0

    def set_level(self, new_level: int) -> None:
        if new_level < 0:
            raise ValueError("new_level must be >= 0")
        if new_level != self.level:
            self.level = new_level
            self.level_trial_id = 0


# -------------------- Session (persistable) --------------------


class AnimalSession(BaseModel):
    session_id: int = Field(..., ge=0)
    start_at: datetime = Field(default_factory=utcnow)
    end_at: datetime | None = None
    trial_id: int = Field(0, ge=0)

    def end(self, at: datetime | None = None) -> None:
        if self.end_at is None:
            self.end_at = at or utcnow()

    def record_trial(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError("n must be >= 0")
        self.trial_id += n


# -------------------- Config --------------------


class AnimalConfig(BaseModel):
    rfid_id: str = Field(default="", frozen=True)
    name: str = Field(default="mock", frozen=True)
    stage: str = Field(default="idle", frozen=True)
    level: int = Field(default=0, ge=0, frozen=True)


# -------------------- State (+ API facade) --------------------


class AnimalState(BaseModel):
    """
    Persistable state for a single animal.

    Notes
    -----
    - sessions are persisted
    - active_session_id points to sessions[*].session_id, enabling restore
    - active_stage stores the key of the active TrainState
    """

    trial_id: int = Field(default=0, ge=0)

    train_states: Dict[str, TrainState] = Field(default_factory=dict)
    active_stage: str | None = None

    sessions: List[AnimalSession] = Field(default_factory=list)
    active_session_id: int | None = None


class Animal(BaseModel):
    config: AnimalConfig
    state: AnimalState
    # ---- Derived / Views ----

    @computed_field
    @property
    def rfid_id(self) -> str:
        return self.config.rfid_id

    @computed_field
    @property
    def name(self) -> str:
        return self.config.name

    @computed_field
    @property
    def active_train_state(self) -> TrainState | None:
        if self.active_stage is None:
            return None
        return self.state.train_states.get(self.active_stage)

    @computed_field
    @property
    def active_session(self) -> AnimalSession | None:
        """
        Return the active session object, if active_session_id is set.

        We assume session_id == index-in-sessions (monotonic append),
        but we still search safely in case of future changes.
        """
        if self.active_session_id is None:
            return None
        for s in self.state.sessions:
            if s.session_id == self.active_session_id:
                return s
        return None

    @computed_field
    @property
    def current_session_id(self) -> int | None:
        return self.active_session_id

    @computed_field
    @property
    def current_session_trials(self) -> int:
        s = self.active_session
        return s.trial_id if s else 0

    # ---- Actions ----

    def start_session(self, *, at: datetime | None = None) -> AnimalSession:
        if self.active_session_id is not None:
            raise ValueError("Session already active")

        sid = len(self.state.sessions)
        s = AnimalSession(session_id=sid, start_at=at or utcnow(), trial_id=0)
        self.state.sessions.append(s)
        self.active_session_id = sid
        return s

    def end_session(self, *, at: datetime | None = None) -> None:
        s = self.active_session
        if s is None:
            return
        s.end(at=at)
        self.active_session_id = None

    def record_trial(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError("n must be >= 0")

        s = self.active_session
        if s is None:
            raise ValueError("No active session")

        ts = self.active_train_state
        if ts is None:
            raise ValueError("No active training state")

        self.trial_id += n
        s.record_trial(n)
        ts.record_trial(n)

    def set_level(self, new_level: int) -> None:
        ts = self.active_train_state
        if ts is None:
            raise ValueError("No active training state")
        ts.set_level(new_level)

    def set_stage(self, new_stage: str, *, reset_level: bool = True) -> None:
        if new_stage not in self.state.train_states:
            self.state.train_states[new_stage] = TrainState(stage=new_stage)

        ts = self.state.train_states[new_stage]
        ts.reset_trial_counters()
        if reset_level:
            ts.set_level(0)

        self.active_stage = new_stage


# -------------------- Container mapping by name --------------------


class Animals(RootModel[dict[str, Animal]]):
    """
    Container mapping animal names to Animal.

    Note: historically this container used `rfid_id` as the key. We now treat
    `Animal.config.name` as the canonical key and auto-migrate old keying on load.
    """

    @model_validator(mode="after")
    def _validate_keys(self) -> "Animals":
        migrated: dict[str, Animal] = {}
        for key, animal in self.root.items():
            name = animal.config.name
            rfid_id = animal.config.rfid_id

            # Canonical: keyed by name
            if key == name:
                if name in migrated:
                    raise ValueError(f"Duplicate animal name key '{name}'")
                migrated[name] = animal
                continue

            # Back-compat: previously keyed by rfid_id
            if key == rfid_id and name:
                if name in migrated:
                    raise ValueError(
                        f"RFID key '{key}' maps to duplicate name key '{name}'"
                    )
                migrated[name] = animal
                continue

            raise ValueError(
                f"Animal key '{key}' must match config.name '{name}' (or legacy config.rfid_id '{rfid_id}')"
            )

        self.root = migrated
        return self

    def add(self, animal: Animal) -> None:
        name = animal.name
        if name in self.root:
            raise ValueError(f"Animal '{name}' already exists")
        self.root[name] = animal

    def get(self, animal_name: str) -> Animal | None:
        return self.root.get(animal_name)

    def remove(self, animal_name: str) -> None:
        self.root.pop(animal_name, None)
