"""Visual identity: nautical chart.

'Chart' (light, default): warm chart-paper background, navy ink, sea-teal accent, soft depth
contours. 'Night bridge' (dark): the same chart under a bridge's night lighting.
Semantic colours always mean the same thing (good / warning / cost), and the regimes keep fixed
colours across every chart: EU ETS = blue, FuelEU = green-teal, IMO = violet.
See docs/decisions/0006-guided-interface.md.
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
    contour: str          # depth-contour lines on backgrounds
    shallow: str          # tint for highlighted areas (like shallow water on a chart)


CHART = Palette(
    name="light", bg="#F4F1EA", sidebar="#ECE7DC", panel="#FFFDF8", panel_alt="#F1EDE4",
    border="#DDD6C8", text="#13283A", muted="#56677A", faint="#97A3AE",
    accent="#0F6E78", accent_text="#FFFFFF", good="#2E7D4F", warn="#A36A00", bad="#B3472F",
    grid="#E8E2D6", ets="#2F6FA8", fueleu="#2A9D8F", imo="#6A55A8",
    contour="#D3E2E2", shallow="#E3EFEE")

NIGHT = Palette(
    name="dark", bg="#0A1622", sidebar="#08121C", panel="#0F2030", panel_alt="#14293B",
    border="#22394D", text="#DCE7EE", muted="#8EA3B3", faint="#587287",
    accent="#46C2B8", accent_text="#06141C", good="#7CC68D", warn="#E9B44C", bad="#E5806B",
    grid="#16293A", ets="#6FA8DC", fueleu="#5CC9A7", imo="#A99BE0",
    contour="#13283A", shallow="#102536")

PALETTES = {p.name: p for p in (CHART, NIGHT)}
DEFAULT = CHART
_current: Palette = DEFAULT


def current() -> Palette:
    return _current


def set_current(p: Palette) -> None:
    global _current
    _current = p


def c(name: str) -> QColor:
    return QColor(getattr(_current, name))


FAMILIES = ["Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans", "DejaVu Sans"]


def ui_font(size: float = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(FAMILIES)
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
QMainWindow, #Content, #Lobby, #ProjectBody {{ background: {p.bg}; }}

/* ---------- top bar */
#TopBar {{ background: {p.panel}; border-bottom: 1px solid {p.border}; }}
#Wordmark {{ font-size: 11pt; font-weight: 700; letter-spacing: 0.3px; }}
#WordmarkSub {{ color: {p.muted}; font-size: 7.5pt; letter-spacing: 1.4px; }}
#TopLabel {{ color: {p.faint}; font-size: 8pt; letter-spacing: 1px; }}
QPushButton#Back {{ background: transparent; border: none; color: {p.muted}; padding: 4px 6px; font-size: 10pt; }}
QPushButton#Back:hover {{ color: {p.accent}; }}
QLineEdit#ProjectName {{ background: transparent; border: 1px solid transparent; font-size: 12pt; font-weight: 600;
  padding: 3px 6px; min-width: 260px; }}
QLineEdit#ProjectName:hover {{ border: 1px dashed {p.border}; }}
QLineEdit#ProjectName:focus {{ border: 1px solid {p.accent}; background: {p.panel_alt}; }}
#Saved {{ color: {p.faint}; font-size: 8.5pt; }}

/* ---------- lobby */
#Eyebrow {{ color: {p.accent}; font-size: 8.5pt; font-weight: 700; letter-spacing: 2px; }}
#Hero {{ font-size: 26pt; font-weight: 700; }}
#HeroLede {{ color: {p.muted}; font-size: 11.5pt; }}
#SectionTitle {{ color: {p.muted}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1.6px; }}
QFrame#Card {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 10px; }}
QFrame#Card:hover {{ border: 1px solid {p.accent}; }}
#CardTitle {{ font-size: 12.5pt; font-weight: 600; }}
#CardMeta {{ color: {p.muted}; font-size: 9pt; }}
#CardValue {{ font-size: 15pt; font-weight: 600; color: {p.accent}; }}
#CardValueLabel {{ color: {p.faint}; font-size: 7.5pt; font-weight: 700; letter-spacing: 1.2px; }}
QFrame#NewCard {{ background: {p.shallow}; border: 1px dashed {p.accent}; border-radius: 10px; }}
QFrame#NewCard:hover {{ background: {p.panel}; }}
#NewCardTitle {{ font-size: 13pt; font-weight: 600; color: {p.accent}; }}
QToolButton#CardMenu {{ border: none; background: transparent; color: {p.faint}; font-size: 14pt; padding: 0 4px; }}
QToolButton#CardMenu:hover {{ color: {p.accent}; }}
QToolButton#CardMenu::menu-indicator {{ image: none; }}
#Footer {{ color: {p.faint}; font-size: 8.5pt; }}
QPushButton#Link {{ background: transparent; border: none; color: {p.accent}; padding: 0; font-size: 8.5pt; }}
QPushButton#Link:hover {{ text-decoration: underline; }}

/* ---------- project: steps */
#StepBar {{ background: {p.panel}; border-bottom: 1px solid {p.border}; }}
#NavBar {{ background: {p.panel}; border-top: 1px solid {p.border}; }}
#StepHint {{ color: {p.faint}; font-size: 9pt; }}
#Question {{ font-size: 20pt; font-weight: 700; }}
#QuestionLede {{ color: {p.muted}; font-size: 10.5pt; }}
#Sentence {{ font-size: 11.5pt; background: {p.shallow}; border-left: 3px solid {p.accent}; border-radius: 4px;
  padding: 12px 16px; }}
#BigNumber {{ font-size: 22pt; font-weight: 700; }}
#BigLabel {{ color: {p.muted}; font-size: 8pt; font-weight: 700; letter-spacing: 1.3px; }}
#BigSub {{ color: {p.faint}; font-size: 8.5pt; }}
#Upcoming {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 10px; padding: 26px; }}
#Badge {{ color: {p.accent}; background: {p.shallow}; border-radius: 9px; padding: 2px 10px; font-size: 8pt; font-weight: 700;
  letter-spacing: 1px; }}

/* ---------- shared content */
#PageTitle {{ font-size: 17pt; font-weight: 600; }}
#PageLede {{ color: {p.muted}; font-size: 10pt; }}
#Panel {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 8px; }}
#PanelTitle {{ color: {p.muted}; font-size: 8pt; font-weight: 700; letter-spacing: 1.4px; }}
#Muted {{ color: {p.muted}; }}
#Faint {{ color: {p.faint}; font-size: 8.5pt; }}
#KpiLabel {{ color: {p.muted}; font-size: 7.5pt; font-weight: 700; letter-spacing: 1.2px; }}
#KpiValue {{ font-size: 17pt; font-weight: 600; }}
#Placeholder {{ background: {p.panel}; border: 1px dashed {p.border}; border-radius: 6px; padding: 24px; color: {p.muted}; }}
QToolButton#ReadMore {{ border: none; background: transparent; color: {p.faint}; font-size: 8.5pt; padding: 0; }}
QToolButton#ReadMore:hover, QToolButton#ReadMore:checked {{ color: {p.accent}; }}
#ReadMoreBody {{ color: {p.muted}; font-size: 8.5pt; background: {p.panel_alt}; border-radius: 4px; padding: 8px 10px; }}
QToolButton#Fold {{ border: none; border-top: 1px solid {p.border}; background: transparent; color: {p.muted};
  font-size: 9.5pt; font-weight: 600; padding: 12px 0 6px 0; text-align: left; }}
QToolButton#Fold:hover, QToolButton#Fold:checked {{ color: {p.accent}; }}
#Estimate {{ color: {p.warn}; font-size: 8.5pt; }}
#Warn {{ color: {p.bad}; font-size: 9.5pt; }}
QToolButton#Reset {{ font-size: 15pt; color: {p.muted}; background: transparent; border: 1px solid {p.border};
    border-radius: 14px; min-width: 26px; min-height: 26px; padding: 0 0 2px 0; }}
QToolButton#Star, QToolButton#Cross {{ color: {p.faint}; background: transparent; border: 1px solid transparent;
    border-radius: 4px; min-width: 22px; min-height: 22px; font-size: 11pt; }}
QToolButton#Star:hover, QToolButton#Cross:hover {{ border-color: {p.border}; }}
QToolButton#Star:checked {{ color: #D9A441; border-color: #D9A441; background: {p.panel_alt}; }}
QToolButton#Cross:checked {{ color: {p.bad}; border-color: {p.bad}; background: {p.panel_alt}; }}
#JudgeName {{ font-size: 9.5pt; }}
QToolButton#ViewChip {{ color: {p.faint}; background: {p.panel}; border: 1px solid {p.border}; border-radius: 4px;
    min-width: 22px; min-height: 20px; padding: 0 3px; font-size: 10pt; }}
QToolButton#ViewChip:hover {{ color: {p.accent}; border-color: {p.accent}; }}
QToolButton#ViewChip:checked {{ color: {p.accent_text}; background: {p.accent}; border-color: {p.accent}; }}
QToolButton#AnimToggle {{ color: {p.faint}; background: transparent; border: 1px solid {p.border}; border-radius: 4px;
    min-width: 26px; min-height: 22px; font-size: 11pt; }}
QToolButton#AnimToggle:checked {{ color: {p.accent}; border-color: {p.accent}; background: {p.shallow}; }}
QProgressBar {{ border: none; background: {p.panel_alt}; border-radius: 3px; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
QToolButton#Reset:hover {{ color: {p.accent}; border-color: {p.accent}; }}
#DetailTitle {{ font-size: 14pt; font-weight: 700; color: {p.text}; }}
#FactValue {{ color: {p.text}; font-size: 9.5pt; }}
#Warning {{ background: {p.panel_alt}; border-left: 3px solid {p.warn}; border-radius: 3px; padding: 8px 12px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {p.faint}; border-radius: 3px; background: {p.panel_alt}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
  background: {p.panel}; border: 1px solid {p.border}; border-radius: 5px; padding: 6px 9px;
  selection-background-color: {p.accent}; selection-color: {p.accent_text}; }}
QLineEdit#Search {{ font-size: 12pt; padding: 10px 14px; border-radius: 8px; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {p.accent}; }}
QDoubleSpinBox, QSpinBox {{ font-weight: 600; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {p.panel}; border: 1px solid {p.border}; selection-background-color: {p.panel_alt};
  selection-color: {p.text}; }}

QPushButton {{ background: {p.panel}; border: 1px solid {p.border}; border-radius: 5px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {p.accent}; color: {p.accent}; }}
QPushButton:disabled {{ color: {p.faint}; }}
QPushButton#Primary {{ background: {p.accent}; color: {p.accent_text}; border: none; font-weight: 600; padding: 9px 20px; }}
QPushButton#Primary:hover {{ background: {p.text}; color: {p.bg}; }}
QPushButton#Primary:disabled {{ background: {p.panel_alt}; color: {p.faint}; border: 1px solid {p.border}; }}
QPushButton#Chosen {{ background: {p.shallow}; color: {p.good}; border: 1px solid {p.good}; font-weight: 600; padding: 9px 20px; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {p.muted}; padding: 9px 14px; }}
QPushButton#Ghost:hover {{ color: {p.accent}; }}
QPushButton#Segment {{ border-radius: 0; padding: 4px 12px; min-width: 34px; }}
QPushButton#Segment:checked {{ background: {p.accent}; color: {p.accent_text}; border-color: {p.accent}; font-weight: 600; }}
QPushButton#SegmentSmall {{ border-radius: 0; padding: 3px 9px; font-size: 8pt; min-width: 26px; }}
QPushButton#SegmentSmall:checked {{ background: {p.shallow}; color: {p.accent}; border-color: {p.accent}; font-weight: 700; }}
QPushButton#Preset {{ text-align: left; padding: 10px 12px; border-radius: 8px; background: {p.panel}; font-size: 9.5pt; }}
QPushButton#Preset:checked {{ border: 2px solid {p.accent}; background: {p.shallow}; color: {p.text}; font-weight: 600; }}
QPushButton#Choice {{ border-radius: 0; padding: 8px 16px; }}
QPushButton#Choice:checked {{ background: {p.accent}; color: {p.accent_text}; border-color: {p.accent}; }}

QTableView::item:selected, QTableWidget::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
QSplitter::handle {{ background: transparent; width: 14px; }}
QTableView, QTableWidget {{ background: {p.panel}; alternate-background-color: {p.panel_alt}; border: 1px solid {p.border};
  gridline-color: {p.grid}; border-radius: 6px; }}
QHeaderView::section {{ background: {p.panel_alt}; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
  padding: 7px 8px; font-size: 8pt; font-weight: 700; }}
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
QMenu {{ background: {p.panel}; border: 1px solid {p.border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.shallow}; color: {p.accent}; }}
QToolTip {{ background: {p.panel}; color: {p.text}; border: 1px solid {p.border}; padding: 6px; }}
QStatusBar {{ background: {p.sidebar}; color: {p.muted}; }}
"""
