"""GAAP concept normalization: human-readable metric names to XBRL concept tags.

Different companies use different XBRL tags for the same economic concept. Apple reports
revenue as ``RevenueFromContractWithCustomerExcludingAssessedTax`` while NVIDIA uses
``Revenues``. This module maps ~30 normalized metric names to prioritized concept lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricMeta:
    """Metadata about a normalized metric."""

    concepts: tuple[str, ...]  # priority-ordered GAAP concepts to try
    duration: bool  # True = P&L/CF (period), False = balance sheet (instant)
    derived: bool = False  # True = computed from other metrics
    formula: str | None = None  # e.g. "gross_profit / revenue"
    components: tuple[str, ...] = ()  # metric names needed for derived calc


# ---------------------------------------------------------------------------
# Income Statement
# ---------------------------------------------------------------------------

METRIC_MAP: dict[str, MetricMeta] = {
    "revenue": MetricMeta(
        concepts=(
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet",
        ),
        duration=True,
    ),
    "cost_of_revenue": MetricMeta(
        concepts=(
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "CostOfGoodsSold",
            "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
        ),
        duration=True,
    ),
    "gross_profit": MetricMeta(
        concepts=("GrossProfit",),
        duration=True,
    ),
    "operating_income": MetricMeta(
        concepts=(
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ),
        duration=True,
    ),
    "net_income": MetricMeta(
        concepts=(
            "NetIncomeLoss",
            "ProfitLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
        ),
        duration=True,
    ),
    "eps_basic": MetricMeta(
        concepts=("EarningsPerShareBasic",),
        duration=True,
    ),
    "eps_diluted": MetricMeta(
        concepts=("EarningsPerShareDiluted",),
        duration=True,
    ),
    "rd_expense": MetricMeta(
        concepts=(
            "ResearchAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        ),
        duration=True,
    ),
    "sga_expense": MetricMeta(
        concepts=(
            "SellingGeneralAndAdministrativeExpense",
            "GeneralAndAdministrativeExpense",
        ),
        duration=True,
    ),
    # EBITDA: derived
    "ebitda": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="operating_income + depreciation_amortization",
        components=("operating_income", "depreciation_amortization"),
    ),
    "depreciation_amortization": MetricMeta(
        concepts=(
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "Depreciation",
        ),
        duration=True,
    ),
    # ---------------------------------------------------------------------------
    # Balance Sheet
    # ---------------------------------------------------------------------------
    "total_assets": MetricMeta(
        concepts=("Assets",),
        duration=False,
    ),
    "current_assets": MetricMeta(
        concepts=("AssetsCurrent",),
        duration=False,
    ),
    "total_liabilities": MetricMeta(
        concepts=(
            "Liabilities",
            "LiabilitiesAndStockholdersEquity",
        ),
        duration=False,
    ),
    "current_liabilities": MetricMeta(
        concepts=("LiabilitiesCurrent",),
        duration=False,
    ),
    "stockholders_equity": MetricMeta(
        concepts=(
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        duration=False,
    ),
    "cash": MetricMeta(
        concepts=(
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsAndShortTermInvestments",
            "Cash",
        ),
        duration=False,
    ),
    "total_debt": MetricMeta(
        concepts=(
            "LongTermDebt",
            "LongTermDebtAndCapitalLeaseObligations",
            "DebtInstrumentCarryingAmount",
            "LongTermDebtNoncurrent",
        ),
        duration=False,
    ),
    "inventory": MetricMeta(
        concepts=(
            "InventoryNet",
            "InventoryFinishedGoodsAndWorkInProcess",
        ),
        duration=False,
    ),
    "accounts_receivable": MetricMeta(
        concepts=(
            "AccountsReceivableNetCurrent",
            "AccountsReceivableNet",
        ),
        duration=False,
    ),
    "accounts_payable": MetricMeta(
        concepts=(
            "AccountsPayableCurrent",
            "AccountsPayableAndAccruedLiabilitiesCurrent",
        ),
        duration=False,
    ),
    # Working capital: derived
    "working_capital": MetricMeta(
        concepts=(),
        duration=False,
        derived=True,
        formula="current_assets - current_liabilities",
        components=("current_assets", "current_liabilities"),
    ),
    # ---------------------------------------------------------------------------
    # Cash Flow
    # ---------------------------------------------------------------------------
    "operating_cash_flow": MetricMeta(
        concepts=(
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        duration=True,
    ),
    "capex": MetricMeta(
        concepts=(
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ),
        duration=True,
    ),
    # Free cash flow: derived
    "free_cash_flow": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="operating_cash_flow - capex",
        components=("operating_cash_flow", "capex"),
    ),
    # ---------------------------------------------------------------------------
    # Per Share
    # ---------------------------------------------------------------------------
    "shares_outstanding": MetricMeta(
        concepts=(
            "CommonStockSharesOutstanding",
            "EntityCommonStockSharesOutstanding",
        ),
        duration=False,
    ),
    "shares_diluted": MetricMeta(
        concepts=("WeightedAverageNumberOfDilutedSharesOutstanding",),
        duration=True,
    ),
    "dividends_per_share": MetricMeta(
        concepts=(
            "CommonStockDividendsPerShareDeclared",
            "CommonStockDividendsPerShareCashPaid",
        ),
        duration=True,
    ),
    # ---------------------------------------------------------------------------
    # Derived Ratios
    # ---------------------------------------------------------------------------
    "gross_margin": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="gross_profit / revenue",
        components=("gross_profit", "revenue"),
    ),
    "operating_margin": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="operating_income / revenue",
        components=("operating_income", "revenue"),
    ),
    "net_margin": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="net_income / revenue",
        components=("net_income", "revenue"),
    ),
    "roe": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="net_income / stockholders_equity",
        components=("net_income", "stockholders_equity"),
    ),
    "roa": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="net_income / total_assets",
        components=("net_income", "total_assets"),
    ),
    "current_ratio": MetricMeta(
        concepts=(),
        duration=False,
        derived=True,
        formula="current_assets / current_liabilities",
        components=("current_assets", "current_liabilities"),
    ),
    "debt_to_equity": MetricMeta(
        concepts=(),
        duration=False,
        derived=True,
        formula="total_debt / stockholders_equity",
        components=("total_debt", "stockholders_equity"),
    ),
}

ALL_METRICS = tuple(METRIC_MAP.keys())


def _max_annual_fy(units: dict[str, list[dict[str, Any]]]) -> int | None:
    """Return the highest fiscal year among annual (FY) entries, or None."""
    best: int | None = None
    for entries in units.values():
        for e in entries:
            if str(e.get("fp", "")).upper() == "FY":
                fy = int(e.get("fy", 0))
                if best is None or fy > best:
                    best = fy
    return best


def _max_any_fy(units: dict[str, list[dict[str, Any]]]) -> int | None:
    """Return the highest fiscal year from any entry, or None."""
    best: int | None = None
    for entries in units.values():
        for e in entries:
            fy = int(e.get("fy", 0))
            if fy and (best is None or fy > best):
                best = fy
    return best


def resolve_concept(
    metric: str,
    facts: dict[str, Any],
    taxonomy: str = "us-gaap",
) -> str | None:
    """Find the best matching GAAP concept for a metric in a companyfacts blob.

    Picks the concept with the most recent annual data. When two concepts share
    the same max fiscal year, priority order from the METRIC_MAP breaks the tie.

    Args:
        metric: Normalized metric name (e.g. "revenue").
        facts: The ``facts`` dict from SEC companyfacts JSON.
        taxonomy: XBRL taxonomy to search (default "us-gaap").

    Returns:
        The concept name that has data, or None if no concept matched.
    """
    meta = METRIC_MAP.get(metric)
    if meta is None or meta.derived:
        return None

    tax_data = facts.get(taxonomy, {})

    best_concept: str | None = None
    best_score: tuple[int, int] = (-1, -1)

    for concept in meta.concepts:
        if concept not in tax_data:
            continue
        units = tax_data[concept].get("units", {})
        if not units:
            continue

        # Score: (max annual FY, max any FY). Annual FY is the primary key,
        # so a concept with FY2024 annual data beats one with only Q1 2025 quarterly.
        annual_fy = _max_annual_fy(units) or 0
        any_fy = _max_any_fy(units) or 0
        score = (annual_fy, any_fy)

        if score > best_score:
            best_score = score
            best_concept = concept
        elif score == best_score and best_concept is None:
            # Same score but first candidate seen wins (priority order)
            best_concept = concept

    return best_concept


def get_metric_meta(metric: str) -> MetricMeta | None:
    """Look up metadata for a normalized metric name."""
    return METRIC_MAP.get(metric)
