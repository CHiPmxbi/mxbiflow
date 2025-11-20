from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel
from datetime import datetime

from mxbi.config import session_config
from mxbi.data_logger import DataLogger, DataLoggerType
from mxbi.detector.detector import Detector, DetectorEvent
from mxbi.detector.detector_factory import DetectorFactory, DorsetLID665v42Config
from mxbi.models.animal import AnimalState
from mxbi.models.scheduler import SchedulerState, ScheduleRunningStateEnum
from mxbi.models.task import TaskEnum
from mxbi.tasks.default.idle_task.idle_scene import IDLEScene
from mxbi.tasks.task_protocol import Task
from mxbi.tasks.task_table import task_table
from mxbi.utils.logger import logger

if TYPE_CHECKING:
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater


class SchedulerEvent(StrEnum):
    TASK_SWITCH = "task_switch"
    LEVEL_CHANGE = "level_change"
    STATE_CHANGE = "state_change"


class SchedulerHistoryRecord(BaseModel):
    event: str
    scheduler_state: str
    running: bool
    animal_name: str | None = None
    task: str | None = None
    level: int | None = None
    trial_id: int | None = None
    current_level_trial_id: int | None = None
    correct_trial: int | None = None
    correct_rate: float | None = None
    previous_state: str | None = None
    new_state: str | None = None
    reason: str | None = None
    previous_task: str | None = None
    previous_level: int | None = None


