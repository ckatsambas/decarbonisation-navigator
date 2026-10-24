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
