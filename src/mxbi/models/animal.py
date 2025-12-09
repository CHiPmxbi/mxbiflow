from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, computed_field

from mxbi.models.task import TaskEnum

if TYPE_CHECKING:
    from mxbi.models.task import Feedback


class AnimalConfig(BaseModel):
    name: str = "mock"
    task: TaskEnum = TaskEnum.IDEL
    level: int = 0
    cross_modal_trial_file: str | None = None


class ScheduleConditionConfig(BaseModel):
    evaluation_interval: int = 20
    difficulty_increase_threshold: float = 0.8
    difficulty_decrease_threshold: float = 0
    allow_decrease: bool = True
    next_task: TaskEnum | None = None


class ScheduleCondition(BaseModel):
    level_count: int = 0
    config: ScheduleConditionConfig


class AnimalState(AnimalConfig):
    trial_id: int = 0
    current_level_trial_id: int = 0
    current_animal_session_trial_id: int = 0
    correct_trial: int = 0
    condition: "ScheduleCondition | None" = None

    @computed_field
    @property
    def correct_rate(self) -> float:
        if self.current_level_trial_id == 0:
            return 0.0
        return self.correct_trial / self.current_level_trial_id

    def reset(self) -> None:
        self.current_level_trial_id = 0
        self.correct_trial = 0

    def leave_session(self) -> None:
        self.current_animal_session_trial_id = 0

    def update(self, feedback: "Feedback") -> None:
        self.trial_id += 1
        self.current_level_trial_id += 1
        if feedback:
            self.correct_trial += 1


class AnimalOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: list[str]
    level: list[int] = Field(default_factory=lambda: [i for i in range(-1, 88)])
    task: list[TaskEnum] = Field(default_factory=lambda: list(TaskEnum))
