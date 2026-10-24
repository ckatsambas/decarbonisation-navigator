"""FuelEU, IMO NZF, CII, fuels and the worldwide estimate against hand calculations."""
import math

import pytest

from navigator.engine import fuels as F
from navigator.engine.compliance import Profile, Rules, Scenario, evaluate
from navigator.engine.estimate import ActivityRules, estimate_share, to_worldwide, user_share
from navigator.engine.models import AnnualEmissions, ScopeSplit, Ship, ShipCategory, YearSeries
from navigator.engine.regulation.cii import CiiRules, attained, cii_type_for
from navigator.engine.regulation.fueleu import FuelEuRules, fueleu_path
from navigator.engine.regulation.imo_nzf import NzfRules, nzf_path

FUELS = F.load()
FE = FuelEuRules.load()
NZ = NzfRules.load()
CII = CiiRules.load()
SHIP = Ship(imo="1", name="Test", ship_type="Bulk carrier", category=ShipCategory.CARGO, gross_tonnage=44_000)
HFO_T = 10_000
# 10,000 t HFO, all on voyages between EU ports
EM = AnnualEmissions(co2=ScopeSplit(intra_eu=HFO_T * 3.114))


def const(x):
    return lambda _y: x


def test_published_fuel_intensities():
    g = FE.gwp
    assert FUELS["hfo"].wtw(g) == pytest.approx(91.74, abs=0.01)
    assert FUELS["mgo"].wtw(g) == pytest.approx(90.77, abs=0.01)
    assert FUELS["lng_otto_ms"].wtw(g) == pytest.approx(89.20, abs=0.01)
    assert F.intensity({"e_methanol": 1}, FUELS, g, rfnbo_factor=2) == pytest.approx(FUELS["e_methanol"].wtw(g) / 2)


def test_infer_mix():
    assert F.infer_mix(3.114)[0] == {"hfo": 1.0}
    assert F.infer_mix(3.206)[0] == {"mgo": 1.0}
    mix, kind = F.infer_mix(2.75)
    assert kind == "lng" and mix == {"lng_otto_ss": 1.0}


def test_fueleu_penalty_and_consecutive_years():
    path = fueleu_path(SHIP, const(EM), const({"hfo": 1}), range(2024, 2027), FE, FUELS)
    assert not path[0].in_scope                                  # starts 2025
    y25, y26 = path[1], path[2]
    assert y25.energy_mj == pytest.approx(4.05e8)
    assert y25.target == pytest.approx(89.3368)
    assert y25.balance_t == pytest.approx(-974.996, rel=1e-4)
    assert y25.penalty == pytest.approx(622_087.7, rel=1e-4)
    assert y26.consecutive == 2 and y26.penalty == pytest.approx(622_087.7 * 1.1, rel=1e-4)


def test_fueleu_half_coverage_and_compliant_fuel():
    em = AnnualEmissions(co2=ScopeSplit(from_eu=HFO_T * 3.114))
    assert fueleu_path(SHIP, const(em), const({"hfo": 1}), range(2025, 2026))[0].energy_mj == pytest.approx(2.025e8)
    bio = fueleu_path(SHIP, const(EM), const({"hvo": 1}), range(2025, 2026))[0]
    assert bio.balance_t > 0 and bio.penalty == 0


def test_nzf_tiers_and_scenarios():
    em = AnnualEmissions(co2=ScopeSplit(outside=HFO_T * 3.114))          # all outside the EU
    y = nzf_path(SHIP, const(em), const({"hfo": 1}), range(2028, 2029), "as_drafted", NZ, FUELS)[0]
    assert y.gfi == pytest.approx(91.6012, rel=1e-5)
    assert y.tier2_t == pytest.approx(823.46, rel=1e-4)
    assert y.tier1_t == pytest.approx(4912.245, rel=1e-4)
    assert y.cost_usd == pytest.approx(804_139.3, rel=1e-4)
    assert y.cost_eur == pytest.approx(804_139.3 * NZ.eur_per_usd, rel=1e-6)
    assert not nzf_path(SHIP, const(em), const({"hfo": 1}), range(2028, 2029), "delayed")[0].applies
    assert not any(r.applies for r in nzf_path(SHIP, const(em), const({"hfo": 1}), range(2028, 2051), "not_adopted"))
    assert not nzf_path(SHIP, const(em), const({"hfo": 1}), range(2030, 2031), domestic_only=True)[0].applies


