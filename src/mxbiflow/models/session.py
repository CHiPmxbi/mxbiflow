from pydantic import BaseModel, Field, PrivateAttr
from .animal import Animal, AnimalConfig
from datetime import datetime, timezone

from .reward import RewardEnum


class SessionConfig(BaseModel):
    experimenter: str = Field(default="auto", frozen=True)
    reward_type: RewardEnum = Field(default=RewardEnum.AGUM_ONE_FIFTH, frozen=True)
    send_email: bool = Field(default=False, frozen=True)
    sync_data: bool = Field(default=False, frozen=True)

    animals: list[AnimalConfig] = Field(default_factory=list)


class Session(BaseModel):
    experimenter: str = Field(default="auto", frozen=True)
    reward_type: RewardEnum = Field(default=RewardEnum.AGUM_ONE_FIFTH, frozen=True)
    send_email: bool = Field(default=False, frozen=True)
    sync_data: bool = Field(default=False, frozen=True)

    session_id: int = Field(default=0, ge=0)
    start_at: float = Field(default=0, ge=0)
    end_at: float = Field(default=0, ge=0)
    note: str = Field(frozen=True)

    _active_animal: str | None = PrivateAttr(default=None)
    animals: dict[str, Animal] = Field(default_factory=dict, frozen=True)

    def start(self):
        self.session_id += 1
        self.start_at = datetime.now(timezone.utc).timestamp()

    def end(self):
        self.end_at = datetime.now(timezone.utc).timestamp()

    # @property
    # def active_animals(self) -> dict[str, Animal] | None:
    #     with self._lock:
    #         ids = list(self._active_animals)

    #     if not ids:
    #         return None

    #     if any(animal_id not in self.animals for animal_id in self._active_animals):
    #         return None

    #     return {
    #         animal_id: self.animals[animal_id] for animal_id in self._active_animals
    #     }

    @property
    def active_animal(self) -> Animal | None:
        if self._active_animal is None:
            return None

        if self._active_animal not in self.animals:
            return None

        return self.animals[self._active_animal]

    def remove_active_animal(self):
        self._active_animal = None

    def set_active_animal(self, animal: str):
        self._active_animal = animal

    # def add_active_animal(self, animal: str):
    #     self._active_animal.append(animal)


class Options(BaseModel):
    mxbis: list[str] = Field(default_factory=list, frozen=True)
    experimenter: list[str] = Field(default_factory=list, frozen=True)
    animals: dict[str, str] = Field(default_factory=dict, frozen=True)
