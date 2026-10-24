"""Main window: sidebar navigation, top bar with language and theme switches, page stack."""
from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, i18n
from ..i18n import tr
from . import theme
from .pages import DecisionPage, MeasuresPage, RegulationPage, ReportPage, ShipPage, UncertaintyPage
from .widgets import TrLabel, amp, label

NAV = [
    ("nav.group.inputs", [("nav.ship", ShipPage), ("nav.measures", MeasuresPage),
                          ("nav.regulation", RegulationPage)]),
    ("nav.group.analysis", [("nav.decision", DecisionPage), ("nav.uncertainty", UncertaintyPage)]),
    ("nav.group.output", [("nav.report", ReportPage)]),
]
START_PAGE = "nav.regulation"   # the only working page in Phase 0


class Segmented(QWidget):
    """Two or more mutually exclusive buttons (language, theme)."""

    def __init__(self, options: list[tuple[str, str]], current: str, on_pick):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for value, text in options:
            b = QPushButton(text)
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setChecked(value == current)
            b.clicked.connect(lambda _=False, v=value: on_pick(v))
            self.group.addButton(b)
            h.addWidget(b)
            self.buttons[value] = b


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._sidebar())
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._topbar())
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        h.addLayout(right, 1)
        self.setCentralWidget(root)

        self.pages = []
        for _, items in NAV:
            for _, cls in items:
                page = cls()
                self.pages.append(page)
                self.stack.addWidget(page)
        keys = [k for _, items in NAV for k, _ in items]
        self.go(keys.index(START_PAGE))
        self._unsubscribe = i18n.on_change(lambda _: self.retranslate())
        self.retranslate()

    def closeEvent(self, event) -> None:
        self._unsubscribe()
        super().closeEvent(event)

    # ------------------------------------------------------------------ layout
    def _sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(248)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 22, 0, 14)
        v.setSpacing(0)
        self.wordmark = TrLabel("app.name", "Wordmark", wrap=True)
        self.wordmark.setContentsMargins(18, 0, 12, 0)
        self.tagline = TrLabel("app.tagline", "WordmarkSub", wrap=True)
        self.tagline.setContentsMargins(18, 4, 12, 10)
        v.addWidget(self.wordmark)
        v.addWidget(self.tagline)
        self.nav_labels: list[TrLabel] = []
        self.nav_buttons: list[tuple[QPushButton, str]] = []
        idx = 0
        for group, items in NAV:
            g = TrLabel(group, "NavGroup")
            self.nav_labels.append(g)
            v.addWidget(g)
            for key, _ in items:
                b = QPushButton()
                b.setObjectName("NavButton")
                b.setCheckable(True)
                b.clicked.connect(lambda _=False, i=idx: self.go(i))
                v.addWidget(b)
                self.nav_buttons.append((b, key))
                idx += 1
        v.addStretch(1)
        version = label(f"v{__version__}", "Faint")
        version.setContentsMargins(18, 0, 0, 0)
        v.addWidget(version)
        return side

    def _topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 8, 24, 8)
        h.setSpacing(10)
        h.addStretch(1)
        self.lang_label = TrLabel("top.language", "TopLabel")
        h.addWidget(self.lang_label)
        self.lang_switch = Segmented([("el", "ΕΛ"), ("en", "EN")], i18n.language(), i18n.set_language)
        h.addWidget(self.lang_switch)
        h.addSpacing(14)
        self.theme_label = TrLabel("top.theme", "TopLabel")
        h.addWidget(self.theme_label)
        self.theme_switch = Segmented([("dark", ""), ("light", "")], theme.current().name, self.set_theme)
        h.addWidget(self.theme_switch)
        return bar

    # ------------------------------------------------------------------ actions
    def go(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        for j, (b, _) in enumerate(self.nav_buttons):
            b.setChecked(j == i)

    def set_theme(self, name: str) -> None:
        theme.set_current(theme.PALETTES[name])
        QApplication.instance().setStyleSheet(theme.stylesheet(theme.current()))
        self.settings.setValue("theme", name)
        for p in self.pages:
            p.on_theme()

    def retranslate(self) -> None:
        self.settings.setValue("language", i18n.language())
        self.setWindowTitle(tr("app.name"))
        for w in (self.wordmark, self.tagline, self.lang_label, self.theme_label, *self.nav_labels):
            w.retranslate()
        for b, key in self.nav_buttons:
            b.setText(amp(tr(key)))
        self.theme_switch.buttons["dark"].setText(tr("theme.dark"))
        self.theme_switch.buttons["light"].setText(tr("theme.light"))
        for p in self.pages:
            p.retranslate()
        reg = next(p for p in self.pages if isinstance(p, RegulationPage))
        n = reg.unverified_count()
        msg = tr("status.ready") + (("  ·  " + tr("status.unverified", n=n)) if n else "")
        self.statusBar().showMessage(msg)
