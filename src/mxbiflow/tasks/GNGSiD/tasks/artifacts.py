from tkinter import Canvas


class BaseViews:
    def _create_background(self, master, width, height) -> None:
        self._backgroud = Canvas(
            master,
            bg="black",
            width=width,
            height=height,
            highlightthickness=0,
        )
        self._backgroud.place(relx=0.5, rely=0.5, anchor="center")
