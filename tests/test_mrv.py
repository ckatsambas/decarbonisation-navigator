"""EU MRV importer on small synthetic files in both EMSA layouts (the real files are not in Git)."""
from datetime import date

import pytest

from navigator.data import mrv
from navigator.engine.models import ShipCategory


@pytest.fixture
def db(mrv_files, tmp_path):
    path = tmp_path / "mrv.sqlite"
    res = mrv.import_files(mrv_files, path)
    assert [r.skipped for r in res] == [False, False]
    d = mrv.MrvDatabase(path)
    yield d
    d.close()


def test_parsers():
    assert mrv.parse_period(2018.0) == (2018, date(2018, 1, 1), date(2018, 12, 31), False)
    assert mrv.parse_period("2025 (1/1 - 11/8)") == (2025, date(2025, 1, 1), date(2025, 8, 11), True)
    assert mrv.parse_tech_efficiency("EEDI (4.12 gCO₂/t·nm)") == ("EEDI", 4.12)
    assert mrv.parse_tech_efficiency("Not Applicable") == (None, None)
    from pathlib import Path
    assert mrv.parse_release(Path("2024-v253-23102026-EU MRV Publication of information.xlsx")) == (2024, 253, "2026-10-23")


def test_releases_and_search(db):
    assert [(r.year, r.version, r.n_full, r.n_partial) for r in db.releases()] == [(2023, 92, 2, 0), (2025, 72, 1, 2)]
    assert db.search("9000001")[0].name == "NEW NAME"           # latest identity
    assert db.search("old name")[0].imo == "9000001"            # past names are searchable
    assert db.search("acme")[0].imo == "9000001"                # and companies
    assert db.count() == 3


def test_old_layout_values(db):
    y = [h for h in db.history("9000001") if h.year == 2023][0]
    assert y.co2_total == 9450 and y.time_at_sea == 5000
    assert y.distance_nm == pytest.approx(9450 * 1000 / 1890)
    assert y.methods == "A,C"
    assert y.tech_eff_type == "EIV" and y.tech_eff_value == pytest.approx(20.1)
    e = y.emissions().co2
    assert (e.intra_eu, e.in_port, e.from_eu, e.to_eu) == (4000, 450, 2000, 3000)
    assert y.ets_reported_co2e is None                          # not published before 2024
    z = db.history("9000002")[0]
    assert z.co2_per_nm is None                                 # "Division by zero!" becomes empty


def test_new_layout_gases_and_ets(db):
    y = db.latest("9000001")
    assert y.year == 2025 and y.company_name == "ACME"
    em = y.emissions()
    assert em.co2.in_port == 1000                               # larger of berth (900) and within-port (1000)
    assert em.ch4.total == pytest.approx(0.1)                 # 0.1 t CH4 split like CO2
    assert y.ets_reported_co2 == 8500
    ship = y.to_ship()
    assert ship.category == ShipCategory.PASSENGER and ship.ice_class == "IA" and ship.ets_scope_override is True


def test_partial_reports_are_combined(db):
    y = db.history("9000003")[0]
    assert y.partial and y.n_reports == 2
    assert y.co2_total == 4000 and y.ets_reported_co2 == 2000
    assert (y.period_start, y.period_end) == ("2025-01-01", "2025-12-31")
    assert y.company_name == "SECOND"                           # identity from the latest part
    assert y.co2_per_nm == pytest.approx(4000 * 1000 / (y.distance_nm))


def test_reimport_keeps_newer_version(mrv_files, tmp_path):
    path = tmp_path / "x.sqlite"
    mrv.import_files(mrv_files, path)
    again = mrv.import_files(mrv_files, path)
    assert all(r.skipped for r in again)
    forced = mrv.import_files(mrv_files, path, force=True)
    assert not any(r.skipped for r in forced)


def test_ship_category():
    assert mrv.ship_category("Passenger ship (Cruise Passenger ship)") == ShipCategory.PASSENGER
    assert mrv.ship_category("Other ship types (Offshore)") == ShipCategory.OFFSHORE
    assert mrv.ship_category("Other ship types") == ShipCategory.OTHER
    assert mrv.ship_category("LNG carrier") == ShipCategory.CARGO


def test_coverage_ratio_from_reported_ets(db):
    y = db.latest("9000001")
    # rule: 4000 intra + 1000 in port + 0.5 × (2000 + 3000) = 7500; EMSA reports 8500
    assert y.ets_coverage_ratio() == pytest.approx(8500 / 7500)
    assert db.history("9000003")[0].to_ship().ets_coverage_ratio is None   # rule matches EMSA exactly
    old = next(h for h in db.history("9000001") if h.year == 2023)
    assert old.ets_coverage_ratio() is None                                 # no ETS figure before 2024
