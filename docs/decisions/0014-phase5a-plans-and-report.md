# 0014 · Phase 5a: investment plans (MILP + two-stage) and the report

- **Date:** 2026-10-26
- **Status:** accepted
- **Author's choices:** core first (5a: plans and report; 5b: fleets, FuelEU pooling, group decisions if
  time allows); Pareto front as the objective, keeping "no-penalty plans only" and yearly cut targets for
  later; PDF + Excel report. Between MILP and dynamic programming the author asked for whichever serves the
  company's decision best.

## 1. Method: MILP, plus the part of dynamic programming that matters to a shipowner
- **What a board approves.** A capital plan: which measures, in which year, how much each year. A
  mixed-integer programme gives exactly that, under budget and compatibility limits, together with a front
  of NPV against emissions cut.
- **What pure dynamic programming would add.** Decision rules ("install when the EUA price passes X").
  They are informative, but they are not a plan that can be approved and financed.
- **What we take from it.** The two-stage idea: what is installed *now* is the same in every future, and
  later steps adapt to how prices and the IMO outcome turn out. This is a stochastic MILP over nine
  futures, and it yields the value of keeping later steps open.

## 2. Plans and the deterministic front (`engine/plan.py`, `engine/optimise.py`)
- **Timed plans.**
  - A plan maps each measure to its installation year.
  - `appraise_plan` runs the ship with the set of measures working in each year: the power model, every
    regime, and the cash flow with capex, renewals, residual value, off-hire and opex counted from each
    measure's own year.
  - With every measure starting together it equals `appraise` (tested).
- **Search.**
  - Each measure has a binary variable for each year it could be installed.
  - The value of each measure alone, and the exact correction for each pair, come from the full engine.
  - Each pair product is linearised (McCormick). Constraints:
    - inequalities only on the side the signs need;
    - after the last installation year all years collapse into one period;
    - measures that exclude each other cannot be combined;
    - an optional budget per year.
  - Pairs whose interaction is below 1% of the largest single value are left out of the search.
- **Front.**
  - The ε-constraint method: the best-NPV plan, the deepest-cut plan, and the highest-NPV plan at six
    levels of cut in between.
  - Each plan found is improved by an exact local search (add, drop, or move one measure), using cached
    per-set yearly values that match the engine. It is then re-appraised exactly, and dominated plans are
    dropped.
  - The front shows only exact values. Interactions of three or more measures are the only approximation,
    and they affect only the search.
- **Speed.** About 15–35 s for all 25 measures on a 9-year window; a few seconds for a shortlist.

## 3. Two-stage plan (`optimise.adaptive`)
- **Futures.** Nine: market (fuel prices and EUA path together: low 25% / central 50% / high 25%) × IMO
  NZF outcome (the market file's odds).
- **Rule.** Installations up to the decision year (default: start + 1) are shared by all futures; later
  ones are free in each future.
- **Comparison.** The value of flexibility compares with the best plan fixed in full today, for the same
  futures and the same average-cut requirement (the value of waiting for information, which is never
  negative). For example, for a Kamsarmax: €1.5m on an expected NPV of €11.8m.

## 4. Plans in MCDA and SMAA
- **Joining the ranking.** A plan chosen on the front ("Add to the options to rank") joins the step-3
  shortlist as an alternative (`criteria.plan_alternative`). Its emissions criterion is the average yearly
  cut over the window, so a later installation counts for less; for single measures this is unchanged.
- **SMAA.** The simulator takes each plan's installation years: `PlanPhysics` switches the physics year
  by year, and capex, opex and off-hire follow each measure's year. A draw at the most likely values
  equals `appraise_plan` (tested).

## 5. Report (step 6, `navigator/report`)
- **Data.** `collect()` words everything in the report's language without switching the interface
  (`i18n.using`).
- **PDF.** Built with matplotlib (0003), seven A4 pages:
  1. summary and settings;
  2. today's position (chart and table);
  3. measures;
  4. plans: the front, the chosen plan's timeline, and the two-stage table;
  5. weights (company, entropy, CRITIC);
  6. ranking, SMAA bubble table and fan of futures;
  7. assumptions still marked "verify", and all sources.
- **Excel.** One sheet per table, with amounts kept as numbers (openpyxl).

## Later (5b and options kept open)
Fleets with FuelEU pooling, banking and borrowing; group decisions (aggregated weights); the
"no-penalty plans only" switch and yearly cut targets (e.g. IMO 2030/2040 checkpoints) as front constraints.
