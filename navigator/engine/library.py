"""Standard ships: every ship type × size class of the Fourth IMO GHG Study, plus named presets.

For companies or ships without EU MRV data (decision 0007-4). A standard ship takes its annual
fuel, distance and days at sea from the study's 2018 class averages, and its EU trading pattern
(share of activity in the EU and how it splits over voyage categories) from the user, with a typical
pattern for the ship type as default.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import fuels as F
from . import reference as R
from .compliance import Profile
from .estimate import EuShare
from .models import AnnualEmissions, ScopeSplit, Ship, ShipCategory
from .uncertainty import Estimate

IMO_TO_CII = {"bulk": "bulk", "oil": "tanker", "chemical": "tanker", "container": "container",
              "general_cargo": "general_cargo", "reefer": "reefer", "vehicle": "vehicle", "roro": "roro",
              "ropax": "ropax", "cruise": "cruise", "other_liquids": "tanker"}
IMO_TO_MRV = {"bulk": "Bulk carrier", "oil": "Oil tanker", "chemical": "Chemical tanker", "container": "Container ship",
              "general_cargo": "General cargo ship", "gas": "Gas carrier", "reefer": "Refrigerated cargo carrier",
              "vehicle": "Vehicle carrier", "roro": "Ro-ro ship", "ropax": "Ro-pax ship", "cruise":
              "Passenger ship (Cruise Passenger ship)", "ferry_pax": "Passenger ship"}
PASSENGER = {"ropax", "cruise", "ferry_pax"}
LIBRARY_TYPES = ["bulk", "oil", "chemical", "container", "gas", "general_cargo", "reefer", "vehicle", "roro", "ropax",
                 "cruise", "ferry_pax"]
MIN_GT_SHIPS = 5000      # classes of very small ships are outside EU MRV/ETS scope and not offered

# Typical EU trading patterns (share of activity in the EU; split of EU emissions by voyage category)
PATTERNS = {
    "deep_sea": {"eu_share": 0.30, "intra_eu": 0.05, "in_port": 0.10, "from_eu": 0.425, "to_eu": 0.425},
    "short_sea": {"eu_share": 1.00, "intra_eu": 0.80, "in_port": 0.20, "from_eu": 0.0, "to_eu": 0.0},
    "mixed": {"eu_share": 0.60, "intra_eu": 0.40, "in_port": 0.15, "from_eu": 0.225, "to_eu": 0.225},
}
DEFAULT_PATTERN = {"ropax": "short_sea", "ferry_pax": "short_sea", "roro": "mixed", "general_cargo": "mixed",
                   "reefer": "mixed", "cruise": "mixed"}


@dataclass(frozen=True)
class Preset:
    key: str
    name: dict
    cls: str               # IMO class key
    capacity: float        # in the CII unit of the type (DWT or GT)


PRESETS = [
    Preset("handysize", {"el": "Handysize φορτηγό χύδην", "en": "Handysize bulk carrier"}, "bulk:10000-34999", 33_000),
    Preset("supramax", {"el": "Supramax / Ultramax", "en": "Supramax / Ultramax"}, "bulk:35000-59999", 58_000),
    Preset("kamsarmax", {"el": "Kamsarmax", "en": "Kamsarmax"}, "bulk:60000-99999", 82_000),
    Preset("capesize", {"el": "Capesize", "en": "Capesize"}, "bulk:100000-199999", 180_000),
    Preset("vloc", {"el": "VLOC (μεταλλεύματα)", "en": "VLOC (ore carrier)"}, "bulk:200000-+", 300_000),
    Preset("mr", {"el": "MR δεξαμενόπλοιο προϊόντων", "en": "MR product tanker"}, "oil:20000-59999", 50_000),
    Preset("lr1", {"el": "LR1 / Panamax δεξαμενόπλοιο", "en": "LR1 / Panamax tanker"}, "oil:60000-79999", 74_000),
    Preset("aframax", {"el": "Aframax / LR2", "en": "Aframax / LR2"}, "oil:80000-119999", 112_000),
    Preset("suezmax", {"el": "Suezmax", "en": "Suezmax"}, "oil:120000-199999", 158_000),
    Preset("vlcc", {"el": "VLCC", "en": "VLCC"}, "oil:200000-+", 300_000),
    Preset("chem", {"el": "Χημικό δεξαμενόπλοιο 40.000+", "en": "Chemical tanker 40,000+"}, "chemical:40000-+", 50_000),
    Preset("feeder", {"el": "Feeder εμπορευματοκιβωτίων", "en": "Feeder container ship"}, "container:1000-1999", 0),
    Preset("panamax_box", {"el": "Panamax εμπορευματοκιβωτίων", "en": "Panamax container ship"}, "container:3000-4999", 0),
    Preset("neopanamax", {"el": "Neo-Panamax εμπορευματοκιβωτίων", "en": "Neo-Panamax container ship"},
           "container:12000-14499", 0),
    Preset("ulcv", {"el": "ULCV εμπορευματοκιβωτίων", "en": "Ultra-large container ship"}, "container:20000-+", 0),
    Preset("lng", {"el": "Πλοίο LNG 174.000 m³", "en": "LNG carrier 174,000 m³"}, "gas:100000-199999", 0),
    Preset("vlgc", {"el": "VLGC (υγραέριο)", "en": "VLGC (LPG)"}, "gas:50000-99999", 0),
    Preset("pctc", {"el": "PCTC οχηματαγωγό", "en": "PCTC car carrier"}, "vehicle:50000-+", 0),
    Preset("ropax", {"el": "Επιβατηγό-οχηματαγωγό (ro-pax)", "en": "Ro-pax ferry"}, "ropax:20000-+", 0),
    Preset("cruise", {"el": "Κρουαζιερόπλοιο 100–150 χιλ. GT", "en": "Cruise ship 100–150k GT"}, "cruise:100000-149999", 0),
]


def library_classes() -> list[R.SizeClass]:
    out = []
    for t in LIBRARY_TYPES:
        for c in R.of_type(t):
            lo, _ = c.bounds
            if c.unit == "gt" and lo < MIN_GT_SHIPS and c.type != "cruise":
                continue
            if c.unit in ("dwt", "teu", "cbm") and c.value("dwt") < 3000:
                continue
            out.append(c)
    return out


def cii_type_of(c: R.SizeClass) -> str | None:
    if c.type == "gas":
        return "lng" if c.bounds[0] >= 100_000 else "gas"
    return IMO_TO_CII.get(c.type)


def default_capacity(c: R.SizeClass, cii_type: str | None) -> float:
    if cii_type in ("vehicle", "roro", "ropax", "cruise"):
        return round(c.gt_mid, -2) if c.unit == "gt" else 0.0
    return round(c.value("dwt"), -2)


def default_mix(c: R.SizeClass) -> F.FuelMix:
    """2018 fleet: LNG carriers mostly burn LNG; otherwise heavy fuel oil with some distillates
    (IMO study Table 34: 221.8 Mt HFO vs 61.5 Mt MDO in international shipping, 2018)."""
    if c.type == "gas" and c.bounds[0] >= 100_000:
        return {"lng_otto_ss": 0.8, "mgo": 0.2}
    return {"hfo": 0.78, "mgo": 0.22}


def profile(c: R.SizeClass, pattern: str | None = None, capacity: float | None = None,
            fuels: dict[str, F.Fuel] | None = None) -> Profile:
    """Engine profile of a standard ship of class `c` with an EU trading pattern."""
    fuels = fuels or F.load()
    pat = PATTERNS[pattern or DEFAULT_PATTERN.get(c.type, "deep_sea")]
    mix = default_mix(c)
    fuel_t = c.fuel_t()
    co2_ww = fuel_t * F.co2_per_t(mix, fuels)
    eu = co2_ww * pat["eu_share"]
    split = ScopeSplit(intra_eu=eu * pat["intra_eu"], in_port=eu * pat["in_port"], from_eu=eu * pat["from_eu"],
                       to_eu=eu * pat["to_eu"])
    # small methane/nitrous oxide quantities in the same split (FuelEU default factors per tonne of fuel)
    ch4 = sum(sh * (fuels[k].cf_ch4 + fuels[k].slip / 100) for k, sh in mix.items()) * fuel_t * pat["eu_share"]
    n2o = sum(sh * fuels[k].cf_n2o for k, sh in mix.items()) * fuel_t * pat["eu_share"]
    tot = split.total or 1
    em = AnnualEmissions(co2=split, ch4=split.scaled(ch4 / tot), n2o=split.scaled(n2o / tot))
    cii_type = cii_type_of(c)
    cap = capacity if capacity else default_capacity(c, cii_type)
    category = ShipCategory.PASSENGER if c.type in PASSENGER else ShipCategory.CARGO
    gt = 5000.0 if c.unit != "gt" else max(c.bounds[0], 5000.0)
    ship = Ship(imo="", name=c.label, ship_type=IMO_TO_MRV.get(c.type, c.label), category=category, gross_tonnage=gt)
    share = EuShare(pat["eu_share"], "user", pat["eu_share"], pat["eu_share"], c.value("days_at_sea"), None, c.key)
    return Profile(ship=ship, emissions=em, fuel_mix=mix, cii_type=cii_type, capacity=cap,
                   distance_nm=c.value("distance_nm") * pat["eu_share"], eu_share=share,
                   size=Estimate.exact(cap, "library", "imo4") if cap else None)


def preset(key: str) -> Preset:
    return next(p for p in PRESETS if p.key == key)
