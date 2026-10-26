"""On-screen charts, hand-drawn with QPainter (decision 0012; the pattern of Financial Architect).

Every chart morphs from what it shows now to the new data whenever an input changes: values,
scale and labels move together in about 0.7 s (ui.anim; off switch in the top bar). Print figures
for reports and the thesis use matplotlib from the same data (decision 0003).

`Switchable` holds two or more views of the same result with a small chip of buttons in the
top-right corner that does not take any layout space.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QStackedWidget, QToolButton, QToolTip, QVBoxLayout, QWidget

from ..i18n import num
from . import anim, theme

DURATION = 700


# ------------------------------------------------------------------ helpers
def lerp(a, b, t):
    return a + (b - a) * t


def with_alpha(col: QColor | str, a: float) -> QColor:
    c = QColor(col)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def nice_step(span: float, n: int = 5) -> float:
    if span <= 0:
        return 1.0
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    return min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=raw)


def nice_range(lo: float, hi: float, n: int = 5) -> tuple[float, float, list[float]]:
    """Axis bounds on round numbers that include 0, and the ticks between them."""
    lo, hi = min(lo, 0.0), max(hi, 0.0)
    if hi - lo < 1e-12:
        hi = 1.0
    step = nice_step(hi - lo, n)
    a, b = math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step
    if b <= a:
        b = a + step
    ticks = [a + i * step for i in range(int(round((b - a) / step)) + 1)]
    return a, b, ticks


def money_tick(v: float, top: float) -> str:
    if top >= 1e6:
        return num(v / 1e6, 1) + "m"
    if top >= 1e3:
        return num(v / 1e3, 0) + "k"
    return num(v, 0)


def number_tick(v: float, top: float) -> str:
    if top >= 1e6:
        return num(v / 1e6, 1) + "m"
    if top >= 1e4:
        return num(v / 1e3, 0) + "k"
    return num(v, 0)


class Morph:
    """An array that eases from its shown value to a new target; mismatched shapes start from zero."""

    def __init__(self):
        self.old: np.ndarray | None = None
        self.new: np.ndarray | None = None

    def set(self, target, t: float, start=None) -> None:
        target = np.asarray(target, float)
        cur = self.at(t)
        if cur is None or cur.shape != target.shape:
            cur = np.zeros_like(target) if start is None else np.broadcast_to(np.asarray(start, float),
                                                                              target.shape).copy()
        self.old, self.new = np.nan_to_num(cur), target

    def at(self, t: float) -> np.ndarray | None:
        if self.new is None:
            return None
        return self.old + (np.nan_to_num(self.new) - self.old) * t


# ------------------------------------------------------------------ base
class AnimatedChart(QWidget):
    duration = DURATION

    def __init__(self, min_h: int = 220):
        super().__init__()
        self.setMinimumHeight(min_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._t = 1.0
        self._hover: int | None = None
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self.duration)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._tick)

    def _tick(self, v) -> None:
        self._t = float(v)
        self.update()

    def _start(self) -> None:
        """Call after the Morphs were set from `self._t`; plays the transition (or jumps to the end)."""
        self._anim.stop()
        if anim.enabled() and self.isVisible():
            self._t = 0.0
            self._anim.start()
        else:
            self._t = 1.0
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(520, self.minimumHeight())

    def painter(self) -> QPainter:
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        g.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        return g

    def draw_legend(self, g: QPainter, items: Sequence[tuple[str, QColor, str]], x: float, y: float) -> float:
        """Legend chips in one wrapped row starting at (x, y); kind 'box' or 'line'. Returns the bottom y."""
        g.setFont(theme.ui_font(8.5))
        fm = QFontMetricsF(g.font())
        x0 = x
        for text, col, kind in items:
            w = 15 + fm.horizontalAdvance(text) + 18
            if x + w > self.width() - 8 and x > x0:
                x, y = x0, y + 18
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(col)
            if kind == "line":
                g.drawRoundedRect(QRectF(x, y + 7, 11, 3), 1.5, 1.5)
            else:
                g.drawRoundedRect(QRectF(x, y + 3, 10, 10), 2.5, 2.5)
            g.setPen(theme.c("muted"))
            g.drawText(QPointF(x + 15, y + 12), text)
            x += w
        return y + 18

    def restyle(self) -> None:
        self.update()

    def leaveEvent(self, _e) -> None:  # noqa: N802 - Qt API
        self._hover = None
        self.update()


# ------------------------------------------------------------------ vertical bars by year
class StackedBarChart(AnimatedChart):
    """Bars by year split into stacked components (positives up, negatives down), with an optional
    line on top (e.g. a reported total). Hover shows the year's figures."""

    def __init__(self, axis: str = "number"):
        super().__init__(240)
        self.tick = money_tick if axis == "money" else number_tick
        self.years: list[int] = []
        self.series: list[tuple[str, str]] = []
        self.line_meta: tuple[str, str] | None = None
        self._vals, self._line, self._mask = Morph(), Morph(), None
        self._scale = Morph()
        self._ticks: list[float] = []
        self._legend = True

    def set_data(self, years: list[int], series: list[tuple[str, list[float], str]],
                 line: tuple[str, list[float | None], str] | None = None) -> None:
        vals = np.array([s[1] for s in series], float).reshape(len(series), len(years))
        same = list(years) == self.years and len(series) == len(self.series)
        if not same:
            self._vals.new = None
        self._vals.set(vals, self._t)
        self.years, self.series = list(years), [(s[0], s[2]) for s in series]
        top = np.clip(vals, 0, None).sum(axis=0).max(initial=0.0)
        bottom = np.clip(vals, None, 0).sum(axis=0).min(initial=0.0)
        if line:
            lv = np.array([np.nan if v is None else v for v in line[1]], float)
            self._mask = ~np.isnan(lv)
            if not same or self.line_meta is None:
                self._line.new = None
            self._line.set(np.nan_to_num(lv), self._t)
            self.line_meta = (line[0], line[2])
            if self._mask.any():
                top = max(top, float(np.nanmax(lv)))
                bottom = min(bottom, float(np.nanmin(lv)))
        else:
            self.line_meta, self._mask = None, None
        lo, hi, self._ticks = nice_range(bottom, top * 1.04)
        self._scale.set([lo, hi], self._t, start=[lo, hi])
        self._start()

    def _geometry(self):
        legend_h = 26 if self._legend and (len(self.series) > 1 or self.line_meta) else 8
        left, right, top, bottom = 58, 12, legend_h + 8, 26
        return QRectF(left, top, self.width() - left - right, self.height() - top - bottom)

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.years:
            return
        g = self.painter()
        p = theme.current()
        r = self._geometry()
        lo, hi = self._scale.at(self._t)
        span = (hi - lo) or 1.0

        def y(v):
            return r.bottom() - (v - lo) / span * r.height()

        top_abs = max(abs(self._ticks[0]), abs(self._ticks[-1])) if self._ticks else 1
        g.setFont(theme.ui_font(8))
        for tv in self._ticks:
            yy = y(tv)
            if yy < r.top() - 4 or yy > r.bottom() + 4:
                continue
            g.setPen(QPen(theme.c("grid"), 1))
            g.drawLine(QPointF(r.left(), yy), QPointF(r.right(), yy))
            g.setPen(theme.c("faint"))
            g.drawText(QRectF(0, yy - 8, r.left() - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       self.tick(tv, top_abs))
        n = len(self.years)
        slot = r.width() / n
        bw = min(slot * 0.64, 46)
        vals = self._vals.at(1.0)
        old = self._vals.old
        if self._hover is not None and 0 <= self._hover < n:
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(with_alpha(p.accent, 0.07))
            g.drawRoundedRect(QRectF(r.left() + slot * self._hover + 2, r.top(), slot - 4, r.height()), 4, 4)
        stagger = 0.35 / max(n, 1)
        for i in range(n):
            ti = max(0.0, min(1.0, (self._t - stagger * i) / max(1 - stagger * (n - 1), 0.3)))
            ti = 1 - (1 - ti) ** 2
            x = r.left() + slot * i + (slot - bw) / 2
            up = down = 0.0
            col_vals = old[:, i] + (vals[:, i] - old[:, i]) * ti
            pos_idx = [k for k in range(len(self.series)) if col_vals[k] >= 0]
            for k, (_name, color) in enumerate(self.series):
                v = col_vals[k]
                if v >= 0:
                    a, b = up, up + v
                    up = b
                else:
                    a, b = down + v, down
                    down = a
                rect = QRectF(x, y(b), bw, max(y(a) - y(b), 0.0))
                if rect.height() < 0.3:
                    continue
                g.setPen(Qt.PenStyle.NoPen)
                g.setBrush(QColor(color))
                if v >= 0 and pos_idx and k == pos_idx[-1]:
                    path = QPainterPath()
                    rad = min(3.0, rect.height(), bw / 2)
                    path.moveTo(rect.bottomLeft())
                    path.lineTo(rect.left(), rect.top() + rad)
                    path.quadTo(rect.topLeft(), QPointF(rect.left() + rad, rect.top()))
                    path.lineTo(rect.right() - rad, rect.top())
                    path.quadTo(rect.topRight(), QPointF(rect.right(), rect.top() + rad))
                    path.lineTo(rect.bottomRight())
                    path.closeSubpath()
                    g.drawPath(path)
                else:
                    g.drawRect(rect)
            g.setPen(theme.c("faint"))
            g.setFont(theme.ui_font(8))
            every = max(1, math.ceil(n / max(r.width() / 44, 1)))
            if i % every == 0 or i == n - 1:
                g.drawText(QRectF(r.left() + slot * i - 10, r.bottom() + 5, slot + 20, 16), Qt.AlignmentFlag.AlignCenter,
                           str(self.years[i]))
        if lo < 0 < hi:
            g.setPen(QPen(theme.c("faint"), 1))
            g.drawLine(QPointF(r.left(), y(0)), QPointF(r.right(), y(0)))
        if self.line_meta and self._mask is not None and self._mask.any():
            lv = self._line.at(self._t)
            col = QColor(self.line_meta[1])
            path = QPainterPath()
            started = False
            pts = []
            for i in range(n):
                if not self._mask[i]:
                    started = False
                    continue
                pt = QPointF(r.left() + slot * (i + 0.5), y(lv[i]))
                pts.append(pt)
                if started:
                    path.lineTo(pt)
                else:
                    path.moveTo(pt)
                    started = True
            g.setPen(QPen(col, 2.2))
            g.setBrush(Qt.BrushStyle.NoBrush)
            g.drawPath(path)
            g.setBrush(theme.c("panel"))
            g.setPen(QPen(col, 2))
            for pt in pts:
                g.drawEllipse(pt, 3.2, 3.2)
        if self._legend and (len(self.series) > 1 or self.line_meta):
            items = [(name, QColor(c), "box") for name, c in self.series]
            if self.line_meta:
                items.append((self.line_meta[0], QColor(self.line_meta[1]), "line"))
            self.draw_legend(g, items, r.left(), 2)
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if not self.years:
            return
        r = self._geometry()
        i = int((e.position().x() - r.left()) / (r.width() / len(self.years)))
        i = i if 0 <= i < len(self.years) and r.contains(e.position()) else None
        if i != self._hover:
            self._hover = i
            self.update()
            if i is None:
                QToolTip.hideText()
                return
            vals = self._vals.new
            top = max(abs(v) for v in self._ticks) if self._ticks else 1
            lines = [f"<b>{self.years[i]}</b>"]
            for k, (name, color) in enumerate(self.series):
                if len(self.series) > 1 or name:
                    lines.append(f"<span style='color:{color}'>■</span> {name}: {self.tick(vals[k, i], top)}")
            if len(self.series) > 1:
                lines.append(f"Σ {self.tick(vals[:, i].sum(), top)}")
            elif not self.series[0][0]:
                lines.append(self.tick(vals[0, i], top))
            if self.line_meta and self._mask is not None and self._mask[i]:
                lines.append(f"<span style='color:{self.line_meta[1]}'>—</span> {self.line_meta[0]}: "
                             f"{self.tick(self._line.new[i], top)}")
            QToolTip.showText(e.globalPosition().toPoint(), "<br>".join(lines), self)


class BarChart(StackedBarChart):
    """Vertical bars by year with a money axis (one series)."""

    def __init__(self):
        super().__init__(axis="money")
        self.setMinimumHeight(260)
        self._legend = False

    def set_data(self, years: list[int], values: list[float], color: str) -> None:  # type: ignore[override]
        super().set_data(years, [("", values, color)])


# ------------------------------------------------------------------ cash flow
class CashFlowChart(AnimatedChart):
    """Yearly net cash flow (bars above or below zero) and the running total (line with a soft area)."""

    def __init__(self):
        super().__init__(220)
        self.years: list[int] = []
        self.labels = ("", "")
        self._flows, self._cum, self._scale = Morph(), Morph(), Morph()
        self._ticks: list[float] = []

    def set_data(self, years: list[int], flows: list[float], labels: tuple[str, str]) -> None:
        if list(years) != self.years:
            self._flows.new = self._cum.new = None
        self.years, self.labels = list(years), labels
        f = np.asarray(flows, float)
        cum = np.cumsum(f) if len(f) else f
        self._flows.set(f, self._t)
        self._cum.set(cum, self._t)
        if len(f):
            lo, hi, self._ticks = nice_range(min(f.min(), cum.min(), 0), max(f.max(), cum.max(), 0))
            self._scale.set([lo, hi], self._t, start=[lo, hi])
        self._start()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.years:
            return
        g = self.painter()
        p = theme.current()
        r = QRectF(58, 30, self.width() - 70, self.height() - 56)
        lo, hi = self._scale.at(self._t)
        span = (hi - lo) or 1.0

        def y(v):
            return r.bottom() - (v - lo) / span * r.height()

        top_abs = max(abs(self._ticks[0]), abs(self._ticks[-1]))
        g.setFont(theme.ui_font(8))
        for tv in self._ticks:
            g.setPen(QPen(theme.c("grid"), 1))
            g.drawLine(QPointF(r.left(), y(tv)), QPointF(r.right(), y(tv)))
            g.setPen(theme.c("faint"))
            g.drawText(QRectF(0, y(tv) - 8, r.left() - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       money_tick(tv, top_abs))
        n = len(self.years)
        slot = r.width() / n
        bw = min(slot * 0.62, 30)
        f = self._flows.at(self._t)
        for i in range(n):
            v = f[i]
            x = r.left() + slot * i + (slot - bw) / 2
            rect = QRectF(x, min(y(v), y(0)), bw, abs(y(v) - y(0)))
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(with_alpha(p.good if v >= 0 else p.bad, 0.85))
            g.drawRoundedRect(rect, 2, 2)
            every = max(1, math.ceil(n / max(r.width() / 44, 1)))
            if i % every == 0 or i == n - 1:
                g.setPen(theme.c("faint"))
                g.drawText(QRectF(r.left() + slot * i - 10, r.bottom() + 5, slot + 20, 16), Qt.AlignmentFlag.AlignCenter,
                           str(self.years[i]))
        g.setPen(QPen(theme.c("faint"), 1))
        g.drawLine(QPointF(r.left(), y(0)), QPointF(r.right(), y(0)))
        cum = self._cum.at(self._t)
        pts = [QPointF(r.left() + slot * (i + 0.5), y(cum[i])) for i in range(n)]
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        area = QPainterPath(path)
        area.lineTo(pts[-1].x(), y(0))
        area.lineTo(pts[0].x(), y(0))
        area.closeSubpath()
        grad = QLinearGradient(0, r.top(), 0, r.bottom())
        grad.setColorAt(0, with_alpha(p.accent, 0.20))
        grad.setColorAt(1, with_alpha(p.accent, 0.02))
        g.fillPath(area, grad)
        g.setPen(QPen(theme.c("accent"), 2.2))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawPath(path)
        g.setBrush(theme.c("accent"))
        g.drawEllipse(pts[-1], 3.5, 3.5)
        if self._t > 0.6:
            g.setPen(with_alpha(p.accent, (self._t - 0.6) / 0.4))
            g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold))
            g.drawText(QRectF(pts[-1].x() - 110, pts[-1].y() - 20, 106, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, money_tick(self._cum.new[-1], top_abs))
        self.draw_legend(g, [(self.labels[0], with_alpha(p.good, 0.85), "box"),
                             (self.labels[1], theme.c("accent"), "line")], r.left(), 4)
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if not self.years or self._flows.new is None:
            return
        r = QRectF(58, 30, self.width() - 70, self.height() - 56)
        i = int((e.position().x() - r.left()) / (r.width() / len(self.years)))
        if 0 <= i < len(self.years) and r.contains(e.position()):
            top = max(abs(self._ticks[0]), abs(self._ticks[-1]))
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"<b>{self.years[i]}</b><br>{self.labels[0]}: {money_tick(self._flows.new[i], top)}"
                              f"<br>{self.labels[1]}: {money_tick(self._cum.new[i], top)}", self)


