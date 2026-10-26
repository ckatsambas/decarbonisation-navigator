"""Fan of futures (decision 0012).

Every thin line is one SMAA future for the chosen option: its cumulative discounted cash flow from
today to the end of the horizon, so where a line ends is that future's NPV. Lines that end above
zero are drawn in blue (the investment pays back), the others in red. On the right, the distribution
of the NPV over all futures, with the two shares written large. The best and the worst futures are
named by what drove them (carbon price, IMO outcome, fuel prices).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QToolTip

from ..i18n import eur_short, pct
from . import theme
from .charts import AnimatedChart, Morph, money_tick, nice_range, with_alpha

GAIN = {"light": "#1F7FA0", "dark": "#5CC3D6"}
LOSS = "#D23B2E"


def smooth_path(xs, ys) -> QPainterPath:
    """Catmull–Rom through the points, as cubic Béziers."""
    path = QPainterPath(QPointF(xs[0], ys[0]))
    n = len(xs)
    for k in range(n - 1):
        x0, y0 = (xs[k - 1], ys[k - 1]) if k > 0 else (xs[k], ys[k])
        x1, y1, x2, y2 = xs[k], ys[k], xs[k + 1], ys[k + 1]
        x3, y3 = (xs[k + 2], ys[k + 2]) if k + 2 < n else (x2, y2)
        path.cubicTo(x1 + (x2 - x0) / 6, y1 + (y2 - y0) / 6, x2 - (x3 - x1) / 6, y2 - (y3 - y1) / 6, x2, y2)
    return path


class FanChart(AnimatedChart):
    def __init__(self):
        super().__init__(440)
        self.years: list[int] = []
        self._paths = Morph()
        self._dens = Morph()
        self._scale = Morph()
        self._ticks: list[float] = []
        self.finals = np.zeros(0)
        self.texts: dict[str, str] = {}
        self.extremes: tuple[int, int] = (-1, -1)
        self._reveal = False
        self._lines: tuple | None = None

    def set_data(self, years, paths, finals, texts: dict[str, str]) -> None:
        """paths: (P, Y) cumulative discounted cash flow of a subsample; finals: (N,) NPV of all futures.
        texts: gain, loss (with {share}), median (with {v}), best, worst, today."""
        paths = np.asarray(paths, float)
        finals = np.asarray(finals, float)
        self._reveal = self._paths.new is None or self._paths.new.shape != paths.shape or list(years) != self.years
        if self._reveal:
            self._paths.new = None
            self._dens.new = None
            self._scale.new = None
        self._lines = None
        self.years, self.texts, self.finals = list(years), dict(texts), finals
        # zero at "today" in front of the first year
        full = np.concatenate([np.zeros((len(paths), 1)), paths], axis=1)
        lo_q, hi_q = np.quantile(full, [0.005, 0.995]) if full.size else (0, 1)
        lo, hi, self._ticks = nice_range(min(lo_q, np.quantile(finals, 0.005)), max(hi_q, np.quantile(finals, 0.995)))
        self._paths.set(full, self._t)
        self._scale.set([lo, hi], self._t, start=[lo, hi])
        bins = np.linspace(lo, hi, 90)
        h, _ = np.histogram(np.clip(finals, lo, hi), bins=bins)
        kern = np.exp(-0.5 * (np.arange(-6, 7) / 2.2) ** 2)
        dens = np.convolve(h.astype(float), kern / kern.sum(), mode="same")
        self._bins = (bins[:-1] + bins[1:]) / 2
        self._dens.set(dens / max(dens.max(), 1e-9), self._t)
        ends = full[:, -1]
        self.extremes = (int(np.argmax(ends)), int(np.argmin(ends))) if len(ends) else (-1, -1)
        self._start()

    def _layout(self):
        W, H = self.width(), self.height()
        plot = QRectF(70, 24, W * 0.58 - 70, H - 58)
        dens = QRectF(plot.right() + 26, plot.top(), W * 0.13, plot.height())
        return plot, dens

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        if not self.years or self._paths.new is None:
            return
        g = self.painter()
        p = theme.current()
        gain, loss = QColor(GAIN[p.name]), QColor(LOSS)
        plot, dens_r = self._layout()
        lo, hi = self._scale.at(self._t)
        span = (hi - lo) or 1.0

        def y(v):
            return plot.bottom() - (v - lo) / span * plot.height()

        top_abs = max(abs(lo), abs(hi))
        g.setFont(theme.ui_font(8))
        for tv in self._ticks:
            yy = y(tv)
            if yy < plot.top() - 2 or yy > plot.bottom() + 2:
                continue
            g.setPen(QPen(theme.c("grid"), 1))
            g.drawLine(QPointF(plot.left(), yy), QPointF(plot.right(), yy))
            g.setPen(theme.c("faint"))
            g.drawText(QRectF(0, yy - 8, plot.left() - 10, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       money_tick(tv, top_abs))
        ny = len(self.years) + 1
        xs = [plot.left() + plot.width() * k / (ny - 1) for k in range(ny)]
        for k, yr in enumerate(self.years, start=1):
            if k == 1 or k == ny - 1 or yr % 5 == 0:
                g.drawText(QRectF(xs[k] - 20, plot.bottom() + 6, 40, 14), Qt.AlignmentFlag.AlignCenter, str(yr))
        # break-even line
        g.setPen(QPen(theme.c("muted"), 1, Qt.PenStyle.DashLine))
        g.drawLine(QPointF(plot.left(), y(0)), QPointF(dens_r.right() + 4, y(0)))
        # the fan: the full set of smooth lines is drawn once into a cached layer; while lines morph
        # from one option to another a lighter subset is drawn live
        paths = self._paths.at(self._t)
        g.save()
        clip_w = plot.width() * (self._t if self._reveal else 1.0) + 2
        g.setClipRect(QRectF(plot.left() - 2, plot.top() - 4, clip_w, plot.height() + 8))
        if self._reveal or self._t >= 1.0:
            g.drawPixmap(0, 0, self._line_layer(xs, y, gain, loss))
        else:
            self._draw_lines(g, paths, xs, y, gain, loss, step=4, smooth=False)
        # best and worst named
        g.setFont(theme.ui_font(8.5))
        for k, key, col in ((self.extremes[0], "best", gain), (self.extremes[1], "worst", loss)):
            if k < 0 or not self.texts.get(key):
                continue
            g.setPen(QPen(with_alpha(col, 0.9), 1.6))
            g.drawPath(smooth_path(xs, [y(v) for v in paths[k]]))
        g.restore()
        # origin: today
        o = QPointF(xs[0], y(0))
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(theme.c("text"))
        g.drawEllipse(o, 4, 4)
        g.setPen(QPen(theme.c("faint"), 1.2, Qt.PenStyle.DotLine))
        g.drawLine(QPointF(o.x(), o.y() + 6), QPointF(o.x(), o.y() + 34))
        g.setPen(theme.c("muted"))
        g.setFont(theme.ui_font(8.5))
        g.drawText(QRectF(o.x() - 60, o.y() + 36, 120, 30), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                   self.texts.get("today", ""))
        # distribution of the NPV
        dens = self._dens.at(self._t)
        top_y = y(hi)
        g.setPen(QPen(theme.c("muted"), 1))
        g.drawLine(QPointF(dens_r.left(), plot.top()), QPointF(dens_r.left(), plot.bottom()))
        for sign, col in ((1, gain), (-1, loss)):
            path = QPainterPath()
            started = False
            pts = []
            for b, d in zip(self._bins, dens, strict=True):
                if (b >= 0) != (sign > 0):
                    continue
                pts.append((b, d))
            if not pts:
                continue
            path.moveTo(dens_r.left(), y(pts[0][0]))
            for b, d in pts:
                path.lineTo(dens_r.left() + d * dens_r.width(), y(b))
                started = True
            path.lineTo(dens_r.left(), y(pts[-1][0]))
            path.closeSubpath()
            if started:
                g.setPen(QPen(col, 1.4))
                g.setBrush(with_alpha(col, 0.42))
                g.drawPath(path)
        del top_y
        # shares written large
        n = max(len(self.finals), 1)
        share_gain = float((self.finals >= 0).sum()) / n
        tx = dens_r.right() + 18
        tw = self.width() - tx - 8
        for share, key, col, anchor in ((share_gain, "gain", gain, max(hi * 0.45, 0)),
                                        (1 - share_gain, "loss", loss, min(lo * 0.45, 0))):
            if share <= 0.0005:
                continue
            yy = min(max(y(anchor), plot.top() + 28), plot.bottom() - 60)
            g.setPen(col)
            g.setFont(theme.ui_font(24, QFont.Weight.DemiBold))
            g.drawText(QRectF(tx, yy - 34, tw, 38), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, pct(share))
            g.setFont(theme.ui_font(9.5))
            g.drawText(QRectF(tx, yy + 4, tw, 54), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                       self.texts.get(key, ""))
        # median
        med = float(np.median(self.finals))
        g.setPen(QPen(theme.c("text"), 1, Qt.PenStyle.DotLine))
        g.drawLine(QPointF(dens_r.left() - 6, y(med)), QPointF(dens_r.right(), y(med)))
        g.setFont(theme.ui_font(8))
        g.setPen(theme.c("text"))
        g.drawText(QRectF(dens_r.left() - 4, y(med) - 15, dens_r.width() + 120, 14), Qt.AlignmentFlag.AlignLeft,
                   self.texts.get("median", "").format(v=eur_short(med)))
        # names of the extremes, dotted to the right edge of the fan
        fm = QFontMetricsF(theme.ui_font(8.5))
        g.setFont(theme.ui_font(8.5))
        for k, key, col in ((self.extremes[0], "best", gain), (self.extremes[1], "worst", loss)):
            txt = self.texts.get(key)
            if k < 0 or not txt:
                continue
            v = paths[k][-1]
            yy = min(max(y(v), plot.top() + 6), plot.bottom() - 6)
            g.setPen(QPen(with_alpha(col, 0.8), 1, Qt.PenStyle.DotLine))
            g.drawLine(QPointF(plot.right() + 3, yy), QPointF(dens_r.left() - 3, yy))
            g.setPen(with_alpha(p.muted, 1.0))
            w = min(fm.horizontalAdvance(txt) + 4, plot.width() * 0.6)
            above = key == "best" or yy > plot.bottom() - 34
            g.drawText(QRectF(plot.right() - w - 6, yy + (-17 if above else 3), w, 14),
                       Qt.AlignmentFlag.AlignRight, fm.elidedText(txt, Qt.TextElideMode.ElideRight, w))
        g.end()

    def _draw_lines(self, g, paths, xs, y, gain, loss, step: int = 1, smooth: bool = True) -> None:
        ends = self._paths.new[:, -1]
        alpha = min(0.16, max(0.035, 9.0 / max(len(paths), 1))) * (1.8 if step > 1 else 1.0)
        g.setBrush(Qt.BrushStyle.NoBrush)
        for sign, col in ((1, gain), (-1, loss)):
            idx = (np.where(ends >= 0)[0] if sign > 0 else np.where(ends < 0)[0])[::step]
            g.setPen(QPen(with_alpha(col, alpha), 1.3))
            for k in idx:
                ys = [y(v) for v in paths[k]]
                if smooth:
                    g.drawPath(smooth_path(xs, ys))
                else:
                    g.drawPolyline([QPointF(a, b) for a, b in zip(xs, ys, strict=True)])

    def _line_layer(self, xs, y, gain, loss) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, theme.current().name)
        if self._lines is not None and self._lines[0] == key:
            return self._lines[1]
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_lines(q, self._paths.new, xs, y, gain, loss)
        q.end()
        self._lines = (key, pm)
        return pm

    def resizeEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(e)
        self._lines = None

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if not self.years or self._paths.new is None:
            return
        plot, dens_r = self._layout()
        if dens_r.adjusted(0, 0, 40, 0).contains(e.position()):
            lo, hi = self._scale.at(1.0)
            v = lo + (plot.bottom() - e.position().y()) / plot.height() * (hi - lo)
            share = float((self.finals <= v).mean())
            QToolTip.showText(e.globalPosition().toPoint(), f"NPV ≤ {eur_short(v)}: {pct(share)}", self)
