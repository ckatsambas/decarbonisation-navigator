"""EU MRV public emission reports (EMSA THETIS-MRV) → local SQLite database.

The yearly spreadsheets come in two layouts:
- 2018–2023: one sheet, 62 columns, CO2 only.
- 2024 onward: "Full ERs" and "Partial ERs" sheets, 113 columns, with CH4, N2O, CO2eq, the
  emissions to be reported under the EU ETS, and the ship's company.
Columns are matched by their header text (not position), so a reordered or extended file still
imports. Partial reports (a ship that changed company during the year) are kept as separate rows
and combined when a ship's year is read.

Usage from the command line:
    python -m navigator.data.mrv build <folder-with-xlsx> [--db path/to/mrv.sqlite]
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sqlite3
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..engine.models import AnnualEmissions, ScopeSplit, Ship, ShipCategory

SCHEMA_VERSION = 1
FILE_RE = re.compile(r"(?P<year>\d{4})-v(?P<version>\d+)-(?P<gen>\d{8})")

# ----------------------------------------------------------------------- column matching
_GROUPS = {"ship": "ship", "company": "company", "doc": "doc", "verifier": "verifier",
           "monitoring methods": "methods", "annual monitoring results": "results",
           "voluntary reporting": "voluntary"}

TEXT_FIELDS = ["name", "ship_type", "company_imo", "company_name", "port_of_registry", "home_port",
               "ice_class", "tech_eff_type", "doc_issue", "doc_expiry", "verifier_name",
               "verifier_country", "methods"]

_GASES = {"co2": "co2", "ch4": "ch4", "n2o": "n2o", "co2eq": "co2eq"}
_SCOPES = {
    "total {g} emissions": "{g}_total",
    "{g} emissions from all voyages between ports under a ms jurisdiction": "{g}_intra",
    "{g} emissions from all voyages which departed from ports under a ms jurisdiction": "{g}_from",
    "{g} emissions from all voyages to ports under a ms jurisdiction": "{g}_to",
    "{g} emissions which occurred within ports under a ms jurisdiction at berth": "{g}_berth",
    "{g} emissions which occurred within ports under a ms jurisdiction": "{g}_port",
    "{g} emissions assigned to on laden": "{g}_laden",
    "{g} emissions to be reported under directive 2003/87/ec": "{g}_ets",
}

RESULT_COLUMNS: dict[str, str] = {
    "total fuel consumption": "fuel_total",
    "fuel consumptions assigned to on laden": "fuel_laden",
    "fuel consumptions assigned to cargo heating": "fuel_cargo_heating",
    "fuel consumptions assigned to dynamic positioning": "fuel_dp",
    "co2eq emissions benefitting from a derogation in accordance with part c, point 1.2, of annex ii "
    "to regulation (eu) 2015/757 (voluntary)": "co2eq_derogation",
    "time spent at sea": "time_at_sea",
    "distance through ice": "distance_ice",
    "fuel consumption per distance": "fuel_per_nm",
    "co2 emissions per distance": "co2_per_nm",
    "co2 emissions per transport work (mass)": "co2_per_tw_mass",
    "co2 emissions per transport work (volume)": "co2_per_tw_volume",
    "co2 emissions per transport work (dwt)": "co2_per_tw_dwt",
    "co2 emissions per transport work (pax)": "co2_per_tw_pax",
    "co2 emissions per transport work (freight)": "co2_per_tw_freight",
    "average density of the cargo transported": "cargo_density",
}
for _pat, _out in _SCOPES.items():
    for _g in _GASES:
        RESULT_COLUMNS[_pat.format(g=_g)] = _out.format(g=_g)

NUMERIC_FIELDS = sorted(set(RESULT_COLUMNS.values())) + ["tech_eff_value", "distance_nm"]
# Quantities that add up when a year is split over several partial reports
ADDITIVE = [f for f in NUMERIC_FIELDS
            if f.startswith(("fuel_total", "fuel_laden", "fuel_cargo", "fuel_dp", "time_at_sea", "distance"))
            or re.match(r"(co2|ch4|n2o|co2eq)_(total|intra|from|to|berth|port|laden|ets|derogation)$", f)]

_SUB = str.maketrans("₂₄₀₁₃", "24013")


def _norm(text: object) -> str:
    s = str(text or "").translate(_SUB).lower()
    s = re.sub(r"\[.*?\]", "", s)          # drop units
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^annual average ", "", s)  # 2018–2023 wording
    s = re.sub(r"^annual time spent at sea$", "time spent at sea", s)
    return s


def map_columns(group_row: Sequence, name_row: Sequence) -> dict[int, str]:
    """Column index → canonical field name, using the merged group header above each column."""
    out: dict[int, str] = {}
    group = ""
    methods = 0
    for i, (g, n) in enumerate(zip(group_row, name_row, strict=False)):
        if isinstance(g, str) and g.strip():
            group = _GROUPS.get(_norm(g), _norm(g))
        name = _norm(n)
        if not name:
            continue
        key = None
        if group == "ship":
            key = {"imo number": "imo", "name": "name", "ship type": "ship_type", "reporting period": "period",
                   "technical efficiency": "tech_eff", "port of registry": "port_of_registry",
                   "home port": "home_port", "ice class": "ice_class"}.get(name)
        elif group == "company":
            key = {"imo number": "company_imo", "name": "company_name"}.get(name)
        elif group == "doc":
            key = {"doc issue date": "doc_issue", "doc expiry date": "doc_expiry"}.get(name)
        elif group == "verifier":
            key = {"verifier name": "verifier_name", "verifier country": "verifier_country"}.get(name)
        elif group == "methods":
            key = f"method_{methods}_{name}"
            methods += 1
        elif group == "results":
            key = RESULT_COLUMNS.get(name)
        if key:
            out[i] = key
    return out


# ----------------------------------------------------------------------- value parsing
def _num(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None                       # "Division by zero!", "N/A", ...


def _text(v: object) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s or None


_TECH = re.compile(r"^\s*(?P<type>[A-Za-z]+)\s*\((?P<val>[-\d.]+)")


def parse_tech_efficiency(v: object) -> tuple[str | None, float | None]:
    """'EEDI (4.12 gCO₂/t·nm)' → ('EEDI', 4.12); 'Not Applicable' → (None, None)."""
    m = _TECH.match(str(v or ""))
    return (m.group("type").upper(), float(m.group("val"))) if m else (None, None)


_PERIOD = re.compile(r"^\s*(?P<y>\d{4})\s*(?:\((?P<d1>\d{1,2})/(?P<m1>\d{1,2})\s*-\s*(?P<d2>\d{1,2})/(?P<m2>\d{1,2})\))?")


def parse_period(v: object) -> tuple[int, date, date, bool]:
    """2018 → (2018, 1 Jan, 31 Dec, full); '2025 (1/1 - 11/8)' → (2025, 1 Jan, 11 Aug, partial)."""
    s = _text(v) or ""
    m = _PERIOD.match(s)
    if not m:
        raise ValueError(f"Unrecognised reporting period: {v!r}")
    y = int(m.group("y"))
    if m.group("d1"):
        return (y, date(y, int(m.group("m1")), int(m.group("d1"))),
                date(y, int(m.group("m2")), int(m.group("d2"))), True)
    return y, date(y, 1, 1), date(y, 12, 31), False


def parse_release(path: Path) -> tuple[int | None, int | None, str | None]:
    """'2024-v253-23102026-EU MRV ...xlsx' → (2024, 253, '2026-10-23')."""
    m = FILE_RE.search(path.name)
    if not m:
        return None, None, None
    g = m.group("gen")
    return int(m.group("year")), int(m.group("version")), f"{g[4:]}-{g[2:4]}-{g[:2]}"


# ----------------------------------------------------------------------- reading files
def _read_sheets(path: Path) -> dict[str, list[list]]:
    """All sheets as lists of rows. Uses the fast Rust reader when installed, else openpyxl."""
    try:
        from python_calamine import CalamineWorkbook
        wb = CalamineWorkbook.from_path(str(path))
        return {name: wb.get_sheet_by_name(name).to_python(skip_empty_area=False) for name in wb.sheet_names}
    except ImportError:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def _header_index(rows: list[list]) -> int:
    for i, r in enumerate(rows[:15]):
        if r and _norm(r[0]) == "imo number":
            return i
    raise ValueError("Header row with 'IMO Number' not found")


def parse_sheet(rows: list[list]) -> list[dict]:
    h = _header_index(rows)
    # Main group labels ("Ship", "Annual monitoring results", ...) are on the row above the header that
    # starts with "Ship". Since 2024 a second row holds sub-groups ("CO₂ Emissions", ...), ignored here.
    top = next((i for i in range(h) if rows[i] and _norm(rows[i][0]) == "ship"), None)
    group_row = rows[top] if top is not None else [""] * len(rows[h])
    cols = map_columns(group_row, rows[h])
    out = []
    for r in rows[h + 1:]:
        rec: dict = {}
        for i, key in cols.items():
            rec[key] = r[i] if i < len(r) else None
        imo = _text(rec.get("imo"))
        if not imo or rec.get("period") in (None, ""):
            continue
        year, start, end, partial = parse_period(rec["period"])
        tt, tv = parse_tech_efficiency(rec.get("tech_eff"))
        row = {"imo": imo, "year": year, "partial": int(partial), "period_start": start.isoformat(),
               "period_end": end.isoformat(), "tech_eff_type": tt, "tech_eff_value": tv}
        for f in TEXT_FIELDS:
            if f not in row and f in rec:
                row[f] = _text(rec[f])
        letters = [k.split("_", 2)[2].upper() for k in rec if k.startswith("method_")
                   and str(rec[k]).strip().lower() == "yes"]
        row["methods"] = ",".join(dict.fromkeys(letters)) or None
        for f in set(RESULT_COLUMNS.values()):
            if f in rec:
                row[f] = _num(rec[f])
        co2, per_nm = row.get("co2_total"), row.get("co2_per_nm")
        row["distance_nm"] = co2 * 1000 / per_nm if co2 and per_nm else None
        out.append(row)
    return out


# ----------------------------------------------------------------------- database
def default_db_path() -> Path:
    env = os.environ.get("NAVIGATOR_MRV_DB")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "DecarbonisationNavigator" / "mrv.sqlite"


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cols = ", ".join([f"{f} TEXT" for f in TEXT_FIELDS] + [f"{f} REAL" for f in NUMERIC_FIELDS])
    con.executescript(f"""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS releases (
            year INTEGER PRIMARY KEY, version INTEGER, generated TEXT, file TEXT,
            imported_at TEXT, n_full INTEGER, n_partial INTEGER);
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY, imo TEXT NOT NULL, year INTEGER NOT NULL, partial INTEGER NOT NULL,
            period_start TEXT, period_end TEXT, {cols});
        CREATE INDEX IF NOT EXISTS ix_reports_imo_year ON reports(imo, year);
        CREATE TABLE IF NOT EXISTS ships (
            imo TEXT PRIMARY KEY, name TEXT, ship_type TEXT, company_name TEXT,
            first_year INTEGER, last_year INTEGER, search TEXT);
    """)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
    return con


def _rebuild_ships(con: sqlite3.Connection) -> None:
    """One row per ship with its latest identity and every name/company it has had (for search)."""
    con.execute("DELETE FROM ships")
    con.execute("""
        INSERT INTO ships (imo, name, ship_type, company_name, first_year, last_year, search)
        SELECT r.imo, latest.name, latest.ship_type, latest.company_name, MIN(r.year), MAX(r.year),
               LOWER(r.imo || ' ' || GROUP_CONCAT(DISTINCT COALESCE(r.name, '')) || ' ' ||
                     GROUP_CONCAT(DISTINCT COALESCE(r.company_name, '')))
        FROM reports r
        JOIN (SELECT imo, name, ship_type, company_name,
                     ROW_NUMBER() OVER (PARTITION BY imo ORDER BY year DESC, period_end DESC) AS rn
              FROM reports) latest ON latest.imo = r.imo AND latest.rn = 1
        GROUP BY r.imo""")


@dataclass
class ImportResult:
    file: str
    year: int
    version: int | None
    generated: str | None
    n_full: int
    n_partial: int
    skipped: bool = False
    reason: str = ""


def import_files(paths: Iterable[Path], db: Path | None = None, *, force: bool = False,
                 progress: Callable[[int, int, str], None] | None = None) -> list[ImportResult]:
    """Import yearly files; a year already present is replaced only by a newer EMSA version (or force)."""
    db = db or default_db_path()
    paths = sorted(Path(p) for p in paths)
    con = _connect(db)
    results = []
    try:
        for k, path in enumerate(paths):
            if progress:
                progress(k, len(paths), path.name)
            year_f, version, generated = parse_release(path)
            rows: list[dict] = []
            n_partial = 0
            for sheet_rows in _read_sheets(path).values():
                parsed = parse_sheet(sheet_rows) if sheet_rows else []
                n_partial += sum(r["partial"] for r in parsed)
                rows += parsed
            if not rows:
                results.append(ImportResult(path.name, year_f or 0, version, generated, 0, 0, True, "no reports"))
                continue
            year = rows[0]["year"]
            old = con.execute("SELECT version FROM releases WHERE year=?", (year,)).fetchone()
            if old and not force and version is not None and old["version"] is not None and version <= old["version"]:
                results.append(ImportResult(path.name, year, version, generated, 0, 0, True,
                                            f"version {old['version']} already imported"))
                continue
            fields = ["imo", "year", "partial", "period_start", "period_end", *TEXT_FIELDS, *NUMERIC_FIELDS]
            with con:
                con.execute("DELETE FROM reports WHERE year=?", (year,))
                con.executemany(f"INSERT INTO reports ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
                                [[r.get(f) for f in fields] for r in rows])
                con.execute("INSERT OR REPLACE INTO releases VALUES (?,?,?,?,?,?,?)",
                            (year, version, generated, path.name, datetime.now().astimezone().isoformat(timespec="seconds"),
                             len(rows) - n_partial, n_partial))
            results.append(ImportResult(path.name, year, version, generated, len(rows) - n_partial, n_partial))
        with con:
            _rebuild_ships(con)
        if progress:
            progress(len(paths), len(paths), "")
    finally:
        con.close()
    return results


# ----------------------------------------------------------------------- bundled database
RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def bundled_path() -> Path:
    return RESOURCES / "mrv.sqlite.xz"


def _bundle_releases(bundle: Path) -> dict[int, int]:
    manifest = bundle.with_name("mrv_manifest.json")
    if manifest.exists():
        import json
        return {r["year"]: r["version"] or 0 for r in json.loads(manifest.read_text(encoding="utf-8"))["releases"]}
    return {}


def _decompress(bundle: Path, target: Path) -> None:
    import lzma
    tmp = target.with_suffix(".part")
    with lzma.open(bundle) as src, tmp.open("wb") as dst:
        while chunk := src.read(1 << 20):
            dst.write(chunk)
    tmp.replace(target)


def ensure_database(db: Path | None = None, bundle: Path | None = None) -> str:
    """Make sure the user's database exists and holds at least the releases bundled with the app.

    Returns "created" (first run), "updated" (newer bundled years merged in), "current" or "no-bundle".
    Years the user imported in a newer EMSA version than the bundle are left untouched.
    """
    db = db or default_db_path()
    bundle = bundle or bundled_path()
    if not bundle.exists():
        return "no-bundle"
    if not db.exists():
        db.parent.mkdir(parents=True, exist_ok=True)
        _decompress(bundle, db)
        return "created"
    con = _connect(db)
    try:
        have = {y: v or 0 for y, v in con.execute("SELECT year, version FROM releases")}
        wanted = _bundle_releases(bundle)
        if wanted and all(have.get(y, -1) >= v for y, v in wanted.items()):
            return "current"
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bundle.sqlite"
            _decompress(bundle, src)
            con.execute("ATTACH DATABASE ? AS b", (str(src),))
            cols = [r[1] for r in con.execute("PRAGMA table_info(reports)") if r[1] != "id"]
            col_list = ", ".join(cols)
            newer = [(y, v) for y, v in con.execute("SELECT year, version FROM b.releases")
                     if have.get(y, -1) < (v or 0)]
            with con:
                for y, _ in newer:
                    con.execute("DELETE FROM reports WHERE year = ?", (y,))
                    con.execute(f"INSERT INTO reports ({col_list}) SELECT {col_list} FROM b.reports WHERE year = ?", (y,))
                    con.execute("INSERT OR REPLACE INTO releases SELECT * FROM b.releases WHERE year = ?", (y,))
                if newer:
                    _rebuild_ships(con)
            con.execute("DETACH DATABASE b")
        return "updated" if newer else "current"
    finally:
        con.close()


# ----------------------------------------------------------------------- reading the database
PASSENGER_TYPES = {"passenger ship", "ro-pax ship", "passenger ship (cruise passenger ship)"}


def ship_category(ship_type: str | None) -> ShipCategory:
    t = (ship_type or "").lower()
    if t in PASSENGER_TYPES:
        return ShipCategory.PASSENGER
    if "offshore" in t:
        return ShipCategory.OFFSHORE
    if t.startswith("other ship types"):
        return ShipCategory.OTHER
    return ShipCategory.CARGO


@dataclass
class ShipYear:
    """One ship's EU MRV results for one year (partial reports combined)."""
    imo: str
    year: int
    partial: bool
    period_start: str
    period_end: str
    n_reports: int
    values: dict = field(repr=False)

    def __getattr__(self, name):            # r.co2_total, r.name, ...
        try:
            return self.__dict__["values"][name]
        except KeyError as e:
            raise AttributeError(name) from e

    def get(self, name: str, default=None):
        v = self.values.get(name)
        return default if v is None else v

    def _split(self, gas: str) -> ScopeSplit:
        g = lambda k: self.get(f"{gas}_{k}", 0.0)
        # In-port: "within ports" normally includes "at berth", but some companies fill only the berth column.
        return ScopeSplit(intra_eu=g("intra"), in_port=max(g("berth"), g("port")),
                          from_eu=g("from"), to_eu=g("to"), outside=0.0)

    def emissions(self) -> AnnualEmissions:
        """EU-related emissions by gas and voyage category. MRV holds no voyages outside the EU."""
        return AnnualEmissions(co2=self._split("co2"), ch4=self._split("ch4"), n2o=self._split("n2o"))

    @property
    def ets_reported_co2e(self) -> float | None:
        """Emissions EMSA lists as reportable under the EU ETS (2024 onward), t CO2e, all three gases."""
        return self.values.get("co2eq_ets")

    @property
    def ets_reported_co2(self) -> float | None:
        """CO2 only (the gas covered by the ETS in 2024–2025), t."""
        return self.values.get("co2_ets")

    def ets_coverage_ratio(self) -> float | None:
        """EMSA's ETS CO2 ÷ the rule-based covered CO2 for this year (None before 2024 or if undefined)."""
        reported = self.ets_reported_co2
        if reported is None:
            return None
        from ..engine.regulation.eu_ets import EtsRules
        cov = EtsRules.load().coverage
        s = self.emissions().co2
        rule = sum(cov.get(k, 0.0) * getattr(s, k) for k in ("intra_eu", "in_port", "from_eu", "to_eu", "outside"))
        return reported / rule if rule > 0 else None

    def to_ship(self) -> Ship:
        ets = self.ets_reported_co2e
        ratio = self.ets_coverage_ratio()
        if ratio is not None and abs(ratio - 1.0) < 0.001:
            ratio = None                   # the rule reproduces EMSA: nothing to correct
        return Ship(imo=self.imo, name=self.get("name", ""), ship_type=self.get("ship_type", ""),
                    category=ship_category(self.get("ship_type")), gross_tonnage=5000.0,
                    flag=self.get("port_of_registry", ""), ice_class=self.get("ice_class"),
                    ets_scope_override=(ets > 0) if ets is not None else None,
                    ets_coverage_ratio=ratio)


