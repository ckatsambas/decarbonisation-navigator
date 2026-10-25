# 0008 · Estimation methods: ship size, EU share, PERT ranges, baselines, standard ships

- **Date:** 2026-10-25
- **Status:** accepted. Implements decision 0007, with one change made on evidence (point 1).
- **Validation:** `docs/validation/size-and-share.md` (from `tools/validate_estimates.py`)

## 1. Ship size (DWT / GT / TEU / m³)
EU MRV publishes no capacity, but CII and the per-capacity indicators need it. The estimate
combines independent signals by **inverse-variance weighting in log space**. Each signal is a
log-normal centre with its own spread:

| Signal | Used when | Basis |
|---|---|---|
| EEDI/EEXI/EIV inversion | the type's reference line slope c ≥ 0.30 | `eedi.json`: reference lines and reduction phases |
| Fuel per hour at sea (engine power) | fitted elasticity β ≥ 0.5 | IMO study Tables 75–81, 2012–2018, by class |
| Type range (prior) | always | IMO study Table 92, EU-scope size mix 2018 |

The result is an `Estimate(low, likely, high)`, labelled in the interface with its method. When
only the type range is available, the interface asks the user to confirm the size.

**Change from 0007-1.** The agreed design used *fuel per nautical mile*. In validation it put 35%
of bulk carriers in the largest class, against 0.7% in the IMO data, because fuel per mile
depends on speed as much as on size. It was replaced by **fuel per hour at sea**, which tracks
installed power (and so size) much more closely. The fuel-per-mile fit is kept in `sizing.fit`
for the thesis comparison. Container EEDI is excluded, because its reference line is too flat to
invert reliably.

Validation (total variation distance from the IMO size mix; 0 = identical): bulk 0.15,
container 0.14, oil 0.12, general cargo 0.19, chemical 0.21, ro-pax 0.21, gas 0.30. Reefer (0.60)
and vehicle carriers (0.84, type range only) are weak and recorded as follow-ups.

## 2. EU share of activity (worldwide view)
`EU share = MRV hours at sea ÷ (IMO class days at sea × 24)`. The class comes from the size
estimate. Days at sea form a PERT range, with `individual_spread` ±25% (to verify) and a cap of
350 days. A ship whose share is at least 0.9 is treated as EU-dominant.

- Hold-out: 759 ships with EU-only voyages. Median estimated share 100%; 65% of them ≥ 90%.
- Plausibility: implied worldwide fuel ÷ class-average fuel has medians of 0.92 (bulk),
  1.02 (container), 0.95 (general cargo, gas), 0.94 (ro-pax).
- **Known limitation:** tankers come out low (oil 0.61, chemical 0.70). The likely cause is that
  tankers spend more time slow-steaming or waiting than the class average, so the share is
  overstated. SMAA will carry the range. A tanker-specific correction is a follow-up.

## 3. Uncertainty format
Every estimate is min / most likely / max and is sampled as **PERT**:
α = 1 + 4(m − a)/(b − a), β = 1 + 4(b − m)/(b − a). `Sampler` gives common random numbers per
named quantity, so all alternatives in an SMAA run see the same draw of each uncertain input.

## 4. "Doing nothing" baseline
Both are computed, and **least-cost compliance** is the default reference.

- In each year with a FuelEU deficit, the ship takes the cheapest of three routes: pay the
  penalty, buy pool surplus (`markets.json`, 96/119/220 €/t), or blend just enough FAME biofuel
  (premium 0/640/1000 $/t, to verify).
- Blending also lowers the ETS cost (biofuel is zero-rated) and the NZF cost, so the comparison
  uses the whole carbon bill.
- "Pay the penalties" (with the +10% escalation for consecutive years) is kept as a sensitivity
  case.
- Examples to 2050: BLUE STAR DELOS €1,327m paying penalties vs €238m at least cost; AQUADONNA
  €80m vs €31m.

## 5. Standard ships (library)
There are 52 IMO type × size classes (ships of 5,000 GT and above) and 20 named presets
(Handysize to cruise ship). Each takes its fuel, distance and days at sea from the IMO study's
2018 class averages. It also takes an EU trading pattern (deep-sea 30%, mixed 60%, short-sea 100%
EU share), with a default per type. The fuel mix is 78% HFO and 22% MGO, while LNG carriers burn
80% LNG (IMO study Table 34).

## Consequences
- Phase 4 samples size, share and days at sea from these ranges (FOLLOW-UPS).
- After the IMO vote, the NZF part of the least-cost baseline must be rerun.
