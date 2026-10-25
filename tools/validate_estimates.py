"""Validate the size and EU-share estimates (decision 0007-7).

    python tools/validate_estimates.py [path/to/mrv.sqlite]

1. Size mix: estimated size classes of the 2018 EU MRV fleet against the Fourth IMO GHG Study's
   Table 92 (the same ships, matched by the study), per ship type; reports the share of ships in the
   right class distribution and the total variation distance.
2. EU-only hold-out: ships whose every reported voyage is between EU ports (intra-EU, no departures
   or arrivals from third countries) must come out with an EU share near 100%.
3. Plausibility (method c): each ship's implied worldwide fuel against the study's average annual fuel
   for its own type and size class; a median near 1 means the estimate is unbiased.
Writes docs/validation/size-and-share.md.
"""
# ruff: noqa: E402  (paths are set up before the imports)
import collections
import math
import sqlite3
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from navigator.engine import reference as R
from navigator.engine.estimate import estimate_share
from navigator.engine.regulation.cii import cii_type_for
from navigator.engine.sizing import estimate_capacity

YEAR = 2018


def main() -> None:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "mrv.sqlite"
    con = sqlite3.connect(db)
    rows = con.execute("SELECT imo, ship_type, fuel_total, distance_nm, time_at_sea, tech_eff_type, tech_eff_value, "
                       "co2_intra, co2_from, co2_to FROM reports WHERE year=? AND partial=0", (YEAR,)).fetchall()
    t92 = collections.defaultdict(dict)
    for r in R.mrv_2018():
        t92[r["type"]][r["size"]] = r["vessels"]
    est = collections.defaultdict(collections.Counter)
    methods = collections.defaultdict(collections.Counter)
    hold, ratios = [], collections.defaultdict(list)
    for _imo, t, f, d, h, tt, tv, intra, frm, to in rows:
        imo_t = R.MRV_TO_IMO.get(t or "")
        e = estimate_capacity(t, cii_type_for(t), f, d, h, tt, tv)
        if e and imo_t:
            u = e.details["unit"]
            c = R.class_for(imo_t, dwt=e.likely if u == "dwt" else None, gt=e.likely if u == "gt" else None)
            est[imo_t][c.size] += 1
            methods[imo_t][e.method] += 1
        s = estimate_share(t, h, e.likely if e else None, e.details["unit"] if e else "dwt", f)
        if imo_t and s.fuel_ratio and s.method == "estimated":
            ratios[imo_t].append(s.fuel_ratio)
        if (intra or 0) > 0 and not (frm or 0) and not (to or 0):
            hold.append(s.share)
    lines = ["# Size and EU-share estimates against independent data", "",
             f"EU MRV reporting year {YEAR}; reference: {R.source_title()} and Table 92.", "",
             "## 1. Size mix by ship type (IMO Table 92 vs estimate)", "",
             "| Ship type | Ships | Signals used | Distance* | IMO mix → estimated mix by size class |", "|---|---|---|---|---|"]
    for imo_t, counts in sorted(t92.items(), key=lambda kv: -sum(kv[1].values())):
        e = est.get(imo_t)
        if not e:
            continue
        tot_i, tot_e = sum(counts.values()), sum(e.values())
        sizes = [c.size for c in R.of_type(imo_t)]
        tvd = 0.5 * sum(abs(counts.get(s, 0) / tot_i - e.get(s, 0) / tot_e) for s in sizes)
        mix = "; ".join(f"{s}: {counts.get(s, 0) / tot_i:.0%}→{e.get(s, 0) / tot_e:.0%}" for s in sizes)
        sig = ", ".join(f"{m} {n / tot_e:.0%}" for m, n in methods[imo_t].most_common())
        lines.append(f"| {R.of_type(imo_t)[0].label} | {tot_e:,} | {sig} | {tvd:.2f} | {mix} |")
    lines += ["", "\\*Total variation distance between the two mixes: 0 = identical, 1 = no overlap. "
              "Ships estimated from the type range alone all fall in the type's median class by construction; "
              "the app asks the user to confirm their size.", "",
              "## 2. Hold-out: ships with EU-only voyages", "",
              f"{len(hold):,} ships reported only voyages between EU ports. Estimated EU share: median "
              f"{st.median(hold):.0%}, share ≥ 90%: {sum(x >= 0.9 for x in hold) / len(hold):.0%}, "
              f"share ≥ 70%: {sum(x >= 0.7 for x in hold) / len(hold):.0%}.", "",
              "## 3. Plausibility: implied worldwide fuel ÷ IMO class average fuel", "",
              "Ships with an estimated (not EU-dominant) share. 1.00 = same as the average ship of the class.", "",
              "| Ship type | Ships | P25 | Median | P75 |", "|---|---|---|---|---|"]
    for t in sorted(ratios, key=lambda k: -len(ratios[k])):
        q = st.quantiles(ratios[t], n=4) if len(ratios[t]) > 3 else [math.nan] * 3
        lines.append(f"| {R.of_type(t)[0].label} | {len(ratios[t]):,} | {q[0]:.2f} | {q[1]:.2f} | {q[2]:.2f} |")
    out = ROOT / "docs" / "validation" / "size-and-share.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
