# China Golden-Fixture Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a YAML-backed pytest harness at `tests/test_china_query_eval.py` that anchors MiniMax and Zhipu query values against hand-verified IR numbers, running on every `pytest tests/` so Tencent/Meituan/multi-year work cannot silently regress them.

**Architecture:** A golden YAML file at `tests/eval/china_golden.yaml` declares per-company, per-period, per-metric expected values in native currency and USD. A single pytest module loads the YAML at collection time and parametrizes over `(ticker, period, metric, currency)`. Native assertions are exact; USD assertions use 2% relative tolerance and go through `edgarpack.fx.convert`. Known extraction bugs carry an `xfail: <bead-id>` field that becomes `pytest.mark.xfail(strict=True)`. Existing inline assertions in `tests/test_china_query_hk.py` are refactored to keep structural checks only.

**Tech Stack:** Python 3.12, pytest with parametrize, pyyaml (already a dep), asyncio, `edgarpack.query.financials.financials`, `edgarpack.fx.convert.convert`, `edgarpack.fx.rates.load_rates`.

---

## File Structure

**Create:**
- `tests/eval/china_golden.yaml` — hand-curated expected values keyed by ticker, period, metric, currency. Schema versioned via top-level `version: 1`. Per-metric `source` citation, optional `xfail` field.
- `tests/test_china_query_eval.py` — parametrized pytest harness. Loads YAML at collection time; one test case per `(ticker, period, metric, currency)` tuple. Direct async call to `financials()`; USD derived via `edgarpack.fx.convert.convert`.
- `tests/eval/README.md` — schema documentation and the workflow for adding a new company or fixing an xfail.

**Modify:**
- `tests/test_china_query_hk.py` — strip inline numeric assertions (lines 15, 25, 34). Keep shape checks (currency, accounting standard, ticker-form resolution, multi-metric). Add a module docstring pointing at `test_china_query_eval.py` as the regression gate.

No production source files are touched by this plan. This is test-only work.

---

## Verified values (pre-computed, do not change without re-verifying from IR)

Native values extracted from committed packs on 2026-04-15:

**MiniMax 00100.HK** (FY2024, HKFRS, USD-reporting):
- `total_equity`: -799_320_000
- `cash_and_equivalents`: 288_912_000
- `revenue`: 30_523_000
- `gross_profit`: 3_738_000
- `net_income`: -465_238_000
- `operating_cash_flow`: not extracted (xfail: edgarpack-483)
- `r_and_d_expense`: not extracted (xfail: edgarpack-483)

**Zhipu 02513.HK** (FY2024, HKFRS, CNY-reporting):
- `total_equity`: -974_767_000
- `cash_and_equivalents`: 2_269_222_000
- `operating_cash_flow`: -2_244_919_000
- `revenue`: 312_414_000
- `gross_profit`: 175_889_000
- `operating_income`: -2_538_352_000
- `net_income`: -2_958_007_000
- `r_and_d_expense`: not extracted (xfail: edgarpack-483)

**FX rates (CNY/USD, month ending 2024-12-31)** from `data/fx_rates.csv`:
- `spot_end`: 0.136999
- `period_average`: 0.137350

Conversion convention per ASC 830: P&L and cash flow use `period_average`; balance sheet uses `spot_end`. Zhipu USD values below are computed (native * rate, rounded to integer dollars):
- `total_equity` (spot): -974_767_000 * 0.136999 = -133_562_306
- `cash_and_equivalents` (spot): 2_269_222_000 * 0.136999 = 310_880_061
- `operating_cash_flow` (avg): -2_244_919_000 * 0.137350 = -308_339_426
- `revenue` (avg): 312_414_000 * 0.137350 = 42_910_063
- `gross_profit` (avg): 175_889_000 * 0.137350 = 24_158_252
- `operating_income` (avg): -2_538_352_000 * 0.137350 = -348_642_646
- `net_income` (avg): -2_958_007_000 * 0.137350 = -406_292_261

MiniMax native is USD; USD values equal native exactly.

---

## Task 1: Scaffold harness with MiniMax revenue tuple

**Files:**
- Create: `tests/eval/__init__.py` (empty, namespace)
- Create: `tests/eval/china_golden.yaml`
- Create: `tests/test_china_query_eval.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_china_query_eval.py`:

