"""Main window: a slim top bar over either the lobby or an open project."""
from __future__ import annotations

import sys

from PySide6.QtCore import QProcess, QPropertyAnimation, QSettings, Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, i18n
from ..data import accounts as A
from ..data.projects import Project, ProjectStore
from ..i18n import tr
from . import anim, theme
from .lobby import Lobby
from .project_view import ProjectView
from .state import AppState
from .widgets import TrLabel, amp, label


class Segmented(QWidget):
    """Two or more mutually exclusive buttons (scope, language, theme)."""

    def __init__(self, options: list[tuple[str, str]], current: str, on_pick, small: bool = False):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for value, text in options:
            b = QPushButton(text)
            b.setObjectName("SegmentSmall" if small else "Segment")
            b.setCheckable(True)
            b.setChecked(value == current)
            b.clicked.connect(lambda _=False, v=value: on_pick(v))
            self.group.addButton(b)
            h.addWidget(b)
            self.buttons[value] = b


class MainWindow(QMainWindow):
    """`accounts` enables local accounts (decision 0015): with `welcome` the window opens on the
    set-up / sign-in pages; with `account` it opens straight into that account."""

    def __init__(self, state: AppState | None = None, store: ProjectStore | None = None,
                 accounts: A.AccountStore | None = None, account: A.Account | None = None,
                 welcome: str | None = None):
        super().__init__()
        self.settings = QSettings()
        self.state = state or AppState()
        self.accounts = accounts
        self.account: A.Account | None = None
        self.store = store or (ProjectStore(accounts.projects_dir(account)) if accounts and account else ProjectStore())
        self.resize(1440, 920)
        self.setMinimumSize(1100, 720)
        self.tour = None

        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._topbar())
        self.stack = QStackedWidget()
        self.lobby = Lobby(self.state, self.store)
        self.project_view = ProjectView(self.state, self.store)
        self.stack.addWidget(self.lobby)
        self.stack.addWidget(self.project_view)
        v.addWidget(self.stack, 1)
        self.app_widget = root
        self.screens = QStackedWidget()
        self.screens.addWidget(root)
        self.welcome = None
        self.setCentralWidget(self.screens)

        self.lobby.new_project.connect(self.new_project)
        self.lobby.open_project.connect(self.open_project)
        self.project_view.leave.connect(self.show_lobby)
        self.project_view.saved.connect(lambda _: self.saved_label.setText(tr("top.saved")))
        self.project_view.name_changed.connect(self.name_edit.setText)
        self.state.view_changed.connect(lambda val: self.view_switch.buttons[val].setChecked(True))
        self._unsubscribe = i18n.on_change(lambda _: self.retranslate())
        self.show_lobby()
        self.retranslate()
        if account is not None:
            self.sign_in_as(account, remember=None)
        if welcome:
            self.show_welcome(welcome)

    # ------------------------------------------------------------------ accounts (decision 0015)
    def show_welcome(self, mode: str = "signin") -> None:
        from .welcome import Welcome
        if self.welcome is not None:
            self.screens.removeWidget(self.welcome)
            self.welcome.deleteLater()
        self.welcome = Welcome(self.accounts, self.settings, mode)
        self.welcome.language_changed.connect(i18n.set_language)
        self.welcome.theme_changed.connect(self.set_theme)
        self.welcome.scale_changed.connect(self.set_scale)
        self.welcome.animations_changed.connect(lambda on: (self.anim_btn.setChecked(on), self.set_animations(on)))
        self.welcome.finished.connect(self._welcome_done)
        self.screens.addWidget(self.welcome)
        self.screens.setCurrentWidget(self.welcome)

    def _welcome_done(self, acc: A.Account, remember: bool, tour: bool) -> None:
        if self.accounts is not None and not self.accounts.setup_done:
            self.accounts.mark_setup_done()
        first_prefs = not acc.prefs
        self.sign_in_as(acc, remember, apply_prefs=not first_prefs)
        if first_prefs:                     # what was chosen on the preferences page becomes the account's
            self._save_prefs()
        w = self.welcome
        if anim.enabled() and w is not None:
            cover = QLabel(self)
            cover.setPixmap(w.grab())
            cover.setGeometry(self.centralWidget().geometry())
            cover.show()
            eff = QGraphicsOpacityEffect(cover)
            cover.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", cover)
            a.setDuration(650)
            a.setStartValue(1.0)
            a.setEndValue(0.0)
            a.finished.connect(cover.deleteLater)
            a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self.screens.setCurrentWidget(self.app_widget)
        if w is not None:
            self.screens.removeWidget(w)
            w.deleteLater()
            self.welcome = None
        if tour:
            self.start_tour()

    def sign_in_as(self, acc: A.Account, remember: bool | None = None, apply_prefs: bool = True) -> None:
        """Switch to an account: its projects, its preferences; `remember` keeps the session."""
        if self.stack.currentWidget() is self.project_view:
            self.project_view.save_now()
        self.account = acc
        if self.accounts is not None:
            if remember is not None:
                self.accounts.remember(acc if remember else None)
            self.set_store(ProjectStore(self.accounts.projects_dir(acc)))
        if apply_prefs and acc.prefs:
            pr = acc.prefs
            if pr.get("theme") in theme.PALETTES and pr["theme"] != theme.current().name:
                self.set_theme(pr["theme"])
            if "animations" in pr:
                self.anim_btn.setChecked(bool(pr["animations"]))
            if pr.get("language") in i18n.LANGUAGES:
                i18n.set_language(pr["language"])
        self.show_lobby()
        self._account_chip()

    def set_store(self, store: ProjectStore) -> None:
        self.store = store
        self.lobby.store = store
        self.project_view.store = store
        self.lobby.refresh()

    def sign_out(self) -> None:
        if self.accounts is None:
            return
        if self.stack.currentWidget() is self.project_view:
            self.project_view.save_now()
        self.show_lobby()
        self.accounts.remember(None)
        self.account = None
        self.show_welcome("signin")

    def _save_prefs(self) -> None:
        if self.accounts is not None and self.account is not None:
            self.accounts.set_prefs(self.account, language=i18n.language(), theme=theme.current().name,
                                    animations=anim.enabled())

    def _account_chip(self) -> None:
        acc = self.account
        self.account_btn.setVisible(acc is not None)
        if acc is None:
            return
        from .welcome import initials
        self.account_btn.setText(tr("acct.guest") if acc.is_guest else initials(acc.display_name))
        menu = QMenu(self)
        head = menu.addAction(tr("acct.guest.long") if acc.is_guest else f"{acc.display_name}  ·  {acc.username}")
        head.setEnabled(False)
        menu.addSeparator()
        menu.addAction(tr("acct.tour"), self.start_tour)
        size = menu.addMenu(tr("acct.scale"))
        grp = QActionGroup(size)
        cur = str(self.settings.value("ui_scale", "100"))
        from .welcome import SCALES
        for sc in SCALES:
            act = size.addAction(f"{sc}%")
            act.setCheckable(True)
            act.setChecked(sc == cur)
            grp.addAction(act)
            act.triggered.connect(lambda _=False, sc=sc: self.set_scale(sc, ask_restart=True))
        menu.addAction(tr("acct.terms"), self.show_terms)
        if not acc.is_guest:
            menu.addAction(tr("acct.password"), self.change_password)
        menu.addSeparator()
        if acc.is_guest:
            menu.addAction(tr("acct.create"), self.sign_out)
        else:
            menu.addAction(tr("acct.switch"), self.sign_out)
        self.account_btn.setMenu(menu)

    def _help_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(tr("help.tour"), self.start_tour)
        menu.addAction(tr("acct.terms"), self.show_terms)
        menu.addSeparator()
        menu.addAction(tr("help.about"), self.show_about)
        self.help_btn.setMenu(menu)
        self.help_btn.setToolTip(tr("help.menu"))

    def show_about(self) -> None:
        QMessageBox.about(self, tr("help.about"), tr("help.about.text", v=__version__))

    def show_terms(self) -> None:
        from .welcome import TermsDialog
        TermsDialog(self).exec()

    def change_password(self) -> None:
        acc = self.account
        if acc is None or acc.is_guest or self.accounts is None:
            return
        old, ok = QInputDialog.getText(self, tr("acct.password"), tr("auth.password"), QLineEdit.EchoMode.Password)
        if not ok:
            return
        new, ok = QInputDialog.getText(self, tr("acct.password"), tr("auth.password.new"), QLineEdit.EchoMode.Password)
        if not ok:
            return
        again, ok = QInputDialog.getText(self, tr("acct.password"), tr("auth.confirm"), QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            self.accounts.change_password(acc, old, new, again)
        except A.AccountError as e:
            QMessageBox.warning(self, tr("acct.password"), tr(e.code, **e.fmt))
            return
        QMessageBox.information(self, tr("acct.password"), tr("acct.password.done"))

    def set_scale(self, value: str, ask_restart: bool = False) -> None:
        """Interface size (QT_SCALE_FACTOR); takes effect at the next start."""
        if str(self.settings.value("ui_scale", "100")) == value:
            return
        self.settings.setValue("ui_scale", value)
        if ask_restart and QMessageBox.question(self, tr("acct.scale"), tr("acct.scale.restart")) == \
                QMessageBox.StandardButton.Yes:
            self.restart()

    def restart(self) -> None:
        if self.stack.currentWidget() is self.project_view:
            self.project_view.save_now()
        args = sys.argv[1:] if getattr(sys, "frozen", False) else ["-m", "navigator", *sys.argv[1:]]
        QProcess.startDetached(sys.executable, args)
        QApplication.quit()

    def start_tour(self) -> None:
        from .tour import Tour
        if self.tour is not None:
            self.tour.finish()
        self.tour = Tour(self)
        self.tour.finished.connect(self._tour_done)
        self.tour.begin()

    def _tour_done(self) -> None:
        self.tour = None
        if self.accounts is not None and self.account is not None:
            self.accounts.set_prefs(self.account, tour_done=True)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.stack.currentWidget() is self.project_view:
            self.project_view.save_now()
        self._unsubscribe()
        super().closeEvent(event)

    # ------------------------------------------------------------------ layout
    def _topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 9, 24, 9)
        h.setSpacing(10)
        # left: wordmark (lobby) or back + project name (project)
        self.brand = QWidget()
        bl = QVBoxLayout(self.brand)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.wordmark = TrLabel("app.name", "Wordmark")
        self.tagline = TrLabel("app.tagline", "WordmarkSub")
        bl.addWidget(self.wordmark)
        bl.addWidget(self.tagline)
        h.addWidget(self.brand)
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("Back")
        self.back_btn.clicked.connect(self.show_lobby)
        h.addWidget(self.back_btn)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("ProjectName")
        self.name_edit.editingFinished.connect(lambda: self.project_view.rename(self.name_edit.text()))
        h.addWidget(self.name_edit)
        self.saved_label = label("", "Saved")
        h.addWidget(self.saved_label)
        h.addStretch(1)
        # right: scope (project only), language, theme
        self.view_box = QWidget()
        vb = QHBoxLayout(self.view_box)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(8)
        self.view_label = TrLabel("top.view", "TopLabel")
        vb.addWidget(self.view_label)
        self.view_switch = Segmented([("eu", "EU"), ("ww", "WW")], self.state.view, self.state.set_view, small=True)
        vb.addWidget(self.view_switch)
        h.addWidget(self.view_box)
        h.addSpacing(14)
        self.lang_switch = Segmented([("el", "ΕΛ"), ("en", "EN")], i18n.language(), i18n.set_language, small=True)
        h.addWidget(self.lang_switch)
        h.addSpacing(8)
        self.theme_switch = Segmented([("light", "☀"), ("dark", "☾")], theme.current().name, self.set_theme, small=True)
        h.addWidget(self.theme_switch)
        h.addSpacing(8)
        self.anim_btn = QToolButton()
        self.anim_btn.setObjectName("AnimToggle")
        self.anim_btn.setText("\u2726")
        self.anim_btn.setCheckable(True)
        on = self.settings.value("animations", "1") != "0"
        anim.set_enabled(on and anim.enabled())
        self.anim_btn.setChecked(anim.enabled())
        self.anim_btn.toggled.connect(self.set_animations)
        h.addWidget(self.anim_btn)
        self.version = label(f"v{__version__}", "TopLabel")
        h.addWidget(self.version)
        h.addSpacing(6)
        self.help_btn = QToolButton()                      # always there: tour, terms, about
        self.help_btn.setObjectName("HelpChip")
        self.help_btn.setText("?")
        self.help_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(self.help_btn)
        self.account_btn = QToolButton()
        self.account_btn.setObjectName("AccountChip")
        self.account_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.account_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.account_btn.setVisible(False)
        h.addWidget(self.account_btn)
        return bar

    # ------------------------------------------------------------------ screens
    def _in_project(self, on: bool) -> None:
        self.brand.setVisible(not on)
        for w in (self.back_btn, self.name_edit, self.saved_label, self.view_box):
            w.setVisible(on)

    def show_lobby(self) -> None:
        if self.stack.currentWidget() is self.project_view:
            self.project_view.save_now()
        self.lobby.refresh()
        self.stack.setCurrentWidget(self.lobby)
        self._in_project(False)

    def new_project(self) -> None:
        p = Project()
        self.store.save(p)
        self._show_project(p)

    def open_project(self, pid: str) -> None:
        self._show_project(self.store.load(pid))

    def _show_project(self, p: Project) -> None:
        self.project_view.open(p)
        self.name_edit.setText(p.name)
        self.name_edit.setPlaceholderText(tr("lobby.untitled"))
        self.saved_label.setText("")
        self.stack.setCurrentWidget(self.project_view)
        self._in_project(True)

    # ------------------------------------------------------------------ language / theme
    def set_theme(self, name: str) -> None:
        theme.set_current(theme.PALETTES[name])
        QApplication.instance().setStyleSheet(theme.stylesheet(theme.current()))
        self.settings.setValue("theme", name)
        self.theme_switch.buttons[name].setChecked(True)
        self.project_view.on_theme()
        self.lobby.bg.update()
        if self.welcome is not None:
            self.welcome.retranslate()
        if self.welcome is None:
            self._save_prefs()

    def set_animations(self, on: bool) -> None:
        anim.set_enabled(on)
        self.settings.setValue("animations", "1" if on else "0")
        if self.welcome is None:
            self._save_prefs()

    def retranslate(self) -> None:
        self.anim_btn.setToolTip(tr("top.anim"))
        self.settings.setValue("language", i18n.language())
        self.setWindowTitle(tr("app.name"))
        for w in (self.wordmark, self.tagline, self.view_label):
            w.retranslate()
        self.view_switch.setToolTip(tr("top.view.tip"))
        self.back_btn.setText(amp("←  " + tr("top.projects")))
        self.name_edit.setPlaceholderText(tr("lobby.untitled"))
        self.theme_switch.buttons["light"].setToolTip(tr("theme.light"))
        self.theme_switch.buttons["dark"].setToolTip(tr("theme.dark"))
        self.lobby.retranslate()
        self.project_view.retranslate()
        self.lang_switch.buttons[i18n.language()].setChecked(True)
        self.account_btn.setToolTip(tr("acct.menu"))
        self._help_menu()
        if getattr(self, "account", None) is not None:
            self._account_chip()
            if self.welcome is None:
                self._save_prefs()
