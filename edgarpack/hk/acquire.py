"""HKEX filing acquisition: ticker to stockId to English annual report PDF.

The search API is JSONP/session-cookie based (Akamai bot protection), verified
live for 0700, 9988, 3690, 1211, 0005 during the 2026-07-05 spike. See
docs/phase3-specs/build-hk.md for the full flow contract.
"""

from __future__ import annotations

import json
import re
import time
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import httpx

_BASE = "https://www1.hkexnews.hk"
_WARMUP_URL = f"{_BASE}/search/titlesearch.xhtml"
_PARTIAL_URL = f"{_BASE}/search/partial.do"
_SERVLET_URL = f"{_BASE}/search/titleSearchServlet.do"
_REFERER = f"{_WARMUP_URL}?lang=en"
_USER_AGENT = "edgarpack/0.1 (+https://github.com)"

# Financial Statements/ESG Information > Annual Report.
_ANNUAL_REPORT_T1CODE = "40000"
_ANNUAL_REPORT_T2CODE = "40100"
# Announcements and Notices > Financial Information > Final Results.
_FINAL_RESULTS_T1CODE = "10000"
_FINAL_RESULTS_T2GCODE = "3"
_FINAL_RESULTS_T2CODE = "13300"

_STALENESS_FLOOR_MONTHS = 18

_LAST_REQUEST_TIME = 0.0
_MIN_INTERVAL = 1.0  # 1 req/s, mirrors edgarpack/sse/client.py pacing


def _rate_limit() -> None:
    global _LAST_REQUEST_TIME
    now = time.monotonic()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_REQUEST_TIME = time.monotonic()


class HKEXSearchBlocked(RuntimeError):  # noqa: N818
    """An HKEX search endpoint returned an empty response body.

    Empty is ambiguous between an Akamai/anti-bot block and a genuine
    zero-result search. Treating it as "no filings" would silently under
    report real filings, so callers must retry rather than accept it as a
    negative result.
    """


class HKEXStockNotFoundError(LookupError):
    """No exact-match stock code survived the partial.do substring search."""


class HKEXStaleFilingError(LookupError):
    """The selected annual report predates the staleness floor."""


class HKFilingMetadataError(ValueError):
    """A filing's text is missing a mandated IAS 1 / HKAS 1 anchor disclosure."""


@dataclass(frozen=True)
class HKStockMatch:
    stock_id: int
    code: str
    name: str


@dataclass(frozen=True)
class HKEXFilingRow:
    news_id: str
    title: str
    date_time: datetime
    file_link: str
    file_info: str
    stock_codes: tuple[str, ...]

    @property
    def pdf_url(self) -> str:
        return _BASE + self.file_link


@dataclass(frozen=True)
class HKFilingRef:
    stock_code: str
    fiscal_year: int
    pdf_url: str
    announcement_date: str


@dataclass(frozen=True)
class HKFilingMeta:
    currency: str
    accounting_standard: str
    legal_name: str | None


def _blocked_message(step: str) -> str:
    return (
        f"HKEX {step} returned an empty response body. This is ambiguous between an "
        "Akamai/anti-bot block and a genuine zero-result search; retry (a fresh warm-up "
        "may be needed) rather than treating it as no filings."
    )


def _normalize_hk_code(code: str) -> str:
    digits = re.sub(r"\D", "", code)
    if not digits:
        raise ValueError(f"Not a valid HKEX stock code: {code!r}")
    return digits.zfill(5)


def _default_client(*, timeout: float) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=timeout)


def warm_up(client: httpx.Client) -> None:
    """Prime the session's Akamai cookie jar. Run once before resolve/list calls."""
    _rate_limit()
    resp = client.get(_WARMUP_URL, params={"lang": "en"})
    resp.raise_for_status()
    if not resp.text or not resp.text.strip():
        raise HKEXSearchBlocked(_blocked_message("search warm-up"))


_JSONP_RE = re.compile(r"^callback\((.*)\)\s*;?\s*$", re.DOTALL)


def _strip_jsonp(raw_text: str, *, step: str) -> dict[str, Any]:
    if not raw_text or not raw_text.strip():
        raise HKEXSearchBlocked(_blocked_message(step))
    match = _JSONP_RE.match(raw_text.strip())
    if not match:
        raise HKEXSearchBlocked(
            f"HKEX {step} response was not JSONP-wrapped as expected (got: {raw_text[:200]!r})"
        )
    return cast(dict[str, Any], json.loads(match.group(1)))


