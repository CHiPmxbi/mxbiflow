from random import choice, choices, randint
from typing import TYPE_CHECKING, Final

from mxbi.data_logger import DataLogger, DataLoggerType
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.GNGSiD.models import PersistentData, Result
from mxbi.tasks.GNGSiD.stages.detect_stage.detect_stage_models import (
    DetectStageConfig,
    config,
)
from mxbi.tasks.GNGSiD.tasks.detect.models import TrialConfig
from mxbi.tasks.GNGSiD.tasks.detect.scene import GNGSiDDetectScene
from mxbi.utils.logger import logger

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater


_presistent_data: dict[str, PersistentData] = {}


class GNGSiDDetectStage:
    STAGE_NAME: Final[str] = "GNGSiD_DETECT_STAGE"

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

        _fixed_config = self._stage_config.params
        _levels_config = self._stage_config.levels_table[animal_state.level]

        _is_go = choices(
            [True, False],
            weights=[_levels_config.go_task_prob, _levels_config.nogo_task_prob],
        )[0]

        _stimulus_duration = randint(
            _levels_config.min_stimulus_duration,
            _levels_config.max_stimulus_duration,
        )

        _master_amp, _digital_amp = self._prepare_stimulus_intensity(
            self._animal_state.name, _fixed_config.stimulus_freq
        )

        _config = TrialConfig(
            level=_levels_config.level,
            stimulation_size=_fixed_config.stimulation_size,
            stimulus_duration=_stimulus_duration,
            time_out=_fixed_config.time_out,
            inter_trial_interval=_fixed_config.inter_trial_interval,
            reward_duration=_fixed_config.reward_duration,
            reward_delay=_fixed_config.reward_delay,
            go=_is_go,
            visual_stimulus_delay=_fixed_config.visual_stimulus_delay,
            stimulus_freq=_fixed_config.stimulus_freq,
            stimulus_freq_duration=_fixed_config.stimulus_freq_duration,
            stimulus_freq_master_amp=_master_amp,
            stimulus_freq_digital_amp=_digital_amp,
            stimulus_interval=_fixed_config.stimulus_interval,
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

        self._task = GNGSiDDetectScene(
            theater,
            session_state.session_config,
            animal_state,
            session_state.session_config.screen_type,
            _config,
            self._presistent_data,
        )

        self._data_logger = DataLogger(
            self._session_state,
            self._animal_state.name,
            self.STAGE_NAME,
            DataLoggerType.JSONL,
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

    def _load_stage_config(self, monkey: str) -> DetectStageConfig:
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

    def _prepare_stimulus_intensity(self, monkey: str, frequency: int):
        bt = choice(([[10, 30], [50, 70]])) if monkey == "wolfgang" else []
        at = [80, 80, 80] if monkey == "wolfgang" else [54,56,58]
        intensity_options = at * 10 + bt

        stimulus_intensity = choice(intensity_options)

        return self._theater.acontroller.get_amp_value(frequency, stimulus_intensity)
