"""Visual identity: maritime-eco. 'Deep Sea' (dark, default) and 'Seafoam' (light).

Concept: a ship's bridge chart table rather than a web form. Deep-water surfaces, one sea-teal
accent for focus and totals, and semantic colours that always mean the same thing:
kelp = good / compliant, sand = warning, coral = cost / deficit.
Regime colours are fixed across every chart: EU ETS = blue, FuelEU = teal, IMO = violet.

Kept deliberately simple for now; the full design pass comes after the engine phases.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    sidebar: str
    panel: str
    panel_alt: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_text: str
    good: str
    warn: str
    bad: str
    grid: str
    ets: str
    fueleu: str
    imo: str


DEEP_SEA = Palette(
    name="dark", bg="#0B1A22", sidebar="#08141B", panel="#10232D", panel_alt="#152D39",
    border="#1F3B48", text="#E4EEEC", muted="#8FA7AE", faint="#56717A",
    accent="#3FB8AF", accent_text="#06141A", good="#7CC68D", warn="#E3B04B", bad="#E5806B",
    grid="#17303C", ets="#6FA8DC", fueleu="#3FB8AF", imo="#A99BE0")

SEAFOAM = Palette(
    name="light", bg="#EEF3F2", sidebar="#E1EAE9", panel="#FFFFFF", panel_alt="#F5F8F8",
    border="#CFDCDB", text="#10232B", muted="#556B72", faint="#93A5AA",
    accent="#0E6B73", accent_text="#FFFFFF", good="#2F7D4A", warn="#9A6A0C", bad="#B04A35",
    grid="#E3EBEA", ets="#2F6FA8", fueleu="#0E6B73", imo="#6650A8")

PALETTES = {p.name: p for p in (DEEP_SEA, SEAFOAM)}
_current: Palette = DEEP_SEA


def current() -> Palette:
    return _current


def set_current(p: Palette) -> None:
    global _current
    _current = p


def c(name: str) -> QColor:
    return QColor(getattr(_current, name))


def ui_font(size: float = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(["Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans", "DejaVu Sans"])
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def upper(text: str) -> str:
    """Greek capitals are written without accents (ΑΝΑΛΥΣΗ, not ΑΝΆΛΥΣΗ)."""
    import unicodedata
    nfd = unicodedata.normalize("NFD", text.upper())
    return unicodedata.normalize("NFC", "".join(ch for ch in nfd if ch not in ("́", "̈")))


def stylesheet(p: Palette) -> str:
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {p.text}; }}
QMainWindow, #Content {{ background: {p.bg}; }}
#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#Wordmark {{ font-size: 11.5pt; font-weight: 700; }}
#WordmarkSub {{ color: {p.muted}; font-size: 7.5pt; letter-spacing: 1.2px; }}
#NavGroup {{ color: {p.faint}; font-size: 7.5pt; letter-spacing: 1.6px; padding: 14px 18px 4px 18px; }}
QPushButton#NavButton {{
  text-align: left; padding: 9px 16px 9px 18px; border: none; border-left: 3px solid transparent;
  background: transparent; color: {p.muted}; font-size: 10pt; border-radius: 0; }}
QPushButton#NavButton:hover {{ color: {p.text}; background: {p.panel}; }}
QPushButton#NavButton:checked {{ color: {p.text}; background: {p.panel}; border-left: 3px solid {p.accent}; font-weight: 600; }}
#TopBar {{ background: {p.panel}; border-bottom: 1px solid {p.border}; }}
#TopLabel {{ color: {p.muted}; font-size: 8pt; letter-spacing: 1px; }}
#PageTitle {{ font-size: 17pt; font-weight: 600; }}
#PageLede {{ color: {p.muted}; font-size: 10pt; }}
#Panel {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 6px; }}
#PanelTitle {{ color: {p.muted}; font-size: 8pt; font-weight: 600; letter-spacing: 1.4px; }}
#Muted {{ color: {p.muted}; }}
#Faint {{ color: {p.faint}; font-size: 8.5pt; }}
#KpiLabel {{ color: {p.muted}; font-size: 7.5pt; font-weight: 600; letter-spacing: 1.2px; }}
#KpiValue {{ font-size: 17pt; font-weight: 600; }}
#Placeholder {{ background: {p.panel}; border: 1px dashed {p.border}; border-radius: 6px; padding: 24px; color: {p.muted}; }}
#Warning {{ background: {p.panel_alt}; border-left: 3px solid {p.warn}; border-radius: 3px; padding: 8px 12px; }}

QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
  background: {p.panel_alt}; border: 1px solid {p.border}; border-radius: 4px; padding: 5px 8px;
  selection-background-color: {p.accent}; selection-color: {p.accent_text}; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {p.accent}; }}
QDoubleSpinBox, QSpinBox {{ font-weight: 600; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {p.panel}; border: 1px solid {p.border}; selection-background-color: {p.panel_alt}; selection-color: {p.text}; }}

QPushButton {{ background: {p.panel_alt}; border: 1px solid {p.border}; border-radius: 4px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {p.muted}; }}
QPushButton#Segment {{ border-radius: 0; padding: 4px 12px; min-width: 34px; }}
QPushButton#Segment:checked {{ background: {p.accent}; color: {p.accent_text}; border-color: {p.accent}; font-weight: 600; }}

QTableView, QTableWidget {{ background: {p.panel}; alternate-background-color: {p.panel_alt}; border: 1px solid {p.border};
  gridline-color: {p.grid}; border-radius: 4px; }}
QHeaderView::section {{ background: {p.panel_alt}; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
  padding: 6px 8px; font-size: 8pt; font-weight: 600; }}
QTableCornerButton::section {{ background: {p.panel_alt}; border: none; }}

QTabBar::tab {{ background: transparent; color: {p.muted}; padding: 8px 16px; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; font-weight: 600; }}
QTabWidget::pane {{ border: none; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}
QToolTip {{ background: {p.panel}; color: {p.text}; border: 1px solid {p.border}; padding: 6px; }}
QStatusBar {{ background: {p.sidebar}; color: {p.muted}; }}
"""