@dataclass(frozen=True)
class ShipSummary:
    imo: str
    name: str
    ship_type: str
    company_name: str | None
    first_year: int
    last_year: int


@dataclass(frozen=True)
class Release:
    year: int
    version: int | None
    generated: str | None
    file: str
    n_full: int
    n_partial: int


def combine(rows: list[dict]) -> ShipYear:
    """Combine the reports of one ship-year; partial reports are summed."""
    rows = sorted(rows, key=lambda r: r["period_end"] or "")
    full = [r for r in rows if not r["partial"]]
    use = full[-1:] if full else rows
    vals = dict(use[-1])
    if len(use) > 1:
        for f in ADDITIVE:
            parts = [r[f] for r in use if r[f] is not None]
            vals[f] = sum(parts) if parts else None
        for f in NUMERIC_FIELDS:
            if f not in ADDITIVE and f != "tech_eff_value":
                vals[f] = None                    # intensities cannot be summed
        if vals.get("co2_total") and vals.get("distance_nm"):
            vals["co2_per_nm"] = vals["co2_total"] * 1000 / vals["distance_nm"]
    return ShipYear(imo=vals["imo"], year=vals["year"], partial=not full,
                    period_start=min(r["period_start"] for r in use), period_end=max(r["period_end"] for r in use),
                    n_reports=len(use), values=vals)


