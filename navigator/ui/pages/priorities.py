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
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QSlider,
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
from ..charts import HBarChart
from ..widgets import Panel, ReadMore, TrLabel, label
from .base import Page
from .position import Choice

LEVELS = {"families": list(C.FAMILIES), "money": ["npv", "capex"],
          "operations": ["offhire", "cargo", "availability", "safety"]}


def item_name(key: str) -> str:
    return tr(f"fam.{key}") if key in C.FAMILIES else tr(f"crit.{key}")


class Scale(QWidget):
    """A 1–9 judgement slider with its verbal meaning."""

    changed = Signal()

    def __init__(self, lo: int = 1, hi: int = 9, value: int = 1, two_sided: bool = False):
        super().__init__()
        self.two_sided = two_sided
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.slider.setPageStep(1)
        self.slider.setMinimumWidth(180)
        self.text = label("", "Muted")
        self.text.setMinimumWidth(215)
        h.addWidget(self.slider, 1)
        h.addWidget(self.text)
        self.slider.valueChanged.connect(self._moved)
        self._moved()

    def _moved(self) -> None:
        self.retranslate()
        self.changed.emit()

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, v: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(v))
        self.slider.blockSignals(False)
        self.retranslate()

    def intensity(self) -> int:
        v = self.slider.value()
        return abs(v) + 1 if self.two_sided else v

    def retranslate(self) -> None:
        n = self.intensity()
        self.text.setText(f"{n} · {tr(f'scale.{n}')}")


class BwmBlock(QWidget):
    changed = Signal()

    def __init__(self, items: list[str]):
        super().__init__()
        self.items = items
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.best_label, self.worst_label = TrLabel("pri.best", "Faint"), TrLabel("pri.worst", "Faint")
        self.best, self.worst = QComboBox(), QComboBox()
        top.addWidget(self.best_label)
        top.addWidget(self.best)
        top.addSpacing(24)
        top.addWidget(self.worst_label)
        top.addWidget(self.worst)
        top.addStretch(1)
        v.addLayout(top)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        v.addLayout(self.grid)
        self.bo: dict[str, Scale] = {}
        self.ow: dict[str, Scale] = {}
        self.q_bo: dict[str, object] = {}
        self.q_ow: dict[str, object] = {}
        for i, k in enumerate(items):
            self.q_bo[k] = label("", "Muted", wrap=True)
            self.q_ow[k] = label("", "Muted", wrap=True)
            self.bo[k], self.ow[k] = Scale(value=2), Scale(value=2)
            self.grid.addWidget(self.q_bo[k], 2 * i, 0)
            self.grid.addWidget(self.bo[k], 2 * i, 1)
            self.grid.addWidget(self.q_ow[k], 2 * i + 1, 0)
            self.grid.addWidget(self.ow[k], 2 * i + 1, 1)
            self.bo[k].changed.connect(self.changed)
            self.ow[k].changed.connect(self.changed)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self._fill_boxes(items[0], items[-1])
        self.best.currentIndexChanged.connect(self._picked)
        self.worst.currentIndexChanged.connect(self._picked)
        self._layout()

    def _fill_boxes(self, best: str, worst: str) -> None:
        for box, sel in ((self.best, best), (self.worst, worst)):
            box.blockSignals(True)
            box.clear()
            for k in self.items:
                box.addItem(item_name(k), k)
            box.setCurrentIndex(self.items.index(sel))
            box.blockSignals(False)

    def _picked(self) -> None:
        if self.best.currentData() == self.worst.currentData():
            other = next(k for k in self.items if k != self.best.currentData())
            self.worst.blockSignals(True)
            self.worst.setCurrentIndex(self.items.index(other))
            self.worst.blockSignals(False)
        self._layout()
        self.changed.emit()

    def _layout(self) -> None:
        b, w = self.best.currentData(), self.worst.currentData()
        for k in self.items:
            self.q_bo[k].setVisible(k != b)
            self.bo[k].setVisible(k != b)
            self.q_ow[k].setVisible(k not in (w, b))
            self.ow[k].setVisible(k not in (w, b))
            self.q_bo[k].setText(tr("pri.q.bo", best=item_name(b), other=item_name(k)))
            self.q_ow[k].setText(tr("pri.q.ow", worst=item_name(w), other=item_name(k)))

    def reset(self) -> None:
        """Back to the starting point: first item most, last least important, every comparison at 2."""
        self._fill_boxes(self.items[0], self.items[-1])
        for sc in (*self.bo.values(), *self.ow.values()):
            sc.set_value(2)
        self._layout()
        self.changed.emit()

    def result(self) -> W.WeightResult:
        b, w = self.best.currentData(), self.worst.currentData()
        bi, wi = self.items.index(b), self.items.index(w)
        a_b = [1.0 if k == b else float(self.bo[k].value()) for k in self.items]
        a_w = [1.0 if k == w else (a_b[wi] if k == b else float(self.ow[k].value())) for k in self.items]
        return W.bwm(bi, wi, a_b, a_w)

    def snapshot(self) -> dict:
        return {"best": self.best.currentData(), "worst": self.worst.currentData(),
                "bo": {k: s.value() for k, s in self.bo.items()}, "ow": {k: s.value() for k, s in self.ow.items()}}

    def restore(self, d: dict) -> None:
        if not d:
            return
        self._fill_boxes(d.get("best", self.items[0]), d.get("worst", self.items[-1]))
        for k, v in d.get("bo", {}).items():
            if k in self.bo:
                self.bo[k].set_value(v)
        for k, v in d.get("ow", {}).items():
            if k in self.ow:
                self.ow[k].set_value(v)
        self._layout()

    def retranslate(self) -> None:
        self._fill_boxes(self.best.currentData(), self.worst.currentData())
        for s in (*self.bo.values(), *self.ow.values()):
            s.retranslate()
        self._layout()


