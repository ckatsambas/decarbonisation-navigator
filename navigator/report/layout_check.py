"""Layout check of the PDF report pages: nothing off the page, no two blocks on top of each other, no
squeezed tables and no table text spilling out of its cell. Used by the tests and by
`tools/check_report.py`; it changes nothing on the page.
"""
from __future__ import annotations

from matplotlib.transforms import Bbox

MARGIN_X, MARGIN_Y = 0.035, 0.012        # of the page width / height
TOLERANCE = 1.5                          # px of overlap that is not a collision (anti-aliasing)


def _overlap(a: Bbox, b: Bbox) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return min(w, h) if w > 0 and h > 0 else 0.0


def check_figure(fig, page: str = "") -> list[str]:
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    W, H = fig.bbox.width, fig.bbox.height
    blocks: list[tuple[str, Bbox]] = []
    problems: list[str] = []
    for t in fig.texts:
        if t.get_text().strip():
            blocks.append((f"text «{t.get_text()[:50]}»", t.get_window_extent(r)))
    for ax in fig.axes:
        if ax.tables:
            for tb in ax.tables:
                blocks.append((f"table «{_first_cell(tb)}»", tb.get_window_extent(r)))
                problems += _check_table(tb, r, page)
        else:
            title = ax.get_title(loc="left") or ax.get_title() or (ax.get_ylabel() or ax.get_xlabel() or "chart")
            blocks.append((f"chart «{title[:40]}»", ax.get_tightbbox(r)))
    for name, b in blocks:
        if b.x0 < MARGIN_X * W - 1 or b.x1 > (1 - MARGIN_X) * W + 1 or b.y0 < MARGIN_Y * H - 1 or b.y1 > H * 0.99:
            problems.append(f"{page}: {name} goes off the page ({b.x0:.0f}–{b.x1:.0f} × {b.y0:.0f}–{b.y1:.0f} px)")
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if _overlap(blocks[i][1], blocks[j][1]) > TOLERANCE:
                problems.append(f"{page}: {blocks[i][0]} overlaps {blocks[j][0]}")
    return problems


def _first_cell(tb) -> str:
    cells = tb.get_celld()
    c = cells.get((0, 0))
    return c.get_text().get_text().replace("\n", " ")[:30] if c is not None else ""


def _check_table(tb, r, page: str) -> list[str]:
    out = []
    for (row, col), cell in tb.get_celld().items():
        text = cell.get_text()
        if not text.get_text().strip():
            continue
        cb, tbx = cell.get_window_extent(r), text.get_window_extent(r)
        if tbx.width > cb.width - 2:
            out.append(f"{page}: table «{_first_cell(tb)}» cell ({row},{col}) «{text.get_text()[:30]}» is wider "
                       f"than its column")
        if tbx.height > cb.height + 1:
            out.append(f"{page}: table «{_first_cell(tb)}» row {row} is squeezed (text taller than the row)")
    return out