class MrvDatabase:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_db_path()
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row

    @classmethod
    def open_default(cls) -> MrvDatabase | None:
        try:
            return cls()
        except FileNotFoundError:
            return None

    def close(self) -> None:
        self.con.close()

    def releases(self) -> list[Release]:
        return [Release(r["year"], r["version"], r["generated"], r["file"], r["n_full"], r["n_partial"])
                for r in self.con.execute("SELECT * FROM releases ORDER BY year")]

    def ship_types(self) -> list[str]:
        return [r[0] for r in self.con.execute("SELECT DISTINCT ship_type FROM ships WHERE ship_type IS NOT NULL ORDER BY 1")]

    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM ships").fetchone()[0]

    def search(self, text: str = "", ship_type: str | None = None, limit: int = 500) -> list[ShipSummary]:
        """IMO number, any past name or company; every word must match. Exact IMO first."""
        sql, args = "SELECT * FROM ships WHERE 1=1", []
        for word in text.lower().split():
            sql += " AND search LIKE ?"
            args.append(f"%{word}%")
        if ship_type:
            sql += " AND ship_type = ?"
            args.append(ship_type)
        sql += " ORDER BY (imo = ?) DESC, last_year DESC, name LIMIT ?"
        args += [text.strip(), limit]
        return [ShipSummary(r["imo"], r["name"] or "", r["ship_type"] or "", r["company_name"], r["first_year"],
                            r["last_year"]) for r in self.con.execute(sql, args)]

    def history(self, imo: str) -> list[ShipYear]:
        rows = [dict(r) for r in self.con.execute("SELECT * FROM reports WHERE imo=? ORDER BY year, period_end", (imo,))]
        by_year: dict[int, list[dict]] = {}
        for r in rows:
            by_year.setdefault(r["year"], []).append(r)
        return [combine(v) for _, v in sorted(by_year.items())]

    def latest(self, imo: str, full_year_only: bool = True) -> ShipYear | None:
        hist = self.history(imo)
        if full_year_only and any(not h.partial for h in hist):
            hist = [h for h in hist if not h.partial]
        return hist[-1] if hist else None


# ----------------------------------------------------------------------- command line
def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m navigator.data.mrv")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="import EMSA yearly .xlsx files")
    b.add_argument("folder", type=Path)
    b.add_argument("--db", type=Path, default=None)
    b.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    files = sorted(args.folder.glob("*.xlsx"))
    if not files:
        print(f"No .xlsx files in {args.folder}", file=sys.stderr)
        return 1
    db = args.db or default_db_path()
    res = import_files(files, db, force=args.force,
                       progress=lambda i, n, f: print(f"[{i + 1}/{n}] {f}", flush=True) if f else None)
    for r in res:
        state = f"skipped ({r.reason})" if r.skipped else f"{r.n_full} full + {r.n_partial} partial reports"
        print(f"{r.year} v{r.version} ({r.generated}): {state}")
    print(f"Database: {db}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
