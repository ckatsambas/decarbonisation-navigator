"""Check the layout of PDF reports built from pickled ReportData (or any list of .pkl files).

    python tools/check_report.py data1.pkl [data2.pkl ...] [--out dir]

Every page goes through `navigator.report.layout_check`; problems are printed and the PDFs are written
next to the data (or to --out) for a visual look.
"""
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from navigator.report import pdf as P  # noqa: E402
from navigator.report.layout_check import check_figure  # noqa: E402


def main(args: list[str]) -> int:
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    found: list[str] = []
    original = P.Doc.save

    for path in map(Path, args):
        data = pickle.loads(path.read_bytes())

        def save(self, fig, _name=path.stem):
            found.extend(check_figure(fig, f"{_name} p.{self.page}"))
            original(self, fig)

        P.Doc.save = save
        target = (out or path.parent) / f"{path.stem}.pdf"
        P.build_pdf(data, target)
    P.Doc.save = original
    print("\n".join(found) if found else "no layout problems")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
