"""Build navigator/config/technology/measures.json (decision 0009): 25 measures plus variants.

Each range is taken from the cited sources (min and max from the spread, likely from the median or
the most rigorous source, as noted per measure). Values still resting on one source or on an
assumption keep "status": "verify". Run:  python tools/build_measures.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USD_PER_EUR = 1 / 0.8666            # imo_nzf.json eur_per_usd
GV = "https://greenvoyage2050.imo.org/technology/"
S = {
 "imo4_q": {"title": "Fourth IMO GHG Study 2020, Annex Q: Tables 93–96 (technologies, applicability, maturity, expected lifetime, extrapolation basis, learning curves) and Section Q.2.7 (pilot fuel ~5% of heat for ammonia engines)", "url": "https://www.imo.org/en/ourwork/Environment/Pages/Fourth-IMO-Greenhouse-Gas-Study-2020.aspx", "checked": "2026-10-25"},
 "gv_coating": {"title": "IMO GreenVoyage2050 EET portal: Hull performance coating (1–5% of total fuel; $30,000–600,000; recoated every fifth year)", "url": GV + "hull-coating/", "checked": "2026-10-25"},
 "gv_cleaning": {"title": "IMO GreenVoyage2050 EET portal: Hull cleaning (1–5% of total fuel; $5,000–50,000 per cleaning)", "url": GV + "hull-cleaning/", "checked": "2026-10-25"},
 "gv_polishing": {"title": "IMO GreenVoyage2050 EET portal: Propeller polishing (3–4% of main engine fuel; 0.5–3% annual average; $4,000–8,000, twice a year)", "url": GV + "propeller-polishing/", "checked": "2026-10-25"},
 "gv_propeller": {"title": "IMO GreenVoyage2050 EET portal: Propeller retrofitting (2–6% of main engine fuel; $400,000–850,000; lifetime 15 years)", "url": GV + "propeller-retrofitting/", "checked": "2026-10-25"},
 "gv_als": {"title": "IMO GreenVoyage2050 EET portal: Air lubrication (net 2–8% annual energy; 7–10% LNG carriers, cruise, ro-ro, ferries; 2–5% others; CAPEX 1–3% of newbuild cost)", "url": GV + "air-cavity-lubrication/", "checked": "2026-10-25"},
 "gv_whr": {"title": "IMO GreenVoyage2050 EET portal: Waste heat recovery systems (2–6% of total fuel; up to 6% of main engine power as electricity; $5.2–11.5 million; maintenance $10,000–30,000 a year; engines ≥ 10 MW; usually newbuild)", "url": GV + "waste-heat-recovery-systems/", "checked": "2026-10-25"},
 "gv_tuning": {"title": "IMO GreenVoyage2050 EET portal: Engine performance optimization, manual (1–3% of total fuel; $4,000–12,000)", "url": GV + "engine-performance-optimization-manual/", "checked": "2026-10-25"},
 "gv_derating": {"title": "IMO GreenVoyage2050 EET portal: Engine de-rating (2–6% of main engine fuel; $55,000–2,500,000; 7–10 days in dock; top speed −10–15%)", "url": GV + "engine-de-rating/", "checked": "2026-10-25"},
 "gv_hybrid": {"title": "IMO GreenVoyage2050 EET portal: Hybridization (2–15% of annual consumption; $0.5–5 million per ship, average $1.5–2.5 million; battery $500–900/kWh)", "url": GV + "hybridization-plug-in-or-conventional/", "checked": "2026-10-25"},
 "gv_shore": {"title": "IMO GreenVoyage2050 EET portal: Shore power (50–100% in port; 0.5–15% of annual fuel; ship side $50,000–2,000,000)", "url": GV + "shore-power/", "checked": "2026-10-25"},
 "gv_steam": {"title": "IMO GreenVoyage2050 EET portal: Steam plant operation improvement (10–30% of boiler fuel; $5,000 a year; crude and product tankers)", "url": GV + "steam-plant-operation-improvement/", "checked": "2026-10-25"},
 "emsa_als": {"title": "EMSA / DNV (2026), Hull Air Lubrication System Study: net power gains at actual speed by ship type (Table 2-14, 9,329 ships), compressor power 3–5% of propulsion power, active ALS TRL 8–9, CAPEX formula (Section 2.7.3.2), OPEX 0.9% of system cost, 8% discount rate", "url": "https://www.emsa.europa.eu/publications/item/5633-hull-air-lubrication-system-study.html", "checked": "2026-10-25"},
 "emsa_wind": {"title": "EMSA / CE Delft (2023), Potential of Wind-Assisted Propulsion for Shipping: units per ship type and size (Table 6), 2021 unit costs (Table 7), measured and simulated savings per installation (Section 2.1), TRL (rotor sails, suction wings, hard sails 9; kites 7–8)", "url": "https://emsa.europa.eu/publications/reports/item/5078-potential-of-wind-assisted-propulsion-for-shipping.html", "checked": "2026-10-25"},
 "bouman_2017": {"title": "Bouman, E.A., Lindstad, E., Rialland, A.I., Strømman, A.H. (2017), State-of-the-art technologies, measures, and potential for reducing GHG emissions from shipping – A review, Transportation Research Part D 52, 408–421, Table 2 (CO2 reduction ranges from ~150 studies)", "url": "https://doi.org/10.1016/j.trd.2017.03.022", "checked": "2026-10-25"},
 "dnv_mf2026": {"title": "DNV (2026), Maritime Forecast to 2050: retrofit business case (5,000 TEU: bow + propeller + PBCF, 16% saving, USD 2.35 million, within a standard dry-docking); EU ETS as the only explicit incentive for onboard carbon capture", "url": "https://www.dnv.com/maritime/publications/maritime-forecast/", "checked": "2026-10-25"},
 "mmmczcs_2022": {"title": "Mærsk Mc-Kinney Møller Center (2022), Preparing Container Vessels for Conversion to Green Fuels: conversion 9–16% (methanol) and 14–24% (ammonia) of a $150 million 15,000 TEU newbuild; lost capacity 240–610 TEU (methanol), 540–1,100 TEU (ammonia)", "url": "https://www.zerocarbonshipping.com/api/file/GB0oH-VjSpSCUskTdnltDg", "checked": "2026-10-25"},
 "emsa_occ": {"title": "EMSA (2026), Onboard Carbon Capture Technologies (corrigendum 5 March 2026): capture 15–60% over the operational profile, fuel penalty 9–30%, CAPEX €180–720 per t CO2 treated a year, disposal €54–117 per t, maintenance 3% of CAPEX, 8% discount rate (Tables 3-14, 3-15)", "url": "https://www.emsa.europa.eu/publications/reports/item/5634-onboard-carbon-capture-technologies.html", "checked": "2026-10-25"},
 "gia_jit_2022": {"title": "IMO Low Carbon GIA / MarineTraffic & EERA (2022), Just In Time Arrival emissions study for container ships (2019 AIS): mean fuel saving 14.16% per voyage with whole-voyage optimisation, 5.90% (last 24 h), 4.23% (last 12 h)", "url": "https://imo-newsroom.prgloo.com/news/study-lowering-containership-emissions-through-just-in-time-arrivals", "checked": "2026-10-25"},
 "gv_guide_2022": {"title": "IMO GreenVoyage2050 (2022), A Practical Guide to the Selection of Energy Efficiency Technologies for Ships: pre-duct average saving 5.5% ± 2.5–3% (GRIP data)", "url": "https://greenvoyage2050.imo.org/practical-guide-to-the-selection-of-energy-efficiency-technologies-for-ships/", "checked": "2026-10-25"},
 "bwlpg_2020": {"title": "S&P Global Commodity Insights (23 Oct 2020): BW LPG dual-fuel retrofit of VLGC BW Gemini about $9 million per ship, 60 days in yard", "url": "https://www.spglobal.com/commodity-insights/en/news-research/latest-news/coal/102320-feature-dorian-lpg-sees-dual-fuel-vlgc-upgrade-costing-3-times-scrubber-retrofitting", "checked": "2026-10-25"},
 "assume": {"title": "Modelling assumption of this application, documented in docs/decisions/0009", "checked": "2026-10-25"},
}


def E(lo, mid, hi):
    return {"low": lo, "likely": mid, "high": hi}


def N(el, en):
    return {"el": el, "en": en}


M = {}


def m(key, group, name, how, effect, capex, opex, refs, lifetime=None, offhire=None, applies=None,
      excludes=(), attributes=None, units=None, note=""):
    """One library entry. Verified when backed by at least two sources other than an assumption."""
    v = {"group": group, "name": name, "how": how, "effect": effect, "capex": capex, "opex": opex,
         "lifetime": lifetime or E(25, 25, 25), "offhire_days": offhire or E(0, 0, 0),
         "applies": applies or {"types": ["*"]}, "excludes": list(excludes), "attributes": attributes or {},
         "refs": list(refs)}
    if units:
        v["units"] = units
    solid = len([r for r in refs if r != "assume" and not S[r]["title"].endswith("(to be read)")]) >= 2
    M[key] = {"value": v, "source": refs[0], "status": "verified" if solid and "assume" not in refs else "verify",
              "note": note}
FIX0 = {"basis": "fixed", "low": 0, "likely": 0, "high": 0}
A = lambda trl, avail=5, safety=5, cargo=0.0: {"trl": trl, "availability": avail, "safety": safety, "cargo_loss": cargo}
FLAT = ["bulk", "oil", "chemical", "gas", "container", "cruise", "ropax", "roro", "vehicle", "general_cargo", "reefer"]
# EMSA (2023) Table 6: number of rotor sails / suction wings / hard sails, and of kites, by type and size class
WIND_UNITS = {
    "bulk": {"0": 0, "10000": 1, "60000": 2, "100000": 4}, "chemical": {"0": 0, "5000": 1, "40000": 2},
    "container": {"0": 0}, "general_cargo": {"0": 0, "5000": 1, "20000": 2}, "gas": {"0": 0, "50000": 1, "100000": 2, "200000": 4},
    "oil": {"0": 0, "5000": 1, "20000": 2, "120000": 4}, "other_liquids": {"0": 0}, "ferry_pax": {"0": 0, "2000": 1},
    "cruise": {"0": 0, "10000": 1, "100000": 2}, "ropax": {"0": 0, "5000": 1}, "reefer": {"0": 0, "6000": 1},
    "roro": {"0": 0, "5000": 1, "15000": 2}, "vehicle": {"0": 0, "30000": 1},
}
KITE_UNITS = {
    "bulk": {"0": 0, "10000": 1}, "chemical": {"0": 0, "5000": 1}, "container": {"0": 0, "1000": 1},
    "general_cargo": {"0": 0, "5000": 1}, "gas": {"0": 0, "50000": 1}, "oil": {"0": 0, "5000": 1},
    "reefer": {"0": 0, "6000": 1}, "roro": {"0": 0, "5000": 1}, "vehicle": {"0": 0, "30000": 1},
}


def T(*tiers):
    """Small / medium / large size tiers (engine.measures.TIER_BOUNDS)."""
    return {"tiers": [E(*t) for t in tiers]}


def eur_k(x):                     # thousand EUR (2021) → USD
    return round(x * 1000 * USD_PER_EUR, -3)


def wind_capex(asset_min, asset_max, inst_min, inst_max):
    """EMSA Table 7, retrofit: asset + retrofit installation + EUR 10k training; small = min, large = max."""
    lo, hi = eur_k(asset_min + inst_min + 10), eur_k(asset_max + inst_max + 10)
    mid = (lo + hi) / 2
    return {"basis": "per_unit", "tiers": [E(lo, lo, mid), E(lo, mid, hi), E(mid, hi, hi)]}


def wind_opex(lo, hi):
    return {"basis": "fixed", "low": eur_k(lo), "likely": eur_k((lo + hi) / 2), "high": eur_k(hi)}

# A · operation
m("slow_steaming", "operation", N("Μείωση ταχύτητας 10%", "Slow steaming −10%"),
  N("Η ισχύς πρόωσης αυξάνεται με τον κύβο της ταχύτητας: 10% χαμηλότερη ταχύτητα σημαίνει περίπου 27% λιγότερη ισχύ ανά ώρα, αλλά περισσότερες ημέρες ταξιδιού.",
    "Propulsion power rises with the cube of speed: 10% slower means about 27% less power per hour, but more days per voyage."),
  {"type": "speed", "value": E(0.10, 0.10, 0.10)}, FIX0, FIX0, ["imo4_q", "bouman_2017"], attributes=A(9),
  excludes=["slow_steaming_20"], note="Cost is the extra time at sea (economics.time_cost_share).")
m("slow_steaming_20", "operation", N("Μείωση ταχύτητας 20%", "Slow steaming −20%"),
  N("Όπως παραπάνω, με 20% χαμηλότερη ταχύτητα (Μελέτη IMO, Πίνακας 99).", "As above, 20% slower (IMO study, Table 99)."),
  {"type": "speed", "value": E(0.20, 0.20, 0.20)}, FIX0, FIX0, ["imo4_q", "bouman_2017"], attributes=A(9),
  excludes=["slow_steaming"], note="Variant of slow steaming.")
m("jit_arrival", "operation", N("Άφιξη ακριβώς στην ώρα (JIT)", "Just-in-time arrival"),
  N("Αντί να φτάνει νωρίς και να περιμένει στην άγκυρα, το πλοίο ρυθμίζει την ταχύτητα ώστε να φτάσει όταν ελευθερωθεί η θέση. Χρειάζεται συνεργασία με το λιμάνι.",
    "Instead of arriving early and waiting at anchor, the ship sails slower to arrive when the berth is free. Needs the port to cooperate."),
  {"type": "jit", "value": E(0.03, 0.04, 0.10)}, FIX0, {"basis": "fixed", "low": 0, "likely": 5000, "high": 20000},
  ["gia_jit_2022", "bouman_2017"], attributes=A(8, 3),
  note="Value = waiting time turned into sailing time, as a share of hours at sea: 0.03–0.04 reproduces the 4.2–5.9% saving of optimising the last 12–24 h, 0.10 the 14% of whole-voyage optimisation (GIA 2022). Availability 3: depends on port cooperation.")
m("weather_routing", "operation", N("Δρομολόγηση βάσει καιρού", "Weather routing"),
  N("Λογισμικό που επιλέγει διαδρομή με λιγότερο αντίθετο άνεμο και κύμα.", "Software that picks a route with less head wind and waves."),
  {"type": "resistance", "value": E(0.01, 0.025, 0.04)}, FIX0, {"basis": "fixed", "low": 3000, "likely": 10000, "high": 25000},
  ["bouman_2017", "assume"], attributes=A(9),
  note="Bouman (2017): voyage optimisation 0.1–48% (very wide); the IMO study left it out of its cost curves because the effect varies by operation. 1–4% kept as a conservative range.")
m("trim_optimisation", "operation", N("Βελτιστοποίηση διαγωγής", "Trim optimisation"),
  N("Φόρτωση και έρμα ώστε η γάστρα να πλέει στη γωνία με τη μικρότερη αντίσταση.", "Loading and ballast set so the hull floats at the angle with least drag."),
  {"type": "resistance", "value": E(0.01, 0.02, 0.05)}, {"basis": "fixed", "low": 0, "likely": 30000, "high": 100000}, FIX0, ["bouman_2017", "assume"],
  lifetime=E(10, 10, 10), attributes=A(9))
# B · hull and propeller
m("hull_coating", "hull", N("Επίστρωση γάστρας χαμηλής τριβής", "Low-friction hull coating"),
  N("Επίστρωση σιλικόνης ή άλλη προηγμένη επίστρωση που μειώνει την τριβή και τις επικαθίσεις. Εφαρμόζεται στη δεξαμενή, κάθε περίπου 5 χρόνια.",
    "Silicone or other advanced coating that lowers friction and fouling. Applied in drydock, about every 5 years."),
  {"type": "resistance", "value": E(0.012, 0.035, 0.06)}, {"basis": "per_dwt", "low": 1.5, "likely": 2.5, "high": 4.0}, FIX0,
  ["gv_coating", "imo4_q"], lifetime=E(5, 5, 5), attributes=A(9),
  note="GreenVoyage gives 1–5% of total fuel; divided by a main-engine share of ~0.85. CAPEX per DWT from the $30,000–600,000 range across sizes.")
m("hull_cleaning_polishing", "hull", N("Καθαρισμός γάστρας και στίλβωση έλικας", "Hull cleaning and propeller polishing"),
  N("Τακτικός υποβρύχιος καθαρισμός της γάστρας και στίλβωση της έλικας από δύτες ή ρομπότ, συνήθως όταν το πλοίο είναι στο λιμάνι.",
    "Regular in-water hull cleaning and propeller polishing by divers or robots, usually while the ship is in port."),
  {"type": "resistance", "value": E(0.015, 0.03, 0.06)}, FIX0, {"basis": "fixed", "low": 13000, "likely": 35000, "high": 66000},
  ["gv_cleaning", "gv_polishing", "imo4_q"], lifetime=E(1, 1, 1), attributes=A(9),
  note="OPEX = one hull cleaning ($5,000–50,000) + two propeller polishings ($4,000–8,000 each) a year.")
m("air_lubrication", "hull", N("Λίπανση με αέρα", "Air lubrication"),
  N("Συμπιεστές δημιουργούν στρώμα φυσαλίδων κάτω από τον επίπεδο πυθμένα και μειώνουν την τριβή. Καλύτερα σε φαρδιά πλοία με μικρό βύθισμα (LNG, ro-ro, κρουαζιερόπλοια).",
    "Compressors make a carpet of air bubbles under the flat bottom and cut friction. Best on wide ships with shallow draught (LNG carriers, ro-ro, cruise ships)."),
  {"type": "als", "compressor_share": 0.0, "value": {"by_type": {
      "bulk": E(0.008, 0.016, 0.05), "container": E(0.005, 0.011, 0.05), "chemical": E(0.009, 0.019, 0.05),
      "oil": E(0.004, 0.008, 0.05), "general_cargo": E(0.010, 0.020, 0.05), "gas": E(0.011, 0.023, 0.10),
      "vehicle": E(0.012, 0.025, 0.10), "roro": E(0.010, 0.020, 0.10), "ropax": E(0.010, 0.020, 0.10),
      "cruise": E(0.006, 0.012, 0.10), "reefer": E(0.012, 0.024, 0.05), "*": E(0.008, 0.015, 0.05)}}},
  {"basis": "fixed", "tiers": [E(eur_k(700), eur_k(900), eur_k(1300)), E(eur_k(900), eur_k(1100), eur_k(1600)),
                               E(eur_k(2200), eur_k(2800), eur_k(4000))]},
  {"basis": "capex_share", "low": 0.005, "likely": 0.007, "high": 0.009},
  ["emsa_als", "gv_als", "bouman_2017", "imo4_q"], applies={"types": FLAT, "min_mcr_kw": 3000}, attributes=A(8),
  note="Net saving as a share of propulsion power (compressor power deducted). Likely = EMSA (2026) average for the type at actual speed; "
       "low = half of it (the study's 95% confidence cases); high = GreenVoyage upper figure (5%, or 10% for LNG, ro-ro, cruise and ferries; Bouman 1–15%). "
       "CAPEX from the EMSA retrofit formula k1·k2·k3·width·√(T+12)·√V·1,000 € for typical dimensions: Handysize ≈ €1.0 m, Kamsarmax ≈ €1.1 m, "
       "Capesize ≈ €3.0 m, large container ≈ €2.8 m, LNG 174k m³ ≈ €2.5 m; Europe yard costs up to 1.7× China (high).")
m("propulsion_devices", "hull", N("Συσκευές βελτίωσης πρόωσης", "Propulsion-improving devices"),
  N("Ακροφύσια (ducts), πτερύγια πριν ή μετά την έλικα και πτερύγια στο κέντρο της (PBCF) που ανακτούν την ενέργεια της περιστροφής του νερού.",
    "Ducts, fins before or after the propeller and propeller-hub fins (PBCF) that recover the energy of the water's swirl."),
  {"type": "resistance", "value": E(0.025, 0.055, 0.085)}, {"basis": "fixed", "low": 100000, "likely": 350000, "high": 1000000}, FIX0,
  ["gv_guide_2022", "bouman_2017", "imo4_q"], attributes=A(9), excludes=[],
  note="Pre-duct 5.5% ± 3% (GreenVoyage guide, GRIP data); Bouman (2017) propulsion efficiency devices 1–25%. CAPEX range assumed (DNV 2026: bow + propeller + PBCF together USD 2.35 million).")
m("propeller_retrofit", "hull", N("Νέα έλικα για την πραγματική ταχύτητα", "Propeller retrofit for actual speed"),
  N("Τα περισσότερα πλοία πλέουν πιο αργά από την ταχύτητα σχεδίασης· μια έλικα (και πλώρη) σχεδιασμένη για την πραγματική ταχύτητα δουλεύει πιο αποδοτικά.",
    "Most ships now sail slower than they were designed for; a propeller (and bow) designed for the actual speed works more efficiently."),
  {"type": "resistance", "value": E(0.02, 0.04, 0.06)}, {"basis": "fixed", "low": 400000, "likely": 600000, "high": 850000}, FIX0,
  ["gv_propeller", "imo4_q"], lifetime=E(15, 15, 15), attributes=A(9))
# C · machinery and energy
m("waste_heat_recovery", "machinery", N("Ανάκτηση θερμότητας καυσαερίων", "Waste heat recovery"),
  N("Ατμοστρόβιλος, στρόβιλος ισχύος ή μονάδα ORC παράγει ηλεκτρισμό από τη θερμότητα των καυσαερίων της κύριας μηχανής, μέχρι ~6% της ισχύος της.",
    "A steam turbine, power turbine or ORC unit makes electricity from the main engine's exhaust heat, up to ~6% of its power."),
  {"type": "whr", "value": E(0.02, 0.04, 0.06)}, {"basis": "per_kw", "low": 190, "likely": 350, "high": 520},
  {"basis": "fixed", "low": 10000, "likely": 20000, "high": 30000}, ["gv_whr", "imo4_q"],
  applies={"types": ["*"], "min_mcr_kw": 10000, "retrofit": False}, attributes=A(9),
  note="Per-kW CAPEX from $5.2 million (≈10 MW) to $11.5 million (≈60 MW).")
m("engine_tuning", "machinery", N("Ρύθμιση και συντήρηση μηχανής", "Engine tuning"),
  N("Ρύθμιση έγχυσης, χρονισμού και στροβιλοσυμπιεστή για καλύτερη απόδοση στο φορτίο που πραγματικά λειτουργεί η μηχανή.",
    "Adjusting injection, timing and turbocharger for better efficiency at the load the engine really runs at."),
  {"type": "me_energy", "value": E(0.01, 0.02, 0.03)}, {"basis": "fixed", "low": 4000, "likely": 8000, "high": 12000}, FIX0,
  ["gv_tuning", "imo4_q"], lifetime=E(5, 5, 5), attributes=A(9))
m("engine_derating", "machinery", N("Αποδυνάμωση (de-rating) μηχανής", "Engine de-rating"),
  N("Μόνιμη μείωση της μέγιστης ισχύος ώστε η μηχανή να λειτουργεί πιο αποδοτικά στη χαμηλή ταχύτητα. Η μέγιστη ταχύτητα πέφτει 10–15%.",
    "Permanently lowering maximum power so the engine runs more efficiently at low speed. Top speed falls 10–15%."),
  {"type": "me_energy", "value": E(0.02, 0.04, 0.06)}, {"basis": "fixed", "low": 55000, "likely": 1500000, "high": 2500000}, FIX0,
  ["gv_derating", "bouman_2017"], offhire=E(7, 8.5, 10), attributes=A(9), excludes=["engine_tuning"])
m("battery_hybrid", "machinery", N("Μπαταρίες / υβριδικό σύστημα", "Batteries / hybrid"),
  N("Οι μπαταρίες καλύπτουν αιχμές φορτίου ώστε οι μηχανές να δουλεύουν στο καλύτερο σημείο, και τροφοδοτούν το πλοίο στο λιμάνι. Ισχυρό για πορθμεία.",
    "Batteries cover load peaks so engines run at their best point, and power the ship in port. Strong for ferries."),
  {"type": "battery", "value": E(0.02, 0.05, 0.12), "port_share": 0.3, "battery_kwh_per_kw_aux": 1.0},
  {"basis": "fixed", "low": 500000, "likely": 2000000, "high": 5000000}, {"basis": "capex_share", "low": 0.0, "likely": 0.01, "high": 0.02},
  ["gv_hybrid", "bouman_2017"], lifetime=E(8, 10, 12), attributes=A(9, 5, 4),
  note="Battery lifetime to be checked.")
m("shore_power", "machinery", N("Ηλεκτροδότηση από την ξηρά", "Shore power"),
  N("Στο λιμάνι οι βοηθητικές μηχανές σβήνουν και το πλοίο παίρνει ρεύμα από την ξηρά. Υποχρεωτικό από το 2030 για πλοία εμπορευματοκιβωτίων και επιβατηγά σε μεγάλα λιμάνια της ΕΕ.",
    "At berth the auxiliary engines are switched off and the ship takes power from shore. Required from 2030 for container and passenger ships in major EU ports."),
  {"type": "shore", "value": E(0.5, 0.8, 1.0)}, {"basis": "fixed", "low": 50000, "likely": 600000, "high": 2000000}, FIX0,
  ["gv_shore", "bouman_2017"], attributes=A(9, 3, 5), note="Value = share of berth electricity taken from shore (depends on port availability).")
m("aux_efficiency", "machinery", N("Αποδοτικές αντλίες, ανεμιστήρες και φωτισμός", "Efficient pumps, fans and lighting"),
  N("Ρυθμιστές στροφών (VFD) σε αντλίες και ανεμιστήρες και φωτισμός LED μειώνουν την ηλεκτρική ζήτηση επί του πλοίου.",
    "Variable-speed drives on pumps and fans and LED lighting cut the electrical demand on board."),
  {"type": "aux", "value": E(0.02, 0.08, 0.20)}, {"basis": "fixed", "low": 50000, "likely": 150000, "high": 400000}, FIX0,
  ["bouman_2017", "imo4_q"], attributes=A(9),
  note="Bouman (2017): on-board power demand 0.1–3% of total CO2, i.e. about 2–20% of the electrical demand. CAPEX assumed.")
m("steam_plant", "machinery", N("Βελτίωση λειτουργίας λεβήτων", "Steam plant improvements"),
  N("Καλύτερη χρήση των λεβήτων (θέρμανση φορτίου, αντλίες εκφόρτωσης) σε δεξαμενόπλοια.", "Better use of the boilers (cargo heating, cargo pumps) on tankers."),
  {"type": "boiler", "value": E(0.10, 0.20, 0.30)}, FIX0, {"basis": "fixed", "low": 3000, "likely": 5000, "high": 8000},
  ["gv_steam", "imo4_q"], applies={"types": ["oil", "chemical", "other_liquids"]}, attributes=A(9))
# D · wind
m("rotor_sails", "wind", N("Περιστρεφόμενα πανιά (rotor sails)", "Rotor sails"),
  N("Περιστρεφόμενοι κύλινδροι στο κατάστρωμα· ο άνεμος παράγει ώση (φαινόμενο Magnus). Ο αριθμός και το μέγεθός τους ακολουθούν το μέγεθος του πλοίου.",
    "Spinning cylinders on deck; the wind produces forward thrust (Magnus effect). Their number and size follow the ship's size."),
  {"type": "wind", "value": T((30, 170, 220), (187, 245, 282), (267, 637, 1222)), "area_factor": 1.0},
  wind_capex(560, 1050, 140, 263), wind_opex(12, 22), ["emsa_wind", "bouman_2017", "imo4_q"],
  units=WIND_UNITS, offhire=E(2, 5, 10), attributes=A(9, 5, 5, 0.002),
  excludes=["suction_wings", "rigid_wings", "kites"],
  note="Value = average thrust power per rotor (kW, annual mean incl. unfavourable wind). Small: Annika Braren 18×3 m (2–4.5%), Afros 16×2 m (12.5% est.), Estraden 18×3 m (6.1%); medium: Sea Zhoushan 24×4 m (8%), Viking Grace 24×4 m (207–282 kW measured); large: Epanastasea 30×5 m (8.2%), Copenhagen 30×5 m (4%), SC Connector 35×5 m (20–25%, supplier). Percentages converted with the IMO class's main engine power at sea. Bouman (2017): wind 1–50%.")
m("suction_wings", "wind", N("Πτερύγια αναρρόφησης (suction wings)", "Suction wings"),
  N("Σταθερά πτερύγια με ανεμιστήρα που αναρροφά τον αέρα από την επιφάνεια και αυξάνει την ώση. Καλύτερα σε πλάγιους ανέμους και χαμηλή ταχύτητα.",
    "Fixed wings with a fan that sucks air off the surface and boosts thrust. Best in side winds and at low speed."),
  {"type": "wind", "value": T((19, 28, 37), (37, 120, 200), (100, 200, 300)), "area_factor": 1.0},
  wind_capex(200, 900, 50, 225), wind_opex(4, 18), ["emsa_wind", "bouman_2017"],
  units=WIND_UNITS, offhire=E(1, 3, 7), attributes=A(9, 5, 5, 0.001),
  excludes=["rotor_sails", "rigid_wings", "kites"],
  note="Small: Frisian Sea 2 × 10 m (2–4% measured); medium and large: supplier figure of over 200 kW for one 10–16 m wing.")
m("rigid_wings", "wind", N("Άκαμπτα πανιά-πτέρυγες", "Rigid wing sails"),
  N("Μεγάλα πτερύγια σαν φτερά αεροπλάνου, συχνά πτυσσόμενα. Μεγάλη ώση σε κατάλληλες διαδρομές.", "Large aeroplane-like wings, often foldable. Large thrust on suitable routes."),
  {"type": "wind", "value": T((34, 337, 558), (34, 429, 721), (337, 558, 1058)), "area_factor": 1.0},
  wind_capex(438, 876, 109, 219), wind_opex(8, 18), ["emsa_wind", "bouman_2017"],
  units=WIND_UNITS, offhire=E(3, 7, 14), attributes=A(9, 5, 5, 0.003),
  excludes=["rotor_sails", "suction_wings", "kites"],
  note="Tanker with five wing sails 2.6% (estimate); Shofu Maru, one sail, 5–8% (simulation); Ciudad de Mahón 2 × 35×12 m, 7–22% (15% realistic, simulation).")
m("kites", "wind", N("Χαρταετός ρυμούλκησης", "Towing kite"),
  N("Μεγάλος χαρταετός στην πλώρη που πετά ψηλά, όπου ο άνεμος είναι πιο δυνατός. Λιγότερο ώριμη τεχνολογία· δεν πιάνει χώρο στο κατάστρωμα.",
    "Large kite at the bow flying high, where the wind is stronger. Less mature; takes no deck space."),
  {"type": "wind", "value": T((54, 150, 400), (54, 271, 814), (271, 558, 866)), "area_factor": 1.0},
  wind_capex(340, 2345, 85, 586), wind_opex(17, 117), ["emsa_wind", "bouman_2017", "imo4_q"],
  units=KITE_UNITS, offhire=E(1, 3, 7), attributes=A(7, 5, 4),
  excludes=["rotor_sails", "suction_wings", "rigid_wings"],
  note="400 m² kite: 1–15% (CE Delft 2016, in EMSA); 375 m² on Ciudad de Mahón: 4–13% (9% realistic). One kite per ship.")
# E · fuels and engine conversions
m("biofuel_blend", "fuel", N("Μείγμα βιοκαυσίμου B30", "Biofuel blend B30"),
  N("30% βιοντίζελ (FAME) αναμεμειγμένο στο συμβατικό καύσιμο. Χωρίς επένδυση· το κόστος είναι η επιπλέον τιμή του καυσίμου.",
    "30% biodiesel (FAME) blended into the usual fuel. No investment; the cost is the fuel's price premium."),
  {"type": "fuel", "value": E(0.3, 0.3, 0.3), "mix": {"fame": 1.0}}, FIX0, FIX0, ["dnv_mf2026", "bouman_2017"],
  attributes=A(9, 3, 5), excludes=["biofuel_b100", "lng_dual_fuel", "methanol_dual_fuel", "ammonia_dual_fuel"],
  note="Value = energy share of biofuel.")
m("biofuel_b100", "fuel", N("Βιοκαύσιμο B100 (HVO)", "Biofuel B100 (HVO)"),
  N("Ανανεώσιμο ντίζελ (HVO) αντί για συμβατικό καύσιμο, χωρίς αλλαγές στη μηχανή.", "Renewable diesel (HVO) instead of fossil fuel, with no engine changes."),
  {"type": "fuel", "value": E(1.0, 1.0, 1.0), "mix": {"hvo": 1.0}}, FIX0, FIX0, ["dnv_mf2026", "bouman_2017"],
  attributes=A(9, 2, 5), excludes=["biofuel_blend", "lng_dual_fuel", "methanol_dual_fuel", "ammonia_dual_fuel"],
  note="Variant of the biofuel measure.")
m("lng_dual_fuel", "fuel", N("Μετατροπή σε διπλού καυσίμου LNG", "LNG dual-fuel conversion"),
  N("Μηχανή διπλού καυσίμου και δεξαμενές LNG. Μικρό όφελος με ορυκτό LNG λόγω διαφυγής μεθανίου· ανοίγει τον δρόμο για βιο-LNG και e-LNG.",
    "Dual-fuel engine and LNG tanks. Small gain on fossil LNG because of methane slip; opens the way to bio-LNG and e-LNG."),
  {"type": "fuel", "value": E(0.9, 0.95, 0.98), "mix": {"lng_otto_ss": 1.0}, "engine": "ssd"},
  {"basis": "per_kw", "low": 400, "likely": 700, "high": 1000}, {"basis": "capex_share", "low": 0.005, "likely": 0.01, "high": 0.015},
  ["mmmczcs_2022", "bwlpg_2020", "bouman_2017", "imo4_q"], offhire=E(30, 60, 80), attributes=A(9, 4, 4, 0.02),
  excludes=["methanol_dual_fuel", "ammonia_dual_fuel", "biofuel_blend", "biofuel_b100"],
  note="Value = energy share on gas. CAPEX: LNG newbuild premium $24 million on a $150 million, ~60 MW ship (≈ $400/kW, MMMCZCS 2022) as the low end; BW Gemini LPG retrofit $9 million on a ~13 MW VLGC (≈ $700/kW, 60 days) as likely; high assumed. Bouman (2017): LNG 5–30%.")
m("methanol_dual_fuel", "fuel", N("Μετατροπή σε διπλού καυσίμου μεθανόλης", "Methanol dual-fuel conversion"),
  N("Μετατροπή της μηχανής και νέες δεξαμενές για μεθανόλη. Όφελος μόνο με βιο- ή e-μεθανόλη.", "Engine conversion and new tanks for methanol. A gain only on bio- or e-methanol."),
  {"type": "fuel", "value": E(0.9, 0.95, 0.98), "mix": {"bio_methanol": 1.0}, "engine": "ssd"},
  {"basis": "per_kw", "low": 225, "likely": 300, "high": 400}, {"basis": "capex_share", "low": 0.005, "likely": 0.01, "high": 0.015},
  ["mmmczcs_2022", "imo4_q"], offhire=E(30, 50, 80), attributes=A(9, 3, 4, 0.03),
  excludes=["lng_dual_fuel", "ammonia_dual_fuel", "biofuel_blend", "biofuel_b100"],
  note="CAPEX: 9–16% of a $150 million 15,000 TEU newbuild (~60 MW) ≈ $225–400/kW.")
m("ammonia_dual_fuel", "fuel", N("Μετατροπή σε διπλού καυσίμου αμμωνίας", "Ammonia dual-fuel conversion"),
  N("Μηχανή αμμωνίας με ~5% πιλοτικό καύσιμο. Σχεδόν μηδενικός άνθρακας με πράσινη αμμωνία· νέα τεχνολογία και τοξικό καύσιμο.",
    "Ammonia engine with ~5% pilot fuel. Near-zero carbon with green ammonia; new technology and a toxic fuel."),
  {"type": "fuel", "value": E(0.93, 0.95, 0.97), "mix": {"e_ammonia": 1.0}, "engine": "ssd"},
  {"basis": "per_kw", "low": 350, "likely": 475, "high": 600}, {"basis": "capex_share", "low": 0.01, "likely": 0.015, "high": 0.02},
  ["mmmczcs_2022", "imo4_q"], offhire=E(40, 60, 90), attributes=A(7, 1, 2, 0.06),
  excludes=["lng_dual_fuel", "methanol_dual_fuel", "biofuel_blend", "biofuel_b100"],
  note="CAPEX: 14–24% of a $150 million newbuild. Energy share 95% (pilot ~5% of heat, IMO study Q.2.7). N2O from ammonia engines not yet modelled.")
m("carbon_capture", "fuel", N("Δέσμευση άνθρακα επί του πλοίου", "Onboard carbon capture"),
  N("Μονάδα χημικής απορρόφησης που δεσμεύει μέρος του CO2 των καυσαερίων και το αποθηκεύει υγροποιημένο για εκφόρτωση στο λιμάνι. Χρειάζεται επιπλέον καύσιμο και χώρο· σήμερα την αναγνωρίζει ουσιαστικά μόνο το EU ETS.",
    "A chemical-absorption unit that captures part of the exhaust CO2 and stores it liquefied for offloading in port. Needs extra fuel and space; today essentially only the EU ETS recognises it."),
  {"type": "capture", "value": E(0.15, 0.35, 0.60), "energy_per_capture": 0.5, "maintenance_share": 0.03},
  {"basis": "per_t_captured", "low": eur_k(0.18), "likely": eur_k(0.45), "high": eur_k(0.72)},
  {"basis": "per_t_captured", "low": eur_k(0.054), "likely": eur_k(0.0855), "high": eur_k(0.117)},
  ["emsa_occ", "dnv_mf2026"], offhire=E(20, 35, 60), attributes=A(7, 2, 3, 0.02),
  note="Capture over the operational profile 15–60% (chemical absorption, six EMSA case ships); fuel penalty 9–30%, modelled as 0.5 × capture rate. "
       "CAPEX €180 / 450 / 720 per tonne of CO2 treated a year; CO2 disposal €54 / 85.5 / 117 per tonne offloaded; maintenance 3% of CAPEX a year. "
       "Container ships lose up to 1–3% of capacity. TRL 7 (chemical absorption: pilots and first installations).")
doc = {"name": "measures", "title": N("Βιβλιοθήκη μέτρων απανθρακοποίησης", "Decarbonisation measure library"), "sources": S, "values": M}
open(ROOT / "navigator/config/technology/measures.json", "w").write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
print(len(M), "entries;", len([k for k in M if M[k]['note'].startswith('Variant')]), "variants")
