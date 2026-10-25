"""Every regulatory value must have a known source; overrides replace single values."""
import json

import pytest

from navigator.engine import params


@pytest.mark.parametrize("name", params.available())
def test_every_value_has_a_source(name):
    ps = params.load(name)
    assert ps.validate() == []
    for p in ps.values.values():
        src = ps.source_of(p.key)
        assert src.title and src.checked, f"{name}.{p.key} source lacks title or check date"


def test_unverified_values_are_reported(tmp_path):
    (tmp_path / "eu_ets_maritime.json").write_text(json.dumps({
        "sources": {"me": {"title": "Draft", "checked": "2026-10-24"}},
        "values": {"first_year": {"value": 2024, "source": "me", "status": "verify"}},
    }), encoding="utf-8")
    ps = params.load("eu_ets_maritime", override_dir=tmp_path)
    assert "first_year" in [p.key for p in ps.unverified()]
    assert "phase_in" not in [p.key for p in ps.unverified()]


def test_user_override(tmp_path):
    (tmp_path / "eu_ets_maritime.json").write_text(json.dumps({
        "sources": {"me": {"title": "My assumption", "checked": "2026-10-24"}},
        "values": {"phase_in": {"value": {"2024": 1.0}, "source": "me"}},
    }), encoding="utf-8")
    ps = params.load("eu_ets_maritime", override_dir=tmp_path)
    assert ps["phase_in"] == {"2024": 1.0}
    assert ps["first_year"] == 2024                        # untouched value kept
    assert len(ps.origin) == 2


def test_unknown_source_rejected(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"values": {"a": {"value": 1, "source": "nope"}}}))
    with pytest.raises(ValueError):
        params.load("x", base_dir=tmp_path)
