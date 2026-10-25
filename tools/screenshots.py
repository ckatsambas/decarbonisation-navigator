"""Render the lobby and the first two steps to PNG without a display.

    python tools/screenshots.py [out_dir] [path/to/mrv.sqlite] [IMO]
"""
# ruff: noqa: E402  (paths are set up before the imports)
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from navigator import i18n
from navigator.data.projects import ProjectStore
from navigator.ui import theme
from navigator.ui.main_window import MainWindow
from navigator.ui.state import AppState

out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
db = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "mrv.sqlite"
imo = sys.argv[3] if len(sys.argv) > 3 else "1013676"
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setFont(theme.ui_font(10))
for lang, pal in (("el", theme.CHART), ("en", theme.NIGHT)):
    i18n.set_language(lang)
    theme.set_current(pal)
    app.setStyleSheet(theme.stylesheet(pal))
    store = ProjectStore(Path(tempfile.mkdtemp()))
    w = MainWindow(AppState(db, bundle=False), store)
    w.resize(1440, 920)
    w.show()
    # two example projects so the lobby is not empty
    for q in ("9565039", imo):
        w.new_project()
        pv = w.project_view
        pv.ship_step.show_imo(q)
        pv.ship_step.detail.use_btn.click()
        pv.next_btn.click()
        pv.position_step.capacity.setValue(82_000 if q == imo else 0)
        pv.position_step.recompute()
        app.processEvents()
        pv.save_now()
    w.show_lobby()
    app.processEvents()
    w.grab().save(str(out / f"lobby-{lang}-{pal.name}.png"))
    w.new_project()
    pv = w.project_view
    pv.ship_step.show_imo(imo)
    app.processEvents()
    w.grab().save(str(out / f"step1-{lang}-{pal.name}.png"))
    pv.ship_step.detail.use_btn.click()
    pv.next_btn.click()
    pv.position_step.capacity.setValue(82_000)
    pv.position_step.recompute()
    app.processEvents()
    w.grab().save(str(out / f"step2-{lang}-{pal.name}.png"))
    w.close()
print("saved to", out)
