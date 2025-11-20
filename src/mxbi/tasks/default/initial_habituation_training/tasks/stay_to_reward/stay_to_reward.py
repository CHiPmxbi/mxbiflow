from datetime import datetime
from math import ceil
from random import uniform
from tkinter import Frame
from typing import TYPE_CHECKING, Final

from mxbi.tasks.default.initial_habituation_training.tasks.stay_to_reward.stay_to_reward_models import (
    DataToShow,
    Result,
    TrialData,
)
from mxbi.utils.aplayer import ToneConfig
from mxbi.utils.tkinter.components.canvas_with_border import CanvasWithInnerBorder
from mxbi.utils.tkinter.components.showdata_widget import ShowDataWidget

if TYPE_CHECKING:
    from concurrent.futures import Future

    from numpy import int16
    from numpy.typing import NDArray

    from mxbi.models.animal import AnimalState
    from mxbi.models.session import ScreenConfig
    from mxbi.tasks.default.initial_habituation_training.stages.models import (
        StageContext,
    )
    from mxbi.tasks.default.initial_habituation_training.tasks.stay_to_reward.stay_to_reward_models import (
        TrialConfig,
    )
    from mxbi.theater import Theater


class DefaultStayToRewardScene:
    def __init__(
        self,
        theater: "Theater",
        animal_state: "AnimalState",
        screen_type: "ScreenConfig",
        trial_config: "TrialConfig",
        context: "StageContext",
        background: "CanvasWithInnerBorder",
    ):
        self._theater: "Final[Theater]" = theater
        self._animal_state: "Final[AnimalState]" = animal_state
        self._screen_type: "Final[ScreenConfig]" = screen_type
        self._trial_config: "Final[TrialConfig]" = trial_config
        self._context: "Final[StageContext]" = context
        self._background = background

        self._play_future: Future[bool] | None = None

        self._tone = self._prepare_stimulus()
        self._standard_reward_stimulus = self._theater.new_standard_reward_stimulus(
            self._trial_config.stimulus_duration
        )

        self._set_stimulus_intensity()
        self._on_trial_start()

    # region public api
    def start(self) -> "TrialData":
        self._theater.mainloop()

        return self._data

    def cancle(self) -> None:
        self._cleanup()

    # endregion

    # region lifecycle
    def _on_trial_start(self) -> None:
        self._create_view()
        self._init_data()
        self._bind_events()
        self._start_tracking_data()

        if (
            self._trial_config.entry_reward
            and self._animal_state.current_animal_session_trial_id == 1
        ):
            self._direct_stimulus()
        else:
            self._start_timing()
            self._stimulus_loop()

    def _on_trial_end(self) -> None:
        if self._play_future is not None:
            self._play_future.add_done_callback(lambda _: self._cleanup())
        else:
            self._cleanup()

    def _cleanup(self) -> None:
        self._data.trial_end_time = datetime.now().timestamp()
        self._data.stay_duration = (
            self._data.trial_end_time - self._data.trial_start_time
        )

        self._theater.aplayer.stop()
        self._trigger.destroy()
        self._show_data_widget.destroy()
        self._theater.root.quit()

    # endregion

    # region views

    def _create_view(self) -> None:
        self._create_background()
        self._create_trigger()
        self._create_show_data_widget()

    def _create_background(self) -> None:
        self._background.place(relx=0.5, rely=0.5, anchor="center")

    def _create_trigger(self) -> None:
        self._trigger = Frame(bg="red", width=0, height=0)
        self._trigger.place(relx=0.5, rely=0.5, anchor="center")
        self._trigger.lower()

    def _create_show_data_widget(self) -> None:
        self._show_data_widget = ShowDataWidget(self._background)
        self._show_data_widget.place(relx=0, rely=1, anchor="sw")
        _data = DataToShow(
            name=self._animal_state.name,
            ald=self._animal_state.current_animal_session_trial_id,
            level=self._animal_state.level,
            id=self._animal_state.trial_id,
            lid=self._animal_state.current_level_trial_id,
            t_dur=f"{self._context.duration} s",
            dur="0 s",
            rewards=0,
        )
        self._show_data_widget.show_data(_data.model_dump())

    # endregion

    # region event binding
    def _bind_events(self) -> None:
        self._trigger.focus_set()

    def _start_timing(self) -> None:
        target_ms = int(self._trial_config.target * 1000)
        self._trigger.after(target_ms, self._on_correct)

    def _stimulus_loop(self) -> None:
        stimulus_interval = uniform(
            self._trial_config.min_stimulus_interval,
            self._trial_config.max_stimulus_interval,
        )
        stimulus_interval_ms = int(stimulus_interval * 1000)

        self._trigger.after(stimulus_interval_ms, self._give_stimulus)

    # endregion

    # region data
    def _start_tracking_data(self) -> None:
        data = DataToShow(
            name=self._animal_state.name,
            ald=self._animal_state.current_animal_session_trial_id,
            level=self._animal_state.level,
            id=self._animal_state.trial_id,
            lid=self._animal_state.current_level_trial_id,
            t_dur=f"{self._context.duration} s",
            dur=f"{int(self._data.stay_duration)} s",
            rewards=self._context.rewards,
        )

        self._data.stay_duration += 1
        self._context.duration += 1

        self._show_data_widget.update_data(data.model_dump())
        self._trigger.after(1000, self._start_tracking_data)

    def _init_data(self) -> None:
        self._data = TrialData(
            level=self._trial_config.level,
            level_trial_id=self._animal_state.current_level_trial_id,
            animal_session_trial_id=self._animal_state.current_animal_session_trial_id,
            animal=self._animal_state.name,
            trial_id=self._animal_state.trial_id,
            trial_start_time=datetime.now().timestamp(),
            trial_end_time=0,
            stay_duration=0,
            result=Result.CORRECT,
        )

    # endregion

    # region stimulus and reward
    def _prepare_stimulus(self) -> "NDArray[int16]":
        unit_duration = (
            self._trial_config.stimulus_freq_duration
            + self._trial_config.stimulus_freq_interval
        )
        times = ceil(self._trial_config.stimulus_duration / unit_duration)
        times = max(times, 1)

        freq_1 = ToneConfig(
            frequency=self._trial_config.stimulus_freq,
            duration=self._trial_config.stimulus_freq_duration,
        )
        freq_2 = ToneConfig(
            frequency=0,
            duration=self._trial_config.stimulus_freq_interval,
        )

        return self._theater.aplayer.generate_stimulus([freq_1, freq_2], times)

    def _set_stimulus_intensity(self) -> None:
        self._theater.acontroller.set_master_volume(self._trial_config.stimulus_density)

    def _give_stimulus(self) -> None:
        self._play_future = self._theater.aplayer.play_stimulus(self._tone)
        self._play_future.add_done_callback(self._on_stimulus_complete)

    def _direct_stimulus(self) -> None:
        self._play_future = self._theater.aplayer.play_stimulus(self._tone)
        self._play_future.add_done_callback(self._on_direct_stimulus_complete)

    def _on_direct_stimulus_complete(self, future: "Future[bool]") -> None:
        if future.result():
            self._trigger.after(0, self._give_reward)

            self._trigger.after(
                self._trial_config.reward_duration,
                lambda: (self._start_timing(), self._stimulus_loop()),
            )

    def _on_stimulus_complete(self, future: "Future[bool]") -> None:
        if future.result():
            self._trigger.after(0, self._give_reward)

            self._trigger.after(self._trial_config.reward_duration, self._stimulus_loop)

    def _on_correct(self) -> None:
        self._data.result = Result.CORRECT
        self._on_trial_end()

    def _give_reward(self) -> None:
        self._context.rewards += 1
        self._theater.reward.give_reward(self._trial_config.reward_duration)

    # endregion
