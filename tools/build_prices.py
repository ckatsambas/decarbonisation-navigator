"""Build navigator/config/market/prices.json from the Phase 3 sources (decision 0009-5).

Every number below is copied from a cited source
the rules that combine them are:
- years 2026 (market, early October 2026), 2030, 2040, 2050
linear in between, flat after 2050;
- for 2030–2050, low = lowest source value, high = highest, central = median of the sources'
  central values (or of the mid-points of their ranges);
- prices are kept in USD per GJ while combining and written as USD per tonne of each fuel
  (lower calorific values from fuels.json).
Run:  python tools/build_prices.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUELS = json.loads((ROOT / "navigator/config/regulation/fuels.json").read_text())["values"]
USD_PER_EUR = 1 / 0.8666            # imo_nzf.json eur_per_usd (Banca d'Italia, 2026)
TOE_GJ = 41.868
YEARS = (2030, 2040, 2050)


def toe(usd_per_toe: float) -> float:
    return usd_per_toe / TOE_GJ


def eur(eur_per_gj: float) -> float:
    return eur_per_gj * USD_PER_EUR


def per_t(usd_t: float, gj_t: float) -> float:
    return usd_t / gj_t


# ---------------------------------------------------------------- source data (USD/GJ unless noted)
# Market, Rotterdam, early October 2026 (USD/t → USD/GJ)
MARKET_2026 = {
    "hfo": per_t(613, 40.5), "lfo": per_t(682.5, 41.0), "mgo": per_t(1340, 42.7),
    # LNG at a $240–364/t VLSFO-equivalent premium over VLSFO ($682.5/t, 41 GJ/t)
    "lng": per_t(682.5 + (240 + 364) / 2, 41.0),
    # LBM (bio-LNG) at a $162–290/t VLSFO-equivalent premium
    "bio_lng": per_t(682.5 + (162 + 290) / 2, 41.0),
    "fame": per_t(1185, 37.0),
}
# DNV Maritime Forecast to 2050 (2026 edition), box "Note on units and metrics" and Section 4.2
DNV_LSHFO = {2030: toe(502), 2040: toe(389), 2050: toe(394)}
DNV_LNG = {2030: toe(410), 2040: toe(440), 2050: toe(473)}
DNV_FAME_2030 = toe(1800)                       # example FAME bio-diesel price, 2030
# DNV Table 4-1: abatement cost ranges (USD/tCO2eq) by feedstock group; Section 4.2: e-ammonia path
DNV_AC = {"bio": {2040: (160, 880), 2050: (130, 810)}, "e": {2040: (550, 1440), 2050: (380, 890)}}
DNV_AC_NH3 = {2030: 680, 2040: 550, 2050: 380}
DNV_GFI_FOSSIL = 95.48


def dnv_price(year: int, ac: float, gfi: float) -> float:
    """Fuel price implied by DNV's abatement cost: LSHFO + AC × ΔGFI × 0.0419 (USD/toe → USD/GJ)."""
    return toe(DNV_LSHFO[year] * TOE_GJ + ac * (DNV_GFI_FOSSIL - gfi) * 0.0419)
# LR & UMAS (2020) Table B3, lower / upper bound (USD/GJ)
LR = {
    "hfo": ({2030: 11, 2040: 11, 2050: 11}, {2030: 11, 2040: 11, 2050: 11}),
    "fame": ({2030: 24, 2040: 27, 2050: 29}, {2030: 49, 2040: 74, 2050: 98}),
    "bio_methanol": ({2030: 21, 2040: 23, 2050: 25}, {2030: 48, 2040: 72, 2050: 96}),   # waste low, wood high
    "e_diesel": ({2030: 114, 2040: 99, 2050: 83}, {2030: 182, 2040: 156, 2050: 130}),
    "e_methanol": ({2030: 73, 2040: 63, 2050: 52}, {2030: 118, 2040: 101, 2050: 83}),
    "e_lng": ({2030: 60, 2040: 51, 2050: 42}, {2030: 98, 2040: 84, 2050: 69}),
    "e_ammonia": ({2030: 47, 2040: 39, 2050: 30}, {2030: 82, 2040: 68, 2050: 55}),
}
# EMSA / CE Delft (2023) wind study, Table 11 (EUR/GJ)
EMSA_VLSFO_2030 = (eur(10.5), eur(14.6))
EMSA_FAME_2030 = (eur(20.1), eur(26.6))
EMSA_NH3_2050 = (eur(29.2), eur(38.0))
# EMSA (2026) ALS study, Table 2-17: current HFO / MDO / LNG (EUR/t)
EMSA_ALS_NOW = {"hfo": per_t(eur(357), 40.5), "mdo": per_t(eur(480), 42.7), "lng": per_t(eur(728), 49.1)}


