"""Radar charts (decision 0012).

- `ProfileRadar`: performance profiles on the nine criteria (0 at the centre, best of the shortlist on
  the rim) as small multiples, one per option, or all overlaid. Also used for weights in step 4.
- `WeightRadar`: the company's weights (red) on a ship's radar screen; the green echoes are the
  weight sets SMAA tries around them for which the recommendation stays first, the amber ones those
  for which another option wins. A sweep turns slowly; echoes light up as it passes.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QToolTip

from ..i18n import pct
from . import anim, theme
from .charts import AnimatedChart, Morph, nice_step, with_alpha

RED = "#D23B2E"


def spoke(i: int, n: int) -> float:
    """Bearing of spoke i in radians, clockwise from north."""
    return 2 * math.pi * i / n


def polar(cx: float, cy: float, r: float, bearing: float) -> QPointF:
    return QPointF(cx + r * math.sin(bearing), cy - r * math.cos(bearing))


def polygon(cx, cy, radius, values, n) -> QPainterPath:
    path = QPainterPath()
    for i, v in enumerate(values):
        pt = polar(cx, cy, radius * max(float(v), 0.0), spoke(i, n))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


# ------------------------------------------------------------------ profiles
class ProfileRadar(AnimatedChart):
    """series: (name, values in [0, 1] of the scale, colour, emphasised, tips per axis or None)."""

    def __init__(self, grid: bool = True, min_h: int = 300):
        super().__init__(min_h)
        self.grid = grid
        self.axes: list[str] = []
        self.short: list[str] = []
        self.axis_colors: list[str] = []
        self.series: list[tuple[str, str, bool, list[str] | None]] = []
        self.ring_fmt = None
        self._vals = Morph()
        self._cells: list[tuple[float, float, float]] = []

    def set_grid(self, on: bool) -> None:
        self.grid = on
        self._layout_height()
        self.update()

    def set_data(self, axes: Sequence[str], short: Sequence[str], axis_colors: Sequence[str],
                 series: Sequence[tuple[str, Sequence[float], str, bool, Sequence[str] | None]], ring_fmt=None) -> None:
        vals = np.array([s[1] for s in series], float).reshape(len(series), len(axes))
        if [s[0] for s in series] != [s[0] for s in self.series] or list(axes) != self.axes:
            self._vals.new = None
        self.axes, self.short, self.axis_colors = list(axes), list(short), list(axis_colors)
        self.series = [(s[0], s[2], s[3], list(s[4]) if s[4] is not None else None) for s in series]
        self.ring_fmt = ring_fmt
        self._vals.set(np.clip(np.nan_to_num(vals), 0, 1.05), self._t)
        self._layout_height()
        self._start()

    def _cols(self) -> int:
        n = len(self.series)
        return max(1, min(n, int(max(self.width(), 340) // 340)))

    def _layout_height(self) -> None:
        if self.grid and self.series:
            rows = math.ceil(len(self.series) / self._cols())
            self.setMinimumHeight(rows * 300 + 30)
        else:
            self.setMinimumHeight(430)

    def resizeEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(e)
        self._layout_height()

    def _draw_frame(self, g, cx, cy, rad, labels, font_pt) -> None:
        p = theme.current()
        n = len(self.axes)
        for k in (0.25, 0.5, 0.75, 1.0):
            g.setPen(QPen(theme.c("border") if k < 1 else theme.c("muted"), 1 if k < 1 else 1.3))
            g.setBrush(Qt.BrushStyle.NoBrush)
            g.drawEllipse(QPointF(cx, cy), rad * k, rad * k)
        g.setFont(theme.ui_font(font_pt))
        fm = QFontMetricsF(g.font())
        for i in range(n):
            b = spoke(i, n)
            col = QColor(self.axis_colors[i]) if self.axis_colors else theme.c("muted")
            pen = QPen(with_alpha(col, 0.75), 1.2)
            g.setPen(pen)
            g.drawLine(QPointF(cx, cy), polar(cx, cy, rad, b))
            txt = labels[i]
            pt = polar(cx, cy, rad + 8 + fm.height() * 0.4, b)
            w = fm.horizontalAdvance(txt)
            sx = math.sin(b)
            x = pt.x() - w / 2 + sx * w / 2
            g.setPen(theme.c("muted"))
            g.drawText(QRectF(x, pt.y() - fm.height() / 2, w + 2, fm.height()), Qt.AlignmentFlag.AlignCenter, txt)
        if self.ring_fmt:
            g.setPen(theme.c("faint"))
            g.setFont(theme.ui_font(7.5))
            for k in (0.25, 0.5, 0.75, 1.0):
                g.drawText(polar(cx, cy, rad * k + 3, math.pi / n) + QPointF(2, 0), self.ring_fmt(k))
        del p

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.series:
            return
        g = self.painter()
        vals = self._vals.at(self._t)
        n = len(self.axes)
        self._cells = []
        if self.grid:
            cols = self._cols()
            cw = self.width() / cols
            ch = 300
            for s, (name, color, emph, _tips) in enumerate(self.series):
                r_, c_ = divmod(s, cols)
                cx, cy = cw * c_ + cw / 2, 40 + ch * r_ + ch / 2 + 4
                rad = min(cw / 2 - 88, ch / 2 - 58)
                g.setFont(theme.ui_font(9.5, QFont.Weight.DemiBold))
                g.setPen(QColor(color) if emph else theme.c("text"))
                fm = QFontMetricsF(g.font())
                g.drawText(QRectF(cw * c_ + 8, 40 + ch * r_ - 30, cw - 16, 20), Qt.AlignmentFlag.AlignCenter,
                           fm.elidedText(name, Qt.TextElideMode.ElideRight, cw - 16))
                self._draw_frame(g, cx, cy, rad, self.short, 7.5)
                path = polygon(cx, cy, rad, vals[s], n)
                col = QColor(color)
                g.setPen(QPen(col, 2.2 if emph else 1.6))
                g.setBrush(with_alpha(col, 0.32 if emph else 0.22))
                g.drawPath(path)
                self._cells.append((cx, cy, rad))
        else:
            cx, cy = self.width() / 2, self.height() / 2 + 6
            rad = min(self.width() / 2 - 120, self.height() / 2 - 46)
            self._draw_frame(g, cx, cy, rad, self.axes, 8.5)
            order = sorted(range(len(self.series)), key=lambda s: self.series[s][2])
            for s in order:
                name, color, emph, _tips = self.series[s]
                col = QColor(color)
                g.setPen(QPen(col, 2.6 if emph else 1.4))
                g.setBrush(with_alpha(col, 0.26 if emph else 0.06))
                g.drawPath(polygon(cx, cy, rad, vals[s], n))
                if emph:
                    g.setBrush(col)
                    g.setPen(QPen(theme.c("panel"), 1.5))
                    for i in range(n):
                        g.drawEllipse(polar(cx, cy, rad * max(vals[s][i], 0), spoke(i, n)), 3.4, 3.4)
            self._cells = [(cx, cy, rad)]
            self.draw_legend(g, [(nm, QColor(c), "box") for nm, c, _e, _t in self.series], 12, 2)
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if not self.series or not self._cells or self._vals.new is None:
            return
        n = len(self.axes)
        pos = e.position()
        for ci, (cx, cy, rad) in enumerate(self._cells):
            dx, dy = pos.x() - cx, pos.y() - cy
            d = math.hypot(dx, dy)
            if d > rad + 20 or d < 6:
                continue
            b = math.atan2(dx, -dy) % (2 * math.pi)
            i = int(round(b / (2 * math.pi / n))) % n
            idx = [ci] if self.grid else range(len(self.series))
            rows = [f"<b>{self.axes[i]}</b>"]
            for s in idx:
                name, color, _emph, tips = self.series[s]
                val = tips[i] if tips else pct(self._vals.new[s][i])
                rows.append(f"<span style='color:{color}'>■</span> {name}: {val}")
            QToolTip.showText(e.globalPosition().toPoint(), "<br>".join(rows), self)
            return
        QToolTip.hideText()


# ------------------------------------------------------------------ ship's radar
SCREEN = "#03140D"
PHOSPHOR = "#46F08F"
AMBER = "#F2B544"


class WeightRadar(AnimatedChart):
    PERIOD_MS = 6000

    def __init__(self):
        super().__init__(470)
        self.axes: list[str] = []
        self.families: list[str] = []
        self.family_colors: list[str] = []
        self._you, self._cloud = Morph(), Morph()
        self.wins = np.zeros(0, bool)
        self.rmax = 0.4
        self.texts = ("", "", "")       # you, holds, flips
        self._sweep = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._turn)
        self._cache: tuple | None = None
        self._static_pm: tuple | None = None
        self._version = 0
        self._geom = (0.0, 0.0, 1.0)

    # sweep runs only while visible and animations are on
    def showEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().showEvent(e)
        if anim.enabled():
            self._timer.start()

    def hideEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().hideEvent(e)
        self._timer.stop()

    def _turn(self) -> None:
        if not anim.enabled():
            self._timer.stop()
            return
        self._sweep = (self._sweep + 2 * math.pi * self._timer.interval() / self.PERIOD_MS) % (2 * math.pi)
        self.update()

    def set_data(self, axes, families, family_colors, you, cloud, wins, texts) -> None:
        you = np.asarray(you, float)
        cloud = np.asarray(cloud, float)
        top = max(float(np.quantile(cloud, 0.97)) if cloud.size else 0.0, float(you.max(initial=0))) * 1.12
        step = nice_step(top, 4)
        self.rmax = max(step * math.ceil(top / step), 0.05)
        if list(axes) != self.axes:
            self._you.new = self._cloud.new = None
        self.axes, self.families, self.family_colors = list(axes), list(families), list(family_colors)
        self._you.set(you / self.rmax, self._t)
        self._cloud.set(cloud / self.rmax, self._t)
        self.wins = np.asarray(wins, bool)
        self.texts = texts
        self._cache = None
        self._version += 1
        self._start()
        if anim.enabled() and self.isVisible() and not self._timer.isActive():
            self._timer.start()

    def _paths(self, cx, cy, rad, cloud):
        key = (round(cx), round(cy), round(rad), round(self._t, 3))
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        n = len(self.axes)
        win, lose = QPainterPath(), QPainterPath()
        sins = np.sin([spoke(i, n) for i in range(n)])
        coss = np.cos([spoke(i, n) for i in range(n)])
        xs = cx + rad * np.clip(cloud, 0, 1.08) * sins
        ys = cy - rad * np.clip(cloud, 0, 1.08) * coss
        for k in range(len(cloud)):
            path = win if (k < len(self.wins) and self.wins[k]) else lose
            path.moveTo(xs[k, 0], ys[k, 0])
            for i in range(1, n):
                path.lineTo(xs[k, i], ys[k, i])
            path.closeSubpath()
        blips = [([QPointF(xs[k, i], ys[k, i]) for k in range(len(cloud)) if k < len(self.wins) and self.wins[k]],
                  [QPointF(xs[k, i], ys[k, i]) for k in range(len(cloud)) if not (k < len(self.wins) and self.wins[k])])
                 for i in range(n)]
        self._cache = (key, (win, lose, blips))
        return self._cache[1]

    def _static(self, cx, cy, rad, cloud) -> QPixmap:
        """Bezel, rings, scales, labels, the faint echo outlines and the key, drawn once per state."""
        dpr = self.devicePixelRatioF()
        settled = self._t >= 1.0
        key = (self.width(), self.height(), dpr, theme.current().name, self._version, settled)
        if self._static_pm is not None and self._static_pm[0] == key:
            return self._static_pm[1]
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        g = QPainter(pm)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        g.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        n = len(self.axes)
        # bezel and screen
        g.setPen(Qt.PenStyle.NoPen)
        bezel = QRadialGradient(QPointF(cx, cy), rad + 26)
        bezel.setColorAt(0.90, QColor("#1B2A26"))
        bezel.setColorAt(1.0, QColor("#0B1310"))
        g.setBrush(QBrush(bezel))
        g.drawEllipse(QPointF(cx, cy), rad + 24, rad + 24)
        screen = QRadialGradient(QPointF(cx, cy), rad)
        screen.setColorAt(0, QColor("#0A3220"))
        screen.setColorAt(1, QColor(SCREEN))
        g.setBrush(QBrush(screen))
        g.drawEllipse(QPointF(cx, cy), rad + 6, rad + 6)
        ph = QColor(PHOSPHOR)
        # range rings with weight labels
        g.setFont(theme.ui_font(7.5))
        for k in (0.25, 0.5, 0.75, 1.0):
            g.setPen(QPen(with_alpha(ph, 0.28 if k < 1 else 0.55), 1))
            g.setBrush(Qt.BrushStyle.NoBrush)
            g.drawEllipse(QPointF(cx, cy), rad * k, rad * k)
            g.setPen(with_alpha(ph, 0.75))
            g.drawText(polar(cx, cy, rad * k - 4, math.pi / n) + QPointF(3, 0), pct(self.rmax * k))
        # bearing scale
        for deg in range(0, 360, 5):
            b = math.radians(deg)
            inner = rad - (9 if deg % 30 == 0 else 4)
            g.setPen(QPen(with_alpha(ph, 0.6 if deg % 30 == 0 else 0.3), 1))
            g.drawLine(polar(cx, cy, inner, b), polar(cx, cy, rad, b))
            if deg % 30 == 0:
                g.setPen(with_alpha(ph, 0.55))
                pt = polar(cx, cy, rad - 19, b)
                g.drawText(QRectF(pt.x() - 14, pt.y() - 7, 28, 14), Qt.AlignmentFlag.AlignCenter, f"{deg:03d}")
        # spokes and labels (criteria), with a family colour dot
        g.setFont(theme.ui_font(8.5))
        fm = QFontMetricsF(g.font())
        for i in range(n):
            b = spoke(i, n)
            g.setPen(QPen(with_alpha(ph, 0.22), 1, Qt.PenStyle.DashLine))
            g.drawLine(QPointF(cx, cy), polar(cx, cy, rad, b))
            txt = self.axes[i]
            w = fm.horizontalAdvance(txt)
            pt = polar(cx, cy, rad + 36, b)
            sx = math.sin(b)
            x = pt.x() - w / 2 + sx * (w / 2 + 4)
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(QColor(self.family_colors[i]))
            g.drawEllipse(QPointF(x - 8, pt.y()), 3.5, 3.5)
            g.setPen(theme.c("text"))
            g.drawText(QRectF(x, pt.y() - fm.height() / 2, w + 4, fm.height()), Qt.AlignmentFlag.AlignVCenter, txt)
        # faint outlines of every echo, once the data has settled
        if settled and cloud is not None and len(cloud):
            win, lose, _blips = self._paths(cx, cy, rad, cloud)
            clip = QPainterPath()
            clip.addEllipse(QPointF(cx, cy), rad + 2, rad + 2)
            g.setClipPath(clip)
            g.setBrush(Qt.BrushStyle.NoBrush)
            g.setPen(QPen(with_alpha(AMBER, 0.05), 1))
            g.drawPath(lose)
            g.setPen(QPen(with_alpha(ph, 0.045), 1))
            g.drawPath(win)
            g.setClipping(False)
        g.setFont(theme.ui_font(8.5))
        y = 8.0
        for col, txt in ((QColor(RED), self.texts[0]), (ph, self.texts[1]), (QColor(AMBER), self.texts[2])):
            if not txt:
                continue
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(col)
            g.drawEllipse(QPointF(14, y + 8), 4.5, 4.5)
            g.setPen(theme.c("muted"))
            g.drawText(QRectF(26, y, 190, 40), Qt.TextFlag.TextWordWrap, txt)
            y += 40
        g.end()
        self._static_pm = (key, pm)
        return pm

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.axes:
            return
        g = self.painter()
        n = len(self.axes)
        W, H = self.width(), self.height()
        rad = min(W / 2 - 150, H / 2 - 52)
        cx, cy = W / 2, H / 2
        self._geom = (cx, cy, rad)
        ph = QColor(PHOSPHOR)
        cloud = self._cloud.at(self._t)
        g.drawPixmap(0, 0, self._static(cx, cy, rad, cloud))
        g.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), rad + 2, rad + 2)
        g.setClipPath(clip)
        if cloud is not None and len(cloud):
            _win, _lose, blips = self._paths(cx, cy, rad, cloud)
            for i in range(n):
                delta = (self._sweep - spoke(i, n)) % (2 * math.pi)
                glow = math.exp(-delta / 1.1) if anim.enabled() else 0.4
                good, bad = blips[i]
                g.setPen(QPen(with_alpha(AMBER, 0.18 + 0.7 * glow), 2.6))
                g.drawPoints(bad)
                g.setPen(QPen(with_alpha(ph, 0.22 + 0.75 * glow), 2.6))
                g.drawPoints(good)
        # sweep
        if anim.enabled():
            cg = QConicalGradient(QPointF(cx, cy), 90 - math.degrees(self._sweep))
            cg.setColorAt(0.0, with_alpha(ph, 0.38))
            cg.setColorAt(0.12, with_alpha(ph, 0.0))
            cg.setColorAt(1.0, with_alpha(ph, 0.0))
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(QBrush(cg))
            g.drawEllipse(QPointF(cx, cy), rad, rad)
            g.setPen(QPen(with_alpha(ph, 0.9), 1.6))
            g.drawLine(QPointF(cx, cy), polar(cx, cy, rad, self._sweep))
        g.restore()
        # the company's weights
        you = self._you.at(self._t)
        if you is not None:
            path = polygon(cx, cy, rad, np.clip(you, 0, 1.08), n)
            g.setPen(QPen(QColor(RED), 2.8))
            g.setBrush(with_alpha(RED, 0.16))
            g.drawPath(path)
            for i in range(n):
                pt = polar(cx, cy, rad * min(max(you[i], 0), 1.08), spoke(i, n))
                g.setPen(QPen(QColor("#FFFFFF"), 1.6))
                g.setBrush(QColor(RED))
                g.drawEllipse(pt, 4.2, 4.2)
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(with_alpha(ph, 0.9))
        g.drawEllipse(QPointF(cx, cy), 2.5, 2.5)
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if not self.axes or self._you.new is None:
            return
        cx, cy, rad = self._geom
        dx, dy = e.position().x() - cx, e.position().y() - cy
        if math.hypot(dx, dy) > rad + 60:
            QToolTip.hideText()
            return
        n = len(self.axes)
        i = int(round((math.atan2(dx, -dy) % (2 * math.pi)) / (2 * math.pi / n))) % n
        c = self._cloud.new[:, i] * self.rmax
        w = self.wins[: len(c)]
        rows = [f"<b>{self.axes[i]}</b>", f"<span style='color:{RED}'>●</span> {pct(self._you.new[i] * self.rmax, 1)}"]
        if w.any():
            lo, hi = np.quantile(c[w], [0.05, 0.95])
            rows.append(f"<span style='color:{PHOSPHOR}'>●</span> {pct(lo, 1)} – {pct(hi, 1)}")
        if (~w).any():
            lo, hi = np.quantile(c[~w], [0.05, 0.95])
            rows.append(f"<span style='color:{AMBER}'>●</span> {pct(lo, 1)} – {pct(hi, 1)}")
        QToolTip.showText(e.globalPosition().toPoint(), "<br>".join(rows), self)

