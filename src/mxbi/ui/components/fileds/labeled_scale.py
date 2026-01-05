from tkinter import DoubleVar, Misc, StringVar
from tkinter.ttk import Frame, Label, Scale


class LabeledScale(Frame):
    def __init__(
        self,
        master: Misc,
        label_text: str,
        *,
        from_value: float,
        to_value: float,
        default_value: float,
        width: int = 15,
        value_format: str = "{:.2f}",
    ) -> None:
        super().__init__(master)
        self._value = DoubleVar(value=default_value)
        self._value_text = StringVar(value=value_format.format(default_value))
        self._value_format = value_format

        label = Label(self, text=label_text, width=width)
        label.grid(row=0, column=0, padx=(10, 0), pady=2, sticky="w")

        self._scale = Scale(
            self,
            from_=from_value,
            to=to_value,
            orient="horizontal",
            variable=self._value,
            command=self._on_change,
        )
        self._scale.grid(row=0, column=1, padx=(0, 10), pady=2, sticky="ew")

        value_label = Label(self, textvariable=self._value_text, width=8)
        value_label.grid(row=0, column=2, padx=(0, 10), pady=2, sticky="e")

        self.columnconfigure(1, weight=1)

    def _on_change(self, _: str) -> None:
        self._value_text.set(self._value_format.format(self._value.get()))

    def get_float(self) -> float:
        return float(self._value.get())

    def get_int(self) -> int:
        return int(round(self._value.get()))
