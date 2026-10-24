"""The window opens, switches language and theme, searches ships and feeds the EU ETS page."""
import pytest

pytest.importorskip("pytestqt")

from navigator import i18n
from navigator.ui import theme
from navigator.ui.main_window import MainWindow
from navigator.ui.pages import RegulationPage, ShipPage
from navigator.ui.state import AppState


def _make(qtbot, path):
    w = MainWindow(AppState(path, bundle=False))
    qtbot.addWidget(w)
    return w


@pytest.fixture
def win(qtbot, mrv_db_path):
    w = _make(qtbot, mrv_db_path)
    yield w
    w.close()
    i18n.set_language(i18n.DEFAULT)
    theme.set_current(theme.DEEP_SEA)


def page(w, cls):
    return next(p for p in w.pages if isinstance(p, cls))


def test_window_language_and_theme(win):
    assert win.windowTitle() == "Πλοηγός Απανθρακοποίησης"
    i18n.set_language("en")
    assert win.windowTitle() == "Decarbonisation Navigator"
    assert win.nav_buttons[0][0].text() == "Ship"
    win.set_theme("light")
    assert theme.current().name == "light"


def test_ets_page_reacts_to_input(win):
    reg = page(win, RegulationPage)
    before = sum(r.cost for r in reg.ets.path)
    reg.ets.scope["in_port"].setValue(reg.ets.scope["in_port"].value() + 1000)
    assert sum(r.cost for r in reg.ets.path) > before
    reg.ets.gt.setValue(1000)                     # below 5000 GT: out of scope
    assert sum(r.cost for r in reg.ets.path) == 0


def test_search_and_use_ship(win):
    ship = page(win, ShipPage)
    assert ship.model.rowCount() == 3
    ship.search.setText("old name")
    ship.run_search()
    assert [r.imo for r in ship.model.rows] == ["9000001"]
    assert ship.detail.history[-1].year == 2025
    ship.detail.use_btn.click()
    reg = page(win, RegulationPage)
    assert reg.ets.loaded is not None and reg.ets.scope["intra_eu"].value() == 4000
    assert reg.ets.ice.currentData() == "IA" and reg.ets.scope_override is True
    reg.ets.reset_example()
    assert reg.ets.loaded is None


def test_empty_database_shows_import_hint(qtbot, tmp_path):
    w = _make(qtbot, tmp_path / "missing.sqlite")
    sp = page(w, ShipPage)
    assert sp.empty.isVisibleTo(w) and not sp.split.isVisibleTo(w)
    w.close()
