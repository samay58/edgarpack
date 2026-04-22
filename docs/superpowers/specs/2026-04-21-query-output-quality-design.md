# Query Output Quality: Formatting, Discovered-KPI Periods, Finance Negatives, UX Vocabulary

**Date**: 2026-04-21
**Status**: Spec
**Scope**: Four user-facing defects observed in `edgarpack query snap ...` testing. Fix at the formatter and discovered-KPI resolver layers. No protocol or storage changes.

## Problem

Four defects observed in a real SNAP query session:

1. **Dumb unit formatting.** `_format_value` in `edgarpack/query/comps.py:706` falls through to `f"{val:,.2f}"` for `unit="count"`, so DAU renders as `474,000,000.00`. `_format_currency` at line 691 uses `{val:,.0f}` for values below $1K, so ARPU `3.62` collapses to `$4` in the multi-period table.
2. **Discovered-KPI period resolution is broken for multi-period queries.** `lookup_company_kpi` at `edgarpack/query/kpi_discover.py:518` returns a single row based only on a form-type filter: `lfy` gets the latest 10-K, `mrq` gets the latest 10-Q, everything else falls through to "most recent row overall." When `financials()` loops `lfy, lfy-1, lfy-2, lfy-3, lfy-4` (or is called once with `annual:6`), every call resolves to the same row. The SNAP output shows `$4` and `474,000,000.00` replicated across every column even though `edgarpack which SNAP` already persisted FY2020 through FY2026 rows.
3. **Negatives render with a minus sign.** `$-532M` and `-60%` instead of finance convention `($532M)` and `(60%)`.
4. **Raw internals leak into CLI output.** `accn 0001564408-26-000013`, `[learned:kpi-discovered ✓]`, `FY FY2025` (double "FY"), `Reproduce: edgarpack query 0001564408 …` (CIK even when user typed `snap`).

## Non-goals

- LTM semantics inference for discovered KPIs (degrade to LFY with a note instead).
- Any change to how KPI discovery writes rows to `company_kpis`.
- Renaming the internal `source="learned:kpi-discovered"` token on `CitedValue`. Only the display surface changes. `tests/test_kpi_discover.py:764` asserts on this string and keeps passing.
- Dedup of the per-metric citation block in single-metric output. Deferred.
- Changing the `unit` column header in `edgarpack which`. Deferred.

## Decisions

| Question | Choice |
|---|---|
| Formatting heuristic | Magnitude-based scale + small-value precision bump when `abs(value) < 100` for currency/ratio units. |
| LTM on discovered KPIs | Degrade to LFY (and `ltm-N` to `lfy-N`), attach a diagnostic. |
| Lookup API shape | Extend `lookup_company_kpi` to return `CompanyKpiRow | list[CompanyKpiRow] | None`, matching how `select_period` already branches scalar vs list. |
| Finance negatives scope | Parens for currency and percent only. Counts and other units keep the minus sign. |
| Formatter home | New module `edgarpack/query/formatting.py` with a shared primitive. Both `comps._format_value` and `compare._format_value` delegate to it. |
| Missing years in `annual:N` | Render what exists, emit a single diagnostic naming the earliest available year. |
| UX scope | Rename `accn` → `filing`, drop `[learned:kpi-discovered ✓]` inline badge (replace with `[discovered]` next to metric label), fix `FY FY2025` double-prefix, preserve user's ticker in `Reproduce` line. |

## Design

### 1. Formatting primitive

New file `edgarpack/query/formatting.py`. Public surface:

```python
def format_number(
    value: float | None,
    unit: str,
    *,
    parens_for_negative: bool | None = None,
) -> str:
    """Canonical numeric formatter used by query/comps and compare.

    Rules:
      - value is None -> "N/A"
      - unit == "pure" -> percent with 1 decimal; negatives use parens.
      - unit == "USD/shares" -> "$X.XX" with 2 decimals; negatives use parens.
      - unit in currency symbols (USD, EUR, GBP, JPY, HKD, CNY, ...) -> symbol + scale.
        Scale: abs>=1B -> "1.2B"; abs>=1M -> "1M"; abs>=1K -> "1K"; abs<1K -> raw.
        Precision bump: if abs<100, render 2 decimals instead of scaling.
        Negatives use parens when parens_for_negative is True (default for currency).
      - unit in {"count", "shares", "headcount"} -> scale with 0 decimals,
        negatives keep minus sign (counts don't go negative in practice).
      - unit is 3-letter alpha code not in symbol map -> treat as currency with
        code prefix ("CHF 1.2B").
      - unknown unit -> raw number with comma thousands separator, 2 decimals.
    """
```

