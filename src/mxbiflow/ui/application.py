import sys

from PySide6.QtWidgets import QApplication


def require_application() -> QApplication:
    """Return a Qt application configured for sequential dialogs."""
    application = QApplication.instance()
    if application is None:
        application = QApplication(sys.argv)
    if not isinstance(application, QApplication):
        raise TypeError("The active Qt application is not a QApplication")

    application.setQuitOnLastWindowClosed(False)
    return application
