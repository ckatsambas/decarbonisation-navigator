"""Route stepper: the project's steps drawn as a voyage line with waypoints."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import tr
from . import theme


class RouteStepper(QWidget):
    """Waypoints for each step. Steps up to `reached` can be clicked; later ones are still uncharted."""

    picked = Signal(int)

    def __init__(self, keys: list[str]):
        super().__init__()
        self.keys = keys
        self.current = 0
        self.reached = 0
        self.setMinimumHeight(74)
        self.setMouseTracking(True)
        self._hover = -1

    def set_state(self, current: int, reached: int) -> None:
        self.current, self.reached = current, max(reached, current)
        self.update()

    def _points(self) -> list[QPointF]:
        n = len(self.keys)
        margin = 70
        span = max(self.width() - 2 * margin, 1)
        return [QPointF(margin + span * i / (n - 1), 26) for i in range(n)]

    def _index_at(self, pos) -> int:
        for i, pt in enumerate(self._points()):
            if abs(pos.x() - pt.x()) < 60 and pos.y() < self.height():
                return i
        return -1

    def mouseMoveEvent(self, e):  # noqa: N802
        i = self._index_at(e.position())
        clickable = 0 <= i <= self.reached and i != self.current
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):  # noqa: N802
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):  # noqa: N802
        i = self._index_at(e.position())
        if 0 <= i <= self.reached:
            self.picked.emit(i)

    def paintEvent(self, event):  # noqa: N802
        p = theme.current()
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        pts = self._points()
        # route line: solid where sailed, dashed where still ahead
        for i in range(len(pts) - 1):
            pen = QPen(QColor(p.accent if i < self.reached else p.border))
            pen.setWidthF(2.4 if i < self.reached else 1.6)
            if i >= self.reached:
                pen.setStyle(Qt.PenStyle.DashLine)
            qp.setPen(pen)
            qp.drawLine(pts[i], pts[i + 1])
        f = QFont(theme.FAMILIES[0])
        f.setFamilies(theme.FAMILIES)
        for i, pt in enumerate(pts):
            done, cur, open_ = i < self.current, i == self.current, i <= self.reached
            if cur:
                qp.setPen(Qt.PenStyle.NoPen)
                qp.setBrush(QColor(p.shallow))
                qp.drawEllipse(pt, 15, 15)
                pen = QPen(QColor(p.accent))
                pen.setWidthF(2.6)
                qp.setPen(pen)
                qp.setBrush(QColor(p.panel))
                qp.drawEllipse(pt, 9, 9)
                # small bow marker: the ship's position on the route
                bow = QPainterPath()
                bow.moveTo(pt.x() + 4.5, pt.y())
                bow.lineTo(pt.x() - 3, pt.y() - 3.6)
                bow.lineTo(pt.x() - 3, pt.y() + 3.6)
                bow.closeSubpath()
                qp.setPen(Qt.PenStyle.NoPen)
                qp.setBrush(QColor(p.accent))
                qp.drawPath(bow)
            else:
                pen = QPen(QColor(p.accent if open_ else p.faint))
                pen.setWidthF(1.8)
                qp.setPen(pen)
                qp.setBrush(QColor(p.accent if done else (p.panel if open_ else p.bg)))
                r = 7.5 if i == self._hover and open_ else 6.5
                qp.drawEllipse(pt, r, r)
            f.setPointSizeF(9.2)
            f.setWeight(QFont.Weight.DemiBold if cur else QFont.Weight.Normal)
            qp.setFont(f)
            qp.setPen(QColor(p.text if cur else (p.muted if open_ else p.faint)))
            label = f"{i + 1}  {tr(self.keys[i])}"
            qp.drawText(QRectF(pt.x() - 80, pt.y() + 16, 160, 22), Qt.AlignmentFlag.AlignHCenter, label)
        qp.end()
