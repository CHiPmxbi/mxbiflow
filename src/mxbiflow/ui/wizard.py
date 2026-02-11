from ..scene import SceneManager
from .experiment_panel import ExperimentPanel
from .mxbi_panel import MXBIPanel


def config_wizard(scene_manager: SceneManager):
    """
    Launch the configuration wizard dialog for MXBI setup.

    Parameters
    ----------
    scene_manager : SceneManager
        The scene manager instance providing stage and level information.

    Notes
    -----
    This function creates a Qt application with a two-panel wizard:
    MXBIPanel for MXBI configuration followed by ExperimentPanel for
    experiment settings. The application exits when the wizard completes.
    """
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    mxbi_panel = MXBIPanel()
    experiment_panel = ExperimentPanel(scene_manager)
    mxbi_panel.accepted.connect(experiment_panel.show)
    mxbi_panel.rejected.connect(lambda: sys.exit(0))
    experiment_panel.accepted.connect(app.quit)
    experiment_panel.rejected.connect(lambda: sys.exit(0))

    mxbi_panel.show()

    app.exec()
