"""Step 1 · Ship: find the ship in EU MRV, check it, confirm its size."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...data import mrv
from ...engine import library as L
from ...engine import reference as R
from ...i18n import num, pick, tr
from .. import theme
from ..charts import StackedBarChart
from ..state import AppState
from ..widgets import Fold, Kpi, Panel, ReadMore, TrLabel, amp, label, size_label
from .base import Page

LIMIT = 500


class ResultsModel(QAbstractTableModel):
    KEYS = ("ship.col.imo", "ship.col.name", "ship.col.type", "ship.col.company", "ship.col.years")

    def __init__(self):
        super().__init__()
        self.rows: list[mrv.ShipSummary] = []

    def set_rows(self, rows: list[mrv.ShipSummary]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: B008, N802
        return len(self.KEYS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(self.KEYS[section])
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        s = self.rows[index.row()]
        years = str(s.first_year) if s.first_year == s.last_year else f"{s.first_year}–{s.last_year}"
        return (s.imo, s.name, s.ship_type, s.company_name or "", years)[index.column()]

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self.KEYS) - 1)


# ============================================================================ EU MRV import
class ImportWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)             # list[ImportResult] | Exception

    def __init__(self, files: list[Path], db: Path):
        super().__init__()
        self.files, self.db = files, db

    def run(self) -> None:
        try:
            self.finished.emit(mrv.import_files(self.files, self.db, progress=self.progress.emit))
        except Exception as e:  # noqa: BLE001 - shown to the user
            self.finished.emit(e)


class MrvImporter(QObject):
    """Import newer EMSA files from a folder, with a progress dialog (used from the lobby)."""

    def __init__(self, parent: QWidget, state: AppState):
        super().__init__(parent)
        self.parent_widget, self.state = parent, state

    def choose_and_import(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.parent_widget, tr("import.choose"))
        if folder:
            self.import_files(sorted(Path(folder).glob("*.xlsx")))

    def import_files(self, files: list[Path]) -> None:
        if not files:
            QMessageBox.information(self.parent_widget, tr("import.title"), tr("import.none"))
            return
        dlg = QProgressDialog(tr("import.title"), None, 0, len(files), self.parent_widget)
        dlg.setWindowTitle(tr("import.title"))
        dlg.setMinimumDuration(0)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        if self.state.db is not None:          # release the read-only handle while writing
            self.state.db.close()
            self.state.db = None
        self._thread = QThread(self)
        self._worker = ImportWorker(files, self.state.db_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda i, n, f: (dlg.setValue(i), dlg.setLabelText(tr("import.progress", file=f))))
        self._worker.finished.connect(lambda res: self._done(res, dlg))
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _done(self, result, dlg: QProgressDialog) -> None:
        dlg.close()
        self.state.reopen()
        if isinstance(result, Exception):
            QMessageBox.warning(self.parent_widget, tr("import.title"), tr("import.error", error=str(result)))
            return
        done = sum(not r.skipped for r in result)
        QMessageBox.information(self.parent_widget, tr("import.title"),
                                tr("import.done", n=done, skipped=len(result) - done))


# ============================================================================ ship card
class ShipDetail(QWidget):
    """The selected ship: identity and latest figures; full history folded underneath."""

    chosen = Signal(object)                  # mrv.ShipYear

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.history: list[mrv.ShipYear] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        head = Panel()
        top = QHBoxLayout()
        self.title = label("", "PageTitle")
        self.title.setWordWrap(True)
        top.addWidget(self.title, 1)
        self.use_btn = QPushButton()
        self.use_btn.setObjectName("Primary")
        self.use_btn.clicked.connect(self._use)
        top.addWidget(self.use_btn, 0, Qt.AlignmentFlag.AlignTop)
        head.body.addLayout(top)
        self.info = QWidget()
        info = QHBoxLayout(self.info)                # identity on the left, key figures on the right
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(36)
        head.body.addWidget(self.info)
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(18)
        self.form.setVerticalSpacing(4)
        self.fields: dict[str, tuple[TrLabel, object]] = {}
        for key in ("type", "company", "registry", "ice"):
            lab, val = TrLabel(f"ship.field.{key}", "Muted"), label("")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.form.addRow(lab, val)
            self.fields[key] = (lab, val)
        info.addLayout(self.form, 3)
        kg = QGridLayout()
        kg.setHorizontalSpacing(24)
        self.k_co2 = Kpi("ship.kpi.co2", year="")
        self.k_fuel = Kpi("ship.kpi.fuel")
        self.k_dist = Kpi("ship.kpi.distance")
        for i, k in enumerate((self.k_co2, self.k_fuel, self.k_dist)):
            kg.addWidget(k, 0, i)
            kg.setColumnStretch(i, 1)
        info.addLayout(kg, 4)

        self.details = Fold("ship.details")
        more = QFormLayout()
        more.setHorizontalSpacing(18)
        more.setVerticalSpacing(4)
        for key in ("tech", "methods"):
            lab, val = TrLabel(f"ship.field.{key}", "Muted"), label("")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            more.addRow(lab, val)
            self.fields[key] = (lab, val)
        self.k_sea = Kpi("ship.kpi.sea")
        self.k_ets = Kpi("ship.kpi.ets")
        km = QGridLayout()
        km.setHorizontalSpacing(24)
        km.addWidget(self.k_sea, 0, 0)
        km.addWidget(self.k_ets, 0, 1)
        self.details.body_layout.addLayout(more)
        self.details.body_layout.addLayout(km)
        self.details.body_layout.addWidget(TrLabel("ship.mrv_note", "Faint", wrap=True))
        cp = Panel("ship.chart.title")
        self.chart = StackedBarChart()
        cp.body.addWidget(self.chart)
        self.details.body_layout.addWidget(cp)
        self.table = QTableWidget(0, 8)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.table.setMinimumHeight(250)
        self.details.body_layout.addWidget(self.table)
        head.body.addWidget(self.details)          # history unfolds under the whole panel
        v.addWidget(head)
        v.addStretch(1)
        self.state.ship_changed.connect(lambda _: self._update_button())

    def show_ship(self, imo: str | None) -> None:
        db = self.state.db
        self.history = db.history(imo) if (db and imo) else []
        self.refresh()

    def refresh(self) -> None:
        h = self.history
        self.info.setVisible(bool(h))
        if not h:
            self.title.setText(tr("ship.pick"))
            self.use_btn.hide()
            return
        self.use_btn.show()
        last = self._latest_full()
        self.title.setText(f"{last.get('name', '')}  ·  IMO {last.imo}")
        tt, tv = last.get("tech_eff_type"), last.get("tech_eff_value")
        values = {"type": last.get("ship_type", "–"), "company": last.get("company_name", "–"),
                  "registry": (last.get("port_of_registry") or "–").title(), "ice": last.get("ice_class", "–"),
                  "tech": f"{tt} {num(tv, 2)} gCO2/t·nm" if tt and tv is not None else "–",
                  "methods": last.get("methods", "–")}
        for k, (_, val) in self.fields.items():
            val.setText(str(values[k]))
        self.k_co2.caption.set_key("ship.kpi.co2", year=last.year)
        self.k_co2.value.setText(num(last.get("co2_total", 0)))
        self.k_fuel.value.setText(num(last.get("fuel_total", 0)))
        self.k_dist.value.setText(num(last.get("distance_nm", 0)))
        self.k_sea.value.setText(num(last.get("time_at_sea", 0)))
        ets = last.ets_reported_co2e
        self.k_ets.value.setText(num(ets) if ets is not None else "–")

        p = theme.current()
        years = [y.year for y in h]
        splits = [y.emissions().co2 for y in h]
        series = [(tr("legend.intra"), [s.intra_eu for s in splits], p.fueleu),
                  (tr("legend.in_port"), [s.in_port for s in splits], p.good),
                  (tr("legend.from"), [s.from_eu for s in splits], p.ets),
                  (tr("legend.to"), [s.to_eu for s in splits], p.imo)]
        self.chart.set_data(years, series, (tr("legend.ets"), [y.ets_reported_co2e for y in h], p.warn))
        cols = ("ship.col.year", "ship.col.co2", "ship.col.fuel", "ship.col.distance", "ship.col.sea",
                "ship.col.co2nm", "ship.col.ets", "ship.col.note")
        self.table.setHorizontalHeaderLabels([tr(c) for c in cols])
        self.table.setRowCount(len(h))
        for i, y in enumerate(reversed(h)):
            per_nm = y.get("co2_per_nm")
            cells = [str(y.year), num(y.get("co2_total", 0)), num(y.get("fuel_total", 0)),
                     num(y.get("distance_nm", 0)), num(y.get("time_at_sea", 0)),
                     num(per_nm, 1) if per_nm else "–",
                     num(y.ets_reported_co2e) if y.ets_reported_co2e is not None else "–",
                     tr("ship.partial", n=y.n_reports) if y.partial else ""]
            for j, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if j < 7:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, it)
        self._update_button()

    def _latest_full(self) -> mrv.ShipYear | None:
        return next((y for y in reversed(self.history) if not y.partial), self.history[-1] if self.history else None)

    def _use(self) -> None:
        y = self._latest_full()
        self.state.use_ship(y)
        self.chosen.emit(y)

    def is_chosen(self) -> bool:
        cur = self.state.ship_year
        return bool(cur and self.history and cur.imo == self.history[-1].imo)

    def _update_button(self) -> None:
        active = self.is_chosen()
        self.use_btn.setText(amp(tr("ship.in_use" if active else "ship.use")))
        self.use_btn.setObjectName("Chosen" if active else "Primary")
        self.use_btn.style().unpolish(self.use_btn)
        self.use_btn.style().polish(self.use_btn)


# ============================================================================ standard ships
class StandardPane(QWidget):
    """Pick a standard ship: a named preset or any IMO type × size class, plus a trading pattern."""

    def __init__(self, state: AppState):
        from PySide6.QtWidgets import QButtonGroup

        from .position import Choice
        super().__init__()
        self.state = state
        self.key: str | None = None
        self.capacity: float | None = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        v.addWidget(TrLabel("std.presets", "SectionTitle"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.group = QButtonGroup(self)
        self.preset_buttons: dict[str, QPushButton] = {}
        for i, pr in enumerate(L.PRESETS):
            b = QPushButton()
            b.setObjectName("Preset")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=pr.key: self.pick_preset(k))
            self.group.addButton(b)
            grid.addWidget(b, i // 4, i % 4)
            self.preset_buttons[pr.key] = b
        v.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(TrLabel("std.any", "Muted"))
        self.type_box = QComboBox()
        self.class_box = QComboBox()
        self.class_box.setMinimumWidth(220)
        row.addWidget(self.type_box)
        row.addWidget(self.class_box)
        row.addStretch(1)
        v.addLayout(row)
        v.addWidget(TrLabel("std.pattern", "SectionTitle"))
        self.pattern = Choice([("deep_sea", "std.pattern.deep_sea"), ("mixed", "std.pattern.mixed"),
                               ("short_sea", "std.pattern.short_sea")])
        v.addWidget(self.pattern, 0, Qt.AlignmentFlag.AlignLeft)
        v.addWidget(ReadMore("std.pattern.more"))
        self.card = Panel()
        top = QHBoxLayout()
        self.title = label("", "PageTitle")
        self.title.setWordWrap(True)
        top.addWidget(self.title, 1)
        self.use_btn = QPushButton()
        self.use_btn.setObjectName("Primary")
        self.use_btn.clicked.connect(self._use)
        top.addWidget(self.use_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.card.body.addLayout(top)
        kg = QGridLayout()
        kg.setHorizontalSpacing(24)
        self.k = {key: Kpi(f"std.kpi.{key}") for key in ("dwt", "power", "speed", "days", "fuel")}
        for i, w in enumerate(self.k.values()):
            kg.addWidget(w, 0, i)
            kg.setColumnStretch(i, 1)
        self.card.body.addLayout(kg)
        self.card.body.addWidget(TrLabel("std.note", "Faint", wrap=True))
        v.addWidget(self.card)
        v.addStretch(1)
        self.pattern.picked.connect(lambda _: self._refresh())
        self.type_box.currentIndexChanged.connect(self._fill_classes)
        self.class_box.activated.connect(lambda _: self.pick_class(self.class_box.currentData()))
        state.standard_changed.connect(lambda _: self._update_button())
        state.ship_changed.connect(lambda _: self._update_button())
        self.retranslate()
        self.pick_preset("kamsarmax")

    def _fill_classes(self) -> None:
        t = self.type_box.currentData()
        self.class_box.blockSignals(True)
        self.class_box.clear()
        for c in L.library_classes():
            if c.type == t:
                self.class_box.addItem(size_label(c), c.key)
        self.class_box.blockSignals(False)

    def pick_preset(self, key: str) -> None:
        pr = L.preset(key)
        self.preset_buttons[key].setChecked(True)
        self.key, self.capacity, self.name = pr.cls, pr.capacity or None, pick(pr.name)
        self._sync_boxes()
        self._refresh()

    def pick_class(self, key: str | None) -> None:
        if not key:
            return
        self.group.setExclusive(False)
        for b in self.preset_buttons.values():
            b.setChecked(False)
        self.group.setExclusive(True)
        c = R.by_key(key)
        self.key, self.capacity, self.name = key, None, f"{c.label} {size_label(c)}"
        self._refresh()

    def _sync_boxes(self) -> None:
        c = R.by_key(self.key)
        self.type_box.blockSignals(True)
        self.type_box.setCurrentIndex(max(self.type_box.findData(c.type), 0))
        self.type_box.blockSignals(False)
        self._fill_classes()
        self.class_box.setCurrentIndex(max(self.class_box.findData(c.key), 0))

    def selection(self) -> tuple:
        c = R.by_key(self.key)
        pattern = self.pattern_value or L.DEFAULT_PATTERN.get(c.type, "deep_sea")
        return (self.key, pattern, self.capacity)

    @property
    def pattern_value(self) -> str | None:
        return next((k for k, b in self.pattern.buttons.items() if b.isChecked()), None)

    def _refresh(self) -> None:
        c = R.by_key(self.key)
        if self.pattern_value is None:
            self.pattern.set_value(L.DEFAULT_PATTERN.get(c.type, "deep_sea"))
        self.title.setText(self.name)
        cap = self.capacity or L.default_capacity(c, L.cii_type_of(c))
        unit = "GT" if L.cii_type_of(c) in ("vehicle", "roro", "ropax", "cruise") else "DWT"
        self.k["dwt"].caption.set_key("std.kpi.cap", unit=unit)
        self.k["dwt"].value.setText(num(cap) if cap else "–")
        self.k["power"].value.setText(num(c.value("power_kw")))
        self.k["speed"].value.setText(num(c.value("speed_at_sea"), 1))
        self.k["days"].value.setText(num(c.value("days_at_sea")))
        self.k["fuel"].value.setText(num(c.fuel_t()))
        self._update_button()

    def _use(self) -> None:
        self.state.use_standard(self.selection())

    def _update_button(self) -> None:
        cur = self.state.standard
        active = bool(cur and self.key and tuple(cur) == self.selection())
        self.use_btn.setText(amp(tr("ship.in_use" if active else "ship.use")))
        self.use_btn.setObjectName("Chosen" if active else "Primary")
        self.use_btn.style().unpolish(self.use_btn)
        self.use_btn.style().polish(self.use_btn)

    def retranslate(self) -> None:
        for pr in L.PRESETS:
            c = R.by_key(pr.cls)
            self.preset_buttons[pr.key].setText(f"{pick(pr.name)}\n{size_label(c)}")
        cur = self.type_box.currentData()
        self.type_box.blockSignals(True)
        self.type_box.clear()
        for t in L.LIBRARY_TYPES:
            if any(c.type == t for c in L.library_classes()):
                self.type_box.addItem(tr(f"std.type.{t}"), t)
        self.type_box.setCurrentIndex(max(self.type_box.findData(cur), 0))
        self.type_box.blockSignals(False)
        self.pattern.retranslate()
        if self.key:
            pr = next((p for p in L.PRESETS if p.cls == self.key and (p.capacity or None) == self.capacity), None)
            if pr:
                self.name = pick(pr.name)
            self._refresh()


# ============================================================================ step page
class StepShip(Page):
    title_key = "step.ship.q"
    lede_key = "step.ship.lede"
    title_style = ("Question", "QuestionLede")

    def __init__(self, state: AppState):
        from .position import Choice
        super().__init__(state)
        self.mode = Choice([("mrv", "std.mode.mrv"), ("standard", "std.mode.standard")])
        self.mode.set_value("mrv")
        self.lay.addWidget(self.mode, 0, Qt.AlignmentFlag.AlignLeft)
        self.mrv_pane = QWidget()
        mv = QVBoxLayout(self.mrv_pane)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(16)
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(420)
        bar.addWidget(self.search, 3)
        self.type_box = QComboBox()
        self.type_box.setMinimumWidth(220)
        bar.addWidget(self.type_box, 1)
        self.count = label("", "Muted")
        bar.addWidget(self.count)
        mv.addLayout(bar)

        self.empty = Panel()
        self.empty.body.addWidget(TrLabel("ship.no_data.title", "PanelTitle"))
        self.empty.body.addWidget(TrLabel("ship.no_data.body", "Muted", wrap=True))
        mv.addWidget(self.empty)

        # selected ship across the full width on top, the results table at full width below
        self.split = QWidget()
        sl = QVBoxLayout(self.split)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(12)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        self.detail = ShipDetail(state)
        rl.addWidget(self.detail)
        sl.addWidget(right)
        self.model = ResultsModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setVisible(False)
        self.view.setShowGrid(False)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setMinimumHeight(380)
        self.view.selectionModel().currentRowChanged.connect(self._row_changed)
        sl.addWidget(self.view, 1)
        mv.addWidget(self.split, 1)
        self.lay.addWidget(self.mrv_pane, 1)
        self.std_pane = StandardPane(state)
        self.std_pane.hide()
        self.lay.addWidget(self.std_pane, 1)
        self.mode.picked.connect(self.set_mode)

        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self.run_search)
        self.search.textChanged.connect(lambda _: self._timer.start())
        self.type_box.currentIndexChanged.connect(lambda _: self._timer.start())
        state.db_changed.connect(self.on_db)
        self.on_db()
        self.on_language()

    def set_mode(self, mode: str) -> None:
        self.mode.set_value(mode)
        self.mrv_pane.setVisible(mode == "mrv")
        self.std_pane.setVisible(mode == "standard")

    def on_db(self) -> None:
        db = self.state.db
        has = db is not None and db.count() > 0
        self.empty.setVisible(not has)
        self.split.setVisible(has)
        self.search.setEnabled(has)
        self.type_box.setEnabled(has)
        self.type_box.blockSignals(True)
        self.type_box.clear()
        self.type_box.addItem(tr("ship.type.all"), None)
        for t in (db.ship_types() if has else []):
            self.type_box.addItem(t, t)
        self.type_box.blockSignals(False)
        self.run_search()

    def run_search(self) -> None:
        db = self.state.db
        rows = db.search(self.search.text(), self.type_box.currentData(), limit=LIMIT) if db else []
        self.model.set_rows(rows)
        text = tr("ship.results", n=num(len(rows)))
        if len(rows) >= LIMIT:
            text += " · " + tr("ship.results.capped", n=num(LIMIT))
        self.count.setText(text)
        if rows:
            self.view.selectRow(0)
        else:
            self.detail.show_ship(None)

    def show_imo(self, imo: str) -> None:
        """Open the step on a given ship (when a saved project is reopened)."""
        self.search.blockSignals(True)
        self.search.setText(imo)
        self.search.blockSignals(False)
        self.run_search()

    def _row_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        if current.isValid():
            self.detail.show_ship(self.model.rows[current.row()].imo)

    def on_language(self) -> None:
        self.mode.retranslate()
        self.std_pane.retranslate()
        self.search.setPlaceholderText(tr("ship.search.placeholder"))
        if self.type_box.count():
            self.type_box.setItemText(0, tr("ship.type.all"))
        self.model.retranslate()
        self.count.setText(tr("ship.results", n=num(len(self.model.rows))))
        self.detail.refresh()

    def on_theme(self) -> None:
        self.detail.chart.restyle()
        self.detail.refresh()