class AhpBlock(QWidget):
    """Every pair once: slider left = first item more important, right = second."""

    changed = Signal()

    def __init__(self, items: list[str]):
        super().__init__()
        self.items = items
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        self.pairs: dict[tuple[int, int], Scale] = {}
        self.names: dict[tuple[int, int], tuple] = {}
        r = 0
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = label("", "Muted"), label("", "Muted")
                s = Scale(-8, 8, 0, two_sided=True)
                g.addWidget(a, r, 0, Qt.AlignmentFlag.AlignRight)
                g.addWidget(s, r, 1)
                g.addWidget(b, r, 2)
                self.pairs[(i, j)] = s
                self.names[(i, j)] = (a, b)
                s.changed.connect(self.changed)
                r += 1
        g.setColumnStretch(1, 1)
        self.retranslate()

    def reset(self) -> None:
        """Every pair back to equal importance."""
        for sc in self.pairs.values():
            sc.set_value(0)
        self.changed.emit()

    def result(self) -> W.WeightResult:
        j = {}
        for (i, k), s in self.pairs.items():
            v = s.value()                   # left (negative) = first item more important
            j[(i, k)] = (1 - v) if v < 0 else 1 / (1 + v)
        return W.ahp(W.ahp_matrix(len(self.items), j))

    def snapshot(self) -> dict:
        return {f"{i}-{k}": s.value() for (i, k), s in self.pairs.items()}

    def restore(self, d: dict) -> None:
        for key, v in (d or {}).items():
            i, k = (int(x) for x in key.split("-"))
            if (i, k) in self.pairs:
                self.pairs[(i, k)].set_value(v)

    def retranslate(self) -> None:
        for (i, k), (a, b) in self.names.items():
            a.setText(item_name(self.items[i]))
            b.setText(item_name(self.items[k]))
            self.pairs[(i, k)].retranslate()


class Level(Panel):
    changed = Signal()

    def __init__(self, key: str, items: list[str]):
        super().__init__(f"pri.level.{key}")
        self.key, self.items = key, items
        top = QHBoxLayout()
        self.hint = label("", "Faint", wrap=True)
        top.addWidget(self.hint, 1)
        self.reset_btn = QToolButton()
        self.reset_btn.setObjectName("Reset")
        self.reset_btn.setText("\u21BA")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.clicked.connect(self.reset)
        top.addWidget(self.reset_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(top)
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

    def reset(self) -> None:
        """Reset this section's answers (only the method shown)."""
        (self.bwm if self.method == "bwm" else self.ahp).reset()

    def retranslate_reset(self) -> None:
        self.reset_btn.setToolTip(tr("pri.reset"))

    def set_method(self, method: str) -> None:
        self.method = method
        self.bwm.setVisible(method == "bwm")
        self.ahp.setVisible(method == "ahp")

    def result(self) -> W.WeightResult:
        return self.bwm.result() if self.method == "bwm" else self.ahp.result()

    def show_status(self, r: W.WeightResult) -> None:
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
        rp.body.addWidget(self.chart)
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
        alts = self.options.alternatives()
        if len(alts) < 2:
            for lv in self.levels.values():
                lv.hint.setText(tr("pri.need_shortlist"))
            return
        x = {k: [a.values[k] for a in alts] for k in C.KEYS}

        def rng(k, fmt):
            return tr("pri.range", lo=fmt(min(x[k])), hi=fmt(max(x[k])))

        txt = {
            "money": tr("crit.npv") + ": " + rng("npv", eur_short) + "; " + tr("crit.capex") + ": " + rng("capex", eur_short),
            "climate": tr("crit.cut") + ": " + rng("cut", pct),
            "technology": tr("crit.trl") + ": " + rng("trl", lambda v: f"TRL {num(v)}"),
            "operations": "; ".join([tr("crit.offhire") + ": " + rng("offhire", lambda v: tr("opt.days", n=num(v))),
                                     tr("crit.cargo") + ": " + rng("cargo", lambda v: pct(v, 1)),
                                     tr("crit.availability") + ": " + rng("availability", lambda v: f"{num(v)}/5"),
                                     tr("crit.safety") + ": " + rng("safety", lambda v: f"{num(v)}/5")]),
            "regulation": tr("crit.nzf_exposure") + ": " + rng("nzf_exposure", eur_short),
        }
        self.levels["families"].hint.setText(tr("pri.hint.families") + "\n" + "\n".join(
            f"• {tr(f'fam.{f}')}: {txt[f]}" for f in C.FAMILIES))
        self.levels["money"].hint.setText(txt["money"])
        self.levels["operations"].hint.setText(txt["operations"])
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
        self.changed.emit()

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
        self.update_weights()
