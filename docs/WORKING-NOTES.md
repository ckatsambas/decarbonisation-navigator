# Working notes for this repository

Thesis software: multi-criteria evaluation of ship decarbonisation investments under the
IMO Net-Zero Framework, EU ETS and FuelEU Maritime. Author: Christos Katsampas (UNIWA).
The thesis is written in Greek; the software is bilingual (Greek default, English).

## Conventions
- Python 3.12+, PySide6. `navigator/engine` must never import from `navigator/ui` or Qt.
- Every regulatory number lives in `navigator/config/**.json` with a `source` id and a
  `checked` date. Unverified values carry `"status": "verify"` and the UI flags them.
- All user-facing text goes through `navigator.i18n.tr("key")`; add keys to BOTH
  `i18n/el.json` and `i18n/en.json` (a test enforces parity).
- Greek capitals are written without accents (use `ui.theme.upper`).
- Code, identifiers, comments and commit messages are in English.
- Record each significant design choice as a new note in `docs/decisions/`.
- Workflow: commit directly to `main`. Use a branch + PR only when a feature is an
  experiment or goes beyond what was asked, so the author can choose.
- Run `python -m pytest` before every push.
