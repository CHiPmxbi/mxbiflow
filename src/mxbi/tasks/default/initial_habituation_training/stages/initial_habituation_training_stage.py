from random import choices
from typing import TYPE_CHECKING, Final

from mxbi.data_logger import DataLogger, DataLoggerType
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.default.initial_habituation_training.stages.models import (
    InitialHabituationTrainingStageConfig,
    StageContext,
    StageContexts,
    config,
)
from mxbi.tasks.default.initial_habituation_training.tasks.stay_to_reward.stay_to_reward import (
    DefaultStayToRewardScene,
)
from mxbi.tasks.default.initial_habituation_training.tasks.stay_to_reward.stay_to_reward_models import (
    Result,
    TrialConfig,
)
from mxbi.utils.logger import logger
from mxbi.utils.tkinter.components.canvas_with_border import CanvasWithInnerBorder

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import SessionConfig, SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater


contexts = StageContexts()
background: CanvasWithInnerBorder | None = None


def _initialize_contexts(session_config: "SessionConfig") -> None:
    global contexts
    for monkey in session_config.animals.keys():
        if contexts.root.get(monkey) is None:
            contexts.root[monkey] = StageContext()


def _initialize_background(theater: "Theater", session_config: "SessionConfig") -> None:
    global background
    background = CanvasWithInnerBorder(
        master=theater.root,
        bg="black",
        width=session_config.screen_type.width,
        height=session_config.screen_type.height,
        border_width=40,
    )


class InitialHabituationTrainingStage:
    STAGE_NAME: Final[str] = "DEFAULT_INITIAL_HABITUATION_TRAINING_STAGE"

    def __init__(
        self,
        theater: "Theater",
        session_state: "SessionState",
        animal_state: "AnimalState",
    ) -> None:
        self._theater = theater
        self._session_state = session_state
        self._animal_state = animal_state

        if not contexts.root:
            _initialize_contexts(session_state.session_config)

        if background is None:
            _initialize_background(theater, session_state.session_config)

        context = contexts.root[animal_state.name]

        self._stage_config = self._load_stage_config(self._animal_state.name)

        _levels_config = self._stage_config.levels_table[animal_state.level]
        self._stage_config.condition.config.evaluation_interval = (
            _levels_config.evaluation_interval
        )

        entry_reward = choices(
            [True, False],
            weights=[_levels_config.entry_reward, 1 - _levels_config.entry_reward],
        )[0]

        _config = TrialConfig(
            level=_levels_config.level,
            entry_reward=entry_reward,
            reward_interval=_levels_config.reward_interval,
            reward_duration=_levels_config.reward_duration,
            stimulus_duration=_levels_config.stimulus_duration,
            stimulus_density=_levels_config.stimulus_density,
        )

        self._data_logger = DataLogger(
            self._session_state,
            self._animal_state.name,
            self.STAGE_NAME,
            DataLoggerType.JSONL,
        )

        if self._animal_state.data_path is None:
            self._animal_state.data_path = self._data_logger.path

        assert background is not None

        self._task = DefaultStayToRewardScene(
            theater=theater,
            animal_state=animal_state,
            screen_type=session_state.session_config.screen_type,
            trial_config=_config,
            context=context,
            background=background,
        )

    def start(self) -> "Feedback":
        trial_data = self._task.start()
        self._data_logger.save(trial_data.model_dump())

        feedback = self._handle_result(trial_data.result)
        logger.debug(
            f"{self.STAGE_NAME}: "
            f"session_id={self._session_state.session_id}, "
            f"animal_name={self._animal_state.name}, "
            f"animal_level={self._animal_state.level}, "
            f"state_name={self.STAGE_NAME}, "
            f"result={trial_data}, "
            f"feedback={feedback}"
        )

        return feedback

    def _load_stage_config(self, monkey: str) -> InitialHabituationTrainingStageConfig:
        stage_config = config.root.get(monkey) or config.root.get("default")
        if stage_config is None:
            raise ValueError("No default stage config found")
        return stage_config

    def _handle_result(self, result: "Result") -> "Feedback":
        feedback = False

        match result:
            case Result.CORRECT:
                feedback = True
            case Result.INCORRECT:
                feedback = False

        return feedback

    def quit(self) -> None:
        self._task.cancle()

    def on_idle(self) -> None:
        self._task.cancle()

    def on_return(self) -> None:
        self._task.cancle()

    @property
    def condition(self) -> "ScheduleCondition | None":
        return self._stage_config.condition
