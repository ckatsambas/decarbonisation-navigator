"""EU ETS engine against hand-worked examples."""
import pytest

from navigator.engine.models import AnnualEmissions, Gas, ScopeSplit, Ship, ShipCategory, YearSeries
from navigator.engine.regulation.eu_ets import EtsRules, cost_path, ets_year, total_cost

RULES = EtsRules.load()

KAMSARMAX = Ship(imo="9000001", name="Example Kamsarmax", ship_type="Bulk carrier",
                 category=ShipCategory.CARGO, gross_tonnage=44_000)

# 19,000 t CO2 a year: 1,000 at berth in EU ports, 4,000 leaving the EU, 3,000 arriving, rest elsewhere
CO2 = ScopeSplit(intra_eu=0, in_port=1_000, from_eu=4_000, to_eu=3_000, outside=11_000)
EM = AnnualEmissions(co2=CO2)


def test_scope_total():
    assert CO2.total == 19_000


def test_2024_phase_in_40_percent():
    # covered = 1,000 + 0.5 × (4,000 + 3,000) = 4,500 t; allowances = 4,500 × 40% = 1,800
    r = ets_year(KAMSARMAX, EM, 2024, price=70.0, rules=RULES)
    assert r.covered == pytest.approx(4_500)
    assert r.allowances == pytest.approx(1_800)
    assert r.cost == pytest.approx(126_000)
    assert r.surrender_year == 2025


def test_phase_in_steps():
    assert RULES.phase_in_share(2023) == 0
    assert RULES.phase_in_share(2025) == pytest.approx(0.70)
    assert RULES.phase_in_share(2026) == pytest.approx(1.0)
    assert RULES.phase_in_share(2040) == pytest.approx(1.0)


def test_methane_counts_only_from_2026():
    em = AnnualEmissions(co2=CO2, ch4=ScopeSplit(in_port=2.0))
    r25 = ets_year(KAMSARMAX, em, 2025, 80.0, RULES)
    r26 = ets_year(KAMSARMAX, em, 2026, 80.0, RULES)
    assert r25.covered_by_gas[Gas.CH4] == 0
    assert r26.covered_by_gas[Gas.CH4] == pytest.approx(2.0 * RULES.gwp[Gas.CH4])
    assert r26.covered == pytest.approx(4_500 + 2.0 * RULES.gwp[Gas.CH4])


def test_ice_class_reduction_until_2030():
    ice = Ship(imo="9000002", name="Ice tanker", ship_type="Oil tanker", gross_tonnage=60_000, ice_class="IA Super")
    assert ets_year(ice, EM, 2030, 80, RULES).allowances == pytest.approx(4_500 * 0.95)
    assert ets_year(ice, EM, 2031, 80, RULES).allowances == pytest.approx(4_500)


def test_out_of_scope_ships():
    small = Ship(imo="9000003", name="Small", ship_type="General cargo ship", gross_tonnage=3_000)
    offshore = Ship(imo="9000004", name="OSV", ship_type="Offshore", category=ShipCategory.OFFSHORE,
                    gross_tonnage=8_000)
    assert ets_year(small, EM, 2030, 80, RULES).cost == 0
    assert ets_year(offshore, EM, 2026, 80, RULES).cost == 0
    assert ets_year(offshore, EM, 2027, 80, RULES).allowances == pytest.approx(4_500)


def test_cost_path_with_price_series_and_measure_starting_later():
    prices = YearSeries({2024: 70, 2030: 100})           # linear in between
    def emissions(year):                                  # a measure saving 10% from 2027
        return EM.scaled(0.9) if year >= 2027 else EM
    path = cost_path(KAMSARMAX, emissions, prices, range(2024, 2031), RULES)
    assert [r.year for r in path] == list(range(2024, 2031))
    assert path[0].price == pytest.approx(70)
    assert path[3].price == pytest.approx(85)             # 2027: 70 + 30 × 3/6
    assert path[3].allowances == pytest.approx(4_500 * 0.9)
    assert total_cost(path) == pytest.approx(sum(r.cost for r in path))


def test_observed_coverage_ratio_applies_until_derogations_end():
    ferry = Ship(imo="9000005", name="Island ferry", ship_type="Ro-pax ship", category=ShipCategory.PASSENGER,
                 gross_tonnage=20_000, ets_coverage_ratio=0.01)
    assert RULES.derogations_until == 2030
    assert ets_year(ferry, EM, 2030, 80, RULES).covered == pytest.approx(4_500 * 0.01)
    assert ets_year(ferry, EM, 2031, 80, RULES).covered == pytest.approx(4_500)
    odd = Ship(imo="9000006", name="Odd", ship_type="Bulk carrier", gross_tonnage=20_000, ets_coverage_ratio=1.4)
    assert ets_year(odd, EM, 2026, 80, RULES).coverage_ratio == 1.0     # never above the rule
