"""Small, quiet animations (200–400 ms) that the user can switch off from the top bar.

`tween(owner, start, end, setter)` runs one eased value change; with animations off (or while
tests and screenshots run) the setter simply gets the end value at once.
"""
from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation

DURATION = 320
_enabled = os.environ.get("NAVIGATOR_ANIMATIONS", "1") != "0"


def enabled() -> bool:
    return _enabled


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)


def tween(owner: QObject, start: float, end: float, setter: Callable[[float], None], ms: int = DURATION,
          key: str = "_tween") -> None:
    """Animate a float from start to end, calling setter on every frame (a running one is replaced)."""
    old = getattr(owner, key, None)
    if old is not None:
        old.stop()
    if not _enabled or start == end:
        setter(end)
        return
    a = QVariantAnimation(owner)
    a.setStartValue(float(start))
    a.setEndValue(float(end))
    a.setDuration(ms)
    a.setEasingCurve(QEasingCurve.Type.OutCubic)
    a.valueChanged.connect(lambda v: setter(float(v)))
    a.finished.connect(lambda: setter(end))
    setattr(owner, key, a)
    a.start()
