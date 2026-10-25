# Follow-ups and reminders

Items that must be revisited later. Every session reads this file (linked from CLAUDE.md) and
reminds the author when an item becomes due. Tick items off with the commit that closes them.

**Thesis deadline: April 2027.**

## After the IMO vote (MEPC extraordinary session, 4 December 2026)
- [ ] Update `navigator/config/regulation/imo_nzf.json` to the outcome: adopted as drafted /
      amended (new targets, prices, start year) / not adopted. Re-check every value marked
      "to verify" (targets after 2035, prices after 2030, surplus-unit value, GWPs, IMO LCA fuel
      factors).
- [ ] Re-weight the NZF scenarios: the actual outcome becomes the default; keep the others only
      if still meaningful.
- [ ] Rerun validation and the thesis case-study numbers; update thesis chapters 2 and 7.

## When Phase 4 (MCDA + SMAA) starts
- [ ] Vectorise the engine with NumPy (EU ETS, FuelEU, NZF, CII) for tens of thousands of runs
      (decision 0007-6; groundwork laid in Phase 2).
- [ ] SMAA samples, with common random numbers across alternatives: EU share (0007-2), ship size
      (0007-1), every PERT input (0007-3), EUA price path, NZF outcome.
- [ ] Use the least-cost compliance baseline (0007-5) as the reference for every alternative;
      report "pay penalties" as a sensitivity case.
- [ ] Move the worldwide estimate's uncertainty from a display range into SMAA (0005, 0007-2).
- [ ] FuelEU pooling, banking and borrowing at fleet level (0005).

## Open data items
- [ ] Replace provisional days at sea (`activity.json`, "to verify") with the Fourth IMO GHG Study
      tables (Phase 2).
- [ ] Confirm EMSA's reuse terms for the bundled EU MRV database before the public release (0004).
- [ ] Code signing of the installers after the thesis (0001).
