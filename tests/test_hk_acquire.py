"""Tests for edgarpack.hk.acquire: HKEX search, selection, and metadata extraction.

Fixtures under tests/fixtures/hkex_search/ are recorded HTTP response bodies
from the 2026-07-05 live spike (0700, 9988, 3690, 1211, 0005), except
`partial_do_multi_candidate.txt` and `servlet_annual_reports_stale.json`,
which are hand-built to the same schema (the spike observed the shape of a
33-candidate substring search and a stale result set but did not save the raw
payloads) and `metadata_hkfrs_hkd.txt` / `metadata_missing_anchor.txt`, which
are synthetic excerpts following the pattern verified in the real Tencent
filing text saved as `metadata_ifrs_rmb.txt`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from edgarpack.hk.acquire import (
    HKEXFilingRow,
    HKEXSearchBlocked,
    HKEXStaleFilingError,
    HKEXStockNotFoundError,
    HKFilingMeta,
    HKFilingMetadataError,
    HKFilingRef,
    HKStockMatch,
    _find_legal_name,
    _months_before,
    _normalize_hk_code,
    _parse_fiscal_year,
    _parse_hk_datetime,
    _select_exact_stock_match,
    _split_stock_codes,
    _strip_jsonp,
    download_pdf,
    extract_metadata_from_text,
    find_latest_annual_report,
    list_annual_reports,
    parse_filing_search_payload,
    resolve_stock_id,
    select_latest_annual_report,
    to_filing_ref,
    warm_up,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "hkex_search"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text()


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        for key, text in self._responses.items():
            if key in url:
                return _FakeResponse(text)
        raise AssertionError(f"no fake response registered for {url}")


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every network-shaped test here uses a fake client; skip the real sleep."""
    monkeypatch.setattr("edgarpack.hk.acquire._rate_limit", lambda: None)


# --- callback-wrapper (JSONP) stripping -------------------------------------


def test_strip_jsonp_handles_trailing_semicolon() -> None:
    payload = _strip_jsonp('callback({"stockInfo": []});', step="test")
    assert payload == {"stockInfo": []}


def test_strip_jsonp_handles_no_trailing_semicolon() -> None:
    payload = _strip_jsonp('callback({"stockInfo": []})', step="test")
    assert payload == {"stockInfo": []}


def test_strip_jsonp_empty_body_raises_blocked() -> None:
    with pytest.raises(HKEXSearchBlocked):
        _strip_jsonp("", step="stock resolution")


def test_strip_jsonp_whitespace_only_body_raises_blocked() -> None:
    with pytest.raises(HKEXSearchBlocked):
        _strip_jsonp("   \n  ", step="stock resolution")


def test_strip_jsonp_non_jsonp_body_raises_blocked() -> None:
    with pytest.raises(HKEXSearchBlocked):
        _strip_jsonp("<html>blocked</html>", step="stock resolution")


# --- partial.do substring resolution, including the multi-candidate case ---


def test_resolve_multi_candidate_fixture_filters_to_exact_code() -> None:
    from edgarpack.hk.acquire import _parse_stock_matches

    payload = _strip_jsonp(
        _read("partial_do_multi_candidate.txt"), step="stock resolution (partial.do)"
    )
    matches = _parse_stock_matches(payload)
    assert len(matches) == 9  # 9 substring candidates for query "700"

    match = _select_exact_stock_match(matches, "700")
    assert match == HKStockMatch(stock_id=7609, code="00700", name="TENCENT")


def test_select_exact_stock_match_raises_with_near_misses_when_no_exact_match() -> None:
    matches = [
        HKStockMatch(stock_id=1, code="01700", name="HUAJIN INTL"),
        HKStockMatch(stock_id=2, code="02700", name="ASIA RESOURCES"),
    ]
    with pytest.raises(HKEXStockNotFoundError, match="01700"):
        _select_exact_stock_match(matches, "700")


def test_select_exact_stock_match_raises_when_no_candidates_at_all() -> None:
    with pytest.raises(HKEXStockNotFoundError):
        _select_exact_stock_match([], "99999")


def test_normalize_hk_code_zero_pads_short_input() -> None:
    assert _normalize_hk_code("700") == "00700"
    assert _normalize_hk_code("00700") == "00700"


def test_normalize_hk_code_rejects_non_numeric() -> None:
    with pytest.raises(ValueError, match="Not a valid"):
        _normalize_hk_code("abc")


