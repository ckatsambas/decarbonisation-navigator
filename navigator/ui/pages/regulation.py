"""Carbon regulations page: EU ETS calculator, placeholders for FuelEU and the IMO NZF,
and the full list of parameters with their sources."""
from __future__ import annotations

import json

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...engine import params as P
from ...engine.models import AnnualEmissions, ScopeSplit, Ship, ShipCategory, YearSeries
from ...engine.regulation.eu_ets import EtsRules, cost_path, total_cost
from ...i18n import eur_short, language, num, pct, tr
from .. import theme
from ..charts import BarChart
from ..widgets import Kpi, Panel, TrLabel, amp
from .base import Page

YEARS = range(2024, 2051)
SCOPES = ("intra_eu", "at_berth", "from_eu", "to_eu", "outside")

# Illustrative Kamsarmax trading partly with the EU (not a real ship)
DEFAULTS = {"gt": 44_000, "intra_eu": 0, "at_berth": 1_000, "from_eu": 4_000, "to_eu": 3_000,
            "outside": 11_000, "ch4": 0.4, "n2o": 1.0, "p2025": 75, "p2030": 110, "p2050": 150}


def ui_locale() -> QLocale:
    """Spin boxes show 44.000 in Greek and 44,000 in English."""
    if language() == "el":
        return QLocale(QLocale.Language.Greek, QLocale.Country.Greece)
    return QLocale(QLocale.Language.English, QLocale.Country.UnitedKingdom)


def spin(value: float, maximum: float = 1e7, decimals: int = 0, step: float = 100) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, maximum)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setGroupSeparatorShown(True)
    s.setLocale(ui_locale())
    s.setValue(value)
    s.setAlignment(Qt.AlignmentFlag.AlignRight)
    s.setMinimumWidth(120)
    return s


class TrCombo(QComboBox):
    """Combo whose item texts are translation keys and whose data are engine values."""

    def __init__(self, items: list[tuple[str, object]]):
        super().__init__()
        self.items = items
        for key, data in items:
            self.addItem(tr(key), data)

    def retranslate(self) -> None:
        for i, (key, _) in enumerate(self.items):
            self.setItemText(i, tr(key))


class EtsCalculator(QWidget):
    def __init__(self):
        super().__init__()
        self.rules = EtsRules.load()
        grid = QHBoxLayout(self)
        grid.setContentsMargins(0, 8, 0, 0)
        grid.setSpacing(16)

        # ---------------------------------------------------------------- inputs
        left = QVBoxLayout()
        left.setSpacing(12)
        self.f_rows: list[tuple[QFormLayout, int, str]] = []

        ship = Panel("ets.panel.ship")
        f = self._form(ship)
        self.gt = spin(DEFAULTS["gt"], 600_000, step=1000)
        self.category = TrCombo([("cat.cargo", ShipCategory.CARGO), ("cat.passenger", ShipCategory.PASSENGER),
                                 ("cat.offshore", ShipCategory.OFFSHORE), ("cat.other", ShipCategory.OTHER)])
        self.ice = TrCombo([("ice.none", None), ("IA", "IA"), ("IA Super", "IA Super")])
        self._row(f, "ets.gt", self.gt)
        self._row(f, "ets.category", self.category)
        self._row(f, "ets.ice", self.ice)
        left.addWidget(ship)

        em = Panel("ets.panel.emissions")
        f = self._form(em)
        self.scope = {}
        for k in SCOPES:
            self.scope[k] = spin(DEFAULTS[k])
            self._row(f, f"scope.{k}", self.scope[k])
        left.addWidget(em)

        gases = Panel("ets.panel.other_gases")
        f = self._form(gases)
        self.ch4 = spin(DEFAULTS["ch4"], 10_000, decimals=2, step=0.1)
        self.n2o = spin(DEFAULTS["n2o"], 10_000, decimals=2, step=0.1)
        self._row(f, "ets.ch4", self.ch4)
        self._row(f, "ets.n2o", self.n2o)
        gases.body.addWidget(TrLabel("ets.gases_hint", "Faint", wrap=True))
        left.addWidget(gases)

        price = Panel("ets.panel.price")
        f = self._form(price)
        self.prices = {y: spin(DEFAULTS[f"p{y}"], 2_000, step=5) for y in (2025, 2030, 2050)}
        for y, s in self.prices.items():
            f.addRow(str(y), s)
        price.body.addWidget(TrLabel("ets.price_hint", "Faint", wrap=True))
        left.addWidget(price)
        left.addStretch(1)

        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(400)
        grid.addWidget(lw, 0, Qt.AlignmentFlag.AlignTop)

        # ---------------------------------------------------------------- results
        right = QVBoxLayout()
        right.setSpacing(12)
        kp = Panel()
        kg = QGridLayout()
        kg.setHorizontalSpacing(28)
        self.k_cov = Kpi("ets.kpi.covered")
        self.k_share = Kpi("ets.kpi.share")
        self.k_year = Kpi("ets.kpi.year", year=2026)
        self.k_total = Kpi("ets.kpi.total", a=YEARS[0], b=YEARS[-1])
        for i, k in enumerate((self.k_cov, self.k_share, self.k_year, self.k_total)):
            kg.addWidget(k, 0, i)
            kg.setColumnStretch(i, 1)
        kp.body.addLayout(kg)
        self.scope_warn = TrLabel("ets.out_of_scope", "Warning", wrap=True)
        kp.body.addWidget(self.scope_warn)
        right.addWidget(kp)

        cp = Panel("ets.chart.title")
        self.chart = BarChart()
        cp.body.addWidget(self.chart)
        right.addWidget(cp)

        tp = Panel()
        self.table = QTableWidget(0, 6)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.table.setMinimumHeight(320)
        tp.body.addWidget(self.table)
        right.addWidget(tp)
        grid.addLayout(right, 1)

        for s in [self.gt, self.ch4, self.n2o, *self.scope.values(), *self.prices.values()]:
            s.valueChanged.connect(self.recompute)
        self.category.currentIndexChanged.connect(self.recompute)
        self.ice.currentIndexChanged.connect(self.recompute)
        self.recompute()

    # ------------------------------------------------------------------ helpers
    def _form(self, panel: Panel) -> QFormLayout:
        f = QFormLayout()
        f.setHorizontalSpacing(14)
        f.setVerticalSpacing(8)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        panel.body.addLayout(f)
        return f

    def _row(self, f: QFormLayout, key: str, w: QWidget) -> None:
        lab = TrLabel(key, "Muted", wrap=True)
        f.addRow(lab, w)

    def ship(self) -> Ship:
        return Ship(imo="", name="", ship_type="", category=self.category.currentData(),
                    gross_tonnage=self.gt.value(), ice_class=self.ice.currentData())

    def emissions(self) -> AnnualEmissions:
        co2 = ScopeSplit(**{k: s.value() for k, s in self.scope.items()})
        tot = co2.total or 1.0
        return AnnualEmissions(co2=co2, ch4=co2.scaled(self.ch4.value() / tot), n2o=co2.scaled(self.n2o.value() / tot))

    # ------------------------------------------------------------------ compute
    def recompute(self) -> None:
        ship, em = self.ship(), self.emissions()
        prices = YearSeries({y: s.value() for y, s in self.prices.items()})
        path = cost_path(ship, em, prices, YEARS, self.rules)
        self.path = path
        full = next((r for r in path if r.year == 2026), path[-1])
        total_co2e = sum(em.gas(g).total * self.rules.gwp[g] for g in self.rules.gwp)
        self.k_cov.value.setText(num(full.covered))
        self.k_share.value.setText(pct(full.covered / total_co2e) if total_co2e else "–")
        self.k_year.value.setText(eur_short(full.cost))
        self.k_total.value.setText(eur_short(total_cost(path)))
        self.scope_warn.setVisible(not any(r.in_scope for r in path))
        self.chart.set_data([r.year for r in path], [r.cost for r in path], theme.current().ets)
        self._fill_table()

    def _fill_table(self) -> None:
        cols = ["ets.col.year", "ets.col.covered", "ets.col.phase", "ets.col.allowances", "ets.col.price",
                "ets.col.cost"]
        self.table.setHorizontalHeaderLabels([tr(c) for c in cols])
        self.table.setRowCount(len(self.path))
        for i, r in enumerate(self.path):
            vals = [str(r.year), num(r.covered), pct(r.phase_in), num(r.allowances), num(r.price, 2), num(r.cost)]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, it)

    def retranslate(self) -> None:
        loc = ui_locale()
        for s in self.findChildren(QDoubleSpinBox):
            s.setLocale(loc)
            s.setValue(s.value())            # redraw with the new separators
        self.category.retranslate()
        self.ice.retranslate()
        self.recompute()

    def restyle(self) -> None:
        self.chart.restyle()
        self.recompute()