# ------------------------------------------------------------------ horizontal bars
class HBarChart(AnimatedChart):
    """Horizontal bars with category labels on the left (weights, shares); optional stacking.
    Values are written at the end of each bar once the bars have settled."""

    ROW = 28

    def __init__(self, percent: bool = True):
        super().__init__(160)
        self.percent = percent
        self.labels: list[str] = []
        self.series: list[tuple[str, str]] = []
        self._vals = Morph()
        self._top = Morph()

    def set_data(self, labels: list[str], series: list[tuple[str, list[float], str]]) -> None:
        vals = np.array([s[1] for s in series], float).reshape(len(series), len(labels))
        if list(labels) != self.labels or len(series) != len(self.series):
            self._vals.new = None
        self.labels, self.series = list(labels), [(s[0], s[2]) for s in series]
        self._vals.set(np.nan_to_num(vals), self._t)
        top = float(vals.sum(axis=0).max(initial=0)) or 1.0
        self._top.set([top], self._t, start=[top])
        self.setMinimumHeight(max(140, self.ROW * len(labels) + (60 if len(series) > 1 else 36)))
        self._start()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.labels:
            return
        g = self.painter()
        p = theme.current()
        g.setFont(theme.ui_font(9))
        fm = QFontMetricsF(g.font())
        left = min(max(fm.horizontalAdvance(t) for t in self.labels) + 20, self.width() * 0.45)
        legend = len(self.series) > 1
        top0 = 26 if legend else 6
        r = QRectF(left, top0, self.width() - left - 58, self.ROW * len(self.labels))
        top = float(self._top.at(self._t)[0]) * 1.02
        vals = self._vals.at(self._t)
        # grid
        step = nice_step(top, 4)
        g.setFont(theme.ui_font(8))
        k = 0.0
        while k <= top + 1e-9:
            x = r.left() + k / top * r.width()
            g.setPen(QPen(theme.c("grid"), 1))
            g.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            g.setPen(theme.c("faint"))
            g.drawText(QRectF(x - 24, r.bottom() + 3, 48, 14), Qt.AlignmentFlag.AlignCenter,
                       f"{num(k * 100)}%" if self.percent else num(k, 0))
            k += step
        for i, lab in enumerate(self.labels):
            yy = r.top() + i * self.ROW
            g.setFont(theme.ui_font(9))
            g.setPen(theme.c("text"))
            g.drawText(QRectF(0, yy, left - 12, self.ROW), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(lab, Qt.TextElideMode.ElideMiddle, left - 14))
            x = r.left()
            for s, (_name, color) in enumerate(self.series):
                w = max(vals[s, i], 0) / top * r.width()
                g.setPen(Qt.PenStyle.NoPen)
                g.setBrush(QColor(color))
                g.drawRoundedRect(QRectF(x, yy + 6, w, self.ROW - 12), 3, 3)
                x += w
            if self._t > 0.55:
                g.setPen(with_alpha(p.muted, (self._t - 0.55) / 0.45))
                g.setFont(theme.ui_font(8.5))
                tot = float(self._vals.new[:, i].sum())
                g.drawText(QRectF(x + 6, yy, 60, self.ROW), Qt.AlignmentFlag.AlignVCenter,
                           f"{num(tot * 100, 1)}%" if self.percent else num(tot, 1))
        if legend:
            self.draw_legend(g, [(n, QColor(c), "box") for n, c in self.series], left, 2)
        g.end()


