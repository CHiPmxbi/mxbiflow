from tkinter import Canvas


def create_circle(
    x_coord: float, y_coord: float, r: float, canvas: Canvas, color: str
) -> int:
    x0 = x_coord - r
    y0 = y_coord - r
    x1 = x_coord + r
    y1 = y_coord + r
    return canvas.create_oval(x0, y0, x1, y1, outline="", fill=color)


class DetectTarget(Canvas):
    def __init__(self, master, size) -> None:
        super().__init__(
            master, width=size, height=size, bg="lightgray", highlightthickness=0
        )
        # TODO: figure out magic number
        circle_config = [
            (0.5, 2.1, "#616161"),
            (0.5, 3.1, "#bababa"),
            (0.5, 6.3, "white"),
        ]
        for cx, divisor, color in circle_config:
            create_circle(
                size * cx,
                size * cx,
                size / divisor,
                self,
                color,
            )


class DiscriminateTarget(Canvas):
    def __init__(self, master, size) -> None:
        super().__init__(
            master, width=size, height=size, bg="lightgray", highlightthickness=0
        )

        circle_config = [
            (0.5, 0.5, 3.1, "#616161"),
            (0.5, 0.5, 6.3, "white"),
            (0.25, 0.25, 6.3, "#616161"),
            (0.75, 0.25, 6.3, "#616161"),
            (0.25, 0.75, 6.3, "#616161"),
            (0.75, 0.75, 6.3, "#616161"),
        ]

        for cx, cy, divisor, color in circle_config:
            create_circle(
                size * cx,
                size * cy,
                size / divisor,
                self,
                color,
            )
