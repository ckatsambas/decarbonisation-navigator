"""Power model (IMO study bottom-up method), measure library and investment appraisal."""
import pytest

from navigator.engine import economics as EC
from navigator.engine import library as L
from navigator.engine import measures as M
from navigator.engine import power as PW
from navigator.engine import reference as R
from navigator.engine.compliance import Rules, Scenario, evaluate
from navigator.engine.models import YearSeries

RULES = Rules.load()
KAMSARMAX = "bulk:60000-99999"


def total_t(r: PW.PowerResult) -> float:
    return sum(r.fuel_t.values())


def test_sfc_curve_and_table_values():
    pr = PW.default_rules()
    assert pr.load_factor(0.8) == pytest.approx(1.0032, abs=1e-4)          # minimum near 80% MCR
    assert pr.load_factor(0.3) > pr.load_factor(0.8)
    assert pr.mj_per_kwh("me", "hfo") == pytest.approx(175 * 40.2 / 1000)
    assert pr.mj_per_kwh("me", "lng_diesel_ss") == pytest.approx((135 * 48 + 6 * 42.7) / 1000)
    assert pr.kw(KAMSARMAX, "aux", "sea") == 410 and pr.kw("oil:200000-+", "boiler", "berth") == 7000
    assert pr.weather("ropax:20000-+") == pytest.approx(0.909) and pr.weather(KAMSARMAX) == pytest.approx(0.867)
    assert pr.delta("cruise:60000-99999") == pytest.approx(0.70) and pr.delta("container:20000-+") == pytest.approx(0.75)


def test_calibration_reproduces_reported_fuel():
    c = R.by_key(KAMSARMAX)
    sp = PW.from_class(KAMSARMAX)
    y = c.years["2018"]
    reported = (y["fuel_main_kt"] + y["fuel_aux_kt"] + y["fuel_boiler_kt"]) * 1000
    assert total_t(PW.run(sp)) == pytest.approx(reported, rel=1e-9)
    assert sp.speed == pytest.approx(y["distance_nm"] / (y["days_at_sea"] * 24))
    assert 0.6 < sp.mcr_kw / y["power_kw"] < 1.2                          # implied engine close to the IMO average


def test_speed_cut_follows_cube_law_with_fixed_auxiliaries():
    sp = PW.from_class(KAMSARMAX)
    base, slow = PW.run(sp), PW.run(sp, PW.Effects(speed=0.9))
    assert slow.hours_sea == pytest.approx(sp.hours_sea / 0.9)
    assert slow.me_kw == pytest.approx(sp.me_kw * 0.9 ** 3)
    me_ratio = slow.energy_mj["me"] / base.energy_mj["me"]
    # per mile ∝ v², corrected by the SFC load curve (lower load → higher SFC)
    lf = PW.default_rules().load_factor
    assert me_ratio == pytest.approx(0.81 * lf(slow.load) / lf(sp.load), rel=1e-6)
    assert slow.energy_mj["ae_sea"] > base.energy_mj["ae_sea"]            # longer at sea
    assert base.energy_mj["ae_port"] == slow.energy_mj["ae_port"]


def test_effects_combine_and_wind_matters_more_at_low_power():
    e = PW.Effects.combine(PW.Effects(resistance=0.95), PW.Effects(resistance=0.97, wind_kw=200),
                           PW.Effects(wind_kw=100, capture=0.5), PW.Effects(capture=0.5))
    assert e.resistance == pytest.approx(0.95 * 0.97) and e.wind_kw == 300 and e.capture == pytest.approx(0.75)
    sp = PW.from_class(KAMSARMAX)
    fast = 1 - total_t(PW.run(sp, PW.Effects(wind_kw=500))) / total_t(PW.run(sp))
    slow_base = PW.run(sp, PW.Effects(speed=0.8))
    slow = 1 - total_t(PW.run(sp, PW.Effects(speed=0.8, wind_kw=500))) / total_t(slow_base)
    assert slow > fast > 0


def test_fuel_switch_and_shore_power():
    sp = PW.from_class(KAMSARMAX)
    base = PW.run(sp)
    meoh = PW.run(sp, PW.Effects(mix={"bio_methanol": 1.0}, dual_share=0.95))
    assert meoh.mix()["bio_methanol"] > 0.9
    assert meoh.total_mj == pytest.approx(base.total_mj, rel=0.03)        # similar engine efficiency
    shore = PW.run(sp, PW.Effects(shore=1.0))
    assert shore.energy_mj["ae_port"] == 0 and shore.grid_kwh == pytest.approx(sp.ae_port_kw * sp.hours_port)


