from PySide6.QtWidgets import QDialog

from ..core.config_store import ConfigStore
from ..core.offline import set_offline
from ..core.path import get_mxbi_panel_config_path
from ..infra.hardware_config import sync_hardware_config
from ..models.panel import MXBIPanelConfig
from ..scene import SceneManager
from .application import require_application
from .experiment_panel import ExperimentPanel
from .mxbi_panel import MXBIPanel


def run_wizard(scene_manager: SceneManager) -> bool:
    """Run the device and experiment configuration panels in sequence.

    Online, cogmote's hardware preset is synced first. The first panel's
    Offline checkbox then decides how the rest of the process runs.
    """
    _application = require_application()

    if not ConfigStore(get_mxbi_panel_config_path(), MXBIPanelConfig).value.offline:
        sync_hardware_config()
    panel = MXBIPanel()
    if panel.exec() != QDialog.DialogCode.Accepted:
        return False
    set_offline(panel.offline)
    return ExperimentPanel(scene_manager).exec() == QDialog.DialogCode.Accepted
