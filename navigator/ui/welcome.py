"""First launch (decision 0015), in the manner of a new Windows device's set-up: three pages on an
animated sea chart. A route is drawn from waypoint to waypoint as you move through the pages.

1. Account: sign in, create a local account (with a recovery code), or continue as a guest; terms
   of use must be accepted. Forgotten password: reset with the recovery code.
2. Preferences: language and theme (applied live), interface size, animations. All can be changed
   later from the top bar and the account menu.
3. Tour: start the guided tour of the real application, or skip it.

Later launches show only the account page (unless "keep me signed in" was ticked).
"""
from __future__ import annotations

import math
import random

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import i18n
from ..data import accounts as A
from ..i18n import tr
from . import anim, theme
from .widgets import amp

SCALES = ("90", "100", "110", "125", "150")


def terms_text(lang: str | None = None) -> str:
    from pathlib import Path
    lang = lang or i18n.language()
    path = Path(i18n.__file__).resolve().parent / f"terms_{lang}.md"
    return path.read_text(encoding="utf-8")


def with_alpha(c: str | QColor, a: float) -> QColor:
    q = QColor(c)
    q.setAlphaF(max(0.0, min(1.0, a)))
    return q


# ------------------------------------------------------------------ animated background
class Ocean(QWidget):
    """Drifting depth contours, plankton, a compass rose and the set-up route with a ship on it."""

    WAYPOINTS = ((0.05, 0.84), (0.17, 0.72), (0.31, 0.82), (0.45, 0.70))

    def __init__(self):
        super().__init__()
        self.phase = 0.0
        self.pos_t = 0.0                 # ship position along the route, 0 … len(WAYPOINTS) − 1
        rnd = random.Random(11)
        self.dots = [(rnd.random(), rnd.random(), rnd.uniform(0.6, 2.2), rnd.uniform(0.2, 1.0)) for _ in range(90)]
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._ship = QVariantAnimation(self)
        self._ship.setDuration(1100)
        self._ship.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._ship.valueChanged.connect(self._sail)

    def showEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().showEvent(e)
        if anim.enabled():
            self._timer.start()

    def hideEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self) -> None:
        if not anim.enabled():
            self._timer.stop()
            return
        self.phase += 0.012
        self.update()

    def _sail(self, v) -> None:
        self.pos_t = float(v)
        self.update()

    def sail_to(self, k: int) -> None:
        if anim.enabled():
            self._ship.stop()
            self._ship.setStartValue(self.pos_t)
            self._ship.setEndValue(float(k))
            self._ship.start()
            if not self._timer.isActive() and self.isVisible():
                self._timer.start()
        else:
            self._sail(k)

    def _pt(self, t: float) -> QPointF:
        w, h = self.width(), self.height()
        n = len(self.WAYPOINTS) - 1
        t = min(max(t, 0.0), n)
        i = min(int(t), n - 1)
        f = t - i
        (x0, y0), (x1, y1) = self.WAYPOINTS[i], self.WAYPOINTS[i + 1]
        # a gentle S-curve between waypoints
        x = x0 + (x1 - x0) * f
        y = y0 + (y1 - y0) * (3 * f * f - 2 * f * f * f) - 0.05 * math.sin(math.pi * f)
        return QPointF(x * w, y * h)

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0, QColor(p.bg))
        grad.setColorAt(1, QColor(p.shallow))
        g.fillRect(self.rect(), grad)
        # drifting contour lines
        for k in range(14):
            path = QPainterPath()
            y0 = h * (0.08 + k * 0.068)
            amp_ = 14 + 6 * math.sin(k * 1.3)
            for i in range(0, w + 24, 24):
                y = (y0 + amp_ * math.sin(i / 210 + k * 0.8 + self.phase * (0.6 + 0.05 * k))
                     + 6 * math.sin(i / 77 - self.phase * 1.3 + k))
                path.moveTo(i, y) if i == 0 else path.lineTo(i, y)
            g.setPen(QPen(with_alpha(p.contour if p.name == "light" else p.border, 0.9 - k * 0.03), 1.2))
            g.drawPath(path)
        # plankton
        g.setPen(Qt.PenStyle.NoPen)
        for x, y, r, a in self.dots:
            xx = (x * w + 18 * math.sin(self.phase * 0.7 + y * 9)) % w
            yy = (y * h + 12 * math.cos(self.phase * 0.5 + x * 7)) % h
            g.setBrush(with_alpha(p.accent, 0.10 + 0.18 * a * (0.5 + 0.5 * math.sin(self.phase * 2 + x * 20))))
            g.drawEllipse(QPointF(xx, yy), r, r)
        # compass rose, slowly turning
        c = QPointF(w * 0.44, 150)
        g.save()
        g.translate(c)
        g.rotate(math.degrees(self.phase * 0.15))
        g.setPen(QPen(with_alpha(p.accent, 0.35), 1))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawEllipse(QPointF(0, 0), 64, 64)
        g.drawEllipse(QPointF(0, 0), 46, 46)
        for k in range(32):
            a = k * math.pi / 16
            r0 = 58 if k % 4 else 50
            g.drawLine(QPointF(r0 * math.sin(a), -r0 * math.cos(a)), QPointF(64 * math.sin(a), -64 * math.cos(a)))
        g.setBrush(with_alpha(p.accent, 0.35))
        for k in range(4):
            a = k * math.pi / 2
            tip = QPointF(60 * math.sin(a), -60 * math.cos(a))
            l_ = QPointF(9 * math.sin(a - math.pi / 2), -9 * math.cos(a - math.pi / 2))
            r_ = QPointF(9 * math.sin(a + math.pi / 2), -9 * math.cos(a + math.pi / 2))
            g.drawPolygon(QPolygonF([tip, l_, QPointF(0, 0), r_]))
        g.restore()
        # the route: dashed ahead, solid behind the ship
        n = len(self.WAYPOINTS) - 1
        steps = 120
        full = QPainterPath(self._pt(0))
        done = QPainterPath(self._pt(0))
        for s in range(1, steps + 1):
            t = n * s / steps
            full.lineTo(self._pt(t))
            if t <= self.pos_t:
                done.lineTo(self._pt(t))
        pen = QPen(with_alpha(p.accent, 0.45), 2, Qt.PenStyle.DashLine)
        g.setPen(pen)
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawPath(full)
        g.setPen(QPen(QColor(p.accent), 3))
        g.drawPath(done)
        for k, (x, y) in enumerate(self.WAYPOINTS):
            pt = QPointF(x * w, y * h)
            reached = k <= self.pos_t + 1e-6
            g.setPen(QPen(QColor(p.accent), 2))
            g.setBrush(QColor(p.accent) if reached else QColor(p.panel))
            g.drawEllipse(pt, 7, 7)
            if reached:
                pulse = 7 + 9 * ((self.phase * 2 + k) % 1.0)
                g.setPen(QPen(with_alpha(p.accent, 1 - (pulse - 7) / 9), 1.5))
                g.setBrush(Qt.BrushStyle.NoBrush)
                g.drawEllipse(pt, pulse, pulse)
        # the ship, pointing along the route
        s = self._pt(self.pos_t)
        a = self._pt(min(self.pos_t + 0.02, n))
        b = self._pt(max(self.pos_t - 0.02, 0))
        ang = math.atan2(a.y() - b.y(), a.x() - b.x())
        g.save()
        g.translate(s)
        g.rotate(math.degrees(ang))
        g.setPen(QPen(QColor(p.panel), 1.5))
        g.setBrush(QColor("#D23B2E"))
        g.drawPolygon(QPolygonF([QPointF(14, 0), QPointF(4, -6), QPointF(-11, -6), QPointF(-11, 6), QPointF(4, 6)]))
        g.restore()
        g.end()


