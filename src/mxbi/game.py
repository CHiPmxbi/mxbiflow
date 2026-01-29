from __future__ import annotations

import queue
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional

import pygame
from pygame.event import Event

from .scene_protocol import SceneProtocol
from .models.animal import Animals
from pymxbi import get_mxbi, MXBI
from pymxbi.detector.detector import DetectionResult, DetectorEvent


EVT_DETECTOR = pygame.USEREVENT + 1


@dataclass(frozen=True)
class DetectorMsg:
    kind: str
    animal: Optional[str]


class SceneManager:
    def __init__(self) -> None:
        self.current: SceneProtocol | None = None
        self._pending: SceneProtocol | None = None

    def switch(self, scene: SceneProtocol, defer: bool = True) -> None:
        if defer:
            self._pending = scene
        else:
            self._switch(scene)

    def _switch(self, next_scene: SceneProtocol) -> None:
        prev = self.current
        if prev is not None:
            prev.quit()

        self.current = next_scene
        next_scene.start()

    def apply_pending(self) -> None:
        if self._pending is None:
            return
        next_scene = self._pending
        self._pending = None
        self._switch(next_scene)

    def handle_event(self, event: Event) -> None:
        if self.current:
            self.current.handle_event(event)

    def update(self, dt_s: float) -> None:
        if self.current:
            self.current.update(dt_s)

    def draw(self, screen: pygame.Surface) -> None:
        if self.current:
            self.current.draw(screen)


class DetectorBridge:
    def __init__(
        self,
        mxbi: MXBI,
        out_q: queue.SimpleQueue[DetectorMsg],
    ) -> None:
        self._mxbi = mxbi
        self._q = out_q
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        # detector 初始化 & 注册回调
        self._mxbi.detector.begin()
        self._mxbi.detector.register_event(
            DetectorEvent.ANIMAL_ENTERED, self._emit_entered
        )
        self._mxbi.detector.register_event(DetectorEvent.ANIMAL_LEFT, self._emit_left)
        self._mxbi.detector.register_event(
            DetectorEvent.ANIMAL_CHANGED, self._emit_changed
        )
        self._mxbi.detector.register_event(
            DetectorEvent.ANIMAL_REMAINED, self._emit_remained
        )
        self._mxbi.detector.register_event(
            DetectorEvent.ANIMAL_RETURNED, self._emit_returned
        )
        self._mxbi.detector.register_event(
            DetectorEvent.FAULT_DETECTED, self._emit_fault
        )

    def _emit(self, kind: str, animal: Optional[str]) -> None:
        # ✅ 线程安全：只入队
        self._q.put(DetectorMsg(kind=kind, animal=animal))

    def _emit_entered(self, detection_result: DetectionResult) -> None:
        self._emit(
            "entered", detection_result.animal_id or detection_result.animal_name
        )

    def _emit_left(self, detection_result: DetectionResult) -> None:
        self._emit("left", detection_result.animal_id or detection_result.animal_name)

    def _emit_changed(self, detection_result: DetectionResult) -> None:
        self._emit(
            "changed", detection_result.animal_id or detection_result.animal_name
        )

    def _emit_remained(self, detection_result: DetectionResult) -> None:
        self._emit(
            "remained", detection_result.animal_id or detection_result.animal_name
        )

    def _emit_returned(self, detection_result: DetectionResult) -> None:
        self._emit(
            "returned", detection_result.animal_id or detection_result.animal_name
        )

    def _emit_fault(self, detection_result: DetectionResult) -> None:
        self._emit("fault", detection_result.animal_id or detection_result.animal_name)


class Scheduler:
    def __init__(
        self,
        animals: Animals,
        scene_manager: SceneManager,
        scenes: Mapping[str, type[SceneProtocol]],
    ) -> None:
        self._animals = animals
        self._scene_manager = scene_manager
        self._scenes = scenes

        self._current_animal: Optional[str] = "mock_001"
        self._need_refresh = True

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != EVT_DETECTOR:
            return

        kind: str = event.kind
        animal: Optional[str] = event.animal

        # 统一折算为“当前动物”
        if kind in ("entered", "changed", "returned", "remained"):
            self._current_animal = animal
        elif kind in ("left", "fault"):
            # 简化：left 直接置空（如果你有 left->entered 的闪烁问题，可以做 debounce）
            self._current_animal = None

        self._need_refresh = True

    def update(self) -> None:
        current = self._scene_manager.current
        if current is not None and current.running is not True:
            current.decide()
            self._need_refresh = True

        if self._need_refresh:
            self._need_refresh = False
            self._refresh_by_state()

    def _refresh_by_state(self) -> None:
        animal = self._current_animal
        if animal is None:
            self._scene_manager.switch(self._scenes["size_reduction"]())
            return

        animal_state = self._animals.root[animal]
        stage = getattr(animal_state.state, "active_stage", None)
        if stage is None:
            self._scene_manager.switch(self._scenes["size_reduction"]())
            return

        self._scene_manager.switch(self._scenes[stage]())


class Game:
    def __init__(
        self,
        animals: Animals,
        scene_manager: SceneManager,
        scenes: Mapping[str, type[SceneProtocol]],
    ) -> None:
        print(animals.root.keys())
        pygame.init()

        self._animals = animals
        self._scene_manager = scene_manager
        self._scenes = scenes

        self._screen = pygame.display.set_mode((1024, 600))
        self._clock = pygame.time.Clock()
        self._running = True

        self._mxbi = get_mxbi()

        # ✅ 后台线程 -> 主线程桥梁
        self._detector_q: "queue.SimpleQueue[DetectorMsg]" = queue.SimpleQueue()
        self._detector_binder = DetectorBridge(self._mxbi, self._detector_q)
        self._detector_binder.start()

        self._scheduler = Scheduler(self._animals, self._scene_manager, self._scenes)

    def _flush_detector_queue_into_pygame_events(self) -> None:
        """
        主线程安全地把后台线程入队消息转换为 pygame event
        """
        while True:
            try:
                msg = self._detector_q.get_nowait()
            except queue.Empty:
                break

            pygame.event.post(
                pygame.event.Event(EVT_DETECTOR, kind=msg.kind, animal=msg.animal)
            )

    def play(self) -> None:
        while self._running:
            dt = self._clock.tick(60) / 1000.0

            # ✅ 先注入 detector 事件到 pygame 队列
            self._flush_detector_queue_into_pygame_events()

            # ✅ 再统一消费 pygame 事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    continue

                # 先让 Scheduler 处理业务事件（detector）
                self._scheduler.handle_event(event)

                # 再交给场景处理输入等
                self._scene_manager.handle_event(event)

            self._scene_manager.update(dt)
            self._scheduler.update()
            self._scene_manager.draw(self._screen)
            self._scene_manager.apply_pending()

            pygame.display.flip()

    def quit(self) -> None:
        pygame.quit()
