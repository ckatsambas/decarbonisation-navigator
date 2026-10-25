"""Detailed inputs and results for all carbon regimes (shown under "Advanced" in step 2).

Inputs: ship, emissions, fuel, activity outside the EU (worldwide view only) and scenario.
Results: key figures and tabs (overview, EU ETS, FuelEU, IMO NZF, CII, sources).
"""
from __future__ import annotations

import json
import math

from PySide6.QtCore import QLocale, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...engine import fuels as F
from ...engine import library as L
from ...engine import params as P
from ...engine import reference as R
from ...engine.compliance import BASELINES, YEARS, Profile, Rules, Scenario, YearResult
from ...engine.estimate import EuShare, user_share
from ...engine.models import AnnualEmissions, ScopeSplit, Ship, ShipCategory, YearSeries
from ...engine.regulation.cii import MRV_TO_CII
from ...engine.regulation.imo_nzf import SCENARIOS
from ...i18n import eur_short, language, num, pct, pick, tr
from .. import theme
from ..charts import BarChart, StackedBarChart
from ..widgets import Kpi, Panel, ReadMore, TrLabel, amp, size_label

EU_SCOPES = ("intra_eu", "in_port", "from_eu", "to_eu")
CII_TYPES = sorted(set(MRV_TO_CII.values()))

# Illustrative Kamsarmax trading partly with the EU (not a real ship)
DEFAULTS = {"gt": 44_000, "intra_eu": 0, "in_port": 1_000, "from_eu": 4_000, "to_eu": 3_000, "ch4": 0.4,
            "n2o": 1.0, "eu_share": 42, "capacity": 82_000, "distance": 60_000, "cii_type": "bulk",
            "fuel1": "hfo", "share1": 100, "fuel2": None, "p2025": 75, "p2030": 110, "p2050": 150}


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
    """Combo whose item texts are translation keys (or callables) and whose data are engine values."""

    def __init__(self, items: list[tuple[object, object]]):
        super().__init__()
        self.items = list(items)
        for key, data in self.items:
            self.addItem(self._text(key), data)

    @staticmethod
    def _text(key) -> str:
        return key() if callable(key) else tr(key)

    def retranslate(self) -> None:
        for i, (key, _) in enumerate(self.items):
            self.setItemText(i, self._text(key))

    def select(self, data) -> None:
        i = self.findData(data)
        self.setCurrentIndex(max(i, 0))


def fill_table(table: QTableWidget, header_keys: list[str], rows: list[list[str]], colors: dict | None = None) -> None:
    table.setColumnCount(len(header_keys))
    table.setHorizontalHeaderLabels([tr(k) for k in header_keys])
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if colors and (i, j) in colors:
                it.setForeground(colors[(i, j)])
            table.setItem(i, j, it)


def new_table(min_height: int = 320) -> QTableWidget:
    t = QTableWidget(0, 1)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    hh.setStretchLastSection(True)
    t.setMinimumHeight(min_height)
    return t


