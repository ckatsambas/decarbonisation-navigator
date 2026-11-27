"""The PDF report: A4 pages drawn with matplotlib (decision 0014-5).

Layout flows from the top of each page: every block asks for the height it needs and moves to a new
("continued") page when it does not fit. Texts are wrapped and table cells fitted by their measured
width, long tables continue on the next page with their header, so nothing is squeezed, cut off or
drawn over something else (checked page by page by `layout_check` in the tests).
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.textpath import TextToPath  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .data import ReportData, Table  # noqa: E402

A4 = (8.27, 11.69)
PAGE_W_PT, PAGE_H_PT = A4[0] * 72, A4[1] * 72
LEFT, RIGHT, TOP, BOTTOM = 0.07, 0.93, 0.92, 0.065
INK, MUTED, FAINT, GRID = "#13283A", "#56677A", "#97A3AE", "#E8E2D6"
ACCENT, RED, ETS, FUELEU, IMO = "#0F6E78", "#D23B2E", "#2F6FA8", "#2A9D8F", "#6A55A8"
SOFT = ["#4C8DB8", "#4FA88A", "#8E7CC3", "#D9A441", "#C77DA0", "#7A9E4F", "#5BB0C9", "#B5835A"]
FONT = "DejaVu Sans"
SMAA_MAX = 12                         # options shown in the rank-acceptability chart
plt.rcParams.update({"font.family": FONT, "font.size": 8.5, "axes.edgecolor": FAINT,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK})

_T2P = TextToPath()


# ------------------------------------------------------------------ measuring text
@lru_cache(maxsize=20000)
def text_width(s: str, size: float, bold: bool = False) -> float:
    """Width of a single line in points."""
    if not s:
        return 0.0
    prop = FontProperties(family=FONT, size=size, weight="bold" if bold else "normal")
    return _T2P.get_text_width_height_descent(s.replace("$", r"\$"), prop, ismath=False)[0]


def fit(s: str, width: float, size: float, bold: bool = False) -> str:
    """`s` shortened with an ellipsis so that it is at most `width` points wide."""
    if text_width(s, size, bold) <= width:
        return s
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(s[:mid].rstrip() + "…", size, bold) <= width:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo].rstrip() + "…"


def wrap(s: str, width: float, size: float, bold: bool = False) -> list[str]:
    """Greedy word wrap by measured width; words longer than a line (URLs) are broken."""
    lines: list[str] = []
    for para in (s or "").split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = f"{cur} {word}" if cur else word
            if text_width(trial, size, bold) <= width:
                cur = trial
                continue
            if cur:
                lines.append(cur)
            while text_width(word, size, bold) > width:      # break a long word
                k = len(fit(word, width, size, bold)) - 1
                k = max(k, 1)
                lines.append(word[:k])
                word = word[k:]
            cur = word
        lines.append(cur)
    return lines or [""]


def upper(text: str) -> str:
    """Greek capitals without accents (as `ui.theme.upper`; the report does not import the interface)."""
    nfd = unicodedata.normalize("NFD", text.upper())
    return unicodedata.normalize("NFC", "".join(ch for ch in nfd if ch not in ("\u0301", "\u0308")))


def line_h(size: float) -> float:
    return size / 72 / A4[1] * 1.45


def _num(x: float, digits: int, lang: str) -> str:
    s = f"{abs(x):,.{digits}f}"
    if lang == "el":
        s = s.replace(",", " ").replace(".", ",").replace(" ", ".")
    return ("−" if x < 0 and round(abs(x), digits) else "") + s


def money_axis(lang: str):
    def f(v, _pos):
        a = abs(v)
        if a >= 1e6:
            return _num(v / 1e6, 1, lang) + "m"
        if a >= 1e3:
            return _num(v / 1e3, 0, lang) + "k"
        return _num(v, 0, lang)
    return FuncFormatter(f)


# ------------------------------------------------------------------ pages and flow
class Doc:
    def __init__(self, data: ReportData, pdf: PdfPages):
        self.d, self.pdf, self.page = data, pdf, 0
        self.title = ""

    def new(self, title: str):
        self.page += 1
        self.title = title
        fig = plt.figure(figsize=A4)
        fig.patch.set_facecolor("white")
        fig._lang = self.d.lang
        fig.text(LEFT, 0.955, fit(upper(title), (RIGHT - LEFT) * PAGE_W_PT, 10, True), fontsize=10, fontweight="bold", color=ACCENT)
        fig.add_artist(plt.Line2D([LEFT, RIGHT], [0.947, 0.947], color=GRID, lw=1))
        foot = f"{self.d.title} · {self.d.subtitle}"
        fig.text(LEFT, 0.03, fit(foot, (RIGHT - LEFT) * PAGE_W_PT * 0.8, 7), fontsize=7, color=FAINT)
        fig.text(RIGHT, 0.03, f"{self.d.labels.get('page', 'p.')} {self.page}", fontsize=7, color=FAINT, ha="right")
        return fig

    def save(self, fig) -> None:
        self.pdf.savefig(fig)
        plt.close(fig)

    def need(self, fig, y: float, h: float):
        """Room for a block of height h below y, or a continuation page."""
        if y - h >= BOTTOM:
            return fig, y
        self.save(fig)
        base = self.title.split(" (")[0]
        return self.new(f"{base} ({self.label('continued')})"), TOP

    def label(self, k: str) -> str:
        return self.d.labels.get(k, k)


def text_block(doc: Doc, fig, y: float, lines: list[str], size: float = 9.5, gap: float = 0.006,
               bullet: str = "", color: str = INK, x: float = LEFT, right: float = RIGHT):
    """Wrapped paragraphs from y down, continuing on a new page when needed; returns (fig, y)."""
    width = (right - x) * PAGE_W_PT
    indent = text_width(bullet, size) if bullet else 0.0
    for line in lines:
        if not line:
            continue
        for k, w in enumerate(wrap(line, width - indent, size)):
            fig, y = doc.need(fig, y, line_h(size))
            if k == 0 and bullet:
                fig.text(x, y, bullet, fontsize=size, color=color, va="top")
            fig.text(x + indent / PAGE_W_PT, y, w, fontsize=size, color=color, va="top")
            y -= line_h(size)
        y -= gap
    return fig, y


def heading(doc: Doc, fig, y: float, text: str, room: float = 0.06):
    """A small section heading, kept together with at least `room` of what follows."""
    fig, y = doc.need(fig, y, 0.02 + room)
    fig.text(LEFT, y, fit(upper(text), (RIGHT - LEFT) * PAGE_W_PT, 8.5, True), fontsize=8.5, fontweight="bold", color=MUTED, va="top")
    return fig, y - 0.022


def _cell(v, f: str, lang: str) -> str:
    if isinstance(v, str) or v is None:
        return v or "–"
    if f == "eur":
        a = abs(v)
        if a >= 1e6:
            n, unit = _num(v / 1e6, 2, lang), ("εκ. €", "m")
        elif a >= 1e4:
            n, unit = _num(v / 1e3, 0, lang), ("χιλ. €", "k")
        else:
            n, unit = _num(v, 0, lang), ("€", "")
        return f"{n} {unit[0]}" if lang == "el" else f"€{n}{unit[1]}"
    if f == "pct":
        return _num(v * 100, 1, lang) + "%"
    if f == "int":
        return str(int(round(v)))
    if f == "num1":
        return _num(v, 1, lang)
    return _num(v, 0, lang)


CELL_PAD = 0.035                      # of the column width, each side


def table(doc: Doc, fig, y: float, t: Table, size: float = 7.5, col_widths=None, wrap_cols: tuple = (),
          max_lines: int = 3, x: float = LEFT, w: float = RIGHT - LEFT):
    """A table from y down: one line per row (or up to `max_lines` in `wrap_cols`), each cell fitted to its
    column; rows that do not fit continue on a new page under a repeated header. Returns (fig, y)."""
    fmts = t.formats or ["text"] * len(t.header)
    n = len(t.header)
    cw = list(col_widths) if col_widths else [1 / n] * n
    cw = [c / sum(cw) for c in cw]
    room = [w * PAGE_W_PT * c * (1 - 2 * CELL_PAD) - 2 for c in cw]
    head = [wrap(h, room[i], size, bold=True)[:3] for i, h in enumerate(t.header)]
    head_lines = max(len(h) for h in head)
    rows = []
    for r in t.rows:
        cells = []
        for i, (v, f) in enumerate(zip(r, fmts, strict=False)):
            s = _cell(v, f, fig._lang)
            if i in wrap_cols:
                ls = wrap(s, room[i], size)
                if len(ls) > max_lines:
                    ls = ls[:max_lines - 1] + [fit(" ".join(ls[max_lines - 1:]), room[i], size)]
            else:
                ls = [fit(s, room[i], size)]
            cells.append(ls)
        rows.append(cells)
    unit = size / 72 / A4[1] * 1.32                     # one text line
    pad = size / 72 / A4[1] * 0.6                       # above and below the text of a row
    i = 0
    while True:
        avail = y - BOTTOM
        hh = head_lines * unit + pad
        chunk, used = [], hh
        while i + len(chunk) < len(rows):
            rh = max(len(c) for c in rows[i + len(chunk)]) * unit + pad
            if used + rh > avail and (chunk or y < TOP - 1e-9):
                break
            chunk.append(rows[i + len(chunk)])
            used += rh
        if not chunk or (len(chunk) < min(2, len(rows) - i) and y < TOP - 1e-9):
            doc.save(fig)                                 # not even the header and two rows: next page
            fig = doc.new(doc.title)
            y = TOP
            continue
        heights = [hh] + [max(len(c) for c in r) * unit + pad for r in chunk]
        ax = fig.add_axes([x, y - used, w, used])
        ax.axis("off")
        tb = ax.table(cellText=[["\n".join(c) for c in r] for r in chunk],
                      colLabels=["\n".join(h) for h in head], cellLoc="right", colLoc="right", colWidths=cw,
                      bbox=[0, 0, 1, 1])
        tb.auto_set_font_size(False)
        tb.set_fontsize(size)
        for (rr, cc), cell in tb.get_celld().items():
            cell.set_edgecolor(GRID)
            cell.set_linewidth(0.6)
            cell.set_height(heights[rr])
            cell.PAD = CELL_PAD
            if cc < len(fmts) and fmts[cc] == "text":
                cell.get_text().set_ha("left")
                cell._loc = "left"
            if rr == 0:
                cell.set_text_props(color=MUTED, fontweight="bold")
                cell.set_facecolor("#F4F1EA")
            elif rr % 2 == 0:
                cell.set_facecolor("#FBFAF6")
        y -= used
        i += len(chunk)
        if i >= len(rows):
            return fig, y - 0.012
        doc.save(fig)
        fig = doc.new(f"{doc.title.split(' (')[0]} ({doc.label('continued')})")
        y = TOP


# ------------------------------------------------------------------ report
def build_pdf(data: ReportData, path: str | Path) -> Path:
    path = Path(path)
    with PdfPages(path) as pdf:
        doc = Doc(data, pdf)
        _cover(doc)
        _position(doc)
        _measures(doc)
        if data.plans.get("front"):
            _plans(doc)
        if data.weights:
            _weights(doc)
        if data.ranking is not None:
            _decision(doc)
        _assumptions(doc)
        info = pdf.infodict()
        info["Title"] = f"{data.title} – {data.subtitle}"
        info["Author"] = "Decarbonisation Navigator"
    return path


def _cover(doc: Doc) -> None:
    d = doc.d
    fig = doc.new(doc.label("summary"))
    fig.text(LEFT, 0.90, fit(d.title, (RIGHT - LEFT) * PAGE_W_PT, 20, True), fontsize=20, fontweight="bold", color=INK)
    fig.text(LEFT, 0.872, fit(d.subtitle, (RIGHT - LEFT) * PAGE_W_PT, 12), fontsize=12, color=MUTED)
    fig.text(LEFT, 0.852, f"{d.date} · Decarbonisation Navigator v{d.version}", fontsize=8, color=FAINT)
    fig, y = text_block(doc, fig, 0.825, d.summary, size=10, bullet="•  ")
    fig, y = heading(doc, fig, y - 0.012, doc.label("settings"))
    for k, v in d.settings:
        fig, y = doc.need(fig, y, 0.02)
        fig.text(LEFT, y, fit(k, 0.31 * PAGE_W_PT, 8.5), fontsize=8.5, color=MUTED, va="top")
        fig.text(0.40, y, fit(v, (RIGHT - 0.40) * PAGE_W_PT, 8.5), fontsize=8.5, color=INK, va="top")
        y -= 0.02
    doc.save(fig)


def _position(doc: Doc) -> None:
    d, p = doc.d, doc.d.position
    if not p:
        return
    fig = doc.new(doc.label("position"))
    fig, y = text_block(doc, fig, TOP, [p.get("sentence", "")])
    fig, y = doc.need(fig, y, 0.42)
    ax = fig.add_axes([0.11, y - 0.40, 0.82, 0.35])
    years = np.array(p["years"])
    bottom = np.zeros(len(years))
    for key, col in (("ets", ETS), ("fueleu", FUELEU), ("nzf", IMO)):
        vals = np.array(p[key])
        ax.bar(years, vals, bottom=bottom, color=col, width=0.68, label=doc.label(f"legend_{key}"))
        bottom += vals
    ax.yaxis.set_major_formatter(money_axis(d.lang))
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, ncol=3, loc="upper left")
    ax.set_title(doc.label("position_chart"), loc="left", fontsize=9, color=MUTED)
    y -= 0.44
    if p.get("table"):
        fig, y = table(doc, fig, y, p["table"], size=7.5)
    doc.save(fig)


def _measures(doc: Doc) -> None:
    t = doc.d.measures
    if t is None or not t.rows:
        return
    fig = doc.new(doc.label("measures"))
    fig, y = text_block(doc, fig, TOP, [t.note]) if t.note else (fig, TOP)
    fig, y = table(doc, fig, y - 0.005, t, size=7.2, col_widths=[0.40, 0.14, 0.15, 0.17, 0.14])
    doc.save(fig)


def _plans(doc: Doc) -> None:
    d, pl = doc.d, doc.d.plans
    fig = doc.new(doc.label("plans"))
    fig, y = text_block(doc, fig, TOP, [pl.get("sentence", "")])
    front = pl["front"]
    fig, y = doc.need(fig, y, 0.36)
    ax = fig.add_axes([0.13, y - 0.33, 0.79, 0.29])
    xs = [f["avoided"] for f in front]
    ys = [f["npv"] for f in front]
    ax.plot(xs, ys, color=ACCENT, lw=1.6, zorder=1)
    sel = pl.get("selected", 0)
    for i, f in enumerate(front):
        ax.scatter([f["avoided"]], [f["npv"]], s=70 if i == sel else 40, color=RED if i == sel else ACCENT,
                   edgecolor="white", zorder=2)
        ax.annotate(f["label"], (f["avoided"], f["npv"]), textcoords="offset points", xytext=(0, 8), ha="center",
                    fontsize=8, color=RED if i == sel else INK, fontweight="bold")
    ax.margins(x=0.06, y=0.12)
    ax.axhline(0, color=FAINT, lw=0.8, ls="--")
    ax.yaxis.set_major_formatter(money_axis(d.lang))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: _num(v / 1e3, 0, d.lang) + "k"))
    ax.set_xlabel(doc.label("axis_cut"))
    ax.set_ylabel(doc.label("axis_npv"))
    ax.grid(color=GRID)
    ax.spines[["top", "right"]].set_visible(False)
    y -= 0.40
    rows = pl.get("timeline", [])                         # timeline of the selected plan
    if rows:
        h = 0.022 * len(rows)
        fig, y = doc.need(fig, y, h + 0.07)
        fig.text(LEFT, y, fit(pl.get("timeline_title", ""), (RIGHT - LEFT) * PAGE_W_PT, 9, True), fontsize=9,
                 fontweight="bold", color=INK, va="top")
        ax2 = fig.add_axes([0.40, y - 0.03 - h, 0.53, h])
        y0, y1 = pl["years"]
        for i, (_name, year, color) in enumerate(rows):
            ax2.barh(i, y1 + 1 - year, left=year, height=0.45, color=color, alpha=0.35)
            ax2.scatter([year], [i], marker="D", color=color, s=26, zorder=3)
            ax2.text(year + 0.3, i, str(year), va="center", fontsize=7, color=MUTED)
        ax2.set_yticks(range(len(rows)), [fit(r[0], 0.30 * PAGE_W_PT, 7.5) for r in rows], fontsize=7.5)
        ax2.invert_yaxis()
        ax2.set_xlim(y0, y1 + 1)
        ax2.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax2.spines[["top", "right", "left"]].set_visible(False)
        ax2.tick_params(axis="y", length=0)
        ax2.grid(axis="x", color=GRID)
        y -= h + 0.075
    ad = pl.get("adaptive")
    if ad:
        fig, y = heading(doc, fig, y, doc.label("adaptive"), room=0.12)
        fig, y = text_block(doc, fig, y, [ad["sentence"], ad["now"]], size=8.5)
        fig, y = table(doc, fig, y - 0.005, ad["table"], size=6.6, col_widths=[0.14, 0.15, 0.1, 0.13, 0.48],
                       wrap_cols=(4,), max_lines=2)
    doc.save(fig)


def _weights(doc: Doc) -> None:
    w = doc.d.weights
    fig = doc.new(doc.label("weights"))
    fig, y = text_block(doc, fig, TOP, [w.get("sentence", ""), w.get("status", "")])
    names = w["names"]
    fig, y = doc.need(fig, y, 0.42)
    ax = fig.add_axes([0.33, y - 0.40, 0.59, 0.37])
    idx = np.arange(len(names))
    series = [(doc.label("company"), w["company"], RED), (doc.label("entropy"), w.get("entropy"), ETS),
              (doc.label("critic"), w.get("critic"), FUELEU)]
    series = [s for s in series if s[1] is not None]
    h = 0.8 / len(series)
    for k, (lab, vals, col) in enumerate(series):
        ax.barh(idx + k * h, vals, height=h * 0.9, color=col, label=lab, alpha=1 if k == 0 else 0.55)
        if k == 0 and w.get("lo") is not None:                  # WAP: the range each weight can take
            v = np.asarray(vals, float)
            err = np.vstack([v - np.asarray(w["lo"]), np.asarray(w["hi"]) - v]).clip(0)
            ax.errorbar(v, idx, xerr=err, fmt="none", ecolor=MUTED, elinewidth=1, capsize=2.5)
    ax.set_yticks(idx + h * (len(series) - 1) / 2, [fit(n, 0.24 * PAGE_W_PT, 8.5) for n in names])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: _num(v * 100, 0, doc.d.lang) + "%"))
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="x", color=GRID)
    ax.spines[["top", "right"]].set_visible(False)
    y -= 0.45
    if w.get("table"):
        fig, y = table(doc, fig, y, w["table"], size=7.5)
    doc.save(fig)


def _decision(doc: Doc) -> None:
    d = doc.d
    fig = doc.new(doc.label("ranking"))
    fig, y = text_block(doc, fig, TOP, d.ranking.note.split("\n") if d.ranking.note else [])
    ncol = len(d.ranking.header)
    fig, y = table(doc, fig, y - 0.005, d.ranking, size=7.2,
                   col_widths=[0.31] + [(1 - 0.31 - 0.14) / (ncol - 2)] * (ncol - 2) + [0.14])
    s = d.smaa
    if s:
        names = s["names"][:SMAA_MAX]                      # sorted by expected rank
        acc = np.array(s["acceptability"])[:SMAA_MAX]
        R = min(acc.shape[1], SMAA_MAX)
        rows_h = 0.03 * len(names)
        fig, y = heading(doc, fig, y - 0.01, doc.label("smaa"), room=0.06 + rows_h)
        lines = [s.get("sentence", "")]
        if len(s["names"]) > SMAA_MAX:
            lines.append(doc.label("smaa_top").format(n=SMAA_MAX, total=len(s["names"])))
        fig, y = text_block(doc, fig, y, lines, size=8.5)
        fig, y = doc.need(fig, y, rows_h + 0.05)
        ax = fig.add_axes([0.37, y - 0.03 - rows_h, 0.48, rows_h])
        cols = s.get("colors") or [SOFT[i % len(SOFT)] for i in range(len(names))]
        for i in range(len(names)):
            for r in range(R):
                v = acc[i, r]
                if v > 0.002:
                    ax.scatter([r], [i], s=700 * v + 6, color=cols[i], alpha=0.55, edgecolor=cols[i])
                if v >= 0.1:
                    ax.text(r, i, _num(v * 100, 0, d.lang) + "%", ha="center", va="center", fontsize=6.3, color=INK)
            ax.text(R - 0.2, i, _num(s["expected"][i], 1, d.lang), va="center", fontsize=7.5, color=INK)
        ax.set_xticks(range(R), [doc.label("rank_short").format(r=r + 1) for r in range(R)], fontsize=7)
        ax.set_yticks(range(len(names)), [fit(n, 0.27 * PAGE_W_PT, 7.5) for n in names], fontsize=7.5)
        ax.set_xlim(-0.6, R + 0.4)
        ax.set_ylim(len(names) - 0.5, -0.5)
        ax.xaxis.tick_top()
        ax.spines[:].set_visible(False)
        ax.tick_params(length=0)
        y -= rows_h + 0.07
        fan = s.get("fan")
        if fan:
            fig, y = heading(doc, fig, y, fan["title"], room=0.26)
            hh = min(y - BOTTOM - 0.04, 0.34)
            ax3 = fig.add_axes([0.13, y - hh - 0.01, 0.79, hh])
            years = [fan["years"][0] - 1, *fan["years"]]
            for path in fan["paths"]:
                full = [0.0, *path]
                ax3.plot(years, full, color=ETS if full[-1] >= 0 else RED, alpha=0.08, lw=0.8)
            ax3.axhline(0, color=FAINT, lw=0.8, ls="--")
            ax3.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
            ax3.yaxis.set_major_formatter(money_axis(d.lang))
            ax3.grid(axis="y", color=GRID)
            ax3.spines[["top", "right"]].set_visible(False)
            shares = "\n".join(fit(x, 0.5 * PAGE_W_PT, 8) for x in fan["shares"].split("\n"))
            ax3.text(0.99, 0.97, shares, transform=ax3.transAxes, ha="right", va="top", fontsize=8, color=INK,
                     bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2})
    doc.save(fig)


def _assumptions(doc: Doc) -> None:
    d = doc.d
    fig = doc.new(doc.label("assumptions"))
    y = TOP
    if d.assumptions is not None and d.assumptions.rows:
        fig, y = text_block(doc, fig, y, [d.assumptions.note], size=8.5)
        fig, y = table(doc, fig, y - 0.005, d.assumptions, size=6.5, col_widths=[0.27, 0.25, 0.48],
                       wrap_cols=(1, 2), max_lines=3)
    fig, y = heading(doc, fig, y - 0.01, doc.label("sources"))
    lines = [f"{t}{' – ' + u if u else ''}{' (' + c + ')' if c else ''}" for t, u, c in d.sources]
    fig, _y = text_block(doc, fig, y, lines, size=6.5, gap=0.0015, bullet="•  ")
    doc.save(fig)