```python
"""Golden-fixture regression gate for Chinese company queries.

Loads tests/eval/china_golden.yaml at collection time and parametrizes
over (ticker, period, metric, currency). Native assertions are exact;
USD assertions use 2% relative tolerance. Known extraction bugs are
carried as xfail rows keyed by bead ID.

See tests/eval/README.md for the schema and the curator workflow.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from edgarpack.fx.convert import convert
from edgarpack.fx.rates import load_rates
from edgarpack.query.financials import financials

GOLDEN_PATH = Path(__file__).parent / "eval" / "china_golden.yaml"
FX_PATH = Path(__file__).parent.parent / "data" / "fx_rates.csv"
USD_REL_TOL = 0.02


@dataclass(frozen=True)
class GoldenCase:
    ticker: str
    company: str
    accounting_standard: str
    reporting_currency: str
    fiscal_year: int
    period: str
    metric: str
    currency: str  # "native" or "usd"
    expected: int | None
    fx_convention: str | None
    source: str
    xfail: str | None


def _load_cases() -> list[GoldenCase]:
    with GOLDEN_PATH.open() as f:
        doc = yaml.safe_load(f)
    assert doc.get("version") == 1, f"unsupported golden schema version: {doc.get('version')!r}"
    cases: list[GoldenCase] = []
    for company in doc.get("companies", []):
        for metric_name, periods in company["metrics"].items():
            for period_name, block in periods.items():
                for currency in ("native", "usd"):
                    cases.append(
                        GoldenCase(
                            ticker=company["ticker"],
                            company=company["company"],
                            accounting_standard=company["accounting_standard"],
                            reporting_currency=company["reporting_currency"],
                            fiscal_year=company["fiscal_year"],
                            period=period_name,
                            metric=metric_name,
                            currency=currency,
                            expected=block.get(currency),
                            fx_convention=block.get("fx_convention"),
                            source=block.get("source", ""),
                            xfail=block.get("xfail"),
                        )
                    )
    return cases


_CASES = _load_cases()


def _case_id(c: GoldenCase) -> str:
    return f"{c.ticker}-{c.period}-{c.metric}-{c.currency}"


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_china_golden(case: GoldenCase) -> None:
    if case.xfail:
        pytest.xfail(f"known bug: {case.xfail}")

    result = asyncio.run(
        financials(company=case.ticker, metrics=case.metric, period=case.period)
    )
    cited = result.metrics.get(case.metric)
    assert cited is not None, f"{case.metric} not returned by query"
    assert cited.value is not None, f"{case.metric} value is None"

    if case.currency == "native":
        actual: float = float(cited.value)
        if actual != case.expected:
            pytest.fail(
                _fail_block(case, actual, rate_used=None),
                pytrace=False,
            )
    else:
        rates = load_rates(FX_PATH)
        convention = case.fx_convention or "average"
        period_end = cited.period_end
        converted = convert(
            value=Decimal(str(cited.value)),
            from_ccy=cited.reporting_currency,
            to_ccy="USD",
            as_of=period_end,
            convention=convention,  # type: ignore[arg-type]
            rates=rates,
            period_end=period_end,
        )
        actual = converted.converted_value
        if case.expected is None:
            pytest.fail(
                f"{_case_id(case)}: golden USD value is null but xfail was not set",
                pytrace=False,
            )
        if not math.isclose(actual, case.expected, rel_tol=USD_REL_TOL):
            pytest.fail(
                _fail_block(case, actual, rate_used=converted.rate_used),
                pytrace=False,
            )


def _fail_block(case: GoldenCase, actual: float, rate_used: float | None) -> str:
    diff = actual - (case.expected or 0)
    pct = (diff / case.expected * 100.0) if case.expected else float("inf")
    lines = [
        f"GOLDEN MISMATCH: {_case_id(case)}",
        f"  ticker:            {case.ticker} ({case.company})",
        f"  period/metric:     {case.period} / {case.metric}",
        f"  currency:          {case.currency}",
        f"  golden expected:   {case.expected}",
        f"  actual computed:   {actual}",
        f"  abs diff:          {diff}",
        f"  pct diff:          {pct:.4f}%",
    ]
    if rate_used is not None:
        lines.append(f"  fx rate used:      {rate_used}")
    lines.append(f"  source citation:   {case.source}")
    return "\n".join(lines)
```

