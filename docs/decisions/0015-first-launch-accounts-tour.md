# 0015 — First launch: local accounts, preferences, guided tour

Date: 27 October 2026. Status: implemented (v0.1.7).

## Context
The author asked for a first-launch sequence in the spirit of a Windows first-time setup:
(1) sign in, with "continue as guest" and a terms checkbox, as functional as possible;
(2) language and theme, with a note that both can be changed later; (3) a guided tour with short
texts and arrows, a skip button and the chosen language. Later additions: an interface size setting
for different resolutions, and a way to revisit the tour from Help.

## Decisions
1. **Local accounts, no server** (`navigator/data/accounts.py`, pure Python like the engine).
   Thesis software has no back end, and project data are commercially sensitive, so nothing leaves the
   computer. Passwords and recovery codes are stored only as scrypt hashes (n = 2^14, r = 8, p = 1,
   16-byte salt; `hmac.compare_digest`). A recovery code (XXXX-XXXX-XXXX, no look-alike characters) is
   shown once at sign-up and is the only way to reset a forgotten password; using it issues a new one.
   Five wrong passwords lock the account for 30 s, doubling each time. "Keep me signed in" lasts 30
   days. Each account has its own projects folder and preferences. The first account takes over the
   projects made before accounts existed. Accounts protect against mixing up work on a shared PC; they
   are not encryption of the project files, and the terms say so.
2. **Guest**: works in a separate folder that is emptied when a new guest session starts. Guests must
   also accept the terms.
3. **Terms v1.0** (`i18n/terms_el.md`, `terms_en.md`): research software, no warranty, results are
   estimates, data stay local, EU MRV data are EMSA's. Raising `TERMS_VERSION` asks every user to
   accept again at the next sign-in. The wording is a draft for the author (and supervisor) to review.
4. **Three pages** (`ui/welcome.py`): an animated ocean background (contours, plankton, compass) and a
   route whose ship sails to the next waypoint on each page, slide and fade transitions, the same
   colours and type as the application. Language and theme apply at once on page 2.
5. **Interface size** 90–150 %, applied through `QT_SCALE_FACTOR` before `QApplication` starts, so
   every widget, font and chart scales consistently. Qt cannot change it while running, so it takes
   effect on restart (offered at once from the account menu). Stored in QSettings, not per account,
   because it belongs to the screen.
6. **The tour runs on the real application** (`ui/tour.py`) over a sample project that is deleted at
   the end: a veil with a moving cut-out around each element, a pulsing ring, an arrow drawn towards
   it, 21 short steps through all six steps of the analysis. Keyboard (←/→/Esc), skip at any point,
   and it follows the language. It can be replayed from the new Help "?" menu (also: terms, about)
   and from the account menu.

## Alternatives rejected
- Online accounts (e.g. a hosted identity service): needs a server, a privacy policy for real personal
  data and network access in university labs; no benefit for a single-user desktop tool.
- A tour made of static screenshots: goes stale with every layout change; the overlay points at the
  live widgets instead.
- Zoom inside the app with a stylesheet font scale: charts and fixed sizes would not follow.
