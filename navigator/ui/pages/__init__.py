from .base import Page, placeholder
from .regulation import RegulationPage

ShipPage = placeholder("page.ship.title", "page.ship.lede", 2)
MeasuresPage = placeholder("page.measures.title", "page.measures.lede", 3)
DecisionPage = placeholder("page.decision.title", "page.decision.lede", 4)
UncertaintyPage = placeholder("page.uncertainty.title", "page.uncertainty.lede", 4)
ReportPage = placeholder("page.report.title", "page.report.lede", 5)

__all__ = ["DecisionPage", "MeasuresPage", "Page", "RegulationPage", "ReportPage", "ShipPage", "UncertaintyPage"]
