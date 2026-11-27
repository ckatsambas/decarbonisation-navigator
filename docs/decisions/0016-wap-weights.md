# 0016 — WAP as the simple way to weight the criteria; BWM and AHP for advanced users

Date: 27 November 2026. Status: implemented.

## Context
On 20 November 2026 the supervisor approved the thesis and the software and suggested replacing AHP,
which he found hard to use, and possibly BWM with WAP (Weights Assessment through Prioritizations,
Tsotsolas, Spyridakos, Siskos & Salmon 2019). The author's own view: BWM and AHP are well established
but ask questions in an old way, tire the eye and make it hard to see what is being measured, and AHP
has known weaknesses (inconsistent judgement matrices, rank reversal). He asked to keep both as options
for advanced users, add WAP as the easy method, and show no charts until the user has picked a method.

## Decisions
1. **Method chooser first** (`ui/wap_input.py: MethodChooser`). Step 4 opens with three cards: WAP marked
   "simple · recommended", BWM and AHP "for advanced users". Until one is picked, nothing else of the
   step is shown and the weights are equal. The method can be changed later from the bar at the top;
   each method keeps its own answers. Projects saved before this note open with the method they used.
2. **WAP engine** (`engine/mcda/wap.py`, pure Python + SciPy HiGHS). The user (a) puts the items in order,
   ties allowed, and (b) gives for each pair of consecutive classes a range [z_min, z_max] for "the upper
   class matters z times as much". Constraints: equal weights within a class,
   z_min·p_low ≤ p_up ≤ z_max·p_low, Σp = 1, p ≥ 0. The 2n LPs min/max p_i give the range of each weight
   and μ_i = max − min; the working weights are the barycentre of the 2n solutions; the Average Stability
   Index ASI (Grigoroudis & Siskos 2010) summarises how much the weights can move. There is nothing that
   can contradict, so no consistency ratio. The product of the z ranges is reported as the z of the
   revised Simos method.
3. **Validation** (`tests/test_mcda.py`): the paper's example (crit1 > {crit2, crit5} > crit3 > crit4) is
   reproduced to four decimals: minima, maxima, barycentre and μ of Table 3 (mean μ 0.0209) and the
   narrowed case of Table 10 (z_max,1 = 1.22). The ASI computed with the published formula on the 2n LP
   solutions is 0.979 for Table 3, where the paper prints 0.9923 from the RAVI software; the formula RAVI
   applies is not documented. Our ASI moves the same way (it rises after narrowing), and it is used only
   as a stability label, so the difference does not affect any weight. To be noted in chapter 6.
4. **Words, then ranges**. Between two neighbours the user clicks a word: same (a tie), a little more
   (×1.1–1.5), clearly more (×1.5–2), much more (×2–3), very much more (×3–5). The word sets a starting
   range that a two-handle slider on a log scale (×1–×6) can narrow or widen; dragging updates the word.
   This replaces RAVI's scroll bars with something one click answers. White cards are not offered: with
   ranges they add nothing the user cannot say directly (the paper makes the same point).
5. **What the user sees**: each item in order with its rank (=2 for ties), ▲ ▼ to move it, and a bar with
   the range its weight can take (band) and the working weight (dot); under each section the ASI as
   "stable / fairly stable / varies a lot" with a hint to narrow ranges (thresholds 0.95 and 0.90). The
   comparison table and the report gain a "Range (WAP)" column; the PDF weight chart shows the ranges as
   error bars. Same two levels as BWM and AHP (families; within money and operations). Global ranges are
   the products of the level ranges, since the levels are independent.
6. **WAP feeds SMAA** (Siskos & Tsotsolas 2015, rule 4). With WAP the SMAA weights are drawn uniformly
   from the polyhedron at each level by hit-and-run (independent vectorised chains started at the
   barycentre, in the space of class weights, ties and z_min = z_max folded in as equalities) and
   multiplied into criteria weights. The arbitrary "how sure are the weights" Dirichlet concentration of
   step 5 is replaced by the company's own ranges; the control is hidden and a note says where the spread
   comes from. With BWM and AHP the Dirichlet stays as before.
7. Also fixed: a new project opened after another one kept the previous project's BWM and AHP answers.

## Alternatives rejected
- Removing BWM and AHP: the author wants them for advanced users and they are the methods most readers
  of the thesis will know; they stay, one click away.
- Revised Simos (cards) with a single z: gives one weight vector from a fixed ratio assumption, which is
  what WAP was designed to relax.
- Using the barycentre in SMAA with a Dirichlet around it: would throw away the information in the ranges.
- Vertex enumeration of the polyhedron (Manas–Nedoma) for the robustness measures: the 2n LP solutions are
  what the method prescribes and suffice for the ranges and the barycentre.

## References
- Tsotsolas N., Spyridakos A., Siskos E., Salmon I. (2019), Criteria weights assessment through
  prioritizations (WAP) using linear programming techniques and visualizations, Operational Research 19:135–150.
- Siskos E., Tsotsolas N. (2015), Elicitation of criteria importance weights through the Simos method:
  a robustness concern, European Journal of Operational Research 246:543–553.
- Grigoroudis E., Siskos Y. (2010), Customer Satisfaction Evaluation, Springer (ASI).
- Tervonen T., van Valkenhoef G., Baştürk N., Postmus D. (2013), Hit-And-Run enables efficient weight
  generation for simulation-based multiple criteria decision analysis, EJOR 224:552–559.
