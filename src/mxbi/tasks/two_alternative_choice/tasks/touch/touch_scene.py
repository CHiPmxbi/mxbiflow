from concurrent.futures import Future
from datetime import datetime
from math import ceil
from tkinter import CENTER, Canvas, Event
from typing import TYPE_CHECKING, Final

from numpy import int16
from numpy.typing import NDArray

from mxbi.tasks.two_alternative_choice.assets.starter import Starter
from mxbi.tasks.two_alternative_choice.models import Result, TouchEvent
from mxbi.tasks.two_alternative_choice.tasks.touch.touch_models import (
    DataToShow,
    TrialData,
)
from mxbi.utils.aplayer import ToneConfig
from mxbi.utils.tkinter.components.canvas_with_border import CanvasWithInnerBorder
from mxbi.utils.tkinter.components.showdata_widget import ShowDataWidget

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import ScreenConfig, SessionConfig
    from mxbi.tasks.two_alternative_choice.models import PersistentData
    from mxbi.tasks.two_alternative_choice.tasks.touch.touch_models import TrialConfig
    from mxbi.theater import Theater


class TwoACTouchScene:
    def __init__(
        self,
        theater: "Theater",
        session: "SessionConfig",
        animal_state: "AnimalState",
        screen_type: "ScreenConfig",
        trial_config: "TrialConfig",
        persistent_data: "PersistentData",
    ) -> None:
        self._theater: "Final[Theater]" = theater
        self._animal_state: "Final[AnimalState]" = animal_state
        self._screen_type: "Final[ScreenConfig]" = screen_type
        self._trial_config: "Final[TrialConfig]" = trial_config
        self._persistent_data: "Final[PersistentData]" = persistent_data

        self._tone = self._prepare_stimulus()
        self._standard_reward_stimulus = self._theater.new_standard_reward_stimulus(
            self._trial_config.stimulus_duration
        )

        self._on_trial_start()

    # region public api
    def start(self) -> "TrialData":
        self._theater.mainloop()

        return self._data

    def cancle(self) -> None:
        self._data.result = Result.CANCEL
        self._theater.aplayer.stop()
        self._on_trial_end()

    # endregion

    # region lifecycle
    def _on_trial_start(self) -> None:
        self._create_view()
        self._init_data()
        self._bind_events()

    def _on_inter_trial(self) -> None:
        self._background.after(
            self._trial_config.inter_trial_interval, self._on_trial_end
        )

    def _on_trial_end(self) -> None:
        self._background.destroy()
        self._theater.root.quit()

    # endregion

    # region views
    def _create_view(self) -> None:
        self._create_background()
        self._create_show_data_widget()
        self._create_target()

    def _create_background(self) -> None:
        self._background = CanvasWithInnerBorder(
            master=self._theater.root,
            bg="black",
            width=self._screen_type.width,
            height=self._screen_type.height,
            border_width=40,
        )

        self._background.place(relx=0.5, rely=0.5, anchor="center")

    def _create_show_data_widget(self) -> None:
        self._show_data_widget = ShowDataWidget(self._background)
        self._show_data_widget.place(relx=0, rely=1.2, anchor="sw")
        data = DataToShow(
            name=self._animal_state.name,
            id=self._animal_state.trial_id,
            level_id=self._animal_state.current_level_trial_id,
            level=self._trial_config.level,
            rewards=self._persistent_data.rewards,
            correct=self._animal_state.correct_trial,
            incorrect=self._persistent_data.incorrect,
            timeout=self._persistent_data.timeout,
        )
        self._show_data_widget.show_data(data.model_dump())

    def _create_target(self) -> None:
        xshift = 240
        xcenter = self._screen_type.width * 0.5 + xshift
        ycenter = self._screen_type.height * 0.5

        self._trigger_canvas = Starter(
            self._background, self._trial_config.stimulation_size
        )
        self._trigger_canvas.place(x=xcenter, y=ycenter, anchor="center")

    def _create_wrong_view(self) -> None:
        self._trigger_canvas = Canvas(
            self._background,
            bg="grey",
            width=self._screen_type.width,
            height=self._screen_type.height,
        )
        self._trigger_canvas.place(relx=0.5, rely=0.5, anchor=CENTER)

    # endregion

    # region event binding
    def _bind_events(self) -> None:
        # Manual reward
        self._background.focus_set()
        self._background.bind("<r>", lambda e: self._give_standard_stimulus())
        self._background.bind("<s>", lambda e: self._theater.caputre(self._background))

        # Trigger event
        self._background.bind("<ButtonPress>", self._on_background_touched)
        self._trigger_canvas.bind("<ButtonPress>", self._on_touched)

        # Timeout event
        self._trigger_canvas.after(self._trial_config.time_out, self._on_timeout)

    # endregion

    # region event handlers
    def _on_touched(self, event: Event) -> None:
        self._data.touch_events.append(
            TouchEvent(time=datetime.now().timestamp(), x=event.x, y=event.y)
        )
        self._background.unbind("<ButtonPress>")
        self._trigger_canvas.destroy()

        future = self._give_stimulus()
        future.add_done_callback(self._on_stimulus_complete)

    def _on_background_touched(self, event: Event) -> None:
        self._data.touch_events.append(
            TouchEvent(time=datetime.now().timestamp(), x=event.x, y=event.y)
        )
        self._background.unbind("<ButtonPress>")
        self._trigger_canvas.destroy()

        self._on_incorrect()

    def _on_correct(self) -> None:
        self._give_reward()
        self._data.result = Result.CORRECT
        self._data.correct_rate = (self._animal_state.correct_trial + 1) / (
            self._animal_state.current_level_trial_id + 1
        )

        self._on_inter_trial()

    def _on_incorrect(self) -> None:
        self._data.result = Result.INCORRECT
        self._data.correct_rate = self._animal_state.correct_trial / (
            self._animal_state.current_level_trial_id + 1
        )

        self._create_wrong_view()
        self._on_inter_trial()

    def _on_timeout(self) -> None:
        self._data.result = Result.TIMEOUT
        self._data.correct_rate = self._animal_state.correct_trial / (
            self._animal_state.current_level_trial_id + 1
        )

        self._create_wrong_view()
        self._on_inter_trial()

    # endregion

    # region sitimulus and reward
    def _prepare_stimulus(self) -> "NDArray[int16]":
        unit_duration = (
            self._trial_config.stimulus_freq_duration
            + self._trial_config.stimulus_freq_duration
        )

        times = ceil(self._trial_config.stimulus_duration / unit_duration)
        times = max(times, 1)

        freq_1 = ToneConfig(
            frequency=self._trial_config.stimulus_freq,
            duration=self._trial_config.stimulus_freq_duration,
        )
        freq_2 = ToneConfig(frequency=0, duration=self._trial_config.stimulus_interval)

        return self._theater.aplayer.generate_stimulus([freq_1, freq_2], times)

    def _give_stimulus(self) -> "Future[bool]":
        return self._theater.aplayer.play_stimulus(self._tone)

    def _on_stimulus_complete(self, future: "Future[bool]") -> None:
        if future.result():
            self._trigger_canvas.after(
                self._trial_config.reward_delay,
                lambda: (self._on_correct()),
            )

    def _give_reward(self) -> None:
        self._persistent_data.rewards += 1
        self._theater.reward.give_reward(self._trial_config.reward_duration)

    def _give_standard_stimulus(self) -> None:
        self._standard_reward_stimulus.play(self._trial_config.reward_duration)

    # endregion

    # region data
    def _init_data(self) -> None:
        self._data = TrialData(
            animal=self._animal_state.name,
            trial_id=self._animal_state.trial_id,
            current_level_trial_id=self._animal_state.current_level_trial_id,
            trial_config=self._trial_config,
            trial_start_time=datetime.now().timestamp(),
            trial_end_time=0,
            result=Result.TIMEOUT,
            correct_rate=0,
            touch_events=[],
        )

    # endregion
