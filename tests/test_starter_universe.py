"""Validation tests for the starter-universe packet: every China entry in
the live universe.toml carries well-formed identifiers, no identifier is
claimed by two entries, every entry resolves through identity.resolve by
its ticker and by an alias, and dual-listed entries carry a valid default
`listing`.

"China entry" is detected structurally (hk_stock_code or stock_code set,
listing in {HKEX, SSE, STAR}, a ticker/alt_ticker ending in ".HK", or a
6-digit ticker with a known China A-share prefix) so this test tracks the
live file rather than a hand-maintained list. A small allowlist covers the
handful of pure-SEC-only China ADRs (Baidu, PDD, Vipshop, TAL, iQIYI, Full
Truck Alliance) that carry no China-specific TOML field at all to detect
structurally.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from edgarpack.harvest.universe import CompanySpec, load_universe
from edgarpack.identity import (
    VenueNotAvailable,
    load_identity,
    looks_like_china_a_share_code,
    resolve,
    select_venue,
    venue_identifier,
)

UNIVERSE_PATH = Path("universe.toml")

# Pure-SEC-only China ADRs verified by this packet (or a sibling pilot) that
# carry no hk_stock_code/stock_code/HKEX/SSE marker to detect structurally.
_PURE_SEC_CHINA_CIKS = {
    "0001329099",  # BIDU, Baidu
    "0001737806",  # PDD, PDD Holdings
    "0001529192",  # VIPS, Vipshop
    "0001499620",  # TAL, TAL Education
    "0001722608",  # IQ, iQIYI
    "0001838413",  # YMM, Full Truck Alliance
}


def _primary_key(spec: CompanySpec) -> str | None:
    """Mirror load_identity()'s own primary_key fallback (ticker, name, cik)."""
    return spec.ticker or spec.name or spec.cik


def _is_china_entry(spec: CompanySpec) -> bool:
    if spec.hk_stock_code or spec.stock_code:
        return True
    if (spec.listing or "").upper() in ("HKEX", "SSE", "STAR", "STAR MARKET"):
        return True
    candidates = [spec.ticker, *spec.alt_tickers]
    if any(t and t.upper().endswith(".HK") for t in candidates):
        return True
    if any(t and looks_like_china_a_share_code(t) for t in candidates):
        return True
    if spec.cik and spec.cik.lstrip("0").zfill(10) in _PURE_SEC_CHINA_CIKS:
        return True
    return False


@pytest.fixture(scope="module")
def universe_companies() -> list[CompanySpec]:
    config = load_universe(UNIVERSE_PATH)
    return [c for c in config.companies if _is_china_entry(c)]


@pytest.fixture(scope="module")
def identity_index():
    return load_identity(UNIVERSE_PATH)


def test_at_least_45_china_entries_landed(universe_companies):
    assert len(universe_companies) >= 45, (
        f"expected 45+ verified China entries, found {len(universe_companies)}"
    )


def test_china_entry_identifiers_are_well_formed(universe_companies):
    for spec in universe_companies:
        label = _primary_key(spec)
        if spec.cik:
            padded = spec.cik.lstrip("0").zfill(10)
            assert padded.isdigit() and len(padded) == 10, f"{label}: malformed cik {spec.cik!r}"
        if spec.hk_stock_code:
            assert spec.hk_stock_code.isdigit() and len(spec.hk_stock_code) == 5, (
                f"{label}: hk_stock_code must be 5-digit zero-padded, got {spec.hk_stock_code!r}"
            )
        if spec.stock_code:
            assert looks_like_china_a_share_code(spec.stock_code), (
                f"{label}: stock_code {spec.stock_code!r} is not a well-formed A-share code"
            )


def test_china_entries_have_no_duplicate_identifiers(universe_companies):
    seen: dict[str, list[str]] = {"cik": [], "hk_stock_code": [], "stock_code": []}
    for spec in universe_companies:
        label = _primary_key(spec) or "?"
        if spec.cik:
            padded = spec.cik.lstrip("0").zfill(10)
            assert padded not in seen["cik"], f"duplicate cik {padded} on {label}"
            seen["cik"].append(padded)
        if spec.hk_stock_code:
            assert spec.hk_stock_code not in seen["hk_stock_code"], (
                f"duplicate hk_stock_code {spec.hk_stock_code} on {label}"
            )
            seen["hk_stock_code"].append(spec.hk_stock_code)
        if spec.stock_code:
            assert spec.stock_code not in seen["stock_code"], (
                f"duplicate stock_code {spec.stock_code} on {label}"
            )
            seen["stock_code"].append(spec.stock_code)


def test_every_china_entry_resolves_by_ticker_and_alias(universe_companies, identity_index):
    for spec in universe_companies:
        primary_key = _primary_key(spec)
        assert primary_key, f"China entry with no ticker/name/cik: {spec}"

        by_ticker = resolve(identity_index, ticker=primary_key, company=None)
        assert by_ticker is not None

        assert spec.aliases, f"{primary_key}: China entry has no alias to resolve by"
        by_alias = resolve(identity_index, ticker=None, company=spec.aliases[0])
        assert by_alias.ticker == by_ticker.ticker, (
            f"{primary_key}: alias {spec.aliases[0]!r} resolved to a different entry"
        )


def test_dual_listed_china_entries_have_valid_default_listing(universe_companies, identity_index):
    for spec in universe_companies:
        populated = [bool(spec.cik), bool(spec.hk_stock_code), bool(spec.stock_code)]
        if sum(populated) < 2:
            continue
        primary_key = _primary_key(spec)
        resolved = resolve(identity_index, ticker=primary_key, company=None)
        assert resolved.listing, f"{primary_key}: dual-listed entry has no default listing"
        assert venue_identifier(resolved, resolved.listing), (
            f"{primary_key}: default listing {resolved.listing!r} has no identifier populated"
        )


# ---------------------------------------------------------------------------
# Done-definition checks: specific lookups the packet spec calls out by name.
# ---------------------------------------------------------------------------


def test_identify_moutai_resolves(identity_index):
    r = resolve(identity_index, ticker=None, company="moutai")
    assert r.source == "SSE"
    assert r.stock_code == "600519"


def test_identify_byddy_resolves(identity_index):
    r = resolve(identity_index, ticker="BYDDY", company=None)
    assert r.stock_code == "002594"
    assert r.hk_stock_code == "01211"
    assert r.source == "SSE"


def test_byd_venue_sec_still_raises_teaching_error(identity_index):
    """Regression: starter-universe additions must not disturb the
    dual-listing-adr BYD teaching-error pilot case."""
    byd = resolve(identity_index, ticker=None, company="byd")
    with pytest.raises(VenueNotAvailable):
        select_venue(byd, "sec")
