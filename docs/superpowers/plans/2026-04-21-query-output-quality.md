# Query Output Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four CLI output defects observed in `edgarpack query snap ...` testing: dumb unit/scale formatting, replicated rows across periods for discovered KPIs, `$-` / `-%` negatives instead of parens, and raw internals leaking to output (accn, `[learned:kpi-discovered ✓]`, `FY FY2025`, CIK-in-Reproduce).

**Architecture:** New `edgarpack/query/formatting.py` owns scale + precision + finance negatives. `comps._format_value` and `compare._format_value` delegate to it. `lookup_company_kpi` grows to return `CompanyKpiRow | list[CompanyKpiRow] | None` and understands `lfy-N`, `mrq-N`, `annual:N`, `quarterly:N`, plus LTM→LFY degradation. `financials()` consumes the richer return and emits diagnostics for LTM degrade and partial `annual:N` coverage. CLI renderer renames `accn` → `filing`, collapses `[learned:kpi-discovered ✓]` → `[discovered]`, removes the `FY FY` double-prefix, and preserves user's input ticker in the `Reproduce` line via a new `display_token` kwarg plumbed through `comps()`.

**Tech Stack:** Python 3.14, pytest, ruff, SQLite (existing `company_kpis` table), no new deps.

**Reference:** [`docs/superpowers/specs/2026-04-21-query-output-quality-design.md`](../specs/2026-04-21-query-output-quality-design.md)

---

## File Structure

**New:**
- `edgarpack/query/formatting.py` - `format_number()`, `_scale_value()`, `_CURRENCY_SYMBOLS`, parens wrapper.
- `tests/test_formatting.py` - primitive tests.
- `tests/test_kpi_discover_periods.py` - period-aware lookup tests.

**Modified:**
- `edgarpack/query/comps.py` - delete `_format_currency`, collapse `_format_value` to a delegation wrapper, re-import `_CURRENCY_SYMBOLS` from `formatting`.
- `edgarpack/compare.py` - delete `_abbrev_usd`, route numeric rendering through `format_number`.
- `edgarpack/query/kpi_discover.py` - rewrite `lookup_company_kpi` body; update return type.
- `edgarpack/query/financials.py` - handle list-return from `lookup_company_kpi`, emit `partial_coverage` and `ltm_degraded` diagnostics.
- `edgarpack/query/models.py` - `fiscal_label` property: drop `"FY "` prefix when `fiscal_period == "FY"`.
- `edgarpack/query/comps.py` - add `display_token: str | None` kwarg to `comps()`; use in permalink construction.
- `edgarpack/cli.py` - pass original CLI arg as `display_token`; rename `accn` → `filing` in citation renderer; compress `[learned:kpi-* ✓]` badges to `[discovered]`.
- `tests/test_comps.py`, `tests/test_cli_*.py` - update any snapshot assertions touching `$-`, `accn`, `FY FY`, or the old badge text.

---

## Task 1: Create the formatting primitive

**Files:**
- Create: `edgarpack/query/formatting.py`
- Create: `tests/test_formatting.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_formatting.py`:

```python
"""Tests for the canonical numeric formatter shared by query/comps and compare."""
from __future__ import annotations

import pytest

from edgarpack.query.formatting import format_number


class TestScaleAndPrecision:
    def test_small_currency_gets_two_decimals(self) -> None:
        assert format_number(3.62, "USD") == "$3.62"

    def test_small_eur_gets_two_decimals(self) -> None:
        assert format_number(42.5, "EUR") == "€42.50"

    def test_billions_one_decimal(self) -> None:
        assert format_number(5_900_000_000, "USD") == "$5.9B"

    def test_millions_integer_strips_trailing_zero(self) -> None:
        assert format_number(474_000_000, "count") == "474M"

    def test_millions_fractional_keeps_one_decimal(self) -> None:
        assert format_number(474_300_000, "count") == "474.3M"

    def test_thousands(self) -> None:
        assert format_number(12_500, "USD") == "$12.5K"

    def test_below_thousand_no_scale(self) -> None:
        assert format_number(532, "USD") == "$532"

    def test_zero_currency(self) -> None:
        assert format_number(0, "USD") == "$0"

    def test_none_value(self) -> None:
        assert format_number(None, "USD") == "N/A"


class TestNegatives:
    def test_negative_currency_uses_parens(self) -> None:
        assert format_number(-532_000_000, "USD") == "($532M)"

    def test_negative_small_currency_uses_parens(self) -> None:
        assert format_number(-0.43, "USD") == "($0.43)"

    def test_negative_percent_uses_parens(self) -> None:
        assert format_number(-0.6, "pure") == "(60.0%)"

    def test_negative_count_keeps_minus(self) -> None:
        assert format_number(-500, "count") == "-500"


class TestUnits:
    def test_pure_is_percent_one_decimal(self) -> None:
        assert format_number(0.125, "pure") == "12.5%"

    def test_usd_per_share(self) -> None:
        assert format_number(3.62, "USD/shares") == "$3.62"

    def test_unknown_three_letter_treated_as_currency(self) -> None:
        assert format_number(1_000_000_000, "CHF") == "CHF 1.0B"

    def test_shares_unit(self) -> None:
        assert format_number(2_500_000_000, "shares") == "2.5B"

    def test_headcount_unit(self) -> None:
        assert format_number(12_345, "headcount") == "12.3K"


class TestSymbolTable:
    def test_currency_symbols_exposed(self) -> None:
        from edgarpack.query.formatting import _CURRENCY_SYMBOLS
        assert _CURRENCY_SYMBOLS["USD"] == "$"
        assert _CURRENCY_SYMBOLS["EUR"] == "€"
        assert _CURRENCY_SYMBOLS["GBP"] == "£"
        assert _CURRENCY_SYMBOLS["JPY"] == "¥"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_formatting.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'edgarpack.query.formatting'`.

- [ ] **Step 3: Implement the formatter**

Create `edgarpack/query/formatting.py`:

