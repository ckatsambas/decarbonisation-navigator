"""Ship power model (decision 0009-3): the bottom-up method of the Fourth IMO GHG Study 2020.

A year of operation is split into the energy of five consumers:

    main engine at sea      P_ME = δw · MCR · (v / v_ref)³ / (ηw · ηf)          (Admiralty law, Eq. 8)
    auxiliary engines       Table 17 power, at sea and at berth
    boilers                 Table 17 power, at sea and at berth
and fuel energy = power × hours × specific consumption, where the main engine's consumption
follows the load curve SFC = SFC_base · (0.455·L² − 0.710·L + 1.280) (Eq. 10).

`calibrate` fits this to a ship's reported year: the auxiliary and boiler demand come from the
study's tables, the main engine gets the rest of the fuel, its load follows from the ship's speed
(distance ÷ hours at sea) against the design speed of its class, and its installed power (MCR)
is whatever makes the reported fuel come out exactly. No hull dimensions are needed.

`run` applies the `Effects` of one or more measures to the calibrated year: lower resistance, wind
thrust, a different speed, better engines, less electrical or heat demand, shore power, other
fuels, carbon capture. Each acts on its own link of the chain, so combinations are not simply
added (a 10% slower ship gains less from a hull coating, wind gives a larger share at low power).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from . import fuels as F
from . import params as _params
from . import reference as R

# Lower calorific values used by the IMO study to convert SFC between fuels (MJ/kg; Table 19 note)
_LCV_TABLE = {"hfo": 40.2, "mdo": 42.7, "lng": 48.0, "methanol": 19.9}
# fuels.json id → SFC family
FAMILY = {"hfo": "hfo", "lfo": "hfo", "mgo": "mdo", "hvo": "mdo", "fame": "mdo", "e_diesel": "mdo",
          "methanol": "methanol", "bio_methanol": "methanol", "e_methanol": "methanol",
          "lng_otto_ms": "lng", "lng_otto_ss": "lng", "lng_diesel_ss": "lng", "lng_lbsi": "lng",
          "bio_lng_otto_ms": "lng", "e_ammonia": "ammonia"}
MIN_MAIN_SHARE = 0.3      # main engine keeps at least this share of the fuel at sea
MIN_LOAD = 0.05
COMPONENTS = ("me", "ae_sea", "bo_sea", "ae_port", "bo_port")


@dataclass(frozen=True)
class PowerRules:
    speed_exp: float
    fouling: float
    weather_default: float
    weather_coastal: float
    coastal: frozenset
    delta_w: dict
    curve: tuple[float, float, float]
    max_load: float
    sfc: dict
    pilot: dict
    aux: dict

    @classmethod
    def load(cls, override_dir: Path | None = None) -> PowerRules:
        ps = _params.load("imo4_power", base_dir=_params.CONFIG_DIR / "model", override_dir=override_dir)
        w = ps["weather_factor"]
        return cls(float(ps["speed_exponent"]), float(ps["fouling_factor"]), float(w["default"]),
                   float(w["coastal"]), frozenset(w["coastal_classes"]), dict(ps["speed_power_correction"]),
                   tuple(ps["sfc_load_curve"]), float(ps["max_load"]), dict(ps["sfc_base"]),
                   dict(ps["pilot_mdo_g_kwh"]), dict(ps["aux_boiler_kw"]))

    def weather(self, key: str) -> float:
        return self.weather_coastal if key in self.coastal else self.weather_default

    def delta(self, key: str) -> float:
        return float(self.delta_w.get(key, self.delta_w.get(key.split(":")[0] + ":*", 1.0)))

    def load_factor(self, load: float) -> float:
        a, b, c = self.curve
        return a * load * load + b * load + c

    def kw(self, key: str, system: str, phase: str) -> float:
        row = self.aux.get(key)
        return float(row[f"{system}_kw"][phase]) if row else 0.0

    def mj_per_kwh(self, system: str, fuel: str, engine: str = "ssd") -> float:
        """Fuel energy per kWh of output at the most efficient point (Table 19, engines from 2001)."""
        fam = FAMILY.get(fuel, "mdo")
        if fam == "ammonia":                 # no IMO value: same efficiency as diesel on distillate
            fam = "mdo"
        if system == "me":
            table = self.sfc["main_" + engine]
            if fam == "lng":
                key = fuel if fuel in table else ("lng_otto_ss" if engine == "ssd" else "lng_otto_ms")
                g = table.get(key, 156)
                return (g * _LCV_TABLE["lng"] + self.pilot.get(key, 0) * _LCV_TABLE["mdo"]) / 1000
            return table[fam] * _LCV_TABLE[fam] / 1000
        table = self.sfc["aux" if system == "ae" else "boiler"]
        fam = "mdo" if fam == "methanol" else fam
        return table[fam] * _LCV_TABLE[fam] / 1000


@lru_cache(maxsize=1)
def default_rules() -> PowerRules:
    return PowerRules.load()


def _mix_mj_per_kwh(rules: PowerRules, system: str, mix: F.FuelMix, fuels: dict[str, F.Fuel], engine: str) -> float:
    """Energy-weighted efficiency of a fuel mix (mass shares)."""
    m = F.normalise(mix)
    e = {k: s * fuels[k].lcv for k, s in m.items()}
    tot = sum(e.values()) or 1.0
    return sum(v / tot * rules.mj_per_kwh(system, k, engine) for k, v in e.items())


@dataclass(frozen=True)
class ShipPower:
    """One calibrated year of operation (EU-recorded scope for MRV ships)."""
    cls_key: str
    hours_sea: float
    hours_port: float
    distance_nm: float
    design_speed: float
    mcr_kw: float
    me_kw: float
    load: float
    ae_sea_kw: float
    bo_sea_kw: float
    ae_port_kw: float
    bo_port_kw: float
    mix: F.FuelMix
    engine: str = "ssd"
    method: str = "calibrated"

    @property
    def speed(self) -> float:
        return self.distance_nm / self.hours_sea if self.hours_sea > 0 else 0.0


@dataclass(frozen=True)
class Effects:
    """What a set of measures changes. Factors multiply, kW add; see `combine`."""
    speed: float = 1.0           # × speed at sea (same distance → hours change)
    resistance: float = 1.0      # × propulsion power at a given speed (hull, propeller, trim, routing)
    wind_kw: float = 0.0         # thrust power delivered by wind at sea (kW, average)
    me_energy: float = 1.0       # × main engine fuel energy per kWh (tuning)
    ae_sea: float = 1.0          # × auxiliary power at sea
    ae_port: float = 1.0         # × auxiliary power at berth
    boiler: float = 1.0          # × boiler heat demand
    ae_extra_kw: float = 0.0     # added electrical load at sea (e.g. air-lubrication compressors)
    whr_share: float = 0.0       # electricity recovered from main engine exhaust, share of ME power
    shore: float = 0.0           # share of berth electricity taken from shore
    battery_port: float = 0.0    # share of berth electricity from batteries charged ashore
    port_hours: float = 1.0      # × hours at berth
    anchor_to_sea: float = 0.0   # hours of waiting replaced by slower sailing (just-in-time arrival)
    mix: F.FuelMix | None = None         # new fuel mix (mass shares) for all engines, None = keep
    dual_share: float = 1.0      # energy share run on the new mix (the rest on the old one)
    engine: str | None = None    # engine family after a conversion ("ssd" / "msd"); None = keep
    capture: float = 0.0         # share of tank-to-wake CO2 captured on board
    capture_energy: float = 0.0  # extra fuel energy per unit of energy for capture (× total)

    @staticmethod
    def combine(*items: Effects) -> Effects:
        out = Effects()
        for e in items:
            out = replace(
                out, speed=out.speed * e.speed, resistance=out.resistance * e.resistance,
                wind_kw=out.wind_kw + e.wind_kw, me_energy=out.me_energy * e.me_energy,
                ae_sea=out.ae_sea * e.ae_sea, ae_port=out.ae_port * e.ae_port, boiler=out.boiler * e.boiler,
                ae_extra_kw=out.ae_extra_kw + e.ae_extra_kw, whr_share=out.whr_share + e.whr_share,
                shore=min(1.0, out.shore + e.shore), battery_port=min(1.0, out.battery_port + e.battery_port),
                port_hours=out.port_hours * e.port_hours, anchor_to_sea=out.anchor_to_sea + e.anchor_to_sea,
                mix=e.mix if e.mix is not None else out.mix,
                dual_share=e.dual_share if e.mix is not None else out.dual_share,
                engine=e.engine or out.engine,
                capture=1 - (1 - out.capture) * (1 - e.capture),
                capture_energy=out.capture_energy + e.capture_energy)
        return out


@dataclass(frozen=True)
class PowerResult:
    energy_mj: dict[str, float]          # by component
    fuel_t: dict[str, float]             # by fuel id, sea and port together
    fuel_sea_t: dict[str, float]
    fuel_port_t: dict[str, float]
    grid_kwh: float                      # shore electricity
    hours_sea: float
    me_kw: float
    load: float
    co2_captured_t: float = 0.0

    @property
    def total_mj(self) -> float:
        return sum(self.energy_mj.values())

    def mix(self) -> F.FuelMix:
        tot = sum(self.fuel_t.values()) or 1.0
        return {k: v / tot for k, v in self.fuel_t.items() if v > 0}

    def co2_t(self, fuels: dict[str, F.Fuel], part: str = "all") -> float:
        src = {"all": self.fuel_t, "sea": self.fuel_sea_t, "port": self.fuel_port_t}[part]
        return sum(t * fuels[k].cf_co2 for k, t in src.items())


def class_of(cls_key: str) -> R.SizeClass:
    return R.by_key(cls_key)


def calibrate(cls_key: str, fuel_sea_t: float, fuel_port_t: float, hours_sea: float, distance_nm: float,
              mix: F.FuelMix, rules: PowerRules | None = None, fuels: dict[str, F.Fuel] | None = None,
              engine: str = "ssd") -> ShipPower:
    """Fit the IMO-study model to a reported year (fuel in tonnes, by sea and berth)."""
    rules = rules or default_rules()
    fuels = fuels or F.load()
    c = class_of(cls_key)
    lcv = F.energy_per_t(mix, fuels)                       # MJ per tonne of the mix
    mj_ae = _mix_mj_per_kwh(rules, "ae", mix, fuels, engine)
    mj_bo = _mix_mj_per_kwh(rules, "bo", mix, fuels, engine)
    mj_me = _mix_mj_per_kwh(rules, "me", mix, fuels, engine)
    # berth: hours follow from the reported berth fuel and the table's berth demand
    ae_b, bo_b = rules.kw(cls_key, "aux", "berth"), rules.kw(cls_key, "boiler", "berth")
    port_mj_per_h = ae_b * mj_ae + bo_b * mj_bo
    e_port = fuel_port_t * lcv
    hours_port = min(e_port / port_mj_per_h, max(8760 - hours_sea, 0)) if port_mj_per_h > 0 else 0.0
    if hours_port > 0 and hours_port * port_mj_per_h < e_port:       # more fuel than the table explains
        scale = e_port / (hours_port * port_mj_per_h)
        ae_b, bo_b = ae_b * scale, bo_b * scale
    # sea: auxiliaries from the table, the main engine gets the rest
    ae_s, bo_s = rules.kw(cls_key, "aux", "sea"), rules.kw(cls_key, "boiler", "sea")
    e_sea = fuel_sea_t * lcv
    h = max(hours_sea, 1.0)
    e_aux = (ae_s * mj_ae + bo_s * mj_bo) * h
    if e_sea - e_aux < MIN_MAIN_SHARE * e_sea:
        k = (1 - MIN_MAIN_SHARE) * e_sea / e_aux if e_aux > 0 else 0.0
        ae_s, bo_s, e_aux = ae_s * k, bo_s * k, e_aux * k
    e_me = e_sea - e_aux
    v = distance_nm / h
    v_ref = c.value("design_speed")
    load = rules.delta(cls_key) * (v / v_ref) ** rules.speed_exp / (rules.weather(cls_key) * rules.fouling)
    load = min(max(load, MIN_LOAD), rules.max_load)
    me_kw = e_me / (h * mj_me * rules.load_factor(load))
    return ShipPower(cls_key, hours_sea, hours_port, distance_nm, v_ref, me_kw / load, me_kw, load,
                     ae_s, bo_s, ae_b, bo_b, dict(mix), engine)


def run(sp: ShipPower, eff: Effects | None = None, rules: PowerRules | None = None,
        fuels: dict[str, F.Fuel] | None = None) -> PowerResult:
    """Energy and fuel of the year with the measures' effects applied (no effects = the calibrated year)."""
    rules = rules or default_rules()
    fuels = fuels or F.load()
    e = eff or Effects()
    v0 = sp.speed or 1.0
    v = v0 * e.speed
    h = sp.hours_sea * v0 / v if v > 0 else sp.hours_sea
    # just-in-time: some waiting at anchor becomes slower sailing; modelled as the same distance over more
    # hours at sea, which lowers the speed (the hours are capped at the waiting that is removed)
    if e.anchor_to_sea > 0:
        h_new = h * (1 + e.anchor_to_sea)
        v, h = v * h / h_new, h_new
    me_kw = sp.me_kw * (v / v0) ** rules.speed_exp * e.resistance
    me_kw = max(me_kw - e.wind_kw, 0.05 * sp.mcr_kw)
    load = min(max(me_kw / sp.mcr_kw, MIN_LOAD), 1.0)
    engine = e.engine or sp.engine
    new_mix, share = e.mix, e.dual_share if e.mix is not None else 0.0

    def mj_kwh(system: str) -> float:
        base = _mix_mj_per_kwh(rules, system, sp.mix, fuels, sp.engine)
        if new_mix is None:
            return base
        alt = _mix_mj_per_kwh(rules, system, new_mix, fuels, engine)
        return (1 - share) * base + share * alt

    whr_kw = e.whr_share * me_kw
    ae_sea_kw = max(sp.ae_sea_kw * e.ae_sea + e.ae_extra_kw - whr_kw, 0.0)
    port_h = sp.hours_port * e.port_hours
    berth_elec = sp.ae_port_kw * e.ae_port * port_h
    grid = berth_elec * min(e.shore + e.battery_port, 1.0)
    energy = {
        "me": me_kw * h * mj_kwh("me") * rules.load_factor(load) * e.me_energy,
        "ae_sea": ae_sea_kw * h * mj_kwh("ae"),
        "bo_sea": sp.bo_sea_kw * e.boiler * h * mj_kwh("bo"),
        "ae_port": (berth_elec - grid) * mj_kwh("ae"),
        "bo_port": sp.bo_port_kw * e.boiler * port_h * mj_kwh("bo"),
    }
    if e.capture_energy:
        energy = {k: v * (1 + e.capture_energy) for k, v in energy.items()}

    def split(mj: float) -> dict[str, float]:
        """Tonnes per fuel for an amount of energy, burnt as the old and new mixes by energy share."""
        out: dict[str, float] = {}
        for m, s in ((sp.mix, 1 - share), (new_mix or {}, share)):
            if s <= 0 or not m:
                continue
            per_t = F.energy_per_t(m, fuels)
            for k, ms in F.normalise(m).items():
                out[k] = out.get(k, 0.0) + mj * s / per_t * ms
        return out

    sea = split(energy["me"] + energy["ae_sea"] + energy["bo_sea"])
    port = split(energy["ae_port"] + energy["bo_port"])
    total = {k: sea.get(k, 0.0) + port.get(k, 0.0) for k in set(sea) | set(port)}
    captured = e.capture * sum(t * fuels[k].cf_co2 for k, t in total.items())
    return PowerResult(energy, total, sea, port, grid, h, me_kw, load, captured)


