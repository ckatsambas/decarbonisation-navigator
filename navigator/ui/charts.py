"""On-screen charts (pyqtgraph). Print figures for reports and the thesis will use matplotlib
from the same data (see docs/decisions/0003)."""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtGui import QColor

from ..i18n import num
from . import theme

pg.setConfigOptions(antialias=True)


class MoneyAxis(pg.AxisItem):
    """Y axis in thousands/millions with the current language's separators."""

    def tickStrings(self, values, scale, spacing):
        top = max((abs(v) for v in values), default=0)
        if top >= 1e6:
            return [num(v / 1e6, 1) + "m" for v in values]
        if top >= 1e3:
            return [num(v / 1e3, 0) + "k" for v in values]
        return [num(v, 0) for v in values]


class YearAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [str(round(v)) for v in values]


def style_plot(w: pg.PlotWidget) -> None:
    p = theme.current()
    w.setBackground(p.panel)
    pi = w.getPlotItem()
    for name in ("left", "bottom"):
        ax = pi.getAxis(name)
        ax.setPen(pg.mkPen(p.border))
        ax.setTextPen(pg.mkPen(p.muted))
    pi.getAxis("left").setWidth(56)
    pi.showGrid(x=False, y=True, alpha=0.25)


class BarChart(pg.PlotWidget):
    """Vertical bars by year with a money axis."""

    def __init__(self):
        super().__init__(axisItems={"left": MoneyAxis("left"), "bottom": YearAxis("bottom")})
        self.setMinimumHeight(260)
        self.setMenuEnabled(False)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self._bars: pg.BarGraphItem | None = None
        style_plot(self)

    def set_data(self, years: list[int], values: list[float], color: str) -> None:
        if self._bars is not None:
            self.removeItem(self._bars)
        col = QColor(color)
        self._bars = pg.BarGraphItem(x=years, height=values, width=0.72, brush=col, pen=pg.mkPen(None))
        self.addItem(self._bars)
        if years:
            self.setXRange(years[0] - 0.8, years[-1] + 0.8, padding=0)
            self.setYRange(0, max(max(values, default=0), 1) * 1.08, padding=0)

    def restyle(self) -> None:
        style_plot(self)


class StackedBarChart(pg.PlotWidget):
    """Bars by year split into stacked components, with an optional line on top (e.g. a reported total)."""

    def __init__(self, axis: str = "number"):
        left = MoneyAxis("left") if axis == "money" else NumberAxis("left")
        super().__init__(axisItems={"left": left, "bottom": YearAxis("bottom")})
        self.setMinimumHeight(240)
        self.setMenuEnabled(False)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.legend = None
        style_plot(self)

    def set_data(self, years: list[int], series: list[tuple[str, list[float], str]],
                 line: tuple[str, list[float | None], str] | None = None) -> None:
        self.clear()
        if self.legend is None:
            self.legend = self.addLegend(offset=(8, 4), colCount=len(series) + 1)
        self.legend.clear()
        self.legend.setLabelTextColor(theme.current().muted)
        base = [0.0] * len(years)
        for name, vals, color in series:
            item = pg.BarGraphItem(x=years, height=vals, y0=base, width=0.66, brush=QColor(color), pen=pg.mkPen(None),
                                   name=name)
            self.addItem(item)            # named items join the legend automatically
            base = [b + v for b, v in zip(base, vals, strict=True)]
        top = max(base, default=0)
        if line:
            name, vals, color = line
            pts = [(y, v) for y, v in zip(years, vals, strict=True) if v is not None]
            if pts:
                xs, ys = zip(*pts, strict=True)
                self.plot(xs, ys, pen=pg.mkPen(color, width=2), symbol="o", symbolSize=6,
                          symbolBrush=QColor(color), symbolPen=pg.mkPen(None), name=name)
                top = max(top, max(ys))
        if years:
            self.setXRange(years[0] - 0.7, years[-1] + 0.7, padding=0)
            self.setYRange(0, max(top, 1) * 1.15, padding=0)

    def restyle(self) -> None:
        style_plot(self)


class NumberAxis(pg.AxisItem):
    """Plain quantities (tonnes) with k/m suffixes."""

    def tickStrings(self, values, scale, spacing):
        top = max((abs(v) for v in values), default=0)
        if top >= 1e6:
            return [num(v / 1e6, 1) + "m" for v in values]
        if top >= 1e4:
            return [num(v / 1e3, 0) + "k" for v in values]
        return [num(v, 0) for v in values]


class CashFlowChart(pg.PlotWidget):
    """Yearly net cash flow (bars above or below zero) and the running total (line)."""

    def __init__(self):
        super().__init__(axisItems={"left": MoneyAxis("left"), "bottom": YearAxis("bottom")})
        self.setMinimumHeight(220)
        self.setMenuEnabled(False)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.legend = None
        style_plot(self)

    def set_data(self, years: list[int], flows: list[float], labels: tuple[str, str]) -> None:
        self.clear()
        if self.legend is None:
            self.legend = self.addLegend(offset=(8, 4), colCount=2)
        self.legend.clear()
        p = theme.current()
        self.legend.setLabelTextColor(p.muted)
        if not years:
            return
        pos = [max(v, 0) for v in flows]
        neg = [min(v, 0) for v in flows]
        self.addItem(pg.BarGraphItem(x=years, height=pos, width=0.66, brush=QColor(p.good), pen=pg.mkPen(None),
                                     name=labels[0]))
        self.addItem(pg.BarGraphItem(x=years, height=neg, width=0.66, brush=QColor(p.bad), pen=pg.mkPen(None)))
        cum, run = [], 0.0
        for v in flows:
            run += v
            cum.append(run)
        self.plot(years, cum, pen=pg.mkPen(p.accent, width=2), name=labels[1])
        lo, hi = min(min(neg), min(cum), 0), max(max(pos), max(cum), 1)
        self.setXRange(years[0] - 0.7, years[-1] + 0.7, padding=0)
        self.setYRange(lo * 1.1, hi * 1.1, padding=0)
        self.addLine(y=0, pen=pg.mkPen(p.faint, width=1))

    def restyle(self) -> None:
        style_plot(self)
