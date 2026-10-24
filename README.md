# Πλοηγός Απανθρακοποίησης · Decarbonisation Navigator

**EL** · Λογισμικό πολυκριτηριακής αξιολόγησης επενδύσεων απανθρακοποίησης πλοίων υπό το IMO
Net-Zero Framework, το EU ETS και τον FuelEU Maritime. Αναπτύσσεται παράλληλα με πτυχιακή εργασία
στο Πανεπιστήμιο Δυτικής Αττικής.

**EN** · Desktop software for the multi-criteria evaluation of ship decarbonisation investments
under the IMO Net-Zero Framework, the EU ETS and FuelEU Maritime. Developed alongside an
undergraduate thesis at the University of West Attica.

> Under development · private · © 2026 Christos Katsampas. See `LICENSE`.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Foundation, engine skeleton, EU ETS cost engine, bilingual shell, CI | in progress |
| 1 | FuelEU Maritime, IMO NZF scenarios, CII, EU MRV ship database | planned |
| 2 | Ship-type library and real ships by IMO number | planned |
| 3 | Technology & fuel library with sourced ranges | planned |
| 4 | Weighting (BWM, AHP, entropy, CRITIC), ranking (SAW, TOPSIS, PROMETHEE II, VIKOR), SMAA-2 | planned |
| 5 | Bundles and timing (mixed-integer optimisation), fleets, FuelEU pooling, group decisions, reports | planned |

## Architecture

```
navigator/
  engine/       calculations only, no interface code; importable from notebooks
    regulation/ EU ETS (done), FuelEU, IMO NZF, CII
  config/       regulation parameters as JSON, each value with its source and check date
  i18n/         el.json / en.json text catalogues (live language switch)
  ui/           PySide6 interface: theme, shell, pages
docs/decisions/ one note per design decision (feeds thesis chapter 6)
tests/          pytest; the engine is tested against worked examples
```

The engine never imports the interface, so every number in the thesis can be produced by the
same code from a notebook:

```python
from navigator.engine.regulation import eu_ets
```

## Run from source

```
python -m pip install -e ".[dev]"
python -m navigator
python -m pytest
```

## Builds

Every push to `main` runs the tests. Pushing a version tag (for example `v0.1.0`) builds the
Windows and macOS programs and attaches them to a GitHub Release.
