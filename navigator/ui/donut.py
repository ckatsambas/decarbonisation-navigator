"""Tilted, exploded donut with depth (decision 0012).

Shares are written next to every slice with a leader line, so the slight 3D tilt never has to carry
the numbers: the reader reads them, the shape only gives the impression. Changing the data morphs the
slices; hovering lifts a slice and shows its figure.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPen, QPolygonF
from PySide6.QtWidgets import QToolTip

from ..i18n import pct
from . import theme
from .charts import AnimatedChart, Morph, with_alpha

TILT = 0.52


def shade(c: QColor, k: float) -> QColor:
    return QColor(int(c.red() * k), int(c.green() * k), int(c.blue() * k), c.alpha())


class Donut3D(AnimatedChart):
    def __init__(self, min_h: int = 360):
        super().__init__(min_h)
        self.names: list[str] = []
        self.colors: list[str] = []
        self.figures: list[str] = []
        self.caption = ""
        self.empty = ""
        self._v = Morph()
        self._hover_slice: int | None = None
        self._geom = (0.0, 0.0, 1.0)

    def set_data(self, items, caption: str = "", empty: str = "") -> None:
        """items: (name, value ≥ 0, colour, figure text for the label)."""
        vals = np.array([max(float(v), 0.0) for _n, v, _c, _f in items], float)
        if [n for n, *_ in items] != self.names:
            self._v.new = None
        self.names = [n for n, *_ in items]
        self.colors = [c for _n, _v, c, _f in items]
        self.figures = [f for *_, f in items]
        self.caption, self.empty = caption, empty
        self._v.set(vals, self._t)
        self._start()

    def _fractions(self) -> tuple[np.ndarray, float]:
        """Current slice fractions and the swept share of the circle (the first appearance sweeps in)."""
        old, new = self._v.old, self._v.new
        if new is None or new.sum() <= 0:
            return np.zeros(0), 0.0
        fn = new / new.sum()
        if old is None or old.sum() <= 0:
            return fn, self._t
        fo = old / old.sum()
        return fo + (fn - fo) * self._t, 1.0

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        g = self.painter()
        p = theme.current()
        if self.caption:
            g.setFont(theme.ui_font(9.5, QFont.Weight.DemiBold))
            g.setPen(theme.c("muted"))
            g.drawText(QRectF(8, 2, self.width() - 16, 20), Qt.AlignmentFlag.AlignLeft, self.caption)
        frac, sweep = self._fractions()
        if not len(frac):
            g.setPen(theme.c("faint"))
            g.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty)
            g.end()
            return
        legend_h = 22 * math.ceil(len(self.names) / max(1, int(self.width() // 200))) + 8
        avail_h = self.height() - 30 - legend_h
        R = min(self.width() * 0.26, avail_h / (2 * TILT) * 0.78, 230)
        depth = R * 0.17
        cx, cy = self.width() / 2, 34 + avail_h / 2 - depth / 2
        self._geom = (cx, cy, R)
        r_in = R * 0.56
        explode = R * 0.07
        a0 = -math.pi / 2
        slices = []
        for i, f in enumerate(frac):
            span = 2 * math.pi * f * sweep
            if span <= 1e-4:
                a0 += span
                continue
            mid = a0 + span / 2
            lift = explode * (1.7 if i == self._hover_slice else 1.0)
            off = QPointF(lift * math.cos(mid), lift * math.sin(mid) * TILT)
            slices.append((i, a0, span, mid, off))
            a0 += span
        # back to front
        slices.sort(key=lambda s: math.sin(s[3]))

        def face(a, span, off, dy=0.0):
            k = max(int(span / (math.pi / 60)), 2)
            ang = np.linspace(a, a + span, k)
            outer = [QPointF(cx + off.x() + R * math.cos(t), cy + off.y() + dy + R * math.sin(t) * TILT) for t in ang]
            inner = [QPointF(cx + off.x() + r_in * math.cos(t), cy + off.y() + dy + r_in * math.sin(t) * TILT)
                     for t in ang[::-1]]
            return QPolygonF(outer + inner)

        for i, a, span, _mid, off in slices:
            col = QColor(self.colors[i])
            g.setPen(Qt.PenStyle.NoPen)
            steps = max(int(depth / 1.5), 2)
            for s in range(steps, 0, -1):
                dy = depth * s / steps
                g.setBrush(shade(col, 0.62 + 0.12 * (1 - s / steps)))
                g.drawPolygon(face(a, span, off, dy))
            g.setBrush(col)
            g.setPen(QPen(with_alpha("#FFFFFF", 0.35), 1))
            g.drawPolygon(face(a, span, off))
        # labels with leader lines, spread so they never overlap
        g.setFont(theme.ui_font(9.5, QFont.Weight.DemiBold))
        fm = QFontMetricsF(g.font())
        sides: dict[int, list] = {-1: [], 1: []}
        for i, _a, span, mid, off in slices:
            side = 1 if math.cos(mid) >= 0 else -1
            anchor = QPointF(cx + off.x() + R * math.cos(mid), cy + off.y() + R * math.sin(mid) * TILT
                             + (depth / 2 if math.sin(mid) > 0 else 0))
            sides[side].append([anchor.y() + math.sin(mid) * 26, i, anchor, mid, span])
        for side, items in sides.items():
            items.sort(key=lambda it: it[0])
            lo_y, hi_y = 46.0, self.height() - legend_h - 22
            if items:
                items[0][0] = max(items[0][0], lo_y)
            for k in range(1, len(items)):
                items[k][0] = max(items[k][0], items[k - 1][0] + 34)
            if items and items[-1][0] > hi_y:
                items[-1][0] = hi_y
                for k in range(len(items) - 2, -1, -1):
                    items[k][0] = min(items[k][0], items[k + 1][0] - 34)
            x_text = cx + side * (R + 44)
            for y, i, anchor, mid, _span in items:
                elbow = QPointF(anchor.x() + math.cos(mid) * 16, y)
                end = QPointF(x_text, y)
                g.setPen(QPen(theme.c("faint"), 1))
                g.drawPolyline(QPolygonF([anchor, elbow, end]))
                g.setPen(QPen(theme.c("muted"), 1))
                g.setBrush(theme.c("muted"))
                g.drawEllipse(anchor, 1.8, 1.8)
                share = float(self._v.new[i] / self._v.new.sum())
                big = pct(share, 1)
                w = max(fm.horizontalAdvance(big), 40)
                rect = QRectF(end.x() + 6 if side > 0 else end.x() - 6 - 220, y - 17, 220, 18)
                align = Qt.AlignmentFlag.AlignLeft if side > 0 else Qt.AlignmentFlag.AlignRight
                g.setFont(theme.ui_font(10.5, QFont.Weight.DemiBold))
                g.setPen(QColor(self.colors[i]) if p.name == "dark" else shade(QColor(self.colors[i]), 0.85))
                g.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, big)
                g.setFont(theme.ui_font(8.5))
                g.setPen(theme.c("muted"))
                sub = QFontMetricsF(g.font()).elidedText(f"{self.names[i]} · {self.figures[i]}" if self.figures[i]
                                                        else self.names[i], Qt.TextElideMode.ElideRight, 220)
                g.drawText(QRectF(rect.x(), y + 1, 220, 16), align | Qt.AlignmentFlag.AlignVCenter, sub)
                del w
                g.setFont(theme.ui_font(9.5, QFont.Weight.DemiBold))
        # legend
        items = [(n, QColor(c), "box") for n, c in zip(self.names, self.colors, strict=True)]
        self.draw_legend(g, items, 16, self.height() - legend_h + 4)
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        frac, sweep = self._fractions()
        if not len(frac):
            return
        cx, cy, R = self._geom
        dx = e.position().x() - cx
        dy = (e.position().y() - cy) / TILT
        rr = math.hypot(dx, dy)
        hit = None
        if R * 0.5 <= rr <= R * 1.15:
            ang = (math.atan2(dy, dx) + math.pi / 2) % (2 * math.pi)
            acc = 0.0
            for i, f in enumerate(frac):
                acc += 2 * math.pi * f * sweep
                if ang <= acc:
                    hit = i
                    break
        if hit != self._hover_slice:
            self._hover_slice = hit
            self.update()
        if hit is not None:
            share = float(self._v.new[hit] / self._v.new.sum())
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"<b>{self.names[hit]}</b><br>{pct(share, 1)}"
                              + (f" · {self.figures[hit]}" if self.figures[hit] else ""), self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, e) -> None:  # noqa: N802 - Qt API
        self._hover_slice = None
        super().leaveEvent(e)
