# 0006 · Guided interface: lobby, six-step route, nautical-chart identity

- **Date:** 2026-10-25
- **Status:** accepted (replaces the sidebar-of-tools layout of v0.1.0)

## Context
v0.1.0 reused Financial Architect's pattern: a sidebar of tools with every input visible at
once. That suits an expert's desk tool, but an entry-level user cannot tell what to fill in,
in which order, to reach a decision. The tool supports one decision process, so the interface
should follow that process.

## Decision
- **Lobby** as the home screen: the user's projects as cards (ship, progress, carbon cost to
  2050 without action), a "New project" action, opening a project file, and the EU MRV data
  status with a link to update it.
- **A project is a route of six steps**, drawn as a voyage line with waypoints: Ship → Today's
  position → Options → Priorities → Decision → Report. Each step is one page with one question.
  Steps unlock in order the first time; afterwards any reached step can be revisited and later
  results update automatically ("guided, revisitable").
- **Simple by default, depth on demand.** Each step asks only the essential choices (e.g. carbon
  price Low/Central/High, NZF outcome, ship capacity for CII). Every detailed input and result
  stays available under one "Advanced" fold; estimates keep their "Read more" notes.
- **Projects library + file export.** Projects save automatically (one JSON file each in the
  user's data folder) and can be exported/imported as `.dnproj` files to share.
- **Visual identity "nautical chart":** warm chart-paper background, navy ink, sea-teal accent,
  soft depth contours and a compass rose in the lobby; "night bridge" as the dark theme. The
  regime colours stay fixed across charts. A fuller bridge-console visual treatment is left for
  the final design pass.

## Consequences
- Only the interface layer changed; the engine, data and their tests are untouched.
- Steps 3–6 show what they will do until their phases are built, so the route is visible from
  the start.
- Interface tests now follow a user's path: lobby → new project → choose ship → position →
  save → reopen.
