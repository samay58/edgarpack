from unittest.mock import patch

from edgarpack.hk.acquire import HKFilingRef, find_annual_report


def test_find_annual_report_parses_index_entry():
    pdf_path = "/listedco/listconews/sehk/2024/0326/2024032600840.pdf"
    fake_html = (
        "<table><tr><td>26/03/2024</td>"
        f'<td><a href="{pdf_path}">Annual Report 2023</a></td></tr></table>'
    )
    with patch("edgarpack.hk.acquire._fetch_index", return_value=fake_html):
        ref = find_annual_report(stock_code="00700", fiscal_year=2023)
    assert isinstance(ref, HKFilingRef)
    assert ref.stock_code == "00700"
    assert ref.fiscal_year == 2023
    assert ref.pdf_url.startswith("https://www1.hkexnews.hk")
    assert ref.pdf_url.endswith(".pdf")
    assert ref.announcement_date == "26/03/2024"


def test_find_annual_report_raises_when_year_missing():
    import pytest

    fake_html = '<a href="/foo/2023.pdf">Annual Report 2022</a>'
    with patch("edgarpack.hk.acquire._fetch_index", return_value=fake_html):
        with pytest.raises(FileNotFoundError):
            find_annual_report(stock_code="00700", fiscal_year=2023)