# ------------------------------------------------------------------ small parts
class Dots(QWidget):
    """Progress dots: the current one stretches into a pill."""

    def __init__(self, n: int):
        super().__init__()
        self.n, self.cur, self._x = n, 0, 0.0
        self.setFixedSize(QSize(18 * n + 30, 14))
        self._a = QVariantAnimation(self)
        self._a.setDuration(380)
        self._a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_x", float(v)), self.update()))

    def set_current(self, k: int) -> None:
        self.cur = k
        if anim.enabled():
            self._a.stop()
            self._a.setStartValue(self._x)
            self._a.setEndValue(float(k))
            self._a.start()
        else:
            self._x = float(k)
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        g.setPen(Qt.PenStyle.NoPen)
        for k in range(self.n):
            g.setBrush(QColor(p.border))
            g.drawEllipse(QPointF(7 + k * 18, 7), 4, 4)
        g.setBrush(QColor(p.accent))
        x = 7 + self._x * 18
        g.drawRoundedRect(QRectF(x - 4, 3, 22, 8), 4, 4)
        g.end()


class PasswordField(QWidget):
    """Line edit with a show/hide toggle."""

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setObjectName("Auth")
        h.addWidget(self.edit, 1)
        self.eye = QToolButton()
        self.eye.setObjectName("Eye")
        self.eye.setText("👁")
        self.eye.setCheckable(True)
        self.eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eye.toggled.connect(lambda on: self.edit.setEchoMode(QLineEdit.EchoMode.Normal if on
                                                                  else QLineEdit.EchoMode.Password))
        h.addWidget(self.eye)

    def text(self) -> str:
        return self.edit.text()

    def clear(self) -> None:
        self.edit.clear()


