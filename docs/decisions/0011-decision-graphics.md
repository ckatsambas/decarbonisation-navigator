# 0011 · Decision graphics: rank heatmap, priority map, quiet animations

- **Date:** 2026-10-26
- **Status:** accepted (author's choices (a) and (b), plus the proposed animations with an off switch)

## Context
Step 5 showed SMAA rank acceptability as stacked horizontal bars. With six options and six ranks the
colours were hard to read, and nothing showed *how far* the company's weights are from a different answer.

## Decisions
1. **Rank heatmap** (`ui/maps.py: RankHeatmap`) replaces the stacked bars: options × ranks, one hue
   (darker = more often), the percentage in each cell and the expected rank on the right. The recommended
   option has a red outline; "do nothing" (the reference) a dashed one. This is the usual presentation of
   rank-acceptability indices in the SMAA literature (Lahdelma & Salminen 2001; Tervonen & Figueira 2008).
2. **Priority map** (`PriorityMap`): for two criteria families chosen by the user (four pairs offered), the
   winner under SAW for every split of weight a, b with a + b ≤ 1. The other families share 1 − a − b in
   the company's proportions and each family keeps its internal split (`criteria.split_weights`), so the
   company's own weights are one point on the map (red dot). The grey cloud is the family-weight sample
   that SMAA draws around it; the sentence below gives the share of the cloud in the dot's region. Legend
   entries give each option's share of the triangle. SAW is used because it is the simplest additive
   model and the one the weights are elicited for; the other methods are compared in the rankings table.
3. **Animations**: 300–450 ms eased transitions (heatmap fade-in, the red dot moving between axis pairs,
   step-2 figures counting up, bars growing). A ✦ switch in the top bar turns them off and the choice is
   remembered; `NAVIGATOR_ANIMATIONS=0` turns them off for tests and screenshots.

## Later (ordered)
Scatter of the ship against the fleet; marginal abatement cost curve; method-agreement heatmap.
