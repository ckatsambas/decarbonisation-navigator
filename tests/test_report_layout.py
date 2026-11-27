"""The PDF report keeps its layout with long texts and many rows: nothing off the page, nothing on top of
something else, no squeezed tables and no cell text spilling out (decision 0014-5)."""
import numpy as np
import pytest

from navigator.report import pdf as P
from navigator.report.data import ReportData, Table
from navigator.report.layout_check import check_figure

LONG = "Μετατροπή σε δίπλο καύσιμο αμμωνίας με αναβάθμιση συστήματος αποθήκευσης και εκπαίδευση πληρώματος"
LABELS = {k: k.capitalize() for k in ("summary", "settings", "position", "position_chart", "measures", "plans",
                                      "adaptive", "weights", "ranking", "smaa", "assumptions", "sources", "page",
                                      "axis_cut", "axis_npv", "company", "entropy", "critic", "legend_ets",
                                      "legend_fueleu", "legend_nzf", "continued")}
LABELS["rank_short"] = "{r}η"
LABELS["smaa_top"] = "Δείχνονται οι {n} από τις {total} επιλογές με την καλύτερη αναμενόμενη θέση."


def stress(lang: str, n_alt: int) -> ReportData:
    rng = np.random.default_rng(1)
    names = [f"{LONG[: 20 + 7 * (i % 9)]} {i}" for i in range(n_alt)]
    sentence = ("Με τις προτεραιότητες της εταιρείας η επιλογή που ξεχωρίζει κρατά την πρώτη θέση σε τρεις από "
                "τις τέσσερις μεθόδους, ενώ η ψηφοφορία του IMO και η τιμή του άνθρακα παραμένουν ανοιχτές. ") * 2
    years = list(range(2026, 2051))
    acc = rng.dirichlet(np.ones(n_alt), n_alt)
    measures = Table("m", ["Μέτρο", "Μείωση εκπομπών", "Επένδυση", "Καθαρή παρούσα αξία", "€ / t CO2e"],
                     [[names[i % n_alt], 0.25, 1.2e6, -2.7e7, 241.0] for i in range(30)],
                     ["text", "pct", "eur", "eur", "num"], sentence)
    head = ["Επιλογή", "SAW", "TOPSIS", "PROMETHEE II", "VIKOR", "Συνολικά", "Καθαρή παρούσα αξία"]
    ranking = Table("r", head, [[nm, 1, 2, 3, 4, 5, -1.2e7] for nm in names],
                    ["text", "int", "int", "int", "int", "int", "eur"], sentence + "\n" + sentence)
    adaptive = Table("a", ["Αγορά", "IMO NZF", "Πιθανότητα", "Καθαρή παρούσα αξία", "Αργότερα"],
                     [["Κεντρική αγορά", "Καθυστερεί ένα έτος", 0.167, 2.5e6, "; ".join(names[:4])]] * 9,
                     ["text", "text", "pct", "eur", "text"])
    weights = Table("w", ["Κριτήριο", "Δικά σας", "Εύρος (WAP)", "Εντροπία", "CRITIC"],
                    [[LONG[:30], 0.2, "15,2–21,4%", 0.1, 0.1]] * 9, ["text", "pct", "text", "pct", "pct"])
    assumptions = Table("as", ["Παράμετρος", "Τιμή", "Σημείωση / πηγή"],
                        [[f"imo_nzf.parameter_with_a_long_name_{i}", "low: 0; likely: 640; high: 1000; " * 3,
                          sentence] for i in range(34)], ["text", "text", "text"], sentence)
    return ReportData(
        lang, "Έκθεση απόφασης απανθρακοποίησης", "Πολύ μεγάλο όνομα πλοίου με πολλές λέξεις · Bulk carrier",
        "2026-11-27", "0.1.7", LABELS, [sentence] * 7,
        [("Τιμή άνθρακα ΕΕ με πολύ μεγάλη ετικέτα που δεν χωράει", LONG)] * 10,
        {"years": years, "ets": [2e5] * 25, "fueleu": [1e5] * 25, "nzf": [5e5] * 25, "sentence": sentence,
         "table": Table("p", ["Έτος", "EU ETS", "FuelEU", "IMO NZF", "Σύνολο"],
                        [[y, 2e5, 1e5, 5e5, 8e5] for y in years[::5]], ["int", "eur", "eur", "eur", "eur"])},
        measures,
        {"front": [{"avoided": 8e4 + 1e4 * i, "npv": 2e6 - 9e5 * i, "label": "ΑΒΓΔΕΖΗ"[i]} for i in range(7)],
         "selected": 4, "sentence": sentence, "timeline_title": LONG,
         "timeline": [(names[i % n_alt], 2027 + i % 9, P.SOFT[i % 8]) for i in range(16)], "years": (2026, 2050),
         "adaptive": {"sentence": sentence, "now": sentence, "table": adaptive}},
        {"names": [LONG[:25 + i] for i in range(9)], "company": [0.11] * 9, "entropy": [0.11] * 9,
         "critic": [0.11] * 9, "lo": [0.09] * 9, "hi": [0.13] * 9, "sentence": sentence, "status": sentence,
         "table": weights},
        ranking,
        {"names": names, "acceptability": acc.tolist(), "expected": list(np.linspace(1, n_alt, n_alt)),
         "sentence": sentence,
         "fan": {"title": LONG, "years": years[1:], "paths": rng.normal(0, 1e6, (50, 24)).cumsum(axis=1).tolist(),
                 "shares": "57% των μελλόντων: η επένδυση αποπληρώνεται (ΚΠΑ > 0)\n43% των μελλόντων: κοστίζει"}},
        assumptions,
        [(sentence[:120], "https://www.example.org/" + "very/long/path/" * 12, "2026-10-25")] * 70)


@pytest.mark.parametrize("n_alt", [3, 30])
def test_report_pages_have_no_layout_problems(tmp_path, monkeypatch, n_alt):
    found: list[str] = []
    original = P.Doc.save

    def save(self, fig):
        found.extend(check_figure(fig, f"p.{self.page}"))
        original(self, fig)

    monkeypatch.setattr(P.Doc, "save", save)
    out = P.build_pdf(stress("el", n_alt), tmp_path / "r.pdf")
    assert out.read_bytes()[:4] == b"%PDF"
    assert not found, "\n".join(found[:20])


def test_fit_and_wrap_measure_text():
    assert P.text_width("WWWW", 10) > P.text_width("iiii", 10)
    s = P.fit(LONG, 100, 8)
    assert s.endswith("…") and P.text_width(s, 8) <= 100
    lines = P.wrap(LONG + " https://example.org/" + "x" * 300, 150, 8)
    assert all(P.text_width(x, 8) <= 150 for x in lines)
    assert P.upper("Σχέδια επενδύσεων") == "ΣΧΕΔΙΑ ΕΠΕΝΔΥΣΕΩΝ"
