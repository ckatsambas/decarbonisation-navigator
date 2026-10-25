"""Page scaffolding: scrolling content with a title and lede, plus language/theme hooks."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..widgets import Fold, ReadMore, TrLabel


class Page(QScrollArea):
    title_key = ""
    lede_key = ""
    title_style = ("PageTitle", "PageLede")

    def __init__(self, state=None):
        super().__init__()
        self.state = state
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("Content")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(56, 30, 56, 40)
        self.lay.setSpacing(16)
        self.title_label = TrLabel(self.title_key, self.title_style[0], wrap=True)
        self.lay.addWidget(self.title_label)
        if self.lede_key:
            lede = TrLabel(self.lede_key, self.title_style[1], wrap=True)
            lede.setMaximumWidth(900)
            self.lay.addWidget(lede)
        self.setWidget(inner)

    def retranslate(self) -> None:
        """Redraw every bound label, then let the page update its own content."""
        for lab in self.findChildren(TrLabel):
            lab.retranslate()
        for w in [*self.findChildren(Fold), *self.findChildren(ReadMore)]:
            w.retranslate()
        self.on_language()

    def on_language(self) -> None:  # pragma: no cover - overridden where needed
        pass

    def on_theme(self) -> None:  # pragma: no cover - overridden where needed
        pass
