"""English-first bilingual table surface for China-path query results.

Bilingual metric cells ("Revenue (营业收入)") and the filing-type context
line render only for China-path values (accounting_standard CAS/HKFRS
carrying a non-empty matched_label). SEC and registration table output, and
all JSON output, are unaffected.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from edgarpack.query.models import CitedValue, QueryResult
from edgarpack.query.render import _render_query_table


def _sse_revenue(matched_label: str = "营业收入", value: float = 4.5e9) -> CitedValue:
    return CitedValue(
        value=value,
        unit="CNY",
        metric="revenue",
        concept="Revenue",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="ANNUAL-REPORT",
        filed=date(2025, 4, 28),
        accession="600519-2024-AR",
        cik="600519",
        company="Kweichow Moutai Co Ltd",
        accounting_standard="CAS",
        reporting_currency="CNY",
        section_id="income-statement",
        matched_label=matched_label,
    )


def _hk_revenue(matched_label: str = "收益") -> CitedValue:
    return CitedValue(
        value=2.1e9,
        unit="HKD",
        metric="revenue",
        concept="Revenue",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="Annual Report",
        filed=date(2025, 3, 20),
        accession="00700-2024-AR",
        cik="00700",
        company="Tencent Holdings Ltd",
        accounting_standard="HKFRS",
        reporting_currency="HKD",
        section_id="income-statement",
        matched_label=matched_label,
    )


def _sec_revenue() -> CitedValue:
    return CitedValue(
        value=130e9,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2025, 1, 26),
        fiscal_year=2025,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 26),
        accession="0001045810-25-000001",
        cik="0001045810",
        company="NVIDIA CORP",
    )


def _args(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = dict(
        citations="inline",
        show_links="none",
        audit=False,
        currency="native",
        strict=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestBilingualCell:
    def test_short_label_renders_bilingual_cell(self) -> None:
        qr = QueryResult(
            company="Kweichow Moutai Co Ltd",
            cik="600519",
            period="lfy",
            metrics={"revenue": _sse_revenue("营业收入")},
        )
        out = _render_query_table(qr, _args())
        assert "Revenue (营业收入)" in out

    def test_long_label_truncates_without_ellipsis_and_footer_carries_full_label(self) -> None:
        long_label = "归属于母公司所有者的净利润和营业总收入合计金额说明汇总统计表格"
        assert len(long_label) > 24
        qr = QueryResult(
            company="Kweichow Moutai Co Ltd",
            cik="600519",
            period="lfy",
            metrics={"revenue": _sse_revenue(long_label)},
        )
        out = _render_query_table(qr, _args())
        truncated = long_label[:24]
        assert f"Revenue ({truncated})" in out
        assert "…" not in out
        assert "..." not in out
        # Full label recovers from the citation line, not the truncated cell.
        assert long_label in out

    def test_context_line_sse(self) -> None:
        qr = QueryResult(
            company="Kweichow Moutai Co Ltd",
            cik="600519",
            period="lfy",
            metrics={"revenue": _sse_revenue()},
        )
        out = _render_query_table(qr, _args())
        assert (
            "Source: 年度报告 (annual report) filed with CNINFO, the A-share equivalent of a 10-K."
            in out
        )

    def test_context_line_hkex(self) -> None:
        qr = QueryResult(
            company="Tencent Holdings Ltd",
            cik="00700",
            period="lfy",
            metrics={"revenue": _hk_revenue()},
        )
        out = _render_query_table(qr, _args())
        assert "Source: annual report filed with HKEX news." in out

    def test_no_matched_label_no_bilingual_cell(self) -> None:
        cv = _sse_revenue(matched_label="")
        qr = QueryResult(
            company="Kweichow Moutai Co Ltd",
            cik="600519",
            period="lfy",
            metrics={"revenue": cv},
        )
        out = _render_query_table(qr, _args())
        assert "Revenue:" in out
        assert "(" not in out.splitlines()[2]


class TestSecUnaffected:
    def test_sec_table_byte_identical(self) -> None:
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": _sec_revenue()},
        )
        out = _render_query_table(qr, _args())
        expected = (
            "NVIDIA CORP (CIK: 0001045810)\n"
            "\n"
            "Revenue: $130.0B [C1]\n"
            "[C1] 10-K FY2025 | period 2025-01-26 | filing 0001045810-25-000001 "
            "| filed 2025-02-26\n"
            "\n"
            "Reproduce: edgarpack query 0001045810 revenue --period lfy"
        )
        assert out == expected

    def test_no_context_line_for_sec(self) -> None:
        qr = QueryResult(
            company="NVIDIA CORP",
            cik="0001045810",
            period="lfy",
            metrics={"revenue": _sec_revenue()},
        )
        out = _render_query_table(qr, _args())
        assert "Source:" not in out


class TestJsonUnaffected:
    def test_lean_json_has_no_context_line_or_parenthesized_label(self) -> None:
        qr = QueryResult(
            company="Kweichow Moutai Co Ltd",
            cik="600519",
            period="lfy",
            metrics={"revenue": _sse_revenue("营业收入")},
        )
        payload = qr.to_lean_dict()
        assert list(payload["metrics"].keys()) == ["revenue"]
        assert "Source:" not in str(payload)
        assert "(营业收入)" not in str(payload)

    def test_cited_json_has_no_context_line_or_parenthesized_label(self) -> None:
        qr = QueryResult(
            company="Kweichow Moutai Co Ltd",
            cik="600519",
            period="lfy",
            metrics={"revenue": _sse_revenue("营业收入")},
        )
        payload = qr.to_cited_dict()
        assert list(payload["metrics"].keys()) == ["revenue"]
        assert "Source:" not in str(payload)
        assert "(营业收入)" not in str(payload)
