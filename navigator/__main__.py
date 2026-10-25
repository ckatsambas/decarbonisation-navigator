"""Entry point: `python -m navigator`."""
from __future__ import annotations

import sys


def selftest() -> int:
    """Run the whole engine once without a window (used to check packaged builds): bundled EU MRV
    data, power model, measure appraisal, BWM weights, the four rankings and a small SMAA run."""
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
    ok = (db is not None and np.isfinite(EC.appraise(model, [lib["hull_coating"]], sc, rules=rules).npv)
          and len(ranks) == 4 and abs(res.acceptability.sum() - len(res.keys)) < 1e-6)
    print("selftest", "ok" if ok else "FAILED", "| database:", db)
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
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
    theme.set_current(theme.PALETTES.get(settings.value("theme", "light"), theme.DEFAULT))
    app.setStyleSheet(theme.stylesheet(theme.current()))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
