"""Fuels and fuel mixes: energy content and well-to-wake GHG intensity.

Per fuel (FuelEU Annex II method, GWP set by the regime that uses it):

    TtW = [(1 − slip)·(Cf_CO2 + Cf_CH4·GWP_CH4 + Cf_N2O·GWP_N2O) + slip·GWP_CH4] / LCV     [gCO2e/MJ]
    WtW = WtT + TtW

A mix is given as mass shares. Its intensity is energy-weighted; FuelEU's RFNBO reward factor
multiplies the energy of RFNBO fuels in the denominator.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import params as _params

FuelMix = dict[str, float]          # fuel id → mass share (sums to 1)


@dataclass(frozen=True)
class Fuel:
    id: str
    name: dict
    lcv: float          # MJ/g
    wtt: float          # gCO2e/MJ
    cf_co2: float       # t CO2 / t fuel
    cf_ch4: float
    cf_n2o: float
    slip: float         # % of fuel mass
    kind: str           # fossil | bio | rfnbo

    def ttw(self, gwp: dict[str, float]) -> float:
        s = self.slip / 100
        combusted = self.cf_co2 * gwp["co2"] + self.cf_ch4 * gwp["ch4"] + self.cf_n2o * gwp["n2o"]
        return ((1 - s) * combusted + s * gwp["ch4"]) / self.lcv

    def wtw(self, gwp: dict[str, float]) -> float:
        return self.wtt + self.ttw(gwp)

    def energy_mj_per_t(self) -> float:
        return self.lcv * 1e6


def load(override_dir: Path | None = None) -> dict[str, Fuel]:
    ps = _params.load("fuels", override_dir=override_dir)
    return {k: Fuel(id=k, **p.value) for k, p in ps.values.items()}


def normalise(mix: FuelMix) -> FuelMix:
    total = sum(v for v in mix.values() if v > 0)
    if total <= 0:
        raise ValueError("Fuel mix is empty")
    return {k: v / total for k, v in mix.items() if v > 0}


def co2_per_t(mix: FuelMix, fuels: dict[str, Fuel]) -> float:
    """Mass-weighted CO2 factor of the mix (t CO2 per t fuel)."""
    return sum(share * fuels[k].cf_co2 for k, share in normalise(mix).items())


def energy_per_t(mix: FuelMix, fuels: dict[str, Fuel]) -> float:
    """MJ per tonne of mixed fuel."""
    return sum(share * fuels[k].energy_mj_per_t() for k, share in normalise(mix).items())


def intensity(mix: FuelMix, fuels: dict[str, Fuel], gwp: dict[str, float],
              rfnbo_factor: float = 1.0) -> float:
    """Well-to-wake GHG intensity of the mix, gCO2e/MJ."""
    num = den = 0.0
    for k, share in normalise(mix).items():
        f = fuels[k]
        e = share * f.energy_mj_per_t()
        num += e * f.wtw(gwp)
        den += e * (rfnbo_factor if f.kind == "rfnbo" else 1.0)
    return num / den


def fuel_tonnes(co2_t: float, mix: FuelMix, fuels: dict[str, Fuel]) -> float:
    """Fuel burned to emit `co2_t` tonnes of CO2 with this mix."""
    cf = co2_per_t(mix, fuels)
    return co2_t / cf if cf > 0 else 0.0


def infer_mix(co2_per_fuel: float | None, lng_engine: str = "lng_otto_ss") -> tuple[FuelMix, str]:
    """Estimate the fuel mix from a ship's reported CO2 ÷ fuel ratio (EU MRV).

    Oil-fuelled ships fall between HFO (3.114) and MDO/MGO (3.206) and are split between the two;
    a lower ratio indicates LNG, split between LNG (2.750) and MGO as pilot/other fuel.
    Returns the mix and a code for the explanation shown to the user.
    """
    if co2_per_fuel is None or co2_per_fuel <= 0:
        return {"hfo": 1.0}, "default"
    cf = co2_per_fuel
    if cf >= 3.10:
        s = min(max((cf - 3.114) / (3.206 - 3.114), 0.0), 1.0)
        return normalise({"hfo": 1 - s, "mgo": s}), "oil"
    s = min(max((3.206 - cf) / (3.206 - 2.750), 0.0), 1.0)
    return normalise({lng_engine: s, "mgo": 1 - s}), "lng"
