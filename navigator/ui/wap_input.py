"""Inputs for WAP, the simple weighting method of step 4 (decision 0016).

The company puts the items in order with ▲ ▼ and, between every two neighbours, says in words how much
more the upper one matters: the same, a little, clearly, much or very much more. Each word starts a range
of "z times as important" that the range slider can narrow or widen. Next to every item a bar shows the
range its weight can take under those answers and the working value (the barycentre); the narrower the
ranges, the more stable the weights (ASI).
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..engine.mcda import wap as WAP
from ..i18n import num, pct, tr
from . import theme
from .charts import AnimatedChart, Morph
from .maps import mix
from .widgets import label

GAPS = ("same", *WAP.LEVELS)          # the words between two neighbours
STEP = 0.05                            # z snaps to this


def z_text(z: tuple[float, float]) -> str:
    a, b = z
    return f"×{num(a, 2)}" if abs(b - a) < 1e-9 else f"×{num(a, 2)}–{num(b, 2)}"


def level_of(z: tuple[float, float]) -> str:
    """The word whose starting range holds the geometric middle of z."""
    mid = math.sqrt(z[0] * z[1])
    return next((k for k, (_a, b) in WAP.LEVELS.items() if mid <= b), "very")


class ZRange(QWidget):
    """Two handles on a log scale from ×1 to ×Z_MAX: the range of "how many times as important"."""

    changed = Signal()
    PAD, TEXT = 9, 92

    def __init__(self):
        super().__init__()
        self.z = WAP.LEVELS["clearly"]
        self._drag: int | None = None
        self.setMinimumHeight(24)
        self.setMinimumWidth(170)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(260, 24)

    def _track(self) -> tuple[float, float]:
        return self.PAD, self.width() - self.TEXT - self.PAD

    def _x(self, z: float) -> float:
        a, b = self._track()
        return a + (b - a) * math.log(z) / math.log(WAP.Z_MAX)

    def _z(self, x: float) -> float:
        a, b = self._track()
        t = min(max((x - a) / max(b - a, 1), 0), 1)
        return round(math.exp(t * math.log(WAP.Z_MAX)) / STEP) * STEP

    def set_z(self, z: tuple[float, float], emit: bool = False) -> None:
        a, b = sorted((max(1.0, float(z[0])), min(WAP.Z_MAX, float(z[1]))))
        self.z = (round(a, 4), round(b, 4))
        self.setToolTip(tr("pri.wap.z_tip", lo=num(self.z[0], 2), hi=num(self.z[1], 2)))
        self.update()
        if emit:
            self.changed.emit()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        a, b = self._track()
        cy = self.height() / 2
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(theme.c("panel_alt"))
        g.drawRoundedRect(QRectF(a, cy - 3, b - a, 6), 3, 3)
        g.setPen(QPen(theme.c("grid"), 1))
        for t in (1, 2, 3, 4, 5, 6):                      # light ticks at ×1 … ×6
            x = self._x(t)
            g.drawLine(int(x), int(cy + 5), int(x), int(cy + 8))
        x0, x1 = self._x(self.z[0]), self._x(self.z[1])
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(mix(p.accent, p.panel, 0.35))
        g.drawRoundedRect(QRectF(x0, cy - 3, max(x1 - x0, 2), 6), 3, 3)
        for x in (x0, x1):
            g.setBrush(QColor(p.accent))
            g.setPen(QPen(theme.c("panel"), 2))
            g.drawEllipse(QRectF(x - 6, cy - 6, 12, 12))
        g.setPen(theme.c("text"))
        g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold))
        g.drawText(QRectF(b + self.PAD + 4, 0, self.TEXT - 4, self.height()), Qt.AlignmentFlag.AlignVCenter,
                   z_text(self.z))
        g.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt API
        x = e.position().x()
        d0, d1 = abs(x - self._x(self.z[0])), abs(x - self._x(self.z[1]))
        self._drag = 0 if d0 < d1 or (d0 == d1 and x < self._x(self.z[0])) else 1
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if self._drag is None:
            return
        z = max(1.0, min(WAP.Z_MAX, self._z(e.position().x())))
        lo, hi = self.z
        new = (min(z, hi), hi) if self._drag == 0 else (lo, max(z, lo))
        if new != self.z:
            self.set_z(new, emit=True)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802 - Qt API
        self._drag = None


class RangeBar(AnimatedChart):
    """The range a weight can take (band) and its working value (dot), with the percentage."""

    TEXT = 50

    def __init__(self):
        super().__init__(22)
        self.setMinimumWidth(130)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._v = Morph()
        self.top = 1.0
        self.emph = False

    def sizeHint(self) -> QSize:
        return QSize(170, 22)

    def set_value(self, lo: float, hi: float, mid: float, top: float, emph: bool = False) -> None:
        self.emph, self.top = emph, max(top, 1e-6)
        self._v.set([lo, hi, mid], self._t)
        self.setToolTip(tr("pri.wap.bar_tip", lo=pct(lo, 1), hi=pct(hi, 1), mid=pct(mid, 1)))
        self._start()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        v = self._v.at(self._t)
        if v is None:
            return
        lo, hi, mid = (min(max(x / self.top, 0), 1) for x in v)
        g = self.painter()
        p = theme.current()
        w = self.width() - self.TEXT
        cy = self.height() / 2
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(theme.c("panel_alt"))
        g.drawRoundedRect(QRectF(0, cy - 4, w, 8), 4, 4)
        g.setBrush(mix(p.accent, p.panel, 0.55))
        g.drawRoundedRect(QRectF(w * lo, cy - 4, max(w * (hi - lo), 3), 8), 4, 4)
        g.setBrush(QColor(p.accent))
        g.setPen(QPen(theme.c("panel"), 1.5))
        g.drawEllipse(QRectF(w * mid - 5, cy - 5, 10, 10))
        g.setPen(theme.c("text") if self.emph else theme.c("muted"))
        g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold if self.emph else QFont.Weight.Normal))
        g.drawText(QRectF(w + 6, 0, self.TEXT - 6, self.height()), Qt.AlignmentFlag.AlignVCenter,
                   pct(float(self._v.new[2]), 1))
        g.end()


class Gap(QWidget):
    """Between two neighbours: how much more the upper one matters (a word, then the range)."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(34, 0, 0, 0)
        h.setSpacing(0)
        self.arrow = label("↑", "Faint")
        self.arrow.setFixedWidth(16)
        h.addWidget(self.arrow)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for k in GAPS:
            b = QPushButton()
            b.setObjectName("SegmentSmall")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=k: self.pick(k))
            self.group.addButton(b)
            h.addWidget(b)
            self.buttons[k] = b
        h.addSpacing(12)
        self.range = ZRange()
        self.range.changed.connect(self._dragged)
        sp = self.range.sizePolicy()
        sp.setRetainSizeWhenHidden(True)                  # the words keep their size on "same"
        self.range.setSizePolicy(sp)
        h.addWidget(self.range, 1)
        self.level = "same"
        self.pick("same", emit=False)
        self.retranslate()

    def pick(self, k: str, emit: bool = True) -> None:
        self.level = k
        for key, b in self.buttons.items():
            b.setChecked(key == k)
        if k != "same":
            self.range.set_z(WAP.LEVELS[k])
        self.range.setVisible(k != "same")
        if emit:
            self.changed.emit()

    def _dragged(self) -> None:
        self.level = level_of(self.range.z)
        for key, b in self.buttons.items():
            b.setChecked(key == self.level)
        self.changed.emit()

    def z(self) -> tuple[float, float] | None:
        return None if self.level == "same" else self.range.z

    def set_state(self, level: str, z=None) -> None:
        level = level if level in GAPS else "same"
        self.pick(level, emit=False)
        if level != "same" and z:
            self.range.set_z((float(z[0]), float(z[1])))

    def retranslate(self) -> None:
        bold = QFontMetricsF(theme.ui_font(8, QFont.Weight.Bold))
        for k, b in self.buttons.items():
            b.setText(tr(f"pri.wap.gap.{k}"))
            b.setMinimumWidth(int(bold.horizontalAdvance(b.text())) + 24)   # room for the bold checked state
            b.setToolTip(tr(f"pri.wap.gap_tip.{k}") if k == "same" else
                         tr("pri.wap.gap_tip", z=z_text(WAP.LEVELS[k])))
        self.arrow.setToolTip(tr("pri.wap.gap_q"))
        self.range.set_z(self.range.z)


