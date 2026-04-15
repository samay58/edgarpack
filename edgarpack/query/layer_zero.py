"""Layer 0 of the self-heal stack: alias map for typo-class metric misses.

This layer is entirely deterministic and has no cost on the fast path. The
alias map is hand-curated; adding an entry here is the right fix for any
"user typed X, we meant Y" class of miss.

When a metric name doesn't resolve even after alias lookup, callers should
raise MetricNotFound with suggestions instead of silently returning None.
"""

from __future__ import annotations

import difflib

METRIC_ALIASES: dict[str, str] = {
    "fcf": "free_cash_flow",
    "opinc": "operating_income",
    "opi": "operating_income",
    "rev": "revenue",
    "ni": "net_income",
    "da": "depreciation_amortization",
    "d&a": "depreciation_amortization",
    "sbc": "stock_based_compensation",
    "rd": "rd_expense",
    "r&d": "rd_expense",
    "sga": "sga_expense",
    "s&ga": "sga_expense",
    "cogs": "cost_of_revenue",
    "gp": "gross_profit",
    "ocf": "operating_cash_flow",
    "capex": "capex",
    "eps": "eps_diluted",
    "shares": "shares_diluted",
}


def resolve_alias(name: str) -> str:
    """Return the canonical metric name for ``name``.

    Lowercases, strips whitespace, and looks up in METRIC_ALIASES. If there
    is no alias entry, returns the lowercased/stripped input unchanged.
    This function never raises; unknown names are the caller's problem.
    """
    key = (name or "").strip().lower()
    return METRIC_ALIASES.get(key, key)


def suggest_metrics(name: str, known: set[str] | frozenset[str], n: int = 3) -> list[str]:
    """Return up to ``n`` close matches for ``name`` from ``known``.

    Used to populate MetricNotFound.suggestions so the user sees
    "did you mean 'revenue'?" instead of a bare error.
    """
    return difflib.get_close_matches(name, sorted(known), n=n, cutoff=0.6)


class MetricNotFoundError(ValueError):
    """Raised when a metric name cannot be resolved after alias lookup."""

    def __init__(self, metric_name: str, suggestions: list[str] | None = None) -> None:
        self.metric_name = metric_name
        self.suggestions = suggestions or []
        hint = ""
        if self.suggestions:
            hint = f" Did you mean: {', '.join(self.suggestions)}?"
        super().__init__(f"Unknown metric: {metric_name!r}.{hint}")


MetricNotFound = MetricNotFoundError
