"""Measure library (decision 0009): 25 measures that adapt to each ship.

Each measure in `config/technology/measures.json` declares
- where it applies (ship types, minimum engine power, retrofit or newbuild),
- what it changes in the power model (`engine.power.Effects`) as a min / likely / max range,
- how its cost scales with the ship (fixed, per kW of engine power, per unit of equipment, ...),
- lifetime, days off-hire, the measures it cannot be combined with, and the qualitative
  attributes that Phase 4 turns into criteria (maturity, fuel availability, safety, cargo space).

`effects()` turns a measure into power-model effects at a chosen quantile (0 = least favourable
for the ship, 0.5 ≈ most likely, 1 = most favourable), so the SMAA in Phase 4 can sample them.
`ship_path()` runs the power model and returns, year by year, what each regime sees.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import fuels as F
from . import params as _params
from . import power as PW
from . import reference as R
from .compliance import Profile, YearState
from .models import AnnualEmissions, ScopeSplit
from .uncertainty import Estimate

GROUPS = ("operation", "hull", "machinery", "wind", "fuel")
CONFIG = _params.CONFIG_DIR / "technology"
# Size tiers for equipment that comes in small / medium / large versions (wind units, air lubrication):
# lower bounds of the medium and large tiers in each class unit
TIER_BOUNDS = {"dwt": (35000, 100000), "teu": (3000, 8000), "cbm": (50000, 150000), "gt": (20000, 60000)}


def tier_of(cls: R.SizeClass) -> int:
    lo = cls.bounds[0]
    mid, big = TIER_BOUNDS.get(cls.unit, (35000, 100000))
    return 2 if lo >= big else 1 if lo >= mid else 0


@dataclass(frozen=True)
class Ranged:
    """A range that may depend on the ship: one Estimate, one per ship type, or one per size tier."""
    base: Estimate
    by_type: dict = field(default_factory=dict)
    tiers: tuple = ()

    @classmethod
    def parse(cls, d, default: float = 0.0) -> Ranged:
        if isinstance(d, dict) and "by_type" in d:
            bt = {k: _est(v) for k, v in d["by_type"].items()}
            return cls(bt.get("*", next(iter(bt.values()))), bt)
        if isinstance(d, dict) and "tiers" in d:
            ts = tuple(_est(v) for v in d["tiers"])
            return cls(ts[1], {}, ts)
        return cls(_est(d, default))

    def for_ship(self, cls: R.SizeClass | None) -> Estimate:
        if cls is None:
            return self.base
        if self.tiers:
            return self.tiers[tier_of(cls)]
        if self.by_type:
            return self.by_type.get(cls.type, self.by_type.get("*", self.base))
        return self.base

    def quantile(self, q: float, cls: R.SizeClass | None = None) -> float:
        return self.for_ship(cls).quantile(q)

    @property
    def low(self) -> float:
        return self.base.low

    @property
    def likely(self) -> float:
        return self.base.likely

    @property
    def high(self) -> float:
        return self.base.high


def _est(d: dict | float | None, default: float = 0.0) -> Estimate:
    if d is None:
        return Estimate.exact(default)
    if isinstance(d, (int, float)):
        return Estimate.exact(float(d))
    return Estimate(float(d["low"]), float(d["likely"]), float(d["high"]))


@dataclass(frozen=True)
class Cost:
    basis: str                 # fixed | per_kw | per_unit | per_kwh | per_dwt | capex_share
    value: Ranged              # USD per basis unit (capex_share: fraction of CAPEX per year)

    def amount(self, q: float, size: float, capex: float = 0.0, cls: R.SizeClass | None = None) -> float:
        v = self.value.quantile(q, cls)
        if self.basis == "fixed":
            return v
        if self.basis == "capex_share":
            return v * capex
        return v * size


@dataclass(frozen=True)
class Measure:
    key: str
    group: str
    name: dict
    how: dict
    effect: str                          # which link of the power model it acts on
    value: Ranged                        # saving fraction / kW per unit / share, as the effect needs
    extra: dict                          # effect-specific settings (fuel mix, compressor power, ...)
    types: tuple[str, ...]               # IMO study types, or ("*",)
    exclude_types: tuple[str, ...]
    min_mcr_kw: float
    retrofit: bool
    newbuild: bool
    capex: Cost
    opex: Cost
    lifetime: Estimate
    offhire_days: Estimate
    excludes: tuple[str, ...]
    attributes: dict
    refs: tuple[str, ...]
    status: str = "verify"
    note: str = ""
    units: dict = field(default_factory=dict)      # equipment count: type → {lower bound: count}

    def applies_to(self, imo_type: str, mcr_kw: float = 0.0, cls: R.SizeClass | None = None) -> tuple[bool, str]:
        if imo_type in self.exclude_types:
            return False, "type"
        if "*" not in self.types and imo_type not in self.types:
            return False, "type"
        if mcr_kw and mcr_kw < self.min_mcr_kw:
            return False, "engine"
        if cls is not None and self.units and self.n_units(cls) == 0:
            return False, "size"
        return True, ""

    def n_units(self, cls: R.SizeClass) -> int:
        """Equipment count (e.g. wind units, EMSA 2023 Table 6) for the ship's type and size class."""
        if not self.units:
            return 1
        table = self.units.get(cls.type, self.units.get("*"))
        if table is None:
            return 0
        lo = cls.bounds[0]
        n = 0
        for threshold, count in sorted((float(k), int(v)) for k, v in table.items()):
            if lo >= threshold:
                n = count
        return n

    def size_basis(self, sp: PW.ShipPower, cls: R.SizeClass) -> float:
        b = self.capex.basis
        if b == "per_kw":
            return sp.mcr_kw
        if b == "per_unit":
            return float(self.n_units(cls))
        if b == "per_kwh":
            return float(self.extra.get("battery_kwh_per_kw_aux", 1.0)) * max(sp.ae_sea_kw, sp.ae_port_kw, 100.0)
        if b == "per_dwt":
            return cls.value("dwt")
        if b == "per_t_captured":                      # tonnes of CO2 captured a year (carbon capture)
            return self.value.quantile(0.5, cls) * PW.run(sp).co2_t(F.load())
        return 1.0

    def capex_usd(self, sp: PW.ShipPower, cls: R.SizeClass, q: float = 0.5) -> float:
        return self.capex.amount(q, self.size_basis(sp, cls), cls=cls)

    def opex_usd(self, sp: PW.ShipPower, cls: R.SizeClass, q: float = 0.5) -> float:
        cap = self.capex_usd(sp, cls, q)
        b = self.opex.basis
        if b == "per_t_captured":
            size = self.value.quantile(0.5, cls) * PW.run(sp).co2_t(F.load())
        elif b in ("fixed", "capex_share"):
            size = 1.0
        else:
            size = self.size_basis(sp, cls)
        out = self.opex.amount(q, size, cap, cls)
        extra = self.extra.get("maintenance_share")
        if extra is not None:
            out += float(extra) * cap
        return out

    def effects(self, sp: PW.ShipPower, cls: R.SizeClass, q: float = 0.5) -> PW.Effects:
        """Power-model effects at quantile q of the saving range (higher q = larger saving)."""
        x = self.value.quantile(q, cls)
        e, ex = self.effect, self.extra
        if e == "speed":
            return PW.Effects(speed=1 - x)
        if e == "resistance":
            return PW.Effects(resistance=1 - x)
        if e == "me_energy":
            return PW.Effects(me_energy=1 - x)
        if e == "aux":
            return PW.Effects(ae_sea=1 - x, ae_port=1 - x)
        if e == "boiler":
            return PW.Effects(boiler=1 - x)
        if e == "whr":
            return PW.Effects(whr_share=x)
        if e == "wind":
            return PW.Effects(wind_kw=x * self.n_units(cls) * float(ex.get("area_factor", 1.0)))
        if e == "als":
            return PW.Effects(resistance=1 - x, ae_extra_kw=float(ex.get("compressor_share", 0.0)) * sp.me_kw)
        if e == "shore":
            return PW.Effects(shore=x)
        if e == "battery":
            return PW.Effects(me_energy=1 - x, battery_port=float(ex.get("port_share", 0.0)))
        if e == "jit":
            return PW.Effects(anchor_to_sea=x)
        if e == "fuel":
            return PW.Effects(mix=dict(ex["mix"]), dual_share=x, engine=ex.get("engine"))
        if e == "capture":
            return PW.Effects(capture=x, capture_energy=x * float(ex.get("energy_per_capture", 0.0)))
        if e == "none":
            return PW.Effects()
        raise ValueError(f"Unknown effect {e!r} in measure {self.key}")