class Row(QFrame):
    """One place in the order: its rank, the item there, ▲ ▼ and the weight range."""

    def __init__(self, pos: int, move):
        super().__init__()
        self.setObjectName("WapRow")
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 3, 8, 3)
        h.setSpacing(8)
        self.rank = label("", "WapRank")
        self.rank.setFixedWidth(26)
        self.rank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.rank)
        self.name = label("", "JudgeName")
        h.addWidget(self.name, 1)
        self.up, self.down = QToolButton(), QToolButton()
        for b, t, d in ((self.up, "▲", -1), (self.down, "▼", 1)):
            b.setObjectName("WapMove")
            b.setText(t)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, d=d: move(pos, d))
            h.addWidget(b)
        self.bar = RangeBar()
        h.addWidget(self.bar, 1)


class WapBlock(QWidget):
    """The items in order of importance with the answers between neighbours (positions keep their
    answers when items move)."""

    changed = Signal()

    def __init__(self, items: list[str], name_of):
        super().__init__()
        self.items, self.name_of = items, name_of
        self.order = list(items)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self.how = label("", "Faint", wrap=True)
        v.addWidget(self.how)
        self.rows: list[Row] = []
        self.gaps: list[Gap] = []
        for i in range(len(items)):
            if i:
                gp = Gap()
                gp.changed.connect(self._changed)
                self.gaps.append(gp)
                v.addWidget(gp)
            r = Row(i, self.move)
            self.rows.append(r)
            v.addWidget(r)
        self.tips: dict[str, str] = {}
        self.retranslate()

    def _changed(self) -> None:
        self._layout()
        self.changed.emit()

    def move(self, pos: int, d: int) -> None:
        k = pos + d
        if 0 <= k < len(self.order):
            self.order[pos], self.order[k] = self.order[k], self.order[pos]
            self._changed()

    def classes(self) -> list[list[int]]:
        idx = [self.items.index(k) for k in self.order]
        return WAP.classes_from_order(idx, [None if g.level == "same" else g.level for g in self.gaps])

    def result(self) -> WAP.WapResult:
        zs = [g.z() for g in self.gaps if g.z() is not None]
        return WAP.wap(len(self.items), self.classes(), zs)

    def _layout(self) -> None:
        rank, n = 1, len(self.order)
        for i, (r, k) in enumerate(zip(self.rows, self.order, strict=True)):
            if i and self.gaps[i - 1].level != "same":
                rank = i + 1
            tied = (i and self.gaps[i - 1].level == "same") or (i < n - 1 and self.gaps[i].level == "same")
            r.rank.setText(f"={rank}" if tied else str(rank))
            r.name.setText(self.name_of(k))
            r.name.setToolTip(self.tips.get(k, ""))
            r.up.setEnabled(i > 0)
            r.down.setEnabled(i < n - 1)

    def set_weights(self, res: WAP.WapResult) -> None:
        top = float(np.max(res.hi)) * 1.08 if len(res.hi) else 1.0
        best = int(np.argmax(res.weights))
        for r, k in zip(self.rows, self.order, strict=True):
            i = self.items.index(k)
            r.bar.set_value(float(res.lo[i]), float(res.hi[i]), float(res.weights[i]), top, i == best)

    def set_tips(self, tips: dict[str, str]) -> None:
        self.tips = dict(tips)
        self._layout()

    def reset(self, emit: bool = True) -> None:
        """Back to the start: the original order, all equally important."""
        self.order = list(self.items)
        for g in self.gaps:
            g.set_state("same")
        self._layout()
        if emit:
            self.changed.emit()

    def snapshot(self) -> dict:
        return {"order": list(self.order),
                "gaps": [{"level": g.level, "z": list(g.range.z)} for g in self.gaps]}

    def restore(self, d: dict | None) -> None:
        d = d or {}
        order = [k for k in d.get("order", []) if k in self.items]
        self.order = order + [k for k in self.items if k not in order] if order else list(self.items)
        gaps = d.get("gaps", [])
        for i, g in enumerate(self.gaps):
            s = gaps[i] if i < len(gaps) else {}
            g.set_state(s.get("level", "same"), s.get("z"))
        self._layout()

    def retranslate(self) -> None:
        self.how.setText(tr("pri.wap.how"))
        for g in self.gaps:
            g.retranslate()
        for r in self.rows:
            r.up.setToolTip(tr("pri.wap.up"))
            r.down.setToolTip(tr("pri.wap.down"))
        self._layout()