Internal helper:

```python
def _scale_value(abs_val: float) -> tuple[float, str, int]:
    """Return (scaled_value, suffix, decimals) for a magnitude pick.

    Small-value bump: abs_val < 100 -> (abs_val, "", 2).
    Otherwise: B at 1e9, M at 1e6, K at 1e3, with 1 decimal (trailing .0 stripped).
    abs_val < 1000 -> (abs_val, "", 0).
    """
```

The 1-decimal output strips a trailing `.0`: `474_000_000` renders `474M`, `474_300_000` renders `474.3M`. Reuses one formatter code path for both integer-valued and fractional scales.

**Currency symbol table** moves from `comps.py:_CURRENCY_SYMBOLS` into `formatting.py` as `_CURRENCY_SYMBOLS`. `comps.py` imports from there. No behavior change; just the source of truth shifts.

**Finance negatives**: `_format_with_parens(rendered: str) -> str` wraps the numeric portion. Currency example: `val=-532_000_000, unit="USD"` → scale to `"$532M"`, then wrap → `"($532M)"`. Percent: `val=-0.6, unit="pure"` → render `"60.0%"`, wrap → `"(60.0%)"`.

### 2. Delegation from existing formatters

`edgarpack/query/comps.py:_format_value(cited: CitedValue) -> str` becomes a thin wrapper:

```python
def _format_value(cited: CitedValue) -> str:
    if cited.value is None:
        return "N/A"
    return format_number(cited.value, cited.unit or "pure")
```

The existing unit-branch block (lines 706–732) deletes. `_format_currency` (lines 691–703) deletes.

`edgarpack/compare.py:_format_value(v: dict | None) -> str` keeps its dict-specific branches (growth, ratio, per_employee_usd, headcount, native-vs-USD). The numeric abbreviation call site:

```python
# Before:
return _abbrev_usd(usd)
# After:
return format_number(usd, "USD")
```

`_abbrev_usd` at `compare.py:220–233` deletes. Native-with-USD line becomes:

```python
return f"{format_number(usd, 'USD')} (native: {format_number(float(val), cur)})"
```

### 3. Period-aware discovered-KPI lookup

