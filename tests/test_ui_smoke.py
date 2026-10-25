"""Lobby → new project → choose ship → today's position → save → reopen."""
import pytest
from PySide6.QtCore import Qt

pytest.importorskip("pytestqt")

from navigator import i18n
from navigator.data.projects import ProjectStore
from navigator.ui import theme
from navigator.ui.main_window import MainWindow
from navigator.ui.state import AppState


@pytest.fixture
def win(qtbot, mrv_db_path, tmp_path):
    w = MainWindow(AppState(mrv_db_path, bundle=False), ProjectStore(tmp_path / "projects"))
    qtbot.addWidget(w)
    yield w
    w.close()
    i18n.set_language(i18n.DEFAULT)
    theme.set_current(theme.DEFAULT)


def start_with_ship(w, query="old name"):
    w.new_project()
    pv = w.project_view
    step = pv.ship_step
    step.search.setText(query)
    step.run_search()
    step.detail.use_btn.click()
    return pv


def test_lobby_language_and_theme(win):
    assert win.stack.currentWidget() is win.lobby
    assert win.windowTitle() == "Πλοηγός Απανθρακοποίησης"
    i18n.set_language("en")
    assert win.windowTitle() == "Decarbonisation Navigator"
    assert win.lobby.new_btn.text().endswith("New project")
    win.set_theme("dark")
    assert theme.current().name == "dark"


def test_new_project_requires_a_ship(win):
    win.new_project()
    pv = win.project_view
    assert win.stack.currentWidget() is pv
    assert not pv.next_btn.isEnabled()                      # step 1 needs a ship
    pv.go(1)
    assert pv.current == 0                                  # later steps still locked


def test_choose_ship_then_position(win):
    pv = start_with_ship(win)
    assert pv.project.name == "NEW NAME"                    # named after the ship
    assert pv.next_btn.isEnabled()
    pv.next_btn.click()
    assert pv.current == 1
    pos = pv.position_step
    assert pos.inputs.loaded is not None and pos.inputs.scope["intra_eu"].value() == 4000
    assert pos.inputs.cii_type.currentData() == "ropax"
    assert pos.results and pos.n_total.value.text() != "–"


def test_price_and_nzf_shortcuts(win):
    pv = start_with_ship(win)
    pv.next_btn.click()
    pos = pv.position_step
    pos._pick_price("high")
    pos.recompute()
    assert pos.inputs.prices[2050].value() == 250
    assert pos.price.buttons["high"].isChecked()
    pos.nzf.picked.emit("not_adopted")
    pos.recompute()
    assert all(not r.nzf.applies for r in pos.results)


def test_view_switch_changes_only_imo_costs(win):
    pv = start_with_ship(win)
    pv.next_btn.click()
    pos = pv.position_step
    pos.inputs.eu_share.setValue(40)                        # user value (method a)
    pos.recompute()
    eu = {r.year: r for r in pos.results}
    win.state.set_view("ww")
    ww = {r.year: r for r in pos.results}
    assert not pos.inputs.ww.isHidden() and win.view_switch.buttons["ww"].isChecked()
    assert ww[2030].ets.cost == eu[2030].ets.cost
    assert ww[2030].nzf.cost_eur >= eu[2030].nzf.cost_eur
    win.state.set_view("eu")


def test_project_saves_and_reopens(win):
    pv = start_with_ship(win)
    pv.next_btn.click()
    pv.position_step._pick_price("low")
    pv.position_step.capacity.setValue(30_000)
    pv.position_step.recompute()
    pv.save_now()
    pid = pv.project.id
    win.show_lobby()
    cards = win.store.list()
    assert [p.id for p in cards] == [pid] and cards[0].ship["imo"] == "9000001"
    assert cards[0].summary["total_eur"] > 0
    win.new_project()                                       # something else in between
    win.open_project(pid)
    pos = win.project_view.position_step
    assert win.project_view.current == 1
    assert pos.inputs.loaded.imo == "9000001"
    assert pos.inputs.prices[2050].value() == 100 and pos.inputs.capacity.value() == 30_000


def test_store_export_import(tmp_path):
    store = ProjectStore(tmp_path / "a")
    from navigator.data.projects import Project
    p = Project(name="Test")
    store.save(p)
    f = store.export(p.id, tmp_path / "out")
    assert f.suffix == ".dnproj"
    q = store.import_file(f)                                # same id exists → new id
    assert q.id != p.id and q.name == "Test" and len(store.list()) == 2
    store.delete(p.id)
    assert [x.id for x in store.list()] == [q.id]


def test_empty_database_shows_hint(qtbot, tmp_path):
    w = MainWindow(AppState(tmp_path / "missing.sqlite", bundle=False), ProjectStore(tmp_path / "p"))
    qtbot.addWidget(w)
    w.new_project()
    step = w.project_view.ship_step
    assert not step.empty.isHidden() and step.split.isHidden()
    w.close()


def test_standard_ship_flow_and_reopen(win):
    win.new_project()
    pv = win.project_view
    step = pv.ship_step
    step.set_mode("standard")
    pane = step.std_pane
    pane.pick_preset("kamsarmax")
    pane.use_btn.click()
    assert win.state.has_ship and pv.next_btn.isEnabled()
    assert pv.project.name == "Kamsarmax"
    pv.next_btn.click()
    pos = pv.position_step
    assert pos.inputs.standard is not None and pos.inputs.cii_type.currentData() == "bulk"
    assert pos.inputs.capacity.value() == 82_000
    assert pos.results and pos.results[-1].total_eur > 0
    pv.save_now()
    pid = pv.project.id
    win.show_lobby()
    win.open_project(pid)
    assert win.project_view.position_step.inputs.standard[0] == "bulk:60000-99999"


def test_baseline_switch_changes_costs(win):
    pv = start_with_ship(win)
    pv.next_btn.click()
    pos = pv.position_step
    pos.base.picked.emit("pay")
    pos.recompute()
    pay = sum(r.total_eur for r in pos.results)
    pos.base.picked.emit("least_cost")
    pos.recompute()
    assert sum(r.total_eur for r in pos.results) <= pay + 1e-6
    assert {r.route for r in pos.results} <= {"none", "pay", "pool", "bio"}


def test_options_step_lists_measures_and_keeps_shortlist(win):
    win.new_project()
    pv = win.project_view
    pv.ship_step.set_mode("standard")
    pv.ship_step.std_pane.pick_preset("kamsarmax")
    pv.ship_step.std_pane.use_btn.click()
    pv.next_btn.click()
    pv.next_btn.click()
    assert pv.current == 2
    opt = pv.options_step
    ok = [r for r in opt.rows if r.ok]
    assert len(ok) >= 18 and all(r.app is not None for r in ok)
    assert not next(r for r in opt.rows if r.m.key == "steam_plant").ok        # tankers only
    rotor = next(i for i, r in enumerate(opt.rows) if r.m.key == "rotor_sails")
    opt.table.item(rotor, 0).setCheckState(Qt.CheckState.Checked)
    assert opt.shortlist == {"rotor_sails"}
    opt.rate.picked.emit("0.10")
    assert opt.settings()["rate"] == pytest.approx(0.10)
    pv.save_now()
    pid = pv.project.id
    win.show_lobby()
    win.open_project(pid)
    opt = win.project_view.options_step
    assert opt.shortlist == {"rotor_sails"} and opt.settings()["rate"] == pytest.approx(0.10)
