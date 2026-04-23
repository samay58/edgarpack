"""Live-SEC identity test: pre-IPO name resolution returns the correct CIK.

This was the bug the WhiteFiber-instead-of-Cerebras regression exposed:
unit tests with mocked payloads verified API *shape* but never verified
*semantics* against real EDGAR search responses. This test closes that gap
by asserting specific name -> CIK mappings hold against live SEC.

Gated on --run-slow + --run-live-sec to avoid SEC rate-limiting in the fast
suite, consistent with other live-SEC smoke tests in this repo.
"""

from __future__ import annotations

import pytest

from edgarpack.sec.tickers import resolve_company_by_name

pytestmark = [
    pytest.mark.slow,
    pytest.mark.live_sec,
    pytest.mark.usefixtures("_require_slow", "_require_live_sec"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,expected_cik,expected_name_fragment",
    [
        ("Cerebras Systems", "0002021728", "Cerebras"),
        ("Cerebras", "0002021728", "Cerebras"),
        ("WhiteFiber", "0002042022", "WhiteFiber"),
        ("Klarna", "0002003292", "Klarna"),
    ],
)
async def test_pre_ipo_name_resolves_to_correct_cik(
    query: str, expected_cik: str, expected_name_fragment: str
):
    cik, title = await resolve_company_by_name(query)
    assert cik == expected_cik, (
        f"Expected {query!r} -> CIK {expected_cik}, got {cik}. "
        "Likely regression in EDGAR search (entityName vs q parameter, "
        "forms-list encoding, or issuer-name substring filter)."
    )
    assert expected_name_fragment.lower() in title.lower()


@pytest.mark.asyncio
async def test_unknown_issuer_raises_cleanly():
    from edgarpack.errors import UnknownCompany

    with pytest.raises(UnknownCompany):
        await resolve_company_by_name("ThisIssuerDefinitelyDoesNotExistCorp")
