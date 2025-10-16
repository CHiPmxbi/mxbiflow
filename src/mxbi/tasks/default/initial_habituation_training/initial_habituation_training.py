from datetime import datetime
from typing import TYPE_CHECKING, Final

from mxbi.data_logger import DataLogger
from mxbi.models.animal import ScheduleCondition
from mxbi.tasks.default.initial_habituation_training.models import (
    DataToShow,
    DetectStageConfig,
    TrialData,
    config,
)
from mxbi.utils.logger import logger
from mxbi.utils.tkinter.components.canvas_with_border import CanvasWithInnerBorder
from mxbi.utils.tkinter.components.showdata_widget import ShowDataWidget

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater


class InitialHabituationTraining:
    STAGE_NAME: Final[str] = "DEFAULT_INITIAL_HABITUATION_TRAINING"

    def __init__(
        self,
        theater: "Theater",
        session_state: "SessionState",
        animal_state: "AnimalState",
    ) -> None:
        self._theater: "Final[Theater]" = theater
        self._session_state: "Final[SessionState]" = session_state
        self._animal_state: "Final[AnimalState]" = animal_state

        self._stage_config = self._load_stage_config(animal_state.name)
        self._data_logger = DataLogger(
            self._session_state, self._animal_state.name, self.STAGE_NAME
        )
        self._reward_times = 0

        self._on_trial_start()

    def start(self) -> "Feedback":
        self._theater.mainloop()

        self._data_logger.save_jsonl(self._data.model_dump())
        logger.debug(
            f"{self.STAGE_NAME}: "
            f"session_id={self._session_state.session_id}, "
            f"animal_name={self._animal_state.name}, "
            f"trial_id={self._animal_state.trial_id}, "
            f"reward_times={self._data.rewards}, "
            f"stay_duration={self._data.stay_duration:.3f}"
        )
        return True

    def _on_trial_start(self) -> None:
        self._create_view()
        self._init_data()
        self._bind_events()
        # self._start_reward_loop()
        self._start_tracking_data()

    def _create_view(self) -> None:
        self._create_background()
        self._create_show_data_widget()

    def _create_background(self) -> None:
        self._background = CanvasWithInnerBorder(
            self._theater.root,
            width=self._session_state.session_config.screen_type.width,
            height=self._session_state.session_config.screen_type.height,
            bg="black",
            border_width=40,
        )

        self._background.place(relx=0.5, rely=0.5, anchor="center")

    def _create_show_data_widget(self) -> None:
        self._show_data_widget = ShowDataWidget(self._background)
        self._show_data_widget.place(relx=0, rely=1, anchor="sw")
        _data = DataToShow(
            name=self._animal_state.name,
            id=self._animal_state.trial_id,
            dur="0 s",
            rewards=0,
        )
        self._show_data_widget.show_data(_data.model_dump())

    def _bind_events(self) -> None:
        # Manual reward
        self._background.focus_set()
        self._background.bind("<r>", lambda e: self._give_reward())

    def _start_reward_loop(self) -> None:
        self._give_reward()
        self._data.rewards[datetime.now().timestamp()] = self._reward_times
        self._background.after(
            self._stage_config.params.stay_duration, self._start_reward_loop
        )

    def _start_tracking_data(self) -> None:
        self._data.stay_duration = (
            datetime.now().timestamp() - self._data.trial_start_time
        )
        data = DataToShow(
            name=self._animal_state.name,
            id=self._animal_state.trial_id,
            dur=f"{int(self._data.stay_duration)} s",
            rewards=self._reward_times,
        )
        self._show_data_widget.update_data(data.model_dump())
        self._background.after(1000, self._start_tracking_data)

    def _give_reward(self) -> None:
        self._reward_times += 1
        self._theater.reward.give_reward(self._stage_config.params.reward_duration)

    def _load_stage_config(self, monkey: str) -> DetectStageConfig:
        stage_config = config.root.get(monkey) or config.root.get("default")
        if stage_config is None:
            raise ValueError("No default stage config found")
        return stage_config

    def quit(self) -> None:
        self._on_trial_end()

    def _on_trial_end(self) -> None:
        self._data.trial_end_time = datetime.now().timestamp()
        self._data.stay_duration = (
            self._data.trial_end_time - self._data.trial_start_time
        )
        self._background.destroy()
        self._theater.root.quit()

    def on_idle(self) -> None:
        self.quit()

    def on_return(self) -> None: ...

    @property
    def condition(self) -> "ScheduleCondition | None":
        return getattr(self._stage_config, "condition", None)

    def _init_data(self) -> None:
        self._data = TrialData(
            animal=self._animal_state.name,
            trial_id=self._animal_state.trial_id,
            trial_start_time=datetime.now().timestamp(),
            trial_end_time=0,
            stay_duration=0,
            rewards={},
        )
