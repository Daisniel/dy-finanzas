from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from impercontrol.branding import APP_NAME, APP_VERSION, LOGO_ICO_PATH
from impercontrol.context import ApplicationContext
from impercontrol.database import Database
from impercontrol.main_window import MainWindow
from impercontrol.styles import build_app_style
from impercontrol.ui_components import install_global_numeric_input_behavior


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("D&Y")
    app.setApplicationVersion(APP_VERSION)
    if LOGO_ICO_PATH.exists():
        app.setWindowIcon(QIcon(str(LOGO_ICO_PATH)))
    app.setStyle("Fusion")
    install_global_numeric_input_behavior(app)

    try:
        database = Database()
        font_increment = int(float(database.get_setting("font_size_increment", "0")))
        theme_name = database.get_setting("theme_name", "Claro")
        app.setProperty("theme_name", theme_name)
        app.setFont(QFont("Segoe UI", 10 + font_increment))
        app.setStyleSheet(build_app_style(font_increment, theme_name))
        context = ApplicationContext(database)
        window = MainWindow(context)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, f"Error al iniciar {APP_NAME}", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