@dataclass(frozen=True)
class Calibration:
    """How well the model reproduces its own input (always 1.0 by construction) and the derived state."""
    ship: ShipPower
    base: PowerResult
    details: dict = field(default_factory=dict)


def from_class(cls_key: str, year: str = "2018", rules: PowerRules | None = None,
               fuels: dict[str, F.Fuel] | None = None, mix: F.FuelMix | None = None,
               engine: str = "ssd") -> ShipPower:
    """Calibrate on an IMO class average (standard ships): fuel split by main/aux/boiler is given."""
    rules = rules or default_rules()
    fuels = fuels or F.load()
    c = class_of(cls_key)
    y = c.years[year]
    mix = mix or {"hfo": 1.0}
    h = y["days_at_sea"] * 24
    lcv = F.energy_per_t(mix, fuels)
    mj_ae = _mix_mj_per_kwh(rules, "ae", mix, fuels, engine)
    mj_bo = _mix_mj_per_kwh(rules, "bo", mix, fuels, engine)
    sea_aux_t = (rules.kw(cls_key, "aux", "sea") * mj_ae + rules.kw(cls_key, "boiler", "sea") * mj_bo) * h / lcv
    aux_t = (y["fuel_aux_kt"] + y["fuel_boiler_kt"]) * 1000
    port_t = max(aux_t - sea_aux_t, 0.0)
    sea_t = y["fuel_main_kt"] * 1000 + min(sea_aux_t, aux_t)
    sp = calibrate(cls_key, sea_t, port_t, h, y["distance_nm"], mix, rules, fuels, engine)
    return replace(sp, method="class")
