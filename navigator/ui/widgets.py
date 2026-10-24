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

    def __init__(self, key: str, name: str | None = None, wrap: bool = False, **fmt):
        super().__init__()
        self.key, self.fmt = key, fmt
        if name:
            self.setObjectName(name)
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
