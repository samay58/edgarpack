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
    ifrs_concepts: tuple[str, ...] = ()  # IFRS concept names (fallback for non-US filers)


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
        ifrs_concepts=("Revenue", "RevenueFromContractsWithCustomers"),
    ),
    "cost_of_revenue": MetricMeta(
        concepts=(
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "CostOfGoodsSold",
            "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
        ),
        duration=True,
        ifrs_concepts=("CostOfSales",),
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
        ifrs_concepts=("ProfitLossFromOperatingActivities", "OperatingProfit"),
    ),
    "net_income": MetricMeta(
        concepts=(
            "NetIncomeLoss",
            "ProfitLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
        ),
        duration=True,
        ifrs_concepts=("ProfitLoss", "ProfitLossAttributableToOwnersOfParent"),
    ),
    "eps_basic": MetricMeta(
        concepts=("EarningsPerShareBasic",),
        duration=True,
        ifrs_concepts=("BasicEarningsLossPerShare",),
    ),
    "eps_diluted": MetricMeta(
        concepts=("EarningsPerShareDiluted",),
        duration=True,
        ifrs_concepts=("DilutedEarningsLossPerShare",),
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
        ifrs_concepts=("Assets",),
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
        ifrs_concepts=("Equity", "EquityAttributableToOwnersOfParent"),
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
        ifrs_concepts=("CashFlowsFromUsedInOperatingActivities",),
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
                fy = int(e.get("fy") or 0)
                if best is None or fy > best:
                    best = fy
    return best


def _max_any_fy(units: dict[str, list[dict[str, Any]]]) -> int | None:
    """Return the highest fiscal year from any entry, or None."""
    best: int | None = None
    for entries in units.values():
        for e in entries:
            fy = int(e.get("fy") or 0)
            if fy and (best is None or fy > best):
                best = fy
    return best


def _find_best_concept(
    concepts: tuple[str, ...],
    tax_data: dict[str, Any],
) -> tuple[str | None, tuple[int, int]]:
    """Find the best concept among candidates within a taxonomy's data."""
    best_concept: str | None = None
    best_score: tuple[int, int] = (-1, -1)

    for concept in concepts:
        if concept not in tax_data:
            continue
        units = tax_data[concept].get("units", {})
        if not units:
            continue

        annual_fy = _max_annual_fy(units) or 0
        any_fy = _max_any_fy(units) or 0
        score = (annual_fy, any_fy)

        if score > best_score:
            best_score = score
            best_concept = concept
        elif score == best_score and best_concept is None:
            best_concept = concept

    return best_concept, best_score


def resolve_concept(
    metric: str,
    facts: dict[str, Any],
    taxonomy: str = "us-gaap",
) -> tuple[str, str] | None:
    """Find the best matching concept for a metric in a companyfacts blob.

    Tries us-gaap first, then ifrs-full as fallback for non-US filers.
    Picks the concept with the most recent annual data. When two concepts share
    the same max fiscal year, priority order from the METRIC_MAP breaks the tie.

    Args:
        metric: Normalized metric name (e.g. "revenue").
        facts: The ``facts`` dict from SEC companyfacts JSON.
        taxonomy: XBRL taxonomy to search first (default "us-gaap").

    Returns:
        (concept_name, taxonomy) tuple, or None if no concept matched.
    """
    meta = METRIC_MAP.get(metric)
    if meta is None or meta.derived:
        return None

    # Try primary taxonomy (us-gaap)
    tax_data = facts.get(taxonomy, {})
    gaap_concept, gaap_score = _find_best_concept(meta.concepts, tax_data)

    if gaap_concept is not None and gaap_score > (0, 0):
        return (gaap_concept, taxonomy)

    # Try ifrs-full as fallback
    ifrs_data = facts.get("ifrs-full", {})
    if ifrs_data:
        # Try IFRS-specific concepts first, then fall back to shared names
        ifrs_candidates = (
            meta.ifrs_concepts + meta.concepts if meta.ifrs_concepts else meta.concepts
        )
        ifrs_concept, ifrs_score = _find_best_concept(ifrs_candidates, ifrs_data)
        if ifrs_concept is not None:
            if gaap_concept is None or ifrs_score > gaap_score:
                return (ifrs_concept, "ifrs-full")

    # Return GAAP result even with score (0, 0) if it's all we have
    if gaap_concept is not None:
        return (gaap_concept, taxonomy)

    return None


def get_metric_meta(metric: str) -> MetricMeta | None:
    """Look up metadata for a normalized metric name."""
    return METRIC_MAP.get(metric)
