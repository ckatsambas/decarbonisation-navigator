"""Lobby: the home screen with the user's projects and a way to start a new one."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..data.projects import SUFFIX, Project, ProjectStore
from ..i18n import eur_short, num, tr
from .pages.ship import MrvImporter
from .project_view import STEP_KEYS
from .state import AppState
from .widgets import ContourBackground, TrLabel, amp, label

COLUMNS = 3


def short_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


class ClickFrame(QFrame):
    clicked = Signal()

    def __init__(self, name: str):
        super().__init__()
        self.setObjectName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(178)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()


class ProjectCard(ClickFrame):
    action = Signal(str, str)               # action, project id

    def __init__(self, p: Project):
        super().__init__("Card")
        self.project = p
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 14, 16)
        v.setSpacing(6)
        top = QHBoxLayout()
        title = label(p.name or tr("lobby.untitled"), "CardTitle")
        title.setWordWrap(True)
        top.addWidget(title, 1)
        menu_btn = QToolButton()
        menu_btn.setObjectName("CardMenu")
        menu_btn.setText("⋯")
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(menu_btn)
        for key in ("open", "rename", "duplicate", "export", "delete"):
            menu.addAction(tr(f"lobby.menu.{key}"), lambda k=key: self.action.emit(k, p.id))
        menu_btn.setMenu(menu)
        top.addWidget(menu_btn, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)
        ship = p.ship or {}
        meta = (f"{ship.get('name', '')} · IMO {ship.get('imo', '')} · {ship.get('type', '')}"
                if ship else tr("lobby.no_ship"))
        m = label(meta, "CardMeta")
        m.setWordWrap(True)
        v.addWidget(m)
        v.addStretch(1)
        total = (p.summary or {}).get("total_eur")
        if total is not None and ship:
            v.addWidget(label(tr("lobby.card.cost"), "CardValueLabel"))
            v.addWidget(label(eur_short(total), "CardValue"))
        step = min(p.step, len(STEP_KEYS) - 1)
        v.addWidget(label(tr("lobby.card.progress", i=step + 1, n=len(STEP_KEYS), step=tr(STEP_KEYS[step]))
                          + "  ·  " + short_date(p.updated), "CardMeta"))
        self.clicked.connect(lambda: self.action.emit("open", p.id))


class Lobby(QScrollArea):
    open_project = Signal(str)
    new_project = Signal()

    def __init__(self, state: AppState, store: ProjectStore):
        super().__init__()
        self.state, self.store = state, store
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.bg = ContourBackground()
        self.bg.setObjectName("Lobby")
        outer = QHBoxLayout(self.bg)
        outer.setContentsMargins(40, 54, 40, 30)
        col = QWidget()
        col.setMaximumWidth(1180)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        outer.addStretch(1)
        outer.addWidget(col, 12)
        outer.addStretch(1)

        v.addWidget(TrLabel("lobby.eyebrow", "Eyebrow"))
        hero = TrLabel("lobby.hero", "Hero", wrap=True)
        hero.setMaximumWidth(820)
        v.addWidget(hero)
        lede = TrLabel("lobby.lede", "HeroLede", wrap=True)
        lede.setMaximumWidth(760)
        v.addWidget(lede)
        v.addSpacing(14)
        actions = QHBoxLayout()
        self.new_btn = QPushButton()
        self.new_btn.setObjectName("Primary")
        self.new_btn.clicked.connect(self.new_project.emit)
        actions.addWidget(self.new_btn)
        self.import_btn = QPushButton()
        self.import_btn.setObjectName("Ghost")
        self.import_btn.clicked.connect(self.import_project)
        actions.addWidget(self.import_btn)
        actions.addStretch(1)
        v.addLayout(actions)
        v.addSpacing(26)
        v.addWidget(TrLabel("lobby.projects", "SectionTitle"))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        v.addLayout(self.grid)
        v.addStretch(1)
        v.addSpacing(30)
        foot = QHBoxLayout()
        self.footer = label("", "Footer")
        foot.addWidget(self.footer)
        self.update_btn = QPushButton()
        self.update_btn.setObjectName("Link")
        self.importer = MrvImporter(self, state)
        self.update_btn.clicked.connect(self.importer.choose_and_import)
        foot.addWidget(self.update_btn)
        foot.addStretch(1)
        v.addLayout(foot)
        self.setWidget(self.bg)
        state.db_changed.connect(self._footer)
        self.refresh()

    # ------------------------------------------------------------------ content
    def refresh(self) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        new = ClickFrame("NewCard")
        nv = QVBoxLayout(new)
        nv.setContentsMargins(20, 18, 20, 18)
        nv.addStretch(1)
        nv.addWidget(label("+", "NewCardTitle"))
        nv.addWidget(label(tr("lobby.new.title"), "NewCardTitle"))
        hint = label(tr("lobby.new.hint"), "CardMeta")
        hint.setWordWrap(True)
        nv.addWidget(hint)
        nv.addStretch(1)
        new.clicked.connect(self.new_project.emit)
        cards: list[QWidget] = [new]
        for p in self.store.list():
            c = ProjectCard(p)
            c.action.connect(self._action)
            cards.append(c)
        for i, c in enumerate(cards):
            self.grid.addWidget(c, i // COLUMNS, i % COLUMNS)
        for col in range(COLUMNS):
            self.grid.setColumnStretch(col, 1)
        self._footer()
        self._texts()

    def _footer(self) -> None:
        db = self.state.db
        rel = db.releases() if db else []
        if rel:
            last = rel[-1]
            self.footer.setText(tr("lobby.data", ships=num(db.count()), first=rel[0].year, last=last.year,
                                   version=last.version))
        else:
            self.footer.setText(tr("ship.no_data.title"))

    def _texts(self) -> None:
        self.new_btn.setText(amp("+  " + tr("lobby.new")))
        self.import_btn.setText(amp(tr("lobby.import")))
        self.update_btn.setText(amp(tr("lobby.update")))

    def retranslate(self) -> None:
        for lab in self.findChildren(TrLabel):
            lab.retranslate()
        self.refresh()

    # ------------------------------------------------------------------ card actions
    def _action(self, action: str, pid: str) -> None:
        if action == "open":
            self.open_project.emit(pid)
        elif action == "rename":
            p = self.store.load(pid)
            name, ok = QInputDialog.getText(self, tr("lobby.menu.rename"), tr("lobby.name"), text=p.name)
            if ok:
                p.name = name.strip()
                self.store.save(p)
                self.refresh()
        elif action == "duplicate":
            p = self.store.load(pid)
            self.store.duplicate(pid, tr("lobby.copy_of", name=p.name or tr("lobby.untitled")))
            self.refresh()
        elif action == "export":
            p = self.store.load(pid)
            target, _ = QFileDialog.getSaveFileName(self, tr("lobby.menu.export"),
                                                    str(Path.home() / f"{p.name or 'project'}{SUFFIX}"),
                                                    tr("lobby.filter", suffix=SUFFIX))
            if target:
                self.store.export(pid, Path(target))
        elif action == "delete":
            p = self.store.load(pid)
            if QMessageBox.question(self, tr("lobby.menu.delete"),
                                    tr("lobby.delete.confirm", name=p.name or tr("lobby.untitled"))) \
                    == QMessageBox.StandardButton.Yes:
                self.store.delete(pid)
                self.refresh()

    def import_project(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, tr("lobby.import"), str(Path.home()),
                                                tr("lobby.filter", suffix=SUFFIX))
        if source:
            try:
                p = self.store.import_file(Path(source))
            except (OSError, ValueError, TypeError) as e:
                QMessageBox.warning(self, tr("lobby.import"), tr("lobby.import.error", error=str(e)))
                return
            self.refresh()
            self.open_project.emit(p.id)
