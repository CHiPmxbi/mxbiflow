from datetime import datetime
from math import ceil
from tkinter import CENTER, Canvas, Event
from typing import TYPE_CHECKING, Final

from mxbi.tasks.GNGSiD.models import Result, TouchEvent
from mxbi.tasks.GNGSiD.tasks.detect.models import DataToShow, TrialConfig, TrialData
from mxbi.tasks.GNGSiD.tasks.utils.targets import DetectTarget
from mxbi.utils.aplayer import ToneConfig
from mxbi.utils.tkinter.components.canvas_with_border import CanvasWithInnerBorder
from mxbi.utils.tkinter.components.showdata_widget import ShowDataWidget

if TYPE_CHECKING:
    from concurrent.futures import Future

    from numpy import int16
    from numpy.typing import NDArray

    from mxbi.models.animal import AnimalState
    from mxbi.models.session import ScreenConfig, SessionConfig
    from mxbi.tasks.GNGSiD.models import PersistentData
    from mxbi.theater import Theater


class GNGSiDDetectScene:
    def __init__(
        self,
        theater: "Theater",
        session_config: "SessionConfig",
        animal_state: "AnimalState",
        screen_type: "ScreenConfig",
        trial_config: "TrialConfig",
        persistent_data: "PersistentData",
    ) -> None:
        self._theater: "Final[Theater]" = theater
        self._animal_state: "Final[AnimalState]" = animal_state
        self._screen_type: "Final[ScreenConfig]" = screen_type
        self._trial_config: "Final[TrialConfig]" = trial_config
        self._persistent_data: Final["PersistentData"] = persistent_data

        self._tone: Final[NDArray[int16]] = self._prepare_stimulus()
        self._standard_reward_stimulus = self._theater.new_standard_reward_stimulus(
            self._trial_config.stimulus_duration
        )

        self._set_stimulus_intensity()

        self._on_trial_start()

    # region public api
    def start(self) -> TrialData:
        self._theater.mainloop()
        return self._data

    def cancle(self) -> None:
        self._data.result = Result.CANCEL
        self._theater.aplayer.stop()
        self._on_trial_end()

    # endregion

    # region Lifecycle
    def _on_trial_start(self) -> None:
        self._create_view()
        self._init_data()
        self._bind_first_stage()

    def _on_inter_trial(self) -> None:
        self._background.after(
            self._trial_config.inter_trial_interval, self._on_trial_end
        )

    def _on_trial_end(self) -> None:
        self._background.destroy()
        self._theater.root.quit()

    # endregion

    # region Views
    def _create_view(self) -> None:
        self._create_background()
        self._create_show_data_view()
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

    def _create_show_data_view(self) -> None:
        self._show_data_widget = ShowDataWidget(self._background)
        self._show_data_widget.place(relx=0, rely=1, anchor="sw")
        data = DataToShow(
            name=self._animal_state.name,
            id=self._animal_state.trial_id,
            level_id=self._animal_state.current_level_trial_id,
            level=self._trial_config.level,
            rewards=self._persistent_data.rewards,
            correct=self._animal_state.correct_trial,
            incorrect=self._persistent_data.incorrect,
            timeout=self._persistent_data.timeout,
            stimulus=self._trial_config.go,
        )
        self._show_data_widget.show_data(data.model_dump())

    def _create_target(self):
        xshift = 240
        xcenter = self._screen_type.width * 0.5 + xshift
        ycenter = self._screen_type.height * 0.5

        self._trigger_canvas = DetectTarget(
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
    def _bind_first_stage(self) -> None:
        self._background.focus_set()
        self._background.bind("<r>", lambda e: self._give_standard_stimulus())
        self._trigger_canvas.bind("<ButtonPress>", self._on_first_touched)
        self._trigger_canvas.after(self._trial_config.time_out, self._on_timeout)

    def _bind_second_stage(self) -> None:
        self._trigger_canvas.bind("<ButtonPress>", self._on_second_touched)

        # TODO: Confirm the waiting time
        if not self._trial_config.go:
            self._trigger_canvas.after(
                self._trial_config.stimulus_duration, self._on_incorrect
            )

    # endregion

    # region event handlers
    def _on_first_touched(self, event: Event) -> None:
        self._trigger_canvas.destroy()
        self._record_touch(event)

        if self._trial_config.go:
            future = self._give_stimulus(self._tone)
            future.add_done_callback(self._on_stimulus_complete)

        self._background.after(
            self._trial_config.visual_stimulus_delay,
            lambda: (self._create_target(), self._bind_second_stage()),
        )

    def _on_second_touched(self, event: Event) -> None:
        self._trigger_canvas.destroy()
        self._record_touch(event)

        if self._trial_config.go:
            self._on_incorrect()
        else:
            future = self._give_stimulus(self._tone)
            future.add_done_callback(self._on_stimulus_complete)

        self._background.after(2000, self._create_target)

    def _record_touch(self, event: Event) -> None:
        self._data.touch_events.append(
            TouchEvent(time=datetime.now().timestamp(), x=event.x, y=event.y)
        )

    # endregion

    # region result handlers
    def _on_correct(self) -> None:
        self._trigger_canvas.destroy()

        self._give_reward()
        self._data.result = Result.CORRECT
        self._data.correct_rate = (self._animal_state.correct_trial + 1) / (
            self._animal_state.current_level_trial_id + 1
        )
        self._on_inter_trial()

    def _on_incorrect(self) -> None:
        self._theater._aplayer.stop()
        self._trigger_canvas.destroy()

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

    # region stimulus and reward
    def _prepare_stimulus(self) -> "NDArray[int16]":
        cycle = (
            self._trial_config.stimulus_freq_duration
            + self._trial_config.stimulus_interval
        )
        repeat = ceil(self._trial_config.stimulus_duration / cycle)
        repeat = max(repeat, 1)

        freq_1 = ToneConfig(
            frequency=self._trial_config.stimulus_freq,
            duration=self._trial_config.stimulus_freq_duration,
        )
        freq_2 = ToneConfig(frequency=0, duration=self._trial_config.stimulus_interval)

        return self._theater.aplayer.generate_stimulus([freq_1, freq_2], repeat)

    def _give_stimulus(self, tone: "NDArray[int16]") -> "Future[bool]":
        return self._theater.aplayer.play_stimulus(tone)

    def _on_stimulus_complete(self, future: "Future[bool]") -> None:
        if future.result():
            self._background.after(self._trial_config.reward_delay, self._on_correct)

    def _give_reward(self, _=None) -> None:
        self._persistent_data.rewards += 1
        self._theater.reward.give_reward(self._trial_config.reward_duration)

    def _set_stimulus_intensity(self) -> None:
        self._theater.acontroller.set_master_volume(
            self._trial_config.stimulus_freq_master_amp
        )
        self._theater.acontroller.set_digital_volume(
            self._trial_config.stimulus_freq_digital_amp
        )

    def _give_standard_stimulus(self) -> None:
        self._standard_reward_stimulus.play(self._trial_config.reward_duration)

    # endregion

    # region data
    def _init_data(self):
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
