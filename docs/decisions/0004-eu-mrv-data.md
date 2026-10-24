# 0004 · EU MRV data: import, interpretation and calibration of the EU ETS

- **Date:** 2026-10-24
- **Status:** accepted

## Context
EMSA publishes one spreadsheet per reporting year (THETIS-MRV, "Emission reports"). The files
used here are 2018 v275 to 2025 v72, generated between 6 February and 24 October 2026:
107,180 full-year reports (exactly the count EMSA's site shows) plus 2,560 partial reports, for
26,178 ships. Two layouts exist: 2018–2023 (62 columns, CO2 only) and 2024 onward (113 columns,
"Full" and "Partial" sheets, CH4, N2O, CO2eq, ETS-reportable emissions and the company).

## Decisions

1. **Local SQLite database, built by an importer** (`navigator/data/mrv.py`). Columns are matched
   by header text, not position, so EMSA can add or reorder columns. Each year stores its EMSA
   version and generation date; a year is replaced only by a newer version. The raw files are
   not committed to Git; the user imports them from a folder (in the app or from the command line).
2. **Partial reports are kept and combined when read.** They arise when a ship changes company
   during the year. Quantities are summed; intensity indicators are recomputed or left empty.
3. **In-port emissions = the larger of "at berth" and "within ports".** In the 2024+ layout the
   "within ports" figure normally includes time at berth, but some companies fill only the berth
   column. Treating them as additive, or using either alone, reproduces EMSA's ETS figure for
   far fewer ships (32% and 64–66%) than the larger-of rule (86.6% exactly, 2024).
4. **Global warming potentials verified from the data.** CO2eq = CO2 + 28·CH4 + 265·N2O holds
   within 0.01 t for 100% of 28,318 ship-years reporting both gases; AR4 (25/298) and AR6 (29.8/273)
   values do not fit. The parameter status changed from "verify" to "verified".
5. **Engine validated against EMSA's ETS figures** (`tools/validate_ets.py`,
   `docs/validation/eu-ets-vs-emsa.md`): exact for 86.6% of ships in 2024 and 78.5% in 2025.
   EMSA is lower where route-specific derogations apply, which annual totals cannot reproduce.
6. **Observed coverage ratio, applied until 2030.** When a ship is loaded from MRV, the ratio
   *EMSA ETS CO2 ÷ rule-based covered CO2* of its latest reported year is stored on the ship and
   applied to projections up to 2030, when the island and outermost-region derogations expire;
   full coverage is assumed from 2031. Example: BLUE STAR DELOS (IMO 9565039), a Greek domestic
   ferry, has a ratio of 0.6% in 2025, so its ETS cost rises roughly 170-fold from 2031.
   Limitation: the transshipment-port rule is permanent, so for affected container ships the
   jump in 2031 overstates the cost; this is listed among the thesis limitations.
7. **ETS scope for MRV ships comes from reported data.** Gross tonnage is not published, and
   from 2025 MRV also covers general cargo and offshore ships of 400–5,000 GT. If EMSA reports
   ETS emissions for the ship, the reported figure decides whether it is in scope.

## Known gap: emissions outside the EU
MRV contains only voyages to, from and between EU ports and time in EU ports; for 94% of ships
the four categories add up exactly to the reported total. A ship's global emissions, needed for
the IMO Net-Zero Framework and CII, are not public (IMO DCS data are confidential). Options are
being evaluated for Phase 1: a user-entered global figure, an estimate from the EU share of
operating time, or ship-type averages from the IMO GHG studies.
