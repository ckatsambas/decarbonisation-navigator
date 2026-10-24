"""Render the main pages to PNG without a display.

    python tools/screenshots.py [out_dir] [path/to/mrv.sqlite] [search text]
"""
# ruff: noqa: E402  (paths are set up before the imports)
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from navigator import i18n
from navigator.ui import theme
from navigator.ui.main_window import NAV, MainWindow
from navigator.ui.state import AppState

out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
db = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "mrv.sqlite"
query = sys.argv[3] if len(sys.argv) > 3 else "1013676"
keys = [k for _, items in NAV for k, _ in items]
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setFont(theme.ui_font(10))
for lang, pal in (("el", theme.DEEP_SEA), ("en", theme.SEAFOAM)):
    i18n.set_language(lang)
    theme.set_current(pal)
    app.setStyleSheet(theme.stylesheet(pal))
    w = MainWindow(AppState(db))
    w.resize(1440, 920)
    w.show()
    ship_page = w.pages[keys.index("nav.ship")]
    ship_page.search.setText(query)
    ship_page.run_search()
    app.processEvents()
    w.grab().save(str(out / f"ship-{lang}-{pal.name}.png"))
    if ship_page.detail.history:
        ship_page.detail.use_btn.click()
    w.go(keys.index("nav.regulation"))
    app.processEvents()
    w.grab().save(str(out / f"regulation-{lang}-{pal.name}.png"))
    w.close()
print("saved to", out)
