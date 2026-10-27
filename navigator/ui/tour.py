"""Guided tour on the real application (decision 0015).

The window darkens, one element at a time is lit (the light glides from element to element), a
bubble explains it and an arrow draws itself from the bubble to the element. The tour walks the
lobby, the top bar and the six steps on a sample project (a Kamsarmax), which is removed at the
end. Back / Next / Skip; arrows and Esc on the keyboard; the text follows the language switch.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .. import i18n
from ..i18n import tr
from . import anim, theme
from .widgets import amp


@dataclass
class Step:
    key: str                                   # tour.<key>.title / tour.<key>.text
    target: Callable[[], QWidget | None]
    before: Callable[[], None] | None = None


def _scroll_into_view(w: QWidget) -> None:
    p = w.parentWidget()
    while p is not None:
        if isinstance(p, QScrollArea):
            p.ensureWidgetVisible(w, 40, 120)
            return
        p = p.parentWidget()


class Bubble(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("TourBubble")
        self.setFixedWidth(360)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 14)
        v.setSpacing(8)
        self.count = QLabel()
        self.count.setObjectName("TourCount")
        v.addWidget(self.count)
        self.title = QLabel()
        self.title.setObjectName("TourTitle")
        self.title.setWordWrap(True)
        v.addWidget(self.title)
        self.text = QLabel()
        self.text.setObjectName("TourText")
        self.text.setWordWrap(True)
        v.addWidget(self.text)
        h = QHBoxLayout()
        self.skip = QPushButton()
        self.skip.setObjectName("Link")
        h.addWidget(self.skip)
        h.addStretch(1)
        self.back = QPushButton()
        self.back.setObjectName("Ghost")
        h.addWidget(self.back)
        self.next = QPushButton()
        self.next.setObjectName("Primary")
        h.addWidget(self.next)
        v.addLayout(h)


class Tour(QWidget):
    finished = Signal()
    PAD = 8

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.k = 0
        self.sample_id: str | None = None
        self.hole = QRectF()
        self._from = QRectF()
        self._to = QRectF()
        self._arrow_t = 1.0
        self._pulse = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.bubble = Bubble(self)
        self.bubble.next.clicked.connect(self.next)
        self.bubble.back.clicked.connect(self.back)
        self.bubble.skip.clicked.connect(self.finish)
        self._move = QVariantAnimation(self)
        self._move.setDuration(480)
        self._move.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._move.valueChanged.connect(self._morph)
        self._move.finished.connect(self._draw_arrow)
        self._arrow = QVariantAnimation(self)
        self._arrow.setDuration(420)
        self._arrow.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._arrow.valueChanged.connect(lambda v: (setattr(self, "_arrow_t", float(v)), self.update()))
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._unsub = i18n.on_change(lambda _l: self._texts())
        win.installEventFilter(self)
        self.steps = self._steps()

    # ------------------------------------------------------------------ the route of the tour
    def _steps(self) -> list[Step]:
        w = self.win
        pv = w.project_view

        def lobby():
            w.show_lobby()

        def open_sample():
            if self.sample_id is None or pv.project is None or pv.project.id != self.sample_id:
                w.new_project()
                pv.rename(tr("tour.sample"))
                w.name_edit.setText(tr("tour.sample"))
                self.sample_id = pv.project.id
                pv.ship_step.set_mode("standard")
                pv.ship_step.std_pane.pick_preset("kamsarmax")
            pv.go(0, save=False)

        def ship_chosen():
            open_sample()
            if pv.position_step.inputs.standard is None:
                pv.ship_step.std_pane.use_btn.click()

        def step(i: int):
            def go():
                ship_chosen()
                if i >= 2 and not pv.options_step.shortlist:
                    for key in ("hull_coating", "propulsion_devices", "rotor_sails"):
                        if any(r.ok and r.m.key == key for r in pv.options_step.rows):
                            pv.options_step.set_ticked(key, True)
                if pv.project is not None:
                    pv.project.reached = max(pv.project.reached, i)
                pv.go(i, save=False)
            return go

        return [
            Step("welcome", lambda: None, lobby),
            Step("new", lambda: w.lobby.new_btn, lobby),
            Step("projects", lambda: _grid_area(w.lobby), lobby),
            Step("language", lambda: w.lang_switch, lobby),
            Step("theme", lambda: w.theme_switch, lobby),
            Step("anim", lambda: w.anim_btn, lobby),
            Step("account", lambda: w.account_btn if w.account_btn.isVisible() else w.version, lobby),
            Step("route", lambda: pv.stepper, open_sample),
            Step("ship", lambda: pv.ship_step.mode, open_sample),
            Step("presets", lambda: pv.ship_step.std_pane.preset_buttons["kamsarmax"].parentWidget(), open_sample),
            Step("continue", lambda: pv.next_btn, ship_chosen),
            Step("scope", lambda: w.view_switch, step(1)),
            Step("position", lambda: pv.position_step.price.parentWidget(), step(1)),
            Step("numbers", lambda: pv.position_step.n_total.parentWidget(), step(1)),
            Step("options", lambda: pv.options_step.table, step(2)),
            Step("plans", lambda: pv.options_step.plans, step(2)),
            Step("priorities", lambda: pv.priorities_step.levels["families"], step(3)),
            Step("decision", lambda: pv.decision_step.table, step(4)),
            Step("smaa", lambda: pv.decision_step.run_btn, step(4)),
            Step("report", lambda: pv.report_step.pdf_btn, step(5)),
            Step("done", lambda: None, lobby),
        ]

    # ------------------------------------------------------------------ control
    def begin(self) -> None:
        self.setGeometry(self.win.rect())
        self.show()
        self.raise_()
        self.setFocus()
        if anim.enabled():
            self._timer.start()
        self.show_step(0, first=True)

    def next(self) -> None:
        if self.k + 1 >= len(self.steps):
            self.finish()
        else:
            self.show_step(self.k + 1)

    def back(self) -> None:
        if self.k > 0:
            self.show_step(self.k - 1)

    def finish(self) -> None:
        self._timer.stop()
        self.win.removeEventFilter(self)
        self._unsub()
        if self.sample_id is not None:
            if self.win.project_view.project is not None and self.win.project_view.project.id == self.sample_id:
                self.win.show_lobby()
            try:
                self.win.store.path(self.sample_id).unlink(missing_ok=True)
            except OSError:
                pass
            self.win.lobby.refresh()
        self.hide()
        self.deleteLater()
        self.finished.emit()

    def show_step(self, k: int, first: bool = False) -> None:
        self.k = k
        st = self.steps[k]
        if st.before:
            st.before()
        target = st.target()
        if target is not None:
            _scroll_into_view(target)
        # let layouts settle before measuring
        QTimer.singleShot(30 if not first else 60, lambda: self._aim(target))
        self._texts()

    def _aim(self, target: QWidget | None) -> None:
        if not self.isVisible():
            return
        self.setGeometry(self.win.rect())
        self.raise_()
        if target is None or not target.isVisible():
            c = QPointF(self.width() / 2, self.height() / 2)
            to = QRectF(c.x(), c.y(), 0, 0)
        else:
            tl = target.mapTo(self.win, QPoint(0, 0))
            to = QRectF(tl.x(), tl.y(), target.width(), target.height()).adjusted(-self.PAD, -self.PAD, self.PAD, self.PAD)
            to = to.intersected(QRectF(self.rect()).adjusted(6, 6, -6, -6))
        self._from, self._to = QRectF(self.hole), to
        self._arrow_t = 0.0
        if anim.enabled() and not self.hole.isNull():
            self._move.stop()
            self._move.setStartValue(0.0)
            self._move.setEndValue(1.0)
            self._move.start()
        else:
            self._morph(1.0)
            self._draw_arrow()
        self._place_bubble(to)

    def _morph(self, t) -> None:
        t = float(t)
        a, b = self._from, self._to
        self.hole = QRectF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t,
                           a.width() + (b.width() - a.width()) * t, a.height() + (b.height() - a.height()) * t)
        self.update()

    def _draw_arrow(self) -> None:
        if anim.enabled():
            self._arrow.stop()
            self._arrow.setStartValue(0.0)
            self._arrow.setEndValue(1.0)
            self._arrow.start()
        else:
            self._arrow_t = 1.0
            self.update()

    def _place_bubble(self, r: QRectF) -> None:
        b = self.bubble
        self._fit_bubble()
        bw, bh, gap = b.width(), b.height(), 44
        W, H = self.width(), self.height()
        if r.width() == 0:
            pos = QPointF((W - bw) / 2, (H - bh) / 2)
        elif r.right() + gap + bw < W - 16:
            pos = QPointF(r.right() + gap, r.center().y() - bh / 2)
        elif r.bottom() + gap + bh < H - 16:
            pos = QPointF(r.center().x() - bw / 2, r.bottom() + gap)
        elif r.top() - gap - bh > 16:
            pos = QPointF(r.center().x() - bw / 2, r.top() - gap - bh)
        else:
            pos = QPointF(max(r.left() - gap - bw, 16), r.center().y() - bh / 2)
        pos = QPoint(int(min(max(pos.x(), 16), W - bw - 16)), int(min(max(pos.y(), 16), H - bh - 16)))
        if anim.enabled() and b.isVisible():
            a = QPropertyAnimation(b, b"pos", b)
            a.setDuration(480)
            a.setEasingCurve(QEasingCurve.Type.InOutCubic)
            a.setEndValue(pos)
            a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        else:
            b.move(pos)
        b.show()
        b.raise_()

    def _texts(self) -> None:
        st = self.steps[self.k]
        b = self.bubble
        b.count.setText(f"{self.k + 1} / {len(self.steps)}")
        b.title.setText(tr(f"tour.{st.key}.title"))
        b.text.setText(tr(f"tour.{st.key}.text"))
        b.skip.setText(amp(tr("tour.skip")))
        b.back.setText(amp(tr("tour.back")))
        b.back.setEnabled(self.k > 0)
        b.next.setText(amp(tr("tour.finish") if self.k + 1 == len(self.steps) else tr("tour.next")))
        self._fit_bubble()

    def _fit_bubble(self) -> None:
        """Wrapped text needs height for the bubble's fixed width."""
        b = self.bubble
        lay = b.layout()
        lay.activate()
        b.resize(b.width(), max(lay.totalHeightForWidth(b.width()), lay.totalMinimumSize().height()))

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.035) % 1.0
        self.update()

    # ------------------------------------------------------------------ drawing
    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        veil = QPainterPath()
        veil.addRect(QRectF(self.rect()))
        if self.hole.width() > 1:
            veil.addRoundedRect(self.hole, 10, 10)
        veil.setFillRule(Qt.FillRule.OddEvenFill)
        g.fillPath(veil, QColor(6, 18, 28, 150 if p.name == "light" else 175))
        if self.hole.width() > 1:
            g.setPen(QPen(QColor(p.accent), 2.5))
            g.setBrush(Qt.BrushStyle.NoBrush)
            g.drawRoundedRect(self.hole, 10, 10)
            grow = 4 + 12 * self._pulse
            c = QColor(p.accent)
            c.setAlphaF(0.6 * (1 - self._pulse))
            g.setPen(QPen(c, 2))
            g.drawRoundedRect(self.hole.adjusted(-grow, -grow, grow, grow), 12 + grow / 2, 12 + grow / 2)
            self._arrow_path(g, p)
        g.end()

    def _arrow_path(self, g: QPainter, p) -> None:
        b = self.bubble.geometry()
        h = self.hole
        bc = QPointF(b.center())
        hc = h.center()
        # start on the bubble's edge facing the target, end on the target's edge
        start = _edge_point(QRectF(b), hc)
        end = _edge_point(h.adjusted(-6, -6, 6, 6), bc)
        mid = (start + end) / 2
        dx, dy = end.x() - start.x(), end.y() - start.y()
        n = math.hypot(dx, dy) or 1
        ctrl = mid + QPointF(-dy / n, dx / n) * min(60, n * 0.25)
        t = self._arrow_t
        pts = []
        for i in range(41):
            s = t * i / 40
            pts.append((1 - s) ** 2 * start + 2 * (1 - s) * s * ctrl + s * s * end)
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        pen = QPen(QColor("#FFFFFF"), 2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        g.setPen(pen)
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawPath(path)
        if t > 0.95 and len(pts) > 2:
            tip, prev = pts[-1], pts[-3]
            ang = math.atan2(tip.y() - prev.y(), tip.x() - prev.x())
            head = QPolygonF([tip, tip - QPointF(math.cos(ang - 0.45), math.sin(ang - 0.45)) * 13,
                              tip - QPointF(math.cos(ang + 0.45), math.sin(ang + 0.45)) * 13])
            g.setBrush(QColor("#FFFFFF"))
            g.drawPolygon(head)

    # ------------------------------------------------------------------ input
    def eventFilter(self, obj: QObject, e: QEvent) -> bool:  # noqa: N802 - Qt API
        if obj is self.win and e.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.win.rect())
            QTimer.singleShot(0, lambda: self._aim(self.steps[self.k].target()))
        return False

    def keyPressEvent(self, e) -> None:  # noqa: N802 - Qt API
        if e.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.next()
        elif e.key() == Qt.Key.Key_Left:
            self.back()
        elif e.key() == Qt.Key.Key_Escape:
            self.finish()

    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt API
        e.accept()                             # the tour leads; clicks on the veil do nothing

    def wheelEvent(self, e) -> None:  # noqa: N802 - Qt API
        e.accept()


def _edge_point(r: QRectF, toward: QPointF) -> QPointF:
    """Where the line from the rectangle's centre toward a point leaves the rectangle."""
    c = r.center()
    dx, dy = toward.x() - c.x(), toward.y() - c.y()
    if dx == 0 and dy == 0:
        return c
    sx = (r.width() / 2) / abs(dx) if dx else math.inf
    sy = (r.height() / 2) / abs(dy) if dy else math.inf
    s = min(sx, sy)
    return QPointF(c.x() + dx * s, c.y() + dy * s)


def _grid_area(lobby) -> QWidget | None:
    """The first project card, or the button for a new project when there are none."""
    for i in range(lobby.grid.count()):
        w = lobby.grid.itemAt(i).widget()
        if w is not None and w.isVisible():
            return w
    return lobby.new_btn

