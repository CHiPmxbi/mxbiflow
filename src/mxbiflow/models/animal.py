from datetime import datetime, timezone

from pydantic import BaseModel, Field, PrivateAttr


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnimalConfig(BaseModel):
    rfid_id: str = Field(default="", frozen=True)
    name: str = Field(default="mock", frozen=True)
    stage: str = Field(default="idle", frozen=True)
    level: int = Field(default=0, ge=0, frozen=True)


class AnimalBaseInfo(BaseModel):
    animal: str
    trial_id: int
    level: int
    level_trial_id: int
    animal_session_id: int
    animal_session_trial_id: int


class TrainState(BaseModel):
    name: str
    stage_trial_id: int = Field(default=0, ge=0)

    level: int = Field(default=0, ge=0)
    total_levels: int = Field(default=10, ge=0)
    level_trial_id: int = Field(default=0, ge=0)


class AnimalSessionState(BaseModel):
    session_id: int = Field(ge=0)
    start_at: datetime = Field(default_factory=utcnow)
    end_at: datetime | None = None
    trial_id: int = Field(default=0, ge=0)


class Animal(BaseModel):
    rfid_id: str = Field(frozen=True)
    name: str = Field(frozen=True)

    trial_id: int = Field(default=0, ge=0)

    _stage: str = PrivateAttr(default="idle")
    _stages: dict[str, TrainState] = PrivateAttr(default_factory=dict)
    _animal_session: int | None = PrivateAttr(default=None)
    _sessions: dict[int, AnimalSessionState] = PrivateAttr(default_factory=dict)

    @property
    def animal_session(self) -> AnimalSessionState | None:
        sid = self._animal_session
        if sid is None:
            return None

        session = self._sessions.get(sid)
        if session is None:
            self._animal_session = None

        return session

    def add_animal_session(self):
        if self._animal_session is None:
            animal_session = AnimalSessionState(session_id=1)
            self._animal_session = animal_session.session_id
            self._sessions[animal_session.session_id] = animal_session
        else:
            self._animal_session += 1
            animal_session = AnimalSessionState(session_id=self._animal_session)
            self._sessions[animal_session.session_id] = animal_session

    @property
    def stage(self) -> TrainState:
        key = self._stage

        train = self._stages.get(key)
        if train is None:
            raise ValueError(f"Unknown stage: {key}")

        return train

    @property
    def base_info(self) -> AnimalBaseInfo:
        if self.animal_session is None:
            raise ValueError("Animal session is not started")

        return AnimalBaseInfo(
            animal=self.name,
            trial_id=self.trial_id,
            level=self.stage.level,
            level_trial_id=self.stage.level_trial_id,
            animal_session_id=self.animal_session.session_id,
            animal_session_trial_id=self.animal_session.trial_id,
        )

    def set_stage(self, stage: TrainState | str):
        if isinstance(stage, str):
            stage = TrainState(name=stage)

        self._stage = stage.name
        if stage.name in self._stages:
            return

        self._stages[stage.name] = stage
