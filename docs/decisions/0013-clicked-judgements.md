# 0013 · Step 4: judgements are clicked, not dragged

- **Date:** 2026-10-26
- **Status:** accepted (author's choices: click scale for BWM, comparison matrix for AHP, ranges as tooltips)

## Context
The author found the 1–9 sliders of step 4 "unstable": a slider's position is hard to judge, and a small
drag changes the answer. He also found the explanatory text above each section unnecessary.

## Decisions
1. **BWM as a small table** (`BwmBlock`, `ui/judgement.py: ClickScale, WeightBar`).
   - Each item is one row. ★ marks the most important item and ✕ the least important, each with one click.
     Choosing the item already marked at the other end swaps the two.
   - Each other row has two nine-cell scales: "how much less important than ★" (a_Bj) and "how much more
     important than ✕" (a_jW).
     - A click picks the value. The cells up to it fill in, and a short word gives its meaning; hovering
       shows the full Saaty meaning.
     - The ★ row's second cell repeats a_BW, as the method requires; the ✕ row has no second cell.
   - The resulting weight is a bar on each row and eases to its new value.
   - Stored answers are unchanged (`best`, `worst`, `bo`, `ow`), so existing projects open as they were.
2. **AHP as the comparison matrix** (`AhpBlock`, `PairMatrix`).
   - The upper cells hold the answers and the lower cells show the reciprocals.
   - A click on either cell opens the 17 Saaty judgements for that pair, phrased with the two names.
   - A cell's colour shows which side wins and by how much.
   - An amber outline marks an answer more than a factor of 3 away from what the other answers imply
     (w_i / w_j); its tooltip gives the implied value.
   - Weights appear in a column on the right.
   - Stored answers are unchanged.
3. **Ranges as tooltips.** The shortlist's range on each item (swing weighting, decision 0010) no longer
   takes space above each section. It appears when the mouse rests on the item's name, and the step's lede
   says so. A section still shows a line when there is nothing to compare yet.
4. **Step 5:** rank acceptability is shown only as the bubble table. The donut was removed at the author's
   request; decision 0012 is updated.
