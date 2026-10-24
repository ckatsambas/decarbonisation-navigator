"""The window opens, switches language and theme, searches ships and feeds the EU ETS page."""
import pytest

pytest.importorskip("pytestqt")

from navigator import i18n
from navigator.ui import theme
from navigator.ui.main_window import MainWindow
from navigator.ui.pages import RegulationPage, ShipPage
from navigator.ui.state import AppState


def _make(qtbot, path):
    from PySide6.QtCore import QSettings
    QSettings().setValue("view", "eu")
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


def ets_total(reg):
    reg.recompute()
    return sum(r.ets.cost for r in reg.results)


def test_regulation_page_reacts_to_input(win):
    reg = page(win, RegulationPage)
    before = ets_total(reg)
    reg.inputs.scope["in_port"].setValue(reg.inputs.scope["in_port"].value() + 1000)
    assert ets_total(reg) > before
    reg.inputs.gt.setValue(1000)                  # below 5000 GT: out of scope
    assert ets_total(reg) == 0


def test_view_switch_changes_only_imo_costs(win):
    reg = page(win, RegulationPage)
    reg.recompute()
    eu = {r.year: r for r in reg.results}
    assert reg.inputs.ww.isHidden()
    win.state.set_view("ww")
    ww = {r.year: r for r in reg.results}
    assert not reg.inputs.ww.isHidden()
    assert win.view_switch.buttons["ww"].isChecked()
    assert ww[2030].ets.cost == eu[2030].ets.cost
    assert ww[2030].nzf.cost_eur > eu[2030].nzf.cost_eur
    win.state.set_view("eu")


def test_search_and_use_ship(win):
    ship = page(win, ShipPage)
    assert ship.model.rowCount() == 3
    ship.search.setText("old name")
    ship.run_search()
    assert [r.imo for r in ship.model.rows] == ["9000001"]
    assert ship.detail.history[-1].year == 2025
    ship.detail.use_btn.click()
    reg = page(win, RegulationPage)
    assert reg.inputs.loaded is not None and reg.inputs.scope["intra_eu"].value() == 4000
    assert reg.inputs.ice.currentData() == "IA" and reg.inputs.scope_override is True
    assert reg.inputs.cii_type.currentData() == "ropax" and reg.inputs.share_estimate is not None
    reg.inputs.reset_example()
    assert reg.inputs.loaded is None


def test_empty_database_shows_import_hint(qtbot, tmp_path):
    w = _make(qtbot, tmp_path / "missing.sqlite")
    sp = page(w, ShipPage)
    assert sp.empty.isVisibleTo(w) and not sp.split.isVisibleTo(w)
    w.close()
