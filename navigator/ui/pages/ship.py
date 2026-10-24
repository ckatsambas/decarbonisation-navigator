"""Ship page: search the EU MRV database, inspect a ship's history, send it to the analysis."""
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
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...data import mrv
from ...i18n import num, tr
from .. import theme
from ..charts import StackedBarChart
from ..state import AppState
from ..widgets import Kpi, Panel, TrLabel, amp, label
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

    def rowCount(self, parent=QModelIndex()):  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: B008
        return len(self.KEYS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
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


class ShipDetail(QWidget):
    """Identity, latest-year figures, history chart and table for one ship."""

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
        info = QVBoxLayout(self.info)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(10)
        head.body.addWidget(self.info)
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(18)
        self.form.setVerticalSpacing(4)
        self.fields: dict[str, tuple[TrLabel, object]] = {}
        for key in ("type", "company", "registry", "ice", "tech", "methods"):
            lab, val = TrLabel(f"ship.field.{key}", "Muted"), label("")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.form.addRow(lab, val)
            self.fields[key] = (lab, val)
        info.addLayout(self.form)
        kg = QGridLayout()
        kg.setHorizontalSpacing(24)
        self.k_co2 = Kpi("ship.kpi.co2", year="")
        self.k_fuel = Kpi("ship.kpi.fuel")
        self.k_dist = Kpi("ship.kpi.distance")
        self.k_sea = Kpi("ship.kpi.sea")
        self.k_ets = Kpi("ship.kpi.ets")
        for i, k in enumerate((self.k_co2, self.k_fuel, self.k_dist, self.k_sea, self.k_ets)):
            kg.addWidget(k, 0, i)
            kg.setColumnStretch(i, 1)
        info.addLayout(kg)
        info.addWidget(TrLabel("ship.mrv_note", "Faint", wrap=True))
        v.addWidget(head)

        self.chart_panel = Panel("ship.chart.title")
        self.chart = StackedBarChart()
        self.chart_panel.body.addWidget(self.chart)
        v.addWidget(self.chart_panel)

        self.table = QTableWidget(0, 8)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.table.setMinimumHeight(250)
        v.addWidget(self.table)
        self.state.ship_changed.connect(lambda _: self._update_button())

    def show_ship(self, imo: str | None) -> None:
        db = self.state.db
        self.history = db.history(imo) if (db and imo) else []
        self.refresh()

    def refresh(self) -> None:
        h = self.history
        for w in (self.info, self.chart_panel, self.table):
            w.setVisible(bool(h))
        if not h:
            self.title.setText(tr("ship.pick"))
            self.use_btn.hide()
            return
        self.use_btn.show()
        last = next((y for y in reversed(h) if not y.partial), h[-1])
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
        self.state.use_ship(self._latest_full())

    def _update_button(self) -> None:
        cur = self.state.ship_year
        active = bool(cur and self.history and cur.imo == self.history[-1].imo)
        self.use_btn.setText(amp(tr("ship.in_use" if active else "ship.use")))
        self.use_btn.setEnabled(not active)


class ShipPage(Page):
    title_key = "page.ship.title"
    lede_key = "page.ship.lede"

    def __init__(self, state: AppState):
        super().__init__(state)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(360)
        bar.addWidget(self.search, 2)
        self.type_box = QComboBox()
        self.type_box.setMinimumWidth(220)
        bar.addWidget(self.type_box, 1)
        self.count = label("", "Muted")
        bar.addWidget(self.count)
        bar.addStretch(1)
        self.import_btn = QPushButton()
        self.import_btn.clicked.connect(self.import_folder)
        bar.addWidget(self.import_btn)
        self.lay.addLayout(bar)
        self.status = label("", "Faint")
        self.lay.addWidget(self.status)

        self.empty = Panel()
        self.empty.body.addWidget(TrLabel("ship.no_data.title", "PanelTitle"))
        self.empty.body.addWidget(TrLabel("ship.no_data.body", "Muted", wrap=True))
        self.lay.addWidget(self.empty)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.model = ResultsModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setVisible(False)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setMinimumWidth(420)
        self.view.selectionModel().currentRowChanged.connect(self._row_changed)
        self.split.addWidget(self.view)
        self.detail = ShipDetail(state)
        self.split.addWidget(self.detail)
        self.split.setStretchFactor(0, 2)
        self.split.setStretchFactor(1, 3)
        self.split.setMinimumHeight(900)
        self.lay.addWidget(self.split, 1)

        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self.run_search)
        self.search.textChanged.connect(lambda _: self._timer.start())
        self.type_box.currentIndexChanged.connect(lambda _: self._timer.start())
        state.db_changed.connect(self.on_db)
        self.on_db()

    # ------------------------------------------------------------------ data
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
        self._status()
        self.run_search()

    def _status(self) -> None:
        db = self.state.db
        rel = db.releases() if db else []
        if not rel:
            self.status.setText("")
            return
        last = rel[-1]
        gen = "/".join(reversed(last.generated.split("-"))) if last.generated else "–"
        self.status.setText(tr("ship.data_status", ships=num(db.count()), first=rel[0].year, last=last.year,
                               year=last.year, version=last.version, date=gen))

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

    def _row_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        if current.isValid():
            self.detail.show_ship(self.model.rows[current.row()].imo)

    # ------------------------------------------------------------------ import
    def import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("import.choose"))
        if folder:
            self.import_files(sorted(Path(folder).glob("*.xlsx")))

    def import_files(self, files: list[Path]) -> None:
        if not files:
            QMessageBox.information(self, tr("import.title"), tr("import.none"))
            return
        dlg = QProgressDialog(tr("import.title"), None, 0, len(files), self)
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
        self._worker.finished.connect(lambda res: self._import_done(res, dlg))
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _import_done(self, result, dlg: QProgressDialog) -> None:
        dlg.close()
        self.state.reopen()
        if isinstance(result, Exception):
            QMessageBox.warning(self, tr("import.title"), tr("import.error", error=str(result)))
            return
        done = sum(not r.skipped for r in result)
        QMessageBox.information(self, tr("import.title"), tr("import.done", n=done, skipped=len(result) - done))

    # ------------------------------------------------------------------ language / theme
    def on_language(self) -> None:
        self.search.setPlaceholderText(tr("ship.search.placeholder"))
        self.import_btn.setText(amp(tr("ship.import")))
        if self.type_box.count():
            self.type_box.setItemText(0, tr("ship.type.all"))
        self.model.retranslate()
        self._status()
        self.count.setText(tr("ship.results", n=num(len(self.model.rows))))
        self.detail.refresh()

    def on_theme(self) -> None:
        self.detail.chart.restyle()
        self.detail.refresh()
