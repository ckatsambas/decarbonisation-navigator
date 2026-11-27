"""Inputs for WAP, the simple weighting method of step 4 (decision 0016).

One movement only: the items are cards on a ladder and are moved up or down (dragged, or with the small
arrows on each card). Higher = more important; cards on the same row are equally important; every empty
row between two cards makes the difference bigger (none: a little more, one: clearly, two: much, three
or more: very much more). Each word is a WAP range of "z times as important" (`engine.mcda.wap.from_rows`).
The left margin says in words what the ladder means; each card shows its weight and the range it can take.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QToolTip, QVBoxLayout, QWidget

from ..engine.mcda import wap as WAP
from ..i18n import num, pct, tr
from . import theme
from .charts import AnimatedChart, Morph
from .maps import mix
from .widgets import label

LEVEL_OF = {"wap": "beginner", "bwm": "intermediate", "ahp": "advanced"}


class Ladder(AnimatedChart):
    """Cards on rows; drag a card (or click its arrows) to another row."""

    changed = Signal()
    GUTTER, ROW_H, CARD_H, PAD, ARROWS = 150, 44, 36, 8, 18

    def __init__(self, items: list[str], name_of):
        self.items, self.name_of = items, name_of
        self.n_rows = len(items) + 3
        super().__init__(self.PAD * 2 + self.n_rows * self.ROW_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.rows = {k: 0 for k in items}
        self.res: WAP.WapResult | None = None
        self.tips: dict[str, str] = {}
        self._pos = Morph()
        self._drag: tuple[str, float] | None = None          # item, grab offset in y
        self._drag_y = 0.0
        self._hover: str | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(640, self.minimumHeight())

    # ---------------------------------------------------------------- geometry
    def row_top(self, r: int) -> float:
        return self.PAD + r * self.ROW_H

    def row_at(self, y: float) -> int:
        return int(min(max((y - self.PAD) // self.ROW_H, 0), self.n_rows - 1))

    def targets(self) -> np.ndarray:
        """Card rectangles (x, y, w, h) in item order; cards on one row share it."""
        out = np.zeros((len(self.items), 4))
        avail = max(self.width() - self.GUTTER - 4, 120)
        for r in range(self.n_rows):
            here = [k for k in self.items if self.rows[k] == r]
            if not here:
                continue
            gap = 8
            w = min(230.0, (avail - gap * (len(here) - 1)) / len(here))
            y = self.row_top(r) + (self.ROW_H - self.CARD_H) / 2
            for j, k in enumerate(here):
                out[self.items.index(k)] = (self.GUTTER + j * (w + gap), y, w, self.CARD_H)
        return out

    def _rects(self) -> np.ndarray:
        cur = self._pos.at(self._t)
        return self.targets() if cur is None or cur.shape != (len(self.items), 4) else cur

    def _snap(self) -> None:
        t = self.targets()
        self._pos.old, self._pos.new = t, t.copy()
        self._t = 1.0
        self.update()

    def resizeEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(e)
        self._snap()

    # ---------------------------------------------------------------- model
    def place(self, k: str, row: int, emit: bool = True) -> None:
        row = int(min(max(row, 0), self.n_rows - 1))
        if self.rows[k] == row:
            return
        old = self._rects().copy()
        self.rows[k] = row
        self._pos.old, self._pos.new = old, self.targets()
        self._start()
        if emit:
            self.changed.emit()

    def move(self, k: str, d: int) -> None:
        self.place(k, self.rows[k] + d)

    def set_rows(self, rows: dict[str, int]) -> None:
        self.rows = {k: int(min(max(int(rows.get(k, 0)), 0), self.n_rows - 1)) for k in self.items}
        self._snap()

    def set_result(self, res: WAP.WapResult) -> None:
        self.res = res
        self.update()

    # ---------------------------------------------------------------- painting
    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = self.painter()
        w = self.width()
        target_row = self.row_at(self._drag_y + self.CARD_H / 2) if self._drag else None
        for r in range(self.n_rows):                         # rows
            y = self.row_top(r)
            if r == target_row:
                g.setPen(Qt.PenStyle.NoPen)
                g.setBrush(mix(p.accent, p.panel, 0.88))
                g.drawRoundedRect(QRectF(self.GUTTER - 6, y + 1, w - self.GUTTER + 4, self.ROW_H - 2), 6, 6)
            g.setPen(QPen(theme.c("grid"), 1, Qt.PenStyle.DashLine))
            g.drawLine(QPointF(self.GUTTER, y + self.ROW_H / 2), QPointF(w - 4, y + self.ROW_H / 2))
        ax = self.GUTTER - 16                                 # the axis: more important at the top
        g.setPen(QPen(theme.c("border"), 1.4))
        g.drawLine(QPointF(ax, self.PAD + 6), QPointF(ax, self.row_top(self.n_rows) - 6))
        head = QPainterPath(QPointF(ax, self.PAD))
        head.lineTo(ax - 4, self.PAD + 8)
        head.lineTo(ax + 4, self.PAD + 8)
        head.closeSubpath()
        g.fillPath(head, theme.c("border"))
        g.setFont(theme.ui_font(7.5, QFont.Weight.Bold))
        g.setPen(theme.c("faint"))
        right = Qt.AlignmentFlag.AlignRight
        g.drawText(QRectF(0, self.PAD - 2, ax - 8, 16), right | Qt.AlignmentFlag.AlignVCenter,
                   theme.upper(tr("pri.wap.more")))
        g.drawText(QRectF(0, self.row_top(self.n_rows) - 16, ax - 8, 16), right | Qt.AlignmentFlag.AlignVCenter,
                   theme.upper(tr("pri.wap.less")))
        used = sorted(set(self.rows.values()))               # what each step between two classes means
        for a, b in zip(used, used[1:], strict=False):
            word = WAP.GAP_LEVELS[min(b - a - 1, len(WAP.GAP_LEVELS) - 1)]
            ya, yb = self.row_top(a) + self.ROW_H / 2, self.row_top(b) + self.ROW_H / 2
            g.setPen(QPen(QColor(p.accent), 2.2))
            g.drawLine(QPointF(ax, ya + 3), QPointF(ax, yb - 3))
            mid = (ya + yb) / 2
            g.setPen(theme.c("text"))
            g.setFont(theme.ui_font(8, QFont.Weight.DemiBold))
            g.drawText(QRectF(0, mid - 15, ax - 8, 15), right | Qt.AlignmentFlag.AlignBottom, tr(f"pri.wap.gap.{word}"))
            g.setPen(theme.c("faint"))
            g.setFont(theme.ui_font(7.5))
            lo, hi = WAP.LEVELS[word]
            g.drawText(QRectF(0, mid, ax - 8, 14), right | Qt.AlignmentFlag.AlignTop, f"×{num(lo, 1)}–{num(hi, 1)}")
        rects = self._rects()
        dragged = self._drag[0] if self._drag else None
        top = float(np.max(self.res.hi)) if self.res is not None and len(self.res.hi) else 1.0
        best = int(np.argmax(self.res.weights)) if self.res is not None else -1
        for k in [k for k in self.items if k != dragged] + ([dragged] if dragged else []):
            i = self.items.index(k)
            x, y, cw, ch = rects[i]
            if k == dragged:
                y = self._drag_y
            self._card(g, k, i, QRectF(x, y, cw, ch), top, i == best, k == dragged)
        g.end()

    def _card(self, g, k: str, i: int, r: QRectF, top: float, emph: bool, lifted: bool) -> None:
        p = theme.current()
        if lifted:
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(QColor(0, 0, 0, 40))
            g.drawRoundedRect(r.translated(2, 3), 8, 8)
        g.setBrush(theme.c("panel"))
        g.setPen(QPen(QColor(p.accent) if (lifted or k == self._hover) else theme.c("border"), 1.3))
        g.drawRoundedRect(r, 8, 8)
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(QColor(p.accent))
        g.drawRoundedRect(QRectF(r.left(), r.top() + 6, 3, r.height() - 12), 1.5, 1.5)
        inner = r.adjusted(10, 3, -self.ARROWS - 6, -3)
        value = pct(float(self.res.weights[i]), 1) if self.res is not None else ""
        g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold if emph else QFont.Weight.Normal))
        vw = QFontMetricsF(g.font()).horizontalAdvance(value) + 6
        g.setPen(theme.c("text") if emph else theme.c("muted"))
        g.drawText(QRectF(inner.right() - vw, inner.top(), vw, 17), right_v(), value)
        g.setFont(theme.ui_font(9))
        g.setPen(theme.c("text"))
        name = QFontMetricsF(g.font()).elidedText(self.name_of(k), Qt.TextElideMode.ElideRight, inner.width() - vw)
        g.drawText(QRectF(inner.left(), inner.top(), inner.width() - vw, 17), Qt.AlignmentFlag.AlignVCenter, name)
        if self.res is not None and top > 0:                 # the range the weight can take, and its value
            band = QRectF(inner.left(), inner.bottom() - 7, inner.width(), 4)
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(theme.c("panel_alt"))
            g.drawRoundedRect(band, 2, 2)
            lo, hi, mid = (min(float(v) / (top * 1.05), 1)
                           for v in (self.res.lo[i], self.res.hi[i], self.res.weights[i]))
            g.setBrush(mix(p.accent, p.panel, 0.5))
            g.drawRoundedRect(QRectF(band.left() + band.width() * lo, band.top(),
                                     max(band.width() * (hi - lo), 3), 4), 2, 2)
            g.setBrush(QColor(p.accent))
            g.drawEllipse(QPointF(band.left() + band.width() * mid, band.center().y()), 3.2, 3.2)
        ar = QRectF(r.right() - self.ARROWS - 3, r.top() + 3, self.ARROWS, r.height() - 6)
        for up in (True, False):                              # ▲ ▼
            ok = self.rows[k] > 0 if up else self.rows[k] < self.n_rows - 1
            c = QPointF(ar.center().x(), ar.top() + ar.height() * (0.27 if up else 0.73))
            s = -1 if up else 1
            tri = QPainterPath(QPointF(c.x(), c.y() + 3.5 * s))
            tri.lineTo(c.x() - 4.5, c.y() - 2.5 * s)
            tri.lineTo(c.x() + 4.5, c.y() - 2.5 * s)
            tri.closeSubpath()
            g.fillPath(tri, theme.c("muted") if ok else theme.c("grid"))

    # ---------------------------------------------------------------- mouse
    def _hit(self, pos: QPointF) -> tuple[str | None, int]:
        """The card under the mouse and −1 / +1 for its up / down arrow (0 = the card itself)."""
        rects = self._rects()
        for i in range(len(self.items) - 1, -1, -1):
            x, y, w, h = rects[i]
            if QRectF(x, y, w, h).contains(pos):
                if pos.x() >= x + w - self.ARROWS - 6:
                    return self.items[i], (-1 if pos.y() < y + h / 2 else 1)
                return self.items[i], 0
        return None, 0

    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt API
        k, arrow = self._hit(e.position())
        if k is None:
            return
        if arrow:
            self.move(k, arrow)
            return
        y = float(self._rects()[self.items.index(k)][1])
        self._drag = (k, e.position().y() - y)
        self._drag_y = y
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if self._drag is not None:
            self._drag_y = min(max(e.position().y() - self._drag[1], 0), self.height() - self.CARD_H)
            self.update()
            return
        k, arrow = self._hit(e.position())
        if k != self._hover:
            self._hover = k
            self.update()
        self.setCursor(Qt.CursorShape.PointingHandCursor if arrow else Qt.CursorShape.OpenHandCursor)
        if k is not None and self.res is not None:
            i = self.items.index(k)
            tip = f"<b>{self.name_of(k)}</b><br>" + tr("pri.wap.bar_tip", lo=pct(float(self.res.lo[i]), 1),
                                                         hi=pct(float(self.res.hi[i]), 1),
                                                         mid=pct(float(self.res.weights[i]), 1))
            if self.tips.get(k):
                tip += "<br><br>" + self.tips[k]
            QToolTip.showText(e.globalPosition().toPoint(), tip, self)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if self._drag is None:
            return
        k = self._drag[0]
        row = self.row_at(self._drag_y + self.CARD_H / 2)
        old = self._rects().copy()
        old[self.items.index(k), 1] = self._drag_y           # ease on from where the card was dropped
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        moved = row != self.rows[k]
        self.rows[k] = row
        self._pos.old, self._pos.new = old, self.targets()
        self._start()
        if moved:
            self.changed.emit()

    def leaveEvent(self, _e) -> None:  # noqa: N802 - Qt API
        self._hover = None
        self.update()


def right_v():
    return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class WapBlock(QWidget):
    """The ladder with one line of instructions; same interface as the BWM and AHP blocks."""

    changed = Signal()

    def __init__(self, items: list[str], name_of):
        super().__init__()
        self.items = items
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.how = label("", "Faint", wrap=True)
        v.addWidget(self.how)
        self.ladder = Ladder(items, name_of)
        self.ladder.changed.connect(self.changed)
        v.addWidget(self.ladder)
        self.retranslate()

    @property
    def rows(self) -> dict[str, int]:
        return self.ladder.rows

    def place(self, k: str, row: int) -> None:
        self.ladder.place(k, row)

    def move(self, k: str, d: int) -> None:
        self.ladder.move(k, d)

    def result(self) -> WAP.WapResult:
        classes, z = WAP.from_rows([self.ladder.rows[k] for k in self.items])
        return WAP.wap(len(self.items), classes, z)

    def set_weights(self, res: WAP.WapResult) -> None:
        self.ladder.set_result(res)

    def set_tips(self, tips: dict[str, str]) -> None:
        self.ladder.tips = dict(tips)

    def reset(self, emit: bool = True) -> None:
        """Back to the start: every item on the top row, all equally important."""
        self.ladder.set_rows({})
        if emit:
            self.changed.emit()

    def snapshot(self) -> dict:
        return {"rows": dict(self.ladder.rows)}

    def restore(self, d: dict | None) -> None:
        self.ladder.set_rows((d or {}).get("rows", {}))

    def retranslate(self) -> None:
        self.how.setText(tr("pri.wap.how"))
        self.ladder.update()


class MethodChooser(QWidget):
    """Three cards: the method's short name, its full name and who it is for. Nothing else."""

    picked = Signal(str)

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        self.cards: dict[str, tuple] = {}
        for k in ("wap", "bwm", "ahp"):
            b = QPushButton()
            b.setObjectName("MethodCardMain" if k == "wap" else "MethodCard")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(170)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            b.clicked.connect(lambda _=False, k=k: self.picked.emit(k))
            v = QVBoxLayout(b)
            v.setContentsMargins(18, 22, 18, 20)
            v.setSpacing(6)
            short = label(k.upper(), "MethodShort")
            full = label("", "MethodFull", wrap=True)
            level = label("", "MethodLevelMain" if k == "wap" else "MethodLevel")
            v.addWidget(short)
            v.addWidget(full)
            v.addStretch(1)
            v.addWidget(level)
            for w in (short, full, level):
                w.setAlignment(Qt.AlignmentFlag.AlignCenter)
                w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            h.addWidget(b, 1)
            self.cards[k] = (b, short, full, level)
        self.retranslate()

    def retranslate(self) -> None:
        for k, (_b, _short, full, level) in self.cards.items():
            full.setText(tr(f"pri.full.{k}"))
            level.setText(theme.upper(tr(f"pri.level_of.{LEVEL_OF[k]}")))
