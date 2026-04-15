"""FX normalization for cross-corpus queries.

Spec: docs/superpowers/specs/2026-04-14-china-query-performance-design.md
"""

from .convert import Convention, ConvertedValue, RateNotFound, convert  # noqa: N818
from .rates import MonthlyRate, RateTable, load_rates

__all__ = [
    "ConvertedValue",
    "Convention",
    "MonthlyRate",
    "RateNotFound",
    "RateTable",
    "convert",
    "load_rates",
]
