"""Decision graphics drawn with QPainter (decision 0010 interface).

- `RankHeatmap`: SMAA rank-acceptability matrix — options × ranks, each cell the share of futures in
  which the option takes that rank (one hue, darker = more often). The recommended option has a red
  outline; "do nothing" is marked as the reference with a dashed outline.
- `PriorityMap`: which option comes first for every possible split of weight between two criteria
  families (the others keep their share of what is left, in the company's proportions). The company's
  weights are a red dot; the cloud of grey points shows the weights SMAA samples around it.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import num, pct
from . import anim, theme


def mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    t = min(max(t, 0.0), 1.0)
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t), int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t))


def ink_on(c: QColor) -> QColor:
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("#FFFFFF") if lum < 140 else QColor("#13283A")


RED = "#D23B2E"


class RankHeatmap(QWidget):
    TOP, ROW, KEY = 34, 34, 30

    def __init__(self):
        super().__init__()
        self.names: list[str] = []
        self.matrix = np.zeros((0, 0))
        self.expected: list[float] = []
        self.best = -1
        self.reference = -1
        self.labels = ("", "", "", "")     # rank header format, expected-rank header, recommended, reference
        self._t = 1.0
        self.setMinimumHeight(120)

    def set_data(self, names, matrix, expected, best, reference, labels) -> None:
        self.names, self.matrix = list(names), np.asarray(matrix, float)
        self.expected, self.best, self.reference, self.labels = list(expected), best, reference, labels
        self.setMinimumHeight(self.TOP + self.ROW * len(self.names) + self.KEY + 8)
        self._t = 0.0
        anim.tween(self, 0.0, 1.0, self._frame, ms=450)

    def _frame(self, t: float) -> None:
        self._t = t
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.names:
            return
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        n_r = self.matrix.shape[1]
        f = QFont(self.font())
        f.setPointSizeF(9)
        g.setFont(f)
        fm = QFontMetricsF(f)
        # label column fits the longest name (up to 40 % of the width; longer names are elided in the middle)
        left = min(max(fm.horizontalAdvance(n) for n in self.names) + 18, self.width() * 0.4)
        right = max(fm.horizontalAdvance(self.labels[1]) + 16, 70)
        cw = max((self.width() - left - right) / max(n_r, 1), 30)
        g.setPen(QColor(p.muted))
        for r in range(n_r):
            g.drawText(QRectF(left + r * cw, 0, cw, self.TOP - 6),
                       Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, self.labels[0].format(r=r + 1))
        g.drawText(QRectF(left + n_r * cw, 0, right, self.TOP - 6),
                   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, self.labels[1])
        for i, name in enumerate(self.names):
            y = self.TOP + i * self.ROW
            g.setPen(QColor(RED) if i == self.best else QColor(p.text))
            g.drawText(QRectF(0, y, left - 12, self.ROW), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(name, Qt.TextElideMode.ElideMiddle, left - 14))
            for r in range(n_r):
                v = float(self.matrix[i, r]) * self._t
                c = mix(p.panel_alt, p.accent, v ** 0.6)
                cell = QRectF(left + r * cw + 1.5, y + 1.5, cw - 3, self.ROW - 3)
                g.setPen(Qt.PenStyle.NoPen)
                g.setBrush(c)
                g.drawRoundedRect(cell, 3, 3)
                if self.matrix[i, r] >= 0.005:
                    g.setPen(ink_on(c))
                    g.drawText(cell, Qt.AlignmentFlag.AlignCenter, pct(self.matrix[i, r]))
            g.setPen(QColor(p.text))
            g.drawText(QRectF(left + n_r * cw, y, right, self.ROW), Qt.AlignmentFlag.AlignCenter,
                       num(self.expected[i], 1))
            if i in (self.best, self.reference):
                g.setPen(self._outline(i, p))
                g.setBrush(Qt.BrushStyle.NoBrush)
                g.drawRoundedRect(QRectF(left, y + 0.5, n_r * cw, self.ROW - 1), 4, 4)
        # key for the two outlines
        y = self.TOP + len(self.names) * self.ROW + 10
        x = left
        g.setBrush(Qt.BrushStyle.NoBrush)
        for i, text in ((self.best, self.labels[2]), (self.reference, self.labels[3])):
            if i < 0:
                continue
            g.setPen(self._outline(i, p))
            g.drawRoundedRect(QRectF(x, y + 3, 26, 13), 3, 3)
            g.setPen(QColor(p.muted))
            w = fm.horizontalAdvance(text)
            g.drawText(QRectF(x + 34, y, w + 4, 20), Qt.AlignmentFlag.AlignVCenter, text)
            x += 34 + w + 28
        g.end()

    def _outline(self, i: int, p) -> QPen:
        pen = QPen(QColor(RED if i == self.best else p.muted), 2.2 if i == self.best else 1.4)
        if i == self.reference and i != self.best:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen


class PriorityMap(QWidget):
    """Winner map over two family weights (x, y ∈ [0, 1], x + y ≤ 1)."""

    hovered = Signal(str)

    def __init__(self):
        super().__init__()
        self.grid = np.zeros((0, 0), int)       # winner index per cell, -1 outside the triangle
        self.names: list[str] = []
        self.colors: list[str] = []
        self.dot = (0.0, 0.0)
        self._shown = (0.0, 0.0)
        self.cloud = np.zeros((0, 2))
        self.axis = ("", "")
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)

    def set_data(self, grid, names, colors, dot, cloud, axis) -> None:
        self.grid, self.names, self.colors = np.asarray(grid), list(names), list(colors)
        self.cloud, self.axis = np.asarray(cloud), axis
        start = self._shown
        self.dot = dot
        anim.tween(self, 0.0, 1.0, lambda t: self._move(start, dot, t), ms=400)

    def _move(self, a, b, t) -> None:
        self._shown = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        self.update()

    def _plot_rect(self) -> QRectF:
        side = min(self.width() - 70, self.height() - 60)
        return QRectF(56, 12, side, side)

    def _to_px(self, x: float, y: float, r: QRectF) -> QPointF:
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if self.grid.size == 0:
            return
        p = theme.current()
        g = QPainter(self)
        r = self._plot_rect()
        n = self.grid.shape[0]
        cell = r.width() / n
        g.setPen(Qt.PenStyle.NoPen)
        for ix in range(n):
            for iy in range(n):
                w = int(self.grid[ix, iy])
                if w < 0:
                    continue
                g.setBrush(QColor(self.colors[w]))
                g.drawRect(QRectF(r.left() + ix * cell, r.bottom() - (iy + 1) * cell, cell + 0.6, cell + 0.6))
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        # SMAA weight cloud and the company's weights
        g.setBrush(QColor(255, 255, 255, 70) if p.name == "dark" else QColor(19, 40, 58, 45))
        for x, y in self.cloud:
            g.drawEllipse(self._to_px(float(x), float(y), r), 1.6, 1.6)
        c = self._to_px(*self._shown, r)
        g.setBrush(QColor(RED))
        g.setPen(QPen(QColor("#FFFFFF"), 2))
        g.drawEllipse(c, 7, 7)
        # axes
        g.setPen(QPen(QColor(p.muted), 1))
        g.drawLine(r.bottomLeft(), r.bottomRight())
        g.drawLine(r.bottomLeft(), r.topLeft())
        g.drawLine(r.bottomRight(), r.topLeft())
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        g.setFont(f)
        for k in range(0, 101, 25):
            t = k / 100
            pt = self._to_px(t, 0, r)
            g.drawText(QRectF(pt.x() - 20, r.bottom() + 4, 40, 16), Qt.AlignmentFlag.AlignCenter, f"{k}%")
            pt = self._to_px(0, t, r)
            g.drawText(QRectF(r.left() - 46, pt.y() - 8, 40, 16), Qt.AlignmentFlag.AlignRight, f"{k}%")
        g.setPen(QColor(p.text))
        g.drawText(QRectF(r.left(), r.bottom() + 20, r.width(), 18), Qt.AlignmentFlag.AlignCenter, self.axis[0])
        g.save()
        g.translate(12, r.center().y())
        g.rotate(-90)
        g.drawText(QRectF(-r.height() / 2, -10, r.height(), 18), Qt.AlignmentFlag.AlignCenter, self.axis[1])
        g.restore()
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        r = self._plot_rect()
        if self.grid.size == 0 or not r.contains(e.position()):
            self.setToolTip("")
            return
        n = self.grid.shape[0]
        ix = int((e.position().x() - r.left()) / r.width() * n)
        iy = int((r.bottom() - e.position().y()) / r.height() * n)
        if 0 <= ix < n and 0 <= iy < n and self.grid[ix, iy] >= 0:
            x, y = (ix + 0.5) / n, (iy + 0.5) / n
            self.setToolTip(f"{self.axis[0]}: {pct(x)} · {self.axis[1]}: {pct(y)}\n→ {self.names[self.grid[ix, iy]]}")
