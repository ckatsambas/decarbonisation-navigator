"""Page scaffolding: scrolling content with a title and lede, plus language/theme hooks."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..widgets import TrLabel


class Page(QScrollArea):
    title_key = ""
    lede_key = ""

    def __init__(self, state=None):
        super().__init__()
        self.state = state
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("Content")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(32, 26, 32, 32)
        self.lay.setSpacing(16)
        self.lay.addWidget(TrLabel(self.title_key, "PageTitle"))
        if self.lede_key:
            lede = TrLabel(self.lede_key, "PageLede", wrap=True)
            lede.setMaximumWidth(900)
            self.lay.addWidget(lede)
        self.setWidget(inner)

    def retranslate(self) -> None:
        """Redraw every bound label, then let the page update its own content."""
        for lab in self.findChildren(TrLabel):
            lab.retranslate()
        self.on_language()

    def on_language(self) -> None:  # pragma: no cover - overridden where needed
        pass

    def on_theme(self) -> None:  # pragma: no cover - overridden where needed
        pass


class PlaceholderPage(Page):
    """A page whose content arrives in a later phase."""

    phase = 1

    def __init__(self, state=None):
        super().__init__(state)
        self.lay.addWidget(TrLabel("placeholder.phase", "Placeholder", n=self.phase))
        self.lay.addStretch(1)


def placeholder(title: str, lede: str, phase: int) -> type[PlaceholderPage]:
    return type(f"Placeholder_{title}", (PlaceholderPage,),
                {"title_key": title, "lede_key": lede, "phase": phase})
