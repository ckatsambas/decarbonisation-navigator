"""What a report contains: plain values and texts, already in the report's language."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Table:
    title: str
    header: list[str]
    rows: list[list]                       # values: str, int or float (Excel keeps numbers as numbers)
    formats: list[str] = field(default_factory=list)   # per column: "text", "eur", "pct", "num", "int"
    note: str = ""


@dataclass
class ReportData:
    lang: str
    title: str
    subtitle: str                          # ship and type
    date: str
    version: str
    labels: dict[str, str]                 # section titles and captions in the report's language
    summary: list[str]                     # executive summary, one sentence per item
    settings: list[tuple[str, str]]        # scenario and appraisal settings: (label, value)
    position: dict = field(default_factory=dict)       # years, ets, fueleu, nzf (€ per year), sentence
    measures: Table | None = None
    plans: dict = field(default_factory=dict)          # front, selected, timeline, adaptive
    weights: dict = field(default_factory=dict)        # names, company, entropy, critic, method, status
    ranking: Table | None = None
    smaa: dict = field(default_factory=dict)           # names, acceptability, expected, confidence, fan
    assumptions: Table | None = None
    sources: list[tuple[str, str, str]] = field(default_factory=list)   # title, url, checked
    tables: list[Table] = field(default_factory=list)  # extra tables for the workbook
