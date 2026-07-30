from pygame import Color, font
from pygame.surface import Surface


class ResultWidget:
    def __init__(
        self,
        text: str,
        border_width: int,
        color: Color | tuple[int, int, int] = (255, 255, 255),
        horizontal_margin: int = 8,
        vertical_margin: int = 10,
    ) -> None:
        if border_width < 1:
            raise ValueError("border_width must be at least 1")
        if horizontal_margin < 0:
            raise ValueError("horizontal_margin must not be negative")
        if vertical_margin < 0:
            raise ValueError("vertical_margin must not be negative")
        if vertical_margin * 2 >= border_width:
            raise ValueError("vertical_margin leaves no space for text")

        self._text = text
        self._border_width = border_width
        self._color = color
        self._horizontal_margin = horizontal_margin
        self._vertical_margin = vertical_margin
        self._fonts: dict[int, font.Font] = {}
        self._cached_surface: Surface | None = None
        self._cached_key: tuple[str, int] | None = None

    def set_text(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self._cached_surface = None
            self._cached_key = None

    def draw(self, screen: Surface) -> None:
        if not self._text:
            return

        border_height = min(self._border_width, screen.get_height())
        max_height = border_height - self._vertical_margin * 2
        if max_height < 1:
            return

        text_surface = self._get_text_surface(max_height)
        x = self._horizontal_margin
        y = (
            screen.get_height()
            - border_height
            + self._vertical_margin
            + (max_height - text_surface.get_height()) // 2
        )
        screen.blit(text_surface, (x, y))

    def _get_text_surface(self, max_height: int) -> Surface:
        cache_key = (self._text, max_height)
        if self._cached_surface is not None and self._cached_key == cache_key:
            return self._cached_surface

        if not font.get_init():
            font.init()

        for font_size in range(max_height, 0, -1):
            text_font = self._fonts.get(font_size)
            if text_font is None:
                text_font = font.Font(None, font_size)
                self._fonts[font_size] = text_font
            text_surface = text_font.render(self._text, True, self._color)
            if text_surface.get_height() <= max_height:
                self._cached_surface = text_surface
                self._cached_key = cache_key
                return text_surface

        raise RuntimeError("Unable to render result text within the border height")
