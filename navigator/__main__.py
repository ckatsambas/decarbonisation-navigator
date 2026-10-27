"""Entry point: `python -m navigator`."""
from __future__ import annotations

import sys


def selftest() -> int:
    """Run the whole engine once without a window (used to check packaged builds): bundled EU MRV
    data, power model, measure appraisal, BWM weights, the four rankings, a small SMAA run, the plan
    optimiser and a one-page PDF + Excel report (matplotlib and openpyxl inside the build)."""
    import tempfile
    from pathlib import Path

    import numpy as np

    from .data.mrv import ensure_database
    from .engine import economics as EC
    from .engine import library as L
    from .engine import measures as M
    from .engine import reference as R
    from .engine.compliance import Rules, Scenario
    from .engine.mcda import criteria as C
    from .engine.mcda import ranking as RK
    from .engine.mcda import smaa as S
    from .engine.mcda import weights as W

    db = ensure_database()
    rules, lib = Rules.load(), M.load()
    model = M.model_for(L.profile(R.by_key("bulk:60000-99999"), "deep_sea"))
    sc, st = Scenario(view="ww"), C.Settings()
    keys = ["hull_coating", "rotor_sails", "biofuel_blend"]
    alts = [C.alternative(model, (lib[k],), sc, st, rules, k) for k in keys] + [C.do_nothing()]
    w = W.bwm(0, 4, [1, 2, 3, 4, 8], [8, 4, 3, 2, 1]).weights
    ranks = RK.rank_all(C.matrix(alts), C.global_weights(dict(zip(C.FAMILIES, w, strict=True)), {}), C.MAXIMISE)
    sim = S.Simulator(model, {k: (lib[k],) for k in keys}, sc, st, rules)
    res = S.run(sim, True, None, n=500)
    from .engine import optimise as O
    from .report import ReportData, build_pdf, build_xlsx
    from .report.data import Table
    libd = {m.key: m for m in lib}
    front = O.pareto(model, libd, keys, sc, O.Settings(window=4), rules, points=3)
    rep = ReportData("el", "Έλεγχος", "Kamsarmax", "2026", "test", {}, ["Δοκιμή ελληνικών"], [("a", "b")],
                     measures=Table("t", ["Μέτρο", "ΚΠΑ"], [[k, a.values["npv"]] for k, a in zip(keys, alts, strict=False)],
                                    ["text", "eur"]))
    with tempfile.TemporaryDirectory() as tmp:
        pdf = build_pdf(rep, Path(tmp) / "r.pdf")
        xlsx = build_xlsx(rep, Path(tmp) / "r.xlsx")
        files_ok = pdf.stat().st_size > 1000 and xlsx.stat().st_size > 1000
    ok = (db is not None and np.isfinite(EC.appraise(model, [lib["hull_coating"]], sc, rules=rules).npv)
          and len(ranks) == 4 and abs(res.acceptability.sum() - len(res.keys)) < 1e-6
          and len(front.plans) >= 1 and files_ok)
    print("selftest", "ok" if ok else "FAILED", "| database:", db)
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    import os

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME, APP_ORG, i18n
    from .data.accounts import AccountStore

    QApplication.setOrganizationName(APP_ORG)
    QApplication.setApplicationName(APP_NAME)
    scale = str(QSettings(APP_ORG, APP_NAME).value("ui_scale", "100"))
    if scale != "100" and "QT_SCALE_FACTOR" not in os.environ:      # interface size (decision 0015)
        os.environ["QT_SCALE_FACTOR"] = f"{int(scale) / 100:.2f}"
    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setFont(theme.ui_font(10))
    settings = QSettings()
    lang = settings.value("language", i18n.DEFAULT)
    if lang in i18n.LANGUAGES:
        i18n.set_language(lang)
    theme.set_current(theme.PALETTES.get(settings.value("theme", "light"), theme.DEFAULT))
    app.setStyleSheet(theme.stylesheet(theme.current()))
    accounts = AccountStore()
    account = accounts.remembered()
    if account is not None:
        win = MainWindow(accounts=accounts, account=account)
    else:
        win = MainWindow(accounts=accounts, welcome="signin" if accounts.setup_done else "setup")
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
