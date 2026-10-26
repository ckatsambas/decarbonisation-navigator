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
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...engine.mcda import criteria as C
from ...engine.mcda import ranking as RK
from ...engine.mcda import smaa as S
from ...i18n import eur_short, num, pct, pick, tr
from .. import theme
from ..maps import RED, PriorityMap, RankHeatmap
from ..widgets import Panel, ReadMore, TrLabel, amp, label
from .base import Page
from .position import Choice

DRAWS = ("2000", "10000", "20000")
ODDS = {"equal": {"as_drafted": 1, "delayed": 1, "not_adopted": 1},
        "adopt": {"as_drafted": 0.6, "delayed": 0.2, "not_adopted": 0.2},
        "reject": {"as_drafted": 0.2, "delayed": 0.2, "not_adopted": 0.6}}
AXES = {"money-climate": ("money", "climate"), "money-operations": ("money", "operations"),
        "climate-technology": ("climate", "technology"), "money-regulation": ("money", "regulation")}
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

        mp = Panel("dec.map")
        mp.body.addWidget(TrLabel("dec.map.lede", "Muted", wrap=True))
        self.axes = Choice([(k, f"dec.axes.{k}") for k in AXES])
        self.axes.set_value("money-climate")
        mp.body.addWidget(self.axes)
        row = QHBoxLayout()
        self.map = PriorityMap()
        row.addWidget(self.map, 3)
        self.legend = QVBoxLayout()
        self.legend.setSpacing(6)
        lw = QWidget()
        lw.setLayout(self.legend)
        row.addWidget(lw, 2, Qt.AlignmentFlag.AlignTop)
        mp.body.addLayout(row)
        self.map_note = label("", "Sentence", wrap=True)
        mp.body.addWidget(self.map_note)
        mp.body.addWidget(ReadMore("dec.map.more"))
        self.lay.addWidget(mp)

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
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)                 # indeterminate: moves while the futures are computed
        self.busy.setTextVisible(False)
        self.busy.setFixedHeight(6)
        self.busy.hide()
        up.body.addWidget(self.busy)
        up.body.addWidget(TrLabel("dec.acc", "SectionTitle"))
        self.acc_chart = RankHeatmap()
        up.body.addWidget(self.acc_chart)
        up.body.addWidget(ReadMore("dec.acc.more"))
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
        self.sure.picked.connect(lambda _: self.draw_map())
        self.axes.picked.connect(lambda v: (self.axes.set_value(v), self.draw_map()))
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
        self.draw_map()
        best = self.name(self.alts[order[0]].key)
        self.sentence.setText(tr("dec.sentence.all" if all_same else "dec.sentence.some", best=best,
                                 n=sum(int(self.rankings[m].rank[order[0]] == 1) for m in RK.METHODS)))
        self.changed.emit()

    def draw_map(self) -> None:
        """Winner map for the chosen pair of families, the company's weights and the SMAA cloud."""
        if len(self.alts) < 2:
            return
        fx, fy = AXES[self._value(self.axes, "money-climate")]
        base = self.priorities.global_weights()
        x = C.matrix(self.alts)
        grid = RK.winner_map(x, C.MAXIMISE, lambda a, b: C.split_weights(base, fx, fy, a, b), n=60)
        fam = C.family_sums(base)
        kappa = SURE[self._value(self.sure, "mid")]
        w = S.sample_weights(None if kappa == 0 else base, 600, kappa or 1.0, 7)
        cloud = np.array([[ws[[i for i, c in enumerate(C.CRITERIA) if c.family == fx]].sum(),
                           ws[[i for i, c in enumerate(C.CRITERIA) if c.family == fy]].sum()] for ws in w])
        p = theme.current()
        palette = [p.ets, p.fueleu, p.imo, p.warn, p.good, "#C9849A", "#8A9A5B", "#5B8FA8", p.faint]
        names = [self.name(a.key) for a in self.alts]
        colors = [p.border if a.key == C.DO_NOTHING else palette[i % len(palette)] for i, a in enumerate(self.alts)]
        self.map.set_data(grid, names, colors, (fam[fx], fam[fy]), cloud,
                          (tr(f"fam.{fx}"), tr(f"fam.{fy}")))
        while self.legend.count():
            it = self.legend.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        present = set(np.unique(grid[grid >= 0]).tolist())
        for i, nm in enumerate(names):
            if i not in present:
                continue
            share = float((grid == i).sum()) / float((grid >= 0).sum())
            lab = label(f'<span style="color:{colors[i]}; font-size:14pt">■</span>&nbsp; {nm} — {pct(share)}', "Muted")
            lab.setTextFormat(Qt.TextFormat.RichText)
            self.legend.addWidget(lab)
        self.legend.addWidget(label(f'<span style="color:{RED}; font-size:14pt">●</span>&nbsp; {tr("dec.map.you")}',
                                    "Muted"))
        self.legend.itemAt(self.legend.count() - 1).widget().setTextFormat(Qt.TextFormat.RichText)
        n = grid.shape[0]
        ix = min(int(fam[fx] * n), n - 1)
        iy = min(int(fam[fy] * n), n - 1)
        here = grid[ix, iy] if grid[ix, iy] >= 0 else int(np.argmax(np.bincount(grid[grid >= 0])))
        inside = []
        for xs, ys in cloud:
            i2, j2 = min(int(xs * n), n - 1), min(int(ys * n), n - 1)
            inside.append(grid[i2, j2] == here if grid[i2, j2] >= 0 else True)
        self.map_note.setText(tr("dec.map.note", name=names[here], share=pct(float(np.mean(inside)))))

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
        self.busy.show()
        self._thread = QThread(self)
        self._worker = Worker(sim, self.priorities.global_weights(), n, kappa, odds)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._finished)
        self._worker.failed.connect(self._failed)
        self._thread.start()

    def _cleanup(self) -> None:
        self.busy.hide()
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
        a = len(res.keys)
        exp = res.expected_rank()
        ref = next((r for r, i in enumerate(order) if res.keys[i] == C.DO_NOTHING), -1)
        self.acc_chart.set_data(names, res.acceptability[order], [exp[i] for i in order], 0, ref,
                                (tr("dec.rank.short"), tr("dec.exp_rank"), tr("dec.recommended"), tr("dec.reference")))
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
        for c in (self.odds, self.sure, self.draws, self.axes):
            c.retranslate()
        self.retranslate_buttons()
        self.recompute()
        if self.smaa is not None:
            self.show_smaa(self.smaa)

    def on_theme(self) -> None:
        self.acc_chart.update()
        self.recompute()
        if self.smaa is not None:
            self.show_smaa(self.smaa)

