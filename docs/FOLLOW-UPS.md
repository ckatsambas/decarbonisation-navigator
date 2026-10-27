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
- [ ] Rerun the least-cost baseline (its NZF part) with the adopted rules (0008-4).
- [ ] Replace the equal NZF odds in SMAA (`markets.json` nzf_probability) with the vote's actual outcome (0010).

## Author's notes for the next session (25 Oct 2026), before Phase 5
- [x] Step-3 shortlist checkboxes confirmed working on Windows by the author (26 Oct).
- [x] Step 1 layout: the ship details box goes above the results table, laid out horizontally across the
      width; the table below at full width so every column shows.
- [x] Step 4: a reset button (circular arrow) in every weighting section. The author is not fully happy with
      the sliders or the step-4 layout but has no alternative yet: no change for now.
- [x] Charts, first batch (0011): rank heatmap and priority map in step 5 (company's weights in red), quiet
      animations with an off switch in the top bar.
- [x] Charts, second batch (0012): every chart morphs on each change (FA style); fan of futures, option
      profile radars, ship's radar of weights, exact priority map, turnable 3D surface, donuts; two views
      where two fit, switched by small chips. The author to review on Windows.
- [x] Step 4 inputs (0013): BWM by clicks on 1–9 scales with ★/✕, AHP as a clickable comparison matrix
      with inconsistency outlines, ranges as tooltips; step-5 donut removed. The author to review.
- [ ] Charts, next batch (in this order): the ship against the fleet (scatter), MAC curve, method-agreement
      heatmap.

## Phase 5 (0014)
- [x] 5a: timed plans, MILP Pareto front with exact re-appraisal, two-stage adaptive plan, plans as MCDA/SMAA
      alternatives, step-6 PDF + Excel report. The author to review on Windows.
- [ ] Kept open by the author: a "no-penalty plans only" switch and yearly cut targets (IMO 2030/2040
      checkpoints) as front constraints.
- [ ] 5b (if time allows, target January 2027): fleets with FuelEU pooling, banking and borrowing; group
      decisions (aggregated weights).
- [ ] After the IMO vote: the two-stage plan's NZF odds come from `markets.json`; set them to the outcome.

## First launch (0015)
- [x] Local accounts with guest and terms, preferences (language, theme, interface size), guided tour,
      Help "?" menu with the tour. The author to review on Windows (also at 125 % and 150 % size).
- [ ] The author (and supervisor) to review the wording of the terms (`i18n/terms_el.md`, `terms_en.md`);
      raise `TERMS_VERSION` if it changes.

## When Phase 4 (MCDA + SMAA) starts
- [x] Vectorise the engine with NumPy for tens of thousands of runs (0010: `mcda/smaa.py`, CII not needed).
- [x] SMAA samples with common random numbers: EU share, every PERT input, prices, EUA path, NZF outcome,
      weights (0010). Ship size only affects CII, which is not a criterion.
- [x] Least-cost compliance is the reference for every alternative and a "do nothing" option (0010).
- [x] The worldwide estimate's range is sampled in SMAA (0010).
- [ ] FuelEU pooling, banking and borrowing at fleet level (0005).

## EU reviews before the thesis deadline
- [ ] EU ETS review (Commission proposal July 2026, political agreement expected Q1 2027): update
      `eu_ets_maritime.json` (scope, zero-rating of RFNBO, credit for onboard carbon capture) (0009).
- [ ] FuelEU Maritime review by 31 December 2027 (may add onboard carbon capture as a compliance route);
      after the thesis, but note it in chapter 2.

## Phase 3 data to improve
- [ ] Daily earnings by ship type (now one cross-sector ClarkSea range) for off-hire and slow-steaming costs.
- [ ] Power model: MRV average speed understates sailing speed (validation report); consider the IMO class
      sailing speed for the engine load, and a steam-turbine / boil-off model for LNG carriers.
- [ ] Ammonia engines: N2O emissions not modelled yet; grey methanol and bio-LNG price paths borrowed
      from LNG and waste bio-methanol.
- [ ] FuelEU shore-power obligation (container and passenger ships from 2030) and its penalty are not in the
      FuelEU engine yet; shore power currently earns only its fuel and carbon savings.
- [ ] Weather routing and trim optimisation rest on Bouman (2017) plus an assumption: find measured data.

## Open data items
- [x] Replace provisional days at sea with the Fourth IMO GHG Study tables (Phase 2, 0008).
- [ ] Verify `individual_spread` (±25% days at sea) and the biofuel premium in `markets.json` (0008).
- [ ] Tanker EU share is biased high (implied fuel 0.61–0.70 × class average); add a tanker
      correction or wider range (0008-2).
- [ ] Ship size for vehicle carriers and ro-ro rests on the type range only; find a GT signal
      (e.g. lane metres or the EIV of ro-ro) (0008-1).
- [ ] Confirm EMSA's reuse terms for the bundled EU MRV database before the public release (0004).
- [ ] Code signing of the installers after the thesis (0001).
