"""Bilingual text and number formatting (Greek default, English).

Text lives in el.json / en.json as flat keys. `tr("nav.ship")` returns the text in the current
language; a missing key falls back to the other language, then to the key itself, so a gap is
visible but never crashes the app. Pure Python: the UI subscribes with `on_change`.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

LANGUAGES = ("el", "en")
DEFAULT = "el"
_DIR = Path(__file__).resolve().parent
_catalogues: dict[str, dict[str, str]] = {}
_current = DEFAULT
_listeners: list[Callable[[str], None]] = []


def catalogue(lang: str) -> dict[str, str]:
    if lang not in _catalogues:
        with (_DIR / f"{lang}.json").open(encoding="utf-8") as fh:
            _catalogues[lang] = json.load(fh)
    return _catalogues[lang]


def language() -> str:
    return _current


def set_language(lang: str) -> None:
    global _current
    if lang not in LANGUAGES:
        raise ValueError(f"Unsupported language: {lang}")
    if lang == _current:
        return
    _current = lang
    for cb in tuple(_listeners):   # copy: a listener may unsubscribe while we iterate
        cb(lang)


def on_change(cb: Callable[[str], None]) -> Callable[[], None]:
    """Subscribe to language changes; returns a function that unsubscribes."""
    _listeners.append(cb)
    return lambda: _listeners.remove(cb) if cb in _listeners else None


def tr(key: str, **kwargs) -> str:
    text = catalogue(_current).get(key)
    if text is None:
        other = next(lang for lang in LANGUAGES if lang != _current)
        text = catalogue(other).get(key, key)
    return text.format(**kwargs) if kwargs else text


def pick(texts: dict[str, str]) -> str:
    """Choose from an inline {"el": ..., "en": ...} dict (used by config files)."""
    return texts.get(_current) or next(iter(texts.values()), "")


# ------------------------------------------------------------------ numbers
def num(x: float, digits: int = 0) -> str:
    s = f"{abs(x):,.{digits}f}"
    if _current == "el":                       # 1.234.567,89
        s = s.replace(",", " ").replace(".", ",").replace(" ", ".")
    sign = "−" if x < 0 and round(abs(x), digits) != 0 else ""
    return sign + s


def eur(x: float, digits: int = 0) -> str:
    return f"{num(x, digits)} €" if _current == "el" else f"€{num(x, digits)}"


def eur_short(x: float) -> str:
    """Compact money: 1,25 εκ. € / €1.25m; 840 χιλ. € / €840k."""
    a = abs(x)
    if a >= 1e6:
        return f"{num(x / 1e6, 2)} εκ. €" if _current == "el" else f"€{num(x / 1e6, 2)}m"
    if a >= 1e4:
        return f"{num(x / 1e3, 0)} χιλ. €" if _current == "el" else f"€{num(x / 1e3, 0)}k"
    return eur(x)


def pct(x: float, digits: int = 0) -> str:
    return f"{num(x * 100, digits)}%"