def combine(lows: list[float], highs: list[float], centrals: list[float]) -> dict[str, float]:
    lo, hi = min(lows), max(highs)
    c = statistics.median(centrals)
    return {"low": lo, "central": min(max(c, lo), hi), "high": hi}


def ratio_path(base: dict[int, dict], r_lo: float, r_c: float, r_hi: float) -> dict[int, dict]:
    return {y: {"low": v["low"] * r_lo, "central": v["central"] * r_c, "high": v["high"] * r_hi} for y, v in base.items()}


def build() -> dict[str, dict[int, dict]]:
    gj: dict[str, dict[int, dict]] = {}
    # heavy fuel oil: LR flat 11, DNV central path, EMSA VLSFO 2030 range as upper evidence
    hfo = {}
    for y in YEARS:
        lows, highs, cs = [LR["hfo"][0][y], DNV_LSHFO[y]], [LR["hfo"][1][y], DNV_LSHFO[y]], [DNV_LSHFO[y], 11.0]
        if y == 2030:
            highs.append(EMSA_VLSFO_2030[1])
        hfo[y] = combine(lows, highs, cs)
    gj["hfo"] = hfo
    # VLSFO and MGO as ratios to HFO observed in the market (Oct 2026) and in EMSA ALS (2025)
    r_lfo = MARKET_2026["lfo"] / MARKET_2026["hfo"]
    gj["lfo"] = ratio_path(hfo, 1.0, r_lfo, r_lfo)
    r_mgo = sorted([EMSA_ALS_NOW["mdo"] / EMSA_ALS_NOW["hfo"], MARKET_2026["mgo"] / MARKET_2026["hfo"]])
    gj["mgo"] = ratio_path(hfo, r_mgo[0], statistics.mean(r_mgo), r_mgo[1])
    # fossil LNG: DNV path; range from the LNG/HFO ratios in DNV, EMSA ALS and the market
    ratios = sorted([DNV_LNG[y] / DNV_LSHFO[y] for y in YEARS] + [EMSA_ALS_NOW["lng"] / EMSA_ALS_NOW["hfo"],
                                                                  MARKET_2026["lng"] / MARKET_2026["hfo"]])
    gj["lng"] = {y: {"low": min(r * hfo[y]["low"] for r in ratios), "central": DNV_LNG[y],
                     "high": max(r * hfo[y]["high"] for r in ratios)} for y in YEARS}
    # biofuels: LR/UMAS lower bound (their upper bound is "illustrative only", 4× the 2020 value, so it is
    # not used), EMSA 2030 range, DNV 2030 FAME example and DNV 2040/2050 biofuel abatement-cost range
    # converted to prices for a FAME-like GHG intensity of 16 gCO2eq/MJ (DNV's example)
    def bio(key: str, gfi: float = 16.0) -> dict:
        out = {}
        for y in YEARS:
            lows, highs, cs = [LR[key][0][y]], [], [LR[key][0][y]]
            if y == 2030:
                if key == "fame":
                    lows.append(EMSA_FAME_2030[0])
                    highs += [EMSA_FAME_2030[1], DNV_FAME_2030]
                    cs += [sum(EMSA_FAME_2030) / 2, DNV_FAME_2030]
                else:
                    highs.append(LR[key][1][y])
                    cs.append((LR[key][0][y] + LR[key][1][y]) / 2)
            else:
                a, b = DNV_AC["bio"][y]
                lows.append(dnv_price(y, a, gfi))
                highs.append(dnv_price(y, b, gfi))
                cs.append((dnv_price(y, a, gfi) + dnv_price(y, b, gfi)) / 2)
            out[y] = combine(lows, highs, cs)
        return out

    gj["fame"] = bio("fame")
    gj["hvo"] = gj["fame"]
    gj["bio_methanol"] = bio("bio_methanol")
    # e-fuels: LR/UMAS bounds plus DNV 2040/2050 e-fuel abatement range (GHG intensity ≈ 0 assumed)
    for k in ("e_diesel", "e_methanol", "e_lng"):
        lo, hi = LR[k]
        out = {}
        for y in YEARS:
            lows, highs, cs = [lo[y]], [hi[y]], [(lo[y] + hi[y]) / 2]
            if y in DNV_AC["e"]:
                a, b = DNV_AC["e"][y]
                lows.append(dnv_price(y, a, 0))
                highs.append(dnv_price(y, b, 0))
                cs.append((dnv_price(y, a, 0) + dnv_price(y, b, 0)) / 2)
            out[y] = combine(lows, highs, cs)
        gj[k] = out
    nh3 = {}
    for y in YEARS:
        lo, hi = LR["e_ammonia"][0][y], LR["e_ammonia"][1][y]
        lows, highs, cs = [lo], [hi], [(lo + hi) / 2, dnv_price(y, DNV_AC_NH3[y], 0)]
        if y == 2050:
            lows.append(EMSA_NH3_2050[0])
            highs.append(EMSA_NH3_2050[1])
            cs.append(sum(EMSA_NH3_2050) / 2)
        nh3[y] = combine(lows, highs, cs)
    gj["e_ammonia"] = nh3
    # bio-LNG: priced like bio-methanol from waste (same feedstock family) — the closest LR/UMAS pathway
    gj["bio_lng"] = gj["bio_methanol"]
    # grey methanol: no forward source; LNG path (both natural-gas based) — flagged "verify"
    gj["methanol"] = gj["lng"]
    # 2026 market values (single observation → low = central = high)
    now = dict(MARKET_2026)
    now["hvo"] = now["fame"]
    for k in gj:
        v = now.get(k, gj[k][2030]["central"])
        gj[k] = {2026: {"low": v, "central": v, "high": v}, **gj[k]}
    return gj


