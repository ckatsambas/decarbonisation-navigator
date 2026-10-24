"""Entry point: `python -m navigator`."""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME, APP_ORG, i18n
    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setOrganizationName(APP_ORG)
    app.setApplicationName(APP_NAME)
    app.setFont(theme.ui_font(10))
    settings = QSettings()
    lang = settings.value("language", i18n.DEFAULT)
    if lang in i18n.LANGUAGES:
        i18n.set_language(lang)
    theme.set_current(theme.PALETTES.get(settings.value("theme", "dark"), theme.DEEP_SEA))
    app.setStyleSheet(theme.stylesheet(theme.current()))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
