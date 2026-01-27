from concurrent.futures import Future
from datetime import datetime
from queue import Empty, SimpleQueue
from tkinter import CENTER, Canvas, Event, TclError
from typing import TYPE_CHECKING, Callable, Final

from mxbi.tasks.GNGSiD.models import Result, TouchEvent
from mxbi.tasks.GNGSiD.tasks.discriminate.discriminate_models import (
    DataToShow,
    TrialConfig,
    TrialData,
)
from mxbi.tasks.GNGSiD.tasks.utils.targets import DiscriminateTarget
from mxbi.utils.aplayer import StimulusSequenceUnit
from mxbi.utils.tkinter.components.canvas_with_border import CanvasWithInnerBorder
from mxbi.utils.tkinter.components.showdata_widget import ShowDataWidget
from mxbi.utils.logger import logger

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import ScreenConfig, SessionConfig
    from mxbi.tasks.GNGSiD.models import PersistentData
    from mxbi.theater import Theater


class GNGSiDDiscriminateScene:
    def __init__(
        self,
        theater: "Theater",
        session_config: "SessionConfig",
        animal_state: "AnimalState",
        screen_type: "ScreenConfig",
        trial_config: "TrialConfig",
        persistent_data: "PersistentData",
    ) -> None:
        # Track shared dependencies and trial configuration
        self._theater: Final[Theater] = theater
        self._session_config = session_config
        self._animal_state: Final[AnimalState] = animal_state
        self._screen_type: Final[ScreenConfig] = screen_type
        self._trial_config: Final[TrialConfig] = trial_config
        self._persistent_data: Final["PersistentData"] = persistent_data

        # NOTE: Scheduler callbacks may call task.quit() from non-Tk threads.
        # Keep all Tk operations on the Tk main thread by dispatching through a queue
        # drained via root.after().
        self._ended = False
        self._result_finalized = False
        self._after_ids: set[str] = set()
        self._ui_queue: SimpleQueue[Callable[[], None]] = SimpleQueue()

        self._ui_dispatch_after_id: str | None = None
        self._stage_timeout_after_id: str | None = None
        self._auto_result_after_id: str | None = None
        self._attention_poll_after_id: str | None = None
        self._reward_after_id: str | None = None
        self._inter_trial_after_id: str | None = None
        self._reward_adjust_after_ids: list[str] = []
        self._attention_future: Future[bool] | None = None

        # Build stimulus units for attention, high, and low tones
        attention_unit = self._build_stimulus_unit(
            frequency=trial_config.stimulus_freq_low,
            duration=trial_config.stimulus_freq_low_duration,
            master_volume=trial_config.stimulus_freq_low_master_amp,
            digital_volume=trial_config.stimulus_freq_low_digital_amp,
        )
        high_unit = self._build_stimulus_unit(
            frequency=trial_config.stimulus_freq_high,
            duration=trial_config.stimulus_freq_high_duration,
            master_volume=trial_config.stimulus_freq_high_master_amp,
            digital_volume=trial_config.stimulus_freq_high_digital_amp,
        )
        low_unit = self._build_stimulus_unit(
            frequency=trial_config.stimulus_freq_low,
            duration=trial_config.stimulus_freq_low_duration,
            master_volume=trial_config.stimulus_freq_low_master_amp,
            digital_volume=trial_config.stimulus_freq_low_digital_amp,
        )

        # Pre-compute the stimuli sequences and timing values used in the trial
        self._attention_stimulus = self._prepare_stimulus(
            [attention_unit], trial_config.attention_duration
        )

        # Calculate total response duration including stimulus duration and extra response time
        self._response_duration = (
            self._trial_config.stimulus_duration
            + self._trial_config.extra_response_time
        )

        self._reward_duration = self._trial_config.reward_duration

        if trial_config.is_stimulus_trial:
            stimulus_units = [high_unit, low_unit]
        else:
            stimulus_units = [attention_unit]
        self._stimulus = self._prepare_stimulus(
            stimulus_units, self._trial_config.stimulus_duration
        )

        self._standard_reward_stimulus = self._theater.new_standard_reward_stimulus(
            self._trial_config.stimulus_duration
        )

        self._start_ui_dispatcher()
        self._on_trial_start()

    # region public api
    def start(self) -> TrialData:
        self._theater.mainloop()
        return self._data

    def cancle(self) -> None:
        self._theater.aplayer.stop()
        self._request_ui(self._cancel_on_ui)

    # endregion

    # region ui thread helpers
    def _request_ui(self, action: Callable[[], None]) -> None:
        self._ui_queue.put(action)

    def _start_ui_dispatcher(self) -> None:
        self._ui_dispatch_after_id = self._after(10, self._drain_ui_queue)

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                action = self._ui_queue.get_nowait()
            except Empty:
                break

            try:
                action()
            except Exception:
                logger.exception("Error while handling queued UI action")

        if self._ended:
            return

        self._ui_dispatch_after_id = self._after(10, self._drain_ui_queue)

    def _after(self, delay_ms: int, callback: Callable, *args) -> str:
        after_id: str | None = None

        def wrapped(*wrapped_args) -> None:
            if after_id is not None:
                self._after_ids.discard(after_id)

            if self._ended:
                return

            callback(*wrapped_args)

        after_id = self._theater.root.after(delay_ms, wrapped, *args)
        self._after_ids.add(after_id)
        return after_id

    def _cancel_after(self, after_id: str | None) -> None:
        if after_id is None:
            return

        try:
            self._theater.root.after_cancel(after_id)
        except TclError:
            pass
        finally:
            self._after_ids.discard(after_id)

    def _cancel_all_afters(self) -> None:
        for after_id in list(self._after_ids):
            self._cancel_after(after_id)
        self._after_ids.clear()

    def _safe_destroy(self, widget) -> None:
        if widget is None:
            return
        try:
            widget.destroy()
        except TclError:
            pass

    # endregion

    # region lifecycle
    def _on_trial_start(self) -> None:
        self._create_view()
        self._init_data()
        self._bind_first_stage()

    def _on_inter_trial(self) -> None:
        self._cancel_after(self._inter_trial_after_id)
        self._inter_trial_after_id = self._after(
            self._trial_config.inter_trial_interval, self._on_trial_end
        )

    def _on_trial_end(self) -> None:
        if self._ended:
            return

        self._ended = True
        self._data.trial_end_time = datetime.now().timestamp()

        self._cancel_all_afters()

        self._safe_destroy(getattr(self, "_trigger_canvas", None))
        self._safe_destroy(getattr(self, "_background", None))
        try:
            self._theater.root.quit()
        except TclError:
            pass

    # endregion

    # region views
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
            stimulus=self._trial_config.is_stimulus_trial,
        )
        self._show_data_widget.show_data(data.model_dump())

    def _create_target(self) -> None:
        x_shift = 240
        x_center = self._screen_type.width * 0.5 + x_shift
        y_center = self._screen_type.height * 0.5

        self._trigger_canvas = DiscriminateTarget(
            self._background, self._trial_config.stimulation_size
        )
        self._trigger_canvas.place(x=x_center, y=y_center, anchor="center")

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
        self._cancel_after(self._stage_timeout_after_id)
        self._stage_timeout_after_id = self._after(
            self._trial_config.time_out, self._on_timeout
        )

    def _bind_second_stage(self) -> None:
        self._reward_duration = self._trial_config.reward_duration
        self._trigger_canvas.bind("<ButtonPress>", self._on_second_touched)
        if self._trial_config.is_stimulus_trial:
            self._cancel_after(self._auto_result_after_id)
            self._auto_result_after_id = self._after(
                self._response_duration, self._on_incorrect
            )
            self._schedule_reward_adjustments()
        else:
            self._cancel_after(self._auto_result_after_id)
            self._auto_result_after_id = self._after(
                self._trial_config.stimulus_duration, self._on_correct
            )

    # endregion

    # region event handlers
    def _on_first_touched(self, event: Event) -> None:
        if self._ended or self._result_finalized:
            return

        self._cancel_after(self._stage_timeout_after_id)
        self._safe_destroy(self._trigger_canvas)
        self._record_touch(event)
        self._attention_future = self._give_stimulus(self._attention_stimulus)
        self._poll_attention_future()

    def _start_stimulus_stage(self, future: Future) -> None:
        if self._ended or self._result_finalized:
            return

        try:
            ok = future.result()
        except Exception:
            logger.exception("Attention stimulus playback failed")
            return

        if not ok:
            return

        self._give_stimulus(self._stimulus)
        self._after(0, self._prepare_second_stage)

    def _prepare_second_stage(self) -> None:
        if self._ended or self._result_finalized:
            return

        self._create_target()
        self._bind_second_stage()

    def _on_second_touched(self, event: Event) -> None:
        if self._ended or self._result_finalized:
            return

        self._cancel_after(self._auto_result_after_id)
        self._cancel_reward_adjustments()
        self._record_touch(event)

        if self._trial_config.is_stimulus_trial:
            self._on_correct()
        else:
            self._on_incorrect()

    def _poll_attention_future(self) -> None:
        if self._ended or self._result_finalized:
            return

        future = self._attention_future
        if future is None:
            return

        if future.done():
            self._attention_poll_after_id = None
            self._start_stimulus_stage(future)
            return

        self._attention_poll_after_id = self._after(10, self._poll_attention_future)

    def _record_touch(self, event: Event) -> None:
        self._data.touch_events.append(
            TouchEvent(time=datetime.now().timestamp(), x=event.x, y=event.y)
        )

    # endregion

    # region result handlers
    def _on_correct(self) -> None:
        if self._ended or self._result_finalized:
            return
        self._result_finalized = True

        self._theater.aplayer.stop()
        self._cancel_after(self._stage_timeout_after_id)
        self._cancel_after(self._auto_result_after_id)
        self._cancel_after(self._attention_poll_after_id)
        self._cancel_reward_adjustments()
        self._safe_destroy(self._trigger_canvas)

        self._cancel_after(self._reward_after_id)
        self._reward_after_id = self._after(
            self._trial_config.reward_delay, self._give_reward
        )
        self._data.result = Result.CORRECT
        self._data.correct_rate = (self._animal_state.correct_trial + 1) / (
            self._animal_state.current_level_trial_id + 1
        )
        self._on_inter_trial()

    def _on_incorrect(self) -> None:
        if self._ended or self._result_finalized:
            return
        self._result_finalized = True

        self._theater.aplayer.stop()
        self._cancel_after(self._stage_timeout_after_id)
        self._cancel_after(self._auto_result_after_id)
        self._cancel_after(self._attention_poll_after_id)
        self._cancel_reward_adjustments()
        self._safe_destroy(self._trigger_canvas)

        self._data.result = Result.INCORRECT
        self._data.correct_rate = self._animal_state.correct_trial / (
            self._animal_state.current_level_trial_id + 1
        )

        self._create_wrong_view()
        self._on_inter_trial()

    def _on_timeout(self) -> None:
        if self._ended or self._result_finalized:
            return
        self._result_finalized = True

        self._theater.aplayer.stop()
        self._cancel_after(self._stage_timeout_after_id)
        self._cancel_after(self._auto_result_after_id)
        self._cancel_after(self._attention_poll_after_id)
        self._cancel_reward_adjustments()
        self._safe_destroy(getattr(self, "_trigger_canvas", None))
        self._data.result = Result.TIMEOUT
        self._data.correct_rate = self._animal_state.correct_trial / (
            self._animal_state.current_level_trial_id + 1
        )
        self._create_wrong_view()
        self._on_inter_trial()

    # endregion

    def _cancel_on_ui(self) -> None:
        if self._ended:
            return

        self._result_finalized = True
        self._data.result = Result.CANCEL

        self._on_trial_end()

    # region stimulus and reward
    def _build_stimulus_unit(
        self,
        *,
        frequency: int,
        duration: int,
        master_volume: int,
        digital_volume: int,
    ) -> StimulusSequenceUnit:
        unit = StimulusSequenceUnit(
            frequency=frequency,
            duration=duration,
            interval=self._trial_config.stimulus_interval,
        )
        self._configure_unit_volume(unit, master_volume, digital_volume)
        return unit

    def _configure_unit_volume(
        self,
        unit: StimulusSequenceUnit,
        master_volume: int,
        digital_volume: int,
    ) -> None:
        unit.master_volume = master_volume
        unit.digital_volume = digital_volume

    def _prepare_stimulus(
        self, stimulus_units: list[StimulusSequenceUnit], total_duration: int
    ) -> list[StimulusSequenceUnit]:
        return self._theater.aplayer.generate_stimulus_sequence(
            stimulus_units, total_duration
        )

    def _give_stimulus(
        self, stimulus_units: list[StimulusSequenceUnit]
    ) -> "Future[bool]":
        return self._theater.aplayer.play_stimulus_sequence(stimulus_units)

    def _give_reward(self) -> None:
        self._persistent_data.rewards += 1
        self._theater.reward.give_reward(self._reward_duration)

    def _give_standard_stimulus(self) -> None:
        self._standard_reward_stimulus.play(self._trial_config.reward_duration)

    def _schedule_reward_adjustments(self) -> None:
        self._cancel_reward_adjustments()
        self._reward_adjust_after_ids.append(
            self._after(
                self._trial_config.medium_reward_threshold,
                self._adjust_reward_duration,
                self._trial_config.medium_reward_duration,
            )
        )
        self._reward_adjust_after_ids.append(
            self._after(
                self._trial_config.stimulus_duration,
                self._adjust_reward_duration,
                self._trial_config.low_reward_duration,
            )
        )

    def _cancel_reward_adjustments(self) -> None:
        for after_id in list(self._reward_adjust_after_ids):
            self._cancel_after(after_id)
        self._reward_adjust_after_ids.clear()

    def _adjust_reward_duration(self, duration: int) -> None:
        self._reward_duration = duration

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