def test_resolve_stock_id_wires_fake_client_through_to_exact_match() -> None:
    client = _FakeClient({"partial.do": _read("partial_do_multi_candidate.txt")})
    match = resolve_stock_id(client, "700")  # type: ignore[arg-type]
    assert match.stock_id == 7609
    assert match.code == "00700"
    call = client.calls[0]
    assert call["params"]["lang"] == "EN"
    assert call["params"]["name"] == "700"


# --- titleSearchServlet.do doubly-encoded response, dual-counter STOCK_CODE -


def test_parse_filing_search_payload_double_decodes_real_tencent_fixture() -> None:
    rows = parse_filing_search_payload(_read("servlet_annual_reports_tencent.json"))
    assert len(rows) == 8
    newest = rows[0]
    assert isinstance(newest, HKEXFilingRow)
    assert newest.title == "ANNUAL REPORT 2025"
    assert newest.stock_codes == ("00700", "80700")  # dual-counter STOCK_CODE split
    assert newest.pdf_url == (
        "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0409/2026040901231.pdf"
    )

    older = rows[3]
    assert older.title == "ANNUAL REPORT 2022"
    assert older.stock_codes == ("00700",)  # single counter, no <br/> to split


def test_parse_filing_search_payload_empty_body_raises_blocked() -> None:
    with pytest.raises(HKEXSearchBlocked):
        parse_filing_search_payload("", step="annual report search")


def test_parse_filing_search_payload_null_result_is_legitimate_zero_rows() -> None:
    assert parse_filing_search_payload('{"result": null, "recordCnt": 0}') == []


def test_split_stock_codes_handles_single_and_dual_counter() -> None:
    assert _split_stock_codes("00700<br/>80700") == ("00700", "80700")
    assert _split_stock_codes("00700") == ("00700",)


def test_parse_hk_datetime_handles_date_and_time() -> None:
    dt = _parse_hk_datetime("09/04/2026 17:21")
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 4, 9, 17, 21)


def test_list_annual_reports_wires_fake_client_and_params() -> None:
    client = _FakeClient({"titleSearchServlet.do": _read("servlet_annual_reports_tencent.json")})
    rows = list_annual_reports(client, 7609)  # type: ignore[arg-type]
    assert len(rows) == 8
    call = client.calls[0]
    assert call["params"]["stockId"] == "7609"
    assert call["params"]["t1code"] == "40000"
    assert call["params"]["t2code"] == "40100"


# --- selection + staleness --------------------------------------------------


def test_select_latest_annual_report_picks_newest_from_real_fixture() -> None:
    rows = parse_filing_search_payload(_read("servlet_annual_reports_tencent.json"))
    selected = select_latest_annual_report(rows, stock_code="00700")
    assert selected.title == "ANNUAL REPORT 2025"


def test_select_latest_annual_report_rejects_stale_result_set() -> None:
    rows = parse_filing_search_payload(_read("servlet_annual_reports_stale.json"))
    with pytest.raises(HKEXStaleFilingError, match="stale"):
        select_latest_annual_report(rows, stock_code="09999")


def test_select_latest_annual_report_raises_when_no_rows() -> None:
    with pytest.raises(LookupError):
        select_latest_annual_report([], stock_code="00700")


def test_select_latest_annual_report_raises_when_no_annual_report_titles() -> None:
    from datetime import datetime

    rows = [
        HKEXFilingRow(
            news_id="1",
            title="2025 SUSTAINABILITY REPORT",
            date_time=datetime(2026, 6, 1),
            file_link="/x.pdf",
            file_info="1MB",
            stock_codes=("09999",),
        )
    ]
    with pytest.raises(LookupError, match="Annual Report"):
        select_latest_annual_report(rows, stock_code="09999")


def test_months_before_handles_year_rollover_and_day_clamping() -> None:
    from datetime import date

    assert _months_before(date(2026, 4, 9), 18) == date(2024, 10, 9)
    assert _months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)


# --- fiscal year parsing + HKFilingRef conversion ---------------------------


@pytest.mark.parametrize(
    ("title", "year"),
    [
        ("ANNUAL REPORT 2025", 2025),
        ("FISCAL YEAR 2026 ANNUAL REPORT", 2026),
        ("2025 ANNUAL REPORT", 2025),
        ("Annual Report 2023 (Printed version)", 2023),
        ("Annual Report and Accounts 2025 (with employee share plans)", 2025),
    ],
)
def test_parse_fiscal_year_across_observed_title_formats(title: str, year: int) -> None:
    assert _parse_fiscal_year(title) == year


