from dataclasses import dataclass
from random import choice
from typing import ClassVar

from pygame import MOUSEBUTTONDOWN, QUIT, Event, Rect, Surface, event, image, transform
from pygame.sprite import Group

from ...assets import APPLE_IMAGES, Corner, CornerButton, create_background
from ...core.context import get_mxbiflow
from ..scene import Scene

_BORDER_WIDTH = 40
_MANUAL_REWARD_DURATION_MS = 1_000


@dataclass
class Asset:
    image: Surface
    rect: Rect


class IDLE(Scene):
    level_table: ClassVar[dict[str, list[int]]] = {}

    def __init__(self) -> None:
        super().__init__()

        self._mxbiflow = get_mxbiflow()

        self._screen_size = self._mxbiflow.mxbi.screen_size
        self._background = create_background(
            (self._screen_size.width, self._screen_size.height),
            border_width=_BORDER_WIDTH,
        )
        self._pos = ((self._screen_size.width // 4) * 3, self._screen_size.height // 2)
        self._vstimulus_size = self._screen_size.width // 2 * 0.75

        self._assets = [
            Asset(
                asset_image := transform.rotate(
                    transform.scale(
                        image.load(path).convert_alpha(),
                        (self._vstimulus_size, self._vstimulus_size),
                    ),
                    -90,
                ),
                asset_image.get_rect(center=self._pos),
            )
            for path in APPLE_IMAGES
        ]

        self._asset = choice(self._assets)
        self._control_buttons = Group(
            CornerButton(
                Corner.TOP_RIGHT,
                _BORDER_WIDTH // 2,
                _BORDER_WIDTH,
                self._give_manual_reward,
                color=(0, 160, 0),
            ),
            CornerButton(
                Corner.BOTTOM_RIGHT,
                _BORDER_WIDTH // 2,
                _BORDER_WIDTH,
                self._request_game_quit,
                color=(200, 0, 0),
            ),
        )

    def start(self) -> None:
        self._running = True

    def quit(self) -> None:
        self._running = False

    def handle_event(self, event: Event) -> None:
        if event.type == MOUSEBUTTONDOWN and event.button == 1:
            any(button.handle_event(event) for button in self._control_buttons)

    def update(self, dt_s: float) -> None:
        self._control_buttons.update(dt_s)

    def draw(self, screen: Surface) -> None:
        screen.blit(self._background, (0, 0))
        screen.blit(self._asset.image, self._asset.rect)
        for button in self._control_buttons:
            button.layout(screen)
        self._control_buttons.draw(screen)

    def _give_manual_reward(self) -> None:
        self._mxbiflow.mxbi.rewarder.give_reward(_MANUAL_REWARD_DURATION_MS)

    def _request_game_quit(self) -> None:
        event.post(Event(QUIT))
