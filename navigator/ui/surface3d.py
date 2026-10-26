"""Turnable 3D surface of the recommendation's lead (decision 0012).

Floor: every split of weight between two criteria families (the triangle of the priority map).
Height: the recommended option's SAW score minus the best other option's score at that split. The
translucent "sea" is zero: where the land rises above it the recommendation stays first (warm
colours, deeper with height), where it sinks another option wins (cool colours). The exact borders
between winners are drawn on the surface with each winner's name. The company's weights are the red
buoy. The scene turns slowly by itself; drag to turn and tilt it.

Drawn with QPainter (painter's algorithm, smooth shading by height): no OpenGL, so nothing changes in
packaging.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF

from ..i18n import pct
from . import anim, theme
from .charts import AnimatedChart, Morph, with_alpha
from .maps import RED, mix

N = 32
HEIGHT = 0.40
COOL = "#4E79A7"
LIGHT = np.array([-0.35, -0.45, 0.82]) / np.linalg.norm([-0.35, -0.45, 0.82])


def _triangles(n: int) -> np.ndarray:
    """Triangles that tile the floor a + b ≤ 1 exactly on an (n + 1)² grid, as vertex index pairs."""
    out = []
    for i in range(n):
        for j in range(n - i):
            out.append(((i, j), (i + 1, j), (i, j + 1)))
            if i + j < n - 1:
                out.append(((i + 1, j), (i + 1, j + 1), (i, j + 1)))
    return np.array(out, int)


TRIS = _triangles(N)


class Surface3D(AnimatedChart):
    SPIN = 0.12          # radians per second

    def __init__(self):
        super().__init__(480)
        self.yaw, self.pitch = -0.55, 1.02
        self._z = Morph()
        self._dot = Morph()
        self.colors: list[str] = []
        self.names: list[str] = []
        self.regions: list[list[tuple[float, float]]] = []
        self.coef = (np.zeros(1), np.zeros(1), np.zeros(1))
        self.best = 0
        self.axis = ("", "")
        self.texts = ("", "", "")      # you, above, below
        self._drag: QPointF | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._spin)
        self.zmax = 1.0

    def showEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().showEvent(e)
        if anim.enabled():
            self._timer.start()

    def hideEvent(self, e) -> None:  # noqa: N802 - Qt API
        super().hideEvent(e)
        self._timer.stop()

    def _spin(self) -> None:
        if not anim.enabled():
            self._timer.stop()
            return
        if self._drag is None:
            self.yaw += self.SPIN * self._timer.interval() / 1000
            self.update()

    def lead(self, a, b):
        """Exact lead of the recommendation at (a, b) (arrays allowed), divided by the largest |lead|."""
        s0, sa, sb = self.coef
        a, b = np.asarray(a, float), np.asarray(b, float)
        sc = s0 + a[..., None] * sa + b[..., None] * sb
        others = np.delete(sc, self.best, axis=-1)
        top = others.max(axis=-1) if others.shape[-1] else 0.0
        return (sc[..., self.best] - top) / self.zmax

    def set_data(self, s0, sa, sb, best: int, colors, names, regions, dot, axis, texts) -> None:
        """Scores are affine in the two family weights: s(a, b) = s0 + a·sa + b·sb (one entry per option);
        `regions` are the exact winner polygons (ranking.winner_regions)."""
        self.coef = tuple(np.asarray(v, float) for v in (s0, sa, sb))
        self.best = best
        self.zmax = 1.0
        g = np.linspace(0, 1, N + 1)
        A, B = np.meshgrid(g, g, indexing="ij")
        raw = self.lead(A, B)
        self.zmax = max(float(np.abs(raw[A + B <= 1 + 1e-9]).max(initial=0)), 1e-6)
        self.colors, self.names, self.axis, self.texts = list(colors), list(names), axis, texts
        self.regions = [list(r) for r in regions]
        self._z.set(raw / self.zmax, self._t)
        d = np.asarray(dot, float)
        self._dot.set([d[0], d[1], float(self.lead(d[0], d[1]))], self._t)
        self._start()
        if anim.enabled() and self.isVisible() and not self._timer.isActive():
            self._timer.start()

    # ------------------------------------------------------------------ projection
    def _project(self, x, y, z, cx, cy, scale):
        X = np.asarray(x, float) - 1 / 3
        Y = np.asarray(y, float) - 1 / 3
        Z = np.asarray(z, float) * HEIGHT
        cyaw, syaw = math.cos(self.yaw), math.sin(self.yaw)
        xr = X * cyaw - Y * syaw
        yr = X * syaw + Y * cyaw
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        depth = yr * sp - Z * cp            # larger = further away
        sy = -(yr * cp + Z * sp)
        persp = 1 / (1 + 0.35 * depth)
        return cx + xr * scale * persp, cy + sy * scale * persp, depth

    def _ramp(self, h: np.ndarray, p) -> np.ndarray:
        """RGB (0–255) for heights h ∈ [−1, 1]: warm above the sea, cool below, deeper with |h|."""
        def rgb(c):
            q = QColor(c)
            return np.array([q.red(), q.green(), q.blue()], float)
        red, cool, panel = rgb(RED), rgb(COOL), rgb(p.panel)
        k = np.abs(np.clip(h, -1, 1))[:, None] ** 0.7
        warm = (panel + (red - panel) * 0.30) + (red - (panel + (red - panel) * 0.30)) * k
        cold = (panel + (cool - panel) * 0.30) + (cool - (panel + (cool - panel) * 0.30)) * k
        return np.where((h >= 0)[:, None], warm, cold)

    def _colour(self, h: float, light: float, p) -> QColor:
        if h >= 0:
            c = mix(mix(RED, p.panel, 0.70), RED, min(h, 1.0) ** 0.7)
        else:
            c = mix(mix(COOL, p.panel, 0.70), COOL, min(-h, 1.0) ** 0.7)
        return QColor(int(c.red() * light), int(c.green() * light), int(c.blue() * light))

    def paintEvent(self, _e) -> None:  # noqa: N802 - Qt API
        z = self._z.at(self._t)
        if z is None:
            return
        g = self.painter()
        p = theme.current()
        W, H = self.width(), self.height()
        cx, cy, scale = W / 2 + 40, H / 2 + 10, min(W * 0.6, H * 1.05)
        grid = np.linspace(0, 1, N + 1)
        A, B = np.meshgrid(grid, grid, indexing="ij")
        px, py, depth = self._project(A, B, z, cx, cy, scale)
        T = TRIS                                   # (T, 3, 2) vertex indices
        ti, tj = T[..., 0], T[..., 1]
        tz = z[ti, tj]                              # (T, 3)
        order = np.argsort(-depth[ti, tj].mean(axis=1), kind="stable")
        P = np.stack([A[ti, tj], B[ti, tj], tz * HEIGHT], axis=-1)      # (T, 3, 3)
        nrm = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True).clip(1e-12)
        lam = 0.72 + 0.28 * np.abs(nrm @ LIGHT)
        h = tz.mean(axis=1)
        rgb = self._ramp(h, p) * lam[:, None]
        rgb = rgb.clip(0, 255).astype(int)
        X, Y = px[ti, tj], py[ti, tj]
        sx, sy, _ = self._project(np.array([0, 1, 0]), np.array([0, 0, 1]), np.zeros(3), cx, cy, scale)
        sea = QPolygonF([QPointF(sx[k], sy[k]) for k in range(3)])
        # floor shadow of the sea, then the sunken land, the sea surface, the land above
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(with_alpha(COOL, 0.08))
        g.drawPolygon(sea)
        sunk = h < 0
        g.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for group in (order[sunk[order]], order[~sunk[order]]):
            for k in group:
                col = QColor(int(rgb[k, 0]), int(rgb[k, 1]), int(rgb[k, 2]))
                g.setBrush(col)
                g.setPen(col)
                g.drawPolygon(QPolygonF([QPointF(X[k, 0], Y[k, 0]), QPointF(X[k, 1], Y[k, 1]),
                                         QPointF(X[k, 2], Y[k, 2])]))
            if group is not None and len(group) and sunk[group[0]]:
                g.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                g.setPen(QPen(with_alpha(COOL, 0.7), 1.2))
                g.setBrush(with_alpha("#9CC3DA" if p.name == "light" else "#2E5C7A", 0.42))
                g.drawPolygon(sea)
                g.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        g.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # exact borders between winners, laid on the surface, with names
        g.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold))
        fm = QFontMetricsF(g.font())
        for i, poly in enumerate(self.regions):
            if len(poly) < 3:
                continue
            pts = []
            for k in range(len(poly)):
                (a0, b0), (a1, b1) = poly[k], poly[(k + 1) % len(poly)]
                t = np.linspace(0, 1, 12)
                aa, bb = a0 + (a1 - a0) * t, b0 + (b1 - b0) * t
                x_, y_, _ = self._project(aa, bb, self.lead(aa, bb), cx, cy, scale)
                pts += [QPointF(float(u), float(v)) for u, v in zip(x_, y_, strict=True)]
            g.setPen(QPen(with_alpha("#FFFFFF", 0.85), 1.4))
            g.setBrush(Qt.BrushStyle.NoBrush)
            g.drawPolygon(QPolygonF(pts))
            area = abs(sum(poly[k][0] * poly[(k + 1) % len(poly)][1] - poly[(k + 1) % len(poly)][0] * poly[k][1]
                           for k in range(len(poly)))) / 2
            if area < 0.015:
                continue
            ca = sum(a for a, _ in poly) / len(poly)
            cb = sum(b for _, b in poly) / len(poly)
            x_, y_, _ = self._project(np.array(ca), np.array(cb), np.array(float(self.lead(ca, cb))), cx, cy, scale)
            dz = self._dot.at(1.0)
            bx_, by_, _ = self._project(np.array(dz[0]), np.array(dz[1]), np.array(dz[2]), cx, cy, scale)
            if math.hypot(float(x_) - float(bx_), float(y_) - float(by_)) < 44:
                y_ = float(by_) + 30
            txt = fm.elidedText(self.names[i], Qt.TextElideMode.ElideRight, 170)
            w = fm.horizontalAdvance(txt) + 14
            box = QRectF(float(x_) - w / 2, float(y_) - 10, w, 20)
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(with_alpha(p.panel, 0.82))
            g.drawRoundedRect(box, 9, 9)
            g.setBrush(QColor(self.colors[i]))
            g.drawEllipse(QPointF(box.left() + 8, box.center().y()), 3.5, 3.5)
            g.setPen(theme.c("text"))
            g.drawText(box.adjusted(12, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, txt)
        # corners
        g.setFont(theme.ui_font(8.5))
        for a, b, txt in ((1, 0, f"{self.axis[0]} 100%"), (0, 1, f"{self.axis[1]} 100%"), (0, 0, "0% · 0%")):
            x_, y_, _ = self._project(np.array(a), np.array(b), np.array(0.0), cx, cy, scale)
            g.setPen(theme.c("muted"))
            g.drawText(QRectF(float(x_) - 90, float(y_) + 8, 180, 16), Qt.AlignmentFlag.AlignCenter, txt)
        # the company's buoy
        d = self._dot.at(self._t)
        bx, by, _ = self._project(np.array(d[0]), np.array(d[1]), np.array(d[2]), cx, cy, scale)
        fx, fy, _ = self._project(np.array(d[0]), np.array(d[1]), np.array(0.0), cx, cy, scale)
        g.setPen(QPen(QColor(RED), 1.8, Qt.PenStyle.DashLine))
        g.drawLine(QPointF(float(fx), float(fy)), QPointF(float(bx), float(by)))
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(with_alpha(RED, 0.35))
        g.drawEllipse(QPointF(float(fx), float(fy)), 5, 2.5)
        g.setPen(QPen(QColor("#FFFFFF"), 2.5))
        g.setBrush(QColor(RED))
        g.drawEllipse(QPointF(float(bx), float(by)), 8, 8)
        g.setFont(theme.ui_font(9, QFont.Weight.DemiBold))
        g.setPen(QColor(RED))
        g.drawText(QPointF(float(bx) + 13, float(by) - 9), f"{self.texts[0]} · {pct(float(d[2]) * self.zmax)}")
        # key: height scale
        x0, y0 = 12.0, 10.0
        g.setFont(theme.ui_font(8.5))
        for k in range(40):
            h = 1 - 2 * k / 39
            g.setPen(Qt.PenStyle.NoPen)
            g.setBrush(self._colour(h, 1.0, p))
            g.drawRect(QRectF(x0, y0 + k * 4, 12, 4.2))
        g.setPen(theme.c("muted"))
        g.drawText(QRectF(x0 + 18, y0 - 4, 260, 34), Qt.TextFlag.TextWordWrap,
                   f"+{pct(self.zmax)}  {self.texts[1]}")
        g.drawText(QRectF(x0 + 18, y0 + 72, 260, 16), Qt.AlignmentFlag.AlignLeft, "0")
        g.drawText(QRectF(x0 + 18, y0 + 130, 260, 34), Qt.TextFlag.TextWordWrap, f"−{pct(self.zmax)}  {self.texts[2]}")
        g.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802 - Qt API
        self._drag = e.position()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802 - Qt API
        if self._drag is None:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        d = e.position() - self._drag
        self._drag = e.position()
        self.yaw += d.x() * 0.01
        self.pitch = min(max(self.pitch + d.y() * 0.006, 0.2), 1.45)
        self.update()

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802 - Qt API
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
