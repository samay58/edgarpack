from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx

_INDEX_URL = (
    "https://www1.hkexnews.hk/listedco/listconews/advancedsearch/search_active_main.aspx"
)
_BASE = "https://www1.hkexnews.hk"


@dataclass(frozen=True)
class HKFilingRef:
    stock_code: str
    fiscal_year: int
    pdf_url: str
    announcement_date: str


def _fetch_index(stock_code: str) -> str:
    resp = httpx.get(
        _INDEX_URL,
        params={"stockcode": stock_code, "documenttype": "Annual Report"},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def find_annual_report(stock_code: str, fiscal_year: int) -> HKFilingRef:
    html = _fetch_index(stock_code)
    pattern = re.compile(
        rf'(\d{{2}}/\d{{2}}/\d{{4}}).*?<a href="([^"]+\.pdf)"[^>]*>Annual Report {fiscal_year}',
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(html)
    if not m:
        raise FileNotFoundError(
            f"No Annual Report {fiscal_year} found for stock code {stock_code}"
        )
    announcement_date, href = m.group(1), m.group(2)
    pdf_url = href if href.startswith("http") else _BASE + href
    return HKFilingRef(
        stock_code=stock_code,
        fiscal_year=fiscal_year,
        pdf_url=pdf_url,
        announcement_date=announcement_date,
    )


def download_pdf(ref: HKFilingRef, out_path: Path) -> None:
    resp = httpx.get(ref.pdf_url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
