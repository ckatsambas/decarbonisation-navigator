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
    pv.position_step.recompute()
    app.processEvents()
    w.grab().save(str(out / f"step2-{lang}-{pal.name}.png"))
    pv.next_btn.click()
    app.processEvents()
    opt = pv.options_step
    row = next((i for i, r in enumerate(opt.rows) if r.m.key == "rotor_sails" and r.ok), 0)
    opt.table.setCurrentCell(row, 1)
    app.processEvents()
    w.grab().save(str(out / f"step3-{lang}-{pal.name}.png"))
    for key in ("rotor_sails", "hull_coating", "propulsion_devices", "biofuel_blend", "methanol_dual_fuel"):
        i = next((i for i, r in enumerate(opt.rows) if r.m.key == key and r.ok), None)
        if i is not None:
            opt.set_ticked(opt.rows[i].m.key, True)
    pv.next_btn.click()
    pri = pv.priorities_step
    fam = pri.levels["families"].bwm
    fam.best.setCurrentIndex(0)
    fam.worst.setCurrentIndex(4)
    for k, v in {"climate": 2, "technology": 4, "operations": 3, "regulation": 7}.items():
        fam.bo[k].slider.setValue(v)
    for k, v in {"money": 7, "climate": 5, "technology": 2, "operations": 3}.items():
        fam.ow[k].slider.setValue(v)
    app.processEvents()
    w.grab().save(str(out / f"step4-{lang}-{pal.name}.png"))
    pv.next_btn.click()
    dec = pv.decision_step
    from navigator.engine.mcda import criteria as MC
    from navigator.engine.mcda import smaa as S
    sim = S.Simulator(opt.model, {a.key: a.measures for a in dec.alts if a.key != MC.DO_NOTHING}, opt.scenario(),
                      opt.mcda_settings(), opt.rules)
    dec.show_smaa(S.run(sim, True, pri.global_weights(), n=10000, kappa=100))
    app.processEvents()
    dec.verticalScrollBar().setValue(dec.verticalScrollBar().maximum() // 3)
    app.processEvents()
    w.grab().save(str(out / f"step5-{lang}-{pal.name}.png"))
    w.new_project()                                   # a standard ship from the library
    pv = w.project_view
    pv.ship_step.set_mode("standard")
    pv.ship_step.std_pane.pick_preset("kamsarmax")
    app.processEvents()
    w.grab().save(str(out / f"step1-standard-{lang}-{pal.name}.png"))
    w.close()
print("saved to", out)
