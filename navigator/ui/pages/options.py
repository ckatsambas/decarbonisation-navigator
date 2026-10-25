"""Step 3 · Options: which of the 25 measures fit this ship, what they cost and what they cut.

Every applicable measure is appraised on the ship's own calibrated power model (decision 0009):
emissions cut, investment, net present value, cost per tonne avoided and payback, at the most
likely values; the detail panel shows the ranges, the attributes and the sources. Ticked measures
form the shortlist that Phase 4 ranks with MCDA under uncertainty (SMAA).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...engine import economics as EC
from ...engine import measures as M
from ...engine import power as PW
from ...engine.compliance import Rules
from ...i18n import eur_short, num, pct, pick, tr
from .. import theme
from ..charts import CashFlowChart
from ..widgets import Panel, ReadMore, TrLabel, label
from .base import Page
from .position import Choice

START_YEARS = ("2026", "2027", "2028", "2030")
LIVES = ("10", "15", "20", "25")
RATES = {"0.06": "6%", "0.08": "8%", "0.10": "10%"}
COLS = ("", "col.measure", "col.cut", "col.invest", "col.npv", "col.mac")


class Row:
    """Results for one measure on the current ship."""

    def __init__(self, m: M.Measure, ok: bool, why: str):
        self.m, self.ok, self.why = m, ok, why
        self.app: EC.Appraisal | None = None
        self.cut = (0.0, 0.0, 0.0)          # well-to-wake emissions cut: low, likely, high (share)
        self.energy = 0.0


class StepOptions(Page):
    title_key = "step.3.q"
    lede_key = "step.3.lede"
    title_style = ("Question", "QuestionLede")

    changed = Signal()

    def __init__(self, state, position):
        super().__init__(state)
        self.position = position
        self.rules: Rules = position.rules
        self.lib = M.load()
        self.rows: list[Row] = []
        self.shortlist: set[str] = set()
        self._filling = False

        sc = QGridLayout()
        sc.setHorizontalSpacing(28)
        sc.setVerticalSpacing(6)
        for i, k in enumerate(("opt.start", "opt.life", "opt.prices", "opt.rate")):
            sc.addWidget(TrLabel(k, "SectionTitle"), 0, i)
        self.start = Choice([(y, f"year.{y}") for y in START_YEARS])
        self.life = Choice([(y, f"opt.life.{y}") for y in LIVES])
        self.prices = Choice([(p, f"pos.price.{p}") for p in EC.PRICE_PATHS])
        self.rate = Choice([(r, f"rate.{r}") for r in RATES])
        for i, w in enumerate((self.start, self.life, self.prices, self.rate)):
            sc.addWidget(w, 1, i, Qt.AlignmentFlag.AlignLeft)
        sc.addWidget(ReadMore("opt.start.more"), 2, 0)
        sc.addWidget(ReadMore("opt.life.more"), 2, 1)
        sc.addWidget(ReadMore("opt.prices.more"), 2, 2)
        sc.addWidget(ReadMore("opt.rate.more"), 2, 3)
        sc.setColumnStretch(4, 1)
        self.lay.addLayout(sc)
        self.start.set_value("2027")
        self.life.set_value("20")
        self.prices.set_value("central")
        self.rate.set_value("0.08")

        self.sentence = label("", "Sentence", wrap=True)
        self.lay.addWidget(self.sentence)

        row = QHBoxLayout()
        row.setSpacing(16)
        tp = Panel("opt.table")
        self.table = QTableWidget(0, len(COLS))
        self.table.setObjectName("Ledger")
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(560)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setMinimumSectionSize(28)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 130)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        tp.body.addWidget(self.table)
        self.shortlist_label = label("", "Muted", wrap=True)
        self.clash_label = label("", "Warn", wrap=True)
        tp.body.addWidget(self.shortlist_label)
        tp.body.addWidget(self.clash_label)
        row.addWidget(tp, 3)

        self.detail = Panel()
        dv = self.detail.body
        self.d_title = label("", "DetailTitle", wrap=True)
        self.d_group = label("", "Faint")
        self.d_how = label("", "Muted", wrap=True)
        self.d_badge = TrLabel("opt.d.verify", "Estimate", wrap=True)
        dv.addWidget(self.d_group)
        dv.addWidget(self.d_title)
        dv.addWidget(self.d_how)
        dv.addWidget(self.d_badge)
        self.facts = QGridLayout()
        self.facts.setHorizontalSpacing(14)
        self.facts.setVerticalSpacing(4)
        self.fact_keys = ("opt.d.cut", "opt.d.energy", "opt.d.invest", "opt.d.opex", "opt.d.life", "opt.d.offhire",
                          "opt.d.npv", "opt.d.mac", "opt.d.payback", "opt.d.trl", "opt.d.avail", "opt.d.safety",
                          "opt.d.cargo")
        self.fact_values: dict[str, object] = {}
        for i, k in enumerate(self.fact_keys):
            self.facts.addWidget(TrLabel(k, "Faint"), i, 0)
            v = label("–", "FactValue", wrap=True)
            self.facts.addWidget(v, i, 1)
            self.fact_values[k] = v
        self.facts.setColumnStretch(1, 1)
        dv.addLayout(self.facts)
        dv.addWidget(TrLabel("chart.cashflow", "SectionTitle"))
        self.chart = CashFlowChart()
        dv.addWidget(self.chart)
        self.d_note = ReadMore("opt.d.note", text="")
        dv.addWidget(self.d_note)
        self.d_sources = label("", "Faint", wrap=True)
        self.d_sources.setOpenExternalLinks(True)
        self.d_sources.setTextFormat(Qt.TextFormat.RichText)
        dv.addWidget(self.d_sources)
        dv.addStretch(1)
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.addWidget(self.detail)
        row.addWidget(holder, 2)
        self.lay.addLayout(row)
        self.lay.addStretch(1)

        for c in (self.start, self.life, self.prices, self.rate):
            c.picked.connect(lambda v, c=c: (c.set_value(v), self.recompute()))
        self.table.itemChanged.connect(self._ticked)
        self.table.currentCellChanged.connect(lambda r, *_: self._show(r))
        position.computed.connect(self.recompute)
        self.table.setHorizontalHeaderLabels([tr(k) if k else "" for k in COLS])
        self.recompute()

    # ------------------------------------------------------------------ settings
    def _value(self, choice: Choice, default: str) -> str:
        return next((v for v, b in choice.buttons.items() if b.isChecked()), default)

    def settings(self) -> dict:
        return {"start": int(self._value(self.start, "2027")), "life": int(self._value(self.life, "20")),
                "prices": self._value(self.prices, "central"), "rate": float(self._value(self.rate, "0.08"))}

    def snapshot(self) -> dict:
        return {**self.settings(), "shortlist": sorted(self.shortlist)}

    def restore(self, d: dict | None) -> None:
        d = d or {}
        self.start.set_value(str(d.get("start", 2027)))
        self.life.set_value(str(d.get("life", 20)))
        self.prices.set_value(d.get("prices", "central"))
        self.rate.set_value(f"{d.get('rate', 0.08):.2f}")
        self.shortlist = {k for k in d.get("shortlist", []) if k in self.lib.measures}
        self.recompute()

    # ------------------------------------------------------------------ compute
    def recompute(self) -> None:
        pos = self.position
        prof = pos.inputs.profile()
        try:
            model = M.model_for(prof, self.rules.fuels)
        except (ValueError, KeyError, ZeroDivisionError):
            self.rows = []
            self._fill()
            return
        self.model = model
        st = self.settings()
        sc = pos.inputs.scenario(pos.view)
        imo_type = model.cls.type
        base_wtw = EC._wtw_t(model.base.fuel_t, self.rules.fuels, self.rules.fueleu.gwp) or 1.0
        rows = []
        for m in self.lib:
            ok, why = m.applies_to(imo_type, model.power.mcr_kw, model.cls)
            r = Row(m, ok, why)
            if ok:
                r.app = EC.appraise(model, [m], sc, st["start"], 0.5, st["prices"], st["rate"],
                                    end=st["start"] + st["life"] - 1, rules=self.rules)
                cuts = []
                for q in (0.0, 0.5, 1.0):
                    res = PW.run(model.power, m.effects(model.power, model.cls, q), fuels=self.rules.fuels)
                    wtw = EC._wtw_t(res.fuel_t, self.rules.fuels, self.rules.fueleu.gwp) - res.co2_captured_t
                    cuts.append(1 - wtw / base_wtw)
                    if q == 0.5:
                        r.energy = 1 - res.total_mj / model.base.total_mj
                r.cut = tuple(sorted(cuts))
            rows.append(r)
        rows.sort(key=lambda r: (not r.ok, -(r.app.npv if r.app else 0)))
        self.rows = rows
        self._fill()
        self._summary()
        self.changed.emit()

    def _fill(self) -> None:
        self._filling = True
        cur = self.table.currentRow()
        key = self.rows[cur].m.key if 0 <= cur < len(self.rows) else None
        self.table.clearSpans()
        self.table.setRowCount(len(self.rows))
        p = theme.current()
        for i, r in enumerate(self.rows):
            tick = QTableWidgetItem()
            if r.ok:
                tick.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                tick.setCheckState(Qt.CheckState.Checked if r.m.key in self.shortlist else Qt.CheckState.Unchecked)
            else:
                tick.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(i, 0, tick)
            name = QTableWidgetItem(pick(r.m.name))
            name.setToolTip(tr(f"group.{r.m.group}"))
            self.table.setItem(i, 1, name)
            if r.ok and r.app:
                a = r.app
                cells = [pct(r.cut[1], 1), eur_short(a.capex_eur), eur_short(a.npv),
                         num(a.cost_per_t) if a.cost_per_t is not None else "–"]
            else:
                cells = [tr(f"opt.na.{r.why}"), "", "", ""]
            for j, text in enumerate(cells, start=2):
                it = QTableWidgetItem(text)
                if j == 2 and r.ok:
                    it.setToolTip(f"{pct(r.cut[0], 1)} – {pct(r.cut[2], 1)}")
                if j >= 3:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if j == 4 and r.ok and r.app:
                    it.setForeground(QColor(p.good if r.app.npv >= 0 else p.bad))
                self.table.setItem(i, j, it)
            if not r.ok:
                self.table.setSpan(i, 2, 1, len(COLS) - 2)
                for j in range(len(COLS)):
                    it = self.table.item(i, j)
                    if it is not None:
                        it.setForeground(QColor(p.faint))
        self._filling = False
        row = next((i for i, r in enumerate(self.rows) if r.m.key == key), 0)
        if self.rows:
            self.table.setCurrentCell(row, 1)
            self._show(row)

    def _ticked(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != 0:
            return
        r = self.rows[item.row()]
        if item.checkState() == Qt.CheckState.Checked:
            self.shortlist.add(r.m.key)
        else:
            self.shortlist.discard(r.m.key)
        self._summary()
        self.changed.emit()

    def _summary(self) -> None:
        ok = [r for r in self.rows if r.ok and r.app]
        main = [r for r in self.lib if not r.note.startswith("Variant")]
        paying = [r for r in ok if r.app.npv > 0]
        cheapest = min((r for r in ok if r.app.cost_per_t is not None and r.cut[1] > 0.005),
                       key=lambda r: r.app.cost_per_t, default=None)
        biggest = max(ok, key=lambda r: r.cut[1], default=None)
        ship = self.position_ship_name()
        if ok:
            self.sentence.setText(tr("opt.sentence", n=len([r for r in ok if not r.m.note.startswith("Variant")]),
                                     total=len(main), ship=ship, paying=len(paying),
                                     cheap=pick(cheapest.m.name) if cheapest else "–",
                                     big=pick(biggest.m.name) if biggest else "–",
                                     cut=pct(biggest.cut[1]) if biggest else "–"))
        else:
            self.sentence.setText(tr("opt.no_model"))
        self.shortlist_label.setText(tr("opt.shortlist", n=len(self.shortlist)))
        clashes = self.lib.clashes(sorted(self.shortlist))
        self.clash_label.setVisible(bool(clashes))
        if clashes:
            a, b = clashes[0]
            self.clash_label.setText(tr("opt.clash", a=pick(self.lib[a].name), b=pick(self.lib[b].name)))

    def position_ship_name(self) -> str:
        inputs = self.position.inputs
        if inputs.loaded is not None:
            return inputs.loaded.get("name", "")
        if inputs.standard:
            from ...engine import reference as R
            return R.by_key(inputs.standard[0]).label
        return tr("pos.example_ship")

    def _show(self, i: int) -> None:
        if not 0 <= i < len(self.rows):
            return
        r = self.rows[i]
        m = r.m
        self.d_group.setText(theme.upper(tr(f"group.{m.group}")))
        self.d_title.setText(pick(m.name))
        self.d_how.setText(pick(m.how))
        self.d_badge.setVisible(m.status != "verified")
        fv = self.fact_values
        usd = self.rules.nzf.eur_per_usd
        if r.ok and r.app:
            a = r.app
            sp, cls = self.model.power, self.model.cls
            fv["opt.d.cut"].setText(f"{pct(r.cut[1], 1)}  ({pct(r.cut[0], 1)} – {pct(r.cut[2], 1)})")
            fv["opt.d.energy"].setText(pct(r.energy, 1))
            fv["opt.d.invest"].setText(f"{eur_short(a.capex_eur)}  ({eur_short(m.capex_usd(sp, cls, 0.0) * usd)} – "
                                       f"{eur_short(m.capex_usd(sp, cls, 1.0) * usd)})")
            fv["opt.d.opex"].setText(eur_short(m.opex_usd(sp, cls) * usd))
            fv["opt.d.npv"].setText(eur_short(a.npv))
            fv["opt.d.mac"].setText(tr("opt.d.mac.value", v=num(a.cost_per_t)) if a.cost_per_t is not None else "–")
            fv["opt.d.payback"].setText(str(a.payback_year) if a.payback_year else tr("opt.never"))
            self.chart.set_data([f.year for f in a.flows], [f.net for f in a.flows],
                                (tr("legend.cash"), tr("legend.cum")))
        else:
            for k in ("opt.d.cut", "opt.d.energy", "opt.d.invest", "opt.d.opex", "opt.d.npv", "opt.d.mac", "opt.d.payback"):
                fv[k].setText("–")
            fv["opt.d.cut"].setText(tr(f"opt.na.{r.why}"))
            self.chart.set_data([], [], ("", ""))
        lt = m.lifetime
        fv["opt.d.life"].setText(tr("opt.years", n=num(lt.likely)))
        fv["opt.d.offhire"].setText(tr("opt.days", n=num(m.offhire_days.likely)))
        at = m.attributes
        fv["opt.d.trl"].setText(str(at.get("trl", "–")))
        fv["opt.d.avail"].setText(tr("opt.score", n=at.get("availability", "–")))
        fv["opt.d.safety"].setText(tr("opt.score", n=at.get("safety", "–")))
        fv["opt.d.cargo"].setText(pct(at.get("cargo_loss", 0.0), 1))
        self.d_note.set_key("opt.d.note", text=m.note or tr("opt.d.no_note"))
        links = []
        for ref in m.refs:
            s = self.lib.sources.get(ref)
            if s is None:
                continue
            t = s.title.split(":")[0]
            links.append(f'<a href="{s.url}">{t}</a>' if s.url else t)
        self.d_sources.setText(tr("opt.d.sources") + " " + " · ".join(links))

    # ------------------------------------------------------------------ language / theme
    def on_language(self) -> None:
        for c in (self.start, self.life, self.prices, self.rate):
            c.retranslate()
        self.table.setHorizontalHeaderLabels([tr(k) if k else "" for k in COLS])
        self._fill()
        self._summary()

    def on_theme(self) -> None:
        self.chart.restyle()
        self._fill()
