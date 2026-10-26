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
    QComboBox,
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
from ...engine.regulation.imo_nzf import SCENARIOS as SCENARIOS_
from ...i18n import eur_short, num, pct, pick, tr
from .. import theme
from ..charts import Switchable
from ..donut import Donut3D
from ..fan import FanChart
from ..maps import FAMILY_COLORS, PriorityMap, RankBubbles, option_colors
from ..radar import ProfileRadar, WeightRadar
from ..surface3d import Surface3D
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
LEVEL = ("low", "central", "high")


def level_of(u: float) -> str:
    return LEVEL[0] if u < 1 / 3 else LEVEL[2] if u > 2 / 3 else LEVEL[1]


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

        pp = Panel("dec.profiles")
        pp.body.addWidget(TrLabel("dec.profiles.lede", "Muted", wrap=True))
        self.prof_grid = ProfileRadar(grid=True)
        self.prof_over = ProfileRadar(grid=False)
        self.profiles = Switchable([("⊞", tr("view.grid"), self.prof_grid), ("◎", tr("view.overlay"), self.prof_over)])
        pp.body.addWidget(self.profiles)
        pp.body.addWidget(ReadMore("dec.profiles.more"))
        self.lay.addWidget(pp)

        mp = Panel("dec.map")
        self.map_lede = label("", "Muted", wrap=True)
        mp.body.addWidget(self.map_lede)
        self.axes = Choice([(k, f"dec.axes.{k}") for k in AXES])
        self.axes.set_value("money-climate")
        mp.body.addWidget(self.axes)
        self.radar = WeightRadar()
        self.map = PriorityMap()
        self.surface = Surface3D()
        self.views = Switchable([("◉", tr("view.radar"), self.radar), ("◭", tr("view.map"), self.map),
                                 ("⛰", tr("view.3d"), self.surface)], on_change=self._view_changed)
        mp.body.addWidget(self.views)
        self.map_note = label("", "Sentence", wrap=True)
        mp.body.addWidget(self.map_note)
        self.map_more = ReadMore("dec.radar.more")
        mp.body.addWidget(self.map_more)
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
        self.smaa_box = QWidget()
        sb = QVBoxLayout(self.smaa_box)
        sb.setContentsMargins(0, 0, 0, 0)
        fh = QHBoxLayout()
        fh.addWidget(TrLabel("dec.fan", "SectionTitle"))
        fh.addStretch(1)
        self.fan_pick = QComboBox()
        self.fan_pick.setMinimumWidth(280)
        self.fan_pick.currentIndexChanged.connect(lambda _i: self.draw_fan())
        fh.addWidget(self.fan_pick)
        sb.addLayout(fh)
        self.fan = FanChart()
        sb.addWidget(self.fan)
        sb.addWidget(ReadMore("dec.fan.more"))
        sb.addWidget(TrLabel("dec.acc", "SectionTitle"))
        self.donut = Donut3D()
        self.acc_chart = RankBubbles()
        self.acc_views = Switchable([("◔", tr("view.donut"), self.donut), ("⁘", tr("view.bubbles"), self.acc_chart)])
        sb.addWidget(self.acc_views)
        sb.addWidget(ReadMore("dec.acc.more"))
        self.smaa_box.hide()
        up.body.addWidget(self.smaa_box)
        self.smaa_table = QTableWidget(0, 5)
        self.smaa_table.setObjectName("Ledger")
        self.smaa_table.verticalHeader().setVisible(False)
        self.smaa_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.smaa_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        sh = self.smaa_table.horizontalHeader()
        sh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        sh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.smaa_table.setMinimumHeight(220)
        sb.addWidget(self.smaa_table)
        sb.addWidget(ReadMore("dec.smaa.more"))
        self.lay.addWidget(up)
        self.lay.addStretch(1)

        for c in (self.odds, self.sure, self.draws):
            c.picked.connect(lambda v, c=c: (c.set_value(v), self._stale()))
        self.sure.picked.connect(lambda _: self.draw_map())
        self.axes.picked.connect(lambda v: (self.axes.set_value(v), self.draw_map()))
        self._view_changed(0)
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
        self.best_key = self.alts[order[0]].key
        keys = [a.key for a in self.alts]
        self.colors = dict(zip(keys, option_colors(keys, self.best_key, C.DO_NOTHING), strict=True))
        self.draw_profiles(order)
        k = len(RK.METHODS)
        rho = (corr.sum() - k) / (k * k - k) if k > 1 else 1.0
        all_same = all(self.rankings[m].rank[order[0]] == 1 for m in RK.METHODS)
        self.agree.setText(tr("dec.agree", rho=num(rho, 2)))
        self.draw_map()
        best = self.name(self.alts[order[0]].key)
        self.sentence.setText(tr("dec.sentence.all" if all_same else "dec.sentence.some", best=best,
                                 n=sum(int(self.rankings[m].rank[order[0]] == 1) for m in RK.METHODS)))
        self.changed.emit()

    def draw_profiles(self, order) -> None:
        """Each option's normalised performance (best of the shortlist on the rim), in ranking order."""
        x = C.matrix(self.alts)
        z = RK.minmax(x, C.MAXIMISE)
        axes = [tr(f"crit.{c.key}") for c in C.CRITERIA]
        short = [tr(f"crit.short.{c.key}") for c in C.CRITERIA]
        fam_cols = [FAMILY_COLORS[c.family] for c in C.CRITERIA]
        series = []
        for i in order:
            a = self.alts[i]
            tips = [self.fmt(c, a.values[c.key]) for c in C.CRITERIA]
            series.append((self.name(a.key), z[i], self.colors[a.key], a.key == self.best_key, tips))
        self.prof_grid.set_data(axes, short, fam_cols, series)
        self.prof_over.set_data(axes, short, fam_cols, series)

    @staticmethod
    def fmt(c, v: float) -> str:
        if c.unit == "eur":
            return eur_short(v)
        if c.unit == "share":
            return pct(v, 1)
        if c.unit == "days":
            return tr("opt.days", n=num(v, 1))
        if c.unit == "trl":
            return f"TRL {num(v)}"
        return f"{num(v)}/5"

    def _view_changed(self, i: int) -> None:
        if not hasattr(self, "axes"):
            return
        self.axes.setVisible(i != 0)
        self.map_lede.setText(tr(("dec.radar.lede", "dec.map.lede", "dec.3d.lede")[i]))
        self.map_more.set_key(("dec.radar.more", "dec.map.more", "dec.3d.more")[i])
        self.draw_map()

    def draw_map(self) -> None:
        """The robustness of the recommendation to the weights, in the view that is showing."""
        if len(self.alts) < 2 or not hasattr(self, "best_key"):
            return
        base = self.priorities.global_weights()
        x = C.matrix(self.alts)
        keys = [a.key for a in self.alts]
        names = [self.name(k) for k in keys]
        colors = [self.colors[k] for k in keys]
        best = keys.index(self.best_key)
        kappa = SURE[self._value(self.sure, "mid")]
        w = S.sample_weights(None if kappa == 0 else base, 300, kappa or 1.0, 7)
        z = RK.minmax(x, C.MAXIMISE)
        view = self.views.index()
        if view == 0:
            wins = (z @ w.T).argmax(axis=0) == best
            share = float(wins.mean())
            self.radar.set_data([tr(f"crit.short.{c.key}") for c in C.CRITERIA], [c.family for c in C.CRITERIA],
                                [FAMILY_COLORS[c.family] for c in C.CRITERIA], base, w, wins,
                                (tr("dec.radar.you"), tr("dec.radar.holds", best=names[best], share=pct(share)),
                                 tr("dec.radar.flips", share=pct(1 - share))))
            self.map_note.setText(tr("dec.radar.note", best=names[best], share=pct(share)))
            return
        fx, fy = AXES[self._value(self.axes, "money-climate")]
        fam_idx = {f: [i for i, c in enumerate(C.CRITERIA) if c.family == f] for f in (fx, fy)}
        fam = C.family_sums(base)

        def at(a, b):
            return C.split_weights(base, fx, fy, a, b)

        s0, sa, sb = RK.affine_scores(x, C.MAXIMISE, at)
        cloud = np.stack([w[:, fam_idx[fx]].sum(axis=1), w[:, fam_idx[fy]].sum(axis=1)], axis=1)
        here = int(np.argmax(s0 + fam[fx] * sa + fam[fy] * sb))
        win_cloud = (s0[None, :] + cloud[:, :1] * sa[None, :] + cloud[:, 1:] * sb[None, :]).argmax(axis=1)
        share = float((win_cloud == here).mean())
        axis = (tr(f"fam.{fx}"), tr(f"fam.{fy}"))
        if view == 1:
            self.map.set_data(RK.winner_regions(x, C.MAXIMISE, at), names, colors, (fam[fx], fam[fy]), cloud, axis,
                              tr("dec.radar.you"))
        else:
            self.surface.set_data(s0, sa, sb, best, colors, names, RK.winner_regions(x, C.MAXIMISE, at),
                                  (fam[fx], fam[fy]), axis,
                                  (tr("dec.radar.you"), tr("dec.3d.above", best=names[best]), tr("dec.3d.below")))
        self.map_note.setText(tr("dec.map.note", name=names[here], share=pct(share)))

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
        cols = [self.colors.get(res.keys[i], "#9AA5AE") for i in order]
        best_row = next((r for r, i in enumerate(order) if res.keys[i] == getattr(self, "best_key", None)), 0)
        self.acc_chart.set_data(names, res.acceptability[order], [exp[i] for i in order], best_row, ref,
                                (tr("dec.rank.short"), tr("dec.exp_rank"), tr("dec.recommended"), tr("dec.reference")),
                                cols)
        self.donut.set_data([(names[r], res.acceptability[i, 0], cols[r], "") for r, i in enumerate(order)
                             if res.acceptability[i, 0] > 0], tr("dec.donut.caption", n=num(res.n)))
        self.smaa_box.show()
        current = self.fan_pick.currentData()
        self.fan_pick.blockSignals(True)
        self.fan_pick.clear()
        for i in order:
            if res.keys[i] != C.DO_NOTHING:
                self.fan_pick.addItem(self.name(res.keys[i]), res.keys[i])
        keys = [self.fan_pick.itemData(k) for k in range(self.fan_pick.count())]
        pick_key = current if current in keys else getattr(self, "best_key", None)
        self.fan_pick.setCurrentIndex(keys.index(pick_key) if pick_key in keys else 0)
        self.fan_pick.blockSignals(False)
        self.draw_fan()
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

    def draw_fan(self) -> None:
        res = self.smaa
        key = self.fan_pick.currentData()
        if res is None or key is None or "paths" not in res.details or key not in res.details["paths"]:
            return
        j = res.keys.index(key)
        dr = res.details["drivers"]
        paths = res.details["paths"][key]
        ends = paths[:, -1]

        def why(k: int) -> str:
            return tr("dec.fan.why", eua=tr(f"level.{level_of(float(dr['eua'][k]))}"),
                      nzf=tr(f"nzf.short.{SCENARIOS_[int(dr['scenario'][k])]}"),
                      fuel=tr(f"level.{level_of(float(dr['fossil'][k]))}"))

        self.fan.set_data(res.details["years"], paths, res.values["npv"][:, j],
                          {"gain": tr("dec.fan.gain"), "loss": tr("dec.fan.loss"), "median": tr("dec.fan.median"),
                           "today": tr("dec.fan.today", y=int(res.details["years"][0])),
                           "best": tr("dec.fan.best") + ": " + why(int(np.argmax(ends))),
                           "worst": tr("dec.fan.worst") + ": " + why(int(np.argmin(ends)))})

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
        self.smaa_box.hide()
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
        self.profiles.set_tips([tr("view.grid"), tr("view.overlay")])
        self.views.set_tips([tr("view.radar"), tr("view.map"), tr("view.3d")])
        self.acc_views.set_tips([tr("view.donut"), tr("view.bubbles")])
        self._view_changed(self.views.index())
        self.retranslate_buttons()
        self.recompute()
        if self.smaa is not None:
            self.show_smaa(self.smaa)

    def on_theme(self) -> None:
        self.acc_chart.update()
        self.recompute()
        if self.smaa is not None:
            self.show_smaa(self.smaa)

