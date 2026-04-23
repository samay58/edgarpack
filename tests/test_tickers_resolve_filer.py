"""Tests for the resolve_filer dispatch across cik / ticker / name."""

from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.errors import UnknownCompany
from edgarpack.harvest.universe import CompanySpec
from edgarpack.sec.tickers import resolve_filer


@pytest.mark.asyncio
async def test_resolve_filer_prefers_explicit_cik():
    spec = CompanySpec(cik="0001045810", ticker="NVDA", name="NVIDIA")
    with patch("edgarpack.sec.tickers.resolve_ticker", new=AsyncMock(side_effect=AssertionError)):
        with patch(
            "edgarpack.sec.tickers.resolve_company_by_name",
            new=AsyncMock(side_effect=AssertionError),
        ):
            cik, title = await resolve_filer(spec)
    assert cik == "0001045810"


@pytest.mark.asyncio
async def test_resolve_filer_uses_ticker_when_no_cik():
    spec = CompanySpec(ticker="NVDA")
    with patch(
        "edgarpack.sec.tickers.resolve_ticker",
        new=AsyncMock(return_value=("0001045810", "NVIDIA Corp")),
    ) as mock_tick:
        cik, title = await resolve_filer(spec)
    mock_tick.assert_awaited_once_with("NVDA")
    assert cik == "0001045810"


@pytest.mark.asyncio
async def test_resolve_filer_falls_back_to_name_when_ticker_unknown():
    spec = CompanySpec(ticker="CRBS", name="Cerebras Systems")
    with patch(
        "edgarpack.sec.tickers.resolve_ticker",
        new=AsyncMock(side_effect=UnknownCompany("CRBS not in map")),
    ):
        with patch(
            "edgarpack.sec.tickers.resolve_company_by_name",
            new=AsyncMock(return_value=("0002021728", "Cerebras Systems Inc")),
        ) as mock_name:
            cik, title = await resolve_filer(spec)
    mock_name.assert_awaited_once_with("Cerebras Systems")
    assert cik == "0002021728"


@pytest.mark.asyncio
async def test_resolve_filer_uses_name_directly_when_only_name_given():
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    with patch(
        "edgarpack.sec.tickers.resolve_company_by_name",
        new=AsyncMock(return_value=("0002021728", "Cerebras Systems Inc")),
    ):
        cik, title = await resolve_filer(spec)
    assert cik == "0002021728"


@pytest.mark.asyncio
async def test_resolve_filer_raises_when_no_identifier_usable():
    spec = CompanySpec(ticker="BOGUS", name="Definitely Not A Real Filer")
    with patch(
        "edgarpack.sec.tickers.resolve_ticker",
        new=AsyncMock(side_effect=UnknownCompany("BOGUS")),
    ):
        with patch(
            "edgarpack.sec.tickers.resolve_company_by_name",
            new=AsyncMock(side_effect=UnknownCompany("not found")),
        ):
            with pytest.raises(UnknownCompany):
                await resolve_filer(spec)
