# 0007 · Phase 2 plan: ship size, worldwide estimate, uncertainty format, baselines

- **Date:** 2026-10-25
- **Status:** accepted (all seven choices: the recommended option)

## Principle
Phase 2 is **data preparation**, not an additional method. Every estimate is produced as a range
(a probability distribution) and its uncertainty is handled by **SMAA**; the ranking is done by
**MCDA**. No separate statistical modelling (Bayesian, machine learning) is introduced, so the
two course methods stay at the centre of the thesis methodology.

## Decisions
1. **Ship size (DWT/GT) for MRV ships: combined estimate.** Fuel per nautical mile within ship
   type, calibrated on the Fourth IMO GHG Study size classes, combined with the inverse of the
   ship's reported EEDI/EEXI against the type's reference line. Shown as a range; user override.
2. **Worldwide EU share: range from IMO data.** Days at sea by ship type *and* size class from the
   IMO study as a distribution, the ship's own fuel per hour, never below the EU-recorded fuel.
   SMAA samples the share.
3. **Uncertainty format: min / most likely / max, sampled as PERT.** Same three numbers for every
   estimated input here and in the Phase 3 technology library.
4. **Ship-type library: full IMO grid + named presets.** Every type × size class of the IMO study,
   each with a representative profile from real MRV ships of that class; presets such as
   Kamsarmax, Capesize, VLCC, Suezmax, MR tanker, container sizes, LNG carrier, ro-pax, cruise.
5. **"Doing nothing" baseline: both, least-cost as default.** (a) pay penalties; (b) comply at
   least cost each year (cheapest of FuelEU penalty, biofuel blending, buying pool surplus).
   Investments are compared with (b) by default.
6. **SMAA speed: groundwork now, full in Phase 4.** Phase 2 stores every estimate as a samplable
   distribution and adds a sampling interface; the vectorised NumPy engine is completed in Phase 4.
7. **Validation: hold-out + IMO aggregates.** Ships with public size data and EU-only ferries
   (known 100% EU share) as hold-out tests; fleet totals by type against the IMO GHG Study / IMO
   DCS figures; error statistics in `docs/validation/`.