```python
"""Canonical numeric formatter used by query.comps and compare.

Single source of truth for scale (B/M/K), precision, and finance-style
negative parentheses across every output surface that renders values to
users.
"""
from __future__ import annotations

_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "HKD": "HK$",
    "CNY": "¥",
}

_COUNT_UNITS = frozenset({"count", "shares", "headcount"})


def _scale_value(abs_val: float) -> tuple[float, str, int]:
    """Return (scaled_value, suffix, decimals) for a magnitude pick.

    Small-value bump: abs_val < 100 returns (abs_val, "", 2).
    abs_val in [100, 1000) returns (abs_val, "", 0).
    Otherwise scales at 1K/1M/1B with 1 decimal.
    """
    if abs_val < 100:
        return (abs_val, "", 2)
    if abs_val < 1_000:
        return (abs_val, "", 0)
    if abs_val < 1_000_000:
        return (abs_val / 1_000, "K", 1)
    if abs_val < 1_000_000_000:
        return (abs_val / 1_000_000, "M", 1)
    return (abs_val / 1_000_000_000, "B", 1)


def _render_number(abs_val: float, decimals: int, suffix: str) -> str:
    """Render a positive magnitude with decimals, stripping a lone trailing .0."""
    if decimals == 0:
        return f"{abs_val:,.0f}{suffix}"
    text = f"{abs_val:,.{decimals}f}"
    if decimals == 1 and text.endswith(".0"):
        text = text[:-2]
    return f"{text}{suffix}"


def format_number(value: float | None, unit: str) -> str:
    """Canonical formatter for numeric values with unit-aware scale and precision.

    Rules:
      - None -> "N/A".
      - unit == "pure" -> percent with 1 decimal; negatives in parens.
      - unit == "USD/shares" -> "$X.XX" with 2 decimals; negatives in parens.
      - unit in {"count", "shares", "headcount"} -> scale with 1 decimal
        (trailing .0 stripped), negatives keep minus sign.
      - unit in _CURRENCY_SYMBOLS or any 3-letter alpha code -> scale with
        1 decimal (small-value bump to 2 decimals when abs<100), negatives
        in parens. Symbol prefixed (or code + space for unknown codes).
      - unknown unit -> plain comma thousands with 2 decimals.
    """
    if value is None:
        return "N/A"

    if unit == "pure":
        pct = value * 100.0
        rendered = f"{abs(pct):.1f}%"
        return f"({rendered})" if value < 0 else rendered

    if unit == "USD/shares":
        rendered = f"${abs(value):,.2f}"
        return f"({rendered})" if value < 0 else rendered

    if unit in _COUNT_UNITS:
        abs_val = abs(value)
        scaled, suffix, decimals = _scale_value(abs_val)
        rendered = _render_number(scaled, decimals, suffix)
        return f"-{rendered}" if value < 0 else rendered

    is_currency = unit in _CURRENCY_SYMBOLS or (len(unit) == 3 and unit.isalpha())
    if is_currency:
        symbol = _CURRENCY_SYMBOLS.get(unit)
        prefix = symbol if symbol is not None else f"{unit} "
        abs_val = abs(value)
        scaled, suffix, decimals = _scale_value(abs_val)
        rendered = f"{prefix}{_render_number(scaled, decimals, suffix)}"
        return f"({rendered})" if value < 0 else rendered

    return f"{value:,.2f}"


__all__ = ["format_number", "_CURRENCY_SYMBOLS"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_formatting.py -v`
Expected: All 18 tests PASS.

- [ ] **Step 5: Lint check**

Run: `.venv/bin/ruff check edgarpack/query/formatting.py tests/test_formatting.py && .venv/bin/ruff format --check edgarpack/query/formatting.py tests/test_formatting.py`
Expected: Clean.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/query/formatting.py tests/test_formatting.py
git commit -m "feat(query): add canonical format_number primitive with finance negatives

Magnitude-scaled (B/M/K) formatter with small-value precision bump
and parentheses for negative currency/percent values. Shared surface
for query.comps and compare to delegate to."
```

---

## Task 2: Route query/comps through format_number

**Files:**
- Modify: `edgarpack/query/comps.py:336-341, 691-732`

- [ ] **Step 1: Write a failing test for the new behavior**

Append to `tests/test_comps.py`, class `TestCurrencyFormatting`:

```python
    def test_arpu_renders_with_two_decimals(self) -> None:
        from datetime import date
        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=3.62,
            unit="USD",
            metric="average_revenue_per_user",
            concept="Average Revenue Per User",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="0001564408-26-000013",
            cik="0001564408",
            company="Snap Inc",
        )
        assert _format_value(cited) == "$3.62"

    def test_count_unit_renders_474m(self) -> None:
        from datetime import date
        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=474_000_000,
            unit="count",
            metric="daily_active_users",
            concept="Daily Active Users",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="0001564408-26-000013",
            cik="0001564408",
            company="Snap Inc",
        )
        assert _format_value(cited) == "474M"

    def test_negative_currency_uses_parens(self) -> None:
        from datetime import date
        from edgarpack.query.comps import _format_value

        cited = CitedValue(
            value=-532_000_000,
            unit="USD",
            metric="operating_income",
            concept="OperatingIncomeLoss",
            period_end=date(2025, 12, 31),
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed=date(2026, 2, 5),
            accession="0001564408-26-000013",
            cik="0001564408",
            company="Snap Inc",
        )
        assert _format_value(cited) == "($532M)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_comps.py::TestCurrencyFormatting -v`
Expected: Three new tests FAIL; existing `test_eur_formatting`, `test_gbp_formatting`, `test_unknown_currency_uses_prefix` should still PASS.

- [ ] **Step 3: Delete `_format_currency` and collapse `_format_value` in comps.py**

In `edgarpack/query/comps.py`:

Replace the existing `_CURRENCY_SYMBOLS` block (line 336–341) with:

```python
from .formatting import _CURRENCY_SYMBOLS, format_number  # noqa: F401  (kept for legacy importers)
```

Place that import at the top of the file with the other imports (remove the inline dict at line 336 entirely).

