"""Package the EU MRV database inside the application.

    python tools/bundle_mrv.py path/to/mrv.sqlite

Writes navigator/resources/mrv.sqlite.xz and mrv_manifest.json (EMSA releases, ship count,
checksum). Run after importing a newer EMSA release, then commit both files.
"""
# ruff: noqa: E402  (paths are set up before the imports)
import hashlib
import json
import lzma
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "navigator" / "resources"
sys.path.insert(0, str(ROOT))
from navigator.data.mrv import IMPORTER_VERSION  # noqa: E402


def main(src: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "mrv.sqlite"
        shutil.copy(src, clean)
        con = sqlite3.connect(clean)
        releases = [dict(zip(("year", "version", "generated"), r, strict=True))
                    for r in con.execute("SELECT year, version, generated FROM releases ORDER BY year")]
        ships = con.execute("SELECT COUNT(*) FROM ships").fetchone()[0]
        reports = con.execute("SELECT COUNT(*) FROM reports WHERE partial = 0").fetchone()[0]
        con.close()
        raw = clean.read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mrv.sqlite.xz").write_bytes(lzma.compress(raw, preset=9))
    manifest = {"source": "EMSA THETIS-MRV public emission reports", "url": "https://mrv.emsa.europa.eu",
                "importer": IMPORTER_VERSION,
                "releases": releases, "ships": ships, "full_reports": reports,
                "sha256": hashlib.sha256(raw).hexdigest()}
    (OUT / "mrv_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{ships:,} ships, {reports:,} full reports, {len(raw)/1e6:.1f} MB -> "
          f"{(OUT / 'mrv.sqlite.xz').stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "mrv.sqlite")
