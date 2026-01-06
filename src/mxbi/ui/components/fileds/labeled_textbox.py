from tkinter import Text
from tkinter.ttk import Frame, Label


class LabeledTextbox(Frame):
    def __init__(
        self, master, label_name: str, width: int = 15, height: int = 1
    ) -> None:
        super().__init__(master)
        label = Label(self, text=label_name, width=width)
        label.grid(row=0, column=0, padx=(10, 0), pady=2, sticky="wn")

        self._textbox = Text(self, height=height)
        self._textbox.grid(row=0, column=1, padx=(0, 10), pady=2, sticky="we")

        self.columnconfigure(index=1, weight=1)

    def get(self) -> str:
        return self._textbox.get("1.0", "end-1c")

    def insert(self, text: str) -> None:
        self._textbox.insert("end", text)

    def set(self, text: str) -> None:
        self._textbox.delete("1.0", "end")
        self._textbox.insert("end", text)


def create_textbox(
    master, label_text: str, width: int = 15, height: int = 1
) -> LabeledTextbox:
    return LabeledTextbox(master, label_text, width, height)


if __name__ == "__main__":
    from tkinter import Tk

    root = Tk()
    root.geometry("400x200")
    root.title("LabeledTextbox Example")

    textbox = create_textbox(root, "Label", height=4)
    textbox.pack(pady=10)

    root.mainloop()
