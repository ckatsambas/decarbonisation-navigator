# 0009 · Phase 3 plan: measure library, power model, fuel prices, investment value

- **Date:** 2026-10-25
- **Status:** accepted (author's choices below)

## Principle
As in Phase 2, Phase 3 prepares **data for MCDA and SMAA**. It produces, for every measure on a
given ship, a set of attributes held as min / likely / max ranges (PERT, decision 0007-3). Phase 4
turns these into criteria, weights them and ranks the alternatives under uncertainty.

## Decisions
1. **Library scope: 25 measures that adapt to each ship.** (Options: about 12, about 25,
   about 40.) There are five groups: operation, hull and propeller, machinery and energy, wind,
   and fuels and engine conversions. Instead of fixed variants per ship size (the 40-measure
   option), each measure has
   - an **applicability rule** by ship type, e.g. air lubrication only for flat-bottomed ships;
   - **scaling rules** for cost and effect, e.g. number of rotor sails by ship size, a minimum
     engine size for waste-heat recovery, and conversion cost proportional to engine power.
2. **Ranges: spread across sources.** (Options: spread across sources; one source ± margin;
   sources + expert review.) Each figure comes from at least three published sources where they
   exist. The min and max come from the spread and the likely value from the median. Every value
   carries its source ids, so it can be checked in the app.
3. **Combination: a ship power model.** (Options: ordered chain with a clash table; simple sum;
   power model. The author chose the power model.) A full hull-resistance model was rejected
   because EU MRV publishes no hull dimensions. The adopted model is the **bottom-up model of the
   Fourth IMO GHG Study**:
   - Admiralty law for propulsion power, with weather and fouling factors;
   - auxiliary and boiler power by ship type, size and operating phase;
   - specific fuel consumption at the actual engine load;
   - wind thrust by trading area;
   - fuel carbon content (`fuels.json`).
   Each measure acts on its own link of the chain. For EU MRV ships the reference power is
   calibrated so that the model reproduces the reported fuel. A table of incompatible pairs
   (e.g. LNG and methanol conversion) still applies.
4. **Attributes: cost, effect and qualitative.** (Options: cost and emissions only; this;
   plus lifecycle and stranded-asset risk.)
   - Cost: CAPEX, OPEX, days off-hire and lifetime.
   - Effect: energy and emission saving.
   - Scored, sourced attributes: technical maturity (TRL), fuel/bunkering availability,
     safety/crew, lost cargo space, and robustness under each regulation.
5. **Fuel prices: low / central / high paths per fuel to 2050.** (Options: this; today's prices
   held constant; random linked paths.) The paths come from published outlooks, the same
   approach as the EU ETS price in Phase 1. Phase 4 SMAA samples between them.
6. **Investment value: NPV with a range.** (Options: this; simple payback; real options.)
   - Discount rate 6 / 8 / 10%.
   - Measure lifetime counted against the ship's remaining life.
   - Lost income during days off-hire.
   - Outputs: NPV, payback years and € per tonne CO2e avoided.
   Real options were left out so that they do not compete with MCDA/SMAA.

## Consequences
- Phase 4 criteria come directly from point 4. SMAA samples every range from points 2, 5 and 6.
- Phase 5 (bundles and timing) uses the power model to combine measures.

## Implementation and results (2026-10-25)
- **Power model** (`engine/power.py`, `config/model/imo4_power.json`): Admiralty law (n = 3, m = 0.66), weather
  factor 0.867 / 0.909 and fouling 0.917 (Annex L), δw for large container and cruise ships, Table 17
  auxiliary and boiler power, Table 19 SFC and the Eq. 10 load curve. On the IMO classes it reproduces
  the reported fuel exactly and implies engines within 15–25% of the class averages.
- **Validation on EU MRV** (`docs/validation/power-model.md`): implied engines are 1.2–1.4× the class
  averages (gas carriers 2.9×), and fuel per mile barely responds to the year-to-year change in MRV average
  speed. The most likely reason is that MRV's distance ÷ time at sea is not the sailing speed; annual MRV
  averages cannot test the speed–power law, so the IMO study's cube law is kept and stated as an assumption.
- **Measures** (`config/technology/measures.json`, built by `tools/build_measures.py`): 25 measures and two
  variants (slow steaming −20%, B100). Sources: IMO GreenVoyage2050 portal, Bouman et al. (2017), EMSA wind
  (2023), EMSA air lubrication (2026), EMSA onboard carbon capture (2026), Mærsk Center (2022), DNV (2026),
  IMO GIA JIT study (2022), IMO study Annex Q. Wind units per ship follow EMSA Table 6; equipment comes in
  three size tiers; air lubrication savings are by ship type (EMSA 2026). Entries resting on one source or
  an assumption keep "verify" (weather routing, trim optimisation).
- **Prices** (`config/market/prices.json`, built by `tools/build_prices.py`): 2026 market (Rotterdam,
  October 2026), then low / central / high to 2050 from DNV (2026), LR & UMAS (2020) and EMSA; LR/UMAS's
  biofuel upper bounds are "illustrative" (4× 2020) and are not used. Electricity from Eurostat; daily
  earnings from the ClarkSea Index (cross-sector, to be split by ship type).
- **Regulation links**: sustainable biofuels zero-rated in the EU ETS (NEa 2025; RFNBO assumed, to verify);
  onboard carbon capture credited in the EU ETS only (DNV 2026), switchable.
- **Economics** (`engine/economics.py`): NPV at 6 / 8 / 10%, horizon = years of service left (≤ 2050),
  renewals and residual value, off-hire and slower-sailing time at daily earnings, cost per tonne
  CO2e avoided well-to-wake (IMO Annex Q.5 "MAC with NPV").
- **Interface**: step 3 lists every measure for the ship with emissions cut, investment, NPV and € per
  tonne; the detail panel shows ranges, attributes, cash flow and sources; ticked measures form the
  shortlist for Phase 4.
