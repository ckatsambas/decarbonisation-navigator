"""Step 6 report (decision 0014-5): a PDF for management and an Excel workbook with every table.

Pure Python + matplotlib + openpyxl, no Qt: the interface collects a `ReportData` (plain values,
already worded in the report's language) and calls `build_pdf` / `build_xlsx`. Print figures use
matplotlib as decided in 0003, so the same figures can go into the thesis.
"""
from .data import ReportData
from .pdf import build_pdf
from .xlsx import build_xlsx

__all__ = ["ReportData", "build_pdf", "build_xlsx"]
