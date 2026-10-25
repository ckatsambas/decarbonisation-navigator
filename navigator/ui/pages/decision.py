"""Step 5 · Decision: the shortlist ranked four ways, and how often the answer holds under uncertainty.

Rankings: SAW, TOPSIS, PROMETHEE II and VIKOR on the most likely values with the company weights,
plus a consensus rank (decision 0010-3). Uncertainty: SMAA-2 over every range and over the weights
(decision 0010-4), run in the background.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...engine.mcda import criteria as C
from ...engine.mcda import ranking as RK
from ...engine.mcda import smaa as S
from ...i18n import eur_short, num, pct, pick, tr
from .. import theme
from ..charts import HBarChart
from ..widgets import Panel, ReadMore, TrLabel, amp, label
from .base import Page
from .position import Choice

DRAWS = ("2000", "10000", "20000")
ODDS = {"equal": {"as_drafted": 1, "delayed": 1, "not_adopted": 1},
        "adopt": {"as_drafted": 0.6, "delayed": 0.2, "not_adopted": 0.2},
        "reject": {"as_drafted": 0.2, "delayed": 0.2, "not_adopted": 0.6}}
SURE = {"high": 300.0, "mid": 100.0, "low": 20.0, "none": 0.0}


class Worker(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, sim, weights, n, kappa, odds):
        super().__init__()
        self.args = (sim, weights, n, kappa, odds)

    def run(self) -> None:
        sim, w, n, kappa, odds = self.args
        try:
            res = S.run(sim, True, None if kappa == 0 else w, n=n, kappa=kappa or 1.0, nzf_prob=odds)
            self.done.emit(res)
        except Exception as e:  # noqa: BLE001 - shown to the user instead of crashing the app
            self.failed.emit(str(e))


class StepDecision(Page):
    title_key = "step.5.q"
    lede_key = "step.5.lede"
    title_style = ("Question", "QuestionLede")

    changed = Signal()

    def __init__(self, state, options, priorities):
        super().__init__(state)
        self.options, self.priorities = options, priorities
        self.alts: list = []
        self.smaa: S.SmaaResult | None = None
        self._thread: QThread | None = None

        self.sentence = label("", "Sentence", wrap=True)
        self.lay.addWidget(self.sentence)

        rp = Panel("dec.rankings")
        self.table = QTableWidget(0, 7)
        self.table.setObjectName("Ledger")
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(260)
        rp.body.addWidget(self.table)
        self.agree = label("", "Muted", wrap=True)
        rp.body.addWidget(self.agree)
        rp.body.addWidget(ReadMore("dec.methods.more"))
        self.lay.addWidget(rp)

        up = Panel("dec.smaa")
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        for i, k in enumerate(("dec.odds", "dec.sure", "dec.draws")):
            grid.addWidget(TrLabel(k, "SectionTitle"), 0, i)
        self.odds = Choice([(k, f"dec.odds.{k}") for k in ODDS])
        self.sure = Choice([(k, f"dec.sure.{k}") for k in SURE])
        self.draws = Choice([(k, f"dec.draws.{k}") for k in DRAWS])
        self.odds.set_value("equal")
        self.sure.set_value("mid")
        self.draws.set_value("10000")
        for i, w in enumerate((self.odds, self.sure, self.draws)):
            grid.addWidget(w, 1, i, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(ReadMore("dec.odds.more"), 2, 0)
        grid.addWidget(ReadMore("dec.sure.more"), 2, 1)
        grid.addWidget(ReadMore("dec.draws.more"), 2, 2)
        grid.setColumnStretch(3, 1)
        up.body.addLayout(grid)
        h = QHBoxLayout()
        self.run_btn = QPushButton()
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run_smaa)
        h.addWidget(self.run_btn)
        self.status = label("", "Muted", wrap=True)
        h.addWidget(self.status, 1)
        up.body.addLayout(h)
        self.smaa_sentence = label("", "Sentence", wrap=True)
        self.smaa_sentence.hide()
        up.body.addWidget(self.smaa_sentence)
        up.body.addWidget(TrLabel("dec.acc", "SectionTitle"))
        self.acc_chart = HBarChart()
        up.body.addWidget(self.acc_chart)
        self.smaa_table = QTableWidget(0, 5)
        self.smaa_table.setObjectName("Ledger")
        self.smaa_table.verticalHeader().setVisible(False)
        self.smaa_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.smaa_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        sh = self.smaa_table.horizontalHeader()
        sh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        sh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.smaa_table.setMinimumHeight(220)
        up.body.addWidget(self.smaa_table)
        up.body.addWidget(ReadMore("dec.smaa.more"))
        self.lay.addWidget(up)
        self.lay.addStretch(1)

        for c in (self.odds, self.sure, self.draws):
            c.picked.connect(lambda v, c=c: (c.set_value(v), self._stale()))
        priorities.changed.connect(self.recompute)
        options.changed.connect(self.recompute)
        self.retranslate_buttons()
        self.recompute()

    # ------------------------------------------------------------------
    def _value(self, choice: Choice, default: str) -> str:
        return next((v for v, b in choice.buttons.items() if b.isChecked()), default)

    def name(self, key: str) -> str:
        if key == C.DO_NOTHING:
            return tr("dec.do_nothing")
        return pick(self.options.lib[key].name)

    def recompute(self) -> None:
        self.alts = self.options.alternatives()
        self._stale()
        if len(self.alts) < 2:
            self.table.setRowCount(0)
            self.sentence.setText(tr("dec.need_shortlist"))
            self.agree.setText("")
            self.run_btn.setEnabled(False)
            return
        self.run_btn.setEnabled(True)
        x = C.matrix(self.alts)
        w = self.priorities.global_weights()
        self.rankings = RK.rank_all(x, w, C.MAXIMISE)
        mean, cons, corr = RK.consensus(self.rankings)
        order = np.argsort(cons, kind="stable")
        heads = [tr("col.option"), *[tr(f"method.{m}") for m in RK.METHODS], tr("dec.consensus"), tr("crit.npv")]
        self.table.setColumnCount(len(heads))
        self.table.setHorizontalHeaderLabels(heads)
        self.table.setRowCount(len(self.alts))
        p = theme.current()
        for r, i in enumerate(order):
            a = self.alts[i]
            cells = [self.name(a.key), *[str(self.rankings[m].rank[i]) for m in RK.METHODS], str(cons[i]),
                     eur_short(a.values["npv"])]
            for j, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if j:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if 1 <= j <= 5 and text == "1":
                    it.setForeground(QColor(p.accent_text))
                    it.setBackground(QColor(p.accent))
                self.table.setItem(r, j, it)
        k = len(RK.METHODS)
        rho = (corr.sum() - k) / (k * k - k) if k > 1 else 1.0
        all_same = all(self.rankings[m].rank[order[0]] == 1 for m in RK.METHODS)
        self.agree.setText(tr("dec.agree", rho=num(rho, 2)))
        best = self.name(self.alts[order[0]].key)
        self.sentence.setText(tr("dec.sentence.all" if all_same else "dec.sentence.some", best=best,
                                 n=sum(int(self.rankings[m].rank[order[0]] == 1) for m in RK.METHODS)))
        self.changed.emit()

    def _stale(self) -> None:
        self.status.setText(tr("dec.smaa.stale") if self.smaa is not None else tr("dec.smaa.ready"))

    def run_smaa(self) -> None:
        if self._thread is not None or len(self.alts) < 2:
            return
        opt = self.options
        alternatives = {a.key: a.measures for a in self.alts if a.key != C.DO_NOTHING}
        sim = S.Simulator(opt.model, alternatives, opt.scenario(), opt.mcda_settings(), opt.rules)
        n = int(self._value(self.draws, "10000"))
        kappa = SURE[self._value(self.sure, "mid")]
        odds = ODDS[self._value(self.odds, "equal")]
        self.status.setText(tr("dec.smaa.running", n=num(n)))
        self.run_btn.setEnabled(False)
        self._thread = QThread(self)
        self._worker = Worker(sim, self.priorities.global_weights(), n, kappa, odds)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._finished)
        self._worker.failed.connect(self._failed)
        self._thread.start()

    def _cleanup(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self.run_btn.setEnabled(True)

    def _failed(self, msg: str) -> None:
        self._cleanup()
        self.status.setText(tr("dec.smaa.failed", msg=msg))

    def _finished(self, res: S.SmaaResult) -> None:
        self._cleanup()
        self.show_smaa(res)
        self.changed.emit()

    def show_smaa(self, res: S.SmaaResult) -> None:
        self.smaa = res
        self.status.setText(tr("dec.smaa.done", n=num(res.n)))
        order = np.argsort(res.expected_rank(), kind="stable")
        names = [self.name(res.keys[i]) for i in order]
        p = theme.current()
        ramp = [p.accent, p.good, p.ets, p.fueleu, p.imo, p.warn, p.bad, p.faint, p.muted, p.border]
        a = len(res.keys)
        series = [(tr("dec.rank", r=r + 1), [float(res.acceptability[i, r]) for i in order], ramp[min(r, len(ramp) - 1)])
                  for r in range(min(a, 6))]
        if a > 6:
            series.append((tr("dec.rank.rest"), [float(res.acceptability[i, 6:].sum()) for i in order], p.faint))
        self.acc_chart.set_data(names, series)
        heads = [tr("col.option"), tr("dec.first"), tr("dec.exp_rank"), tr("dec.conf"), tr("dec.central")]
        self.smaa_table.setHorizontalHeaderLabels(heads)
        self.smaa_table.setRowCount(a)
        for r, i in enumerate(order):
            cw = res.central_weights[i]
            top = "–"
            if not np.isnan(cw).any():
                j = np.argsort(-cw)[:2]
                top = ", ".join(f"{tr(f'crit.{C.KEYS[k]}')} {pct(cw[k])}" for k in j)
            cells = [names[r], pct(res.acceptability[i, 0]), num(res.expected_rank()[i], 2), pct(res.confidence[i]), top]
            for j, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if 0 < j < 4:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.smaa_table.setItem(r, j, it)
        lead = order[0]
        self.smaa_sentence.setText(tr("dec.smaa.sentence", best=self.name(res.keys[lead]),
                                      first=pct(res.acceptability[lead, 0]), n=num(res.n),
                                      conf=pct(res.confidence[lead])))
        self.smaa_sentence.show()

    def snapshot(self) -> dict:
        d = {"odds": self._value(self.odds, "equal"), "sure": self._value(self.sure, "mid"),
             "draws": self._value(self.draws, "10000")}
        if self.smaa is not None:
            d["smaa"] = {"keys": self.smaa.keys, "first": [float(v) for v in self.smaa.acceptability[:, 0]],
                         "n": self.smaa.n}
        return d

    def restore(self, d: dict | None) -> None:
        d = d or {}
        self.odds.set_value(d.get("odds", "equal"))
        self.sure.set_value(d.get("sure", "mid"))
        self.draws.set_value(d.get("draws", "10000"))
        self.smaa = None
        self.smaa_sentence.hide()
        self.recompute()

    def summary(self) -> dict:
        if not self.alts or not hasattr(self, "rankings"):
            return {}
        _, cons, _ = RK.consensus(self.rankings)
        best = self.alts[int(np.argmin(cons))].key
        return {"best": best}

    def retranslate_buttons(self) -> None:
        self.run_btn.setText(amp(tr("dec.run")))

    def on_language(self) -> None:
        for c in (self.odds, self.sure, self.draws):
            c.retranslate()
        self.retranslate_buttons()
        self.recompute()
        if self.smaa is not None:
            self.show_smaa(self.smaa)

    def on_theme(self) -> None:
        self.acc_chart.restyle()
        self.recompute()
        if self.smaa is not None:
            self.show_smaa(self.smaa)

