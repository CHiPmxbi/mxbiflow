from tkinter import Canvas


def create_circle(
    x_coord: float, y_coord: float, r: float, canvas: Canvas, color: str
) -> int:
    x0 = x_coord - r
    y0 = y_coord - r
    x1 = x_coord + r
    y1 = y_coord + r
    return canvas.create_oval(x0, y0, x1, y1, outline="", fill=color)
