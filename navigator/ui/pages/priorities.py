"""Step 4 · Priorities: what matters most to the company, asked as simple comparisons.

Best-Worst Method by default, AHP as an option (decision 0010-2), at two levels of the criteria tree:
the five families, then the criteria inside "money" and "operations". Each question shows how far
apart the shortlisted options actually are on that family (swing weighting), because in an additive
model a weight means "how much this difference matters", not importance in the abstract.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...engine.mcda import criteria as C
from ...engine.mcda import weights as W
from ...i18n import eur_short, num, pct, tr
from .. import theme
from ..charts import HBarChart, Switchable
from ..judgement import ClickScale, PairMatrix, WeightBar, ratio
from ..maps import FAMILY_COLORS, RED
from ..radar import ProfileRadar
from ..widgets import Panel, ReadMore, TrLabel, label
from .base import Page
from .position import Choice

LEVELS = {"families": list(C.FAMILIES), "money": ["npv", "capex"],
          "operations": ["offhire", "cargo", "availability", "safety"]}


def item_name(key: str) -> str:
    return tr(f"fam.{key}") if key in C.FAMILIES else tr(f"crit.{key}")


class BwmBlock(QWidget):
    """BWM as a small table: ★ marks the most important item, ✕ the least; each other item gets two
    clicked judgements (how much less than ★, how much more than ✕) and shows its resulting weight."""

    changed = Signal()

    def __init__(self, items: list[str]):
        super().__init__()
        self.items = items
        self.best_key, self.worst_key = items[0], items[-1]
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(5)
        self.head_bo = label("", "Faint", wrap=True)
        self.head_ow = label("", "Faint", wrap=True)
        self.head_w = TrLabel("pri.col.weight", "Faint")
        star_h, cross_h = label("★", "Faint"), label("✕", "Faint")
        self.star_h, self.cross_h = star_h, cross_h
        g.addWidget(star_h, 0, 1, Qt.AlignmentFlag.AlignCenter)
        g.addWidget(cross_h, 0, 2, Qt.AlignmentFlag.AlignCenter)
        g.addWidget(self.head_bo, 0, 3)
        g.addWidget(self.head_ow, 0, 4)
        g.addWidget(self.head_w, 0, 5)
        self.names: dict[str, object] = {}
        self.stars: dict[str, QToolButton] = {}
        self.crosses: dict[str, QToolButton] = {}
        self.bo: dict[str, ClickScale] = {}
        self.ow: dict[str, ClickScale] = {}
        self.bars: dict[str, WeightBar] = {}
        for r, k in enumerate(items, start=1):
            self.names[k] = label("", "JudgeName")
            self.stars[k] = self._mark("★", "Star", lambda _=False, k=k: self.set_best(k))
            self.crosses[k] = self._mark("✕", "Cross", lambda _=False, k=k: self.set_worst(k))
            self.bo[k], self.ow[k], self.bars[k] = ClickScale(2), ClickScale(2), WeightBar()
            self.bo[k].changed.connect(self._judged)
            self.ow[k].changed.connect(self._judged)
            for c, w in enumerate((self.names[k], self.stars[k], self.crosses[k], self.bo[k], self.ow[k], self.bars[k])):
                g.addWidget(w, r, c)
        g.setColumnStretch(3, 1)
        g.setColumnStretch(4, 1)
        self.retranslate()

    @staticmethod
    def _mark(text: str, name: str, slot) -> QToolButton:
        b = QToolButton()
        b.setObjectName(name)
        b.setText(text)
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def _judged(self) -> None:
        self._layout()
        self.changed.emit()

    def set_best(self, k: str, emit: bool = True) -> None:
        if k == self.worst_key:
            self.worst_key = self.best_key
        self.best_key = k
        self._layout()
        if emit:
            self.changed.emit()

    def set_worst(self, k: str, emit: bool = True) -> None:
        if k == self.best_key:
            self.best_key = self.worst_key
        self.worst_key = k
        self._layout()
        if emit:
            self.changed.emit()

    def _layout(self) -> None:
        b, w = self.best_key, self.worst_key
        for k in self.items:
            self.stars[k].setChecked(k == b)
            self.crosses[k].setChecked(k == w)
            self.bo[k].set_fixed(k == b)
            self.ow[k].set_fixed(k in (b, w), self.bo[w].value() if k == b else None)
        self.head_bo.setText(tr("pri.col.vs_best", best=item_name(b)))
        self.head_ow.setText(tr("pri.col.vs_worst", worst=item_name(w)))

    def set_weights(self, weights) -> None:
        top = int(np.argmax(weights))
        for i, k in enumerate(self.items):
            self.bars[k].set_value(float(weights[i]), i == top)

    def set_tips(self, tips: dict[str, str]) -> None:
        for k in self.items:
            self.names[k].setToolTip(tips.get(k, ""))

    def reset(self) -> None:
        """Back to the starting point: first item most, last least important, every comparison at 2."""
        self.best_key, self.worst_key = self.items[0], self.items[-1]
        for sc in (*self.bo.values(), *self.ow.values()):
            sc.set_value(2)
        self._layout()
        self.changed.emit()

    def result(self) -> W.WeightResult:
        b, w = self.best_key, self.worst_key
        bi, wi = self.items.index(b), self.items.index(w)
        a_b = [1.0 if k == b else float(self.bo[k].value()) for k in self.items]
        a_w = [1.0 if k == w else (a_b[wi] if k == b else float(self.ow[k].value())) for k in self.items]
        return W.bwm(bi, wi, a_b, a_w)

    def snapshot(self) -> dict:
        return {"best": self.best_key, "worst": self.worst_key,
                "bo": {k: s.value() for k, s in self.bo.items()}, "ow": {k: s.value() for k, s in self.ow.items()}}

    def restore(self, d: dict) -> None:
        if not d:
            return
        best, worst = d.get("best", self.items[0]), d.get("worst", self.items[-1])
        self.best_key = best if best in self.items else self.items[0]
        self.worst_key = worst if worst in self.items and worst != self.best_key else self.items[-1]
        for k, v in d.get("bo", {}).items():
            if k in self.bo:
                self.bo[k].set_value(v)
        for k, v in d.get("ow", {}).items():
            if k in self.ow:
                self.ow[k].set_value(v)
        self._layout()

    def retranslate(self) -> None:
        for k in self.items:
            self.names[k].setText(item_name(k))
            self.stars[k].setToolTip(tr("pri.best"))
            self.crosses[k].setToolTip(tr("pri.worst"))
        self.star_h.setToolTip(tr("pri.best"))
        self.cross_h.setToolTip(tr("pri.worst"))
        self.head_w.retranslate()
        self._layout()


class Pair:
    """One AHP answer (value −8…8; negative = the first item matters more) inside a PairMatrix."""

    def __init__(self, matrix: PairMatrix, key: tuple[int, int]):
        self.matrix, self.key = matrix, key

    def value(self) -> int:
        return self.matrix.values[self.key]

    def set_value(self, v: int, emit: bool = False) -> None:
        self.matrix.set_value(self.key, v, emit=emit)


class AhpBlock(QWidget):
    """Every pair once, in the comparison matrix; click a cell to answer."""

    changed = Signal()

    def __init__(self, items: list[str]):
        super().__init__()
        self.items = items
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.matrix = PairMatrix(items, item_name)
        self.matrix.changed.connect(self.changed)
        v.addWidget(self.matrix)
        self.how = TrLabel("pri.ahp.how", "Faint", wrap=True)
        v.addWidget(self.how)
        self.pairs = {key: Pair(self.matrix, key) for key in self.matrix.values}

    def reset(self) -> None:
        """Every pair back to equal importance."""
        for key in self.matrix.values:
            self.matrix.values[key] = 0
        self.matrix.update()
        self.changed.emit()

    def result(self) -> W.WeightResult:
        j = {key: ratio(v) for key, v in self.matrix.values.items()}
        return W.ahp(W.ahp_matrix(len(self.items), j))

    def set_weights(self, weights) -> None:
        self.matrix.set_weights(weights)

    def set_tips(self, tips: dict[str, str]) -> None:
        self.matrix.tips = dict(tips)

    def snapshot(self) -> dict:
        return {f"{i}-{k}": v for (i, k), v in self.matrix.values.items()}

    def restore(self, d: dict) -> None:
        for key, v in (d or {}).items():
            i, k = (int(x) for x in key.split("-"))
            if (i, k) in self.matrix.values:
                self.matrix.values[(i, k)] = int(v)
        self.matrix.update()

    def retranslate(self) -> None:
        self.how.retranslate()
        self.matrix.update()


class Level(Panel):
    changed = Signal()

    def __init__(self, key: str, items: list[str]):
        super().__init__(f"pri.level.{key}")
        self.key, self.items = key, items
        self.hint = label("", "Faint", wrap=True)          # only when there is nothing to compare yet
        self.hint.hide()
        self.body.addWidget(self.hint)
        self.reset_btn = QToolButton(self)                  # floats in the panel's top-right corner
        self.reset_btn.setObjectName("Reset")
        self.reset_btn.setText("↺")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.clicked.connect(self.reset)
        self.bwm, self.ahp = BwmBlock(items), AhpBlock(items)
        self.body.addWidget(self.bwm)
        self.body.addWidget(self.ahp)
        self.status = label("", "Muted", wrap=True)
        self.body.addWidget(self.status)
        self.bwm.changed.connect(self.changed)
        self.ahp.changed.connect(self.changed)
        self.method = "bwm"
        self.set_method("bwm")
        self.retranslate_reset()

    def resizeEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(e)
        self.reset_btn.adjustSize()
        self.reset_btn.move(self.width() - self.reset_btn.width() - 12, 8)
        self.reset_btn.raise_()

    def reset(self) -> None:
        """Reset this section's answers (only the method shown)."""
        (self.bwm if self.method == "bwm" else self.ahp).reset()

    def retranslate_reset(self) -> None:
        self.reset_btn.setToolTip(tr("pri.reset"))

    def set_method(self, method: str) -> None:
        self.method = method
        self.bwm.setVisible(method == "bwm")
        self.ahp.setVisible(method == "ahp")

    def set_tips(self, tips: dict[str, str]) -> None:
        self.bwm.set_tips(tips)
        self.ahp.set_tips(tips)

    def result(self) -> W.WeightResult:
        return self.bwm.result() if self.method == "bwm" else self.ahp.result()

    def show_status(self, r: W.WeightResult) -> None:
        (self.bwm if self.method == "bwm" else self.ahp).set_weights(r.weights)
        key = "pri.cons.ok" if r.acceptable else "pri.cons.bad"
        self.status.setText(tr(key, cr=num(r.consistency, 2), limit=num(r.threshold, 2)))
        self.status.setObjectName("Muted" if r.acceptable else "Warn")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


