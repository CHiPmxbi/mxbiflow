from collections.abc import Callable
from enum import StrEnum, auto
from typing import cast

from pygame import MOUSEBUTTONDOWN, MOUSEBUTTONUP, Color, Event, Rect
from pygame.sprite import Sprite
from pygame.surface import Surface


class Corner(StrEnum):
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()


class CornerButton(Sprite):
    def __init__(
        self,
        corner: Corner,
        size: int,
        border_width: int,
        on_click: Callable[[], None],
        color: Color | tuple[int, int, int],
        pressed_color: Color | tuple[int, int, int] | None = None,
        margin: int = 0,
        pressed_duration_s: float = 0.1,
    ) -> None:
        super().__init__()

        if size < 1:
            raise ValueError("size must be at least 1")
        if size >= border_width:
            raise ValueError("size must be smaller than border_width")
        if margin < 0:
            raise ValueError("margin must not be negative")
        if size + margin * 2 > border_width:
            raise ValueError("size and margin must fit within border_width")
        if pressed_duration_s < 0:
            raise ValueError("pressed_duration_s must not be negative")

        self._corner = corner
        self._on_click = on_click
        normal_color = self._to_color(color)
        active_color = (
            self._to_color(pressed_color)
            if pressed_color is not None
            else self._darken(normal_color)
        )
        self._margin = margin
        self._pressed_duration_s = pressed_duration_s
        self._pressed_remaining_s = 0.0
        self._normal_image = Surface((size, size))
        self._normal_image.fill(normal_color)
        self._pressed_image = Surface((size, size))
        self._pressed_image.fill(active_color)
        self.image = self._normal_image
        self.rect = self.image.get_rect()

    def handle_event(self, event: Event) -> bool:
        rect = cast(Rect, self.rect)
        if (
            event.type == MOUSEBUTTONDOWN
            and event.button == 1
            and rect.collidepoint(event.pos)
        ):
            self.image = self._pressed_image
            self._pressed_remaining_s = self._pressed_duration_s
            self._on_click()
            return True

        return bool(
            event.type == MOUSEBUTTONUP
            and event.button == 1
            and self._pressed_remaining_s
        )

    def layout(self, screen: Surface) -> None:
        screen_rect = screen.get_rect()
        image = cast(Surface, self.image)
        self.rect = image.get_rect()

        match self._corner:
            case Corner.TOP_LEFT:
                self.rect.topleft = screen_rect.topleft
                self.rect.move_ip(self._margin, self._margin)
            case Corner.TOP_RIGHT:
                self.rect.topright = screen_rect.topright
                self.rect.move_ip(-self._margin, self._margin)
            case Corner.BOTTOM_LEFT:
                self.rect.bottomleft = screen_rect.bottomleft
                self.rect.move_ip(self._margin, -self._margin)
            case Corner.BOTTOM_RIGHT:
                self.rect.bottomright = screen_rect.bottomright
                self.rect.move_ip(-self._margin, -self._margin)

    def update(self, dt_s: float) -> None:
        if self._pressed_remaining_s == 0:
            return

        self._pressed_remaining_s = max(0, self._pressed_remaining_s - dt_s)
        if self._pressed_remaining_s == 0:
            self.image = self._normal_image

    @staticmethod
    def _to_color(color: Color | tuple[int, int, int]) -> Color:
        return color if isinstance(color, Color) else Color(*color)

    @staticmethod
    def _darken(color: Color) -> Color:
        return Color(color.r * 7 // 10, color.g * 7 // 10, color.b * 7 // 10)
