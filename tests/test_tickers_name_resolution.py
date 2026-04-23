"""Tests for SEC EDGAR name-based CIK resolution (pre-IPO filers)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.errors import AmbiguousCompany, UnknownCompany
from edgarpack.sec.tickers import resolve_company_by_name


def _canned_hits(*companies: tuple[str, str]) -> str:
    """Build a canned EDGAR full-text search response.

    Each tuple is (cik_10digit, display_name).
    """
    return json.dumps(
        {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "ciks": [cik],
                            "display_names": [f"{name} (CIK {cik})"],
                        }
                    }
                    for cik, name in companies
                ]
            }
        }
    )


@pytest.mark.asyncio
async def test_resolve_company_by_name_unique_match():
    canned = _canned_hits(("0002021728", "Cerebras Systems Inc"))
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        cik, title = await resolve_company_by_name("Cerebras Systems")
    assert cik == "0002021728"
    assert "Cerebras" in title


@pytest.mark.asyncio
async def test_resolve_company_by_name_ambiguous_raises():
    canned = _canned_hits(
        ("0002021728", "Cerebras Systems Inc"),
        ("0001234567", "Cerebras Holdings LLC"),
    )
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        with pytest.raises(AmbiguousCompany) as exc:
            await resolve_company_by_name("Cerebras")
    assert "0002021728" in str(exc.value)
    assert "0001234567" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_company_by_name_zero_matches_raises():
    canned = json.dumps({"hits": {"hits": []}})
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        with pytest.raises(UnknownCompany):
            await resolve_company_by_name("ThisCompanyDoesNotExist Corp")


@pytest.mark.asyncio
async def test_resolve_company_by_name_dedupes_repeated_cik():
    """SEC search sometimes returns the same CIK on multiple hits (one per form)."""
    canned = _canned_hits(
        ("0002021728", "Cerebras Systems Inc"),
        ("0002021728", "Cerebras Systems Inc"),
    )
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        cik, _title = await resolve_company_by_name("Cerebras")
    assert cik == "0002021728"


@pytest.mark.asyncio
async def test_resolve_company_by_name_rejects_content_only_matches():
    """If EDGAR returns filings where the query is ONLY in the content (not
    the display_name), those hits must be discarded. This guards against
    WhiteFiber's S-1 mentioning "Cerebras" ever resolving to WhiteFiber."""
    canned = _canned_hits(
        ("0002042022", "WhiteFiber, Inc."),
        ("0001866692", "Amplitude, Inc."),
    )
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        with pytest.raises(UnknownCompany) as exc:
            await resolve_company_by_name("Cerebras")
    assert "Cerebras" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_company_by_name_prefers_issuer_name_match_over_content_match():
    """When the result set mixes real issuer matches with content-only matches,
    only the issuer match survives."""
    canned = _canned_hits(
        ("0002042022", "WhiteFiber, Inc."),  # content mention
        ("0002021728", "Cerebras Systems Inc"),  # actual issuer
        ("0001866692", "Amplitude, Inc."),  # content mention
    )
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        cik, title = await resolve_company_by_name("Cerebras Systems")
    assert cik == "0002021728"
    assert "Cerebras" in title
