# 0012 · Animated charts: one drawing layer, seven chart forms, switchable views

- **Date:** 2026-10-26
- **Status:** accepted (the author asked for every idea to be built, with a small switch where two fit
  the same section)
- **Replaces:** the on-screen part of [0003](0003-charts-and-language.md); the first decision graphics
  of [0011](0011-decision-graphics.md).

## Context
The author found the charts of 0011 neither readable nor striking: dark, competing colours that hid the
red mark, and a priority map that looked pixelated. He asked for charts that, as in Financial
Architect, move smoothly to their new values whenever any setting changes, in every step, and for new
forms inspired by references he supplied: a fan of flows (an infographic of journeys from one origin),
radar charts (small multiples from a ScienceDirect overview and a plain one), a tilted exploded donut,
and a ship's radar screen; and to try a turnable 3D view. Accuracy comes first.

## Decisions
1. **One drawing layer.** All on-screen charts are drawn with QPainter (`ui/charts.py`), following
   Financial Architect: each chart keeps what it shows and eases to new data over 0.7 s (out-cubic), with
   the axis scale gliding too and bars rising in a short wave. Value labels fade in once settled; hover
   shows the figures. The ✦ switch in the top bar turns all motion off. pyqtgraph is removed (smaller
   installer). matplotlib remains for print figures.
2. **Switchable views.** Where two forms fit the same result, both are built and a column of small
   chips in a 30-px gutter on the right switches between them, without covering the chart.
3. **Forms and where they are used** (each chosen for what it shows accurately):

   | Step | Section | Views |
   |---|---|---|
   | 2 | Annual compliance cost | stacked bars by year · tilted donut of each regime's share over the horizon |
   | 4 | Resulting weights | bars · radar of the company's weights against entropy and CRITIC |
   | 5 | Option profiles (new) | one radar per option (small multiples) · all options on one radar |
   | 5 | Robustness to priorities | ship's radar of weights · priority map of two families · turnable 3D surface |
   | 5 | Fan of futures (new) | cumulative discounted cash flow of 400 SMAA futures for a chosen option, NPV distribution, shares |
   | 5 | Chance of each rank | bubble matrix of rank acceptability (the donut was removed at the author's request, 26 Oct) |

4. **Accuracy rules.**
   - Profile radars use the same min–max normalisation as SAW, and the hover gives the actual values. The text says that a
     shape's area is not a score.
   - The donut's slight tilt only gives depth; every share is written next to its slice.
   - The priority map's regions are exact convex polygons. SAW scores are affine in the two family weights, so each winner's
     region is the triangle clipped by half-planes (`ranking.winner_regions`). This replaces a 60×60 grid. A test checks the
     result against the grid.
   - The weight radar's echoes are the same Dirichlet sample SMAA uses, and the winners are computed at the most likely
     values.
   - The 3D surface's height is the exact SAW lead of the recommendation (`affine_scores`). Winner borders are drawn on it
     exactly.
   - The fan's paths are the engine's own yearly flows, discounted with each future's rate (`SmaaResult.details["paths"]`).
     A test checks that their end points equal the NPV.
5. **Colours.**
   - In step 5 the recommendation is red everywhere and "do nothing" is grey. The other options take soft colours that read
     in both themes.
   - In the fan, red means loss and blue means gain, as in the author's reference.
   - The ship's radar is always a dark phosphor screen.
6. **The 3D view** is drawn in software: painter's algorithm with flat shading coloured by height, plus a translucent "sea"
   at zero lead. It needs no OpenGL, so it brings no packaging risk. It turns slowly by itself, and dragging turns and tilts
   it.
7. **Performance.** Measured offscreen at 1200×480:
   - The fan draws its 400 smooth lines once into a cached layer (3 ms per frame afterwards). While it morphs, it draws a
     lighter subset.
   - The ship's radar caches its static layer: about 6 ms per frame with the sweep running.
   - The 3D surface is vectorised: about 25 ms per frame for roughly 1,000 triangles.
   - Timers run only while a chart is visible and motion is on.

## Consequences
- Tests: `tests/test_charts.py` makes every chart morph between two data sets with motion on and checks that it settles.
  Further tests cover the exact winner regions and the fan's paths.
- Screenshots: `tools/screenshots.py` also saves every view of every switchable chart in
  `docs/screenshots/views/`.