# =============================================================================== inputs
class Inputs(QWidget):
    changed = Signal()

    def __init__(self, state, rules: Rules):
        super().__init__()
        self.state, self.rules = state, rules
        self.loaded = None                          # mrv.ShipYear the inputs came from
        self.loaded_em: AnnualEmissions | None = None
        self.scope_override: bool | None = None
        self.coverage_ratio: float | None = None
        self.share_estimate: EuShare | None = None
        self.size_estimate = None                      # Estimate of capacity (from MRV data)
        self.standard = None                           # (class key, pattern, capacity) for a library ship
        self._filling = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        # source banner
        self.source = Panel()
        self.source_text = TrLabel("ets.from_mrv", "Muted", wrap=True, name="", imo="", year="")
        self.source.body.addWidget(self.source_text)
        self.ratio_text = TrLabel("ets.ratio", "Warning", wrap=True, pct="", until="")
        self.ratio_text.hide()
        self.source.body.addWidget(self.ratio_text)
        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self.reset_example)
        self.source.body.addWidget(self.reset_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.source.hide()
        v.addWidget(self.source)

        # ship
        ship = Panel("in.panel.ship")
        f = self._form(ship)
        self.gt = spin(DEFAULTS["gt"], 600_000, step=1000)
        self.category = TrCombo([("cat.cargo", ShipCategory.CARGO), ("cat.passenger", ShipCategory.PASSENGER),
                                 ("cat.offshore", ShipCategory.OFFSHORE), ("cat.other", ShipCategory.OTHER)])
        self.ice = TrCombo([("ice.none", None), ("IA", "IA"), ("IA Super", "IA Super")])
        self.cii_type = TrCombo([("in.fuel.none", None)] + [(f"cii.type.{t}", t) for t in CII_TYPES])
        self.capacity = spin(DEFAULTS["capacity"], 600_000, step=1000)
        self.capacity_label = TrLabel("in.capacity.dwt", "Muted", wrap=True)
        self.distance = spin(DEFAULTS["distance"], 1_000_000, step=1000)
        self.domestic = QCheckBox()
        self._row(f, "ets.gt", self.gt)
        self._row(f, "ets.category", self.category)
        self._row(f, "ets.ice", self.ice)
        self._row(f, "in.cii_type", self.cii_type)
        f.addRow(self.capacity_label, self.capacity)
        self._row(f, "in.distance", self.distance)
        ship.body.addWidget(self.domestic)
        ship.body.addWidget(ReadMore("in.domestic.more"))
        v.addWidget(ship)

        # emissions
        em = Panel("ets.panel.emissions")
        f = self._form(em)
        self.scope = {k: spin(DEFAULTS[k]) for k in EU_SCOPES}
        for k, s in self.scope.items():
            self._row(f, f"scope.{k}", s)
        self.ch4 = spin(DEFAULTS["ch4"], 10_000, decimals=2, step=0.1)
        self.n2o = spin(DEFAULTS["n2o"], 10_000, decimals=2, step=0.1)
        self._row(f, "ets.ch4", self.ch4)
        self._row(f, "ets.n2o", self.n2o)
        em.body.addWidget(TrLabel("ets.gases_hint", "Faint", wrap=True))
        v.addWidget(em)

        # fuel
        fuel = Panel("in.panel.fuel")
        f = self._form(fuel)
        names = [(lambda k=k: pick(rules.fuels[k].name), k) for k in rules.fuels]
        self.fuel1 = TrCombo(names)
        self.fuel2 = TrCombo([("in.fuel.none", None)] + names)
        self.share1 = spin(DEFAULTS["share1"], 100, decimals=0, step=5)
        self._row(f, "in.fuel1", self.fuel1)
        self._row(f, "in.share1", self.share1)
        self._row(f, "in.fuel2", self.fuel2)
        self.fuel_more = ReadMore("in.fuel.more.oil", cf="")
        self.fuel_more.hide()
        fuel.body.addWidget(self.fuel_more)
        v.addWidget(fuel)

        # worldwide
        self.ww = Panel("in.panel.ww")
        f = self._form(self.ww)
        self.eu_share = spin(DEFAULTS["eu_share"], 100, decimals=0, step=5)
        self.eu_share.setMinimum(1)
        self._row(f, "in.eu_share", self.eu_share)
        self.ww_method = TrLabel("ww.method.user", "Estimate", wrap=True)
        self.ww.body.addWidget(self.ww_method)
        self.ww_more = ReadMore("ww.more", hours="", cls="", days="", dlo="", dhi="", share="", low="", high="", ratio="")
        self.ww.body.addWidget(self.ww_more)
        v.addWidget(self.ww)

        # scenario
        sc = Panel("in.panel.scenario")
        f = self._form(sc)
        self.prices = {y: spin(DEFAULTS[f"p{y}"], 2_000, step=5) for y in (2025, 2030, 2050)}
        for y, s in self.prices.items():
            f.addRow(f"EUA {y} (€/t)", s)
        self.nzf = TrCombo([(f"nzf.{s}", s) for s in SCENARIOS])
        self._row(f, "in.nzf", self.nzf)
        self.baseline = TrCombo([(f"base.{b}", b) for b in BASELINES])
        self._row(f, "in.baseline", self.baseline)
        sc.body.addWidget(TrLabel("ets.price_hint", "Faint", wrap=True))
        sc.body.addWidget(ReadMore("in.nzf.more"))
        v.addWidget(sc)
        v.addStretch(1)

        self.fuel1.select(DEFAULTS["fuel1"])
        self.cii_type.select(DEFAULTS["cii_type"])
        self._timer = QTimer(self, singleShot=True, interval=60)
        self._timer.timeout.connect(self.changed.emit)
        for s in [self.ch4, self.n2o, *self.scope.values()]:
            s.valueChanged.connect(self._emissions_edited)
        for s in [self.distance, self.share1, *self.prices.values()]:
            s.valueChanged.connect(self._poke)
        self.capacity.valueChanged.connect(self._capacity_edited)
        self.eu_share.valueChanged.connect(self._share_edited)
        self.gt.valueChanged.connect(self._ship_edited)
        self.category.currentIndexChanged.connect(self._ship_edited)
        for c in (self.ice, self.nzf, self.fuel1, self.fuel2, self.baseline):
            c.currentIndexChanged.connect(self._poke)
        self.cii_type.currentIndexChanged.connect(self._cii_type_changed)
        self.domestic.toggled.connect(self._poke)
        self.retranslate()
        self._cii_type_changed()

    # ------------------------------------------------------------------ helpers
    def _form(self, panel: Panel) -> QFormLayout:
        f = QFormLayout()
        f.setHorizontalSpacing(14)
        f.setVerticalSpacing(8)
        panel.body.addLayout(f)
        return f

    def _row(self, f: QFormLayout, key: str, w: QWidget) -> None:
        f.addRow(TrLabel(key, "Muted", wrap=True), w)

    def _poke(self) -> None:
        if not self._filling:
            self._timer.start()

    def _emissions_edited(self) -> None:
        if not self._filling:
            self.loaded_em = None              # back to the proportional split of the entered figures
            self.coverage_ratio = None
            self.ratio_text.hide()
        self._poke()

    def _ship_edited(self) -> None:
        if not self._filling:
            self.scope_override = None
        self._poke()

    def _capacity_edited(self) -> None:
        if not self._filling:
            self.size_estimate = None          # the user's own value replaces the estimate
        self._poke()

    def _share_edited(self) -> None:
        if not self._filling:
            self.share_estimate = None         # the user's own value (method a)
            self._show_share_method()
        self._poke()

    def _cii_type_changed(self) -> None:
        t = self.cii_type.currentData()
        unit = self.rules.cii.capacity_unit(t) if t else "dwt"
        self.capacity_label.set_key(f"in.capacity.{unit}")
        self._poke()

    # ------------------------------------------------------------------ build engine inputs
    def ship(self) -> Ship:
        return Ship(imo=self.loaded.imo if self.loaded else "", name="", ship_type="",
                    category=self.category.currentData(), gross_tonnage=self.gt.value(),
                    ice_class=self.ice.currentData(), ets_scope_override=self.scope_override,
                    ets_coverage_ratio=self.coverage_ratio)

    def emissions(self) -> AnnualEmissions:
        if self.loaded_em is not None:
            return self.loaded_em
        co2 = ScopeSplit(**{k: s.value() for k, s in self.scope.items()})
        tot = co2.total or 1.0
        return AnnualEmissions(co2=co2, ch4=co2.scaled(self.ch4.value() / tot), n2o=co2.scaled(self.n2o.value() / tot))

    def fuel_mix(self) -> F.FuelMix:
        f1, f2, s = self.fuel1.currentData(), self.fuel2.currentData(), self.share1.value() / 100
        if not f2 or f2 == f1 or s >= 1:
            return {f1: 1.0}
        return F.normalise({f1: s, f2: 1 - s})

    def eu_share_value(self) -> EuShare:
        if self.share_estimate is not None:
            return self.share_estimate
        return user_share(self.eu_share.value() / 100)

    def profile(self) -> Profile:
        return Profile(ship=self.ship(), emissions=self.emissions(), fuel_mix=self.fuel_mix(),
                       cii_type=self.cii_type.currentData(), capacity=self.capacity.value(),
                       distance_nm=self.distance.value(), domestic_only=self.domestic.isChecked(),
                       eu_share=self.eu_share_value())

    def scenario(self, view: str) -> Scenario:
        return Scenario(eua=YearSeries({y: s.value() for y, s in self.prices.items()}),
                        nzf=self.nzf.currentData(), view=view, baseline=self.baseline.currentData())

    # ------------------------------------------------------------------ from EU MRV
    def _fill(self, vals: dict, category, ice, fuel_mix: F.FuelMix, cii_type, domestic: bool) -> None:
        self._filling = True
        try:
            self.gt.setValue(vals["gt"])
            for k in EU_SCOPES:
                self.scope[k].setValue(vals[k])
            self.ch4.setValue(vals["ch4"])
            self.n2o.setValue(vals["n2o"])
            self.category.select(category)
            if ice and self.ice.findData(ice) < 0:
                self.ice.items.append((lambda i=ice: i, ice))
                self.ice.addItem(ice, ice)
            self.ice.select(ice)
            fuels = sorted(fuel_mix.items(), key=lambda kv: -kv[1])
            self.fuel1.select(fuels[0][0])
            self.share1.setValue(round(fuels[0][1] * 100))
            self.fuel2.select(fuels[1][0] if len(fuels) > 1 else None)
            self.cii_type.select(cii_type)
            self.capacity.setValue(vals["capacity"])
            self.distance.setValue(vals["distance"])
            self.domestic.setChecked(domestic)
            self.eu_share.setValue(vals["eu_share"])
        finally:
            self._filling = False
        self._cii_type_changed()

    def _load_profile(self, p: Profile) -> None:
        em = p.emissions
        vals = {"gt": p.ship.gross_tonnage, "ch4": em.ch4.total, "n2o": em.n2o.total, "capacity": p.capacity or 0,
                "distance": p.distance_nm, "eu_share": round(p.eu_share.share * 100) if p.eu_share else 100}
        vals.update({k: getattr(em.co2, k) for k in EU_SCOPES})
        self._fill(vals, p.ship.category, p.ship.ice_class, p.fuel_mix, p.cii_type, p.domestic_only)
        self.loaded_em = em
        self.scope_override, self.coverage_ratio = p.ship.ets_scope_override, p.ship.ets_coverage_ratio
        self.share_estimate = p.eu_share
        self.size_estimate = p.size

    def load_standard(self, std) -> None:
        """A standard ship from the library: (class key, trading pattern, capacity or None)."""
        if std is None:
            return
        key, pattern, capacity = std
        c = R.by_key(key)
        self._load_profile(L.profile(c, pattern, capacity))
        self.loaded, self.standard = None, std
        self.share_estimate = None                     # the pattern's share is the user's value (method a)
        self.size_estimate = None
        self.source_text.set_key("std.source", name=c.label, size=size_label(c), unit="")
        self.ratio_text.hide()
        self.fuel_more.hide()
        self.source.show()
        self._show_share_method()
        self.changed.emit()

    def load_ship(self, ship_year) -> None:
        if ship_year is None:
            return
        p = ship_year.profile()
        self._load_profile(p)
        self.loaded, self.standard = ship_year, None
        self.source_text.set_key("ets.from_mrv", name=p.ship.name, imo=p.ship.imo, year=ship_year.year)
        if self.coverage_ratio is not None:
            self.ratio_text.set_key("ets.ratio", pct=pct(min(max(self.coverage_ratio, 0), 1), 1),
                                    until=self.rules.ets.derogations_until)
        self.ratio_text.setVisible(self.coverage_ratio is not None)
        cf = ship_year.co2_per_fuel()
        _, kind = F.infer_mix(cf)
        if cf and kind in ("oil", "lng"):
            self.fuel_more.set_key(f"in.fuel.more.{kind}", cf=num(cf, 3))
            self.fuel_more.show()
        self.source.show()
        self._show_share_method()
        self.changed.emit()

    def reset_example(self) -> None:
        self._fill(DEFAULTS, ShipCategory.CARGO, None, {"hfo": 1.0}, "bulk", False)
        self.loaded = self.loaded_em = self.scope_override = self.coverage_ratio = self.share_estimate = None
        self.size_estimate = self.standard = None
        self.source.hide()
        self.fuel_more.hide()
        self._show_share_method()
        self.changed.emit()

    def _show_share_method(self) -> None:
        e = self.share_estimate
        method = e.method if e is not None else "user"
        self.ww_method.set_key(f"ww.method.{method}")
        show = e is not None and e.sea_days is not None and e.mrv_hours is not None and e.days is not None
        self.ww_more.setVisible(show)
        if show:
            c = R.by_key(e.size_class)
            fr = e.fuel_ratio
            self.ww_more.set_key("ww.more", hours=num(e.mrv_hours), cls=f"{c.label} {size_label(c)}",
                                 days=num(e.sea_days), dlo=num(e.days.low), dhi=num(e.days.high),
                                 share=pct(e.share), low=pct(e.low), high=pct(e.high),
                                 ratio=num(fr, 2) if fr else "–")

    # ------------------------------------------------------------------ save / restore
    SPINS = ("gt", "capacity", "distance", "ch4", "n2o", "share1", "eu_share")
    COMBOS = ("category", "ice", "cii_type", "fuel1", "fuel2", "nzf", "baseline")

    def snapshot(self) -> dict:
        d = {k: getattr(self, k).value() for k in self.SPINS}
        d.update({k: getattr(self, k).currentData() for k in self.COMBOS})
        d.update({f"scope_{k}": s.value() for k, s in self.scope.items()})
        d.update({f"eua_{y}": s.value() for y, s in self.prices.items()})
        d["domestic"] = self.domestic.isChecked()
        d["ship"] = {"imo": self.loaded.imo, "year": self.loaded.year} if self.loaded else None
        d["standard"] = list(self.standard) if self.standard else None
        d["em_from_mrv"] = self.loaded_em is not None
        d["share_from_estimate"] = self.share_estimate is not None
        d["size_from_estimate"] = self.size_estimate is not None
        d["scope_override"] = self.scope_override
        d["coverage_ratio"] = self.coverage_ratio
        return d

    def restore(self, d: dict, db=None) -> None:
        """Bring back a saved project's inputs (reloading its ship from EU MRV when available)."""
        if not d:
            return
        ship = d.get("ship")
        if d.get("standard"):
            self.load_standard(tuple(d["standard"]))
        elif ship and db is not None:
            year = next((h for h in db.history(ship["imo"]) if h.year == ship["year"]), None)
            if year is not None:
                self.load_ship(year)
        self._filling = True
        try:
            for k in self.SPINS:
                if k in d:
                    getattr(self, k).setValue(d[k])
            for k in self.COMBOS:
                if k in d:
                    getattr(self, k).select(d[k])
            for k, s in self.scope.items():
                s.setValue(d.get(f"scope_{k}", s.value()))
            for y, s in self.prices.items():
                s.setValue(d.get(f"eua_{y}", s.value()))
            self.domestic.setChecked(bool(d.get("domestic", False)))
        finally:
            self._filling = False
        if not d.get("em_from_mrv"):
            self.loaded_em = None
            self.coverage_ratio = None
            self.ratio_text.hide()
        if not d.get("share_from_estimate"):
            self.share_estimate = None
        if not d.get("size_from_estimate"):
            self.size_estimate = None
        self.scope_override = d.get("scope_override", self.scope_override)
        self._cii_type_changed()
        self._show_share_method()
        self.changed.emit()

    # ------------------------------------------------------------------ language
    def retranslate(self) -> None:
        self.reset_btn.setText(amp(tr("ets.reset")))
        self.domestic.setText(tr("in.domestic"))
        for c in (self.category, self.ice, self.cii_type, self.fuel1, self.fuel2, self.nzf):
            c.retranslate()
        loc = ui_locale()
        self._filling = True
        try:
            for s in self.findChildren(QDoubleSpinBox):
                s.setLocale(loc)
                s.setValue(s.value())
        finally:
            self._filling = False
        for rm in self.findChildren(ReadMore):
            rm.retranslate()
        self._show_share_method()


# =============================================================================== results
class Results(QWidget):
    def __init__(self, rules: Rules):
        super().__init__()
        self.rules = rules
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        kp = Panel()
        self.kpi_panel = kp
        kg = QGridLayout()
        kg.setHorizontalSpacing(24)
        self.k_total = Kpi("kpi.total", a=YEARS[0], b=YEARS[-1])
        self.k_2030 = Kpi("kpi.year", year=2030)
        self.k_2035 = Kpi("kpi.year", year=2035)
        self.k_cii = Kpi("kpi.cii", year=2030)
        for i, k in enumerate((self.k_total, self.k_2030, self.k_2035, self.k_cii)):
            kg.addWidget(k, 0, i)
            kg.setColumnStretch(i, 1)
        kp.body.addLayout(kg)
        self.estimate_note = TrLabel("ww.method.estimated", "Estimate")
        kp.body.addWidget(self.estimate_note)
        self.scope_warn = TrLabel("ets.out_of_scope", "Warning", wrap=True)
        kp.body.addWidget(self.scope_warn)
        v.addWidget(kp)

        self.tabs = QTabWidget()
        self.tab_keys = ["reg.tab.overview", "reg.tab.ets", "reg.tab.fueleu", "reg.tab.nzf", "reg.tab.cii",
                         "reg.tab.params"]
        ov = QWidget()
        ol = QVBoxLayout(ov)
        ol.setContentsMargins(0, 8, 0, 0)
        p = Panel("chart.overview")
        self.ov_chart = StackedBarChart(axis="money")
        p.body.addWidget(self.ov_chart)
        ol.addWidget(p)
        self.ov_table = new_table()
        ol.addWidget(self.ov_table)
        self.reg_charts: dict[str, BarChart] = {}
        self.reg_tables: dict[str, QTableWidget] = {}
        pages = [ov]
        for key in ("ets", "fueleu", "nzf"):
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 8, 0, 0)
            p = Panel(f"chart.{key}")
            self.reg_charts[key] = BarChart()
            p.body.addWidget(self.reg_charts[key])
            wl.addWidget(p)
            self.reg_tables[key] = new_table()
            wl.addWidget(self.reg_tables[key])
            pages.append(w)
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(0, 8, 0, 0)
        self.cii_missing = TrLabel("cii.need_capacity", "Warning", wrap=True)
        cl.addWidget(self.cii_missing)
        self.cii_table = new_table()
        cl.addWidget(self.cii_table)
        cl.addWidget(ReadMore("cii.more"))
        cl.addStretch(1)
        pages.append(cw)
        self.params = ParamsTable()
        pages.append(self.params)
        for w, k in zip(pages, self.tab_keys, strict=True):
            self.tabs.addTab(w, amp(tr(k)))
        v.addWidget(self.tabs, 1)
        self.results: list[YearResult] = []

    def display(self, results: list[YearResult], view: str, share: EuShare | None) -> None:
        self.results = results
        r = {x.year: x for x in results}
        self.k_total.value.setText(eur_short(sum(x.total_eur for x in results)))
        self.k_2030.value.setText(eur_short(r[2030].total_eur))
        self.k_2035.value.setText(eur_short(r[2035].total_eur))
        c = r[2030].cii
        self.k_cii.value.setText(c.rating if c and not math.isnan(c.attained) else "–")
        self.estimate_note.setVisible(view == "ww" and share is not None and share.method == "estimated")
        self.scope_warn.setVisible(not any(x.ets.in_scope for x in results))
        p = theme.current()
        years = [x.year for x in results]
        self.ov_chart.set_data(years, [(tr("legend.ets_cost"), [x.ets.cost for x in results], p.ets),
                                       (tr("legend.fueleu"), [x.fueleu_cost for x in results], p.fueleu),
                                       (tr("legend.nzf"), [max(x.nzf.cost_eur, 0) for x in results], p.imo)])

        def rating(x):
            return x.cii.rating if x.cii and not math.isnan(x.cii.attained) else "–"

        fill_table(self.ov_table, ["col.year", "col.ets", "col.fueleu", "col.nzf", "col.total", "col.cii"],
                   [[str(x.year), num(x.ets.cost), num(x.fueleu_cost), num(x.nzf.cost_eur), num(x.total_eur),
                     rating(x)] for x in results])
        self.reg_charts["ets"].set_data(years, [x.ets.cost for x in results], p.ets)
        fill_table(self.reg_tables["ets"], ["ets.col.year", "ets.col.covered", "ets.col.phase", "ets.col.allowances",
                                            "ets.col.price", "ets.col.cost"],
                   [[str(x.year), num(x.ets.covered), pct(x.ets.phase_in), num(x.ets.allowances), num(x.ets.price, 2),
                     num(x.ets.cost)] for x in results])
        self.reg_charts["fueleu"].set_data(years, [x.fueleu_cost for x in results], p.fueleu)
        fill_table(self.reg_tables["fueleu"], ["col.year", "col.energy", "col.intensity", "col.target", "col.balance",
                                               "col.route", "col.cost"],
                   [[str(x.year), num(x.fueleu.energy_mj / 1000),
                     num(x.fueleu.intensity, 2) if x.fueleu.in_scope else "–", num(x.fueleu.target, 2),
                     num(x.fueleu.balance_t), tr(f"route.{x.route}", share=pct(x.bio_share)),
                     num(x.fueleu_cost)] for x in results])
        self.reg_charts["nzf"].set_data(years, [max(x.nzf.cost_eur, 0) for x in results], p.imo)
        fill_table(self.reg_tables["nzf"], ["col.year", "col.energy", "col.gfi", "col.base", "col.direct", "col.tier2",
                                            "col.tier1", "col.surplus", "col.cost"],
                   [[str(x.year), num(x.nzf.energy_mj / 1000), num(x.nzf.gfi, 2) if x.nzf.applies else "–",
                     num(x.nzf.base, 2) if x.nzf.base else "–", num(x.nzf.direct, 2) if x.nzf.direct else "–",
                     num(x.nzf.tier2_t), num(x.nzf.tier1_t), num(x.nzf.surplus_t),
                     num(x.nzf.cost_eur) if x.nzf.applies else tr("na")] for x in results])
        have = any(x.cii and not math.isnan(x.cii.attained) for x in results)
        self.cii_missing.setVisible(not have)
        self.cii_table.setVisible(have)
        if have:
            rows, colors = [], {}
            rc = {"A": "good", "B": "good", "C": "muted", "D": "warn", "E": "bad"}
            for i, x in enumerate(x for x in results if x.year >= 2023):
                rows.append([str(x.year), num(x.cii.attained, 2), num(x.cii.required, 2), num(x.cii.ratio, 3),
                             x.cii.rating])
                colors[(i, 4)] = theme.c(rc[x.cii.rating])
            fill_table(self.cii_table, ["col.year", "col.attained", "col.required", "col.ratio", "col.rating"],
                       rows, colors)

    def retranslate(self) -> None:
        for i, k in enumerate(self.tab_keys):
            self.tabs.setTabText(i, amp(tr(k)))
        for rm in self.findChildren(ReadMore):
            rm.retranslate()
        self.params.fill()

    def restyle(self) -> None:
        self.ov_chart.restyle()
        for ch in self.reg_charts.values():
            ch.restyle()
        self.params.fill()


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
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(True)
        self.table.setMinimumHeight(560)
        v.addWidget(self.table)
        self.sets = [P.load(n) for n in P.available()]
        self.fill()

    def fill(self) -> None:
        self.table.setHorizontalHeaderLabels([tr(c) for c in self.COLS])
        rows = [(ps, p) for ps in self.sets for p in ps.values.values()]
        self.table.setRowCount(len(rows))
        for i, (ps, p) in enumerate(rows):
            src = ps.source_of(p.key)
            value = p.value if isinstance(p.value, (int, float, str)) else json.dumps(p.value, ensure_ascii=False)
            if len(str(value)) > 90:
                value = str(value)[:88] + "…"
            ok = p.status == P.VERIFIED
            cells = [f"{ps.name}.{p.key}", str(value), src.title, src.checked,
                     tr("params.verified") if ok else tr("params.verify")]
            for j, text in enumerate(cells):
                it = QTableWidgetItem(text)
                tip = "\n".join(x for x in (p.note, src.url, json.dumps(p.value, ensure_ascii=False)[:600]) if x)
                it.setToolTip(tip)
                if j == 4:
                    it.setForeground(theme.c("good" if ok else "warn"))
                self.table.setItem(i, j, it)
        for col, width in ((0, 260), (1, 260), (2, 360), (3, 90)):
            self.table.setColumnWidth(col, width)
