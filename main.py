from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.logging_config import configure_logging
from app.paths import get_app_paths
from ui.main_window import MainWindow


APP_USER_MODEL_ID = "SistemasAnaliticos.AutomaticEnvio"


def _configure_windows_taskbar_icon() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def main() -> int:
    _configure_windows_taskbar_icon()
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Automatic")
    app_icon = QIcon(str(get_app_paths().resource("resources/icons/Automatic.png")))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    app.setOrganizationName("Sistemas Analiticos")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
