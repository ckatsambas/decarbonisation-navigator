"""Shared application state: the open EU MRV database and the ship chosen for analysis."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..data import mrv


class AppState(QObject):
    db_changed = Signal()
    ship_changed = Signal(object)          # mrv.ShipYear | None
    view_changed = Signal(str)             # "eu" | "ww"

    def __init__(self, db_path: Path | None = None, bundle: Path | None | bool = None):
        """`bundle`: the packaged EU MRV database (default), another .xz file, or False for none."""
        super().__init__()
        self.db_path = Path(db_path) if db_path else mrv.default_db_path()
        self.db: mrv.MrvDatabase | None = None
        self.ship_year: mrv.ShipYear | None = None
        self.view = "eu"
        self.bundle_status = "no-bundle"
        if bundle is not False:
            try:
                self.bundle_status = mrv.ensure_database(self.db_path, bundle or None)
            except Exception:  # noqa: BLE001 - a damaged bundle must not stop the app; import still works
                self.bundle_status = "error"
        self.reopen()

    def reopen(self) -> None:
        if self.db is not None:
            self.db.close()
        try:
            self.db = mrv.MrvDatabase(self.db_path)
        except FileNotFoundError:
            self.db = None
        self.db_changed.emit()

    def use_ship(self, ship_year: mrv.ShipYear | None) -> None:
        self.ship_year = ship_year
        self.ship_changed.emit(ship_year)

    def set_view(self, view: str) -> None:
        if view in ("eu", "ww") and view != self.view:
            self.view = view
            self.view_changed.emit(view)
