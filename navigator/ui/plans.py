"""Investment plans in step 3 (decision 0014): the optimiser's Pareto front, the chosen plan's timeline,
and the two-stage adaptive plan. Chosen plans join the shortlist as alternatives for steps 4–5."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..engine import optimise as O
from ..engine.plan import Plan
from ..i18n import eur_short, language, num, pick, tr
from . import theme
from .charts import AnimatedChart, Morph, money_tick, nice_range, with_alpha
from .maps import FAMILY_COLORS, RED, mix
from .widgets import Panel, ReadMore, TrLabel, amp, label

LETTERS = {"el": "ΑΒΓΔΕΖΗΘΙΚ", "en": "ABCDEFGHIJ"}
GROUP_COLOR = {"operation": FAMILY_COLORS["operations"], "hull": "#4FA88A", "propulsion": "#5BB0C9",
               "machinery": "#8E7CC3", "wind": "#7A9E4F", "fuel": "#D9A441", "capture": "#C77DA0"}


def letter(i: int) -> str:
    s = LETTERS.get(language(), LETTERS["en"])
    return s[i] if i < len(s) else str(i + 1)


# ------------------------------------------------------------------ charts
class ParetoChart(AnimatedChart):
    """Exact NPV against tonnes avoided for every plan on the front; click a point to choose it."""

    picked = Signal(int)

    def __init__(self):
        super().__init__(320)
        self.labels: list[str] = []
        self._pts = Morph()
        self.sel = 0
        self._sx = self._sy = None

    def set_data(self, cuts, npvs, labels, sel: int = 0) -> None:
        pts = np.array([cuts, npvs], float).T
        if self._pts.new is None or self._pts.new.shape != pts.shape:
            self._pts.new = None
        self._pts.set(pts, self._t)
        self.labels, self.sel = list(labels), sel
        x_lo, x_hi, self.xt = nice_range(0, float(pts[:, 0].max(initial=1)) * 1.08)
        y_lo, y_hi, self.yt = nice_range(float(pts[:, 1].min(initial=0)), float(pts[:, 1].max(initial=1)))
        self.bounds = (x_lo, x_hi, y_lo, y_hi)
        self._start()

    def select(self, i: int) -> None:
        self.sel = i
        self.update()

    def _rect(self) -> QRectF:
        return QRectF(64, 16, self.width() - 84, self.height() - 52)

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        pts = self._pts.at(self._t)
        if pts is None or not len(pts):
            return
        g = self.painter()
        p = theme.current()
        r = self._rect()
        x_lo, x_hi, y_lo, y_hi = self.bounds

        def sx(v):
            return r.left() + (v - x_lo) / (x_hi - x_lo or 1) * r.width()

        def sy(v):
            return r.bottom() - (v - y_lo) / (y_hi - y_lo or 1) * r.height()

        self._sx, self._sy = sx, sy
        g.setFont(theme.ui_font(8))
        top = max(abs(y_lo), abs(y_hi))
        for v in self.yt:
            g.setPen(QPen(theme.c("grid"), 1))
            g.drawLine(QPointF(r.left(), sy(v)), QPointF(r.right(), sy(v)))
            g.setPen(theme.c("faint"))
            g.drawText(QRectF(0, sy(v) - 8, r.left() - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       money_tick(v, top))
        for v in self.xt:
            g.setPen(theme.c("faint"))
            g.drawText(QRectF(sx(v) - 30, r.bottom() + 4, 60, 14), Qt.AlignmentFlag.AlignCenter, f"{num(v / 1e3)}k")
        g.drawText(QRectF(r.left(), r.bottom() + 20, r.width(), 16), Qt.AlignmentFlag.AlignCenter, tr("plan.axis.cut"))
        if y_lo < 0 < y_hi:
            g.setPen(QPen(theme.c("muted"), 1, Qt.PenStyle.DashLine))
            g.drawLine(QPointF(r.left(), sy(0)), QPointF(r.right(), sy(0)))
        # the frontier as a smooth line through the plans, with a soft area under it
        order = np.argsort(pts[:, 0])
        path = QPainterPath(QPointF(sx(pts[order[0], 0]), sy(pts[order[0], 1])))
        for k in order[1:]:
            path.lineTo(QPointF(sx(pts[k, 0]), sy(pts[k, 1])))
        g.setPen(QPen(with_alpha(p.accent, 0.8), 2.0))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawPath(path)
        for i, (x, y) in enumerate(pts):
            c = QPointF(sx(x), sy(y))
            chosen = i == self.sel
            g.setPen(QPen(QColor("#FFFFFF"), 2))
            g.setBrush(QColor(RED) if chosen else theme.c("accent"))
            rad = 9 if chosen else 6.5
            g.drawEllipse(c, rad, rad)
            g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold))
            g.setPen(QColor(RED) if chosen else theme.c("text"))
            g.drawText(QRectF(c.x() - 40, c.y() - 30, 80, 16), Qt.AlignmentFlag.AlignCenter, self.labels[i])
        g.end()

    def _hit(self, pos) -> int | None:
        pts = self._pts.new
        if pts is None or self._sx is None:
            return None
        best, dist = None, 18.0
        for i, (x, y) in enumerate(pts):
            d = math.hypot(self._sx(x) - pos.x(), self._sy(y) - pos.y())
            if d < dist:
                best, dist = i, d
        return best

    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt API
        i = self._hit(e.position())
        if i is not None:
            self.select(i)
            self.picked.emit(i)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        i = self._hit(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if i is not None else Qt.CursorShape.ArrowCursor)
        if i is not None:
            x, y = self._pts.new[i]
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"<b>{tr('plan.name', l=self.labels[i])}</b><br>{tr('col.npv')}: {eur_short(y)}"
                              f"<br>{tr('plan.avoided', t=num(x / 1e3))}", self)


class PlanTimeline(AnimatedChart):
    """One row per measure: the installation year (diamond) and the years it works (bar)."""

    ROW = 26

    def __init__(self):
        super().__init__(120)
        self.rows: list[tuple[str, int, str]] = []
        self.years = (2027, 2046)
        self.window = (2027, 2035)

    def set_data(self, rows, years, window) -> None:
        self.rows, self.years, self.window = list(rows), years, window
        self.setMinimumHeight(30 + self.ROW * max(len(self.rows), 1))
        self._start()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.rows:
            return
        g = self.painter()
        p = theme.current()
        g.setFont(theme.ui_font(8.8))
        fm = QFontMetricsF(g.font())
        left = min(max(fm.horizontalAdvance(n) for n, _y, _c in self.rows) + 16, self.width() * 0.42)
        y0, y1 = self.years
        span = max(y1 - y0 + 1, 1)
        r = QRectF(left, 20, self.width() - left - 10, self.ROW * len(self.rows))

        def x(y):
            return r.left() + (y - y0) / span * r.width()

        w0, w1 = self.window
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(with_alpha(p.accent, 0.06))
        g.drawRect(QRectF(x(w0), r.top() - 4, x(w1 + 1) - x(w0), r.height() + 8))
        g.setFont(theme.ui_font(7.8))
        for yy in range(y0, y1 + 1):
            if yy in (y0, y1) or (yy % 5 == 0 and y1 - yy >= 3 and yy - y0 >= 3):
                g.setPen(theme.c("faint"))
                g.drawText(QRectF(x(yy) - 20, 2, 40 + r.width() / span, 14), Qt.AlignmentFlag.AlignLeft, str(yy))
                g.setPen(QPen(theme.c("grid"), 1))
                g.drawLine(QPointF(x(yy), r.top() - 2), QPointF(x(yy), r.bottom()))
        for i, (name, year, color) in enumerate(self.rows):
            yy = r.top() + i * self.ROW
            g.setFont(theme.ui_font(8.8))
            g.setPen(theme.c("text"))
            g.drawText(QRectF(0, yy, left - 10, self.ROW), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(name, Qt.TextElideMode.ElideRight, left - 12))
            grow = min(max(self._t * 1.3 - i * 0.04, 0), 1)
            bar_end = x(year) + (x(y1 + 1) - x(year)) * grow
            col = QColor(color)
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(with_alpha(col, 0.35))
            g.drawRoundedRect(QRectF(x(year), yy + 9, bar_end - x(year), self.ROW - 18), 3, 3)
            c = QPointF(x(year) + 1, yy + self.ROW / 2)
            g.setBrush(col)
            g.setPen(QPen(theme.c("panel"), 1.5))
            d = 6.5
            g.drawPolygon([QPointF(c.x(), c.y() - d), QPointF(c.x() + d, c.y()), QPointF(c.x(), c.y() + d),
                           QPointF(c.x() - d, c.y())])
            g.setPen(theme.c("muted"))
            g.setFont(theme.ui_font(8))
            g.drawText(QRectF(c.x() + 10, yy, 60, self.ROW), Qt.AlignmentFlag.AlignVCenter, str(year))
        g.end()


class FuturesGrid(QWidget):
    """3 × 3: fuel and carbon market (rows) × IMO NZF outcome (columns); what is added later and NPV."""

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)

    def set_data(self, ad: O.Adaptive, name_of) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        markets = ["low", "central", "high"]
        outcomes = sorted({b.nzf for b in ad.branches}, key=lambda z: ["as_drafted", "delayed", "not_adopted"].index(z))
        for j, z in enumerate(outcomes, start=1):
            self.grid.addWidget(label(tr(f"nzf.short.{z}"), "Faint"), 0, j, Qt.AlignmentFlag.AlignCenter)
        npvs = [b.npv for b in ad.branches]
        lo, hi = min(npvs), max(npvs)
        p = theme.current()
        for i, mk in enumerate(markets, start=1):
            self.grid.addWidget(label(tr(f"plan.market.{mk}"), "Faint"), i, 0, Qt.AlignmentFlag.AlignRight)
            for j, z in enumerate(outcomes, start=1):
                b = next((b for b in ad.branches if b.market == mk and b.nzf == z), None)
                if b is None:
                    continue
                later = [(k, y) for k, y in b.plan.installs if y > ad.decide_after]
                steps = "<br>".join(f"{y} · {name_of(k)}" for k, y in later) or tr("plan.nothing_more")
                t = (b.npv - lo) / (hi - lo) if hi > lo else 0.5
                bg = mix(p.panel_alt, p.accent, 0.08 + 0.25 * t).name()
                cell = label(f"<b>{eur_short(b.npv)}</b> <span style='color:{p.faint}'>· {num(b.prob * 100)}%</span>"
                             f"<br><span style='font-size:8.5pt'>{steps}</span>", None, wrap=True)
                cell.setTextFormat(Qt.TextFormat.RichText)
                cell.setStyleSheet(f"background:{bg}; border-radius:6px; padding:8px;")
                cell.setToolTip(tr("plan.fixed_here", v=eur_short(b.rigid_npv)))
                self.grid.addWidget(cell, i, j)
        for j in range(1, len(outcomes) + 1):
            self.grid.setColumnStretch(j, 1)


# ------------------------------------------------------------------ worker
class Job(QObject):
    progress = Signal(float)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception as e:  # noqa: BLE001 - shown to the user
            self.failed.emit(str(e))


# ------------------------------------------------------------------ panel
class PlansPanel(Panel):
    """Optimiser controls and results. `options` is the step-3 page (ship model, settings, shortlist)."""

    changed = Signal()
    CANDIDATES = ("all", "shortlist")
    WINDOWS = ("5", "9")
    BUDGETS = ("none", "1", "3", "10")

    def __init__(self, options):
        super().__init__("plan.title")
        from .pages.position import Choice
        self.options = options
        self.front: O.Front | None = None
        self.adaptive_result: O.Adaptive | None = None
        self.chosen: dict[str, Plan] = {}           # plans added to the shortlist: key → plan
        self.labels: dict[str, str] = {}
        self.sel = 0
        self._thread: QThread | None = None
        self.body.addWidget(TrLabel("plan.lede", "Muted", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        for i, k in enumerate(("plan.candidates", "plan.window", "plan.budget")):
            grid.addWidget(TrLabel(k, "SectionTitle"), 0, i)
        self.cand = Choice([(k, f"plan.candidates.{k}") for k in self.CANDIDATES])
        self.window = Choice([(k, f"plan.window.{k}") for k in self.WINDOWS])
        self.budget = Choice([(k, f"plan.budget.{k}") for k in self.BUDGETS])
        self.cand.set_value("all")
        self.window.set_value("9")
        self.budget.set_value("none")
        for i, w in enumerate((self.cand, self.window, self.budget)):
            grid.addWidget(w, 1, i, Qt.AlignmentFlag.AlignLeft)
            w.picked.connect(lambda v, w=w: (w.set_value(v), self._stale()))
        grid.setColumnStretch(3, 1)
        self.body.addLayout(grid)
        h = QHBoxLayout()
        self.run_btn = QPushButton()
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run)
        h.addWidget(self.run_btn)
        self.status = label("", "Muted", wrap=True)
        h.addWidget(self.status, 1)
        self.body.addLayout(h)
        self.busy = QProgressBar()
        self.busy.setRange(0, 100)
        self.busy.setTextVisible(False)
        self.busy.setFixedHeight(6)
        self.busy.hide()
        self.body.addWidget(self.busy)

        self.results = QWidget()
        rv = QVBoxLayout(self.results)
        rv.setContentsMargins(0, 0, 0, 0)
        self.sentence = label("", "Sentence", wrap=True)
        rv.addWidget(self.sentence)
        row = QHBoxLayout()
        row.setSpacing(18)
        left = QVBoxLayout()
        left.addWidget(TrLabel("plan.front", "SectionTitle"))
        self.chart = ParetoChart()
        self.chart.picked.connect(self.pick)
        left.addWidget(self.chart)
        row.addLayout(left, 3)
        right = QVBoxLayout()
        self.p_title = label("", "DetailTitle", wrap=True)
        right.addWidget(self.p_title)
        self.p_facts = label("", "Muted", wrap=True)
        self.p_facts.setTextFormat(Qt.TextFormat.RichText)
        right.addWidget(self.p_facts)
        self.timeline = PlanTimeline()
        right.addWidget(self.timeline)
        bh = QHBoxLayout()
        self.add_btn = QPushButton()
        self.add_btn.setCheckable(True)
        self.add_btn.setObjectName("Choice")
        self.add_btn.toggled.connect(self.toggle_chosen)
        bh.addWidget(self.add_btn)
        bh.addStretch(1)
        right.addLayout(bh)
        right.addStretch(1)
        row.addLayout(right, 2)
        rv.addLayout(row)
        rv.addWidget(ReadMore("plan.more"))

        # two-stage plan
        rv.addWidget(TrLabel("plan.adaptive", "SectionTitle"))
        ah = QHBoxLayout()
        self.ad_btn = QPushButton()
        self.ad_btn.setObjectName("Choice")
        self.ad_btn.clicked.connect(self.run_adaptive)
        ah.addWidget(self.ad_btn)
        self.ad_status = label("", "Muted", wrap=True)
        ah.addWidget(self.ad_status, 1)
        rv.addLayout(ah)
        self.ad_box = QWidget()
        av = QVBoxLayout(self.ad_box)
        av.setContentsMargins(0, 0, 0, 0)
        self.ad_sentence = label("", "Sentence", wrap=True)
        av.addWidget(self.ad_sentence)
        self.ad_now = label("", "Muted", wrap=True)
        self.ad_now.setTextFormat(Qt.TextFormat.RichText)
        av.addWidget(self.ad_now)
        self.futures = FuturesGrid()
        av.addWidget(self.futures)
        av.addWidget(ReadMore("plan.adaptive.more"))
        self.ad_box.hide()
        rv.addWidget(self.ad_box)
        self.results.hide()
        self.body.addWidget(self.results)
        self.retranslate_buttons()
        self._stale()

    # ------------------------------------------------------------------
    def _value(self, choice, default: str) -> str:
        return next((v for v, b in choice.buttons.items() if b.isChecked()), default)

    def name_of(self, key: str) -> str:
        return pick(self.options.lib[key].name)

    def settings(self) -> O.Settings:
        st = self.options.settings()
        b = self._value(self.budget, "none")
        return O.Settings(start=st["start"], window=int(self._value(self.window, "9")), price_path=st["prices"],
                          discount=st["rate"], budget_eur=None if b == "none" else float(b) * 1e6,
                          end=min(st["start"] + st["life"] - 1, 2050))

    def candidates(self) -> list[str]:
        ok = [r.m.key for r in self.options.rows if r.ok]
        if self._value(self.cand, "all") == "shortlist":
            return [k for k in ok if k in self.options.shortlist]
        return ok

    def _stale(self) -> None:
        self.status.setText(tr("plan.ready") if self.front is None else tr("plan.stale"))

    def _start(self, fn, done) -> bool:
        if self._thread is not None or not getattr(self.options, "model", None):
            return False
        self.busy.setValue(0)
        self.busy.show()
        self.run_btn.setEnabled(False)
        self.ad_btn.setEnabled(False)
        self._thread = QThread(self)
        self._job = Job(fn)
        self._job.moveToThread(self._thread)
        self._thread.started.connect(self._job.run)
        # bound methods of this widget, so Qt queues the calls into the interface thread (a lambda would
        # run in the worker thread and touch widgets from there: the crash of 26 Oct)
        self._done = done
        self._job.progress.connect(self._on_progress)
        self._job.done.connect(self._on_done)
        self._job.failed.connect(self._on_failed)
        self._thread.start()
        return True

    def _on_progress(self, x: float) -> None:
        self.busy.setValue(int(100 * x))

    def _on_done(self, res) -> None:
        self._cleanup()
        self._done(res)

    def _on_failed(self, msg: str) -> None:
        self._cleanup()
        self.status.setText(tr("plan.failed", msg=msg))

    def _cleanup(self) -> None:
        self.busy.hide()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self.run_btn.setEnabled(True)
        self.ad_btn.setEnabled(True)

    def run(self) -> None:
        keys = self.candidates()
        if len(keys) < 1:
            self.status.setText(tr("plan.need"))
            return
        opt = self.options
        st, sc, model = self.settings(), opt.scenario(), opt.model
        lib = {m.key: m for m in opt.lib}
        rules = opt.rules
        self.status.setText(tr("plan.running", n=len(keys)))
        self._start(lambda prog: O.pareto(model, lib, keys, sc, st, rules, progress=prog), self.show_front)

    def run_adaptive(self) -> None:
        if self.front is None or not self.front.plans:
            return
        opt = self.options
        st, sc, model = self.settings(), opt.scenario(), opt.model
        lib = {m.key: m for m in opt.lib}
        keys = sorted({k for r in self.front.plans for k in r.plan.keys})
        target = self.front.plans[self.sel].avoided * 0.999 if self.sel else None
        self.ad_status.setText(tr("plan.adaptive.running"))
        self._start(lambda prog: O.adaptive(model, lib, keys, sc, st, opt.rules, min_expected_cut=target,
                                            progress=prog), self.show_adaptive)

    # ------------------------------------------------------------------
    def show_front(self, fr: O.Front) -> None:
        self.front = fr
        self.status.setText(tr("plan.done", n=len(fr.plans)))
        if not fr.plans:
            self.results.hide()
            return
        self.results.show()
        self.ad_box.hide()
        self.ad_status.setText("")
        best = max(range(len(fr.plans)), key=lambda i: fr.plans[i].npv)
        self.sel = best
        self.chart.set_data([r.avoided for r in fr.plans], [r.npv for r in fr.plans],
                            [letter(i) for i in range(len(fr.plans))], best)
        first, last = fr.plans[0], fr.plans[-1]
        self.sentence.setText(tr("plan.sentence", n=len(fr.plans), a=letter(best), npv=eur_short(fr.plans[best].npv),
                                 k=len(fr.plans[best].plan.keys), deep=letter(len(fr.plans) - 1),
                                 cut=num(last.avoided / 1e3), cost=eur_short(first.npv - last.npv)))
        self.pick(best)

    def pick(self, i: int) -> None:
        if self.front is None or not (0 <= i < len(self.front.plans)):
            return
        self.sel = i
        self.chart.select(i)
        r = self.front.plans[i]
        a = r.appraisal
        self.p_title.setText(tr("plan.name", l=letter(i)))
        self.p_facts.setText(tr("plan.facts", npv=eur_short(a.npv), t_cut=num(r.avoided / 1e3),
                                capex=eur_short(a.capex_eur), payback=str(a.payback_year or "–"),
                                mac=num(a.cost_per_t) if a.cost_per_t is not None else "–"))
        st = self.settings()
        rows = [(self.name_of(k), y, GROUP_COLOR.get(self.options.lib[k].group, "#888888")) for k, y in r.plan.installs]
        self.timeline.set_data(rows, (st.start, st.end or st.start + 19), (st.start, st.start + st.window - 1))
        self.add_btn.blockSignals(True)
        self.add_btn.setChecked(r.plan in self.chosen.values())
        self.add_btn.blockSignals(False)
        self.retranslate_buttons()

    def toggle_chosen(self, on: bool) -> None:
        if self.front is None:
            return
        r = self.front.plans[self.sel]
        key = "plan:" + ",".join(f"{k}@{y}" for k, y in r.plan.installs)
        if on:
            self.chosen[key] = r.plan
            self.labels[key] = tr("plan.name", l=letter(self.sel))
        else:
            self.chosen.pop(key, None)
            self.labels.pop(key, None)
        self.retranslate_buttons()
        self.changed.emit()

    def show_adaptive(self, ad: O.Adaptive) -> None:
        self.adaptive_result = ad
        self.ad_status.setText("")
        self.ad_box.show()
        now = ", ".join(self.name_of(k) for k in ad.now.keys) or tr("plan.nothing_now")
        self.ad_sentence.setText(tr("plan.adaptive.sentence", y=ad.decide_after, e=eur_short(ad.expected_npv),
                                    flex=eur_short(ad.value_of_flexibility), rigid=eur_short(ad.expected_rigid)))
        self.ad_now.setText(f"<b>{tr('plan.now', y=ad.decide_after)}</b> {now}")
        self.futures.set_data(ad, self.name_of)

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {"candidates": self._value(self.cand, "all"), "window": self._value(self.window, "9"),
                "budget": self._value(self.budget, "none"),
                "chosen": {k: {"label": self.labels.get(k, ""), "installs": [list(p) for p in pl.installs]}
                           for k, pl in self.chosen.items()}}

    def restore(self, d: dict | None) -> None:
        d = d or {}
        self.cand.set_value(d.get("candidates", "all"))
        self.window.set_value(d.get("window", "9"))
        self.budget.set_value(d.get("budget", "none"))
        self.chosen, self.labels = {}, {}
        for k, v in d.get("chosen", {}).items():
            pl = Plan.of((a, int(b)) for a, b in v.get("installs", []) if a in self.options.lib.measures)
            if pl:
                self.chosen[k] = pl
                self.labels[k] = v.get("label", "")
        self.front = None
        self.results.hide()
        self._stale()

    def retranslate_buttons(self) -> None:
        self.run_btn.setText(amp(tr("plan.run")))
        self.ad_btn.setText(amp(tr("plan.adaptive.run")))
        self.add_btn.setText(amp(tr("plan.added" if self.add_btn.isChecked() else "plan.add")))

    def on_language(self) -> None:
        for c in (self.cand, self.window, self.budget):
            c.retranslate()
        self.retranslate_buttons()
        if self.front is not None:
            self.show_front(self.front)
        if self.adaptive_result is not None:
            self.show_adaptive(self.adaptive_result)
