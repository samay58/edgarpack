"""CNINFO acquisition connector.

MVP implementation intentionally keeps connector behavior deterministic.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast
from urllib.parse import urljoin


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
    excluded = ("摘要", "更正", "修订", "取消", "问询", "说明", "已取消")
    return not any(token in title for token in excluded)


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
        source_url = _cninfo_pdf_url(
            item.get("adjunctUrl") or item.get("sourceUrl") or item.get("url")
        )
        filing_date = _date_from_cninfo_url(source_url) or _parse_cninfo_date(
            item.get("announcementTime")
            or item.get("announcementDate")
            or item.get("time")
            or item.get("date")
        )
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
    return sorted(candidates, key=lambda ref: (ref.filing_date, ref.source_url), reverse=True)[0]


def _cninfo_market_params(stock_code: str) -> tuple[str, str]:
    code = stock_code.strip()
    if code.startswith("6"):
        return "sse", "sh"
    return "szse", "sz"


def _cninfo_annual_query_data(stock_code: str) -> dict[str, str]:
    column, plate = _cninfo_market_params(stock_code)
    return {
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


def fetch_cninfo_announcements(stock_code: str) -> dict[str, Any]:
    """Fetch CNINFO annual-report search results for a stock code."""
    import httpx

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.cninfo.com.cn",
        "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch",
        "User-Agent": "edgarpack/0.1 (+https://github.com)",
    }
    data = _cninfo_annual_query_data(stock_code)
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
    return selected
