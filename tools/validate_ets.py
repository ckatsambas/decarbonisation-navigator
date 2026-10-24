"""Validate the EU ETS coverage rule against the ETS emissions EMSA publishes per ship.

    python tools/validate_ets.py [path/to/mrv.sqlite]

For every full-year report from 2024 onward, the engine's covered CO2 (voyage coverage only,
before phase-in) is compared with EMSA's "CO2 emissions to be reported under Directive
2003/87/EC". Writes docs/validation/eu-ets-vs-emsa.md and a figure for the thesis.
"""
# ruff: noqa: E402  (paths are set up before the imports)
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from navigator.data.mrv import default_db_path
from navigator.engine.models import Gas, ScopeSplit
from navigator.engine.regulation.eu_ets import EtsRules

TOL = 0.001   # 0.1 %


def main() -> None:
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "data" / "mrv.sqlite" if (ROOT / "data" / "mrv.sqlite").exists()
                                                         else default_db_path())
    con = sqlite3.connect(db)
    df = pd.read_sql("SELECT r.*, rel.version, rel.generated FROM reports r JOIN releases rel USING(year) "
                     "WHERE r.year >= 2024 AND r.partial = 0", con)
    rules = EtsRules.load()
    cov = rules.coverage

    def covered(r) -> float:
        s = ScopeSplit(intra_eu=r.co2_intra or 0, in_port=max(r.co2_berth or 0, r.co2_port or 0),
                       from_eu=r.co2_from or 0, to_eu=r.co2_to or 0)
        return sum(cov[k] * getattr(s, k) for k in cov)

    df["engine"] = df.apply(covered, axis=1)
    df["emsa"] = df["co2_ets"].fillna(0)
    df["rel"] = (df["emsa"] - df["engine"]) / df["engine"].replace(0, np.nan)
    df["exact"] = (df["rel"].abs() < TOL) | ((df["emsa"] == 0) & (df["engine"] == 0))
    df["within5"] = (df["rel"].abs() < 0.05) | df["exact"]

    # GWP check on the same data
    m = (df.ch4_total > 0) & (df.n2o_total > 0) & df.co2eq_total.notna()
    resid = df.co2eq_total - (df.co2_total + rules.gwp[Gas.CH4] * df.ch4_total + rules.gwp[Gas.N2O] * df.n2o_total)
    gwp_ok = (resid[m].abs() < 0.01).mean()

    out_dir = ROOT / "docs" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# EU ETS engine against EMSA's published ETS emissions", "",
             "Data: EU MRV public emission reports, full-year reports, "
             + ", ".join(f"{y} v{v} ({g})" for y, v, g in df[["year", "version", "generated"]].drop_duplicates().values)
             + ".", "",
             "Engine rule: 100% of CO2 on voyages between EU ports and within EU ports (the larger of the "
             "'at berth' and 'within ports' figures), 50% on voyages to or from a non-EU port. "
             "Compared before phase-in.", "",
             "| Year | Ships | Exact (±0.1%) | Within ±5% | Exact, ships with EMSA > 0 | EMSA lower | EMSA higher | EMSA = 0 |",
             "|---|---|---|---|---|---|---|---|"]
    for y, g in df.groupby("year"):
        lower = ((~g.exact) & (g.emsa < g.engine)).mean()
        higher = ((~g.exact) & (g.emsa > g.engine)).mean()
        pos = g[g.emsa > 0]
        lines.append(f"| {y} | {len(g):,} | {g.exact.mean():.1%} | {g.within5.mean():.1%} | {pos.exact.mean():.1%} | {lower:.1%} | "
                     f"{higher:.1%} | {((g.emsa == 0) & (g.engine > 0)).mean():.1%} |")
    tot_engine, tot_emsa = df.engine.sum(), df.emsa.sum()
    lines += ["", f"Fleet total: engine {tot_engine/1e6:.2f} Mt CO2, EMSA {tot_emsa/1e6:.2f} Mt CO2 "
              f"(EMSA {tot_emsa/tot_engine - 1:+.1%}).", "",
              "## By ship type (both years)", "", "| Ship type | Ships | Exact | Within ±5% |", "|---|---|---|---|"]
    for t, g in df.groupby("ship_type"):
        lines.append(f"| {t} | {len(g):,} | {g.exact.mean():.1%} | {g.within5.mean():.1%} |")
    lines += ["", "## Global warming potentials", "",
              f"CO2eq = CO2 + {rules.gwp[Gas.CH4]:g}·CH4 + {rules.gwp[Gas.N2O]:g}·N2O holds within 0.01 t for "
              f"{gwp_ok:.1%} of {m.sum():,} ship-years that report both gases.", "",
              "## Interpretation", "",
              "Where EMSA's figure is lower, the likely causes are route-specific rules the engine does not "
              "model from annual totals: the island and outermost-region derogations (ro-pax and passenger "
              "ships) and the treatment of calls at neighbouring container transshipment ports (container "
              "ships). Ships with an EMSA figure of zero are mostly outside the ETS: general cargo ships of "
              "400–5,000 GT and offshore ships, both added to EU MRV in 2025 (offshore ships enter the ETS in "
              "2027). About 100 bulk carriers a year also show zero without an evident reason; they are left "
              "unexplained. For past years the application therefore uses EMSA's reported figure; the rule is used "
              "for projections and for ships without reported data.", "",
              "![Engine vs EMSA](eu-ets-vs-emsa.png)", ""]
    (out_dir / "eu-ets-vs-emsa.md").write_text("\n".join(lines), encoding="utf-8")

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.2), dpi=150)
    ax[0].scatter(df.engine / 1e3, df.emsa / 1e3, s=3, alpha=0.35, color="#2F6FA8", linewidths=0)
    lim = max(df.engine.max(), df.emsa.max()) / 1e3
    ax[0].plot([0, lim], [0, lim], color="#B04A35", lw=1)
    ax[0].set_xlabel("Engine: covered CO2 (kt)")
    ax[0].set_ylabel("EMSA: ETS CO2 (kt)")
    ax[0].set_title("Per ship, 2024–2025")
    r = df.rel.clip(-1, 1).dropna()
    ax[1].hist(r, bins=np.linspace(-1, 1, 81), color="#0E6B73")
    ax[1].set_yscale("log")
    ax[1].set_xlabel("(EMSA − engine) / engine")
    ax[1].set_ylabel("Ships (log)")
    ax[1].set_title("Relative difference")
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_dir / "eu-ets-vs-emsa.png")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
