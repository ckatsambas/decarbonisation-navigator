"""Fourth IMO GHG Study 2020 fleet reference: ship type × size class averages, 2012–2018.

Data: navigator/config/reference/imo4_fleet.json, extracted by tools/extract_imo4.py from the
study's Annex Tables 75–81 (and Table 92 for validation).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "config" / "reference" / "imo4_fleet.json"

# EU MRV ship type → IMO study type
MRV_TO_IMO = {
    "Bulk carrier": "bulk", "Combination carrier": "bulk", "Oil tanker": "oil", "Chemical tanker": "chemical",
    "Container ship": "container", "Gas carrier": "gas", "LNG carrier": "gas", "General cargo ship": "general_cargo",
    "Refrigerated cargo carrier": "reefer", "Vehicle carrier": "vehicle", "Ro-ro ship": "roro",
    "Container/ro-ro cargo ship": "roro", "Ro-pax ship": "ropax", "Passenger ship": "ferry_pax",
    "Passenger ship (Cruise Passenger ship)": "cruise", "Other ship types": "service_other",
    "Other ship types (Offshore)": "offshore",
}


@dataclass(frozen=True)
class SizeClass:
    type: str
    label: str
    unit: str                 # unit of the class bounds: dwt | teu | cbm | gt
    size: str                 # e.g. "60000-99999", "200000-+"
    years: dict               # year → field → value

    @property
    def key(self) -> str:
        return f"{self.type}:{self.size}"

    @property
    def bounds(self) -> tuple[float, float]:
        lo, hi = self.size.split("-")
        return float(lo), (math.inf if hi in ("+", "") else float(hi) + 1)

    @property
    def latest(self) -> dict:
        return self.years[max(self.years)]

    def value(self, field: str, year: str | None = None) -> float:
        return float(self.years[year or max(self.years)][field])

    def series(self, field: str) -> list[float]:
        return [float(v[field]) for _, v in sorted(self.years.items())]

    @property
    def gt_mid(self) -> float:
        """Representative gross tonnage of a GT-bounded class (geometric middle; open top: 1.4 × lower)."""
        lo, hi = self.bounds
        lo = max(lo, 100.0)
        return lo * 1.4 if math.isinf(hi) else math.sqrt(lo * hi)

    def fuel_per_nm(self, year: str | None = None) -> float:
        """Average fuel per nautical mile sailed, kg/nm (main + auxiliary + boiler, at sea and in port)."""
        y = self.years[year or max(self.years)]
        kt = y["fuel_main_kt"] + y["fuel_aux_kt"] + y["fuel_boiler_kt"]
        return kt * 1e6 / y["distance_nm"] if y["distance_nm"] else math.nan

    def fuel_t(self, year: str | None = None) -> float:
        y = self.years[year or max(self.years)]
        return (y["fuel_main_kt"] + y["fuel_aux_kt"] + y["fuel_boiler_kt"]) * 1000


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def classes() -> tuple[SizeClass, ...]:
    return tuple(SizeClass(c["type"], c["label"], c["unit"], c["size"], c["years"]) for c in _load()["classes"])


def of_type(imo_type: str) -> list[SizeClass]:
    return [c for c in classes() if c.type == imo_type]


def by_key(key: str) -> SizeClass:
    return next(c for c in classes() if c.key == key)


def source_title() -> str:
    return _load()["source"]["title"]


def mrv_2018() -> list[dict]:
    return _load()["mrv_2018"]["rows"]


def class_for(imo_type: str, dwt: float | None = None, gt: float | None = None) -> SizeClass | None:
    """Size class of a ship: by the class bounds when they are in DWT or GT, otherwise (TEU, m³) by the
    class whose average DWT is nearest on a log scale."""
    cs = of_type(imo_type)
    if not cs:
        return None
    unit = cs[0].unit
    value = dwt if unit == "dwt" else gt if unit == "gt" else None
    if value is not None and value > 0:
        for c in cs:
            lo, hi = c.bounds
            if lo <= value < hi:
                return c
        return cs[-1] if value >= cs[-1].bounds[0] else cs[0]
    if dwt and dwt > 0:
        return min(cs, key=lambda c: abs(math.log(max(c.value("dwt"), 1)) - math.log(dwt)))
    return None
