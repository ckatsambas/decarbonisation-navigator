# Power model against the EU MRV fleet

Model: Fourth IMO GHG Study bottom-up method (Admiralty law, Table 17 auxiliaries and boilers, SFC load curve), calibrated to each ship's reported fuel (decision 0009-3).

## 1. Implied main-engine power vs IMO class average (2018)

Ratio = engine power (MCR) the calibration needs ÷ the IMO study's average installed power for the ship's type and size class. 1.00 = same as the class average.

| Ship type | Ships | P25 | Median | P75 | Median engine load |
|---|---|---|---|---|---|
| Bulk carrier | 3,198 | 0.96 | 1.21 | 1.68 | 48% |
| Oil tanker | 1,737 | 0.93 | 1.29 | 1.95 | 35% |
| Container | 1,604 | 1.05 | 1.31 | 1.89 | 32% |
| Chemical tanker | 1,270 | 1.04 | 1.39 | 2.08 | 42% |
| General cargo | 1,087 | 1.02 | 1.38 | 2.03 | 48% |
| Liquefied gas tanker | 482 | 1.40 | 2.88 | 4.65 | 50% |
| Vehicle | 428 | 1.11 | 1.27 | 1.47 | 55% |
| Ferry-RoPax | 374 | 0.92 | 1.17 | 1.48 | 54% |
| Refrigerated bulk | 131 | 0.92 | 1.16 | 1.42 | 86% |

## 2. Fuel per mile when the same ship sails at a different speed

Pairs of consecutive reporting years (2018–2025) of the same ship with a change in average speed of 7% or more. Elasticity = % change in fuel per nautical mile ÷ % change in speed (2 = pure cube law on all fuel).

- Pairs: 34,576
- Observed elasticity, median: -0.10 (P25 -0.59, P75 0.40)
- Model elasticity, median: 1.41
- Median difference (observed − model): -1.46

**Reading.** The observed elasticity is close to zero, far from the model's value and from the physics of ship resistance. The most likely cause is the speed signal rather than the law: EU MRV only gives the annual average *distance ÷ time at sea*, and that average falls mostly when a ship spends more time manoeuvring, drifting or on short legs, which raises fuel per mile instead of lowering it. A cross-section of ships within the same size class shows the same pattern. Annual MRV averages therefore cannot test the speed–power law; the model keeps the cube law of the IMO study (and of the hydrodynamic literature), and the slow-steaming measure is reported with that assumption stated.

The same effect explains part of section 1: a low average speed gives a low estimated engine load and so a larger implied engine. Gas carriers stand out (≈ 2.9×) because many LNG carriers use steam turbines or burn boil-off gas in boilers, which the diesel-engine table does not describe.
