import asyncio

import pytest

from edgarpack.query.financials import financials


def test_minimax_query_returns_revenue_from_pack():
    result = asyncio.run(financials(company="minimax", metrics="revenue", period="lfy"))
    assert result is not None
    revenue = result.metrics.get("revenue")
    assert revenue is not None, f"No revenue in {list(result.metrics.keys())}"
    assert revenue.reporting_currency == "USD"
    assert revenue.accounting_standard == "HKFRS"
    assert revenue.value == 30_523_000
    assert revenue.fiscal_year == 2024


def test_zhipu_query_returns_net_income_from_pack():
    result = asyncio.run(financials(company="zhipu", metrics="net_income", period="lfy"))
    ni = result.metrics.get("net_income")
    assert ni is not None
    assert ni.reporting_currency == "CNY"
    assert ni.accounting_standard == "HKFRS"
    assert ni.value == -2_958_007_000


def test_minimax_ticker_form_also_works():
    result = asyncio.run(
        financials(company="00100.HK", metrics="cash_and_equivalents", period="lfy")
    )
    cash = result.metrics.get("cash_and_equivalents")
    assert cash is not None
    assert cash.value == 288_912_000


def test_minimax_full_query_returns_multiple_metrics():
    result = asyncio.run(financials(company="minimax", metrics=None, period="lfy"))
    metrics = set(result.metrics.keys())
    assert {"revenue", "net_income", "cash_and_equivalents"} <= metrics


def test_unknown_hkex_company_raises():
    with pytest.raises(Exception):
        asyncio.run(financials(company="00999.HK", metrics="revenue", period="lfy"))
