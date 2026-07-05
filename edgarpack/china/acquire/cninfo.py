"""CNINFO acquisition connector.

MVP implementation intentionally keeps connector behavior deterministic.
"""

from __future__ import annotations

import calendar
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

_STALENESS_FLOOR_MONTHS = 18


@dataclass(frozen=True)
class CninfoAnnualReportRef:
    """Primary-source annual report selected from CNINFO announcement search."""

    stock_code: str
    company_name: str
    title: str
    filing_date: date
    source_url: str


def _clean_title(title: object) -> str:
    text = re.sub(r"<[^>]+>", "", str(title or ""))
    return text.replace("&nbsp;", " ").strip()


def _is_full_annual_report(title: str) -> bool:
    lower = title.lower()
    if "annual report" in lower:
        return "summary" not in lower
    if "年度报告" not in title:
        return False
    if "英文版" in title:
        return False
    excluded = ("摘要", "更正", "修订", "取消", "问询", "说明", "已取消")
    return not any(token in title for token in excluded)


def _prefers_chinese_edition(title: str) -> bool:
    """True unless the title carries an English-edition marker.

    `_is_full_annual_report` already drops titles containing the literal
    "英文版" token, but some filers label the English edition "(英文)" without
    the trailing 版. This is a second, broader check used only to break a
    same-date tie deterministically, never to exclude a candidate outright.
    """
    return "英文" not in title


