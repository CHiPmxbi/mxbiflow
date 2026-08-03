from PySide6.QtWidgets import QDialog

from ..scene import SceneManager
from .application import require_application
from .experiment_panel import ExperimentPanel
from .mxbi_panel import MXBIPanel


def run_wizard(scene_manager: SceneManager) -> bool:
    """Run the device and experiment configuration panels in sequence."""
    _application = require_application()

    if MXBIPanel().exec() != QDialog.DialogCode.Accepted:
        return False
    return ExperimentPanel(scene_manager).exec() == QDialog.DialogCode.Accepted
