from tkinter import Canvas


class CanvasWithInnerBorder(Canvas):
    def __init__(
        self,
        master,
        bg: str,
        width: int,
        height: int,
        border_color: str = "white",
        border_width: int = 0,
        **kwargs,
    ) -> None:
        self._width = width
        self._height = height
        self._color = bg
        self._border_width = border_width
        self._border_color = border_color
        self._border_tag = "border"

        super().__init__(
            master,
            bg=self._border_color,
            width=width,
            height=height,
            highlightthickness=0,
            **kwargs,
        )

        self._draw_border()

    def _draw_border(self) -> None:
        self.delete(self._border_tag)
        margin = min(
            self._border_width,
            self._width // 2,
            self._height // 2,
        )
        x0, y0 = margin, margin
        x1, y1 = self._width - margin, self._height - margin

        self.create_rectangle(
            x0, y0, x1, y1, fill=self._color, outline="", tags=self._border_tag
        )

    def set_border_color(self, color: str) -> None:
        self.configure(bg=color)

    def set_border_width(self, width: int) -> None:
        self._border_width = max(1, width)
        self._draw_border()
