"""Acquisition connectors for China Lens."""

from .cninfo import (
    CninfoAnnualReportRef,
    find_latest_annual_report,
    latest_annual_from_cninfo_payload,
)

__all__ = [
    "CninfoAnnualReportRef",
    "find_latest_annual_report",
    "latest_annual_from_cninfo_payload",
]
