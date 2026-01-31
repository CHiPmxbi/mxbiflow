from collections.abc import Mapping
from tkinter import Frame, Label, StringVar


class ShowDataWidget(Frame):
    def __init__(
        self,
        master=None,
        width: int = 800,
        height: int = 40,
        fg: str = "black",
        bg: str = "white",
        font: tuple[str, int] | tuple[str, int, str] = ("", 12),
        padding: int = 4,
        **kw,
    ):
        super().__init__(master, width=width, height=height, bg=bg, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)

        self._padding = padding
        self._text_var = StringVar(value="")
        self._label = Label(
            self,
            textvariable=self._text_var,
            bg=bg,
            fg=fg,
            font=font,
            anchor="sw",
            justify="left",
            wraplength=max(width - 2 * padding, 0),
        )
        self._label.pack(fill="both", expand=True, padx=padding, pady=padding)
        self.bind("<Configure>", self._on_resize, add="+")

    def show_data(self, data: Mapping):
        formatted_entries = "; ".join(f"{key}: {value}" for key, value in data.items())
        self._text_var.set(formatted_entries)

    def update_data(self, data: Mapping):
        self.show_data(data)

    def _on_resize(self, event):
        wraplength = max(event.width - 2 * self._padding, 0)
        self._label.configure(wraplength=wraplength)