Replace lines 691–732 (both `_format_currency` and `_format_value`) with:

```python
def _format_value(cited: CitedValue) -> str:
    """Format a CitedValue for human display."""
    if cited.value is None:
        return "N/A"
    return format_number(cited.value, cited.unit or "pure")
```

- [ ] **Step 4: Run the comps tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_comps.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run the broader query test suite**

Run: `.venv/bin/python -m pytest tests/test_comps.py tests/test_financials.py tests/test_cli_query_currency.py -v`
Expected: All PASS. Investigate and fix any that break on the new negative/count formatting.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check edgarpack/query/comps.py && .venv/bin/ruff format --check edgarpack/query/comps.py`
Expected: Clean.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/query/comps.py tests/test_comps.py
git commit -m "refactor(comps): route _format_value through format_number

Deletes _format_currency and the unit-branch fall-through. Fixes
ARPU precision (\$3.62 not \$4), count rendering (474M not
474,000,000.00), and negative currency (\$532M not -\$532M)."
```

---

## Task 3: Route compare.py through format_number

**Files:**
- Modify: `edgarpack/compare.py:222-258`

- [ ] **Step 1: Write a failing test**

Append to `tests/test_compare.py` (create the file if it doesn't have a test class; place in an existing class otherwise):

```python
class TestCompareFormatting:
    def test_abbrev_usd_large(self) -> None:
        from edgarpack.compare import _format_value
        v = {"value": 5_900_000_000, "currency": "USD", "usd_value": 5_900_000_000}
        assert _format_value(v) == "$5.9B"

    def test_abbrev_usd_negative_parens(self) -> None:
        from edgarpack.compare import _format_value
        v = {"value": -532_000_000, "currency": "USD", "usd_value": -532_000_000}
        assert _format_value(v) == "($532M)"

    def test_native_and_usd(self) -> None:
        from edgarpack.compare import _format_value
        v = {"value": 28_262_000_000, "currency": "EUR", "usd_value": 30_000_000_000}
        assert _format_value(v) == "$30.0B (native: €28.3B)"
```

- [ ] **Step 2: Run to verify the tests fail**

Run: `.venv/bin/python -m pytest tests/test_compare.py -v -k TestCompareFormatting`
Expected: FAIL (native test fails on formatting; negative parens fail).

- [ ] **Step 3: Replace `_abbrev_usd` and the numeric tail of `_format_value`**

In `edgarpack/compare.py`, delete `_abbrev_usd` (lines 222–233). Update `_format_value` (lines 236–258) to:

```python
def _format_value(v: dict[str, Any] | None) -> str:
    if v is None or v.get("value") is None:
        return "n/a"
    if "growth" in (v or {}):
        pct = v["growth"] * 100
        return f"{pct:+.0f}%" if abs(pct) >= 10 else f"{pct:+.1f}%"
    if "ratio" in (v or {}):
        return format_number(v["ratio"], "pure")
    if "per_employee_usd" in (v or {}):
        return format_number(float(v["per_employee_usd"]), "USD")
    if "headcount" in (v or {}):
        return format_number(float(v["headcount"]), "headcount")
    val = v["value"]
    cur = v.get("currency", "")
    usd = v.get("usd_value")
    if usd is not None and cur != "USD":
        return f"{format_number(float(usd), 'USD')} (native: {format_number(float(val), cur)})"
    if usd is not None:
        return format_number(float(usd), "USD")
    if cur:
        return format_number(float(val), cur)
    return format_number(float(val), "")
```

Add at top of `edgarpack/compare.py` with the other imports:

```python
from .query.formatting import format_number
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_compare.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check edgarpack/compare.py && .venv/bin/ruff format --check edgarpack/compare.py`
Expected: Clean.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/compare.py tests/test_compare.py
git commit -m "refactor(compare): route _format_value through format_number

Deletes _abbrev_usd, shares one source of truth with query.comps for
scale, precision, and finance negatives."
```

---

## Task 4: Period-aware lookup_company_kpi

**Files:**
- Modify: `edgarpack/query/kpi_discover.py:518-564`
- Create: `tests/test_kpi_discover_periods.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_kpi_discover_periods.py`:

```python
"""Period resolution for discovered-KPI lookup (lfy-N, mrq-N, annual:N, quarterly:N, ltm)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from edgarpack.query.kpi_discover import lookup_company_kpi
from edgarpack.query.learned_registry import CompanyKpiRow, LearnedRegistry


@pytest.fixture
def seeded_registry() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "learned.db"
        reg = LearnedRegistry(db_path=db)
        # 6 annual rows FY2020-FY2025 + 3 quarterly rows for FY2025 Q1-Q3.
        cik = "0001564408"
        annual_years = [2020, 2021, 2022, 2023, 2024, 2025]
        for yr in annual_years:
            reg.company_kpi_upsert(
                CompanyKpiRow(
                    cik=cik,
                    accession=f"000-{yr}-ANN",
                    slug="daily_active_users",
                    display_name="Daily Active Users",
                    aliases=[],
                    unit="count",
                    magnitude=None,
                    value=float((yr - 2019) * 50_000_000),
                    period_end=f"{yr}-12-31",
                    fiscal_year=yr,
                    fiscal_period="FY",
                    form_type="10-K",
                    definition=None,
                    section_id=None,
                    chunk_id=None,
                    source_substring=None,
                    confidence=None,
                    extracted_at=f"{yr + 1}-02-05T00:00:00",
                )
            )
        for q in (1, 2, 3):
            reg.company_kpi_upsert(
                CompanyKpiRow(
                    cik=cik,
                    accession=f"000-2025-Q{q}",
                    slug="daily_active_users",
                    display_name="Daily Active Users",
                    aliases=[],
                    unit="count",
                    magnitude=None,
                    value=float(400_000_000 + q * 10_000_000),
                    period_end=f"2025-{3 * q:02d}-31",
                    fiscal_year=2025,
                    fiscal_period=f"Q{q}",
                    form_type="10-Q",
                    definition=None,
                    section_id=None,
                    chunk_id=None,
                    source_substring=None,
                    confidence=None,
                    extracted_at=f"2025-{3 * q + 1:02d}-05T00:00:00",
                )
            )
        reg.close()
        yield db


class TestScalarPeriods:
    def test_lfy_returns_latest_annual(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="lfy", registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_year == 2025
        assert row.form_type == "10-K"

    def test_lfy_back_three(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="lfy-3", registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_year == 2022

    def test_lfy_out_of_bounds_returns_none(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="lfy-10", registry_path=seeded_registry,
        )
        assert row is None

    def test_mrq(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="mrq", registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_period == "Q3"

    def test_mrq_back_one(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="mrq-1", registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
        assert row.fiscal_period == "Q2"

    def test_mrp_returns_newest_of_any_form(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="mrp", registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)


class TestLtmDegrades:
    def test_ltm_returns_same_as_lfy(self, seeded_registry: Path) -> None:
        lfy_row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="lfy", registry_path=seeded_registry,
        )
        ltm_row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="ltm", registry_path=seeded_registry,
        )
        assert lfy_row is not None and ltm_row is not None
        assert not isinstance(lfy_row, list) and not isinstance(ltm_row, list)
        assert ltm_row.fiscal_year == lfy_row.fiscal_year

    def test_ltm_back_two_matches_lfy_back_two(self, seeded_registry: Path) -> None:
        lfy_row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="lfy-2", registry_path=seeded_registry,
        )
        ltm_row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="ltm-2", registry_path=seeded_registry,
        )
        assert lfy_row is not None and ltm_row is not None
        assert not isinstance(lfy_row, list) and not isinstance(ltm_row, list)
        assert ltm_row.fiscal_year == lfy_row.fiscal_year


class TestSeries:
    def test_annual_six(self, seeded_registry: Path) -> None:
        rows = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="annual:6", registry_path=seeded_registry,
        )
        assert isinstance(rows, list)
        assert len(rows) == 6
        assert [r.fiscal_year for r in rows] == [2025, 2024, 2023, 2022, 2021, 2020]

    def test_annual_partial_coverage(self, seeded_registry: Path) -> None:
        rows = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="annual:10", registry_path=seeded_registry,
        )
        assert isinstance(rows, list)
        assert len(rows) == 6  # Caller handles the partial-coverage diagnostic.

    def test_quarterly_two(self, seeded_registry: Path) -> None:
        rows = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="quarterly:2", registry_path=seeded_registry,
        )
        assert isinstance(rows, list)
        assert [r.fiscal_period for r in rows] == ["Q3", "Q2"]


class TestMisses:
    def test_unknown_slug_returns_none(self, seeded_registry: Path) -> None:
        assert lookup_company_kpi(
            cik="0001564408", slug="nonexistent",
            period="lfy", registry_path=seeded_registry,
        ) is None

    def test_unknown_period_falls_back_to_newest(self, seeded_registry: Path) -> None:
        row = lookup_company_kpi(
            cik="0001564408", slug="daily_active_users",
            period="weirdo", registry_path=seeded_registry,
        )
        assert row is not None and not isinstance(row, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover_periods.py -v`
Expected: Most FAIL (lfy-3 returns latest, annual:6 returns single row, etc.).

- [ ] **Step 3: Rewrite `lookup_company_kpi`**

In `edgarpack/query/kpi_discover.py`, replace the body of `lookup_company_kpi` (lines 518–564) with:

```python
def lookup_company_kpi(
    *,
    cik: str,
    slug: str,
    period: str,
    registry_path: Path | None = None,
    pack_registry: PackRegistry | None = None,
) -> CompanyKpiRow | list[CompanyKpiRow] | None:
    """Resolve (cik, slug, period) to one or more persisted CompanyKpiRows.

    Understands: lfy, lfy-N, mrq, mrq-N, mrp, ltm, ltm-N, annual:N,
    quarterly:N. Scalars return a single row (or None). Series
    (annual:N, quarterly:N) return a list ordered newest-first.

    LTM degrades to LFY (and ltm-N to lfy-N). Callers emit the
    diagnostic so the user sees why LTM wasn't computed.
    """
    own_registry = False
    if pack_registry is None:
        pack_registry = PackRegistry()
        own_registry = True
    learned_reg = LearnedRegistry(db_path=registry_path)
    try:
        rows = learned_reg.company_kpi_list(cik=cik, slug=slug)
        if not rows:
            return None

        def _is_annual(r: CompanyKpiRow) -> bool:
            ft = (r.form_type or "").upper()
            return ft.startswith("10-K") or ft in {"20-F", "40-F"}

        def _is_quarterly(r: CompanyKpiRow) -> bool:
            return (r.form_type or "").upper().startswith("10-Q")

        def _sort_key(r: CompanyKpiRow) -> tuple:
            return (r.fiscal_year or 0, r.period_end or "", r.extracted_at)

        p = period.strip().lower()

        # LTM degrades to LFY before we branch on anything else.
        if p == "ltm":
            p = "lfy"
        elif p.startswith("ltm-"):
            p = "lfy-" + p.split("-", 1)[1]

        if p == "lfy":
            annual = sorted((r for r in rows if _is_annual(r)), key=_sort_key, reverse=True)
            return annual[0] if annual else None

        if p.startswith("lfy-"):
            try:
                n = int(p.split("-", 1)[1])
            except ValueError:
                return None
            annual = sorted((r for r in rows if _is_annual(r)), key=_sort_key, reverse=True)
            return annual[n] if 0 <= n < len(annual) else None

        if p == "mrq":
            q = sorted((r for r in rows if _is_quarterly(r)), key=_sort_key, reverse=True)
            return q[0] if q else None

        if p.startswith("mrq-"):
            try:
                n = int(p.split("-", 1)[1])
            except ValueError:
                return None
            q = sorted((r for r in rows if _is_quarterly(r)), key=_sort_key, reverse=True)
            return q[n] if 0 <= n < len(q) else None

        if p == "mrp":
            all_rows = sorted(rows, key=_sort_key, reverse=True)
            return all_rows[0] if all_rows else None

        if p.startswith("annual:"):
            try:
                n = int(p.split(":", 1)[1])
            except ValueError:
                return None
            annual = sorted((r for r in rows if _is_annual(r)), key=_sort_key, reverse=True)
            return annual[:n] if annual else None

        if p.startswith("quarterly:"):
            try:
                n = int(p.split(":", 1)[1])
            except ValueError:
                return None
            q = sorted((r for r in rows if _is_quarterly(r)), key=_sort_key, reverse=True)
            return q[:n] if q else None

        # Unknown selector: preserve prior most-recent-fallback behavior.
        all_rows = sorted(rows, key=_sort_key, reverse=True)
        return all_rows[0] if all_rows else None
    finally:
        learned_reg.close()
        if own_registry:
            pack_registry.close()
```

Update the docstring at the top of the function to match the new signature. Also update the return-type annotation.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover_periods.py -v`
Expected: All 14 tests PASS.

- [ ] **Step 5: Run existing kpi_discover tests for regression**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover.py -v`
Expected: All PASS. The prior `lookup_company_kpi` contract (lfy → latest 10-K, mrq → latest 10-Q) is preserved as a subset of the new behavior.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check edgarpack/query/kpi_discover.py tests/test_kpi_discover_periods.py && .venv/bin/ruff format --check edgarpack/query/kpi_discover.py tests/test_kpi_discover_periods.py`
Expected: Clean.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/query/kpi_discover.py tests/test_kpi_discover_periods.py
git commit -m "feat(kpi): period-aware lookup_company_kpi

Understands lfy-N, mrq-N, annual:N, quarterly:N; LTM degrades to
LFY. Series selectors return a list ordered newest-first. Unblocks
multi-period queries for discovered KPIs like DAU and ARPU."
```

---

## Task 5: Consume period-aware lookup in financials()

**Files:**
- Modify: `edgarpack/query/financials.py:372-396`
- Modify: `tests/test_financials.py` (add new test class)

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_financials.py` a new class (import additions as needed):

```python
class TestDiscoveredKpiMultiPeriod:
    """financials() returns distinct CitedValues per period for discovered KPIs."""

    @pytest.fixture
    def seeded_dau(self, tmp_path, monkeypatch):
        from pathlib import Path
        from edgarpack.query.learned_registry import CompanyKpiRow, LearnedRegistry
        db = tmp_path / "learned.db"
        reg = LearnedRegistry(db_path=db)
        for yr in (2020, 2021, 2022, 2023, 2024, 2025):
            reg.company_kpi_upsert(
                CompanyKpiRow(
                    cik="0001564408",
                    accession=f"000-{yr}-ANN",
                    slug="daily_active_users",
                    display_name="Daily Active Users",
                    aliases=[],
                    unit="count",
                    magnitude=None,
                    value=float((yr - 2019) * 50_000_000),
                    period_end=f"{yr}-12-31",
                    fiscal_year=yr,
                    fiscal_period="FY",
                    form_type="10-K",
                    definition=None,
                    section_id=None,
                    chunk_id=None,
                    source_substring=None,
                    confidence=None,
                    extracted_at=f"{yr + 1}-02-05T00:00:00",
                )
            )
        reg.close()
        monkeypatch.setattr(
            "edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH", db
        )
        return db

    @pytest.mark.asyncio
    async def test_lfy_vs_lfy_back_three_differ(self, seeded_dau, monkeypatch):
        # Stub identity resolution + facts fetch so only the discovered path runs.
        from edgarpack.query import financials as fin_mod
        async def _fake_company_info(_):
            return ("0001564408", "Snap Inc")
        async def _fake_facts(*a, **k):
            return {"facts": {}}
        monkeypatch.setattr(fin_mod, "resolve_company_identity", _fake_company_info)
        monkeypatch.setattr(fin_mod, "fetch_company_facts", _fake_facts)

        from edgarpack.query.financials import financials
        lfy_result = await financials("SNAP", metrics="daily_active_users", period="lfy")
        lfy3_result = await financials("SNAP", metrics="daily_active_users", period="lfy-3")
        lfy_cited = lfy_result.metrics["daily_active_users"]
        lfy3_cited = lfy3_result.metrics["daily_active_users"]
        assert lfy_cited is not None and lfy3_cited is not None
        assert lfy_cited.fiscal_year == 2025
        assert lfy3_cited.fiscal_year == 2022

    @pytest.mark.asyncio
    async def test_annual_six_returns_list(self, seeded_dau, monkeypatch):
        from edgarpack.query import financials as fin_mod
        async def _fake_company_info(_):
            return ("0001564408", "Snap Inc")
        async def _fake_facts(*a, **k):
            return {"facts": {}}
        monkeypatch.setattr(fin_mod, "resolve_company_identity", _fake_company_info)
        monkeypatch.setattr(fin_mod, "fetch_company_facts", _fake_facts)

        from edgarpack.query.financials import financials
        result = await financials("SNAP", metrics="daily_active_users", period="annual:6")
        values = result.metrics["daily_active_users"]
        assert isinstance(values, list)
        assert len(values) == 6
        assert [v.fiscal_year for v in values] == [2025, 2024, 2023, 2022, 2021, 2020]

    @pytest.mark.asyncio
    async def test_ltm_emits_degraded_diagnostic(self, seeded_dau, monkeypatch):
        from edgarpack.query import financials as fin_mod
        async def _fake_company_info(_):
            return ("0001564408", "Snap Inc")
        async def _fake_facts(*a, **k):
            return {"facts": {}}
        monkeypatch.setattr(fin_mod, "resolve_company_identity", _fake_company_info)
        monkeypatch.setattr(fin_mod, "fetch_company_facts", _fake_facts)

        from edgarpack.query.financials import financials
        result = await financials("SNAP", metrics="daily_active_users", period="ltm")
        diag_kinds = [d.kind for d in result.diagnostics]
        assert "ltm_degraded" in diag_kinds
        cited = result.metrics["daily_active_users"]
        assert cited is not None and cited.fiscal_year == 2025

    @pytest.mark.asyncio
    async def test_annual_partial_coverage_diagnostic(self, seeded_dau, monkeypatch):
        from edgarpack.query import financials as fin_mod
        async def _fake_company_info(_):
            return ("0001564408", "Snap Inc")
        async def _fake_facts(*a, **k):
            return {"facts": {}}
        monkeypatch.setattr(fin_mod, "resolve_company_identity", _fake_company_info)
        monkeypatch.setattr(fin_mod, "fetch_company_facts", _fake_facts)

        from edgarpack.query.financials import financials
        result = await financials("SNAP", metrics="daily_active_users", period="annual:10")
        diag_kinds = [d.kind for d in result.diagnostics]
        assert "partial_coverage" in diag_kinds
        values = result.metrics["daily_active_users"]
        assert isinstance(values, list)
        assert len(values) == 6
```

Note: adjust the monkeypatch targets (`resolve_company_identity`, `fetch_company_facts`) to match the actual symbol names in `edgarpack.query.financials` by checking the module's imports. If the real names differ, substitute them.

- [ ] **Step 2: Run to verify the tests fail**

Run: `.venv/bin/python -m pytest tests/test_financials.py::TestDiscoveredKpiMultiPeriod -v`
Expected: FAIL (single value replicated or diagnostics absent).

- [ ] **Step 3: Update the discovered-KPI branch in financials()**

In `edgarpack/query/financials.py`, replace lines 372–396 with:

```python
            # Company-specific discovered KPI (populated by `edgarpack which`).
            # Resolves against the cached company_kpis rows; no LLM call.
            looked_up = lookup_company_kpi(cik=cik, slug=metric, period=period)
            if looked_up is None:
                result_metrics[metric] = None
                diagnostics_list.append(
                    Diagnostic(
                        metric=metric,
                        kind="layer_b_unresolved",
                        message=(
                            f"Discovered KPI '{metric}' has no cached row for "
                            f"period '{period}'. Run `edgarpack which {cik}` to "
                            f"refresh discovery, or check the period against "
                            f"what's available."
                        ),
                    )
                )
            elif isinstance(looked_up, list):
                cited_list = [
                    _cited_from_company_kpi_row(row, cik=cik, company=company_name)
                    for row in looked_up
                ]
                result_metrics[metric] = cited_list if cited_list else None
                # Partial-coverage diagnostic for series selectors.
                if period.startswith("annual:") or period.startswith("quarterly:"):
                    try:
                        requested = int(period.split(":", 1)[1])
                    except ValueError:
                        requested = 0
                    if 0 < len(cited_list) < requested:
                        earliest = cited_list[-1].fiscal_year
                        diagnostics_list.append(
                            Diagnostic(
                                metric=metric,
                                kind="partial_coverage",
                                message=(
                                    f"Only {len(cited_list)} of {requested} "
                                    f"requested periods available for "
                                    f"'{metric}'; earliest is FY{earliest}."
                                ),
                            )
                        )
            else:
                result_metrics[metric] = _cited_from_company_kpi_row(
                    looked_up, cik=cik, company=company_name
                )

            # LTM-degraded diagnostic (shared across scalar and series paths
            # above so user sees why LTM wasn't computed).
            p_lower = period.strip().lower()
            if p_lower == "ltm" or p_lower.startswith("ltm-"):
                diagnostics_list.append(
                    Diagnostic(
                        metric=metric,
                        kind="ltm_degraded",
                        message=(
                            f"LTM not computed for discovered KPI "
                            f"'{metric}'; showing latest annual (10-K) "
                            f"value instead."
                        ),
                    )
                )
            continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_financials.py::TestDiscoveredKpiMultiPeriod -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Run the full financials test suite**

Run: `.venv/bin/python -m pytest tests/test_financials.py -v`
Expected: All PASS.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check edgarpack/query/financials.py tests/test_financials.py && .venv/bin/ruff format --check edgarpack/query/financials.py tests/test_financials.py`
Expected: Clean.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/query/financials.py tests/test_financials.py
git commit -m "feat(financials): consume period-aware discovered-KPI lookup

Distinct CitedValues per period; emits ltm_degraded diagnostic when
LTM is requested on a discovered KPI, and partial_coverage when
annual:N exceeds cached years."
```

---

## Task 6: Fix the FY FY double-prefix

**Files:**
- Modify: `edgarpack/query/models.py:138-140`
- Modify: `tests/test_financials.py` (or a small new `tests/test_models.py` if absent)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_financials.py` (or create `tests/test_models.py`):

```python
class TestFiscalLabel:
    def test_annual_drops_fy_double_prefix(self) -> None:
        from datetime import date
        from edgarpack.query.models import CitedValue
        cv = CitedValue(
            value=1, unit="USD", metric="m", concept="c",
            period_end=date(2025, 12, 31), fiscal_year=2025,
            fiscal_period="FY", form_type="10-K",
            filed=date(2026, 2, 5), accession="a", cik="c", company="co",
        )
        assert cv.fiscal_label == "FY2025"

    def test_quarter_label_unchanged(self) -> None:
        from datetime import date
        from edgarpack.query.models import CitedValue
        cv = CitedValue(
            value=1, unit="USD", metric="m", concept="c",
            period_end=date(2025, 6, 30), fiscal_year=2025,
            fiscal_period="Q2", form_type="10-Q",
            filed=date(2025, 8, 6), accession="a", cik="c", company="co",
        )
        assert cv.fiscal_label == "Q2 FY2025"
```

- [ ] **Step 2: Run to verify the FY test fails**

Run: `.venv/bin/python -m pytest tests/test_financials.py::TestFiscalLabel -v`
Expected: `test_annual_drops_fy_double_prefix` FAILS (returns `"FY FY2025"`).

- [ ] **Step 3: Fix `fiscal_label`**

In `edgarpack/query/models.py` replace lines 137–140 with:

```python
    @property
    def fiscal_label(self) -> str:
        """Human-readable fiscal label (e.g. 'FY2025', 'Q2 FY2025')."""
        if self.fiscal_period in ("FY", ""):
            return f"FY{self.fiscal_year}"
        return f"{self.fiscal_period} FY{self.fiscal_year}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_financials.py::TestFiscalLabel tests/test_comps.py tests/test_cli_query_currency.py -v`
Expected: All PASS. If CLI snapshot tests assert on `"FY FY2025"`, update them to `"FY2025"`.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/models.py tests/test_financials.py
git commit -m "fix(models): drop FY FY double-prefix in fiscal_label

When fiscal_period == 'FY' or empty, render 'FY2025' not
'FY FY2025'. Quarter labels unchanged."
```

---

## Task 7: CLI vocabulary sweep (accn → filing, discovered badge)

**Files:**
- Modify: `edgarpack/cli.py:1237-1240, 1307-1316`
- Modify: `tests/test_cli_which_ux.py` or new `tests/test_cli_output_vocab.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_output_vocab.py`:

```python
"""CLI output vocabulary: filing (not accn), [discovered] (not raw taxonomy tag)."""
from __future__ import annotations

from unittest.mock import MagicMock


class TestCitationRendererVocab:
    def test_citation_uses_filing_not_accn(self) -> None:
        from edgarpack.cli import _render_citation_record
        record = {
            "form_type": "10-K",
            "fiscal_label": "FY2025",
            "period": "2025-12-31",
            "accession": "0001564408-26-000013",
            "filed": "2026-02-05",
        }
        lines = _render_citation_record(
            "C1", record, show_links="off", width=120,
        )
        joined = "\n".join(lines)
        assert "filing 0001564408-26-000013" in joined
        assert "accn" not in joined


class TestSourceBadgeVocab:
    def test_discovered_kpi_collapses_to_discovered_badge(self) -> None:
        from edgarpack.cli import _source_badge_for
        cited = MagicMock()
        cited.source = "learned:kpi-discovered"
        cited.warnings = []
        assert _source_badge_for(cited) == " [discovered]"

    def test_other_learned_sources_keep_compact_form(self) -> None:
        from edgarpack.cli import _source_badge_for
        cited = MagicMock()
        cited.source = "learned:llm"
        cited.warnings = []
        assert _source_badge_for(cited) == " [learned:llm ✓]"

    def test_hardcoded_returns_empty(self) -> None:
        from edgarpack.cli import _source_badge_for
        cited = MagicMock()
        cited.source = "hardcoded"
        cited.warnings = []
        assert _source_badge_for(cited) == ""
```

The second test group references `_source_badge_for` - the refactor promotes the current inner `_source_badge` closure to a module-level function so it can be imported and tested.

- [ ] **Step 2: Run to verify the tests fail**

Run: `.venv/bin/python -m pytest tests/test_cli_output_vocab.py -v`
Expected: FAIL (ImportError on `_render_citation_record` depending on current name, and on `_source_badge_for` which doesn't exist yet; `accn` still appears in citation text).

- [ ] **Step 3: Rename accn → filing in citation renderer**

In `edgarpack/cli.py`, update the citation summary around line 1237:

```python
    summary = (
        f"[{citation_id}] {form_type} {fiscal_label} | period {period} | "
        f"filing {accession} | filed {filed}"
    )
```

Confirm the enclosing function is named `_render_citation_record`. If it's named differently (e.g., `_render_citation`), adjust the test's import accordingly.

- [ ] **Step 4: Promote `_source_badge` to module-level with `[discovered]` collapse**

In `edgarpack/cli.py`, extract the closure at lines 1307–1316 to a module-level helper above the function that uses it:

```python
def _source_badge_for(v: Any) -> str:
    """Render the source indicator that follows a metric's formatted value.

    - 'hardcoded' -> empty (no badge).
    - 'learned:kpi-discovered' -> ' [discovered]'.
    - 'learned:kpi-*' -> ' [discovered]' (all pattern-based discovered KPIs
      collapse to the same human label; the specific taxonomy stays on the
      CitedValue for programmatic callers).
    - anything else 'learned:*' -> ' [<source> ✓]' (self-heal badge).
    - warning contains 'unverified' -> ✓ becomes ⚠.
    """
    src = getattr(v, "source", "hardcoded")
    if src == "hardcoded":
        return ""
    if src.startswith("learned:kpi-"):
        return " [discovered]"
    mark = "✓"
    for w in getattr(v, "warnings", []):
        if "unverified" in w.lower():
            mark = "⚠"
            break
    return f" [{src} {mark}]"
```

Replace the inner `_source_badge(v)` call at line 1360 with `_source_badge_for(raw_value)`, and delete the nested definitions at lines 1304–1316.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_output_vocab.py tests/test_cli_which_ux.py -v`
Expected: All PASS. If any existing CLI snapshot test matches `accn ` or `[learned:kpi-discovered ✓]`, update its expectation.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check edgarpack/cli.py tests/test_cli_output_vocab.py && .venv/bin/ruff format --check edgarpack/cli.py tests/test_cli_output_vocab.py`
Expected: Clean.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/cli.py tests/test_cli_output_vocab.py
git commit -m "ux(cli): human-readable citation and discovered-KPI labels

'accn <X>' becomes 'filing <X>'. '[learned:kpi-discovered ✓]'
collapses to '[discovered]'. Internal CitedValue.source token
unchanged; only the display layer changes."
```

---

## Task 8: Preserve user's ticker in Reproduce line

**Files:**
- Modify: `edgarpack/query/comps.py:674-680` (add `display_token` kwarg, use in permalink)
- Modify: `edgarpack/cli.py` (pass the original arg)
- Modify: `tests/test_comps.py` (new permalink test)

- [ ] **Step 1: Find the `comps()` signature and CLI call site**

Run: `grep -n "def comps" edgarpack/query/comps.py`
Run: `grep -n "comps(" edgarpack/cli.py`

Note the exact signature of `comps()` and the single-company query wrapper (if any) that feeds the Reproduce permalink.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_comps.py`:

```python
class TestPermalinkDisplayToken:
    def test_permalink_uses_display_token_over_cik(self) -> None:
        """When display_token is set (e.g., user typed 'SNAP'), permalink
        uses it instead of the resolved CIK."""
        from edgarpack.query.comps import _build_permalink
        link = _build_permalink(
            cik="0001564408",
            company="Snap Inc",
            metrics=["revenue"],
            periods=["lfy"],
            display_token="snap",
        )
        assert link == "edgarpack query snap revenue --period lfy"

    def test_permalink_falls_back_to_cik_without_token(self) -> None:
        from edgarpack.query.comps import _build_permalink
        link = _build_permalink(
            cik="0001564408",
            company="Snap Inc",
            metrics=["revenue"],
            periods=["lfy"],
            display_token=None,
        )
        assert link == "edgarpack query 0001564408 revenue --period lfy"
```

- [ ] **Step 3: Run to verify the tests fail**

Run: `.venv/bin/python -m pytest tests/test_comps.py::TestPermalinkDisplayToken -v`
Expected: FAIL (`_build_permalink` does not exist yet).

- [ ] **Step 4: Extract `_build_permalink` and thread `display_token` through**

In `edgarpack/query/comps.py` near the existing permalink construction at line 678, add:

```python
def _build_permalink(
    *,
    cik: str | None,
    company: str | None,
    metrics: list[str],
    periods: list[str],
    display_token: str | None,
) -> str:
    """Reproduce line builder. Prefers user's input token over the CIK."""
    subject = display_token or cik or company or ""
    return (
        f"edgarpack query {subject} {','.join(metrics)} "
        f"--period {','.join(periods)}"
    )
```

Add `display_token: str | None = None` as a kwarg to the `comps()` function signature (wherever `comps` is defined in `comps.py`). Replace the existing inline permalink at line 678 with:

```python
        "permalink": _build_permalink(
            cik=cik,
            company=company,
            metrics=metrics,
            periods=periods,
            display_token=display_token,
        ),
```

- [ ] **Step 5: Thread through `financials()` and CLI**

Check callers of `comps()`:

Run: `grep -n "comps(" edgarpack/`

For each caller, add a `display_token=<user-supplied token>` kwarg. In `edgarpack/cli.py`, the ticker/CIK positional arg is already captured - pass it verbatim (don't lowercase-normalize for display).

If a single-metric query path builds its own permalink (not via `comps()`), check `cli.py:1274` area and any `_build_permalink`-equivalent; apply the same fallback.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_comps.py::TestPermalinkDisplayToken tests/test_comps.py tests/test_cli_query_currency.py -v`
Expected: All PASS.

- [ ] **Step 7: Lint**

Run: `.venv/bin/ruff check edgarpack/query/comps.py edgarpack/cli.py tests/test_comps.py && .venv/bin/ruff format --check edgarpack/query/comps.py edgarpack/cli.py tests/test_comps.py`
Expected: Clean.

- [ ] **Step 8: Commit**

```bash
git add edgarpack/query/comps.py edgarpack/cli.py tests/test_comps.py
git commit -m "ux(comps): preserve user's input token in Reproduce line

Adds display_token kwarg to comps() and extracts _build_permalink.
CLI passes the original positional arg; if user typed 'snap', the
Reproduce line reads 'edgarpack query snap ...' instead of
'edgarpack query 0001564408 ...'."
```

---

## Task 9: Full-suite regression + end-to-end SNAP verification

**Files:**
- Run existing suite.

- [ ] **Step 1: Run the full pytest suite**

Run: `.venv/bin/python -m pytest tests/ -x -v`
Expected: All PASS. Fix any failures before proceeding.

- [ ] **Step 2: Run ruff across the project**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: Clean.

- [ ] **Step 3: Run the actual SNAP CLI session from the user's test**

If a local registry with SNAP discovered rows exists, run:

```bash
.venv/bin/edgarpack query snap average_revenue_per_user,revenue,daily_active_users,operating_income,net_income --period annual:6
```

Expected output characteristics:
- ARPU renders `$3.44`, `$4.06`, etc. (two decimals, no `$4` collapse).
- DAU renders `265M`, `319M`, ..., `474M` (scaled, no trailing `.00`).
- Operating Income negatives render `($532M)`, `($787M)` (parens).
- Each fiscal-year row has a distinct value (not the same one replicated).
- Citation lines read `filing 0001564408-...` (no `accn`).
- Fiscal labels read `FY2025` (no `FY FY2025`).
- Reproduce line reads `edgarpack query snap ...` (ticker, not CIK).
- Discovered-metric label includes `[discovered]` (not `[learned:kpi-discovered ✓]`).

If the end-to-end session cannot be run (no populated registry), skip this step and rely on the test suite.

- [ ] **Step 4: Commit final cleanup (if needed)**

```bash
git status
# If any test snapshot or expectation tweaks were missed:
git add -u
git commit -m "chore: test snapshot updates for output vocab and negative parens"
```

- [ ] **Step 5: Final lint + test gate**

Run: `.venv/bin/python -m pytest tests/ -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: Clean.

---

## Open Questions

None. Spec is fully resolved.

## Self-Review Notes

- **Spec coverage:** Every section of the spec maps to a task: formatting primitive (Task 1), comps + compare delegation (Tasks 2–3), period-aware lookup + financials consumer (Tasks 4–5), FY fix (Task 6), CLI vocab + badge (Task 7), permalink plumbing (Task 8), final regression (Task 9).
- **Placeholders:** None. Every step has concrete code or exact commands.
- **Type consistency:** `lookup_company_kpi` return type `CompanyKpiRow | list[CompanyKpiRow] | None` is consistent between Task 4 (definition) and Task 5 (consumer). `format_number(value, unit)` signature is consistent across Tasks 1, 2, and 3. `_build_permalink` kwargs match across Task 8 test and implementation.
- **Scope:** Four defects, one worktree, ships as nine atomic commits.
