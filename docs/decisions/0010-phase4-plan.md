# 0010 · Phase 4 plan: criteria, weights, ranking and SMAA

- **Date:** 2026-10-25
- **Status:** accepted (all four choices: the recommended option)

## Principle
This is the methodological core of the thesis. The alternatives are the measures shortlisted in step 3.
Each alternative's performance comes from the Phase 3 engine:
- the power model;
- the regulation engines;
- the NPV calculation.
MCDA turns the company's priorities into a ranking. SMAA tests whether that ranking survives every
uncertainty gathered in Phases 2–3 together with uncertainty in the weights.

## Decisions
1. **Criteria: a two-level tree.** (Options: this; the five criteria listed in the step-4 placeholder;
   four classic criteria.) Five families and nine criteria (leaves):

   | Family | Criterion | Direction | From |
   |---|---|---|---|
   | Money | Net present value | max | economics.appraise |
   | Money | Investment (CAPEX) | min | measure library |
   | Climate | Emissions cut, well-to-wake | max | power model |
   | Technology | Maturity (TRL) | max | measure attributes |
   | Operations | Days off-hire | min | measure library |
   | Operations | Cargo capacity lost | min | measure attributes |
   | Operations | Fuel / infrastructure availability | max | measure attributes |
   | Operations | Safety and crew | max | measure attributes |
   | Regulation | Exposure to the IMO vote: NPV lost if the NZF is not adopted | min | computed |

   Family weights × local weights = global weights.
2. **Weights: BWM by default, AHP as an option.** (Options: this; AHP only; weights left open.)
   - Best-Worst Method (Rezaei 2015, linear model, with its consistency ratio) at each level of the tree.
   - AHP (eigenvector, Saaty consistency ratio) can be chosen instead.
   - Entropy and CRITIC are shown as data-driven weights for comparison.
3. **Ranking: SAW, TOPSIS, PROMETHEE II and VIKOR, plus an agreement view.** (Options: this; the four
   side by side; TOPSIS only.)
   - The agreement view is a consensus rank: mean rank over the four methods, Borda-style.
   - It also shows the pairwise Spearman correlation between the methods' rankings.
4. **SMAA-2 on inputs and weights.** (Options: this; weights only; SMAA for every method.)
   - About 10,000 draws with common random numbers. Each draw samples:
     - the measure ranges;
     - fuel price level (fossil and alternative fuels separately);
     - EUA price level;
     - FuelEU pool price and biofuel premium;
     - the IMO NZF outcome (probabilities adjustable);
     - EU share;
     - discount rate;
     - weights from a Dirichlet distribution centred on the company weights (or uniform if none).
   - Outputs: rank acceptability indices, central weight vectors and confidence factors.
   - The utility is additive (SAW-type), as in SMAA-2.

## Engine
- Physical quantities (energy and fuel by fuel and scope, ETS allowances, FuelEU balance and intensity,
  NZF intensity) depend only on a measure's own uncertain effect. They are precomputed with the scalar
  engine on a grid of effect quantiles and interpolated.
- The price- and scenario-dependent parts are vectorised with NumPy over the draws:
  - ETS cost;
  - FuelEU least-cost route, including consecutive penalties;
  - NZF tiers;
  - fuel cost;
  - NPV.
- A test checks that a draw at the most likely values reproduces the scalar appraisal. This closes the
  Phase 4 follow-up "vectorise the engine".

## Implementation and results (2026-10-25)
- `engine/mcda/weights.py`: linear BWM solved as a linear programme (SciPy HiGHS). Consistency uses the
  input-based ratio with the thresholds of Liang, Brunelli & Rezaei (2020, Omega 96, Table 3). Also AHP
  (eigenvector; Saaty's random index), entropy and CRITIC.
- `engine/mcda/ranking.py`: SAW (min–max), TOPSIS (vector normalisation), PROMETHEE II (V-shape
  preference with p = criterion range), VIKOR (v = 0.5, with the two compromise conditions), and a
  consensus by mean rank with the Spearman matrix.
- `engine/mcda/criteria.py`: the tree of decision 1. "Do nothing" (least-cost compliance) is included as
  a reference alternative.
- `engine/mcda/smaa.py`: physics on an 11-point grid of effect quantiles; prices, scenarios and money
  vectorised. In tests, a draw at the most likely values equals `economics.appraise` to the euro, in
  both views and both baselines. 10,000 draws for 6 alternatives take about 3 seconds.
- **Range effect.** In an additive model a weight acts on the spread between options. A first test run
  ranked pure biofuel first in 92% of draws despite an NPV of about −€24 million, because its emissions
  cut (81%) dwarfed the others. The Priorities screen therefore shows, for each family, the actual range
  across the shortlist before asking the question (swing weighting).
- Interface: step 4 (BWM by default, AHP option, three levels, consistency messages, comparison with
  entropy and CRITIC); step 5 (four rankings plus consensus; SMAA settings: IMO vote odds, confidence in
  the weights (Dirichlet κ = 300 / 100 / 20 / uniform), number of draws; rank-acceptability chart;
  first-rank share, expected rank, confidence factor, central weights).
- Fixed on the way: the power model used a generic size class for standard ships and for ships with a
  manually entered EU share. It now receives the ship's class and reported hours at sea from the inputs.