# ------------------------------------------------------------------ view switcher
class Switchable(QWidget):
    """Several views of one result; small toggle chips stand in a narrow gutter on the right."""

    GUTTER = 30

    def __init__(self, views: Sequence[tuple[str, str, QWidget]], on_change: Callable[[int], None] | None = None):
        """views: (glyph, tooltip, widget)."""
        super().__init__()
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, self.GUTTER, 0)
        lay.addWidget(self.stack)
        self.buttons: list[QToolButton] = []
        self.on_change = None
        for i, (glyph, tip, w) in enumerate(views):
            self.stack.addWidget(w)
            b = QToolButton(self)
            b.setObjectName("ViewChip")
            b.setText(glyph)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=i: self.set_index(k))
            self.buttons.append(b)
        self.set_index(0)
        self.on_change = on_change

    def widget(self, i: int) -> QWidget:
        return self.stack.widget(i)

    def index(self) -> int:
        return self.stack.currentIndex()

    def set_index(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        for k, b in enumerate(self.buttons):
            b.setChecked(k == i)
        if self.on_change:
            self.on_change(i)

    def set_tips(self, tips: Sequence[str]) -> None:
        for b, t in zip(self.buttons, tips, strict=False):
            b.setToolTip(t)

    def resizeEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(e)
        y = 2
        for b in self.buttons:
            b.setFixedSize(26, 24)
            b.move(self.width() - 27, y)
            b.raise_()
            y += 27