def test_nzf_interpolated_targets_and_surplus():
    base, direct = NZ.targets(2029, "as_drafted")
    assert (base, direct) == (pytest.approx(87.702), pytest.approx(75.573))
    y = nzf_path(SHIP, const(EM), const({"bio_methanol": 1}), range(2028, 2029))[0]
    assert y.surplus_t > 0 and y.tier1_t == 0 and y.cost_usd <= 0


def test_cii_reference_and_rating():
    assert CII.reference("bulk", 82_000) == pytest.approx(4.1672, rel=1e-4)
    assert CII.required("bulk", 82_000, 2026) == pytest.approx(3.7088, rel=1e-4)
    assert CII.reference("bulk", 400_000) == pytest.approx(4745 * 279_000 ** -0.622)      # capacity cap
    assert CII.reference("lng", 50_000) == pytest.approx(14779e10 * 65_000 ** -2.673)    # capacity floor
    assert CII.z(2030) == pytest.approx(0.215) and CII.z(2031) == pytest.approx(0.24125)
    req = CII.required("bulk", 82_000, 2026)
    assert CII.rating("bulk", 82_000, req * 0.85, req) == "A"
    assert CII.rating("bulk", 82_000, req * 1.00, req) == "C"
    assert CII.rating("bulk", 82_000, req * 1.20, req) == "E"
    assert attained(1000, 50_000, 10_000) == pytest.approx(2.0)
    assert cii_type_for("Oil tanker") == "tanker" and cii_type_for("Other ship types") is None


def test_eu_share_estimate():
    rules = ActivityRules.load()
    days = rules.sea_days["Bulk carrier"]
    s = estimate_share("Bulk carrier", days * 24 * 0.25, rules)
    assert s.method == "estimated" and s.share == pytest.approx(0.25)
    assert s.low < s.share < s.high
    assert estimate_share("Ro-pax ship", 9000, rules).eu_dominant
    assert estimate_share("Bulk carrier", None, rules).method == "unknown"
    ww = to_worldwide(EM, 0.25)
    assert ww.co2.total == pytest.approx(EM.co2.total * 4) and ww.co2.intra_eu == EM.co2.intra_eu


def test_evaluate_views():
    profile = Profile(ship=SHIP, emissions=EM, fuel_mix={"hfo": 1}, cii_type="bulk", capacity=82_000,
                      distance_nm=40_000, eu_share=user_share(0.25))
    eu = evaluate(profile, Scenario(eua=YearSeries.constant(80), view="eu"))
    ww = evaluate(profile, Scenario(eua=YearSeries.constant(80), view="ww"))
    r_eu, r_ww = eu[2030 - 2024], ww[2030 - 2024]
    assert r_eu.ets.cost == r_ww.ets.cost and r_eu.fueleu.penalty == r_ww.fueleu.penalty   # EU regimes unchanged
    assert r_ww.nzf.cost_eur == pytest.approx(4 * r_eu.nzf.cost_eur, rel=1e-9)            # IMO on worldwide activity
    assert r_eu.cii.attained == pytest.approx(r_ww.cii.attained)                           # CII is ratio-invariant
    assert r_eu.total_eur == pytest.approx(r_eu.ets.cost + r_eu.fueleu.penalty + r_eu.nzf.cost_eur)
    assert not math.isnan(r_eu.cii.attained)


def test_rules_bundle_loads():
    r = Rules.load()
    assert r.fueleu.target(2030) == pytest.approx(91.16 * 0.94)
