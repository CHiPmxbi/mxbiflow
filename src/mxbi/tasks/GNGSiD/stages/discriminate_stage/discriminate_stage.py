from random import choice, choices, randint
from typing import TYPE_CHECKING, Final

from mxbi.data_logger import DataLogger, DataLoggerType
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.GNGSiD.models import PersistentData, Result
from mxbi.tasks.GNGSiD.stages.discriminate_stage.discriminate_stage_models import (
    DiscriminateStageConfig,
    config,
)
from mxbi.tasks.GNGSiD.tasks.discriminate.discriminate_models import TrialConfig
from mxbi.tasks.GNGSiD.tasks.discriminate.discriminate_scene import (
    GNGSiDDiscriminateScene,
)
from mxbi.utils.logger import logger

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater

_presistent_data: dict[str, PersistentData] = {}


class GNGSiDDiscriminateStage:
    STAGE_NAME: Final[str] = "GNGSiD_DISCRIMINATE_STAGE"

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

        _stimulus_config = choice(_fixed_config.stimulus_configs)
        _stimulus_duration = randint(
            _fixed_config.min_stimulus_duration, _fixed_config.max_stimulus_duration
        )

        _is_stimulus_trial = choices(
            [True, False],
            weights=[
                _levels_config.stimulus_trial_prob,
                _levels_config.nostimulus_trial_prob,
            ],
        )[0]

        _high_master_amp, _high_digital_amp = self._prepare_stimulus_intensity(
            animal_state.name, _stimulus_config.stimulus_freq_high
        )
        _low_master_amp, _low_digital_amp = self._prepare_stimulus_intensity(
            animal_state.name, _stimulus_config.stimulus_freq_low
        )

        _config = TrialConfig(
            level=_levels_config.level,
            stimulation_size=_fixed_config.stimulation_size,
            stimulus_duration=_stimulus_duration,
            time_out=_fixed_config.time_out,
            inter_trial_interval=_fixed_config.inter_trial_interval,
            reward_duration=_fixed_config.reward_duration,
            reward_delay=_fixed_config.reward_delay,
            is_stimulus_trial=_is_stimulus_trial,
            visual_stimulus_delay=_fixed_config.visual_stimulus_delay,
            medium_reward_duration=_fixed_config.medium_reward_duration,
            medium_reward_threshold=_fixed_config.medium_reward_threshold,
            low_reward_duration=_fixed_config.low_reward_duration,
            attention_duration=_fixed_config.attention_duration,
            stimulus_freq_low=_stimulus_config.stimulus_freq_low,
            stimulus_freq_low_duration=_stimulus_config.stimulus_freq_low_duration,
            stimulus_freq_low_master_amp=_low_master_amp,
            stimulus_freq_low_digital_amp=_low_digital_amp,
            stimulus_freq_high=_stimulus_config.stimulus_freq_high,
            stimulus_freq_high_duration=_stimulus_config.stimulus_freq_high_duration,
            stimulus_freq_high_master_amp=_high_master_amp,
            stimulus_freq_high_digital_amp=_high_digital_amp,
            stimulus_interval=_fixed_config.stimulus_interval,
            extra_response_time=_fixed_config.extra_response_time,
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

        self._task = GNGSiDDiscriminateScene(
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

    def _load_stage_config(self, monkey: str) -> DiscriminateStageConfig:
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
        stimulus_intensity = choice([54,56,58])

        return self._theater.acontroller.get_amp_value(frequency, stimulus_intensity)
