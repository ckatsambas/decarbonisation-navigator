"""Step 2 · Today's position: what doing nothing costs under every carbon regime."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...engine.compliance import YEARS, Rules, evaluate
from ...engine.regulation.imo_nzf import SCENARIOS
from ...i18n import eur_short, pct, tr
from .. import theme
from ..charts import StackedBarChart
from ..widgets import Fold, Panel, ReadMore, TrLabel, amp, label
from .base import Page
from .regulation import Inputs, Results, spin

# Carbon-price paths (EUA €/t at 2025, 2030, 2050). Scenario assumptions, not forecasts.
PRICE_PATHS = {"low": {2025: 70, 2030: 80, 2050: 100}, "central": {2025: 75, 2030: 110, 2050: 150},
               "high": {2025: 80, 2030: 150, 2050: 250}}


class Choice(QWidget):
    """Row of mutually exclusive buttons whose labels are translation keys."""

    picked = Signal(str)

    def __init__(self, options: list[tuple[str, str]]):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.group = QButtonGroup(self)
        self.options = options
        self.buttons: dict[str, QPushButton] = {}
        for value, _key in options:
            b = QPushButton()
            b.setObjectName("Choice")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, v=value: self.picked.emit(v))
            self.group.addButton(b)
            h.addWidget(b)
            self.buttons[value] = b
        self.retranslate()

    def set_value(self, value: str | None) -> None:
        self.group.setExclusive(False)
        for v, b in self.buttons.items():
            b.setChecked(v == value)
        self.group.setExclusive(True)

    def retranslate(self) -> None:
        for value, key in self.options:
            self.buttons[value].setText(amp(tr(key)))


class BigNumber(Panel):
    def __init__(self, key: str, **fmt):
        super().__init__()
        self.caption = TrLabel(key, "BigLabel", **fmt)
        self.value = label("–", "BigNumber")
        self.sub = label("", "BigSub")
        self.sub.setWordWrap(True)
        self.body.addWidget(self.caption)
        self.body.addWidget(self.value)
        self.body.addWidget(self.sub)


class StepPosition(Page):
    title_key = "step.pos.q"
    lede_key = "step.pos.lede"
    title_style = ("Question", "QuestionLede")

    computed = Signal()

    def __init__(self, state):
        super().__init__(state)
        self.rules = Rules.load()
        self.results = []

        # --- scenario choices (the only decisions asked here)
        sc = QGridLayout()
        sc.setHorizontalSpacing(28)
        sc.setVerticalSpacing(6)
        sc.addWidget(TrLabel("pos.price", "SectionTitle"), 0, 0)
        sc.addWidget(TrLabel("pos.nzf", "SectionTitle"), 0, 1)
        self.price = Choice([("low", "pos.price.low"), ("central", "pos.price.central"), ("high", "pos.price.high")])
        self.nzf = Choice([(s, f"nzf.short.{s}") for s in SCENARIOS])
        sc.addWidget(self.price, 1, 0, Qt.AlignmentFlag.AlignLeft)
        sc.addWidget(self.nzf, 1, 1, Qt.AlignmentFlag.AlignLeft)
        sc.addWidget(ReadMore("pos.price.more"), 2, 0)
        sc.addWidget(ReadMore("in.nzf.more"), 2, 1)
        sc.setColumnStretch(2, 1)
        self.lay.addLayout(sc)

        # --- four numbers
        nums = QHBoxLayout()
        nums.setSpacing(14)
        self.n_total = BigNumber("kpi.total", a=YEARS[0], b=YEARS[-1])
        self.n_2030 = BigNumber("kpi.year", year=2030)
        self.n_2035 = BigNumber("kpi.year", year=2035)
        self.n_cii = BigNumber("kpi.cii", year=2030)
        cap = QHBoxLayout()
        self.cap_label = TrLabel("in.capacity.dwt", "Faint")
        self.capacity = spin(0, 600_000, step=1000)
        self.capacity.setMinimumWidth(110)
        cap.addWidget(self.cap_label)
        cap.addWidget(self.capacity)
        self.n_cii.body.addLayout(cap)
        for n in (self.n_total, self.n_2030, self.n_2035, self.n_cii):
            nums.addWidget(n, 1)
        self.lay.addLayout(nums)
        self.estimate = TrLabel("ww.method.estimated", "Estimate")
        self.lay.addWidget(self.estimate)

        # --- one sentence, one chart
        self.sentence = label("", "Sentence")
        self.sentence.setWordWrap(True)
        self.lay.addWidget(self.sentence)
        cp = Panel("chart.overview")
        self.chart = StackedBarChart(axis="money")
        self.chart.setMinimumHeight(300)
        cp.body.addWidget(self.chart)
        self.lay.addWidget(cp)

        # --- everything else, folded
        self.advanced = Fold("pos.advanced")
        row = QHBoxLayout()
        row.setSpacing(16)
        self.inputs = Inputs(state, self.rules)
        self.inputs.setFixedWidth(410)
        row.addWidget(self.inputs, 0, Qt.AlignmentFlag.AlignTop)
        self.out = Results(self.rules)
        self.out.kpi_panel.hide()
        row.addWidget(self.out, 1)
        holder = QWidget()
        holder.setLayout(row)
        self.advanced.body_layout.addWidget(holder)
        self.lay.addWidget(self.advanced)
        self.lay.addStretch(1)

        self.price.picked.connect(self._pick_price)
        self.nzf.picked.connect(lambda v: self.inputs.nzf.select(v))
        self.capacity.valueChanged.connect(lambda v: self.inputs.capacity.setValue(v))
        self.inputs.changed.connect(self.recompute)
        if state is not None:
            state.ship_changed.connect(self.inputs.load_ship)
            state.view_changed.connect(lambda _: self.recompute())
        self.recompute()

    # ------------------------------------------------------------------ scenario shortcuts
    def _pick_price(self, key: str) -> None:
        for y, v in PRICE_PATHS[key].items():
            self.inputs.prices[y].setValue(v)

    def _sync_controls(self) -> None:
        cur = {y: s.value() for y, s in self.inputs.prices.items()}
        self.price.set_value(next((k for k, p in PRICE_PATHS.items() if p == cur), None))
        self.nzf.set_value(self.inputs.nzf.currentData())
        self.capacity.blockSignals(True)
        self.capacity.setLocale(self.inputs.capacity.locale())
        self.capacity.setValue(self.inputs.capacity.value())
        self.capacity.blockSignals(False)
        t = self.inputs.cii_type.currentData()
        self.cap_label.set_key(f"in.capacity.{self.rules.cii.capacity_unit(t) if t else 'dwt'}")

    # ------------------------------------------------------------------ compute
    @property
    def view(self) -> str:
        return self.state.view if self.state is not None else "eu"

    def recompute(self) -> None:
        self.inputs.ww.setVisible(self.view == "ww")
        prof = self.inputs.profile()
        self.results = evaluate(prof, self.inputs.scenario(self.view), YEARS, self.rules)
        self.out.display(self.results, self.view, prof.eu_share)
        self._sync_controls()
        r = {x.year: x for x in self.results}
        total = sum(x.total_eur for x in self.results)
        self.n_total.value.setText(eur_short(total))
        self.n_2030.value.setText(eur_short(r[2030].total_eur))
        self.n_2035.value.setText(eur_short(r[2035].total_eur))
        c = r[2030].cii
        has_cii = bool(c and not math.isnan(c.attained))
        self.n_cii.value.setText(c.rating if has_cii else "–")
        self.n_cii.value.setStyleSheet(f"color: {getattr(theme.current(), self.rating_colour(c.rating))};"
                                       if has_cii else "")
        self.n_cii.sub.setText("" if has_cii else tr("pos.cii.need"))
        self.estimate.setVisible(self.view == "ww" and prof.eu_share is not None
                                 and prof.eu_share.method == "estimated")
        nzf_total = sum(max(x.nzf.cost_eur, 0) for x in self.results)
        ship = self.inputs.loaded.get("name") if self.inputs.loaded else tr("pos.example_ship")
        year = self.inputs.loaded.year if self.inputs.loaded else 2025
        key = "pos.sentence.nzf" if nzf_total > 0 else "pos.sentence"
        self.sentence.setText(tr(key, ship=ship, year=year, a=eur_short(r[2026].total_eur),
                                 b=eur_short(r[2035].total_eur), total=eur_short(total),
                                 share=pct(nzf_total / total) if total else "0%"))
        p = theme.current()
        years = [x.year for x in self.results]
        self.chart.set_data(years, [(tr("legend.ets_cost"), [x.ets.cost for x in self.results], p.ets),
                                    (tr("legend.fueleu"), [x.fueleu.penalty for x in self.results], p.fueleu),
                                    (tr("legend.nzf"), [max(x.nzf.cost_eur, 0) for x in self.results], p.imo)])
        self.computed.emit()

    @staticmethod
    def rating_colour(rating: str) -> str:
        return {"A": "good", "B": "good", "C": "text", "D": "warn", "E": "bad"}[rating]

    def summary(self) -> dict:
        if not self.results:
            return {}
        r = {x.year: x for x in self.results}
        c = r[2030].cii
        return {"total_eur": sum(x.total_eur for x in self.results), "cost_2030": r[2030].total_eur,
                "cii_2030": c.rating if c and not math.isnan(c.attained) else None}

    # ------------------------------------------------------------------ language / theme
    def on_language(self) -> None:
        self.price.retranslate()
        self.nzf.retranslate()
        self.inputs.retranslate()
        self.out.retranslate()
        self.recompute()

    def on_theme(self) -> None:
        self.chart.restyle()
        self.out.restyle()
        self.recompute()


class StepUpcoming(Page):
    """A step whose tools arrive in a later phase: says what it will do, so the route is clear."""

    title_style = ("Question", "QuestionLede")

    def __init__(self, state, n: int, phase: int, bullets: int):
        self.title_key, self.lede_key = f"step.{n}.q", f"step.{n}.lede"
        super().__init__(state)
        box = QWidget()
        box.setObjectName("Upcoming")
        v = QVBoxLayout(box)
        v.setSpacing(10)
        v.addWidget(TrLabel("upcoming.badge", "Badge", n=phase), 0, Qt.AlignmentFlag.AlignLeft)
        for i in range(1, bullets + 1):
            v.addWidget(TrLabel(f"step.{n}.b{i}", "Muted", wrap=True))
        box.setMaximumWidth(860)
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.lay.addWidget(box)
        self.lay.addStretch(1)
