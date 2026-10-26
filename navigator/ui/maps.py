"""Decision graphics for step 5 (decisions 0011 and 0012).

- `RankBubbles`: SMAA rank acceptability as a bubble matrix (options × ranks); the bubble's area is
  the share of futures in which the option takes that rank, in the option's colour. Replaces the
  first heatmap, whose dark cells hid the recommendation.
- `PriorityMap`: which option comes first for every split of weight between two criteria families.
  The regions are exact convex polygons (SAW scores are affine in the two weights), filled with soft
  tints and named in place; the company's weights are a red dot with a white halo and the SMAA weight
  sample is a light cloud. Changing the pair cross-fades the regions and glides the dot.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QToolTip

from ..i18n import num, pct
from . import theme
from .charts import AnimatedChart, Morph, with_alpha

RED = "#D23B2E"
# soft, distinguishable colours for the other options (light and dark themes); grey for "do nothing"
OPTION_COLORS = ["#4C8DB8", "#4FA88A", "#8E7CC3", "#D9A441", "#C77DA0", "#7A9E4F", "#5BB0C9", "#B5835A"]
REFERENCE = "#9AA5AE"
FAMILY_COLORS = {"money": "#D9A441", "climate": "#4FA88A", "technology": "#8E7CC3", "operations": "#4C8DB8",
                 "regulation": "#C77DA0"}


def option_colors(keys: list[str], best: str | None, reference: str) -> list[str]:
    out, k = [], 0
    for key in keys:
        if key == best:
            out.append(RED)
        elif key == reference:
            out.append(REFERENCE)
        else:
            out.append(OPTION_COLORS[k % len(OPTION_COLORS)])
            k += 1
    return out


def mix(a: str | QColor, b: str | QColor, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    t = min(max(t, 0.0), 1.0)
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t), int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t))


# ------------------------------------------------------------------ rank bubbles
class RankBubbles(AnimatedChart):
    TOP, ROW = 34, 48

    def __init__(self):
        super().__init__(160)
        self.names: list[str] = []
        self.colors: list[str] = []
        self.expected: list[float] = []
        self.best = self.reference = -1
        self.labels = ("", "", "", "")
        self._m = Morph()

    def set_data(self, names, matrix, expected, best, reference, labels, colors=None) -> None:
        if list(names) != self.names:
            self._m.new = None
        self.names, self.expected = list(names), list(expected)
        self.best, self.reference, self.labels = best, reference, labels
        self.colors = list(colors) if colors else [RED if i == best else OPTION_COLORS[i % 8] for i in range(len(names))]
        self._m.set(np.asarray(matrix, float), self._t)
        self.setMinimumHeight(self.TOP + self.ROW * len(self.names) + 16)
        self._start()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.names:
            return
        p = theme.current()
        g = self.painter()
        m = self._m.at(self._t)
        n_r = m.shape[1]
        g.setFont(theme.ui_font(9))
        fm = QFontMetricsF(g.font())
        left = min(max(fm.horizontalAdvance(nm) for nm in self.names) + 22, self.width() * 0.38)
        right = max(fm.horizontalAdvance(self.labels[1]) + 16, 80)
        cw = max((self.width() - left - right) / max(n_r, 1), 34)
        rmax = min(cw, self.ROW) / 2 - 2
        g.setPen(theme.c("muted"))
        g.setFont(theme.ui_font(8.5))
        for r in range(n_r):
            g.drawText(QRectF(left + r * cw, 0, cw, self.TOP - 8), Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                       self.labels[0].format(r=r + 1))
        g.drawText(QRectF(left + n_r * cw, 0, right, self.TOP - 8), Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                   self.labels[1])
        for i, name in enumerate(self.names):
            y = self.TOP + i * self.ROW
            cy = y + self.ROW / 2
            if i == self.best:
                g.setPen(Qt.PenStyle.NoPen)
                g.setBrush(with_alpha(RED, 0.07))
                g.drawRoundedRect(QRectF(4, y + 2, self.width() - 8, self.ROW - 4), 6, 6)
            g.setPen(QPen(theme.c("grid"), 1))
            g.drawLine(QPointF(left, cy), QPointF(left + n_r * cw, cy))
            g.setFont(theme.ui_font(9, QFont.Weight.DemiBold if i == self.best else QFont.Weight.Normal))
            g.setPen(QColor(RED) if i == self.best else (theme.c("muted") if i == self.reference else theme.c("text")))
            fm2 = QFontMetricsF(g.font())
            g.drawText(QRectF(0, y, left - 12, self.ROW), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fm2.elidedText(name, Qt.TextElideMode.ElideMiddle, left - 14))
            col = QColor(self.colors[i])
            for r in range(n_r):
                v = max(float(m[i, r]), 0.0)
                rad = rmax * math.sqrt(v)
                c = QPointF(left + r * cw + cw / 2, cy)
                if rad < 0.6:
                    g.setPen(Qt.PenStyle.NoPen)
                    g.setBrush(theme.c("border"))
                    g.drawEllipse(c, 1.5, 1.5)
                    continue
                g.setPen(QPen(col, 1.4))
                g.setBrush(with_alpha(col, 0.55 if i == self.best else 0.38))
                g.drawEllipse(c, rad, rad)
                if self._m.new[i, r] >= 0.1 and rad > 11:
                    g.setPen(theme.c("text") if p.name == "light" else QColor("#FFFFFF"))
                    g.setFont(theme.ui_font(8, QFont.Weight.DemiBold))
                    g.drawText(QRectF(c.x() - 24, c.y() - 8, 48, 16), Qt.AlignmentFlag.AlignCenter,
                               pct(self._m.new[i, r]))
            g.setPen(theme.c("text"))
            g.setFont(theme.ui_font(9))
            g.drawText(QRectF(left + n_r * cw, y, right, self.ROW), Qt.AlignmentFlag.AlignCenter,
                       num(self.expected[i], 1))
        self._geom = (left, cw)
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if not self.names or self._m.new is None or not hasattr(self, "_geom"):
            return
        left, cw = self._geom
        i = int((e.position().y() - self.TOP) // self.ROW)
        r = int((e.position().x() - left) // cw)
        if 0 <= i < len(self.names) and 0 <= r < self._m.new.shape[1]:
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"{self.names[i]}<br>{self.labels[0].format(r=r + 1)}: <b>{pct(self._m.new[i, r], 1)}</b>",
                              self)
        else:
            QToolTip.hideText()


RankHeatmap = RankBubbles       # the name used before decision 0012


# ------------------------------------------------------------------ priority map
class PriorityMap(AnimatedChart):
    """Winner regions over two family weights (x, y ∈ [0, 1], x + y ≤ 1)."""

    def __init__(self):
        super().__init__(440)
        self.setMinimumSize(420, 440)
        self.regions: list[list[tuple[float, float]]] = []
        self._old_regions: list[list[tuple[float, float]]] = []
        self.names: list[str] = []
        self.colors: list[str] = []
        self._old_colors: list[str] = []
        self._dot = Morph()
        self.cloud = np.zeros((0, 2))
        self.axis = ("", "")
        self.you = ""

    def set_data(self, regions, names, colors, dot, cloud, axis, you: str = "") -> None:
        self._old_regions, self._old_colors = self.regions, self.colors
        self.regions, self.names, self.colors = [list(r) for r in regions], list(names), list(colors)
        self.cloud, self.axis, self.you = np.asarray(cloud, float), axis, you
        self._dot.set(np.asarray(dot, float), self._t)
        self._start()

    def _rect(self) -> QRectF:
        side = min(self.width() - 80, self.height() - 64)
        return QRectF(62 + (self.width() - 80 - side) / 2, 14, side, side)

    def _px(self, x: float, y: float, r: QRectF) -> QPointF:
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def _poly(self, pts, r) -> QPolygonF:
        return QPolygonF([self._px(a, b, r) for a, b in pts])

    def _fill(self, color: str) -> QColor:
        p = theme.current()
        return mix(color, p.panel, 0.55 if p.name == "light" else 0.30)

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.regions:
            return
        p = theme.current()
        g = self.painter()
        r = self._rect()
        # light grid
        g.setFont(theme.ui_font(8))
        for k in range(0, 101, 25):
            t = k / 100
            g.setPen(QPen(theme.c("grid"), 1))
            g.drawLine(self._px(t, 0, r), self._px(t, 1 - t, r))
            g.drawLine(self._px(0, t, r), self._px(1 - t, t, r))
            g.setPen(theme.c("faint"))
            pt = self._px(t, 0, r)
            g.drawText(QRectF(pt.x() - 20, r.bottom() + 5, 40, 14), Qt.AlignmentFlag.AlignCenter, f"{k}%")
            pt = self._px(0, t, r)
            g.drawText(QRectF(r.left() - 48, pt.y() - 7, 42, 14), Qt.AlignmentFlag.AlignRight, f"{k}%")
        # regions: old ones fade out while the new fade in
        sep = QPen(theme.c("panel"), 2.2)
        for regions, colors, alpha in ((self._old_regions, self._old_colors, 1 - self._t), (self.regions, self.colors, self._t)):
            if alpha <= 0.01:
                continue
            for i, poly in enumerate(regions):
                if not poly:
                    continue
                g.setPen(sep)
                g.setBrush(with_alpha(self._fill(colors[i]), alpha))
                g.drawPolygon(self._poly(poly, r))
        # region names, two lines at most, kept clear of the red dot
        d_now = self._dot.at(self._t)
        dot_px = self._px(float(d_now[0]), float(d_now[1]), r)
        for i, poly in enumerate(self.regions):
            if len(poly) < 3:
                continue
            area = _area(poly)
            if area < 0.012:
                continue
            c = self._label_point(poly, dot_px, r)
            width = min(max(90.0, math.sqrt(area * 2) * r.width() * 0.8), 180.0)
            g.setFont(theme.ui_font(8.6, QFont.Weight.DemiBold))
            fm = QFontMetricsF(g.font())
            text = f"{self.names[i]}  {pct(area / 0.5)}"
            br = fm.boundingRect(QRectF(0, 0, width, 60), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter, text)
            box = QRectF(c.x() - br.width() / 2 - 8, c.y() - br.height() / 2 - 3, br.width() + 16, br.height() + 6)
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(with_alpha(p.panel, 0.84 * self._t))
            g.drawRoundedRect(box, 8, 8)
            g.setPen(with_alpha(p.text, self._t))
            g.drawText(box, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
        # outline of the triangle
        g.setPen(QPen(theme.c("muted"), 1.2))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawPolygon(self._poly([(0, 0), (1, 0), (0, 1)], r))
        # SMAA weight cloud
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(with_alpha(p.text, 0.22 if p.name == "light" else 0.30))
        for x, y in self.cloud:
            g.drawEllipse(self._px(float(x), float(y), r), 1.7, 1.7)
        # the company's weights
        d = self._dot.at(self._t)
        c = self._px(float(d[0]), float(d[1]), r)
        glow = QRadialGradient(c, 24)
        glow.setColorAt(0, with_alpha(RED, 0.35))
        glow.setColorAt(1, with_alpha(RED, 0.0))
        g.setBrush(QBrush(glow))
        g.drawEllipse(c, 24, 24)
        g.setBrush(QColor("#FFFFFF"))
        g.drawEllipse(c, 10.5, 10.5)
        g.setBrush(QColor(RED))
        g.drawEllipse(c, 7.5, 7.5)
        if self.you:
            g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold))
            g.setPen(QColor(RED))
            g.drawText(QRectF(c.x() + 14, c.y() - 22, 120, 16), Qt.AlignmentFlag.AlignLeft, self.you)
        # axis titles
        g.setFont(theme.ui_font(9))
        g.setPen(theme.c("text"))
        g.drawText(QRectF(r.left(), r.bottom() + 22, r.width(), 18), Qt.AlignmentFlag.AlignCenter, self.axis[0] + "  →")
        g.save()
        g.translate(r.left() - 50, r.center().y())
        g.rotate(-90)
        g.drawText(QRectF(-r.height() / 2, -9, r.height(), 18), Qt.AlignmentFlag.AlignCenter, self.axis[1] + "  →")
        g.restore()
        g.end()

    def _label_point(self, poly, dot: QPointF, r: QRectF) -> QPointF:
        """The centroid, or, if the red dot sits there, the point of the region farthest from the dot
        among a few candidates between the centroid and the vertices."""
        cx = sum(a for a, _ in poly) / len(poly)
        cy = sum(b for _, b in poly) / len(poly)
        best = self._px(cx, cy, r)
        if math.hypot(best.x() - dot.x(), best.y() - dot.y()) > 60:
            return best
        cands = [best] + [self._px(cx + (a - cx) * 0.6, cy + (b - cy) * 0.6, r) for a, b in poly]
        return max(cands, key=lambda q: math.hypot(q.x() - dot.x(), q.y() - dot.y()))

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        r = self._rect()
        x = (e.position().x() - r.left()) / r.width()
        y = (r.bottom() - e.position().y()) / r.height()
        if x < 0 or y < 0 or x + y > 1:
            QToolTip.hideText()
            return
        for i, poly in enumerate(self.regions):
            if poly and self._poly(poly, r).containsPoint(e.position(), Qt.FillRule.OddEvenFill):
                QToolTip.showText(e.globalPosition().toPoint(),
                                  f"{self.axis[0]}: {pct(x)} · {self.axis[1]}: {pct(y)}<br>→ <b>{self.names[i]}</b>", self)
                return


def _area(poly) -> float:
    s = 0.0
    for k in range(len(poly)):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2
