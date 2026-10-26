"""The PDF report: A4 pages drawn with matplotlib (decision 0014-5)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .data import ReportData, Table  # noqa: E402

A4 = (8.27, 11.69)
INK, MUTED, FAINT, GRID = "#13283A", "#56677A", "#97A3AE", "#E8E2D6"
ACCENT, RED, ETS, FUELEU, IMO = "#0F6E78", "#D23B2E", "#2F6FA8", "#2A9D8F", "#6A55A8"
SOFT = ["#4C8DB8", "#4FA88A", "#8E7CC3", "#D9A441", "#C77DA0", "#7A9E4F", "#5BB0C9", "#B5835A"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": FAINT,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK})


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


class Doc:
    def __init__(self, data: ReportData, pdf: PdfPages):
        self.d, self.pdf, self.page = data, pdf, 0

    def new(self, title: str):
        self.page += 1
        fig = plt.figure(figsize=A4)
        fig.patch.set_facecolor("white")
        fig.text(0.07, 0.955, title.upper(), fontsize=10, fontweight="bold", color=ACCENT)
        fig.add_artist(plt.Line2D([0.07, 0.93], [0.947, 0.947], color=GRID, lw=1))
        fig.text(0.07, 0.03, f"{self.d.title} · {self.d.subtitle}", fontsize=7, color=FAINT)
        fig.text(0.93, 0.03, f"{self.d.labels.get('page', 'p.')} {self.page}", fontsize=7, color=FAINT, ha="right")
        return fig

    def save(self, fig) -> None:
        self.pdf.savefig(fig)
        plt.close(fig)

    def label(self, k: str) -> str:
        return self.d.labels.get(k, k)


def text_block(fig, x: float, y: float, lines: list[str], width: int = 95, size: float = 9.5, gap: float = 0.006,
               bullet: str = "•  ", color: str = INK) -> float:
    """Wrapped paragraphs from the top (figure coordinates); returns the y below them."""
    for line in lines:
        wrapped = textwrap.wrap(line, width) or [""]
        for k, w in enumerate(wrapped):
            prefix = bullet if k == 0 and bullet else ("   " if bullet else "")
            fig.text(x, y, prefix + w, fontsize=size, color=color, va="top")
            y -= size / 72 / A4[1] * 1.45
        y -= gap
    return y


def table(fig, rect, t: Table, size: float = 7.5, max_rows: int = 40, col_widths=None, max_chars: int = 70) -> float:
    """A table fitted to the top of `rect` (x, y, w, h in figure coordinates): one line per row, long texts
    shortened with an ellipsis, text columns left-aligned. Returns the y below the table."""
    fmts = t.formats or ["text"] * len(t.header)
    rows = []
    for r in t.rows[:max_rows]:
        cells = []
        for v, f in zip(r, fmts, strict=False):
            c = _cell(v, f, fig._lang)
            cells.append(c if len(c) <= max_chars else c[: max_chars - 1] + "…")
        rows.append(cells)
    if not rows:
        return rect[1] + rect[3]
    header = ["\n".join(textwrap.wrap(h, 16)) or h for h in t.header]
    lines = max(h.count("\n") + 1 for h in header)
    row_h = size / 72 / A4[1] * 1.9
    height = min(rect[3], row_h * (len(rows) + lines))
    ax = fig.add_axes([rect[0], rect[1] + rect[3] - height, rect[2], height])
    ax.axis("off")
    tb = ax.table(cellText=rows, colLabels=header, cellLoc="right", colLoc="right", colWidths=col_widths,
                  bbox=[0, 0, 1, 1])
    tb.auto_set_font_size(False)
    tb.set_fontsize(size)
    for (r, c), cell in tb.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.set_linewidth(0.6)
        text_col = c < len(fmts) and fmts[c] == "text"
        if text_col:
            cell.get_text().set_ha("left")
            cell._loc = "left"
            cell.PAD = 0.02
        if r == 0:
            cell.set_text_props(color=MUTED, fontweight="bold")
            cell.set_facecolor("#F4F1EA")
            cell.set_height(cell.get_height() * lines)
        elif r % 2 == 0:
            cell.set_facecolor("#FBFAF6")
    return rect[1] + rect[3] - height


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


def _fig(doc: Doc, title: str):
    fig = doc.new(title)
    fig._lang = doc.d.lang
    return fig


# ------------------------------------------------------------------ pages
def _cover(doc: Doc) -> None:
    d = doc.d
    fig = _fig(doc, doc.label("summary"))
    fig.text(0.07, 0.90, d.title, fontsize=20, fontweight="bold", color=INK)
    fig.text(0.07, 0.872, d.subtitle, fontsize=12, color=MUTED)
    fig.text(0.07, 0.852, f"{d.date} · Decarbonisation Navigator v{d.version}", fontsize=8, color=FAINT)
    y = text_block(fig, 0.07, 0.82, d.summary, width=92, size=10)
    fig.text(0.07, y - 0.02, doc.label("settings").upper(), fontsize=8.5, fontweight="bold", color=MUTED)
    y -= 0.045
    for k, v in d.settings:
        fig.text(0.07, y, k, fontsize=8.5, color=MUTED)
        fig.text(0.40, y, v, fontsize=8.5, color=INK)
        y -= 0.02
    doc.save(fig)


def _position(doc: Doc) -> None:
    d, p = doc.d, doc.d.position
    if not p:
        return
    fig = _fig(doc, doc.label("position"))
    y = text_block(fig, 0.07, 0.92, [p.get("sentence", "")], bullet="", width=95)
    ax = fig.add_axes([0.1, y - 0.42, 0.83, 0.38])
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
    if p.get("table"):
        table(fig, [0.07, 0.07, 0.86, y - 0.52], p["table"], size=7.5)
    doc.save(fig)


def _measures(doc: Doc) -> None:
    t = doc.d.measures
    if t is None or not t.rows:
        return
    fig = _fig(doc, doc.label("measures"))
    y = text_block(fig, 0.07, 0.92, [t.note], bullet="", width=95) if t.note else 0.92
    table(fig, [0.07, 0.07, 0.86, y - 0.09], t, size=7.2, col_widths=[0.44, 0.13, 0.15, 0.16, 0.12])
    doc.save(fig)


def _plans(doc: Doc) -> None:
    d, pl = doc.d, doc.d.plans
    fig = _fig(doc, doc.label("plans"))
    y = text_block(fig, 0.07, 0.92, [pl.get("sentence", "")], bullet="", width=95)
    front = pl["front"]
    ax = fig.add_axes([0.12, y - 0.33, 0.8, 0.29])
    xs = [f["avoided"] for f in front]
    ys = [f["npv"] for f in front]
    ax.plot(xs, ys, color=ACCENT, lw=1.6, zorder=1)
    sel = pl.get("selected", 0)
    for i, f in enumerate(front):
        ax.scatter([f["avoided"]], [f["npv"]], s=70 if i == sel else 40, color=RED if i == sel else ACCENT,
                   edgecolor="white", zorder=2)
        ax.annotate(f["label"], (f["avoided"], f["npv"]), textcoords="offset points", xytext=(0, 8), ha="center",
                    fontsize=8, color=RED if i == sel else INK, fontweight="bold")
    ax.axhline(0, color=FAINT, lw=0.8, ls="--")
    ax.yaxis.set_major_formatter(money_axis(d.lang))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: _num(v / 1e3, 0, d.lang) + "k"))
    ax.set_xlabel(doc.label("axis_cut"))
    ax.set_ylabel(doc.label("axis_npv"))
    ax.grid(color=GRID)
    ax.spines[["top", "right"]].set_visible(False)
    # timeline of the selected plan
    rows = pl.get("timeline", [])
    if rows:
        top = y - 0.40
        fig.text(0.07, top + 0.02, pl.get("timeline_title", ""), fontsize=9, fontweight="bold", color=INK)
        ax2 = fig.add_axes([0.38, top - 0.022 * len(rows) - 0.02, 0.55, 0.022 * len(rows)])
        y0, y1 = pl["years"]
        for i, (_name, year, color) in enumerate(rows):
            ax2.barh(i, y1 + 1 - year, left=year, height=0.45, color=color, alpha=0.35)
            ax2.scatter([year], [i], marker="D", color=color, s=26, zorder=3)
            ax2.text(year + 0.3, i, str(year), va="center", fontsize=7, color=MUTED)
        ax2.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=7.5)
        ax2.invert_yaxis()
        ax2.set_xlim(y0, y1 + 1)
        ax2.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax2.spines[["top", "right", "left"]].set_visible(False)
        ax2.tick_params(axis="y", length=0)
        ax2.grid(axis="x", color=GRID)
        top = top - 0.022 * len(rows) - 0.07
    else:
        top = y - 0.42
    ad = pl.get("adaptive")
    if ad:
        fig.text(0.07, top, doc.label("adaptive").upper(), fontsize=8.5, fontweight="bold", color=MUTED)
        yy = text_block(fig, 0.07, top - 0.015, [ad["sentence"], ad["now"]], bullet="", width=100, size=8.5)
        table(fig, [0.07, 0.06, 0.86, max(yy - 0.075, 0.12)], ad["table"], size=6.4,
              col_widths=[0.14, 0.15, 0.1, 0.13, 0.48], max_chars=80)
    doc.save(fig)


def _weights(doc: Doc) -> None:
    w = doc.d.weights
    fig = _fig(doc, doc.label("weights"))
    y = text_block(fig, 0.07, 0.92, [w.get("sentence", ""), w.get("status", "")], bullet="", width=95)
    ax = fig.add_axes([0.32, y - 0.42, 0.6, 0.38])
    names = w["names"]
    n = len(names)
    idx = np.arange(n)
    series = [(doc.label("company"), w["company"], RED), (doc.label("entropy"), w.get("entropy"), ETS),
              (doc.label("critic"), w.get("critic"), FUELEU)]
    series = [s for s in series if s[1] is not None]
    h = 0.8 / len(series)
    for k, (lab, vals, col) in enumerate(series):
        ax.barh(idx + k * h, vals, height=h * 0.9, color=col, label=lab, alpha=1 if k == 0 else 0.55)
    ax.set_yticks(idx + h * (len(series) - 1) / 2, names)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: _num(v * 100, 0, doc.d.lang) + "%"))
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="x", color=GRID)
    ax.spines[["top", "right"]].set_visible(False)
    if w.get("table"):
        table(fig, [0.07, 0.07, 0.86, y - 0.52], w["table"], size=7.5)
    doc.save(fig)


def _decision(doc: Doc) -> None:
    d = doc.d
    fig = _fig(doc, doc.label("ranking"))
    y = text_block(fig, 0.07, 0.92, d.ranking.note.split("\n") if d.ranking.note else [], bullet="", width=95)
    nrow = len(d.ranking.rows)
    h = min(0.03 * (nrow + 1), 0.3)
    table(fig, [0.07, y - h - 0.01, 0.86, h], d.ranking, size=7.2,
          col_widths=[0.34] + [0.11] * (len(d.ranking.header) - 1), max_chars=48)
    y = y - h - 0.05
    s = d.smaa
    if s:
        fig.text(0.07, y, doc.label("smaa").upper(), fontsize=8.5, fontweight="bold", color=MUTED)
        y = text_block(fig, 0.07, y - 0.015, [s.get("sentence", "")], bullet="", width=100, size=8.5)
        acc = np.array(s["acceptability"])
        names = s["names"]
        ax = fig.add_axes([0.35, y - 0.03 * len(names) - 0.04, 0.5, 0.03 * len(names)])
        R = acc.shape[1]
        cols = s.get("colors") or [SOFT[i % len(SOFT)] for i in range(len(names))]
        for i in range(len(names)):
            for r in range(R):
                v = acc[i, r]
                if v > 0.002:
                    ax.scatter([r], [i], s=900 * v + 6, color=cols[i], alpha=0.55, edgecolor=cols[i])
                if v >= 0.1:
                    ax.text(r, i, _num(v * 100, 0, d.lang) + "%", ha="center", va="center", fontsize=6.5, color=INK)
            ax.text(R - 0.3, i, _num(s["expected"][i], 1, d.lang), va="center", fontsize=7.5, color=INK)
        ax.set_xticks(range(R), [doc.label("rank_short").format(r=r + 1) for r in range(R)])
        ax.set_yticks(range(len(names)), [n if len(n) <= 38 else n[:37] + "…" for n in names], fontsize=7.5)
        ax.set_xlim(-0.6, R + 0.4)
        ax.set_ylim(len(names) - 0.5, -0.5)
        ax.xaxis.tick_top()
        ax.spines[:].set_visible(False)
        ax.tick_params(length=0)
        y = y - 0.03 * len(names) - 0.08
        fan = s.get("fan")
        if fan and y > 0.25:
            fig.text(0.07, y, fan["title"].upper(), fontsize=8.5, fontweight="bold", color=MUTED)
            ax3 = fig.add_axes([0.12, 0.07, 0.8, y - 0.11])
            years = [fan["years"][0] - 1, *fan["years"]]
            for path in fan["paths"]:
                full = [0.0, *path]
                ax3.plot(years, full, color=ETS if full[-1] >= 0 else RED, alpha=0.08, lw=0.8)
            ax3.axhline(0, color=FAINT, lw=0.8, ls="--")
            ax3.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
            ax3.yaxis.set_major_formatter(money_axis(d.lang))
            ax3.grid(axis="y", color=GRID)
            ax3.spines[["top", "right"]].set_visible(False)
            ax3.text(0.99, 0.97, fan["shares"], transform=ax3.transAxes, ha="right", va="top", fontsize=8, color=INK)
    doc.save(fig)


def _assumptions(doc: Doc) -> None:
    d = doc.d
    fig = _fig(doc, doc.label("assumptions"))
    y = 0.92
    if d.assumptions is not None and d.assumptions.rows:
        y = text_block(fig, 0.07, y, [d.assumptions.note], bullet="", width=95, size=8.5)
        h = min(0.022 * (len(d.assumptions.rows) + 1), 0.45)
        table(fig, [0.07, y - h, 0.86, h], d.assumptions, size=6.3, max_rows=30,
              col_widths=[0.28, 0.17, 0.55], max_chars=95)
        y = y - h - 0.04
    fig.text(0.07, y, doc.label("sources").upper(), fontsize=8.5, fontweight="bold", color=MUTED)
    lines = [f"{t}{' – ' + u if u else ''}{' (' + c + ')' if c else ''}" for t, u, c in d.sources[:40]]
    text_block(fig, 0.07, y - 0.015, lines, width=120, size=6.5, gap=0.001)
    doc.save(fig)