def test_parse_fiscal_year_raises_when_no_year_present() -> None:
    with pytest.raises(ValueError, match="fiscal year"):
        _parse_fiscal_year("ANNUAL REPORT")


def test_to_filing_ref_produces_adapter_compatible_shape() -> None:
    rows = parse_filing_search_payload(_read("servlet_annual_reports_tencent.json"))
    selected = select_latest_annual_report(rows, stock_code="00700")
    ref = to_filing_ref(selected, stock_code="700")

    assert isinstance(ref, HKFilingRef)
    assert ref.stock_code == "00700"
    assert ref.fiscal_year == 2025
    assert ref.pdf_url.startswith("https://www1.hkexnews.hk")
    assert ref.announcement_date == "09/04/2026"


# --- end-to-end wiring (fake client, no live network) -----------------------


def test_find_latest_annual_report_end_to_end_with_fake_client() -> None:
    client = _FakeClient(
        {
            "titlesearch.xhtml": "<html>ok</html>",
            "partial.do": _read("partial_do_multi_candidate.txt"),
            "titleSearchServlet.do": _read("servlet_annual_reports_tencent.json"),
        }
    )
    ref = find_latest_annual_report("700", client=client)  # type: ignore[arg-type]
    assert ref.stock_code == "00700"
    assert ref.fiscal_year == 2025


def test_warm_up_raises_blocked_on_empty_body() -> None:
    client = _FakeClient({"titlesearch.xhtml": ""})
    with pytest.raises(HKEXSearchBlocked):
        warm_up(client)  # type: ignore[arg-type]


def test_download_pdf_writes_bytes_via_injected_client(tmp_path: Path) -> None:
    class _BytesResponse(_FakeResponse):
        def __init__(self, content: bytes) -> None:
            super().__init__("")
            self.content = content

    class _BytesClient(_FakeClient):
        def get(self, url: str, **kwargs: Any) -> _BytesResponse:  # type: ignore[override]
            self.calls.append({"url": url, **kwargs})
            return _BytesResponse(b"%PDF-1.4\n")

    ref = HKFilingRef(
        stock_code="00700",
        fiscal_year=2025,
        pdf_url="https://www1.hkexnews.hk/x.pdf",
        announcement_date="09/04/2026",
    )
    out_path = tmp_path / "nested" / "0700_2025.pdf"
    download_pdf(ref, out_path, client=_BytesClient({}))  # type: ignore[arg-type]
    assert out_path.read_bytes() == b"%PDF-1.4\n"


def test_download_pdf_accepts_legacy_two_positional_arg_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """edgarpack.hk.adapter calls download_pdf(ref, out) with no client kwarg."""
    import httpx

    class _StubResponse:
        content = b"%PDF-1.4\n"

        def raise_for_status(self) -> None:
            pass

    class _StubClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def get(self, url: str, **kwargs: Any) -> _StubResponse:
            return _StubResponse()

        def close(self) -> None:
            pass

    monkeypatch.setattr(httpx, "Client", _StubClient)
    ref = HKFilingRef(
        stock_code="00700",
        fiscal_year=2025,
        pdf_url="https://www1.hkexnews.hk/x.pdf",
        announcement_date="09/04/2026",
    )
    out_path = tmp_path / "legacy.pdf"
    download_pdf(ref, out_path)
    assert out_path.read_bytes() == b"%PDF-1.4\n"


# --- metadata extraction (IFRS/RMB, HKFRS/HKD, missing-anchor failure) ------


def test_extract_metadata_from_text_ifrs_rmb_real_tencent_excerpt() -> None:
    meta = extract_metadata_from_text(_read("metadata_ifrs_rmb.txt"), source="tencent.pdf")
    assert meta == HKFilingMeta(
        currency="CNY", accounting_standard="IFRS", legal_name="Tencent Holdings Limited"
    )


def test_extract_metadata_from_text_hkfrs_hkd_synthetic_excerpt() -> None:
    meta = extract_metadata_from_text(_read("metadata_hkfrs_hkd.txt"), source="example.pdf")
    assert meta.currency == "HKD"
    assert meta.accounting_standard == "HKFRS"
    assert meta.legal_name == "Example Holdings Limited"


def test_extract_metadata_from_text_raises_when_both_anchors_missing() -> None:
    with pytest.raises(HKFilingMetadataError, match="presentation currency"):
        extract_metadata_from_text(_read("metadata_missing_anchor.txt"), source="other.pdf")


def test_find_legal_name_returns_none_when_no_corporate_information_section() -> None:
    assert _find_legal_name("Just some unrelated text with no section headers.") is None