class MethodChooser(QWidget):
    """Three cards, the simple method first; nothing else of step 4 shows until one is picked."""

    picked = Signal(str)

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        self.cards: dict[str, tuple] = {}
        for k in ("wap", "bwm", "ahp"):
            b = QPushButton()
            b.setObjectName("MethodCard" if k != "wap" else "MethodCardMain")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(190)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            b.clicked.connect(lambda _=False, k=k: self.picked.emit(k))
            v = QVBoxLayout(b)
            v.setContentsMargins(18, 16, 18, 16)
            v.setSpacing(6)
            tag = label("", "MethodTagMain" if k == "wap" else "MethodTag")
            title = label("", "MethodTitle", wrap=True)
            text = label("", "MethodText", wrap=True)
            meta = label("", "Faint", wrap=True)
            for w in (tag, title, text):
                w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                v.addWidget(w)
            v.addStretch(1)
            meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            v.addWidget(meta)
            h.addWidget(b, 1)
            self.cards[k] = (b, tag, title, text, meta)
        self.retranslate()

    def retranslate(self) -> None:
        for k, (_b, tag, title, text, meta) in self.cards.items():
            tag.setText(theme.upper(tr("pri.choose.easy" if k == "wap" else "pri.choose.advanced")))
            title.setText(tr(f"pri.method.{k}"))
            text.setText(tr(f"pri.choose.{k}"))
            meta.setText(tr(f"pri.choose.{k}.meta"))
