"""Inputs for the weighting methods of step 4 (decision 0013): judgements are clicked, not dragged.

- `ClickScale`: nine cells 1–9; a click picks the value, the cells up to it fill in, and a short word
  says what it means (equal … absolute). Hover shows the full meaning.
- `WeightBar`: the resulting weight of one item, easing to its new value.
- `PairMatrix`: the AHP comparison matrix. A click on a cell opens the 17 Saaty judgements for that
  pair; the mirror cell shows the reciprocal; cells that disagree with the other answers are outlined.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QMenu, QSizePolicy, QToolTip, QWidget

from ..i18n import pct, tr
from . import theme
from .charts import AnimatedChart, Morph
from .maps import mix


class ClickScale(QWidget):
    """A 1–9 judgement picked with one click. `fixed` shows a dash and takes no clicks."""

    changed = Signal()
    CELL, WORD = 21, 88

    def __init__(self, value: int = 2):
        super().__init__()
        self._v = int(value)
        self._hover: int | None = None
        self.fixed = False
        self.setMouseTracking(True)
        self.setMinimumHeight(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(self.CELL * 9 + self.WORD, 26)

    def minimumSizeHint(self) -> QSize:
        return QSize(16 * 9 + 50, 26)

    def value(self) -> int:
        return self._v

    def set_value(self, v: int, emit: bool = False) -> None:
        self._v = max(1, min(9, int(v)))
        self.update()
        if emit:
            self.changed.emit()

    def set_fixed(self, fixed: bool, shown: int | None = None) -> None:
        self.fixed = fixed
        self._shown = shown
        self.setCursor(Qt.CursorShape.ArrowCursor if fixed else Qt.CursorShape.PointingHandCursor)
        self.update()

    def _cell_w(self) -> float:
        return max(min((self.width() - self.WORD) / 9, 26), 14)

    def _cell_at(self, x: float) -> int | None:
        k = int(x // self._cell_w()) + 1
        return k if 1 <= k <= 9 else None

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        cw = self._cell_w()
        h = self.height()
        g.setFont(theme.ui_font(8))
        if self.fixed:
            shown = getattr(self, "_shown", None)
            g.setPen(theme.c("faint"))
            txt = "—" if shown is None else f"= {shown} · {tr(f'scale.short.{shown}')}"
            g.drawText(QRectF(4, 0, self.width() - 4, h), Qt.AlignmentFlag.AlignVCenter, txt)
            g.end()
            return
        for k in range(1, 10):
            r = QRectF((k - 1) * cw + 1, 3, cw - 2, h - 6)
            on = k <= self._v
            if on:
                col = mix(mix(p.accent, p.panel, 0.75), p.accent, (k - 1) / 8)
                g.setBrush(col)
                g.setPen(Qt.PenStyle.NoPen)
            else:
                g.setBrush(theme.c("panel"))
                g.setPen(QPen(theme.c("border"), 1))
            if k == self._hover:
                g.setPen(QPen(theme.c("accent"), 1.4))
            g.drawRoundedRect(r, 3, 3)
            if k == self._v or k == self._hover:
                g.setPen(QColor(p.accent_text) if on and k > 3 else theme.c("text"))
                g.setFont(theme.ui_font(8, QFont.Weight.DemiBold))
                g.drawText(r, Qt.AlignmentFlag.AlignCenter, str(k))
                g.setFont(theme.ui_font(8))
        g.setPen(theme.c("muted"))
        g.drawText(QRectF(9 * cw + 6, 0, self.width() - 9 * cw - 6, h), Qt.AlignmentFlag.AlignVCenter,
                   tr(f"scale.short.{self._v}"))
        g.end()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if self.fixed:
            return
        k = self._cell_at(e.position().x())
        if k != self._hover:
            self._hover = k
            self.update()
            if k is not None:
                QToolTip.showText(e.globalPosition().toPoint(), f"{k} · {tr(f'scale.{k}')}", self)

    def leaveEvent(self, _e) -> None:  # noqa: N802 - Qt API
        self._hover = None
        self.update()

    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt API
        if self.fixed:
            return
        k = self._cell_at(e.position().x())
        if k is not None and k != self._v:
            self.set_value(k, emit=True)


class WeightBar(AnimatedChart):
    """One weight as a short bar with its percentage; eases to new values."""

    def __init__(self):
        super().__init__(22)
        self.setMinimumWidth(110)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._w = Morph()
        self.emph = False

    def sizeHint(self) -> QSize:
        return QSize(130, 22)

    def set_value(self, w: float, emph: bool = False) -> None:
        self.emph = emph
        self._w.set([float(w)], self._t)
        self._start()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        v = self._w.at(self._t)
        if v is None:
            return
        g = self.painter()
        p = theme.current()
        track = QRectF(0, 7, self.width() - 46, 8)
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(theme.c("panel_alt"))
        g.drawRoundedRect(track, 4, 4)
        g.setBrush(QColor(p.accent))
        g.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * min(max(v[0], 0), 1), 8), 4, 4)
        g.setPen(theme.c("text") if self.emph else theme.c("muted"))
        g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold if self.emph else QFont.Weight.Normal))
        g.drawText(QRectF(track.right() + 4, 0, 44, self.height()), Qt.AlignmentFlag.AlignVCenter,
                   pct(float(self._w.new[0]), 1))
        g.end()


def ratio(v: int) -> float:
    """Stored judgement v ∈ [−8, 8] → a_ij: v < 0 means the first item matters more (1 − v times)."""
    return float(1 - v) if v <= 0 else 1.0 / (1 + v)


def ratio_text(v: int) -> str:
    return str(1 - v) if v <= 0 else f"1/{1 + v}"


class PairMatrix(QWidget):
    """AHP matrix: upper cells are the answers, lower cells their reciprocals, plus a weight column."""

    changed = Signal()
    HEAD, CELL_H = 30, 36

    def __init__(self, items: list[str], name_of):
        super().__init__()
        self.items = items
        self.name_of = name_of
        self.values: dict[tuple[int, int], int] = {(i, j): 0 for i in range(len(items))
                                                   for j in range(i + 1, len(items))}
        self.weights: np.ndarray | None = None
        self.tips: dict[str, str] = {}
        self._hover: tuple[int, int] | None = None
        self.setMouseTracking(True)
        n = len(items)
        self.setMinimumHeight(self.HEAD + self.CELL_H * n + 6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(560, self.HEAD + self.CELL_H * len(self.items) + 6)

    def _geom(self):
        g_font = theme.ui_font(9)
        fm = QFontMetricsF(g_font)
        left = min(max(fm.horizontalAdvance(self.name_of(k)) for k in self.items) + 16, self.width() * 0.3)
        n = len(self.items)
        wcol = 110
        cw = max(min((self.width() - left - wcol - 8) / n, 92), 44)
        return left, cw, wcol

    def cell_rect(self, i: int, j: int) -> QRectF:
        left, cw, _ = self._geom()
        return QRectF(left + j * cw + 1.5, self.HEAD + i * self.CELL_H + 1.5, cw - 3, self.CELL_H - 3)

    def set_value(self, pair: tuple[int, int], v: int, emit: bool = True) -> None:
        self.values[pair] = max(-8, min(8, int(v)))
        self.update()
        if emit:
            self.changed.emit()

    def set_weights(self, w) -> None:
        self.weights = np.asarray(w, float)
        self.update()

    def deviation(self, i: int, j: int) -> float:
        """How far the answer for (i, j) is from what the weights imply, in Saaty steps (log scale)."""
        if self.weights is None:
            return 0.0
        a = ratio(self.values[(i, j)])
        implied = self.weights[i] / max(self.weights[j], 1e-12)
        return abs(math.log(a) - math.log(implied))

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, cw, wcol = self._geom()
        n = len(self.items)
        fm = QFontMetricsF(theme.ui_font(8.5))
        # column heads
        g.setFont(theme.ui_font(8.5))
        g.setPen(theme.c("muted"))
        for j, k in enumerate(self.items):
            g.drawText(QRectF(left + j * cw, 0, cw, self.HEAD - 6), Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                       fm.elidedText(self.name_of(k), Qt.TextElideMode.ElideRight, cw - 4))
        g.drawText(QRectF(left + n * cw + 8, 0, wcol, self.HEAD - 6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                   tr("pri.col.weight"))
        warm, cool = QColor(p.accent), QColor(p.ets)
        for i, ki in enumerate(self.items):
            y = self.HEAD + i * self.CELL_H
            g.setFont(theme.ui_font(9))
            g.setPen(theme.c("text"))
            g.drawText(QRectF(0, y, left - 10, self.CELL_H), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetricsF(theme.ui_font(9)).elidedText(self.name_of(ki), Qt.TextElideMode.ElideRight, left - 12))
            for j in range(n):
                r = self.cell_rect(i, j)
                if i == j:
                    g.setPen(Qt.PenStyle.NoPen)
                    g.setBrush(theme.c("panel_alt"))
                    g.drawRoundedRect(r, 4, 4)
                    g.setPen(theme.c("faint"))
                    g.setFont(theme.ui_font(8.5))
                    g.drawText(r, Qt.AlignmentFlag.AlignCenter, "1")
                    continue
                upper = i < j
                pair = (i, j) if upper else (j, i)
                v = self.values[pair]
                # from the row's point of view: positive strength = row matters more
                s = -v if upper else v
                strength = abs(s) / 8
                base = warm if s > 0 else cool
                fill = mix(p.panel, base, 0.12 + 0.6 * strength) if s != 0 else QColor(p.panel)
                if not upper:
                    fill = mix(fill, p.panel, 0.55)
                g.setBrush(fill)
                g.setPen(QPen(theme.c("border"), 1))
                if self._hover in ((i, j), (j, i)):
                    g.setPen(QPen(theme.c("accent"), 1.6))
                if upper and self.weights is not None and self.deviation(i, j) > math.log(3):
                    g.setPen(QPen(theme.c("warn"), 2.0))
                g.drawRoundedRect(r, 4, 4)
                text = ratio_text(v) if upper else ratio_text(-v)
                g.setFont(theme.ui_font(9.5 if upper else 8.5, QFont.Weight.DemiBold if upper else QFont.Weight.Normal))
                g.setPen(theme.c("text") if upper else theme.c("faint"))
                g.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            if self.weights is not None:
                track = QRectF(left + n * cw + 8, y + self.CELL_H / 2 - 4, wcol - 52, 8)
                g.setPen(Qt.PenStyle.NoPen)
                g.setBrush(theme.c("panel_alt"))
                g.drawRoundedRect(track, 4, 4)
                g.setBrush(warm)
                g.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * float(self.weights[i]), 8), 4, 4)
                g.setPen(theme.c("muted"))
                g.setFont(theme.ui_font(8.5))
                g.drawText(QRectF(track.right() + 4, y, 48, self.CELL_H), Qt.AlignmentFlag.AlignVCenter,
                           pct(float(self.weights[i]), 1))
        g.end()

    def _at(self, pos: QPointF) -> tuple[int, int] | None:
        n = len(self.items)
        for i in range(n):
            for j in range(n):
                if i != j and self.cell_rect(i, j).contains(pos):
                    return i, j
        return None

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        hit = self._at(e.position())
        if hit != self._hover:
            self._hover = hit
            self.update()
        if hit is None:
            left, _cw, _w = self._geom()
            if e.position().x() < left:
                i = int((e.position().y() - self.HEAD) // self.CELL_H)
                if 0 <= i < len(self.items) and self.tips.get(self.items[i]):
                    QToolTip.showText(e.globalPosition().toPoint(), self.tips[self.items[i]], self)
                    return
            QToolTip.hideText()
            return
        i, j = hit
        a, b = (i, j) if i < j else (j, i)
        v = self.values[(a, b)]
        lines = [f"{self.name_of(self.items[i])} : {self.name_of(self.items[j])} = "
                 f"{ratio_text(v) if i < j else ratio_text(-v)}"]
        if self.weights is not None and self.deviation(a, b) > math.log(3):
            implied = self.weights[a] / max(self.weights[b], 1e-12)
            lines.append(tr("pri.ahp.off", v=(f"{implied:.1f}" if implied >= 1 else f"1/{1 / implied:.1f}")))
        QToolTip.showText(e.globalPosition().toPoint(), "<br>".join(lines), self)

    def leaveEvent(self, _e) -> None:  # noqa: N802 - Qt API
        self._hover = None
        self.update()

    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt API
        hit = self._at(e.position())
        if hit is None:
            return
        i, j = hit
        a, b = (i, j) if i < j else (j, i)
        na, nb = self.name_of(self.items[a]), self.name_of(self.items[b])
        menu = QMenu(self)
        current = self.values[(a, b)]
        for v in range(-8, 9):
            n = abs(v) + 1
            if v < 0:
                text = f"{na} · {tr(f'scale.{n}')} ({n})"
            elif v > 0:
                text = f"{nb} · {tr(f'scale.{n}')} ({n})"
            else:
                text = f"{tr('scale.1')} (1)"
            act = menu.addAction(text)
            act.setCheckable(True)
            act.setChecked(v == current)
            act.triggered.connect(lambda _=False, v=v: self.set_value((a, b), v))
            if v in (-1, 0):
                menu.addSeparator()
        menu.exec(e.globalPosition().toPoint())

