"""Main window: a slim top bar over either the lobby or an open project."""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, i18n
from ..data.projects import Project, ProjectStore
from ..i18n import tr
from . import theme
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
    def __init__(self, state: AppState | None = None, store: ProjectStore | None = None):
        super().__init__()
        self.settings = QSettings()
        self.state = state or AppState()
        self.store = store or ProjectStore()
        self.resize(1440, 920)
        self.setMinimumSize(1100, 720)

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
        self.setCentralWidget(root)

        self.lobby.new_project.connect(self.new_project)
        self.lobby.open_project.connect(self.open_project)
        self.project_view.leave.connect(self.show_lobby)
        self.project_view.saved.connect(lambda _: self.saved_label.setText(tr("top.saved")))
        self.project_view.name_changed.connect(self.name_edit.setText)
        self.state.view_changed.connect(lambda val: self.view_switch.buttons[val].setChecked(True))
        self._unsubscribe = i18n.on_change(lambda _: self.retranslate())
        self.show_lobby()
        self.retranslate()

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
        self.version = label(f"v{__version__}", "TopLabel")
        h.addWidget(self.version)
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
        self.project_view.on_theme()
        self.lobby.bg.update()

    def retranslate(self) -> None:
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