def _parse_stock_matches(payload: dict[str, Any]) -> list[HKStockMatch]:
    matches = []
    for entry in payload.get("stockInfo") or []:
        matches.append(
            HKStockMatch(
                stock_id=int(entry["stockId"]),
                code=str(entry["code"]),
                name=str(entry.get("name", "")),
            )
        )
    return matches


def _select_exact_stock_match(matches: list[HKStockMatch], code: str) -> HKStockMatch:
    target = _normalize_hk_code(code)
    exact = [m for m in matches if m.code == target]
    if exact:
        return exact[0]
    if matches:
        near = ", ".join(f"{m.code} ({m.name})" for m in matches[:10])
        raise HKEXStockNotFoundError(
            f"No exact HKEX stock code match for {code!r} (normalized {target!r}) among "
            f"{len(matches)} substring candidates. Near misses: {near}"
        )
    raise HKEXStockNotFoundError(
        f"No HKEX stock code candidates at all for {code!r} (normalized {target!r})"
    )


def resolve_stock_id(client: httpx.Client, code: str) -> HKStockMatch:
    """Resolve a ticker/code to its numeric HKEX stockId.

    partial.do does a SUBSTRING match over all exchange codes (including
    warrants/CBBCs), so a query like "700" can return dozens of candidates;
    this filters down to the exact zero-padded code.
    """
    _rate_limit()
    resp = client.get(
        _PARTIAL_URL,
        params={"lang": "EN", "type": "A", "name": code, "market": "SEHK", "callback": "callback"},
        headers={"Referer": _REFERER},
    )
    resp.raise_for_status()
    payload = _strip_jsonp(resp.text, step="stock resolution (partial.do)")
    matches = _parse_stock_matches(payload)
    return _select_exact_stock_match(matches, code)


def _split_stock_codes(field_value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in field_value.split("<br/>") if part.strip())


_HK_DATETIME_FORMATS = ("%d/%m/%Y %H:%M", "%d/%m/%Y")


def _parse_hk_datetime(value: str) -> datetime:
    text = value.strip()
    for fmt in _HK_DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized HKEX DATE_TIME format: {value!r}")


def parse_filing_search_payload(
    raw_text: str, *, step: str = "filing search"
) -> list[HKEXFilingRow]:
    """Parse a titleSearchServlet.do response body.

    The response's own `result` field is a JSON string, not a nested object:
    it must be decoded twice.
    """
    if not raw_text or not raw_text.strip():
        raise HKEXSearchBlocked(_blocked_message(step))
    envelope = cast(dict[str, Any], json.loads(raw_text))
    result_field = envelope.get("result")
    if result_field in (None, "null", ""):
        return []
    rows_raw = cast(list[dict[str, Any]], json.loads(cast(str, result_field)))
    rows = []
    for row in rows_raw:
        rows.append(
            HKEXFilingRow(
                news_id=str(row["NEWS_ID"]),
                title=str(row["TITLE"]),
                date_time=_parse_hk_datetime(str(row["DATE_TIME"])),
                file_link=str(row["FILE_LINK"]),
                file_info=str(row["FILE_INFO"]),
                stock_codes=_split_stock_codes(str(row["STOCK_CODE"])),
            )
        )
    return rows


def _filing_search_params(
    stock_id: int,
    *,
    t1code: str,
    t2code: str,
    t2gcode: str,
    from_date: str,
    to_date: str,
) -> dict[str, str]:
    return {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": str(stock_id),
        "documentType": "-1",
        "fromDate": from_date,
        "toDate": to_date,
        "title": "",
        "searchType": "1",
        "t1code": t1code,
        "t2Gcode": t2gcode,
        "t2code": t2code,
        "rowRange": "100",
        "lang": "E",
    }


def list_annual_reports(
    client: httpx.Client,
    stock_id: int,
    *,
    from_date: str = "19990101",
    to_date: str | None = None,
) -> list[HKEXFilingRow]:
    _rate_limit()
    resp = client.get(
        _SERVLET_URL,
        params=_filing_search_params(
            stock_id,
            t1code=_ANNUAL_REPORT_T1CODE,
            t2code=_ANNUAL_REPORT_T2CODE,
            t2gcode="-1",
            from_date=from_date,
            to_date=to_date or date.today().strftime("%Y%m%d"),
        ),
        headers={"Referer": _REFERER},
    )
    resp.raise_for_status()
    return parse_filing_search_payload(resp.text, step="annual report search")