class ParamsTable(QWidget):
    """Every regulatory parameter with its source, check date and verification status."""

    COLS = ("params.col.param", "params.col.value", "params.col.source", "params.col.checked",
            "params.col.status")

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 8, 0, 0)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.table)
        self.sets = [P.load(n) for n in P.available()]
        self.fill()

    def fill(self) -> None:
        self.table.setHorizontalHeaderLabels([tr(c) for c in self.COLS])
        rows = [(ps, p) for ps in self.sets for p in ps.values.values()]
        self.table.setRowCount(len(rows))
        theme.current()
        for i, (ps, p) in enumerate(rows):
            src = ps.source_of(p.key)
            value = p.value if isinstance(p.value, (int, float, str)) else json.dumps(p.value, ensure_ascii=False)
            ok = p.status == P.VERIFIED
            cells = [f"{ps.name}.{p.key}", str(value), src.title, src.checked,
                     tr("params.verified") if ok else tr("params.verify")]
            for j, text in enumerate(cells):
                it = QTableWidgetItem(text)
                tip = "\n".join(x for x in (p.note, src.url) if x)
                if tip:
                    it.setToolTip(tip)
                if j == 4:
                    it.setForeground(theme.c("good" if ok else "warn"))
                self.table.setItem(i, j, it)
        self.table.resizeRowsToContents()


class RegulationPage(Page):
    title_key = "reg.title"
    lede_key = "reg.lede"

    def __init__(self):
        super().__init__()
        self.tabs = QTabWidget()
        self.ets = EtsCalculator()
        self.params = ParamsTable()
        self.fueleu = TrLabel("placeholder.phase", "Placeholder", n=1)
        self.nzf = TrLabel("placeholder.phase", "Placeholder", n=1)
        for w in (self.fueleu, self.nzf):
            w.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.tab_keys = ["reg.tab.ets", "reg.tab.fueleu", "reg.tab.nzf", "reg.tab.params"]
        for w, k in zip((self.ets, self.fueleu, self.nzf, self.params), self.tab_keys):
            self.tabs.addTab(w, amp(tr(k)))
        self.lay.addWidget(self.tabs, 1)

    def unverified_count(self) -> int:
        return sum(len(ps.unverified()) for ps in self.params.sets)

    def on_language(self) -> None:
        for i, k in enumerate(self.tab_keys):
            self.tabs.setTabText(i, amp(tr(k)))
        self.ets.retranslate()
        self.params.fill()

    def on_theme(self) -> None:
        self.ets.restyle()
        self.params.fill()
