"""A project: the six steps on a route line, with Back/Continue and automatic saving."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ..data.projects import Project, ProjectStore
from ..i18n import tr
from .pages.options import StepOptions
from .pages.position import StepPosition, StepUpcoming
from .pages.ship import StepShip
from .state import AppState
from .stepper import RouteStepper
from .widgets import amp, label, size_label

STEP_KEYS = ["step.1", "step.2", "step.3", "step.4", "step.5", "step.6"]


class ProjectView(QWidget):
    saved = Signal(str)            # project id
    name_changed = Signal(str)
    leave = Signal()

    def __init__(self, state: AppState, store: ProjectStore):
        super().__init__()
        self.state, self.store = state, store
        self.project: Project | None = None
        self._loading = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("StepBar")
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(24, 10, 24, 6)
        self.stepper = RouteStepper(STEP_KEYS)
        bl.addWidget(self.stepper)
        v.addWidget(bar)

        body = QWidget()
        body.setObjectName("ProjectBody")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.ship_step = StepShip(state)
        self.position_step = StepPosition(state)
        self.options_step = StepOptions(state, self.position_step)
        self.steps = [self.ship_step, self.position_step, self.options_step, StepUpcoming(state, 4, 4, 3),
                      StepUpcoming(state, 5, 4, 3), StepUpcoming(state, 6, 5, 3)]
        for s in self.steps:
            self.stack.addWidget(s)
        bv.addWidget(self.stack)
        v.addWidget(body, 1)

        nav = QFrame()
        nav.setObjectName("NavBar")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(40, 12, 40, 12)
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("Ghost")
        self.back_btn.clicked.connect(lambda: self.go(self.current - 1))
        nl.addWidget(self.back_btn)
        nl.addStretch(1)
        self.hint = label("", "StepHint")
        nl.addWidget(self.hint)
        nl.addStretch(1)
        self.next_btn = QPushButton()
        self.next_btn.setObjectName("Primary")
        self.next_btn.clicked.connect(self._continue)
        nl.addWidget(self.next_btn)
        v.addWidget(nav)

        self.current = 0
        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self.save_now)
        self.stepper.picked.connect(self.go)
        self.ship_step.detail.chosen.connect(self._ship_chosen)
        state.standard_changed.connect(self._standard_chosen)
        self.position_step.computed.connect(self._dirty)
        self.options_step.changed.connect(self._dirty)
        state.ship_changed.connect(lambda _: self._refresh_nav())
        state.view_changed.connect(lambda _: self._dirty())

    # ------------------------------------------------------------------ open / save
    def open(self, project: Project) -> None:
        self._loading = True
        try:
            self.project = project
            self.state.set_view(project.view if project.view in ("eu", "ww") else "eu")
            inputs = self.position_step.inputs
            self.state.ship_year = None
            if project.inputs:
                inputs.restore(project.inputs, self.state.db)
            else:
                inputs.reset_example()
            self.state.ship_year, self.state.standard = inputs.loaded, inputs.standard
            self.state.ship_changed.emit(None)          # refresh buttons without reloading inputs
            if inputs.loaded is not None:
                self.ship_step.set_mode("mrv")
                self.ship_step.show_imo(inputs.loaded.imo)
            elif inputs.standard is not None:
                self.ship_step.set_mode("standard")
            self.position_step.recompute()
            self.options_step.restore(project.inputs.get("options") if project.inputs else None)
            self.current = 0
            self.go(min(project.step, project.reached), save=False)
        finally:
            self._loading = False

    def _dirty(self) -> None:
        if not self._loading and self.project is not None:
            self._save_timer.start()

    def save_now(self) -> None:
        if self.project is None:
            return
        p = self.project
        inputs = self.position_step.inputs
        p.inputs = {**inputs.snapshot(), "options": self.options_step.snapshot()}
        p.view = self.state.view
        y = inputs.loaded
        p.ship = {"imo": y.imo, "year": y.year, "name": y.get("name", ""), "type": y.get("ship_type", "")} if y else None
        if inputs.standard:
            from ..engine import reference as R
            c = R.by_key(inputs.standard[0])
            p.ship = {"imo": "", "year": 2018, "name": self.ship_step.std_pane.name, "type": f"{c.label} {size_label(c)}"}
        p.summary = self.position_step.summary()
        p.step, p.reached = self.current, max(p.reached, self.current)
        self.store.save(p)
        self.saved.emit(p.id)

    def rename(self, name: str) -> None:
        if self.project is not None:
            self.project.name = name.strip()
            self._dirty()

    # ------------------------------------------------------------------ navigation
    def _ship_chosen(self, ship_year) -> None:
        if self.project is not None and not self.project.name and ship_year is not None:
            self.project.name = ship_year.get("name", "")
            self.name_changed.emit(self.project.name)
        self._refresh_nav()
        self._dirty()

    def _standard_chosen(self, std) -> None:
        if self.project is not None and not self.project.name and std is not None:
            self.project.name = self.ship_step.std_pane.name
            self.name_changed.emit(self.project.name)
        self._refresh_nav()
        self._dirty()

    def can_continue(self) -> bool:
        return self.current != 0 or self.state.has_ship

    def _continue(self) -> None:
        if self.current == len(self.steps) - 1:
            self.save_now()
            self.leave.emit()
        elif self.can_continue():
            if self.project is not None:
                self.project.reached = max(self.project.reached, self.current + 1)
            self.go(self.current + 1)

    def go(self, i: int, save: bool = True) -> None:
        reached = self.project.reached if self.project else 0
        if not 0 <= i < len(self.steps) or i > max(reached, self.current):
            return
        self.current = i
        self.stack.setCurrentIndex(i)
        self.stepper.set_state(i, reached)
        self._refresh_nav()
        if save:
            self._dirty()

    def _refresh_nav(self) -> None:
        i, n = self.current, len(self.steps)
        self.back_btn.setVisible(i > 0)
        self.back_btn.setText(amp("←  " + tr(STEP_KEYS[i - 1]))) if i > 0 else None
        if i == n - 1:
            self.next_btn.setText(amp(tr("nav.finish")))
        else:
            self.next_btn.setText(amp(tr("nav.continue", step=tr(STEP_KEYS[i + 1])) + "  →"))
        self.next_btn.setEnabled(self.can_continue())
        self.hint.setText(tr("nav.hint.ship") if (i == 0 and not self.can_continue())
                          else tr("nav.step_of", i=i + 1, n=n))

    def retranslate(self) -> None:
        for s in self.steps:
            s.retranslate()
        self.stepper.update()
        self._refresh_nav()

    def on_theme(self) -> None:
        for s in self.steps:
            s.on_theme()
        self.stepper.update()
