# 0001 · Desktop application in Python and PySide6

- **Date:** 2026-10-24
- **Status:** accepted

## Context
The tool must evaluate single decarbonisation measures *and* bundles of measures over time,
for any ship in the EU MRV database (about 12,000 ships per reporting year) and for standard
ship types. Bundles with a budget and timing turn the problem into a mixed-integer
optimisation, and SMAA requires tens of thousands of Monte Carlo runs. The author maintains
the software alone and already builds Python/Qt desktop software (Financial Architect).

## Options considered
1. **Web application (TypeScript + React), engine in the browser.** Shareable link, no install;
   but a second language to maintain, weaker optimisation solvers, and a separate Python copy
   of the engine would be needed for thesis validation.
2. **Desktop application (Python + PySide6).** Mature scientific stack (NumPy, pandas, SciPy,
   OR-Tools/HiGHS), one engine shared by the app and the thesis notebooks, data stays on the
   user's machine; costs: installers, unsigned-app warnings, no instant demo link.

## Decision
Option 2, built engine-first: the calculation engine is a pure Python package with no
interface code, so a different front end can be added later without rewriting it.

## Consequences
- Thesis results (chapter 7) are produced by the same code that runs inside the app.
- Demo access is provided through GitHub Releases installers, screenshots and a short video.
- Code signing is deferred until after the thesis.
