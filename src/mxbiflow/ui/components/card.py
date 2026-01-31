from PySide6.QtWidgets import QFrame


class CardFrame(QFrame):
    def __init__(self, parent=None, object_name: str = "card"):
        super().__init__(parent=parent)

        self.setObjectName(object_name)
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setStyleSheet(
            f"""
            QFrame#{object_name} {{
                border: 1px solid #C8C8C8;
                border-radius: 6px;
            }}
            """
        )
