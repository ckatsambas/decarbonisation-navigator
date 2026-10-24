"""Render the main window to PNG without a display: python tools/screenshots.py [out_dir]"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from navigator import i18n  # noqa: E402
from navigator.ui import theme  # noqa: E402
from navigator.ui.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setFont(theme.ui_font(10))
for lang, pal in (("el", theme.DEEP_SEA), ("en", theme.SEAFOAM)):
    i18n.set_language(lang)
    theme.set_current(pal)
    app.setStyleSheet(theme.stylesheet(pal))
    w = MainWindow()
    w.resize(1440, 920)
    w.show()
    app.processEvents()
    w.grab().save(str(out / f"regulation-{lang}-{pal.name}.png"))
    w.close()
print("saved to", out)
