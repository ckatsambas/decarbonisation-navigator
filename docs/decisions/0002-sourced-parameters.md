# 0002 · Regulatory parameters as sourced, editable data

- **Date:** 2026-10-24
- **Status:** accepted

## Context
The three regimes change often. The IMO Net-Zero Framework is due for an adoption decision on
4 December 2026 and may be revised; EU ETS and FuelEU are reviewed periodically. A thesis
also has to show where every number comes from.

## Decision
Every regulatory parameter is stored in `navigator/config/regulation/*.json`, never in code.
Each file lists its sources (title, URL, date checked) and each value points to a source id.
Values that could not be confirmed against a primary source carry `"status": "verify"`;
the interface shows them with a warning marker.

A user may keep a personal override file (as in Financial Architect), so a rule change never
requires a new build.

## Consequences
- Updating a regulation is an edit to one file, and the change is visible in the Git history.
- The thesis can cite the source list directly (chapter 2 and the methodology chapter).
- Tests check that every value has a source and that unverified values are flagged.