def _parse_cninfo_date(value: object) -> date | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
        except (OSError, OverflowError, ValueError):
            return None

    text = str(value or "").strip()
    if not text:
        return None
    text = text.split(" ", 1)[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _cninfo_pdf_url(adjunct_url: object) -> str:
    raw = str(adjunct_url or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    return urljoin("https://static.cninfo.com.cn/", raw.lstrip("/"))


def _date_from_cninfo_url(source_url: str) -> date | None:
    match = re.search(r"/(\d{4}-\d{2}-\d{2})/", source_url)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _extract_announcement_fields(item: dict[str, Any]) -> tuple[str, date | None]:
    """Parse (pdf_source_url, filing_date) out of a raw CNINFO announcement row."""
    source_url = _cninfo_pdf_url(item.get("adjunctUrl") or item.get("sourceUrl") or item.get("url"))
    filing_date = _date_from_cninfo_url(source_url) or _parse_cninfo_date(
        item.get("announcementTime")
        or item.get("announcementDate")
        or item.get("time")
        or item.get("date")
    )
    return source_url, filing_date


def _newest_announcement_date(announcements: list[Any]) -> date | None:
    """Newest filing_date across every announcement in the payload.

    Used as the staleness anchor, not just the dates of full-annual-report
    candidates, so a selection that lags behind fresher (but filtered-out)
    announcements in the same result set gets caught.
    """
    dates: list[date] = []
    for item in announcements:
        if not isinstance(item, dict):
            continue
        _, filing_date = _extract_announcement_fields(item)
        if filing_date is not None:
            dates.append(filing_date)
    return max(dates) if dates else None


def _months_before(anchor: date, months: int) -> date:
    month_index = anchor.year * 12 + (anchor.month - 1) - months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def latest_annual_from_cninfo_payload(
    payload: dict[str, Any],
    *,
    stock_code: str,
) -> CninfoAnnualReportRef | None:
    """Select the newest full annual report from a CNINFO search response."""
    announcements = payload.get("announcements") or payload.get("data") or []
    if not isinstance(announcements, list):
        return None

    candidates: list[CninfoAnnualReportRef] = []
    for item in announcements:
        if not isinstance(item, dict):
            continue
        item_code = str(item.get("secCode") or item.get("stockCode") or "").strip()
        if item_code and item_code != stock_code:
            continue
        title = _clean_title(item.get("announcementTitle") or item.get("title"))
        if not _is_full_annual_report(title):
            continue
        source_url, filing_date = _extract_announcement_fields(item)
        if filing_date is None or not source_url:
            continue
        company_name = _clean_title(item.get("secName") or item.get("companyName"))
        candidates.append(
            CninfoAnnualReportRef(
                stock_code=stock_code,
                company_name=company_name,
                title=title,
                filing_date=filing_date,
                source_url=source_url,
            )
        )

    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda ref: (ref.filing_date, _prefers_chinese_edition(ref.title), ref.source_url),
        reverse=True,
    )[0]


def _cninfo_market_params(stock_code: str) -> tuple[str, str]:
    code = stock_code.strip()
    if code.startswith("6"):
        return "sse", "sh"
    return "szse", "sz"


def _cninfo_annual_query_data(stock_code: str, *, org_id: str | None = None) -> dict[str, str]:
    column, plate = _cninfo_market_params(stock_code)
    data = {
        "pageNum": "1",
        "pageSize": "30",
        "column": column,
        "tabName": "fulltext",
        "plate": plate,
        "stock": "",
        "searchkey": stock_code,
        "secid": "",
        "category": "category_ndbg_szsh",
        "trade": "",
        "seDate": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    if org_id:
        # stock=<code>,<orgId> returns the filer's full history; searchkey=<code>
        # is a full-text search that can miss recent filings entirely.
        data["stock"] = f"{stock_code},{org_id}"
        data["searchkey"] = ""
    return data


def _org_id_query_data(stock_code: str) -> dict[str, str]:
    return {"keyWord": stock_code, "maxNum": "10"}


def _org_id_from_topsearch_payload(payload: Any, stock_code: str) -> str | None:
    """Parse CNINFO's topSearch response: a bare JSON list of {code, orgId, ...}."""
    if not isinstance(payload, list):
        return None
    for item in payload:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if code != stock_code:
            continue
        org_id = str(item.get("orgId") or "").strip()
        if org_id:
            return org_id
    return None


def _post_cninfo_topsearch(stock_code: str) -> Any:
    import httpx

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.cninfo.com.cn",
        "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch",
        "User-Agent": "edgarpack/0.1 (+https://github.com)",
    }
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        response = client.post(
            "https://www.cninfo.com.cn/new/information/topSearch/query",
            headers=headers,
            data=_org_id_query_data(stock_code),
        )
        response.raise_for_status()
        return response.json()


def _resolve_cninfo_org_id(
    stock_code: str,
    *,
    poster: Callable[[str], Any] = _post_cninfo_topsearch,
) -> str | None:
    """Resolve the orgId CNINFO's `stock=` parameter needs for full filing history.

    Any failure (network error, unexpected shape, no match) returns None so the
    caller falls back to the old searchkey= full-text search rather than
    blocking acquisition.
    """
    try:
        payload = poster(stock_code)
    except Exception as exc:
        logger.warning(
            "CNINFO orgId resolution failed for %s: %s; falling back to searchkey search",
            stock_code,
            exc,
        )
        return None
    return _org_id_from_topsearch_payload(payload, stock_code)


def fetch_cninfo_announcements(stock_code: str) -> dict[str, Any]:
    """Fetch CNINFO annual-report search results for a stock code."""
    import httpx

    org_id = _resolve_cninfo_org_id(stock_code)
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.cninfo.com.cn",
        "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch",
        "User-Agent": "edgarpack/0.1 (+https://github.com)",
    }
    data = _cninfo_annual_query_data(stock_code, org_id=org_id)
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.post(
            "https://www.cninfo.com.cn/new/hisAnnouncement/query",
            headers=headers,
            data=data,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())


def find_latest_annual_report(
    stock_code: str,
    *,
    fetcher: Callable[[str], dict[str, Any]] = fetch_cninfo_announcements,
) -> CninfoAnnualReportRef:
    """Return the latest CNINFO full annual report for an A-share stock code."""
    payload = fetcher(stock_code)
    selected = latest_annual_from_cninfo_payload(payload, stock_code=stock_code)
    if selected is None:
        raise LookupError(f"No full annual report found on CNINFO for {stock_code}")

    # Staleness is measured against the newest announcement date IN THE PAYLOAD,
    # not wall-clock time: acquisition must stay reproducible against a recorded
    # payload fixture no matter when it is replayed.
    announcements = payload.get("announcements") or payload.get("data") or []
    newest = _newest_announcement_date(announcements) if isinstance(announcements, list) else None
    if newest is not None:
        floor = _months_before(newest, _STALENESS_FLOOR_MONTHS)
        if selected.filing_date < floor:
            raise LookupError(
                f"Latest full annual report found on CNINFO for {stock_code} is "
                f"'{selected.title}' filed {selected.filing_date.isoformat()}, more than "
                f"{_STALENESS_FLOOR_MONTHS} months before the newest announcement in this "
                f"result set ({newest.isoformat()}). Rejecting as stale rather than returning "
                "a years-old filing as the latest annual report."
            )
    return selected
