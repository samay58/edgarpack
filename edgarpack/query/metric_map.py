from __future__ import annotations

import difflib
from typing import Literal

AccountingStandard = Literal["US-GAAP", "IFRS", "HKFRS", "CAS"]
CanonicalMetric = str


class UnknownMetric(ValueError):  # noqa: N818
    pass


CANONICAL_METRICS: tuple[CanonicalMetric, ...] = (
    "revenue",
    "gross_profit",
    "gross_margin",
    "operating_income",
    "operating_margin",
    "ebitda",
    "net_income",
    "eps_basic",
    "eps_diluted",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "cash_and_equivalents",
    "total_debt",
    "shares_outstanding_basic",
    "shares_outstanding_diluted",
    "cash_burn",
    "runway_months",
    "r_and_d_intensity",
    "revenue_growth_yoy",
    "gross_margin_trend",
)


METRIC_MAP: dict[AccountingStandard, dict[CanonicalMetric, list[str]]] = {
    "US-GAAP": {
        "revenue": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
        ],
        "gross_profit": ["GrossProfit"],
        "gross_margin": [],
        "operating_income": ["OperatingIncomeLoss"],
        "operating_margin": [],
        "ebitda": [],
        "net_income": ["NetIncomeLoss", "ProfitLoss"],
        "eps_basic": ["EarningsPerShareBasic"],
        "eps_diluted": ["EarningsPerShareDiluted"],
        "total_assets": ["Assets"],
        "total_liabilities": ["Liabilities"],
        "total_equity": [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ],
        "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
        "total_debt": ["LongTermDebt", "DebtCurrent"],
        "shares_outstanding_basic": ["WeightedAverageNumberOfSharesOutstandingBasic"],
        "shares_outstanding_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
        "cash_burn": ["NetCashProvidedByUsedInOperatingActivities"],
        "runway_months": [],
        "r_and_d_intensity": [],
        "revenue_growth_yoy": [],
        "gross_margin_trend": [],
    },
    "IFRS": {
        "revenue": ["Revenue", "RevenueFromContractsWithCustomers", "RevenueFromContracts"],
        "gross_profit": ["GrossProfit"],
        "gross_margin": [],
        "operating_income": ["ProfitLossFromOperatingActivities", "OperatingProfit"],
        "operating_margin": [],
        "ebitda": [],
        "net_income": ["ProfitLoss", "NetIncomeLoss"],
        "eps_basic": ["BasicEarningsLossPerShare"],
        "eps_diluted": ["DilutedEarningsLossPerShare"],
        "total_assets": ["Assets", "TotalAssets"],
        "total_liabilities": ["Liabilities", "TotalLiabilities"],
        "total_equity": ["Equity", "TotalEquity"],
        "cash_and_equivalents": ["CashAndCashEquivalents"],
        "total_debt": ["Borrowings", "LongTermBorrowings"],
        "shares_outstanding_basic": ["WeightedAverageShares"],
        "shares_outstanding_diluted": ["WeightedAverageDilutedShares"],
        "cash_burn": ["CashFlowsFromUsedInOperatingActivities"],
        "runway_months": [],
        "r_and_d_intensity": [],
        "revenue_growth_yoy": [],
        "gross_margin_trend": [],
    },
    "HKFRS": {
        "revenue": ["Revenue", "Turnover", "RevenueFromContracts"],
        "gross_profit": ["GrossProfit"],
        "gross_margin": [],
        "operating_income": ["OperatingProfit", "ProfitLossFromOperatingActivities"],
        "operating_margin": [],
        "ebitda": [],
        "net_income": ["ProfitForTheYear", "ProfitLoss"],
        "eps_basic": ["BasicEarningsPerShare", "BasicEarningsLossPerShare"],
        "eps_diluted": ["DilutedEarningsPerShare", "DilutedEarningsLossPerShare"],
        "total_assets": ["TotalAssets", "Assets"],
        "total_liabilities": ["TotalLiabilities", "Liabilities"],
        "total_equity": ["TotalEquity", "Equity"],
        "cash_and_equivalents": ["CashAndCashEquivalents", "BankBalancesAndCash"],
        "total_debt": ["Borrowings", "BankBorrowings"],
        "shares_outstanding_basic": ["WeightedAverageNumberOfOrdinarySharesInIssue"],
        "shares_outstanding_diluted": ["WeightedAverageNumberOfOrdinarySharesDiluted"],
        "cash_burn": ["CashFlowsFromUsedInOperatingActivities"],
        "runway_months": [],
        "r_and_d_intensity": [],
        "revenue_growth_yoy": [],
        "gross_margin_trend": [],
    },
    "CAS": {m: [] for m in CANONICAL_METRICS},
}


def resolve_concepts(metric: CanonicalMetric, standard: AccountingStandard) -> list[str]:
    if metric not in CANONICAL_METRICS:
        suggestions = difflib.get_close_matches(metric, CANONICAL_METRICS, n=3)
        raise UnknownMetric(
            f"Unknown metric {metric!r}. Did you mean: {', '.join(suggestions) or 'none'}?"
        )
    return METRIC_MAP[standard][metric]