class Scheduler:
    def __init__(self, theater: "Theater") -> None:
        self._theater = theater
        self._detector: Detector = self._init_detector()

        self._animal_states = {
            animal.name: AnimalState(
                name=animal.name,
                task=animal.task,
                level=animal.level,
                current_level_trial_id=animal.level_trial_id or 0,
            )
            for animal in session_config.value.animals.values()
        }

        self._scheduler_state = SchedulerState(
            running=False,
            state=ScheduleRunningStateEnum.SCHEDULE,
            animal_state=None,
        )
        self._scheduler_state.current_task = None

        self._scheduler_logger = DataLogger(
            self._theater._session_state, "scheduler", "scheduler", DataLoggerType.JSONL
        )

        self._bind_events()

    def _init_detector(self) -> Detector:
        config = self._theater.session_config
        if (
            config.detector_port
            and config.detector_baudrate is not None
            and config.detector_interval is not None
        ):
            detector_config = DorsetLID665v42Config(
                port=config.detector_port,
                baudrate=config.detector_baudrate,
                interval=config.detector_interval,
            )

            return DetectorFactory.create(detector_config, self._theater)

        return DetectorFactory.create(None, self._theater)

    def start(self) -> None:
        self._detector.start()
        self._scheduler_state.running = True
        self._scheduler_loop()

    def quit(self) -> None:
        for animal_state in self._animal_states.values():
            animal_state.trial_id = 0
            animal_state.reset()

        session_config.save()

        self._scheduler_state.running = False
        self._detector.quit()
        if self._scheduler_state.current_task is not None:
            self._scheduler_state.current_task.quit()

    def _bind_events(self) -> None:
        self._theater.register_event_quit(self.quit)
        self._theater.root.bind("<n>", self._on_manual_next_task)
        self._theater.root.bind("<m>", self._on_manual_next_level)

        self._detector.register_event(
            DetectorEvent.ANIMAL_ENTERED, self._on_animal_entered
        )
        self._detector.register_event(
            DetectorEvent.ANIMAL_RETUREND, self._on_animal_returned
        )
        self._detector.register_event(DetectorEvent.ANIMAL_LEFT, self._on_animal_left)
        self._detector.register_event(
            DetectorEvent.ANIMAL_CHANGED, self._on_animal_changed
        )
        self._detector.register_event(
            DetectorEvent.ERROR_DETECTED, self._on_detect_error
        )
        self._detector.register_event(
            DetectorEvent.ANIMAL_STAYED, self._on_animal_stayed
        )

    def _on_manual_next_task(self, _) -> None:
        if not self._scheduler_state.running:
            return

        if self._scheduler_state.animal_state is None:
            logger.warning(
                "No animal selected, unable to start the next task manually."
            )
            return

        if self._scheduler_state.current_task is not None:
            try:
                self._scheduler_state.current_task.quit()
            except Exception:
                logger.exception("Error quitting current task during manual advance")

        self._scheduler_state.current_task = None

        condition = self._scheduler_state.animal_state.condition
        if condition is None or condition.config.next_task is None:
            logger.warning("Manual advance requested but no next task is defined.")
        else:
            previous_task = self._scheduler_state.animal_state.task
            previous_level = self._scheduler_state.animal_state.level

            self._scheduler_state.animal_state.task = condition.config.next_task
            self._scheduler_state.animal_state.level = 0
            self._scheduler_state.animal_state.reset()

            session_config.value.animals[
                self._scheduler_state.animal_state.name
            ].task = self._scheduler_state.animal_state.task

            session_config.save()
            self._log_task_switch(self._scheduler_state.animal_state, previous_task)
            if previous_level != self._scheduler_state.animal_state.level:
                self._log_level_change(
                    self._scheduler_state.animal_state, previous_level
                )

    def _on_manual_next_level(self, _) -> None:
        if not self._scheduler_state.running:
            return

        animal_state = self._scheduler_state.animal_state
        if animal_state is None:
            logger.warning("No animal selected, unable to advance the level manually.")
            return

        if animal_state.condition is None:
            logger.warning(
                "Manual level advance requested but no condition is defined."
            )
            return

        if self._scheduler_state.current_task is not None:
            try:
                self._scheduler_state.current_task.quit()
            except Exception:
                logger.exception(
                    "Error quitting current task during manual level advance"
                )
            self._scheduler_state.current_task = None

        previous_level = animal_state.level
        previous_task = animal_state.task

        self._increase_difficulty(animal_state)

        if animal_state.level == previous_level and animal_state.task == previous_task:
            logger.info(
                "Manual level advance requested but already at the highest level."
            )
            return

    def _scheduler_loop(self) -> None:
        while self._scheduler_state.running:
            match self._scheduler_state.state:
                case ScheduleRunningStateEnum.IDLE:
                    self._run_idle_state()

                case ScheduleRunningStateEnum.SCHEDULE:
                    self._run_schedule_state()

                case ScheduleRunningStateEnum.ERROR:
                    self._run_error_state()

                case _:
                    logger.error(f"Unknown scheduler state: {self._state.state}")
                    self._state.running = False

    def _run_idle_state(self) -> None:
        self._start_system_task(TaskEnum.IDEL)
        self._scheduler_state.current_task = None

    def _run_schedule_state(self) -> None:
        animal_state = self._scheduler_state.animal_state
        if animal_state is None:
            self._transition_to_state(
                ScheduleRunningStateEnum.IDLE, reason="no_animal_selected"
            )
            return

        animal_state.current_animal_session_trial_id += 1

        self._scheduler_state.current_task = self._create_task(animal_state)
        feedback = self._scheduler_state.current_task.start()
        logger.debug(
            f"Task completed: {self._scheduler_state.current_task.__class__.__name__}, "
            f"feedback: {feedback}"
        )

        self._handle_task_feedback(animal_state, feedback)
        self._scheduler_state.current_task = None

    def _run_error_state(self) -> None:
        self._start_system_task(TaskEnum.ERROR)
        self._scheduler_state.current_task = None

    def _start_system_task(self, task_enum: TaskEnum) -> None:
        self._scheduler_state.current_task = task_table[task_enum](
            self._theater,
            self._theater._session_state,
            AnimalState(),
        )
        self._scheduler_state.current_task.start()

    def _create_task(self, animal_state: AnimalState) -> Task:
        task = task_table[animal_state.task](
            self._theater, self._theater._session_state, animal_state
        )

        animal_state.condition = task.condition

        return task

    def _handle_task_feedback(
        self, animal_state: AnimalState, feedback: "Feedback"
    ) -> None:
        if self._scheduler_state.current_task is None:
            return

        animal_state.update(feedback)

        if animal_state.condition is not None:
            animal_config = session_config.value.animals[animal_state.name]
            animal_config.level_trial_id = (
                animal_state.current_level_trial_id
                if animal_state.condition.config.present_level_trial_id
                else None
            )

        self._evaluate_and_adjust_difficulty(animal_state)

    def _get_animal_state(self, animal_name: str) -> AnimalState:
        try:
            return self._animal_states[animal_name]
        except KeyError as e:
            logger.error("Unknown animal name from detector: %s", animal_name)
            raise KeyError(animal_name) from e

    def _evaluate_and_adjust_difficulty(self, state: AnimalState) -> None:
        if state.condition is None:
            return

        config = state.condition.config

        if state.current_level_trial_id < config.evaluation_interval:
            return

        if state.correct_rate >= config.difficulty_increase_threshold:
            self._increase_difficulty(state)
        elif (
            state.correct_rate <= config.difficulty_decrease_threshold
            and config.allow_decrease
        ):
            self._decrease_difficulty(state)

    def _increase_difficulty(self, state: AnimalState) -> None:
        if state.condition is None:
            return

        previous_task = state.task
        previous_level = state.level

        if state.level < state.condition.level_count - 1:
            state.level += 1
            logger.debug(f"Increasing difficulty to level {state.level}")
        else:
            next_task = state.condition.config.next_task
            if next_task is None:
                return

            state.task = next_task
            state.level = 0

        state.reset()

        animal_config = session_config.value.animals.get(state.name)
        if animal_config is not None:
            animal_config.task = state.task
            animal_config.level = state.level
        else:
            logger.warning(
                "Unable to find animal config during difficulty increase: %s",
                state.name,
            )
        session_config.save()
        if state.task != previous_task:
            self._log_task_switch(state, previous_task)
        elif state.level != previous_level:
            self._log_level_change(state, previous_level)

    def _decrease_difficulty(self, state: AnimalState) -> None:
        if state.level > 0:
            previous_level = state.level
            state.level -= 1
            state.reset()
            animal_config = session_config.value.animals.get(state.name)
            if animal_config is not None:
                animal_config.level = state.level
            else:
                logger.warning(
                    "Unable to find animal config during difficulty decrease: %s",
                    state.name,
                )
            session_config.save()
            self._log_level_change(state, previous_level)

    def _on_animal_entered(self, animal_name: str) -> None:
        self._scheduler_state.animal_state = self._get_animal_state(animal_name)

        self._scheduler_state.animal_state.animal_session_start_time = datetime.now().timestamp()

        self._transition_to_state(
            ScheduleRunningStateEnum.SCHEDULE, reason="animal_entered"
        )

        if self._scheduler_state.current_task is not None:
            self._scheduler_state.current_task.quit()

    def _on_animal_returned(self, _: str) -> None:
        if self._scheduler_state.animal_state is not None:
            self._scheduler_state.animal_state.animal_session_start_time = datetime.now().timestamp()

        self._transition_to_state(
            ScheduleRunningStateEnum.SCHEDULE, reason="animal_returned"
        )
        if self._scheduler_state.current_task is not None:
            self._scheduler_state.current_task.on_return()

    def _on_animal_left(self, _: str) -> None:
        if self._scheduler_state.animal_state is not None:
            self._scheduler_state.animal_state.animal_session_start_time = 0.0
            self._scheduler_state.animal_state.leave_session()

        self._transition_to_state(ScheduleRunningStateEnum.IDLE, reason="animal_left")
        if self._scheduler_state.current_task is not None:
            self._scheduler_state.current_task.quit()

    def _on_animal_changed(self, animal_name: str) -> None:
        self._scheduler_state.animal_state = self._get_animal_state(animal_name)
        self._scheduler_state.animal_state.animal_session_start_time = datetime.now().timestamp()
        self._transition_to_state(
            ScheduleRunningStateEnum.SCHEDULE, reason="animal_changed"
        )
        if self._scheduler_state.current_task is not None:
            self._scheduler_state.current_task.quit()

    def _on_animal_stayed(self, _: str) -> None:
        self._transition_to_state(
            ScheduleRunningStateEnum.SCHEDULE, reason="animal_stayed"
        )

        if self._scheduler_state.current_task is None:
            return

        if self._scheduler_state.animal_state is None:
            return

        if self._scheduler_state.animal_state.task == TaskEnum.IDEL:
            return

        if isinstance(self._scheduler_state.current_task, IDLEScene):
            self._scheduler_state.current_task.quit()

    def _on_detect_error(self, _: str) -> None:
        self._transition_to_state(
            ScheduleRunningStateEnum.ERROR, reason="error_detected"
        )
        if self._scheduler_state.current_task is not None:
            self._scheduler_state.current_task.quit()

    def _log_task_switch(
        self, animal_state: AnimalState, previous_task: TaskEnum
    ) -> None:
        if animal_state.task == previous_task:
            return

        record = self._build_history_record(SchedulerEvent.TASK_SWITCH, animal_state)
        record.previous_task = previous_task.name

        self._save_history_record(record)

    def _log_level_change(self, animal_state: AnimalState, previous_level: int) -> None:
        if animal_state.level == previous_level:
            return

        record = self._build_history_record(SchedulerEvent.LEVEL_CHANGE, animal_state)
        record.previous_level = previous_level

        self._save_history_record(record)

    def _transition_to_state(
        self, new_state: ScheduleRunningStateEnum, *, reason: str | None = None
    ) -> None:
        previous_state = self._scheduler_state.state
        if previous_state == new_state:
            return

        self._scheduler_state.state = new_state
        self._log_state_change(previous_state, new_state, reason)

    def _log_state_change(
        self,
        previous_state: ScheduleRunningStateEnum,
        new_state: ScheduleRunningStateEnum,
        reason: str | None,
    ) -> None:
        record = self._build_history_record(
            SchedulerEvent.STATE_CHANGE, self._scheduler_state.animal_state
        )
        record.previous_state = previous_state.name
        record.new_state = new_state.name
        if reason is not None:
            record.reason = reason

        self._save_history_record(record)

    def _build_history_record(
        self, event: SchedulerEvent, animal_state: AnimalState | None
    ) -> SchedulerHistoryRecord:
        return SchedulerHistoryRecord(
            event=event.value,
            scheduler_state=self._scheduler_state.state.name,
            running=self._scheduler_state.running,
            animal_name=animal_state.name if animal_state else None,
            task=animal_state.task.name if animal_state and animal_state.task else None,
            level=animal_state.level if animal_state else None,
            trial_id=animal_state.trial_id if animal_state else None,
            current_level_trial_id=(
                animal_state.current_level_trial_id if animal_state else None
            ),
            correct_trial=animal_state.correct_trial if animal_state else None,
            correct_rate=animal_state.correct_rate if animal_state else None,
        )

    def _save_history_record(self, record: SchedulerHistoryRecord) -> None:
        try:
            self._scheduler_logger.save(record.model_dump(mode="json"))
        except Exception:
            logger.exception("Failed to write scheduler history log")


if __name__ == "__main__":
    # TODO: Add main function
    pass