def test_library_has_25_measures_in_five_groups_and_clashes():
    lib = M.load()
    main = [m for m in lib if not m.note.startswith("Variant")]
    assert len(main) == 25
    assert {m.group for m in main} == set(M.GROUPS)
    assert ("lng_dual_fuel", "methanol_dual_fuel") in lib.clashes(["lng_dual_fuel", "methanol_dual_fuel"])
    assert not lib.clashes(["hull_coating", "rotor_sails"])
    for m in lib:
        assert all(r in lib.sources for r in m.refs), m.key
        assert m.name.get("el") and m.name.get("en")


def test_applicability_and_scaling():
    lib = M.load()
    assert not lib["steam_plant"].applies_to("bulk")[0] and lib["steam_plant"].applies_to("oil")[0]
    assert lib["waste_heat_recovery"].applies_to("bulk", 8000) == (False, "engine")
    rotor = lib["rotor_sails"]
    cape, handy, small = R.by_key("bulk:200000-+"), R.by_key("bulk:10000-34999"), R.by_key("bulk:0-9999")
    assert not rotor.applies_to("container", cls=R.by_key("container:3000-4999"))[0]     # EMSA: no deck space
    assert rotor.applies_to("bulk", cls=small) == (False, "size")
    assert rotor.n_units(handy) == 1 and rotor.n_units(cape) == 4                            # EMSA 2023 Table 6
    assert M.tier_of(handy) == 0 and M.tier_of(cape) == 2
    sp_s, sp_b = PW.from_class(handy.key), PW.from_class(cape.key)
    assert rotor.capex_usd(sp_b, cape) > 4 * rotor.capex_usd(sp_s, handy)                   # more and larger rotors
    als = lib["air_lubrication"]
    assert als.value.for_ship(R.by_key("oil:200000-+")).likely < als.value.for_ship(R.by_key("gas:100000-199999")).likely
    occ = lib["carbon_capture"]
    sp = PW.from_class(KAMSARMAX)
    captured = occ.value.quantile(0.5) * PW.run(sp).co2_t(RULES.fuels)
    assert occ.capex_usd(sp, R.by_key(KAMSARMAX)) == pytest.approx(captured * occ.capex.value.quantile(0.5))


def test_measures_reach_the_regimes_and_appraisal():
    c = R.by_key(KAMSARMAX)
    model = M.model_for(L.profile(c, "deep_sea"))
    lib = M.load()
    sc = Scenario(eua=YearSeries.constant(100), view="ww", baseline="pay")
    path = M.ship_path(model, [lib["hull_coating"]], start=2027)
    res = evaluate(model.profile, sc, rules=RULES, path=path)
    base = evaluate(model.profile, sc, rules=RULES)
    y26, y30 = 2026 - 2024, 2030 - 2024
    assert res[y26].ets.cost == pytest.approx(base[y26].ets.cost)           # not yet installed
    assert res[y30].ets.cost < base[y30].ets.cost
    # biofuel is zero-rated in the ETS but still burnt (FuelEU energy unchanged)
    bio = evaluate(model.profile, sc, rules=RULES, path=M.ship_path(model, [lib["biofuel_b100"]], 2026))
    assert bio[y30].ets.cost == pytest.approx(0, abs=1) and bio[y30].fueleu.balance_t > 0
    assert bio[y30].fueleu.energy_mj == pytest.approx(base[y30].fueleu.energy_mj, rel=0.01)
    a = EC.appraise(model, [lib["hull_coating"]], sc, 2026, rules=RULES, build_year=2015)
    assert a.flows[0].year == 2026 and a.flows[-1].year == 2040          # 25-year ship life
    assert a.co2e_avoided > 0 and a.carbon_saved > 0
    hi = EC.appraise(model, [lib["hull_coating"]], sc, 2026, rules=RULES, build_year=2015, discount=0.10)
    lo = EC.appraise(model, [lib["hull_coating"]], sc, 2026, rules=RULES, build_year=2015, discount=0.06)
    assert lo.npv > hi.npv


def test_mrv_profile_calibrates(mrv_db_path):
    from navigator.data.mrv import MrvDatabase
    db = MrvDatabase(mrv_db_path)
    y = db.latest(db.search("old name")[0].imo)
    model = M.model_for(y.profile())
    assert total_t(model.base) == pytest.approx(
        model.profile.emissions.co2.total / 3.114, rel=0.05)
