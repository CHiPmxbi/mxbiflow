from pygame import Event, Surface
from pygame.sprite import Group
from ..scene_protocol import SceneProtocol
from .target import RectCircleSprite
from pymxbi import get_mxbi
from ..infra.eventbus import event_bus

import pygame


class SizeReductionStage:
    def __init__(self) -> None:
        self._mxbi = get_mxbi()
        pos = (
            pygame.display.get_window_size()[0] // 2,
            pygame.display.get_window_size()[1] // 2,
        )
        size = (100, 100)
        rect_color = (255, 0, 0)
        circle_color = (0, 0, 255)
        radius = 50
        self._target = RectCircleSprite(pos, size, rect_color, circle_color, radius)

        self._target_group = Group()
        self._target_group.add(self._target)

        event_bus.subscribe("reward", self.give_reward)

    def give_reward(self, reward_ms: int) -> None:
        self._mxbi.rewarder.give_reward(reward_ms)

    def handle_event(self, event: Event) -> None:
        self._target.handle_event(event, pygame.display.get_window_size())

    def update(self, dt_s: float) -> None:
        self._target.update(dt_s)

    def draw(self, screen: Surface) -> None:
        self._target_group.draw(screen)

    def decide(self) -> type[SceneProtocol]: ...

    @property
    def running(self) -> bool:
        return True
