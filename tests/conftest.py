"""Shared fixtures: small synthetic EMSA files in both layouts (the real files are not in Git)."""
import openpyxl
import pytest

OLD_HEAD = ["IMO Number", "Name", "Ship type", "Reporting Period", "Technical efficiency", "Port of Registry",
            "Home Port", "Ice Class", "DoC issue date", "DoC expiry date", "Verifier Name", "Verifier Country",
            "A", "B", "C", "D", "D", "Total fuel consumption [m tonnes]", "Total CO₂ emissions [m tonnes]",
            "CO₂ emissions from all voyages between ports under a MS jurisdiction [m tonnes]",
            "CO₂ emissions from all voyages which departed from ports under a MS jurisdiction [m tonnes]",
            "CO₂ emissions from all voyages to ports under a MS jurisdiction [m tonnes]",
            "CO₂ emissions which occurred within ports under a MS jurisdiction at berth [m tonnes]",
            "Annual Time spent at sea [hours]", "Annual average CO₂ emissions per distance [kg CO₂ / n mile]",
            "Through ice [n miles]"]
OLD_GROUPS = (["Ship"] + [""] * 7 + ["DoC", "", "Verifier", "", "Monitoring methods"] + [""] * 4
              + ["Annual monitoring results"] + [""] * 7 + ["Voluntary reporting"])


def _gas_cols(g: str) -> list[str]:
    return [f"Total {g} emissions [m tonnes]",
            f"{g} emissions from all voyages between ports under a MS jurisdiction [m tonnes]",
            f"{g} emissions from all voyages which departed from ports under a MS jurisdiction [m tonnes]",
            f"{g} emissions from all voyages to ports under a MS jurisdiction [m tonnes]",
            f"{g} emissions which occurred within ports under a MS jurisdiction at berth [m tonnes]",
            f"{g} emissions which occurred within ports under a MS jurisdiction [m tonnes]",
            f"{g} emissions to be reported under Directive 2003/87/EC [m tonnes]"]


NEW_HEAD = (["IMO Number", "Name", "Ship type", "Reporting Period", "Technical efficiency", "Port of Registry",
             "Home Port", "Ice Class", "IMO Number", "Name", "DoC issue date", "DoC expiry date",
             "Total fuel consumption [m tonnes]"]
            + _gas_cols("CO₂") + _gas_cols("CH₄") + _gas_cols("N₂O") + _gas_cols("CO₂eq")
            + ["Time spent at sea [hours]", "CO₂ emissions per distance [kg CO₂ / n mile]"])
NEW_GROUPS = ["Ship"] + [""] * 7 + ["Company", "", "DoC", "", "Annual monitoring results"] + [""] * (len(NEW_HEAD) - 13)
NEW_SUB = [""] * 12 + ["Fuel consumption"] + ["CO₂ Emissions"] + [""] * (len(NEW_HEAD) - 14)


def _write(path, sheets: dict[str, list[list]]):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(path)


def _new_row(imo, name, period, co2, intra, frm, to, berth, port, ets, ch4=0.1, n2o=0.2, company="ACME"):
    def gas(scale):
        return [co2 * scale, intra * scale, frm * scale, to * scale, berth * scale, port * scale, ets * scale]
    eq = [a + 28 * b + 265 * c for a, b, c in zip(gas(1), gas(ch4 / co2), gas(n2o / co2), strict=True)]
    return ([imo, name, "Ro-pax ship", period, "EEXI (12.5 gCO₂/t·nm)", "Piraeus", "", "IA", "1234567", company,
             "01/03/2026", "30/06/2027", co2 / 3.15] + gas(1) + gas(ch4 / co2) + gas(n2o / co2) + eq
            + [1000, co2 * 1000 / 5000])


@pytest.fixture
def mrv_files(tmp_path):
    old = tmp_path / "2023-v92-29092026-EU MRV Publication of information.xlsx"
    _write(old, {"2023": [OLD_GROUPS, [], OLD_HEAD,
                          ["9000001", "OLD NAME", "Ro-pax ship", 2023, "EIV (20.1 gCO₂/t·nm)", "Piraeus", "", "IA",
                           "01/02/2024", "30/06/2025", "V", "GR", "Yes", "", "Yes", "", "", 3000, 9450, 4000, 2000,
                           3000, 450, 5000, 1890, 0],
                          ["9000002", "DIVZERO", "Bulk carrier", 2023, "Not Applicable", "", "", "", "", "", "", "",
                           "", "", "", "", "", 100, 315, 0, 315, 0, 0, 10, "Division by zero!", 0]]})
    new = tmp_path / "2025-v72-24102026-EU MRV Publication of information.xlsx"
    full = [NEW_GROUPS, NEW_SUB, NEW_HEAD,
            _new_row("9000001", "NEW NAME", 2025, 10_000, 4000, 2000, 3000, 900, 1000, 8500)]
    partial = [NEW_GROUPS, NEW_SUB, NEW_HEAD,
               _new_row("9000003", "SPLIT", "2025 (1/1 - 30/6)", 1000, 0, 500, 500, 0, 0, 500, company="FIRST"),
               _new_row("9000003", "SPLIT", "2025 (1/7 - 31/12)", 3000, 0, 1500, 1500, 0, 0, 1500, company="SECOND")]
    _write(new, {"2025 Full ERs": full, "2025 Partial ERs": partial})
    return [old, new]




@pytest.fixture
def mrv_db_path(mrv_files, tmp_path):
    from navigator.data import mrv
    path = tmp_path / "mrv.sqlite"
    mrv.import_files(mrv_files, path)
    return path