@dataclass(frozen=True)
class Library:
    measures: dict[str, Measure]
    sources: dict[str, _params.Source]
    params: _params.ParamSet

    def __iter__(self):
        return iter(self.measures.values())

    def __getitem__(self, key: str) -> Measure:
        return self.measures[key]

    def by_group(self, group: str) -> list[Measure]:
        return [m for m in self.measures.values() if m.group == group]

    def clashes(self, keys: Iterable[str]) -> list[tuple[str, str]]:
        ks = list(keys)
        out = []
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                if b in self.measures[a].excludes or a in self.measures[b].excludes:
                    out.append((a, b))
        return out


def _measure(key: str, p: _params.Param) -> Measure:
    v = p.value
    ap = v.get("applies", {})
    eff = v["effect"]
    return Measure(
        key=key, group=v["group"], name=v["name"], how=v.get("how", {}), effect=eff["type"],
        value=Ranged.parse(eff.get("value")), extra={k: x for k, x in eff.items() if k not in ("type", "value")},
        types=tuple(ap.get("types", ["*"])), exclude_types=tuple(ap.get("exclude", [])),
        min_mcr_kw=float(ap.get("min_mcr_kw", 0)), retrofit=bool(ap.get("retrofit", True)),
        newbuild=bool(ap.get("newbuild", True)),
        capex=Cost(v["capex"]["basis"], Ranged.parse(v["capex"])), opex=Cost(v["opex"]["basis"], Ranged.parse(v["opex"])),
        lifetime=_est(v.get("lifetime"), 25), offhire_days=_est(v.get("offhire_days"), 0),
        excludes=tuple(v.get("excludes", [])), attributes=dict(v.get("attributes", {})),
        refs=tuple(v.get("refs", [p.source])), status=p.status, note=p.note, units=dict(v.get("units", {})))