class StepPriorities(Page):
    title_key = "step.4.q"
    lede_key = "step.4.lede"
    title_style = ("Question", "QuestionLede")

    changed = Signal()

    def __init__(self, state, options):
        super().__init__(state)
        self.options = options
        top = QHBoxLayout()
        top.addWidget(TrLabel("pri.method", "SectionTitle"))
        self.method = Choice([("bwm", "pri.method.bwm"), ("ahp", "pri.method.ahp")])
        self.method.set_value("bwm")
        top.addWidget(self.method)
        top.addStretch(1)
        self.lay.addLayout(top)
        self.lay.addWidget(ReadMore("pri.method.more"))

        row = QHBoxLayout()
        row.setSpacing(16)
        left = QVBoxLayout()
        self.levels = {k: Level(k, items) for k, items in LEVELS.items()}
        for lv in self.levels.values():
            left.addWidget(lv)
            lv.changed.connect(self.update_weights)
        left.addStretch(1)
        lw = QWidget()
        lw.setLayout(left)
        row.addWidget(lw, 3)

        rp = Panel("pri.result")
        self.chart = HBarChart()
        self.radar = ProfileRadar(grid=False, min_h=380)
        self.chart_views = Switchable([("▤", tr("view.bars"), self.chart), ("◎", tr("view.radar.simple"), self.radar)])
        rp.body.addWidget(self.chart_views)
        rp.body.addWidget(TrLabel("pri.compare", "SectionTitle"))
        self.cmp = QTableWidget(len(C.CRITERIA), 4)
        self.cmp.setObjectName("Ledger")
        self.cmp.verticalHeader().setVisible(False)
        self.cmp.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.cmp.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cmp.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cmp.setMinimumHeight(320)
        rp.body.addWidget(self.cmp)
        rp.body.addWidget(ReadMore("pri.compare.more"))
        rp.body.addStretch(1)
        row.addWidget(rp, 2)
        self.lay.addLayout(row)
        self.lay.addStretch(1)

        self.method.picked.connect(self._method)
        options.changed.connect(self.update_hints)
        self.weights = C.global_weights({f: 0.2 for f in C.FAMILIES}, {})
        self.results: dict[str, W.WeightResult] = {}
        self.update_hints()
        self.update_weights()

    # ------------------------------------------------------------------
    def _method(self, m: str) -> None:
        self.method.set_value(m)
        for lv in self.levels.values():
            lv.set_method(m)
        self.update_weights()

    def update_hints(self) -> None:
        """The spread of the shortlist on each item, shown as a tooltip on its name (swing weighting)."""
        alts = self.options.alternatives()
        empty = len(alts) < 2
        for lv in self.levels.values():
            lv.hint.setText(tr("pri.need_shortlist") if empty else "")
            lv.hint.setVisible(empty)
        if empty:
            for lv in self.levels.values():
                lv.set_tips({})
            return
        x = {k: [a.values[k] for a in alts] for k in C.KEYS}
        fmt = {"npv": eur_short, "capex": eur_short, "cut": pct, "trl": lambda v: f"TRL {num(v)}",
               "offhire": lambda v: tr("opt.days", n=num(v)), "cargo": lambda v: pct(v, 1),
               "availability": lambda v: f"{num(v)}/5", "safety": lambda v: f"{num(v)}/5", "nzf_exposure": eur_short}

        def rng(k):
            return f"{tr(f'crit.{k}')}: " + tr("pri.range", lo=fmt[k](min(x[k])), hi=fmt[k](max(x[k])))

        tips = {k: tr("pri.tip.range") + "<br>" + rng(k) for k in C.KEYS}
        for f in C.FAMILIES:
            tips[f] = tr("pri.tip.range") + "<br>" + "<br>".join(rng(c.key) for c in C.CRITERIA if c.family == f)
        for lv in self.levels.values():
            lv.set_tips(tips)
        self._data_weights(alts)

    def update_weights(self) -> None:
        self.results = {k: lv.result() for k, lv in self.levels.items()}
        for k, lv in self.levels.items():
            lv.show_status(self.results[k])
        fam = dict(zip(LEVELS["families"], self.results["families"].weights, strict=True))
        local = {f: dict(zip(LEVELS[f], self.results[f].weights, strict=True)) for f in ("money", "operations")}
        self.weights = C.global_weights(fam, local)
        p = theme.current()
        self.chart.set_data([tr(f"crit.{c.key}") for c in C.CRITERIA], [("", list(self.weights), p.accent)])
        self._data_weights(self.options.alternatives())
        self.draw_radar()
        self.changed.emit()

    def draw_radar(self) -> None:
        """The company's weights against the data-driven ones (entropy, CRITIC), on one radar."""
        alts = self.options.alternatives()
        sets = [(tr("pri.radar.you"), self.weights, RED, True)]
        if len(alts) >= 2:
            x = C.matrix(alts)
            p = theme.current()
            sets += [(tr("pri.entropy"), W.entropy(x, C.MAXIMISE).weights, p.ets, False),
                     (tr("pri.critic"), W.critic(x, C.MAXIMISE).weights, p.fueleu, False)]
        top = max(float(np.max(w)) for _n, w, _c, _e in sets) * 1.1
        step = 0.05 if top < 0.3 else 0.1
        top = step * np.ceil(top / step)
        self.radar.set_data([tr(f"crit.{c.key}") for c in C.CRITERIA], [tr(f"crit.short.{c.key}") for c in C.CRITERIA],
                            [FAMILY_COLORS[c.family] for c in C.CRITERIA],
                            [(n, np.asarray(w) / top, c, e, [pct(v, 1) for v in w]) for n, w, c, e in sets],
                            ring_fmt=lambda k: pct(k * top))

    def _data_weights(self, alts) -> None:
        self.cmp.setHorizontalHeaderLabels([tr("col.criterion"), tr("pri.yours"), tr("pri.entropy"), tr("pri.critic")])
        ent = cri = None
        if len(alts) >= 2:
            x = C.matrix(alts)
            ent, cri = W.entropy(x, C.MAXIMISE).weights, W.critic(x, C.MAXIMISE).weights
        for i, c in enumerate(C.CRITERIA):
            vals = [tr(f"crit.{c.key}"), pct(self.weights[i], 1),
                    pct(ent[i], 1) if ent is not None else "–", pct(cri[i], 1) if cri is not None else "–"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.cmp.setItem(i, j, it)

    def global_weights(self) -> np.ndarray:
        return self.weights

    def snapshot(self) -> dict:
        return {"method": self.levels["families"].method,
                "bwm": {k: lv.bwm.snapshot() for k, lv in self.levels.items()},
                "ahp": {k: lv.ahp.snapshot() for k, lv in self.levels.items()}}

    def restore(self, d: dict | None) -> None:
        d = d or {}
        for k, lv in self.levels.items():
            lv.bwm.restore(d.get("bwm", {}).get(k, {}))
            lv.ahp.restore(d.get("ahp", {}).get(k, {}))
        self._method(d.get("method", "bwm"))

    def on_language(self) -> None:
        self.method.retranslate()
        for lv in self.levels.values():
            lv.bwm.retranslate()
            lv.ahp.retranslate()
            lv.retranslate_reset()
        self.update_hints()
        self.update_weights()

    def on_theme(self) -> None:
        self.chart.restyle()
        self.radar.restyle()
        self.update_weights()