Replace the body of `edgarpack/query/kpi_discover.py:lookup_company_kpi`. New signature:

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

    Understands: lfy, lfy-N, mrq, mrq-N, mrp, ltm, ltm-N, annual:N, quarterly:N.
    Scalars return a single row (or None). Series (annual:N, quarterly:N) return
    a list ordered newest-first.

    LTM degrades: ltm -> lfy, ltm-N -> lfy-N. Callers handle the diagnostic.
    """
```

Implementation sketch:

```python
rows = learned_reg.company_kpi_list(cik=cik, slug=slug)
if not rows:
    return None

p = period.strip().lower()

def _is_annual(r: CompanyKpiRow) -> bool:
    return (r.form_type or "").upper().startswith("10-K") or \
           (r.form_type or "").upper() in {"20-F", "40-F"}

def _is_quarterly(r: CompanyKpiRow) -> bool:
    return (r.form_type or "").upper().startswith("10-Q")

def _sort_key(r: CompanyKpiRow) -> tuple:
    return (r.fiscal_year or 0, r.period_end or "", r.extracted_at)

# LTM degrades before branching.
if p == "ltm":
    p = "lfy"
elif p.startswith("ltm-"):
    p = "lfy-" + p.split("-", 1)[1]

if p == "lfy":
    annual = sorted([r for r in rows if _is_annual(r)], key=_sort_key, reverse=True)
    return annual[0] if annual else None

if p.startswith("lfy-"):
    n = int(p.split("-", 1)[1])
    annual = sorted([r for r in rows if _is_annual(r)], key=_sort_key, reverse=True)
    return annual[n] if 0 <= n < len(annual) else None

if p == "mrq":
    q = sorted([r for r in rows if _is_quarterly(r)], key=_sort_key, reverse=True)
    return q[0] if q else None

if p.startswith("mrq-"):
    n = int(p.split("-", 1)[1])
    q = sorted([r for r in rows if _is_quarterly(r)], key=_sort_key, reverse=True)
    return q[n] if 0 <= n < len(q) else None

if p == "mrp":
    all_rows = sorted(rows, key=_sort_key, reverse=True)
    return all_rows[0] if all_rows else None

if p.startswith("annual:"):
    n = int(p.split(":", 1)[1])
    annual = sorted([r for r in rows if _is_annual(r)], key=_sort_key, reverse=True)
    return annual[:n] if annual else None

if p.startswith("quarterly:"):
    n = int(p.split(":", 1)[1])
    q = sorted([r for r in rows if _is_quarterly(r)], key=_sort_key, reverse=True)
    return q[:n] if q else None

# Unknown: fall back to most recent, preserving prior behavior.
all_rows = sorted(rows, key=_sort_key, reverse=True)
return all_rows[0] if all_rows else None
```

### 4. Consume the period-aware lookup in financials()

`edgarpack/query/financials.py` lines 372–396. The discovered-KPI branch becomes:

```python
# Discovered KPI path.
looked_up = lookup_company_kpi(cik=cik, slug=metric, period=period)
if looked_up is None:
    result_metrics[metric] = None
    diagnostics_list.append(
        Diagnostic(
            metric=metric,
            kind="layer_b_unresolved",
            message=(
                f"Discovered KPI '{metric}' has no cached row for "
                f"period '{period}'. Run `edgarpack which {cik}` to refresh, "
                f"or check the period against what's available."
            ),
        )
    )
    continue

if isinstance(looked_up, list):
    cited_list = [
        _cited_from_company_kpi_row(row, cik=cik, company=company_name)
        for row in looked_up
    ]
    result_metrics[metric] = cited_list if cited_list else None

    # Missing-year diagnostic for series selectors.
    if period.startswith("annual:") or period.startswith("quarterly:"):
        requested = int(period.split(":", 1)[1])
        if len(cited_list) < requested:
            earliest = cited_list[-1].fiscal_year if cited_list else "unknown"
            diagnostics_list.append(
                Diagnostic(
                    metric=metric,
                    kind="partial_coverage",
                    message=(
                        f"Only {len(cited_list)} of {requested} requested "
                        f"periods available for '{metric}'; earliest filing "
                        f"is FY{earliest}."
                    ),
                )
            )
else:
    result_metrics[metric] = _cited_from_company_kpi_row(
        looked_up, cik=cik, company=company_name
    )

# LTM degradation diagnostic.
p_lower = period.strip().lower()
if p_lower == "ltm" or p_lower.startswith("ltm-"):
    diagnostics_list.append(
        Diagnostic(
            metric=metric,
            kind="ltm_degraded",
            message=(
                f"LTM not computed for discovered KPI '{metric}'; "
                f"showing latest annual (10-K) value instead."
            ),
        )
    )
continue
```

`Diagnostic` already exists in `edgarpack/query/models.py`. `kind` is a free-text string per the existing pattern (`"layer_b_unresolved"`), so `"partial_coverage"` and `"ltm_degraded"` need no schema change.

### 5. UX vocabulary sweep

**Citation rendering.** `edgarpack/cli.py` lines around 1326–1361 render citation blocks. Replace the `accn 0001564408-26-000013` substring with `filing 0001564408-26-000013`. One string change; the underlying `accession` field name stays internal. Keep the `link(filing_url): ...` line as-is.

**Discovered marker.** Drop the inline `[learned:kpi-discovered ✓]` badge. Replace with a compact `[discovered]` suffix next to the metric label when `CitedValue.source` starts with `"learned:"`. Single render point.

**Fiscal label.** Grep for `f"FY {cited.fiscal_year}"` and similar. Remove the literal `"FY "` prefix when `fiscal_period` starts with `"FY"`. Target the single formatter (likely `_format_fiscal_label` or equivalent in `cli.py` / `comps.py`); grep confirms the current output prints `FY FY2025` via `f"{fiscal_period} FY{fiscal_year}"` pattern.

**Reproduce line.** `edgarpack/query/comps.py:678` builds the permalink from `cik or company`. Add an optional `display_token: str | None = None` parameter to `comps()` (and its call sites in `cli.py` + `query/financials.py`). When `display_token` is set (ticker the user typed), the permalink uses it; otherwise falls back to the current `cik or company` behavior. CLI passes the original positional arg verbatim. Adds one string through one function. No permalink semantics change for API callers that don't pass it.

## Test plan

New file `tests/test_formatting.py`:

- `format_number(3.62, "USD")` → `"$3.62"`.
- `format_number(5_900_000_000, "USD")` → `"$5.9B"`.
- `format_number(474_000_000, "count")` → `"474M"`.
- `format_number(474_300_000, "count")` → `"474.3M"`.
- `format_number(-532_000_000, "USD")` → `"($532M)"`.
- `format_number(-0.6, "pure")` → `"(60.0%)"`.
- `format_number(-500, "count")` → `"-500"` (counts keep minus).
- `format_number(None, "USD")` → `"N/A"`.
- `format_number(1_000_000_000, "CHF")` → `"CHF 1.0B"` (parens still wrap negatives).
- Small-value bump: `format_number(42.5, "USD")` → `"$42.50"`; `format_number(42.5, "EUR")` → `"€42.50"`.
- Zero: `format_number(0, "USD")` → `"$0"`.

Existing `TestCurrencyFormatting` tests in `tests/test_comps.py:274` stay green; they use substring assertions (`"B"`, `"€"`, `"CHF"`, `"£"` in output).

New file `tests/test_kpi_discover_periods.py` (or extend existing `test_kpi_discover.py`):

- Seed SNAP-shaped rows: 6 annual (FY2020–FY2025), 3 quarterly (Q1–Q3 FY2025).
- `lookup_company_kpi(..., period="lfy")` → row with `fiscal_year=2025`.
- `lookup_company_kpi(..., period="lfy-3")` → row with `fiscal_year=2022`.
- `lookup_company_kpi(..., period="lfy-10")` → `None` (out of bounds).
- `lookup_company_kpi(..., period="annual:6")` → list of 6 rows, newest first.
- `lookup_company_kpi(..., period="annual:10")` → list of 6 rows (partial coverage, caller handles diagnostic).
- `lookup_company_kpi(..., period="mrq-1")` → Q2 row.
- `lookup_company_kpi(..., period="ltm")` → same row as `lfy`.
- `lookup_company_kpi(..., period="ltm-2")` → same row as `lfy-2`.
- Unknown slug → `None`.

New test in `tests/test_financials.py` (or equivalent): with a seeded discovered KPI across 6 fiscal years, call `financials(...)` once per `lfy, lfy-1, ..., lfy-5`. Each call returns a different `CitedValue` with the corresponding `fiscal_year`. `annual:6` returns a list of 6 distinct `CitedValue`s.

LTM-on-discovered diagnostic test: seed a discovered KPI, request `ltm`, assert result is the LFY row AND a `Diagnostic` with `kind="ltm_degraded"` is in the result.

CLI integration test in `tests/test_cli_query_currency.py` (or sibling): invoke `edgarpack query SNAP ...` against a fixture-backed registry; assert `$-` does not appear in output, `($` does; assert `accn ` is absent and `filing ` is present; assert `FY FY` is absent.

## Rollout

1. Land `formatting.py` + test, keeping `comps._format_value` / `compare._format_value` call-throughs behind the same contracts.
2. Land `lookup_company_kpi` period extension + test.
3. Land `financials()` consumption + diagnostics + test.
4. Land CLI vocabulary sweep (`accn`, `[discovered]`, `FY FY`, permalink plumbing) + snapshot updates.

Each step lands independently; steps 1–3 gate on tests, step 4 is mechanical once 1 is in.

## Risk

- **Snapshot/string-match tests** in `tests/test_cli_*.py` may assert on `$-` or `accn`. Grep before editing; update expectations where present.
- **Permalink plumbing** adds a kwarg to `comps()`. Call sites: `cli.py:1268` area, any API route under `edgarpack/api/`. Grep all callers, default to `None` so non-CLI consumers are unchanged.
- **LTM degradation** changes the answer for any caller that today gets `None` for `ltm` on a discovered KPI. Behavioral change, not a regression: diagnostic makes it visible.

## Open questions

None. All decisions are resolved above.
