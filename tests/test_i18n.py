"""Both language catalogues must have the same keys and placeholders."""
import re

import pytest

from navigator import i18n


def test_catalogues_have_same_keys():
    el, en = i18n.catalogue("el"), i18n.catalogue("en")
    assert set(el) - set(en) == set(), "keys missing in en.json"
    assert set(en) - set(el) == set(), "keys missing in el.json"


def test_placeholders_match():
    el, en = i18n.catalogue("el"), i18n.catalogue("en")
    for k in el:
        assert set(re.findall(r"{(\w+)}", el[k])) == set(re.findall(r"{(\w+)}", en[k])), k


@pytest.fixture
def lang():
    yield i18n
    i18n.set_language(i18n.DEFAULT)


def test_switch_and_format(lang):
    lang.set_language("en")
    assert lang.tr("nav.ship") == "Ship"
    assert lang.num(1234567.891, 2) == "1,234,567.89"
    assert lang.eur_short(2_500_000) == "€2.50m"
    lang.set_language("el")
    assert lang.tr("nav.ship") == "Πλοίο"
    assert lang.num(1234567.891, 2) == "1.234.567,89"
    assert lang.num(-5, 0) == "−5"
    assert lang.pct(0.237) == "24%"


def test_missing_key_falls_back_to_key(lang):
    assert lang.tr("does.not.exist") == "does.not.exist"


def test_listener_called(lang):
    seen = []
    lang.on_change(seen.append)
    lang.set_language("en")
    assert seen == ["en"]
