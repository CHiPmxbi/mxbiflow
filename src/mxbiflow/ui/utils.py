from .experiment_panel import ExperimentPanel
from .mxbi_panel import MXBIPanel


def config_wizard():
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    mxbi_panel = MXBIPanel()
    experiment_panel = ExperimentPanel()
    mxbi_panel.accepted.connect(experiment_panel.show)
    experiment_panel.accepted.connect(app.quit)

    mxbi_panel.show()

    app.exec()
