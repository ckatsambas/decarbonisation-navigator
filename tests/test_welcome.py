"""First launch: account page, preferences, tour offer; sign-out and sign-in; guest; the tour."""
import pytest

pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from navigator import i18n
from navigator.data import accounts as A
from navigator.data.projects import Project, ProjectStore
from navigator.ui import theme
from navigator.ui.main_window import MainWindow
from navigator.ui.state import AppState


@pytest.fixture
def setup(qtbot, mrv_db_path, tmp_path):
    store = A.AccountStore(tmp_path / "data")
    w = MainWindow(AppState(mrv_db_path, bundle=False), accounts=store, welcome="setup")
    qtbot.addWidget(w)
    yield w, store
    w.close()
    i18n.set_language(i18n.DEFAULT)
    theme.set_current(theme.DEFAULT)


def create(w, name="maria", pw="Sea-route-2027", terms=True):
    ap = w.welcome.account_page
    ap.show_form("create")
    ap.c_name.setText("Maria P.")
    ap.c_user.setText(name)
    ap.c_pw.edit.setText(pw)
    ap.c_pw2.edit.setText(pw)
    ap.c_terms.box.setChecked(terms)
    ap.create()
    return ap


def test_setup_creates_account_and_applies_preferences(setup):
    w, store = setup
    assert w.screens.currentWidget() is w.welcome and w.welcome.index == 0
    ap = create(w, terms=False)
    assert ap.error.text() == i18n.tr("auth.err.terms")
    ap = create(w)
    code = ap.k_code.text()
    assert ap.forms.currentIndex() == ap.FORMS["code"] and len(code) == 14
    assert not ap.k_btn.isEnabled()
    ap.k_saved.setChecked(True)
    ap.k_btn.click()
    assert w.welcome.index == 1
    w.welcome.prefs_page.lang_tiles["en"].click()           # live language and theme
    w.welcome.prefs_page.theme_tiles["dark"].click()
    assert i18n.language() == "en" and theme.current().name == "dark"
    assert w.welcome.title.text() == i18n.tr("wel.prefs.title")
    w.welcome.next_btn.click()
    w.welcome.tour_page.no.click()                            # skip the tour
    assert w.screens.currentWidget() is w.app_widget and w.account.username == "maria"
    assert store.setup_done and store.find("maria").prefs["language"] == "en"
    assert w.store.folder == store.projects_dir(store.find("maria"))
    assert w.account_btn.isVisible() or w.account_btn.text() == "MP"
    assert w.help_btn.menu() is not None and len(w.help_btn.menu().actions()) >= 3


def test_sign_out_then_sign_in_restores_projects_and_prefs(setup):
    w, store = setup
    create(w).k_saved.setChecked(True)
    w.welcome.account_page.k_btn.click()
    w.welcome.prefs_page.theme_tiles["dark"].click()
    w.welcome.go(2)
    w.welcome.tour_page.no.click()
    w.new_project()
    w.project_view.rename("Maria's ship")
    w.show_lobby()
    w.sign_out()
    assert w.welcome is not None and w.welcome.mode == "signin" and store.remembered() is None
    w.set_theme("light")
    ap = w.welcome.account_page
    assert ap.forms.currentIndex() == ap.FORMS["signin"] and ap.in_user.text() == "maria"
    ap.in_pw.edit.setText("wrong-password")
    ap.sign_in()
    assert "4" in ap.error.text()
    ap.in_pw.edit.setText("Sea-route-2027")
    ap.remember.setChecked(True)
    ap.sign_in()                                              # known account: straight in
    assert w.screens.currentWidget() is w.app_widget and theme.current().name == "dark"
    assert [p.name for p in w.store.list()] == ["Maria's ship"]
    assert store.remembered().username == "maria"


def test_guest_starts_empty(setup):
    w, store = setup
    ap = w.welcome.account_page
    ap.show_form("guest")
    ap.guest()
    assert "auth.err.terms" not in ap.error.text() and ap.error.text()
    ap.g_terms.box.setChecked(True)
    ap.guest()
    assert w.welcome.index == 1 and w.welcome.account.is_guest
    w.welcome.go(2)
    w.welcome.tour_page.no.click()
    assert w.account.is_guest and w.store.list() == []


def test_terms_change_asks_again(qtbot, mrv_db_path, tmp_path, monkeypatch):
    store = A.AccountStore(tmp_path / "data")
    store.create("nikos", "longenough1", "longenough1", accept_terms=True)
    store.mark_setup_done()
    monkeypatch.setattr(A, "TERMS_VERSION", "2.0")
    w = MainWindow(AppState(mrv_db_path, bundle=False), accounts=store, welcome="signin")
    qtbot.addWidget(w)
    ap = w.welcome.account_page
    ap.in_user.setText("nikos")
    ap.in_pw.edit.setText("longenough1")
    ap.sign_in()
    assert ap.forms.currentIndex() == ap.FORMS["terms"]
    ap.t_terms.box.setChecked(True)
    ap.t_btn.click()
    assert store.find("nikos").terms_version == "2.0"
    w.close()


def test_tour_walks_every_step_and_removes_the_sample(setup, qtbot):
    w, store = setup
    w.show()
    create(w).k_saved.setChecked(True)
    w.welcome.account_page.k_btn.click()
    w.welcome.go(2)
    w.welcome.tour_page.go.click()
    tour = w.tour
    assert tour is not None and tour.isVisible()
    ProjectStore(w.store.folder).save(Project(name="mine"))
    n = len(tour.steps)
    for _ in range(n - 1):
        tour.next()
        qtbot.wait(40)
        assert tour.bubble.title.text() and not tour.bubble.title.text().startswith("tour.")
    i18n.set_language("en")                                  # the bubble follows the language
    assert tour.bubble.title.text() == i18n.tr(f"tour.{tour.steps[tour.k].key}.title")
    tour.next()                                              # finish
    assert w.tour is None
    assert [p.name for p in w.store.list()] == ["mine"]      # the sample is gone, the user's project stays
    assert store.find("maria").prefs.get("tour_done") is True
    w.start_tour()                                           # Help → tour, then skip with Esc
    qtbot.keyClick(w.tour, Qt.Key.Key_Escape)
    assert w.tour is None