@lru_cache(maxsize=4)
def load(override_dir: Path | None = None) -> Library:
    ps = _params.load("measures", base_dir=CONFIG, override_dir=override_dir)
    return Library({k: _measure(k, p) for k, p in ps.values.items()}, ps.sources, ps)


# ------------------------------------------------------------------ ship → power model → regimes
@dataclass(frozen=True)
class ShipModel:
    """A profile linked to its calibrated power model."""
    profile: Profile
    cls: R.SizeClass
    power: PW.ShipPower
    base: PW.PowerResult


def imo_type(profile: Profile) -> str:
    return R.MRV_TO_IMO.get(profile.ship.ship_type, "service_other")


def model_for(profile: Profile, fuels: dict[str, F.Fuel] | None = None, rules: PW.PowerRules | None = None,
              cls_key: str | None = None, hours_at_sea: float | None = None) -> ShipModel:
    """Calibrate the power model on the profile's EU-recorded year (class and hours can be given)."""
    fuels = fuels or F.load()
    rules = rules or PW.default_rules()
    share = profile.eu_share
    cls_key = cls_key or (share.size_class if share and share.size_class else None)
    cls = R.by_key(cls_key) if cls_key else R.class_for(imo_type(profile), dwt=profile.capacity or None,
                                                         gt=profile.ship.gross_tonnage or None)
    co2 = profile.emissions.co2
    per_t = F.co2_per_t(profile.fuel_mix, fuels) or 3.114
    port_t = co2.in_port / per_t
    sea_t = (co2.total - co2.in_port) / per_t
    hours = hours_at_sea or (share.mrv_hours if share and share.mrv_hours else None)
    if not hours:                                    # no reported time at sea: the class's speed
        v = cls.value("speed_at_sea") or 12.0
        hours = profile.distance_nm / v if profile.distance_nm else cls.value("days_at_sea") * 24
    distance = profile.distance_nm or hours * cls.value("speed_at_sea")
    sp = PW.calibrate(cls.key, sea_t, port_t, hours, distance, profile.fuel_mix, rules, fuels)
    return ShipModel(profile, cls, sp, PW.run(sp, None, rules, fuels))


