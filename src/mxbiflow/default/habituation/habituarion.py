from pygame.surface import Surface
from pygame.event import Event
from ...scene.scene_protocol import SceneProtocol
from mxbiflow import get_mxbiflow
from .models import HabituationResult, Result, load_configs
from datetime import datetime
from random import randint
from pathlib import Path

RESULT = Path(__file__).parent / "result.jsonl"


class Habituarion:
    _running: bool

    def __init__(self) -> None:
        self._mxbiflow = get_mxbiflow()

        self._rewarder = self._mxbiflow.mxbi.rewarder
        self._timer = self._mxbiflow.timer

        self._configs = load_configs()

        self._animal = self._mxbiflow.session.active_animal
        if self._animal is None:
            raise ValueError("No active animal")

        self._config = self._configs.root["default"][self._animal.stage.level]
        self._config.stimulus_interval = randint(
            self._config.min_stimulus_interval, self._config.max_stimulus_interval
        )

        self._result = HabituationResult(
            animals=[self._animal.base_info],
            result=Result.INCORRECT,
            trial_start_time=datetime.now().timestamp(),
            trial_end_time=datetime.now().timestamp(),
            stay_duration=0,
        )

    def start(self) -> None:
        self._running = True
        self._reward_task = self._timer.every(
            self._config.stimulus_interval, self._on_give_reward
        )
        self._target_task = self._timer.after(self._config.target, self._on_correct)

    def _on_correct(self) -> None:
        self._result.result = Result.CORRECT
        self._result.trial_end_time = datetime.now().timestamp()
        self._result.stay_duration = self._config.target
        self.quit()

    def quit(self) -> None:
        self._clean()
        self._result.save(RESULT)
        self._running = False

    def _clean(self) -> None:
        self._timer.cancel(self._reward_task)
        self._timer.cancel(self._target_task)

    def _on_give_reward(self) -> None:
        self._rewarder.give_reward(self._config.reward_dutration)

    def _give_reward(self, duration_ms: int) -> None:
        self._rewarder.give_reward(duration_ms)

    @property
    def running(self) -> bool:
        return self._running

    def handle_event(self, event: Event) -> None: ...

    def update(self, dt_s: float) -> None:
        self._timer.update()

    def draw(self, screen: Surface) -> None: ...

    def decide(self) -> type[SceneProtocol]:
        return type(self)