def list_results_announcements(
    client: httpx.Client,
    stock_id: int,
    *,
    from_date: str = "19990101",
    to_date: str | None = None,
) -> list[HKEXFilingRow]:
    """List final-results announcements. Not consumed by the build flow yet.

    Final results land roughly three weeks ahead of the annual report and
    share the same row shape; exposed as a sibling for a future faster-signal
    path or cross-check, not wired into `find_latest_annual_report`.
    """
    _rate_limit()
    resp = client.get(
        _SERVLET_URL,
        params=_filing_search_params(
            stock_id,
            t1code=_FINAL_RESULTS_T1CODE,
            t2code=_FINAL_RESULTS_T2CODE,
            t2gcode=_FINAL_RESULTS_T2GCODE,
            from_date=from_date,
            to_date=to_date or date.today().strftime("%Y%m%d"),
        ),
        headers={"Referer": _REFERER},
    )
    resp.raise_for_status()
    return parse_filing_search_payload(resp.text, step="final results search")


_NON_ANNUAL_REPORT_TITLE_MARKERS = (
    "sustainability report",
    "esg report",
    "environmental, social and governance report",
)


def _is_annual_report_title(title: str) -> bool:
    lower = title.lower()
    if "annual report" not in lower:
        return False
    return not any(marker in lower for marker in _NON_ANNUAL_REPORT_TITLE_MARKERS)


def _months_before(anchor: date, months: int) -> date:
    month_index = anchor.year * 12 + (anchor.month - 1) - months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


def select_latest_annual_report(rows: list[HKEXFilingRow], *, stock_code: str) -> HKEXFilingRow:
    """Pick the newest Annual Report row, rejecting a stale result set.

    Staleness mirrors the CNINFO connector: it is measured against the
    newest filing date found ANYWHERE in the payload (not wall-clock time),
    so a replayed fixture always gives the same verdict. This catches a
    resolved stockId whose annual reports are old even though the company
    is still filing other documents in the same category (e.g. ESG /
    Sustainability Reports share the Annual Report category on HKEX).
    """
    if not rows:
        raise LookupError(f"No filing rows returned for HKEX stock code {stock_code}")

    newest_overall = max(row.date_time for row in rows).date()

    candidates = [row for row in rows if _is_annual_report_title(row.title)]
    if not candidates:
        titles = [row.title for row in rows][:5]
        raise LookupError(
            f"{len(rows)} rows returned for HKEX stock code {stock_code} but none had an "
            f"'Annual Report' title (titles seen: {titles})"
        )

    selected = max(candidates, key=lambda row: row.date_time)

    floor = _months_before(newest_overall, _STALENESS_FLOOR_MONTHS)
    if selected.date_time.date() < floor:
        raise HKEXStaleFilingError(
            f"Latest annual report found for HKEX stock code {stock_code} is "
            f"'{selected.title}' filed {selected.date_time.date().isoformat()}, more than "
            f"{_STALENESS_FLOOR_MONTHS} months before the newest filing in this result set "
            f"({newest_overall.isoformat()}). Rejecting as stale rather than returning a "
            "years-old filing as the latest annual report."
        )
    return selected


_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _parse_fiscal_year(title: str) -> int:
    match = _YEAR_RE.search(title)
    if not match:
        raise ValueError(f"Could not parse a fiscal year out of annual report title: {title!r}")
    return int(match.group(0))


def to_filing_ref(row: HKEXFilingRow, *, stock_code: str) -> HKFilingRef:
    return HKFilingRef(
        stock_code=_normalize_hk_code(stock_code),
        fiscal_year=_parse_fiscal_year(row.title),
        pdf_url=row.pdf_url,
        announcement_date=row.date_time.strftime("%d/%m/%Y"),
    )


def find_latest_annual_report(
    stock_code: str, *, client: httpx.Client | None = None
) -> HKFilingRef:
    """Ticker/code to stockId to the latest English annual report reference."""
    owns_client = client is None
    active_client = client or _default_client(timeout=30.0)
    try:
        warm_up(active_client)
        match = resolve_stock_id(active_client, stock_code)
        rows = list_annual_reports(active_client, match.stock_id)
        selected = select_latest_annual_report(rows, stock_code=match.code)
        return to_filing_ref(selected, stock_code=match.code)
    finally:
        if owns_client:
            active_client.close()


def download_pdf(ref: HKFilingRef, out_path: Path, *, client: httpx.Client | None = None) -> None:
    """Download the referenced PDF.

    Accepts an optional shared `client` so a caller that already warmed up a
    session (see `find_latest_annual_report`) can reuse its cookie jar;
    defaults to a fresh client to stay compatible with callers (e.g.
    `edgarpack.hk.adapter`) that only pass the two positional arguments.
    """
    owns_client = client is None
    active_client = client or _default_client(timeout=120.0)
    try:
        _rate_limit()
        resp = active_client.get(ref.pdf_url, headers={"Referer": _REFERER})
        resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
    finally:
        if owns_client:
            active_client.close()


