# 0005 · FuelEU, IMO NZF and CII engines; worldwide scope from public data

- **Date:** 2026-10-24
- **Status:** accepted

## Scope: ships trading with the EU, analysed worldwide
The population is the EU MRV fleet (26,178 ships, public data). EU MRV records only voyages that
touch an EU port, while the IMO Net-Zero Framework (NZF) applies to all international voyages.
Limiting the analysis to EU activity would understate NZF costs most for deep-sea ships (the core
of Greek shipping). The application therefore offers two views, switched quietly in the top bar:

- **EU:** recorded EU MRV data only. The IMO measures are computed on EU-recorded activity, which
  is a lower bound.
- **WW:** non-EU activity is added from the EU share of activity, obtained in this order:
  (a) the user's own value; (b) an estimate, *MRV time at sea ÷ (typical days at sea for the ship
  type × 24)*; (c) a plausibility check against IMO GHG Study averages (to be added with the
  study's tables). Ships with an estimated share of 90% or more are treated as trading mainly in
  the EU. Every estimate is labelled and explained in an unfolding "Read more" note.

The EU ETS and FuelEU are EU measures and do not change between views. CII does not change
either: CO2 and distance scale by the same factor.

**Open item:** the typical days at sea are provisional round values (flagged "to verify") until
checked against the Fourth IMO GHG Study 2020 activity tables.

## Fuel mix from public data
EU MRV does not publish fuel types. The CO2 ÷ fuel ratio identifies the family: oil-fuelled
ships lie between HFO (3.114) and MGO (3.206) and are split in proportion; lower ratios indicate
LNG (2.750), split with MGO. In 2024 the medians were 3.12–3.17 for most ship types, 2.74 for
LNG carriers and 3.206 for offshore ships. The LNG engine type, which sets methane slip, is an
assumption the user can change.

## FuelEU Maritime
Annex II default factors and the Commission's calculation methodology. Well-to-wake intensity
uses GWP 25/298 as FuelEU specifies (the EU ETS uses 28/265). Reproduces published intensities:
HFO 91.74, MGO 90.77, LNG Otto medium-speed 89.20 gCO2e/MJ. Penalty with the 10% increase per
consecutive deficit year. Banking, borrowing and pooling are fleet-level and come later; the
single-ship view is therefore conservative. The island/outermost-region derogations (to 2029,
flagged "to verify") reuse the observed EU ETS coverage ratio as a proxy.

## IMO Net-Zero Framework
MEPC 83 draft: reference 93.3 gCO2e/MJ; base/direct targets confirmed for 2028 (4%/17%),
2030 (8%/21%), 2035 (30%/43%) and base 2040 (65%), linear in between. Tier 1 $100 and Tier 2
$380 per t CO2e (2028–2030). Assumptions, all flagged: direct target keeps the 13-point gap to
2040 and both reach 100% in 2050; prices constant after 2030; surplus units valued at zero;
FuelEU fuel factors with AR5 GWPs until the IMO LCA defaults are final. Three scenarios: adopted
as drafted (from 2028), adopted one year late, not adopted. Domestic-only ships are excluded; for
MRV ships this is suggested when all voyages are intra-EU and EMSA counts under 20% for the ETS.

## CII
Reference lines (MEPC.353(78)), rating boundaries (G4) and reduction factors to 2030 (MEPC 83).
After 2030 the 2.625-point annual step is assumed to continue (flagged). The operating profile of
the reported year is held constant. Capacity (DWT/GT) is not in EU MRV and must be entered.

## Validation
Hand-calculated cases in `tests/test_regimes.py`: FuelEU penalty for 10,000 t HFO in 2025
(€622,088; ×1.1 in the second consecutive year), NZF tiers in 2028 (823.5 t Tier 2, 4,912.2 t
Tier 1, $804,139), CII reference for an 82,000 DWT bulk carrier (4.1672) and capacity caps.
