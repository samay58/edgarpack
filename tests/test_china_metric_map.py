import pytest

from edgarpack.query.metric_map import (
    CANONICAL_METRICS,
    METRIC_MAP,
    UnknownMetric,
    resolve_concepts,
)


def test_every_standard_covers_every_canonical_metric():
    for standard in ("US-GAAP", "IFRS", "HKFRS"):
        missing = [m for m in CANONICAL_METRICS if m not in METRIC_MAP[standard]]
        assert not missing, f"{standard} missing: {missing}"


def test_resolve_concepts_us_gaap_revenue():
    concepts = resolve_concepts("revenue", "US-GAAP")
    assert (
        "Revenues" in concepts
        or "RevenueFromContractWithCustomerExcludingAssessedTax" in concepts
    )


def test_resolve_concepts_hkfrs_revenue_includes_turnover():
    concepts = resolve_concepts("revenue", "HKFRS")
    assert "Turnover" in concepts or "Revenue" in concepts


def test_unknown_metric_raises_with_suggestions():
    with pytest.raises(UnknownMetric) as excinfo:
        resolve_concepts("revnue", "US-GAAP")
    assert "revenue" in str(excinfo.value)


def test_canonical_metrics_covers_full_fundamental_set():
    required = {
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
    }
    assert required <= set(CANONICAL_METRICS)