class Strength(QWidget):
    """Four segments filling with the password's strength."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self.level = 0

    def set_level(self, k: int) -> None:
        self.level = k
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        p = theme.current()
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        cols = [p.bad, p.warn, p.good, p.accent]
        w = (self.width() - 9) / 4
        for k in range(4):
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(QColor(cols[self.level - 1]) if k < self.level else QColor(p.border))
            g.drawRoundedRect(QRectF(k * (w + 3), 0, w, 6), 3, 3)
        g.end()


def shake(w: QWidget) -> None:
    """A short horizontal shake (wrong password, missing field)."""
    if not anim.enabled():
        return
    a = QPropertyAnimation(w, b"pos", w)
    p0 = w.pos()
    a.setDuration(360)
    for k, dx in enumerate((0, -10, 9, -7, 5, -3, 0)):
        a.setKeyValueAt(k / 6, p0 + QPoint(dx, 0))
    a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def field(label_key: str, widget: QWidget, holder: list) -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    lab = QLabel()
    lab.setObjectName("AuthLabel")
    lab.setProperty("tr", label_key)
    v.addWidget(lab)
    v.addWidget(widget)
    holder.append(lab)
    return box


class TermsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 600)
        self.setWindowTitle(tr("terms.title"))
        v = QVBoxLayout(self)
        self.text = QTextBrowser()
        self.text.setObjectName("Terms")
        self.text.setMarkdown(terms_text())
        v.addWidget(self.text, 1)
        h = QHBoxLayout()
        h.addStretch(1)
        close = QPushButton(amp(tr("terms.close")))
        close.setObjectName("Ghost")
        close.clicked.connect(self.reject)
        ok = QPushButton(amp(tr("terms.accept")))
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        h.addWidget(close)
        h.addWidget(ok)
        v.addLayout(h)


class TermsCheck(QWidget):
    """'I accept the terms' with a link that opens them; accepting in the dialog ticks the box."""

    changed = Signal(bool)

    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.box = QCheckBox()
        self.box.toggled.connect(self.changed)
        h.addWidget(self.box)
        self.label = QLabel()
        self.label.setObjectName("AuthSmall")
        self.label.setWordWrap(True)
        self.label.linkActivated.connect(self.open)
        h.addWidget(self.label, 1)
        self.retranslate()

    def open(self, *_a) -> None:
        dlg = TermsDialog(self.window())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.box.setChecked(True)

    def checked(self) -> bool:
        return self.box.isChecked()

    def retranslate(self) -> None:
        p = theme.current()
        self.label.setText(tr("auth.terms", a=f"<a href='#' style='color:{p.accent}'>", b="</a>"))


# ------------------------------------------------------------------ page 1: account
class AccountPage(QWidget):
    done = Signal(object, bool)              # account, remember

    def __init__(self, store: A.AccountStore):
        super().__init__()
        self.store = store
        self.labels: list[QLabel] = []
        self._lock_left = 0
        self._pending: A.Account | None = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        tabs = QHBoxLayout()
        tabs.setSpacing(0)
        self.tab_group = QButtonGroup(self)
        self.tabs: dict[str, QPushButton] = {}
        for key in ("signin", "create", "guest"):
            b = QPushButton()
            b.setObjectName("AuthTab")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.show_form(k))
            self.tab_group.addButton(b)
            tabs.addWidget(b)
            self.tabs[key] = b
        v.addLayout(tabs)
        self.forms = QStackedWidget()
        v.addWidget(self.forms)
        self.error = QLabel()
        self.error.setObjectName("AuthError")
        self.error.setWordWrap(True)
        v.addWidget(self.error)
        v.addStretch(1)

        # --- sign in
        f = QWidget()
        fv = QVBoxLayout(f)
        fv.setContentsMargins(0, 8, 0, 0)
        fv.setSpacing(10)
        self.users = QHBoxLayout()
        self.users.setSpacing(8)
        fv.addLayout(self.users)
        self.in_user = QLineEdit()
        self.in_user.setObjectName("Auth")
        fv.addWidget(field("auth.username", self.in_user, self.labels))
        self.in_pw = PasswordField()
        self.in_pw.edit.returnPressed.connect(self.sign_in)
        fv.addWidget(field("auth.password", self.in_pw, self.labels))
        self.remember = QCheckBox()
        self.remember.setObjectName("AuthSmall")
        fv.addWidget(self.remember)
        self.in_btn = QPushButton()
        self.in_btn.setObjectName("Primary")
        self.in_btn.clicked.connect(self.sign_in)
        fv.addWidget(self.in_btn)
        self.forgot_btn = QPushButton()
        self.forgot_btn.setObjectName("Link")
        self.forgot_btn.clicked.connect(lambda: self.show_form("forgot"))
        fv.addWidget(self.forgot_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.forms.addWidget(f)

        # --- create
        f = QWidget()
        fv = QVBoxLayout(f)
        fv.setContentsMargins(0, 8, 0, 0)
        fv.setSpacing(10)
        self.c_name = QLineEdit()
        self.c_name.setObjectName("Auth")
        fv.addWidget(field("auth.display", self.c_name, self.labels))
        self.c_user = QLineEdit()
        self.c_user.setObjectName("Auth")
        fv.addWidget(field("auth.username.new", self.c_user, self.labels))
        self.c_pw = PasswordField()
        self.c_pw.edit.textChanged.connect(lambda t: self.meter.set_level(A.password_strength(t)))
        fv.addWidget(field("auth.password.new", self.c_pw, self.labels))
        self.meter = Strength()
        fv.addWidget(self.meter)
        self.c_pw2 = PasswordField()
        self.c_pw2.edit.returnPressed.connect(self.create)
        fv.addWidget(field("auth.confirm", self.c_pw2, self.labels))
        self.c_terms = TermsCheck()
        fv.addWidget(self.c_terms)
        self.c_btn = QPushButton()
        self.c_btn.setObjectName("Primary")
        self.c_btn.clicked.connect(self.create)
        fv.addWidget(self.c_btn)
        self.forms.addWidget(f)

        # --- guest
        f = QWidget()
        fv = QVBoxLayout(f)
        fv.setContentsMargins(0, 8, 0, 0)
        fv.setSpacing(12)
        self.g_text = QLabel()
        self.g_text.setObjectName("AuthText")
        self.g_text.setWordWrap(True)
        fv.addWidget(self.g_text)
        self.g_terms = TermsCheck()
        fv.addWidget(self.g_terms)
        self.g_btn = QPushButton()
        self.g_btn.setObjectName("Primary")
        self.g_btn.clicked.connect(self.guest)
        fv.addWidget(self.g_btn)
        fv.addStretch(1)
        self.forms.addWidget(f)

        # --- forgot password
        f = QWidget()
        fv = QVBoxLayout(f)
        fv.setContentsMargins(0, 8, 0, 0)
        fv.setSpacing(10)
        self.r_text = QLabel()
        self.r_text.setObjectName("AuthText")
        self.r_text.setWordWrap(True)
        fv.addWidget(self.r_text)
        self.r_user = QLineEdit()
        self.r_user.setObjectName("Auth")
        fv.addWidget(field("auth.username", self.r_user, self.labels))
        self.r_code = QLineEdit()
        self.r_code.setObjectName("Auth")
        self.r_code.setPlaceholderText("XXXX-XXXX-XXXX")
        fv.addWidget(field("auth.code", self.r_code, self.labels))
        self.r_pw = PasswordField()
        fv.addWidget(field("auth.password.new", self.r_pw, self.labels))
        self.r_pw2 = PasswordField()
        fv.addWidget(field("auth.confirm", self.r_pw2, self.labels))
        self.r_btn = QPushButton()
        self.r_btn.setObjectName("Primary")
        self.r_btn.clicked.connect(self.reset)
        fv.addWidget(self.r_btn)
        self.r_back = QPushButton()
        self.r_back.setObjectName("Link")
        self.r_back.clicked.connect(lambda: self.show_form("signin"))
        fv.addWidget(self.r_back, 0, Qt.AlignmentFlag.AlignLeft)
        self.forms.addWidget(f)

        # --- recovery code (after sign-up or reset)
        f = QWidget()
        fv = QVBoxLayout(f)
        fv.setContentsMargins(0, 8, 0, 0)
        fv.setSpacing(12)
        self.k_text = QLabel()
        self.k_text.setObjectName("AuthText")
        self.k_text.setWordWrap(True)
        fv.addWidget(self.k_text)
        self.k_code = QLabel()
        self.k_code.setObjectName("RecoveryCode")
        self.k_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.k_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fv.addWidget(self.k_code)
        self.k_copy = QPushButton()
        self.k_copy.setObjectName("Ghost")
        self.k_copy.clicked.connect(self._copy_code)
        fv.addWidget(self.k_copy, 0, Qt.AlignmentFlag.AlignCenter)
        self.k_saved = QCheckBox()
        self.k_saved.setObjectName("AuthSmall")
        fv.addWidget(self.k_saved)
        self.k_btn = QPushButton()
        self.k_btn.setObjectName("Primary")
        self.k_btn.setEnabled(False)
        self.k_saved.toggled.connect(self.k_btn.setEnabled)
        self.k_btn.clicked.connect(self._code_saved)
        fv.addWidget(self.k_btn)
        fv.addStretch(1)
        self.forms.addWidget(f)

        # --- terms changed since this account accepted them
        f = QWidget()
        fv = QVBoxLayout(f)
        fv.setContentsMargins(0, 8, 0, 0)
        fv.setSpacing(12)
        self.t_text = QLabel()
        self.t_text.setObjectName("AuthText")
        self.t_text.setWordWrap(True)
        fv.addWidget(self.t_text)
        self.t_terms = TermsCheck()
        fv.addWidget(self.t_terms)
        self.t_btn = QPushButton()
        self.t_btn.setObjectName("Primary")
        self.t_btn.clicked.connect(self._accept_new_terms)
        fv.addWidget(self.t_btn)
        fv.addStretch(1)
        self.forms.addWidget(f)

        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(1000)
        self._lock_timer.timeout.connect(self._lock_tick)
        self.retranslate()
        self.show_form("signin" if self.store.accounts() else "create")

    FORMS = {"signin": 0, "create": 1, "guest": 2, "forgot": 3, "code": 4, "terms": 5}

    def show_form(self, key: str) -> None:
        self.error.setText("")
        for k, b in self.tabs.items():
            b.setChecked(k == key or (key == "forgot" and k == "signin"))
        self.forms.setCurrentIndex(self.FORMS[key])
        tabs_on = key in ("signin", "create", "guest", "forgot")
        for b in self.tabs.values():
            b.setVisible(tabs_on)
        if key == "signin":
            self._fill_users()
            (self.in_pw.edit if self.in_user.text() else self.in_user).setFocus()
        elif key == "create":
            self.c_name.setFocus()

    def _fill_users(self) -> None:
        while self.users.count():
            it = self.users.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for acc in self.store.accounts()[:4]:
            b = QPushButton(f"{initials(acc.display_name)}  {acc.display_name}")
            b.setObjectName("UserChip")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, u=acc.username: (self.in_user.setText(u), self.in_pw.edit.setFocus()))
            self.users.addWidget(b)
        self.users.addStretch(1)
        if not self.in_user.text() and self.store.accounts():
            self.in_user.setText(self.store.accounts()[0].username)

    def fail(self, e: A.AccountError, target: QWidget | None = None) -> None:
        self.error.setText(tr(e.code, **e.fmt))
        shake(target or self.forms)
        if e.code == "auth.err.locked":
            self._lock_left = int(e.fmt.get("s", 30))
            self.in_btn.setEnabled(False)
            self._lock_timer.start()

    def _lock_tick(self) -> None:
        self._lock_left -= 1
        if self._lock_left <= 0:
            self._lock_timer.stop()
            self.in_btn.setEnabled(True)
            self.error.setText("")
        else:
            self.error.setText(tr("auth.err.locked", s=self._lock_left))

    def sign_in(self) -> None:
        try:
            acc = self.store.login(self.in_user.text(), self.in_pw.text())
        except A.AccountError as e:
            self.in_pw.clear()
            self.fail(e)
            return
        self.in_pw.clear()
        if acc.needs_terms:
            self._pending = acc
            self.show_form("terms")
            return
        self.done.emit(acc, self.remember.isChecked())

    def _accept_new_terms(self) -> None:
        if not self.t_terms.checked():
            self.fail(A.AccountError("auth.err.terms"), self.t_terms)
            return
        acc = self.store.accept_terms(self._pending)
        self.done.emit(acc, self.remember.isChecked())

    def create(self) -> None:
        try:
            acc, code = self.store.create(self.c_user.text(), self.c_pw.text(), self.c_pw2.text(), self.c_name.text(),
                                          self.c_terms.checked())
        except A.AccountError as e:
            self.fail(e)
            return
        self._pending = acc
        self.c_pw.clear()
        self.c_pw2.clear()
        self.show_code(code)

    def reset(self) -> None:
        try:
            acc, code = self.store.reset_password(self.r_user.text(), self.r_code.text(), self.r_pw.text(),
                                                  self.r_pw2.text())
        except A.AccountError as e:
            self.fail(e)
            return
        self._pending = acc
        self.r_pw.clear()
        self.r_pw2.clear()
        self.show_code(code, reset=True)

    def show_code(self, code: str, reset: bool = False) -> None:
        self.k_code.setText(code)
        self.k_text.setText(tr("auth.code.reset" if reset else "auth.code.text"))
        self.k_saved.setChecked(False)
        self.show_form("code")

    def _copy_code(self) -> None:
        QGuiApplication.clipboard().setText(self.k_code.text())
        self.k_copy.setText(tr("auth.copied"))

    def _code_saved(self) -> None:
        acc = self._pending
        if acc is not None and acc.needs_terms:
            self.show_form("terms")
            return
        self.done.emit(acc, self.remember.isChecked())

    def guest(self) -> None:
        try:
            acc = self.store.start_guest(self.g_terms.checked())
        except A.AccountError as e:
            self.fail(e, self.g_terms)
            return
        self.done.emit(acc, False)

    def retranslate(self) -> None:
        for k, b in self.tabs.items():
            b.setText(tr(f"auth.tab.{k}"))
        for lab in self.labels:
            lab.setText(tr(lab.property("tr")))
        self.remember.setText(tr("auth.remember"))
        self.in_btn.setText(amp(tr("auth.signin")))
        self.forgot_btn.setText(amp(tr("auth.forgot")))
        self.c_btn.setText(amp(tr("auth.create")))
        self.g_text.setText(tr("auth.guest.text"))
        self.g_btn.setText(amp(tr("auth.guest")))
        self.r_text.setText(tr("auth.reset.text"))
        self.r_btn.setText(amp(tr("auth.reset")))
        self.r_back.setText(amp(tr("auth.back")))
        self.k_copy.setText(amp(tr("auth.copy")))
        self.k_saved.setText(tr("auth.code.saved"))
        self.k_btn.setText(amp(tr("auth.continue")))
        self.t_text.setText(tr("auth.terms.changed"))
        self.t_btn.setText(amp(tr("auth.continue")))
        for t in (self.c_terms, self.g_terms, self.t_terms):
            t.retranslate()
        self.c_user.setPlaceholderText(tr("auth.username.hint"))


def initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


# ------------------------------------------------------------------ page 2: preferences
class Tile(QPushButton):
    """A large choice tile with a painted preview."""

    def __init__(self, kind: str, value: str):
        super().__init__()
        self.kind, self.value = kind, value
        self.setCheckable(True)
        self.setObjectName("Tile")
        self.setMinimumSize(170, 120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    caption = ""

    def paintEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().paintEvent(e)
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        g.setPen(theme.c("text"))
        cf = QFont(self.font())
        cf.setPointSizeF(10)
        cf.setBold(True)
        g.setFont(cf)
        g.drawText(QRectF(self.rect()).adjusted(0, 0, 0, -8), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                   self.caption)
        r = QRectF(self.rect()).adjusted(14, 12, -14, -34)
        if self.kind == "theme":
            pal = theme.PALETTES[self.value]
            g.setPen(QPen(QColor(pal.border), 1))
            g.setBrush(QColor(pal.bg))
            g.drawRoundedRect(r, 6, 6)
            g.setBrush(QColor(pal.panel))
            g.drawRoundedRect(QRectF(r.left() + 8, r.top() + 16, r.width() * 0.55, r.height() - 24), 4, 4)
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(QColor(pal.accent))
            g.drawRoundedRect(QRectF(r.left() + 8, r.top() + 6, r.width() * 0.3, 5), 2, 2)
            for k in range(3):
                g.setBrush(QColor(pal.faint))
                g.drawRoundedRect(QRectF(r.left() + 14, r.top() + 24 + k * 9, r.width() * 0.4 - k * 10, 4), 2, 2)
            for k, hgt in enumerate((0.5, 0.75, 0.4)):
                g.setBrush(QColor((pal.ets, pal.fueleu, pal.imo)[k]))
                bh = (r.height() - 30) * hgt
                g.drawRect(QRectF(r.left() + r.width() * 0.68 + k * 12, r.bottom() - 8 - bh, 8, bh))
        else:
            p = theme.current()
            g.setPen(QColor(p.accent))
            f = QFont(self.font())
            f.setPointSizeF(26)
            f.setBold(True)
            g.setFont(f)
            g.drawText(r, Qt.AlignmentFlag.AlignCenter, "ΕΛ" if self.value == "el" else "EN")
        g.end()


class PrefsPage(QWidget):
    language_changed = Signal(str)
    theme_changed = Signal(str)
    scale_changed = Signal(str)
    animations_changed = Signal(bool)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.h_lang, self.h_theme, self.h_scale = QLabel(), QLabel(), QLabel()
        for h in (self.h_lang, self.h_theme, self.h_scale):
            h.setObjectName("AuthLabel")
        v.addWidget(self.h_lang)
        row = QHBoxLayout()
        self.lang_tiles = {k: Tile("lang", k) for k in ("el", "en")}
        grp = QButtonGroup(self)
        for k, t in self.lang_tiles.items():
            grp.addButton(t)
            t.setChecked(k == i18n.language())
            t.clicked.connect(lambda _=False, k=k: self.language_changed.emit(k))
            row.addWidget(t)
        v.addLayout(row)
        v.addWidget(self.h_theme)
        row = QHBoxLayout()
        self.theme_tiles = {k: Tile("theme", k) for k in ("light", "dark")}
        grp2 = QButtonGroup(self)
        for k, t in self.theme_tiles.items():
            grp2.addButton(t)
            t.setChecked(k == theme.current().name)
            t.clicked.connect(lambda _=False, k=k: self.theme_changed.emit(k))
            row.addWidget(t)
        v.addLayout(row)
        v.addWidget(self.h_scale)
        row = QHBoxLayout()
        row.setSpacing(0)
        self.scale_buttons: dict[str, QPushButton] = {}
        grp3 = QButtonGroup(self)
        cur = str(settings.value("ui_scale", "100"))
        for s in SCALES:
            b = QPushButton(f"{s}%")
            b.setObjectName("Choice")
            b.setCheckable(True)
            b.setChecked(s == cur)
            b.clicked.connect(lambda _=False, s=s: self.scale_changed.emit(s))
            grp3.addButton(b)
            row.addWidget(b)
            self.scale_buttons[s] = b
        row.addStretch(1)
        v.addLayout(row)
        self.scale_note = QLabel()
        self.scale_note.setObjectName("AuthSmall")
        self.scale_note.setWordWrap(True)
        v.addWidget(self.scale_note)
        self.anim_box = QCheckBox()
        self.anim_box.setChecked(anim.enabled())
        self.anim_box.toggled.connect(self.animations_changed)
        v.addWidget(self.anim_box)
        self.later = QLabel()
        self.later.setObjectName("AuthSmall")
        self.later.setWordWrap(True)
        v.addWidget(self.later)
        v.addStretch(1)
        self.retranslate()

    def retranslate(self) -> None:
        self.h_lang.setText(tr("wel.lang"))
        self.h_theme.setText(tr("wel.theme"))
        self.h_scale.setText(tr("wel.scale"))
        self.scale_note.setText(tr("wel.scale.note"))
        self.anim_box.setText(tr("wel.anim"))
        self.later.setText(tr("wel.later"))
        for k, t in self.lang_tiles.items():
            t.caption = "Ελληνικά" if k == "el" else "English"
            t.setAccessibleName(t.caption)
            t.update()
        for k, t in self.theme_tiles.items():
            t.caption = tr(f"theme.{k}")
            t.setAccessibleName(t.caption)
            t.update()


# ------------------------------------------------------------------ page 3: tour
class TourPage(QWidget):
    start = Signal()
    skip = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        self.points = [QLabel() for _ in range(4)]
        for p in self.points:
            p.setObjectName("AuthText")
            p.setWordWrap(True)
            v.addWidget(p)
        v.addSpacing(8)
        self.go = QPushButton()
        self.go.setObjectName("Primary")
        self.go.clicked.connect(self.start)
        v.addWidget(self.go)
        self.no = QPushButton()
        self.no.setObjectName("Ghost")
        self.no.clicked.connect(self.skip)
        v.addWidget(self.no)
        v.addStretch(1)
        self.retranslate()

    def retranslate(self) -> None:
        for k, p in enumerate(self.points, start=1):
            p.setText(tr(f"wel.tour.p{k}"))
        self.go.setText(amp(tr("wel.tour.start")))
        self.no.setText(amp(tr("wel.tour.skip")))


# ------------------------------------------------------------------ the whole set-up
class Welcome(QWidget):
    """`finished(account, remember, start_tour)` when done. mode: 'setup' (all pages) or 'signin'."""

    finished = Signal(object, bool, bool)
    language_changed = Signal(str)
    theme_changed = Signal(str)
    scale_changed = Signal(str)
    animations_changed = Signal(bool)

    PAGES = 3

    def __init__(self, store: A.AccountStore, settings, mode: str = "setup"):
        super().__init__()
        self.store, self.settings, self.mode = store, settings, mode
        self.account: A.Account | None = None
        self.remember = False
        self.ocean = Ocean()
        self.ocean.setParent(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(56, 36, 56, 30)
        top = QHBoxLayout()
        self.brand = QLabel()
        self.brand.setObjectName("WelBrand")
        top.addWidget(self.brand)
        top.addStretch(1)
        self.lang_quick = QPushButton()
        self.lang_quick.setObjectName("Ghost")
        self.lang_quick.clicked.connect(lambda: self.language_changed.emit("en" if i18n.language() == "el" else "el"))
        top.addWidget(self.lang_quick)
        root.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(48)
        left = QVBoxLayout()
        left.addStretch(2)
        self.step_label = QLabel()
        self.step_label.setObjectName("Eyebrow")
        left.addWidget(self.step_label)
        self.title = QLabel()
        self.title.setObjectName("WelTitle")
        self.title.setWordWrap(True)
        left.addWidget(self.title)
        self.sub = QLabel()
        self.sub.setObjectName("WelSub")
        self.sub.setWordWrap(True)
        left.addWidget(self.sub)
        left.addStretch(3)
        body.addLayout(left, 5)
        self.card = QFrame()
        self.card.setObjectName("WelCard")
        self.card.setMinimumWidth(460)
        self.card.setMaximumWidth(560)
        cv = QVBoxLayout(self.card)
        cv.setContentsMargins(34, 30, 34, 30)
        self.pages = QStackedWidget()
        self.account_page = AccountPage(store)
        self.prefs_page = PrefsPage(settings)
        self.tour_page = TourPage()
        for w in (self.account_page, self.prefs_page, self.tour_page):
            self.pages.addWidget(w)
        cv.addWidget(self.pages)
        body.addWidget(self.card, 4, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(body, 1)
        foot = QHBoxLayout()
        self.dots = Dots(self.PAGES)
        foot.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignVCenter)
        foot.addStretch(1)
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("Ghost")
        self.back_btn.clicked.connect(lambda: self.go(self.index - 1))
        self.next_btn = QPushButton()
        self.next_btn.setObjectName("Primary")
        self.next_btn.clicked.connect(lambda: self.go(self.index + 1))
        foot.addWidget(self.back_btn)
        foot.addWidget(self.next_btn)
        root.addLayout(foot)
        self.index = 0
        self.account_page.done.connect(self._signed_in)
        self.prefs_page.language_changed.connect(self.language_changed)
        self.prefs_page.theme_changed.connect(self.theme_changed)
        self.prefs_page.scale_changed.connect(self.scale_changed)
        self.prefs_page.animations_changed.connect(self.animations_changed)
        self.tour_page.start.connect(lambda: self._finish(True))
        self.tour_page.skip.connect(lambda: self._finish(False))
        self._unsub = i18n.on_change(lambda _l: self.retranslate())
        self.destroyed.connect(lambda *_: self._unsub())
        self.retranslate()
        self._show(0, animate=False)

    def resizeEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(e)
        self.ocean.setGeometry(self.rect())
        self.ocean.lower()

    # ------------------------------------------------------------------
    def _signed_in(self, acc: A.Account, remember: bool) -> None:
        self.account, self.remember = acc, remember
        first_time = self.mode == "setup" or not acc.prefs
        if first_time:
            self.go(1)
        else:
            self._finish(False)

    def go(self, k: int) -> None:
        if k < 0 or k >= self.PAGES or (k > 0 and self.account is None):
            return
        self._show(k)

    def _show(self, k: int, animate: bool = True) -> None:
        old = self.pages.currentWidget()
        self.index = k
        new = self.pages.widget(k)
        if animate and anim.enabled() and old is not new:
            snap = QLabel(self.card)
            snap.setPixmap(old.grab())
            snap.setGeometry(old.geometry().translated(self.pages.pos()))
            snap.show()
            self.pages.setCurrentIndex(k)
            eff = QGraphicsOpacityEffect(new)
            new.setGraphicsEffect(eff)
            group = QParallelAnimationGroup(self)
            fade_in = QPropertyAnimation(eff, b"opacity")
            fade_in.setDuration(420)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            out = QPropertyAnimation(snap, b"pos")
            out.setDuration(380)
            out.setStartValue(snap.pos())
            out.setEndValue(snap.pos() + QPoint(-80, 0))
            out.setEasingCurve(QEasingCurve.Type.InCubic)
            snap_eff = QGraphicsOpacityEffect(snap)
            snap.setGraphicsEffect(snap_eff)
            fade_out = QPropertyAnimation(snap_eff, b"opacity")
            fade_out.setDuration(300)
            fade_out.setStartValue(1.0)
            fade_out.setEndValue(0.0)
            for a in (fade_in, out, fade_out):
                group.addAnimation(a)
            group.finished.connect(lambda: (snap.deleteLater(), new.setGraphicsEffect(None)))
            group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
            self._rise()
        else:
            self.pages.setCurrentIndex(k)
        self.dots.set_current(k)
        self.ocean.sail_to(k)
        self.retranslate()

    def _rise(self) -> None:
        """The page title rises into place."""
        for w, delay in ((self.title, 0), (self.sub, 90)):
            eff = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", w)
            a.setDuration(520 + delay)
            a.setStartValue(0.0)
            a.setKeyValueAt(delay / (520 + delay), 0.0)
            a.setEndValue(1.0)
            a.finished.connect(lambda w=w: w.setGraphicsEffect(None))
            a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _finish(self, tour: bool) -> None:
        if self.account is None:
            return
        self.finished.emit(self.account, self.remember, tour)

    def retranslate(self) -> None:
        k = self.index
        self.brand.setText(tr("app.name"))
        self.lang_quick.setText("English" if i18n.language() == "el" else "Ελληνικά")
        keys = ("account", "prefs", "tour")
        self.step_label.setText(theme.upper(tr("wel.step", n=k + 1, of=self.PAGES)))
        self.title.setText(tr(f"wel.{keys[k]}.title"))
        self.sub.setText(tr(f"wel.{keys[k]}.sub"))
        self.back_btn.setText(amp("←  " + tr("wel.back")))
        self.next_btn.setText(amp(tr("wel.next") + "  →"))
        self.back_btn.setVisible(k == 2)           # once signed in, the account page is behind us
        self.next_btn.setVisible(k == 1)
        self.account_page.retranslate()
        self.prefs_page.retranslate()
        self.tour_page.retranslate()
        for k2, t in self.prefs_page.lang_tiles.items():
            t.setChecked(k2 == i18n.language())
        for k2, t in self.prefs_page.theme_tiles.items():
            t.setChecked(k2 == theme.current().name)
        self.update()


def apply_theme(name: str) -> None:
    theme.set_current(theme.PALETTES.get(name, theme.DEFAULT))
    QApplication.instance().setStyleSheet(theme.stylesheet(theme.current()))
