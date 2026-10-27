"""Screenshots of the first launch and the tour (decision 0015), saved to docs/screenshots/welcome.

    QT_QPA_PLATFORM=offscreen NAVIGATOR_ANIMATIONS=0 python tools/screenshots_welcome.py
"""
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from navigator.data.accounts import AccountStore  # noqa: E402
from navigator.ui import theme  # noqa: E402
from navigator.ui.main_window import MainWindow  # noqa: E402

OUT = ROOT / "docs" / "screenshots" / "welcome"
TOUR_SHOTS = (1, 3, 7, 9, 14, 15, 16, 19)


def pump(n: int = 10) -> None:
    for _ in range(n):
        app.processEvents()
        time.sleep(0.03)


def shot(w, name: str) -> None:
    w.grab().save(str(OUT / f"{name}.png"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    app.setStyleSheet(theme.stylesheet(theme.current()))
    accounts = AccountStore(Path(tempfile.mkdtemp()))
    w = MainWindow(accounts=accounts, welcome="setup")
    w.resize(1440, 900)
    w.show()
    pump()
    shot(w, "1-account")
    ap = w.welcome.account_page
    ap.c_name.setText("Maria P.")
    ap.c_user.setText("maria")
    ap.c_pw.edit.setText("Sea-route-2027")
    ap.c_pw2.edit.setText("Sea-route-2027")
    ap.create()                                   # terms not ticked: the error shows
    pump()
    shot(w, "1b-error")
    ap.c_terms.box.setChecked(True)
    ap.create()
    pump()
    shot(w, "2-code")
    ap.k_saved.setChecked(True)
    ap.k_btn.click()
    pump(30)
    shot(w, "3-prefs")
    w.welcome.prefs_page.theme_changed.emit("dark")
    pump()
    shot(w, "3b-prefs-dark")
    w.welcome.go(2)
    pump(30)
    shot(w, "4-tour")
    w.welcome.tour_page.go.click()
    pump(40)
    shot(w, "5-tour0")
    for k in range(1, len(w.tour.steps)):
        w.tour.next()
        pump(25)
        if k in TOUR_SHOTS:
            shot(w, f"6-tour{k}")
    w.tour.next()
    pump()
    print("saved to", OUT)


if __name__ == "__main__":
    main()
