from time import time

from pydantic import BaseModel, Field, PrivateAttr


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


class StageState(BaseModel):
    stage_name: str
    stage_trial_id: int = Field(default=0, ge=0)

    level: int = Field(default=0, ge=0)
    level_trial_id: int = Field(default=0, ge=0)

    def level_up(self):
        self.level_trial_id = 0
        self.level += 1

    def level_down(self):
        self.level_trial_id = 0
        self.level -= 1


class AnimalSessionState(BaseModel):
    session_id: int = Field(ge=0)
    start_at: float = Field(default_factory=lambda: time())
    end_at: float | None = None
    trial_id: int = Field(default=0, ge=0)


class Animal(BaseModel):
    rfid_id: str = Field(frozen=True)
    name: str = Field(frozen=True)

    trial_id: int = Field(default=0, ge=0)

    _current_stage: str = PrivateAttr(default="idle")
    _stages: dict[str, StageState] = PrivateAttr(default_factory=dict)
    _current_animal_session: AnimalSessionState | None = PrivateAttr(default=None)
    _sessions: list[AnimalSessionState] = PrivateAttr(default_factory=list)

    def add_trial(self) -> None:
        self.trial_id += 1
        self.current_stage.stage_trial_id += 1
        self.current_stage.level_trial_id += 1
        assert self.current_animal_session is not None
        self.current_animal_session.trial_id += 1

    @property
    def current_animal_session(self) -> AnimalSessionState | None:
        return self._current_animal_session

    def start_animal_session(self):
        session_id = 1

        if self._current_animal_session is not None:
            raise ValueError("Animal session is already started")

        if self._sessions:
            session_id = len(self._sessions) + 1

        session = AnimalSessionState(session_id=session_id)
        self._current_animal_session = session
        self._sessions.append(session)

    def end_animal_session(self):
        if self._current_animal_session is None:
            raise ValueError("Animal session is not started")

        self._current_animal_session.end_at = time()
        self._current_animal_session = None

    @property
    def current_stage(self) -> StageState:
        key = self._current_stage

        state = self._stages.get(key)
        if state is None:
            raise ValueError(f"Unknown stage: {key}")

        return state

    def set_current_stage(self, stage: StageState | str) -> None:
        if isinstance(stage, str):
            stage = StageState(stage_name=stage)

        self._current_stage = stage.stage_name
        if stage.stage_name in self._stages:
            return

        self._stages[stage.stage_name] = stage

    def clear_current_stage(self) -> None:
        self._current_stage = "idle"

    def level_up(self) -> int:
        self.current_stage.level_up()
        return self.current_stage.level

    def level_down(self) -> int:
        self.current_stage.level_down()
        return self.current_stage.level

    @property
    def base_info(self) -> AnimalBaseInfo:
        if self.current_animal_session is None:
            raise ValueError("Animal session is not started")

        return AnimalBaseInfo(
            animal=self.name,
            trial_id=self.trial_id,
            level=self.current_stage.level,
            level_trial_id=self.current_stage.level_trial_id,
            animal_session_id=self.current_animal_session.session_id,
            animal_session_trial_id=self.current_animal_session.trial_id,
        )
