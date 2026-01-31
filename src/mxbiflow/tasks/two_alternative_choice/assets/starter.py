from tkinter import Canvas

from mxbi.utils.tkinter.create_circle import create_circle


class Starter(Canvas):
    def __init__(self, master, size) -> None:
        super().__init__(
            master, width=size, height=size, bg="blue", highlightthickness=0
        )

        create_circle(
            size * 0.5,
            size * 0.5,
            (size - 1) / 2,
            self,
            "white",
        )


if __name__ == "__main__":
    from tkinter import Tk

    root = Tk()
    root.geometry("300x300")
    Starter(root, 300).pack()
    root.mainloop()
