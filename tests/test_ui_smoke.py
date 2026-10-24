"""The window opens, switches language and theme, and the EU ETS page computes."""
import pytest

pytest.importorskip("pytestqt")

from navigator import i18n
from navigator.ui import theme
from navigator.ui.main_window import MainWindow
from navigator.ui.pages import RegulationPage


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.close()
    i18n.set_language(i18n.DEFAULT)
    theme.set_current(theme.DEEP_SEA)


def test_window_language_and_theme(win):
    assert win.windowTitle() == "Πλοηγός Απανθρακοποίησης"
    i18n.set_language("en")
    assert win.windowTitle() == "Decarbonisation Navigator"
    assert win.nav_buttons[0][0].text() == "Ship"
    win.set_theme("light")
    assert theme.current().name == "light"


def test_ets_page_reacts_to_input(win):
    reg = next(p for p in win.pages if isinstance(p, RegulationPage))
    before = sum(r.cost for r in reg.ets.path)
    reg.ets.scope["at_berth"].setValue(reg.ets.scope["at_berth"].value() + 1000)
    assert sum(r.cost for r in reg.ets.path) > before
    reg.ets.gt.setValue(1000)                     # below 5000 GT: out of scope
    assert sum(r.cost for r in reg.ets.path) == 0