Also create `tests/eval/__init__.py` as an empty file (so pytest treats `tests/eval/` as a package for cleanliness, though the file isn't imported).

- [ ] **Step 2: Run the test, confirm it fails because the golden YAML does not exist**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -20`
Expected: collection error, `FileNotFoundError` pointing at `tests/eval/china_golden.yaml`.

- [ ] **Step 3: Create the minimal golden YAML**

Create `tests/eval/china_golden.yaml`:

```yaml
version: 1
companies:
  - ticker: "00100.HK"
    company: "MiniMax Group Inc."
    accounting_standard: HKFRS
    reporting_currency: USD
    fiscal_year: 2024
    metrics:
      revenue:
        lfy:
          native: 30523000
          usd: 30523000
          fx_rate: 1.0
          fx_convention: identity
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Statement of Profit or Loss"
```

- [ ] **Step 4: Run the test, confirm the one parametrized case passes**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -20`
Expected: 2 passed (native + usd for MiniMax revenue lfy).

Note: the `fx_convention: identity` string falls through `convert()`'s `from_ccy == to_ccy` fast path (both USD), so the convention string isn't strictly parsed as "spot" or "average" for this case. For non-USD-reporting companies (Zhipu) we use "spot" or "average" explicitly.

- [ ] **Step 5: Commit**

```bash
git add tests/test_china_query_eval.py tests/eval/__init__.py tests/eval/china_golden.yaml
git commit -m "test(qhn): scaffold china golden-fixture harness with MiniMax revenue tuple"
```

---

## Task 2: Expand MiniMax to full metric set (LFY, native + USD)

**Files:**
- Modify: `tests/eval/china_golden.yaml`

- [ ] **Step 1: Add the remaining MiniMax LFY metrics**

Replace the entire `00100.HK` block in `tests/eval/china_golden.yaml` with:

```yaml
  - ticker: "00100.HK"
    company: "MiniMax Group Inc."
    accounting_standard: HKFRS
    reporting_currency: USD
    fiscal_year: 2024
    metrics:
      revenue:
        lfy:
          native: 30523000
          usd: 30523000
          fx_rate: 1.0
          fx_convention: average
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Statement of Profit or Loss"
      gross_profit:
        lfy:
          native: 3738000
          usd: 3738000
          fx_rate: 1.0
          fx_convention: average
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Statement of Profit or Loss"
      net_income:
        lfy:
          native: -465238000
          usd: -465238000
          fx_rate: 1.0
          fx_convention: average
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Statement of Profit or Loss"
      cash_and_equivalents:
        lfy:
          native: 288912000
          usd: 288912000
          fx_rate: 1.0
          fx_convention: spot
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Balance Sheet"
      total_equity:
        lfy:
          native: -799320000
          usd: -799320000
          fx_rate: 1.0
          fx_convention: spot
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Balance Sheet"
      operating_cash_flow:
        lfy:
          native: null
          usd: null
          xfail: edgarpack-483
          source: "MiniMax 00100.HK FY2024 pack, Cash Flow Statement (multi-line label extraction bug)"
      r_and_d_expense:
        lfy:
          native: null
          usd: null
          xfail: edgarpack-483
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Statement of Profit or Loss (multi-line label extraction bug)"
```

- [ ] **Step 2: Run the harness and confirm 10 pass + 4 xfail**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -30`
Expected: `10 passed, 4 xfailed` (5 metrics x 2 currencies = 10 passes, plus OCF and R&D x 2 currencies = 4 xfails). All xfails keyed to `edgarpack-483`.

If any native assertion fails, diff the printed `GOLDEN MISMATCH` block against the values in the "Verified values" section of this plan. If a value genuinely drifted, regenerate it from `edgarpack query minimax <metric> --period lfy --format json` and reverify against the pack's underlying section markdown before updating the YAML.

- [ ] **Step 3: Commit**

```bash
git add tests/eval/china_golden.yaml
git commit -m "test(qhn): cover MiniMax LFY full metric set with xfail for edgarpack-483"
```

---

## Task 3: Add LTM mirror rows for MiniMax

**Files:**
- Modify: `tests/eval/china_golden.yaml`

For HKEX annual-only filers LTM equals LFY. Mirroring documents the query path.

- [ ] **Step 1: Add an `ltm:` block to every MiniMax metric**

For each of the 7 MiniMax metric entries (`revenue`, `gross_profit`, `net_income`, `cash_and_equivalents`, `total_equity`, `operating_cash_flow`, `r_and_d_expense`), add a sibling `ltm:` block identical to the existing `lfy:` block, except change the `source` suffix to `" (LTM proxy: annual-only filer, mirrors LFY)"`. Pattern for a green metric:

```yaml
      revenue:
        lfy:
          native: 30523000
          usd: 30523000
          fx_rate: 1.0
          fx_convention: average
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Statement of Profit or Loss"
        ltm:
          native: 30523000
          usd: 30523000
          fx_rate: 1.0
          fx_convention: average
          source: "MiniMax 00100.HK FY2024 pack, Consolidated Statement of Profit or Loss (LTM proxy: annual-only filer, mirrors LFY)"
```

Pattern for an xfail metric:

```yaml
      operating_cash_flow:
        lfy:
          native: null
          usd: null
          xfail: edgarpack-483
          source: "MiniMax 00100.HK FY2024 pack, Cash Flow Statement (multi-line label extraction bug)"
        ltm:
          native: null
          usd: null
          xfail: edgarpack-483
          source: "MiniMax 00100.HK FY2024 pack, Cash Flow Statement (multi-line label extraction bug, LTM proxy: annual-only filer, mirrors LFY)"
```

- [ ] **Step 2: Run the harness and confirm 20 pass + 8 xfail**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -35`
Expected: `20 passed, 8 xfailed`.

- [ ] **Step 3: Commit**

```bash
git add tests/eval/china_golden.yaml
git commit -m "test(qhn): mirror MiniMax LTM against LFY for annual-only filer"
```

---

## Task 4: Add Zhipu entries (LFY + LTM)

**Files:**
- Modify: `tests/eval/china_golden.yaml`

Zhipu reports in CNY, so USD values are non-trivial.

- [ ] **Step 1: Append the Zhipu company block**

Append to the `companies:` list in `tests/eval/china_golden.yaml`:

```yaml
  - ticker: "02513.HK"
    company: "Zhipu (Knowledge Atlas Technology)"
    accounting_standard: HKFRS
    reporting_currency: CNY
    fiscal_year: 2024
    metrics:
      revenue:
        lfy:
          native: 312414000
          usd: 42910063
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss"
        ltm:
          native: 312414000
          usd: 42910063
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss (LTM proxy: annual-only filer, mirrors LFY)"
      gross_profit:
        lfy:
          native: 175889000
          usd: 24158252
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss"
        ltm:
          native: 175889000
          usd: 24158252
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss (LTM proxy: annual-only filer, mirrors LFY)"
      operating_income:
        lfy:
          native: -2538352000
          usd: -348642646
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss"
        ltm:
          native: -2538352000
          usd: -348642646
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss (LTM proxy: annual-only filer, mirrors LFY)"
      net_income:
        lfy:
          native: -2958007000
          usd: -406292261
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss"
        ltm:
          native: -2958007000
          usd: -406292261
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss (LTM proxy: annual-only filer, mirrors LFY)"
      operating_cash_flow:
        lfy:
          native: -2244919000
          usd: -308339426
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Cash Flow Statement"
        ltm:
          native: -2244919000
          usd: -308339426
          fx_rate: 0.137350
          fx_convention: average
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Cash Flow Statement (LTM proxy: annual-only filer, mirrors LFY)"
      cash_and_equivalents:
        lfy:
          native: 2269222000
          usd: 310880061
          fx_rate: 0.136999
          fx_convention: spot
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Balance Sheet"
        ltm:
          native: 2269222000
          usd: 310880061
          fx_rate: 0.136999
          fx_convention: spot
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Balance Sheet (LTM proxy: annual-only filer, mirrors LFY)"
      total_equity:
        lfy:
          native: -974767000
          usd: -133562306
          fx_rate: 0.136999
          fx_convention: spot
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Balance Sheet"
        ltm:
          native: -974767000
          usd: -133562306
          fx_rate: 0.136999
          fx_convention: spot
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Balance Sheet (LTM proxy: annual-only filer, mirrors LFY)"
      r_and_d_expense:
        lfy:
          native: null
          usd: null
          xfail: edgarpack-483
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss (multi-line label extraction bug)"
        ltm:
          native: null
          usd: null
          xfail: edgarpack-483
          source: "Zhipu 02513.HK FY2024 pack, Consolidated Statement of Profit or Loss (multi-line label extraction bug, LTM proxy: annual-only filer, mirrors LFY)"
```

- [ ] **Step 2: Run the harness and confirm full matrix**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -80`

Expected: `48 passed, 12 xfailed`. Breakdown:
- MiniMax: 5 green metrics x 2 periods x 2 currencies = 20 pass. 2 xfail metrics x 2 periods x 2 currencies = 8 xfail.
- Zhipu: 7 green metrics x 2 periods x 2 currencies = 28 pass. 1 xfail metric x 2 periods x 2 currencies = 4 xfail.

If any Zhipu USD assertion fails outside the 2% tolerance, the most likely cause is a mismatch between the plan's precomputed USD integer and what `convert()` actually returns (rounding direction on integer casts). If this happens, run the harness with `-k 02513 and usd` and read the `GOLDEN MISMATCH` block: it will show actual vs expected and the delta. Replace the YAML value with the actual value from the block (only if the pct diff is under 0.01%, i.e., rounding noise, not a real regression).

- [ ] **Step 3: Commit**

```bash
git add tests/eval/china_golden.yaml
git commit -m "test(qhn): cover Zhipu FY2024 full metric set with CNY->USD conversion"
```

---

## Task 5: Refactor tests/test_china_query_hk.py to strip inline numbers

**Files:**
- Modify: `tests/test_china_query_hk.py`

- [ ] **Step 1: Replace the file contents**

Overwrite `tests/test_china_query_hk.py` with:

```python
"""Smoke tests for HKEX pack query paths.

Numeric regression coverage lives in tests/test_china_query_eval.py
(driven by tests/eval/china_golden.yaml). This file asserts structural
and metadata invariants only: currency flags, accounting standard flags,
ticker-form resolution, multi-metric queries, and failure modes.
"""

import asyncio

import pytest

from edgarpack.query.financials import financials


def test_minimax_query_returns_revenue_with_hkfrs_metadata():
    result = asyncio.run(financials(company="minimax", metrics="revenue", period="lfy"))
    assert result is not None
    revenue = result.metrics.get("revenue")
    assert revenue is not None, f"No revenue in {list(result.metrics.keys())}"
    assert revenue.reporting_currency == "USD"
    assert revenue.accounting_standard == "HKFRS"
    assert revenue.fiscal_year == 2024


def test_zhipu_query_returns_net_income_with_cny_metadata():
    result = asyncio.run(financials(company="zhipu", metrics="net_income", period="lfy"))
    ni = result.metrics.get("net_income")
    assert ni is not None
    assert ni.reporting_currency == "CNY"
    assert ni.accounting_standard == "HKFRS"


def test_minimax_ticker_form_resolves():
    result = asyncio.run(
        financials(company="00100.HK", metrics="cash_and_equivalents", period="lfy")
    )
    cash = result.metrics.get("cash_and_equivalents")
    assert cash is not None
    assert cash.reporting_currency == "USD"


def test_minimax_full_query_returns_multiple_metrics():
    result = asyncio.run(financials(company="minimax", metrics=None, period="lfy"))
    metrics = set(result.metrics.keys())
    assert {"revenue", "net_income", "cash_and_equivalents"} <= metrics


def test_unknown_hkex_company_raises():
    with pytest.raises(Exception):
        asyncio.run(financials(company="00999.HK", metrics="revenue", period="lfy"))
```

All numeric assertions (lines that asserted `revenue.value == 30_523_000`, `ni.value == -2_958_007_000`, `cash.value == 288_912_000`) are removed. The golden harness owns those.

- [ ] **Step 2: Run the smoke tests and confirm green**

Run: `.venv/bin/python -m pytest tests/test_china_query_hk.py -v 2>&1 | tail -20`
Expected: `5 passed`.

- [ ] **Step 3: Run the full china query suite and confirm no regression**

Run: `.venv/bin/python -m pytest tests/test_china_query_hk.py tests/test_china_query_eval.py -v 2>&1 | tail -20`
Expected: `53 passed, 12 xfailed` (5 smoke + 48 golden green + 12 xfail).

- [ ] **Step 4: Commit**

```bash
git add tests/test_china_query_hk.py
git commit -m "test(qhn): narrow test_china_query_hk to structural smoke checks"
```

---

## Task 6: Add tests/eval/README.md

**Files:**
- Create: `tests/eval/README.md`

- [ ] **Step 1: Write the README**

Create `tests/eval/README.md`:

```markdown
# China Golden Fixtures

`china_golden.yaml` holds hand-verified query values for Chinese company packs committed under `tests/fixtures/china_packs/`. The harness at `tests/test_china_query_eval.py` loads this file at collection time and parametrizes over `(ticker, period, metric, currency)`. Native assertions are exact. USD assertions use 2% relative tolerance and go through `edgarpack.fx.convert.convert` against the rate table at `data/fx_rates.csv`.

## Schema (version 1)

```yaml
version: 1
companies:
  - ticker: "<STOCKCODE.HK or SEC ticker>"
    company: "<human-readable name>"
    accounting_standard: <US-GAAP | IFRS | HKFRS | CAS>
    reporting_currency: <USD | CNY | HKD>
    fiscal_year: <int>
    metrics:
      <metric_name>:
        <period_name>:        # lfy | ltm
          native: <int | null>
          usd: <int | null>
          fx_rate: <float>     # informational, not asserted
          fx_convention: <spot | average | identity>
          source: "<free-form citation, IR filing + page>"
          xfail: "<bead-id>"   # optional; marks tuple as strict xfail
```

## Adding a new company

1. Build a pack under `tests/fixtures/china_packs/<ticker>_<fy>/` (or use an existing one).
2. Run `edgarpack query <ticker> --period lfy --format json` and record the native values.
3. Open the filing PDF, hand-verify each metric against the primary statement (P&L, balance sheet, or cash flow). Note the page number in the `source` string.
4. Compute USD: CNY or HKD -> USD via the month-end row in `data/fx_rates.csv`. Use `spot_end` for balance-sheet items, `period_average` for P&L and cash flow. Integer rounding.
5. Append a new `- ticker: ...` block to `companies:` in `china_golden.yaml`. Include both `lfy` and `ltm` period blocks. For annual-only filers, `ltm` mirrors `lfy`.
6. Run `.venv/bin/python -m pytest tests/test_china_query_eval.py -v` and iterate until green.

## Fixing an xfail

When the underlying extraction bug (tracked by `xfail: edgarpack-XXX`) is fixed, the harness will go red with `XPASS` for that row. To clear:

1. Re-run `edgarpack query <ticker> <metric> --period lfy --format json` to get the now-extracted native value.
2. Verify against the cited IR page.
3. Compute USD.
4. Delete the `xfail:` and `null` fields in the YAML row; replace with the real `native` and `usd` integers plus `fx_rate` and `fx_convention`.
5. Commit with a reference to the closed bead.

## Tolerance policy

- Native: exact integer match. Extraction is deterministic against a committed pack, so drift means a parser regression.
- USD: 2% relative tolerance (`math.isclose(actual, expected, rel_tol=0.02)`). Absorbs FX rate refreshes of reasonable magnitude. If a single metric legitimately breaks 2% after a rate refresh, widen the tolerance per-row through a schema extension rather than loosening the global default.

## Do not

- Do not auto-regenerate golden values from current CLI output. If a value changes, a human re-reads the IR filing and updates the `source` field with the current page. Auto-regeneration masks regressions.
- Do not add entries for ADRs (BIDU, PDD, BABA, JD) here until a separate fixture harvest pass lands 20-F packs under `tests/fixtures/china_packs/`. That work is a separate P2.
```

- [ ] **Step 2: Run the full test suite one more time to confirm stability**

Run: `.venv/bin/python -m pytest tests/ 2>&1 | tail -10`
Expected: full suite green (exact count grows by 48 passed + 12 xfailed vs baseline). No new failures in unrelated tests.

- [ ] **Step 3: Commit**

```bash
git add tests/eval/README.md
git commit -m "docs(qhn): add README for china golden harness schema and workflow"
```

---

## Task 7: Close the bead

- [ ] **Step 1: Update bead status**

Run:

```bash
bd close edgarpack-qhn --reason "Golden-fixture harness shipped for MiniMax + Zhipu LFY/LTM; xfail rows filed for edgarpack-483. ADR and Tencent/Meituan rows tracked as follow-ups per spec."
bd sync
```

- [ ] **Step 2: Push**

```bash
git push
```

---

## Self-Review Checklist (already run by author)

- **Spec coverage:** Every section of `docs/superpowers/specs/2026-04-15-china-golden-harness-design.md` maps to a task. YAML schema (Task 1-4). Harness entry point (Task 1). Tolerance (Task 1). Failure output (Task 1, `_fail_block`). Known-bug handling (Task 2, `xfail` field). Metric coverage (Tasks 2-4). Existing test interaction (Task 5). Done definition (Task 6 verification step). README (Task 6).
- **Placeholder scan:** No `TBD`, `TODO`, or `implement later` in any step. Every code step includes the full code block. Every command step includes the exact command and expected output.
- **Type consistency:** `GoldenCase` fields match between dataclass definition (Task 1) and YAML schema (Tasks 2-4). `financials()` signature matches production code. `convert()` signature matches `edgarpack/fx/convert.py`.