def _gas_totals(fuel_t: dict[str, float], fuels: dict[str, F.Fuel], zero_kinds: frozenset = frozenset()) -> tuple[float, float, float]:
    co2 = ch4 = n2o = 0.0
    for k, t in fuel_t.items():
        f = fuels[k]
        if f.kind in zero_kinds:
            continue
        co2 += t * f.cf_co2
        ch4 += t * (f.cf_ch4 + f.slip / 100)
        n2o += t * f.cf_n2o
    return co2, ch4, n2o


def _scale(split: ScopeSplit, sea: float, port: float) -> ScopeSplit:
    return ScopeSplit(split.intra_eu * sea, split.in_port * port, split.from_eu * sea, split.to_eu * sea,
                      split.outside * sea)


def year_state(model: ShipModel, result: PW.PowerResult, fuels: dict[str, F.Fuel],
               zero_kinds: frozenset, capture_credit: bool) -> YearState:
    """Scale the reported emissions by the model's ratios (new ÷ calibrated), part by part."""
    em = model.profile.emissions
    b_sea = _gas_totals(model.base.fuel_sea_t, fuels)
    b_port = _gas_totals(model.base.fuel_port_t, fuels)

    def ratios(sea_t: dict, port_t: dict, zk: frozenset, cap: float) -> list[tuple[float, float]]:
        n_sea, n_port = _gas_totals(sea_t, fuels, zk), _gas_totals(port_t, fuels, zk)
        out = []
        for i in range(3):
            rs = n_sea[i] / b_sea[i] if b_sea[i] > 0 else (1.0 if n_sea[i] == 0 else 1.0)
            rp = n_port[i] / b_port[i] if b_port[i] > 0 else 1.0
            if i == 0:
                rs, rp = rs * (1 - cap), rp * (1 - cap)
            out.append((rs, rp))
        return out

    cap = result.co2_captured_t / max(result.co2_t(fuels), 1e-9) if result.co2_captured_t else 0.0
    phys = ratios(result.fuel_sea_t, result.fuel_port_t, frozenset(), 0.0)
    ets = ratios(result.fuel_sea_t, result.fuel_port_t, zero_kinds, cap if capture_credit else 0.0)

    def build(r):
        return AnnualEmissions(_scale(em.co2, *r[0]), _scale(em.ch4, *r[1]), _scale(em.n2o, *r[2]))

    return YearState(build(phys), build(ets), result.mix())


@lru_cache(maxsize=1)
def _ets_rules() -> tuple[frozenset, bool]:
    ps = _params.load("eu_ets_maritime")
    return frozenset(ps["zero_rated_kinds"]), bool(ps["capture_credit"])


def ship_path(model: ShipModel, measures: Iterable[Measure], start: int = 2026, q: float = 0.5,
              fuels: dict[str, F.Fuel] | None = None, rules: PW.PowerRules | None = None,
              capture_credit: bool | None = None):
    """Year → YearState with the measures in place from `start` (before: as reported)."""
    fuels = fuels or F.load()
    rules = rules or PW.default_rules()
    zero, credit = _ets_rules()
    credit = credit if capture_credit is None else capture_credit
    ms = list(measures)
    eff = PW.Effects.combine(*(m.effects(model.power, model.cls, q) for m in ms))
    after = year_state(model, PW.run(model.power, eff, rules, fuels), fuels, zero, credit)
    before = year_state(model, model.base, fuels, zero, credit)
    return lambda y: after if y >= start else before
