from pathlib import Path

from .experiment_panel import ExperimentPanel
from .mxbi_panel import MXBIPanel


def config_wizard(
    mxbi_config_path: Path,
    session_config_path: Path,
    options_path: Path,
):
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    mxbi_panel = MXBIPanel(mxbi_config_path, options_path)
    experiment_panel = ExperimentPanel(session_config_path, options_path)
    mxbi_panel.accepted.connect(experiment_panel.show)
    experiment_panel.accepted.connect(app.quit)

    mxbi_panel.show()

    app.exec()