FUEL_FAMILY = {"hfo": "hfo", "lfo": "lfo", "mgo": "mgo", "lng_otto_ms": "lng", "lng_otto_ss": "lng",
               "lng_diesel_ss": "lng", "lng_lbsi": "lng", "methanol": "methanol", "hvo": "hvo", "fame": "fame",
               "bio_methanol": "bio_methanol", "bio_lng_otto_ms": "bio_lng", "e_methanol": "e_methanol",
               "e_diesel": "e_diesel", "e_ammonia": "e_ammonia"}


def main() -> None:
    gj = build()
    fuel = {}
    for fid, fam in FUEL_FAMILY.items():
        gj_t = FUELS[fid]["value"]["lcv"] * 1000          # MJ/g → GJ/t
        fuel[fid] = {str(y): {k: round(v * gj_t) for k, v in p.items()} for y, p in gj[fam].items()}
    doc = {
        "name": "prices", "title": {"el": "Τιμές καυσίμων και αγοράς", "en": "Fuel and market prices"},
        "sources": {
            "market_oct26": {"title": "Ship & Bunker port indications 6 Oct 2026 (via ShipUniverse, 7 Oct 2026): Rotterdam VLSFO $682.50/t, MGO $1,340/t, HSFO $613/t; ENGINE Fuel Switch Snapshot 5 Oct 2026: Rotterdam LNG $240–364/t and LBM $162–290/t VLSFO-equivalent above VLSFO; ENGINE Biofuel Bunker Snapshot 12 Oct 2026: B100 $1,185/t",
                             "url": "https://www.shipuniverse.com/?p=22139", "checked": "2026-10-25"},
            "dnv_mf2026": {"title": "DNV (2026), Maritime Forecast to 2050: LSHFO 502/389/394 USD/toe and fossil LNG 410/440/473 USD/toe in 2030/2040/2050; FAME example 1,800 USD/toe in 2030; abatement costs (Table 4-1) biofuels 160–880 / 130–810 and e-fuels 550–1,440 / 380–890 USD/tCO2eq in 2040 / 2050; e-ammonia 680/550/380 USD/tCO2eq; discount rate 8%",
                           "url": "https://www.dnv.com/maritime/publications/maritime-forecast/", "checked": "2026-10-25"},
            "lr_umas_2020": {"title": "Lloyd's Register & UMAS (2020), Techno-economic assessment of zero-carbon fuels, Table B3: lower and upper bound fuel prices 2030–2050 (USD/GJ)",
                             "url": "https://www.methanol.org/wp-content/uploads/2020/04/Techno_economic_assessment_of_zero_carbon_fuels.pdf", "checked": "2026-10-25"},
            "emsa_wind": {"title": "EMSA / CE Delft (2023), Potential of Wind-Assisted Propulsion for Shipping, Table 11: VLSFO 10.5–14.6 and FAME 20.1–26.6 EUR/GJ in 2030; green ammonia 29.2–38.0 EUR/GJ in 2050",
                          "url": "https://emsa.europa.eu/publications/reports/item/5078-potential-of-wind-assisted-propulsion-for-shipping.html", "checked": "2026-10-25"},
            "emsa_als": {"title": "EMSA (2026), Hull Air Lubrication System Study, Table 2-17: current HFO 357, MDO 480, LNG 728 EUR/t; discount rate 8% (after DNV)",
                         "url": "https://www.emsa.europa.eu/publications/item/5633-hull-air-lubrication-system-study.html", "checked": "2026-10-25"},
            "imo4_q": {"title": "Fourth IMO GHG Study 2020, Annex Q: interest rate 4% (IMarEST 2011: 10%); standard ship lifetime 25 years",
                       "url": "https://www.imo.org/en/ourwork/Environment/Pages/Fourth-IMO-Greenhouse-Gas-Study-2020.aspx", "checked": "2026-10-25"},
            "eurostat_h2_2025": {"title": "Eurostat non-household electricity prices, second half of 2025 (reported by Cyprus Mail, 8 May 2026): EU average €18.37 per 100 kWh; Ireland €25.52; Finland €7.48",
                                 "url": "https://cyprus-mail.com/2026/05/08/cyprus-businesses-pay-second-highest-electricity-rates-in-europe", "checked": "2026-10-25"},
            "clarksea_oct26": {"title": "Clarksons Research via ShipUniverse (5 Oct 2026): ClarkSea Index $75,658/day, Q3 2026 average $46,384/day, 84% above the 10-year trend",
                               "url": "https://www.shipuniverse.com/?p=21695", "checked": "2026-10-25"},
            "assume": {"title": "Modelling assumption of this application, documented in docs/decisions/0009", "checked": "2026-10-25"},
        },
        "values": {
            "fuel_usd_t": {"value": fuel, "source": "dnv_mf2026",
                           "note": "Built by tools/build_prices.py from market_oct26, dnv_mf2026, lr_umas_2020, emsa_wind and emsa_als. "
                                   "Grey methanol follows LNG and bio-LNG follows waste bio-methanol (no direct forward source): to verify."},
            "electricity_eur_kwh": {"value": {"low": 0.0748, "central": 0.1837, "high": 0.2552}, "source": "eurostat_h2_2025",
                                    "note": "Non-household electricity, second half of 2025: EU average (central), Finland (low), Ireland (high). Port shore-power tariffs may differ."},
            "earnings_usd_day": {"value": {"default": {"low": 24000, "likely": 46384, "high": 75658}}, "source": "clarksea_oct26",
                                 "status": "verify",
                                 "note": "Cross-sector ClarkSea Index: 5 Oct 2026 $75,658/day (high), Q3 2026 average $46,384/day (likely), "
                                         "≈ 10-year trend $24,000/day (low; the index was 84% above trend). Ship-type figures to be added."},
            "discount_rate": {"value": {"low": 0.06, "likely": 0.08, "high": 0.10}, "source": "dnv_mf2026",
                              "note": "Decision 0009-6. 8% as in DNV (2026) and EMSA (2026); IMO study 4%, IMarEST 10%."},
            "ship_life_years": {"value": 25, "source": "imo4_q"},
            "time_cost_share": {"value": {"low": 0.0, "likely": 0.5, "high": 1.0}, "source": "imo4_q", "status": "verify",
                                "note": "Share of extra days at sea that costs earnings; the IMO study assumed half the lost capacity is replaced by new ships."},
        },
    }
    out = ROOT / "navigator/config/market/prices.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    for k in ("hfo", "lng", "fame", "bio_methanol", "e_methanol", "e_ammonia"):
        print(k, {y: tuple(round(v, 1) for v in p.values()) for y, p in gj[k].items()})


if __name__ == "__main__":
    main()
