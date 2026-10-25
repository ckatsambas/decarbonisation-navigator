"""Small reusable widgets. Every widget that shows text takes a translation key, not a string,
so it can redraw itself when the language changes."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..i18n import tr


def amp(text: str) -> str:
    """Escape '&' for buttons and tabs, where Qt would otherwise turn it into a shortcut marker."""
    return text.replace("&", "&&")


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


class TrLabel(QLabel):
    """A label bound to a translation key; call retranslate() after a language change."""

    def __init__(self, key: str, obj_name: str | None = None, wrap: bool = False, **fmt):
        super().__init__()
        self.key, self.fmt = key, fmt
        if obj_name:
            self.setObjectName(obj_name)
        self.setWordWrap(wrap)
        self.retranslate()

    def set_key(self, key: str, **fmt) -> None:
        self.key, self.fmt = key, fmt
        self.retranslate()

    def retranslate(self) -> None:
        self.setText(tr(self.key, **self.fmt))


class Panel(QFrame):
    """Bordered card with an optional uppercase title."""

    def __init__(self, title_key: str | None = None):
        super().__init__()
        self.setObjectName("Panel")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 16)
        self.body.setSpacing(10)
        self.title = TrLabel(title_key, "PanelTitle") if title_key else None
        if self.title:
            self.body.addWidget(self.title)


class Kpi(QWidget):
    """Label over a large value."""

    def __init__(self, key: str, **fmt):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self.caption = TrLabel(key, "KpiLabel", wrap=True, **fmt)
        self.value = label("–", "KpiValue")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.caption)
        v.addWidget(self.value)


class ReadMore(QWidget):
    """A quiet "Read more" link that unfolds an explanation (used for every estimate)."""

    def __init__(self, key: str, **fmt):
        from PySide6.QtWidgets import QToolButton
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.toggle = QToolButton()
        self.toggle.setObjectName("ReadMore")
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.toggled.connect(self._toggled)
        v.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.body = TrLabel(key, "ReadMoreBody", wrap=True, **fmt)
        self.body.hide()
        v.addWidget(self.body)
        self.retranslate()

    def _toggled(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.body.setVisible(on)

    def set_key(self, key: str, **fmt) -> None:
        self.body.set_key(key, **fmt)

    def retranslate(self) -> None:
        self.toggle.setText(tr("readmore"))
        self.body.retranslate()


class Fold(QWidget):
    """A section that stays folded until asked for ("Advanced", "Details")."""

    def __init__(self, key: str, **fmt):
        from PySide6.QtWidgets import QSizePolicy, QToolButton
        super().__init__()
        self.key, self.fmt = key, fmt
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.toggle = QToolButton()
        self.toggle.setObjectName("Fold")
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggle.toggled.connect(self._toggled)
        v.addWidget(self.toggle)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        self.body.hide()
        v.addWidget(self.body)
        self.retranslate()

    def _toggled(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.body.setVisible(on)

    def set_open(self, on: bool) -> None:
        self.toggle.setChecked(on)

    def retranslate(self) -> None:
        self.toggle.setText("  " + tr(self.key, **self.fmt))


class ContourBackground(QWidget):
    """Plain container that paints soft depth contours and a small compass rose, like a sea chart."""

    def __init__(self, seed: int = 7):
        super().__init__()
        self.seed = seed
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        import math

        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

        from . import theme
        p = theme.current()
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        qp.fillRect(self.rect(), QColor(p.bg))
        w, h = self.width(), self.height()
        pen = QPen(QColor(p.contour))
        pen.setWidthF(1.2)
        qp.setPen(pen)
        # two families of contours: a bank in the lower right and gentle swells across the top
        for k in range(9):
            path = QPainterPath()
            r = 140 + k * 46
            cx, cy = w * 0.86, h * 0.98
            for i in range(73):
                a = math.pi + i * (math.pi / 2) / 72
                wob = 1 + 0.06 * math.sin(3 * a + k * 0.7 + self.seed) + 0.03 * math.sin(7 * a + k)
                pt = QPointF(cx + r * wob * math.cos(a) * 1.6, cy + r * wob * math.sin(a))
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            qp.drawPath(path)
        for k in range(5):
            path = QPainterPath()
            y0 = 40 + k * 34
            for i in range(0, w + 20, 20):
                y = y0 + 10 * math.sin(i / 140 + k * 0.9 + self.seed) + 5 * math.sin(i / 53 + k)
                path.moveTo(i, y) if i == 0 else path.lineTo(i, y)
            qp.drawPath(path)
        # compass rose
        cx, cy, r = w - 90, 110, 34
        pen.setColor(QColor(p.faint))
        pen.setWidthF(1.0)
        qp.setPen(pen)
        qp.drawEllipse(QPointF(cx, cy), r, r)
        qp.drawEllipse(QPointF(cx, cy), r * 0.62, r * 0.62)
        for i in range(16):
            a = i * math.pi / 8
            ln = r * (1.18 if i % 4 == 0 else 1.05)
            qp.drawLine(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)),
                        QPointF(cx + ln * math.cos(a), cy + ln * math.sin(a)))
        qp.setBrush(QColor(p.accent))
        qp.setPen(Qt.PenStyle.NoPen)
        north = QPainterPath()
        north.moveTo(cx, cy - r * 0.95)
        north.lineTo(cx - 6, cy)
        north.lineTo(cx + 6, cy)
        north.closeSubpath()
        qp.drawPath(north)
        qp.setBrush(QColor(p.faint))
        south = QPainterPath()
        south.moveTo(cx, cy + r * 0.95)
        south.lineTo(cx - 6, cy)
        south.lineTo(cx + 6, cy)
        south.closeSubpath()
        qp.drawPath(south)
        qp.setPen(QColor(p.muted))
        qp.setFont(self.font())
        qp.drawText(QPointF(cx - 4, cy - r - 10), "N")
        qp.end()