_PRESENTATION_ANCHOR_PATTERNS = (
    re.compile(
        r"presents?\s+its\s+(?:consolidated\s+)?financial\s+statements?\s+in\b",
        re.IGNORECASE,
    ),
    re.compile(r"financial\s+statements?\s+(?:are|is)\s+presented\s+in\b", re.IGNORECASE),
)

_CURRENCY_KEYWORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bRMB\b|Renminbi", re.IGNORECASE), "CNY"),
    (re.compile(r"Hong\s+Kong\s+dollars?|HK\$|\bHKD\b", re.IGNORECASE), "HKD"),
    (re.compile(r"United\s+States\s+dollars?|US\$|\bUSD\b", re.IGNORECASE), "USD"),
)

_STANDARD_KEYWORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"IFRS\s+Accounting\s+Standards|International\s+Financial\s+Reporting\s+Standards",
            re.IGNORECASE,
        ),
        "IFRS",
    ),
    (
        re.compile(r"Hong\s+Kong\s+Financial\s+Reporting\s+Standards|\bHKFRS\b", re.IGNORECASE),
        "HKFRS",
    ),
)

_CORP_SUFFIX_RE = re.compile(
    r"(Limited|Ltd\.?|Holdings|Inc\.?|Corporation|PLC|Group|Company)\s*$", re.IGNORECASE
)

_LEGAL_NAME_PREFIX_PAGES = 15


def _find_currency(text: str) -> str | None:
    for anchor in _PRESENTATION_ANCHOR_PATTERNS:
        match = anchor.search(text)
        if not match:
            continue
        window = text[match.end() : match.end() + 60]
        for pattern, iso in _CURRENCY_KEYWORDS:
            if pattern.search(window):
                return iso
    return None


def _find_accounting_standard(text: str) -> str | None:
    for pattern, name in _STANDARD_KEYWORDS:
        if pattern.search(text):
            return name
    return None


def _find_legal_name(text: str) -> str | None:
    """Best-effort legal name: the line immediately above a "Corporate
    Information" section header that ends in a corporate suffix.

    Verified against a real filing (Tencent's 2025 annual report places
    "Tencent Holdings Limited" directly above its Corporate Information
    page). Not a mandated anchor: returns None rather than guessing when
    the pattern is not found.
    """
    lines = [line.strip() for line in text.splitlines()]
    for i, line in enumerate(lines):
        if "corporate information" not in line.lower():
            continue
        for j in range(i - 1, max(-1, i - 6), -1):
            candidate = lines[j]
            if not candidate or candidate.isdigit():
                continue
            if _CORP_SUFFIX_RE.search(candidate):
                return candidate
            break
    return None


def extract_metadata_from_text(text: str, *, source: str = "<text>") -> HKFilingMeta:
    currency = _find_currency(text)
    standard = _find_accounting_standard(text)
    missing = []
    if currency is None:
        missing.append("presentation currency")
    if standard is None:
        missing.append("basis of preparation / accounting standard")
    if missing:
        raise HKFilingMetadataError(
            f"Could not find mandated IAS 1 / HKAS 1 disclosure(s) in {source}: "
            f"{', '.join(missing)}. Refusing to default the currency or accounting standard."
        )
    return HKFilingMeta(
        currency=cast(str, currency),
        accounting_standard=cast(str, standard),
        legal_name=_find_legal_name(text),
    )


def extract_filing_metadata(pdf_path: Path) -> HKFilingMeta:
    """Extract currency/accounting-standard/legal-name from an annual report PDF.

    Scans the full document text for the currency and accounting-standard
    anchors: real filings place these deep in the notes (verified: Tencent's
    2025 annual report states its basis of preparation on page 142 of 282),
    so a small fixed-page prefix would miss them. The legal name search stays
    scoped to the cover pages to avoid a false match on an unrelated deep
    mention of "Corporate Information".
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n".join(page_texts)

    meta = extract_metadata_from_text(full_text, source=pdf_path.name)
    if meta.legal_name is not None:
        return meta

    prefix_name = _find_legal_name("\n".join(page_texts[:_LEGAL_NAME_PREFIX_PAGES]))
    if prefix_name is None:
        return meta
    return HKFilingMeta(
        currency=meta.currency,
        accounting_standard=meta.accounting_standard,
        legal_name=prefix_name,
    )
