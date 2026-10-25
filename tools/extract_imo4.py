"""Extract the fleet activity tables of the Fourth IMO GHG Study 2020 (Tables 75–81, 2012–2018).

    python tools/extract_imo4.py "Fourth IMO GHG Study 2020 - Full report and annexes.pdf"

Writes navigator/config/reference/imo4_fleet.json: per ship type and size class, per year, the
averages the study reports (DWT, main engine power, design speed, days at sea, speed, distance,
AER, main/aux/boiler fuel, CO2). Needs `pdftotext` (poppler) on the PATH.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "navigator" / "config" / "reference" / "imo4_fleet.json"

# Ship types and size classes in the order the study prints them
LAYOUT = [
    ("bulk", "Bulk carrier", "dwt", ["0-9999", "10000-34999", "35000-59999", "60000-99999", "100000-199999", "200000-+"]),
    ("chemical", "Chemical tanker", "dwt", ["0-4999", "5000-9999", "10000-19999", "20000-39999", "40000-+"]),
    ("container", "Container", "teu", ["0-999", "1000-1999", "2000-2999", "3000-4999", "5000-7999", "8000-11999",
                                        "12000-14499", "14500-19999", "20000-+"]),
    ("general_cargo", "General cargo", "dwt", ["0-4999", "5000-9999", "10000-19999", "20000-+"]),
    ("gas", "Liquefied gas tanker", "cbm", ["0-49999", "50000-99999", "100000-199999", "200000-+"]),
    ("oil", "Oil tanker", "dwt", ["0-4999", "5000-9999", "10000-19999", "20000-59999", "60000-79999", "80000-119999",
                                  "120000-199999", "200000-+"]),
    ("other_liquids", "Other liquids tankers", "dwt", ["0-999", "1000-+"]),
    ("ferry_pax", "Ferry-pax only", "gt", ["0-299", "300-999", "1000-1999", "2000-+"]),
    ("cruise", "Cruise", "gt", ["0-1999", "2000-9999", "10000-59999", "60000-99999", "100000-149999", "150000-+"]),
    ("ropax", "Ferry-RoPax", "gt", ["0-1999", "2000-4999", "5000-9999", "10000-19999", "20000-+"]),
    ("reefer", "Refrigerated bulk", "dwt", ["0-1999", "2000-5999", "6000-9999", "10000-+"]),
    ("roro", "Ro-Ro", "dwt", ["0-4999", "5000-9999", "10000-14999", "15000-+"]),
    ("vehicle", "Vehicle", "gt", ["0-29999", "30000-49999", "50000-+"]),
    ("yacht", "Yacht", "gt", ["0-+"]),
    ("tug", "Service - tug", "gt", ["0-+"]),
    ("fishing", "Miscellaneous - fishing", "gt", ["0-+"]),
    ("offshore", "Offshore", "gt", ["0-+"]),
    ("service_other", "Service - other", "gt", ["0-+"]),
    ("misc_other", "Miscellaneous - other", "gt", ["0-+"]),
]
FIELDS = ["n_type12", "n_type3", "n_type4", "dwt", "power_kw", "design_speed", "days_at_sea", "days_international",
          "days_seca", "speed_at_sea", "distance_nm", "aer", "fuel_main_kt", "fuel_aux_kt", "fuel_boiler_kt",
          "ghg_mt", "co2_mt"]
NUM = re.compile(r"\d[\d,]*\.?\d*")
TABLES = {75: 2012, 76: 2013, 77: 2014, 78: 2015, 79: 2016, 80: 2017, 81: 2018}


def text_of(pdf: Path) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True, text=True)
    return out.stdout.splitlines()


DATA = re.compile(r"(?:(?P<size>\d+-(?:\d+|\+)?)\s*†?\s+)?(?P<unit>dwt|teu|cbm|gt)\s+(?P<nums>[\d,.\s]+?)\s*$")


def parse_table(lines: list[str]) -> list[dict]:
    """Rows are read in print order. The PDF sometimes wraps a size label away from its data line
    ("120000-" … "199999"); such rows take the next expected size class of the same unit. A class with
    no ships in a year is absent from the table; a printed size label lets the parser skip over it."""
    expected = [(t, label, unit, s) for t, label, unit, sizes in LAYOUT for s in sizes]
    rows, k = [], 0
    for line in lines:
        if k >= len(expected):
            break
        m = DATA.search(line)
        if not m:
            continue
        nums = [float(x.replace(",", "")) for x in NUM.findall(m.group("nums"))]
        if len(nums) < len(FIELDS):
            continue
        size, unit = m.group("size"), m.group("unit")
        if size and not size.endswith("-"):
            j = next((j for j in range(k, min(k + 3, len(expected)))
                      if expected[j][3] == size and expected[j][2] == unit), None)
            if j is None:
                raise ValueError(f"Expected {expected[k][1]} {expected[k][3]}, found {size}: {line.strip()}")
            k = j
        elif expected[k][2] != unit:
            raise ValueError(f"Unit mismatch at {expected[k][1]} {expected[k][3]}: {line.strip()}")
        t, label, u, sz = expected[k]
        rows.append({"type": t, "label": label, "unit": u, "size": sz,
                     **dict(zip(FIELDS, nums[:len(FIELDS)], strict=True))})
        k += 1
    if len(rows) < len(expected) - 3:
        raise ValueError(f"Parsed only {len(rows)} of {len(expected)} rows")
    # within each type, average DWT must rise with the size class: a check on the row assignment
    for t, _, _, _sizes in LAYOUT:
        dw = [r["dwt"] for r in rows if r["type"] == t]
        if any(b < a * 0.8 for a, b in zip(dw, dw[1:], strict=False)) and t not in ("ferry_pax", "cruise", "ropax"):
            raise ValueError(f"DWT not increasing for {t}: {dw}")
    return rows


T92 = re.compile(r"^\s*\d+\s+\d+\s+(?P<label>[A-Za-z][A-Za-z \-]+?)\s+(?P<size>\d+-(?:\d+|\+)?)\s+(?P<unit>dwt|teu|cbm|gt)"
                 r"\s+(?P<n>\d+)\s+(?P<mrv>[\d.]+)\s+(?P<imo>[\d.]+)\s+(?P<pct>-?\d+)%")


def parse_table92(lines: list[str]) -> list[dict]:
    """Table 92: EU MRV ships matched in the study, 2018, by type and size (count, CO2 MRV vs IMO4)."""
    start = max(i for i, ln in enumerate(lines) if "Table 92 – MRV summary statistics per vessel type and size" in ln)
    labels = {label: t for t, label, _, _ in LAYOUT}
    labels["Other liquids"] = "other_liquids"
    out = []
    for ln in lines[start:start + 150]:
        m = T92.match(ln)
        if m:
            out.append({"type": labels.get(m.group("label").strip(), m.group("label").strip()), "size": m.group("size"),
                        "unit": m.group("unit"), "vessels": int(m.group("n")), "co2_mrv_t": float(m.group("mrv")),
                        "co2_imo4_t": float(m.group("imo"))})
    return out


def main(pdf: Path) -> None:
    lines = text_of(pdf)
    starts = {}
    for i, ln in enumerate(lines):
        m = re.search(r"Table (\d+) – Detailed results for (\d{4}) describing the fleet", ln)
        if m and int(m.group(1)) in TABLES:
            starts[int(m.group(1))] = i          # last occurrence = the table itself, not the list of tables
    years = {}
    for t, year in TABLES.items():
        i = starts[t]
        nxt = min([s for s in starts.values() if s > i] + [i + 400])
        try:
            years[year] = parse_table(lines[i:nxt])
        except ValueError as e:
            raise ValueError(f"{year}: {e}") from e
    classes = {}
    for year, rows in years.items():
        missing = {f"{t}:{sz}" for t, _, _, sizes in LAYOUT for sz in sizes} - {f"{r['type']}:{r['size']}" for r in rows}
        if missing:
            print(year, "no ships in:", sorted(missing))
        for r in rows:
            key = f"{r['type']}:{r['size']}"
            c = classes.setdefault(key, {"type": r["type"], "label": r["label"], "unit": r["unit"], "size": r["size"],
                                         "years": {}})
            c["years"][str(year)] = {f: r[f] for f in FIELDS}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = {"source": {"title": "Fourth IMO GHG Study 2020, Annex: Tables 75–81, detailed results 2012–2018 describing "
                                "the fleet (international, domestic and fishing), bottom-up method",
                      "url": "https://www.imo.org/en/ourwork/Environment/Pages/Fourth-IMO-Greenhouse-Gas-Study-2020.aspx",
                      "publisher": "International Maritime Organization, 2021"},
           "fields": FIELDS, "classes": list(classes.values()),
           "mrv_2018": {"source": "Fourth IMO GHG Study 2020, Annex: Table 92, MRV summary statistics per vessel type "
                                  "and size (2018, EU MRV ships matched to the study's fleet)",
                        "rows": parse_table92(lines)}}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(classes)} classes × {len(years)} years -> {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
