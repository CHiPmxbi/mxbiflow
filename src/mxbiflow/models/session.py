import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from .animal import Animal, AnimalConfig
from .reward import RewardEnum


class SessionConfig(BaseModel):
    experimenter: str = Field(default="auto", frozen=True)
    reward_type: RewardEnum = Field(default=RewardEnum.AGUM_ONE_FIFTH, frozen=True)
    send_email: bool = Field(default=False, frozen=True)
    sync_data: bool = Field(default=False, frozen=True)
    note: str = Field(default="", max_length=1000)

    animals: list[AnimalConfig] = Field(default_factory=list)


class DailySessionCounter(BaseModel):
    day: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).date().isoformat()
    )
    last_session_id: int = Field(default=0, ge=0)


@dataclass
class DailySessionIdStore:
    path: Path

    def _today_utc(self):
        return datetime.now(timezone.utc).date().isoformat()

    def _load(self) -> DailySessionCounter:
        if not self.path.exists():
            return DailySessionCounter()

        text = self.path.read_text()

        try:
            return DailySessionCounter.model_validate_json(text)
        except ValueError, ValidationError:
            return DailySessionCounter()

    def _atomic_write(self, data: DailySessionCounter) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix=self.path.name,
            suffix=".tmp",
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data.model_dump_json())
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp, self.path)
        finally:
            try:
                os.remove(tmp)
            except FileNotFoundError:
                pass

    @property
    def session_id(self) -> int:
        today = self._today_utc()
        data = self._load()

        if data.day != today:
            data.day = today
            data.last_session_id = 0

        data.last_session_id += 1
        self._atomic_write(data)

        return data.last_session_id


class Session(BaseModel):
    experimenter: str = Field(default="auto", frozen=True)
    reward_type: RewardEnum = Field(default=RewardEnum.AGUM_ONE_FIFTH, frozen=True)
    send_email: bool = Field(default=False, frozen=True)
    sync_data: bool = Field(default=False, frozen=True)

    session_id: int = Field(default=0, ge=0)
    start_at: float = Field(default=0, ge=0)
    end_at: float = Field(default=0, ge=0)
    note: str = Field(frozen=True)

    _current_animal: str | None = PrivateAttr(default=None)
    animals: dict[str, Animal] = Field(default_factory=dict, frozen=True)

    def start(self):
        self.start_at = datetime.now(timezone.utc).timestamp()

    def end(self):
        self.end_at = datetime.now(timezone.utc).timestamp()

    @property
    def current_animal(self) -> Animal | None:
        key = self._current_animal
        if key is None:
            return None

        return self.animals[key]

    @property
    def require_current_animal(self) -> Animal:
        key = self._current_animal
        if key is None:
            raise RuntimeError(
                f"Animal: {key} is not set. Please call set_current_animal() first"
            )

        return self.animals[key]

    def clear_current_animal(self):
        a = self.current_animal
        if a is None:
            return

        a.end_animal_session()
        self._current_animal = None

    def set_current_animal(self, animal: str):
        self.clear_current_animal()

        try:
            a = self.animals[animal]
        except KeyError:
            raise ValueError(f"animal {animal} not found")

        self._current_animal = animal
        a.start_animal_session()


class Options(BaseModel):
    mxbis: list[str] = Field(default_factory=list, frozen=True)
    experimenter: list[str] = Field(default_factory=list, frozen=True)
    animals: dict[str, str] = Field(default_factory=dict, frozen=True)
    stages: list[str] = Field(default_factory=list)
