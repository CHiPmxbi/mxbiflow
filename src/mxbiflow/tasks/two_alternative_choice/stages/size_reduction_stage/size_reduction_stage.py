from typing import TYPE_CHECKING, Final

from mxbi.data_logger import DataLogger, DataLoggerType
from mxbi.tasks.two_alternative_choice.models import PersistentData, Result
from mxbi.tasks.two_alternative_choice.stages.size_reduction_stage.size_reduction_models import (
    config,
)
from mxbi.tasks.two_alternative_choice.tasks.touch.touch_scene import TwoACTouchScene
from mxbi.utils.logger import logger

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState, ScheduleCondition
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.tasks.two_alternative_choice.stages.size_reduction_stage.size_reduction_models import (
        SizeReductionStageConfig,
    )
    from mxbi.theater import Theater

_presistent_data: dict[str, PersistentData] = {}


class TWOACSizeReductionStage:
    STAGE_NAME: Final[str] = "twoac_size_reduction_stage"

    def __init__(
        self,
        theater: "Theater",
        session_state: "SessionState",
        animal_state: "AnimalState",
    ) -> None:
        self._theater = theater
        self._session_state = session_state
        self._animal_state = animal_state

        self._stage_config = self._load_stage_config(animal_state.name)

        _levels_config = self._stage_config.levels_table[animal_state.level]
        _config = self._stage_config.trial_config

        _config.level = _levels_config.level
        _config.stimulation_size = _levels_config.stimulation_size

        self._data_logger = DataLogger(
            self._session_state,
            self._animal_state.name,
            self.STAGE_NAME,
            DataLoggerType.JSONL,
        )

        self._presistent_data = _presistent_data.get(self._animal_state.name)

        if self._presistent_data is None:
            self._presistent_data = PersistentData(
                rewards=0,
                correct=0,
                incorrect=0,
                timeout=0,
            )
            _presistent_data[self._animal_state.name] = self._presistent_data

        self._task = TwoACTouchScene(
            theater,
            session_state.session_config,
            animal_state,
            session_state.session_config.screen_type,
            _config,
            self._presistent_data,
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

    def _load_stage_config(self, monkey: str) -> "SizeReductionStageConfig":
        stage_config = config.root.get(monkey) or config.root.get("default")
        if stage_config is None:
            raise ValueError("No default stage config found")
        return stage_config

    def _handle_result(self, result: "Result") -> "Feedback":
        feedback = False
        match result:
            case Result.CORRECT:
                _presistent_data[self._animal_state.name].correct += 1
                feedback = True
            case Result.INCORRECT:
                _presistent_data[self._animal_state.name].incorrect += 1
                feedback = False
            case Result.TIMEOUT:
                _presistent_data[self._animal_state.name].timeout += 1
                feedback = False
            case Result.CANCEL:
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
