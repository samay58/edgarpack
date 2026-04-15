# China Lens Extraction Quality + Multi-Year YoY Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship extraction-quality fixes and multi-year YoY derivations for the China Lens vertical slice, landing as three ordered commits.

**Architecture:** Three thin slices in order. Slice 1 is a localized regex preprocessor in the HKEX extractor. Slice 2 adds a new canonical metric (`headcount`) with HKEX + SEC extraction paths. Slice 3 generalizes the HK extractor to emit one fact per disclosed fiscal year, extends `MetricMeta.components` with per-component period offsets so `_compute_derived` can express `x[fy] / x[fy-1]`, and wires four derivations.

**Tech Stack:** Python 3.14, pytest, ruff. Core files: `edgarpack/hk/extract.py`, `edgarpack/query/{concepts,metric_map,financials,periods}.py`, `edgarpack/compare.py`, `tests/fixtures/china_packs/`, `tests/eval/china_golden.yaml`.

**Spec:** `docs/superpowers/specs/2026-04-15-china-lens-extraction-yoy-design.md`.

**Beads:** edgarpack-483 (Slice 1), edgarpack-ws7 (Slice 2), edgarpack-ej1 (Slice 3).

---

## File Structure

Files created (2):
- `tests/test_hk_label_merge.py` — Slice 1 unit tests.
- `tests/test_hk_headcount.py` — Slice 2 HKEX + SEC headcount tests.

Files modified:
- `edgarpack/hk/extract.py` — all three slices.
- `edgarpack/query/metric_map.py` — Slice 2 (register `headcount`).
- `edgarpack/query/concepts.py` — Slice 2 (headcount MetricMeta) and Slice 3 (period offsets + derived metrics).
- `edgarpack/query/financials.py` — Slices 2 and 3 (SEC headcount fallback, multi-period pack query, `_compute_derived` offset support).
- `edgarpack/query/periods.py` — Slice 3 (period_offset kwarg on `select_period`).
- `edgarpack/compare.py` — Slice 2 (headcount render) and Slice 3 (growth percent render).
- `tests/fixtures/china_packs/minimax_2024/facts.json` — regenerated twice (after Slice 1 and after Slice 3).
- `tests/fixtures/china_packs/zhipu_2024/facts.json` — regenerated twice.
- `tests/eval/china_golden.yaml` — extended after each slice.

---

## Slice 1 — MiniMax label continuation (edgarpack-483)

### Task 1.1: Write failing unit tests for `_merge_wrapped_labels`

**Files:**
- Create: `tests/test_hk_label_merge.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the wrapped-label preprocessor in edgarpack.hk.extract.

The preprocessor joins a label line to the next line when the label wraps
across a newline, which happens in MiniMax's prospectus for 'Research and
development / expenses' and similar rows.
"""

from __future__ import annotations

from edgarpack.hk.extract import _merge_wrapped_labels


def test_merges_rd_label_across_newline():
    lines = [
        "Research and development",
        "expenses /H1118/H1118 (10,560) - (70,002) -",
    ]
    merged = _merge_wrapped_labels(lines)
    assert len(merged) == 1
    assert merged[0].startswith("Research and development expenses")
    assert "(10,560)" in merged[0]
    assert "(70,002)" in merged[0]


def test_does_not_merge_when_line_contains_amounts():
    lines = [
        "Research and development (10,560)",
        "expenses (70,002)",
    ]
    merged = _merge_wrapped_labels(lines)
    assert merged == lines, "rows with digits on both lines are real separate rows"


def test_does_not_merge_when_next_line_starts_with_capital_word():
    lines = [
        "Research and development",
        "Total operating expenses 50,000",
    ]
    merged = _merge_wrapped_labels(lines)
    assert merged == lines, "uppercase continuation word is a new row, not a wrap"


def test_preserves_unrelated_lines():
    lines = [
        "Year ended 31 December",
        "2022 2023 2024",
        "Revenue 100 200 300",
    ]
    assert _merge_wrapped_labels(lines) == lines


def test_merges_only_when_line1_matches_known_label_prefix():
    lines = [
        "Arbitrary free text",
        "continuation of arbitrary 1,234",
    ]
    # Not a known label prefix => no merge.
    assert _merge_wrapped_labels(lines) == lines
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_hk_label_merge.py -v`
Expected: ImportError / AttributeError on `_merge_wrapped_labels`.

### Task 1.2: Implement `_merge_wrapped_labels` and wire into `extract_with_regex`

**Files:**
- Modify: `edgarpack/hk/extract.py` (new helper near top; call from `extract_with_regex`).

- [ ] **Step 1: Add the helper at module scope (below `_strip_filler`)**

```python
def _merge_wrapped_labels(lines: list[str]) -> list[str]:
    """Join a label line to the next line when a known label wraps.

    Applies only when:
      * line N, after filler strip, matches a known _PROSE_LABELS prefix,
      * line N contains no digits outside filler tokens,
      * line N+1 begins with a lowercase word or a filler token.
    """
    all_label_prefixes: list[str] = []
    for labels in _PROSE_LABELS.values():
        for label in labels:
            first_word = label.split()[0].lower() if label.split() else ""
            if first_word:
                all_label_prefixes.append(first_word)
    prefix_set = set(all_label_prefixes)

    merged: list[str] = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        stripped = _strip_filler(line).strip()
        if not stripped:
            merged.append(line)
            continue
        first_word = stripped.split()[0].lower()
        has_digits = bool(re.search(r"\d", stripped))
        if (
            first_word in prefix_set
            and not has_digits
            and i + 1 < len(lines)
        ):
            next_line = lines[i + 1]
            next_stripped = _strip_filler(next_line).strip()
            if next_stripped and (
                next_stripped[0].islower() or next_stripped.startswith("/H")
            ):
                merged.append(f"{line.rstrip()} {next_line.lstrip()}")
                skip_next = True
                continue
        merged.append(line)
    return merged
```

- [ ] **Step 2: Call the helper at the start of `_extract_metric_from_section`**

In `_extract_metric_from_section`, change:

```python
    lines = text.split("\n")
```

to:

```python
    lines = _merge_wrapped_labels(text.split("\n"))
```

- [ ] **Step 3: Run unit tests**

Run: `.venv/bin/python -m pytest tests/test_hk_label_merge.py -v`
Expected: all five tests PASS.

- [ ] **Step 4: Run the full HK extractor tests**

Run: `.venv/bin/python -m pytest tests/ -k "hk or china" -x 2>&1 | tail -20`
Expected: no regressions.

### Task 1.3: Regenerate MiniMax and Zhipu facts.json

**Files:**
- Modify: `tests/fixtures/china_packs/minimax_2024/facts.json` (regenerated via script).
- Modify: `tests/fixtures/china_packs/zhipu_2024/facts.json` (regenerated via script).

- [ ] **Step 1: Regenerate via the extraction entry point**

```bash
.venv/bin/python -c "
from pathlib import Path
from edgarpack.hk.extract import extract_facts_from_pack
for name in ('minimax_2024', 'zhipu_2024'):
    p = Path(f'tests/fixtures/china_packs/{name}')
    extract_facts_from_pack(p, llm_fallback=False)
    print('regenerated', name)
"
```

- [ ] **Step 2: Verify MiniMax now has rd_expense and operating_cash_flow**

```bash
.venv/bin/python -c "
import json
data = json.load(open('tests/fixtures/china_packs/minimax_2024/facts.json'))
concepts = data['facts']['hkfrs']
assert 'ResearchAndDevelopmentExpense' in concepts, list(concepts)
assert 'NetCashProvidedByUsedInOperatingActivities' in concepts, list(concepts)
print('OK: MiniMax facts.json contains rd_expense and operating_cash_flow')
"
```

Expected: `OK: MiniMax facts.json contains rd_expense and operating_cash_flow`.

- [ ] **Step 3: Run golden harness to verify no numeric regressions on already-covered values**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -20`
Expected: all rows pass; no unexpected value changes.

### Task 1.4: Commit Slice 1

- [ ] **Step 1: Stage and commit**

```bash
cd /Users/samaydhawan/edgarpack
git add edgarpack/hk/extract.py tests/test_hk_label_merge.py \
  tests/fixtures/china_packs/minimax_2024/facts.json \
  tests/fixtures/china_packs/zhipu_2024/facts.json
git commit -m "$(cat <<'EOF'
fix(hk): merge wrapped labels so MiniMax R&D and OCF extract

MiniMax's prospectus renders some financial-statement row labels
across two lines ('Research and development\nexpenses ...'), which
the single-line regex in _extract_metric_from_section did not match.
Adds a targeted _merge_wrapped_labels preprocessor that joins a
label line to the next line only when the label matches a known
_PROSE_LABELS prefix, contains no digits, and the next line begins
with a lowercase word or filler token.

Regenerates MiniMax and Zhipu facts.json; MiniMax now extracts
rd_expense and operating_cash_flow.

Closes: edgarpack-483
EOF
)"
```

- [ ] **Step 2: Close bead**

Run: `bd close edgarpack-483`

---

## Slice 2 — Headcount extraction (edgarpack-ws7)

### Task 2.1: Register `headcount` as a canonical metric in `metric_map.py`

**Files:**
- Modify: `edgarpack/query/metric_map.py`.

- [ ] **Step 1: Add to CANONICAL_METRICS and METRIC_MAP**

In `edgarpack/query/metric_map.py`, add `"headcount"` to the `CANONICAL_METRICS` tuple (insert before `"r_and_d_intensity"`):

```python
CANONICAL_METRICS: tuple[CanonicalMetric, ...] = (
    "revenue",
    # ... existing entries ...
    "cash_burn",
    "runway_months",
    "headcount",
    "r_and_d_intensity",
    "revenue_growth_yoy",
    "gross_margin_trend",
)
```

Add `"headcount"` to each standard's dict in `METRIC_MAP`:

```python
    "US-GAAP": {
        # ... existing ...
        "runway_months": [],
        "headcount": ["EntityNumberOfEmployees", "NumberOfEmployees"],
        "r_and_d_intensity": [],
        # ... existing ...
    },
    "IFRS": {
        # ... existing ...
        "runway_months": [],
        "headcount": [],
        # ... existing ...
    },
    "HKFRS": {
        # ... existing ...
        "runway_months": [],
        "headcount": [],
        # ... existing ...
    },
    "CAS": {m: [] for m in CANONICAL_METRICS},
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_metric_map.py -v 2>&1 | tail -10`
Expected: green (no existing assertions on CANONICAL_METRICS length; if any, update to new length).

### Task 2.2: Add `headcount` to concepts.py MetricMeta

**Files:**
- Modify: `edgarpack/query/concepts.py`.

- [ ] **Step 1: Add a MetricMeta entry for headcount**

Locate `METRIC_MAP` in `edgarpack/query/concepts.py` and add:

```python
    "headcount": MetricMeta(
        concepts=("EntityNumberOfEmployees", "NumberOfEmployees"),
        duration=False,  # point-in-time disclosure at fiscal year end
    ),
```

Place it near other DEI / non-financial metrics, or beside `shares_outstanding_basic`.

- [ ] **Step 2: Run full suite**

Run: `.venv/bin/python -m pytest tests/ --ignore=tests/test_stress.py -q 2>&1 | tail -10`
Expected: green.

### Task 2.3: Write failing tests for HKEX headcount extraction

**Files:**
- Create: `tests/test_hk_headcount.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for HKEX headcount extraction + SEC fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgarpack.hk.extract import extract_headcount_from_pack


def test_minimax_headcount_is_385():
    pack = Path("tests/fixtures/china_packs/minimax_2024")
    fact = extract_headcount_from_pack(pack)
    assert fact is not None
    assert fact.value == 385
    assert fact.unit == "headcount"


def test_zhipu_headcount_is_883():
    pack = Path("tests/fixtures/china_packs/zhipu_2024")
    fact = extract_headcount_from_pack(pack)
    assert fact is not None
    assert fact.value == 883
    assert fact.unit == "headcount"


def test_out_of_bounds_value_is_rejected(tmp_path: Path):
    # Synthetic section with an obvious misfire (page number or share count).
    sections = tmp_path / "sections"
    sections.mkdir()
    (sections / "business_overview.md").write_text(
        "As of December 31, 2024, we had 42 employees at our Page 42 office.\n"
        "Background: 7 employees at founding.\n"
    )
    (tmp_path / "manifest.json").write_text(
        '{"stock_code": "XXXX", "company": "Test", "accounting_standard": "HKFRS", '
        '"reporting_currency": "USD", "fiscal_year": 2024}'
    )
    fact = extract_headcount_from_pack(tmp_path)
    # 42 is below the 50-lower-bound; 7 is also below. Should be None.
    assert fact is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_hk_headcount.py -v`
Expected: ImportError on `extract_headcount_from_pack`.

### Task 2.4: Implement `extract_headcount_from_pack` and wire into `extract_facts_from_pack`

**Files:**
- Modify: `edgarpack/hk/extract.py`.

- [ ] **Step 1: Add the extractor**

At module scope, near `extract_facts_from_pack`, add:

```python
_HEADCOUNT_PATTERN = re.compile(
    r"(\d{1,3}(?:,\d{3})*|\d+)\s+(?:full[\s\-]time\s+)?employees",
    re.IGNORECASE,
)

_HEADCOUNT_MIN = 50
_HEADCOUNT_MAX = 5_000_000


def extract_headcount_from_pack(pack_dir: Path) -> HKFact | None:
    """Scan every section for an employee-count phrase; return first bounded match."""
    import logging

    logger = logging.getLogger(__name__)
    sections_dir = pack_dir / "sections"
    if not sections_dir.exists():
        return None
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    fy: int = manifest["fiscal_year"]

    for section_file in sorted(sections_dir.glob("*.md")):
        text = section_file.read_text()
        for m in _HEADCOUNT_PATTERN.finditer(text):
            raw = m.group(1).replace(",", "")
            try:
                value = int(raw)
            except ValueError:
                continue
            if _HEADCOUNT_MIN <= value <= _HEADCOUNT_MAX:
                return HKFact(
                    metric="headcount",
                    concept="EntityNumberOfEmployees",
                    value=value,
                    unit="headcount",
                    section_id=section_file.stem,
                    extraction_method="regex",
                    matched_label=m.group(0),
                )
            logger.warning(
                "headcount candidate %s out of bounds in %s", value, section_file.name
            )
    _ = fy  # reserved for future per-period attribution
    return None
```

- [ ] **Step 2: Wire headcount into `extract_facts_from_pack`**

In `extract_facts_from_pack`, after the financial-section loop, before `if llm_fallback:`, add:

```python
    headcount_fact = extract_headcount_from_pack(pack_dir)
    if headcount_fact is not None:
        all_facts.append(headcount_fact)
```

- [ ] **Step 3: Update `extract_facts_from_pack` to emit non-currency units correctly**

In the `nested` assembly block, change:

```python
    nested: dict = {standard.lower(): {}}
    for fact in all_facts:
        concept_key = fact.concept
        nested[standard.lower()].setdefault(
            concept_key,
            {"label": concept_key, "units": {currency: []}},
        )
        nested[standard.lower()][concept_key]["units"].setdefault(currency, []).append(
```

to honor `fact.unit` (which is `"headcount"` for headcount facts and `currency` for everything else):

```python
    nested: dict = {standard.lower(): {}}
    for fact in all_facts:
        concept_key = fact.concept
        fact_unit = fact.unit if fact.unit == "headcount" else currency
        nested[standard.lower()].setdefault(
            concept_key,
            {"label": concept_key, "units": {}},
        )
        nested[standard.lower()][concept_key]["units"].setdefault(fact_unit, []).append(
```

- [ ] **Step 4: Run HK headcount tests**

Run: `.venv/bin/python -m pytest tests/test_hk_headcount.py -v`
Expected: three tests PASS.

### Task 2.5: SEC headcount text-scan helper + tests

**Files:**
- Create: `edgarpack/sec/headcount_text.py`.
- Modify: `tests/test_hk_headcount.py` (add SEC-path tests).

- [ ] **Step 1: Write failing SEC-path tests (append to `tests/test_hk_headcount.py`)**

```python
from edgarpack.sec.headcount_text import scan_headcount_from_text


def test_sec_text_scan_finds_approximate_phrase():
    text = (
        "Human Capital Resources\n\n"
        "As of December 31, 2024, we had approximately 32,000 full-time employees "
        "globally across our research, product, and operations teams."
    )
    assert scan_headcount_from_text(text) == 32_000


def test_sec_text_scan_respects_bounds():
    text = "We had 7 employees at founding; by year-end we reached 0 full-time employees."
    assert scan_headcount_from_text(text) is None


def test_sec_text_scan_returns_none_when_absent():
    text = "No disclosure of human capital resources."
    assert scan_headcount_from_text(text) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_hk_headcount.py::test_sec_text_scan_finds_approximate_phrase -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Create the module**

```python
# edgarpack/sec/headcount_text.py
"""Text-scan fallback for employee counts in SEC 10-K / 20-F filings.

Used when dei:EntityNumberOfEmployees is not disclosed as XBRL. The regex
is deliberately simple: find the first 'N employees' phrase whose integer
value falls within bounded expectations.
"""

from __future__ import annotations

import re

_PATTERN = re.compile(
    r"(?:approximately\s+)?(\d{1,3}(?:,\d{3})*|\d+)\s+(?:full[\s\-]time\s+)?employees",
    re.IGNORECASE,
)

_MIN = 50
_MAX = 5_000_000


def scan_headcount_from_text(text: str) -> int | None:
    """Return the first in-bounds employee-count integer, or None."""
    for m in _PATTERN.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            value = int(raw)
        except ValueError:
            continue
        if _MIN <= value <= _MAX:
            return value
    return None
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_hk_headcount.py -v`
Expected: all six tests PASS.

### Task 2.6: Wire SEC XBRL-first + text-scan fallback in `financials.py`

**Files:**
- Modify: `edgarpack/query/financials.py`.

Scope: after `fetch_company_facts` runs and `facts` is populated, when `headcount` is requested and `resolve_concept("headcount", facts)` returns `None`, fetch the primary document HTML for the most-recent 10-K / 20-F and apply `scan_headcount_from_text`.

- [ ] **Step 1: Add helper function below `_build_doc_map`**

```python
async def _scan_headcount_fallback(
    cik: str,
    doc_map: dict[str, str],
    accessions: list[str],
    force: bool = False,
) -> tuple[int, str] | None:
    """Return (value, accession) for the first in-bounds headcount match.

    Iterates accessions newest-first. Reads primary documents lazily; stops
    at the first match. Returns None when no accession yields a match.
    """
    from ..sec.headcount_text import scan_headcount_from_text

    cik_bare = cik.lstrip("0")
    for accn in accessions:
        primary_doc = doc_map.get(accn, "")
        if not primary_doc:
            continue
        meta = FilingMeta(
            cik=cik_bare,
            accession=accn,
            form_type="",
            filing_date=_date.min,
            primary_document=primary_doc,
            company_name="",
        )
        try:
            html_bytes = await fetch_file(meta, primary_doc)
        except (HTTPError, OSError, ValueError) as e:
            logger.warning("headcount fallback fetch failed for %s: %s", accn, e)
            continue
        text = html_bytes.decode("utf-8", errors="replace")
        value = scan_headcount_from_text(text)
        if value is not None:
            return value, accn
    return None
```

- [ ] **Step 2: Wire the fallback into the main query loop**

In `financials()`, after the per-metric resolution loop, add a post-pass for `headcount` when its value is still `None`:

Locate the metric-resolution block (where `resolve_concept` is called per metric). After the main loop, add:

```python
    if "headcount" in metric_list and result_metrics.get("headcount") is None:
        # Newest accession first. doc_map already built above.
        accessions_sorted = sorted(doc_map.keys(), reverse=True)
        fallback = await _scan_headcount_fallback(cik, doc_map, accessions_sorted, force=force)
        if fallback is not None:
            value, accn = fallback
            result_metrics["headcount"] = CitedValue(
                value=value,
                unit="headcount",
                metric="headcount",
                concept="EntityNumberOfEmployees",
                period_end=_date.today(),
                period_start=_date.today(),
                fiscal_year=_date.today().year,
                fiscal_period="FY",
                form_type="10-K",
                filed=_date.today(),
                accession=accn,
                cik=cik,
                company=company_name,
                taxonomy="dei",
                accounting_standard="US-GAAP",
                reporting_currency="USD",
                source="text-scan",
            )
```

(Exact shape of `CitedValue` constructor and the surrounding loop will need light adaptation to whatever the current code uses; the intent is: when XBRL path yielded no value, run the fallback and populate the metric with a CitedValue flagged `source="text-scan"`.)

- [ ] **Step 3: Run targeted test**

Run: `.venv/bin/python -m pytest tests/test_hk_headcount.py -v`
Expected: still green.

- [ ] **Step 4: Optional smoke against live SEC (gated on network)**

```bash
.venv/bin/python -m edgarpack.cli query NVDA headcount --period lfy 2>&1 | head -5
```

Expected: prints a plausible integer (30k-40k range as of 2025). If the value is None, confirm the primary 10-K contains the phrase; if not, that's expected and the feature gracefully returns `n/a`.

### Task 2.7: Compare renderer handles unit=headcount

**Files:**
- Modify: `edgarpack/compare.py`.

- [ ] **Step 1: Locate the rendering function and branch on unit**

Open `edgarpack/compare.py`. Find the cell-rendering helper (search for the function that formats individual metric values; it currently normalizes to USD via FX).

Add a guard at the top of the per-cell formatter:

```python
def _format_cell_value(value: CitedValue, target_currency: str) -> str:
    if value is None:
        return "n/a"
    if value.unit == "headcount":
        return f"{int(value.value):,}"
    # ... existing FX and currency formatting ...
```

If the compare renderer uses a different shape (e.g., formats per-row), port the `headcount` short-circuit into the equivalent seam. Critical invariants:
1. `unit == "headcount"` skips FX conversion entirely.
2. Output is a thousands-separated integer, no currency suffix.

- [ ] **Step 2: Run compare tests**

Run: `.venv/bin/python -m pytest tests/test_compare.py -v 2>&1 | tail -20`
Expected: green.

### Task 2.8: Regenerate fixtures and extend golden harness

**Files:**
- Modify: `tests/fixtures/china_packs/minimax_2024/facts.json`.
- Modify: `tests/fixtures/china_packs/zhipu_2024/facts.json`.
- Modify: `tests/eval/china_golden.yaml`.

- [ ] **Step 1: Regenerate facts.json with headcount**

```bash
.venv/bin/python -c "
from pathlib import Path
from edgarpack.hk.extract import extract_facts_from_pack
for name in ('minimax_2024', 'zhipu_2024'):
    extract_facts_from_pack(Path(f'tests/fixtures/china_packs/{name}'), llm_fallback=False)
    print('regenerated', name)
"
```

- [ ] **Step 2: Verify headcount is in facts.json**

```bash
.venv/bin/python -c "
import json
for name in ('minimax_2024', 'zhipu_2024'):
    data = json.load(open(f'tests/fixtures/china_packs/{name}/facts.json'))
    concepts = data['facts']['hkfrs']
    assert 'EntityNumberOfEmployees' in concepts, f'{name}: {list(concepts)}'
    print(name, 'OK')
"
```

- [ ] **Step 3: Extend `tests/eval/china_golden.yaml`**

Add rows (exact format per existing file):

```yaml
- company: minimax
  metric: headcount
  period: lfy
  expected_value: 385
  tolerance_pct: 0
  unit: headcount
- company: zhipu
  metric: headcount
  period: lfy
  expected_value: 883
  tolerance_pct: 0
  unit: headcount
```

- [ ] **Step 4: Run golden harness**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -20`
Expected: green; new headcount rows pass.

### Task 2.9: Commit Slice 2

- [ ] **Step 1: Stage and commit**

```bash
cd /Users/samaydhawan/edgarpack
git add edgarpack/query/metric_map.py edgarpack/query/concepts.py \
  edgarpack/query/financials.py edgarpack/hk/extract.py \
  edgarpack/sec/headcount_text.py edgarpack/compare.py \
  tests/test_hk_headcount.py tests/eval/china_golden.yaml \
  tests/fixtures/china_packs/minimax_2024/facts.json \
  tests/fixtures/china_packs/zhipu_2024/facts.json
git commit -m "$(cat <<'EOF'
feat(query): canonical headcount metric with HKEX + SEC paths

Adds 'headcount' as a canonical metric with unit='headcount'
(non-currency). HKEX path scans all pack sections for an
'N employees' phrase with 50 <= N <= 5,000,000 bounds. SEC path
tries dei:EntityNumberOfEmployees first; when the XBRL concept is
absent, falls back to a 10-K / 20-F primary-document text scan.
Compare renderer skips FX conversion for headcount units and
formats as a thousands-separated integer.

Closes: edgarpack-ws7
EOF
)"
```

- [ ] **Step 2: Close bead**

Run: `bd close edgarpack-ws7`

---

## Slice 3 — Multi-year HKEX extraction + YoY derivations (edgarpack-ej1)

### Task 3.1: Add `fiscal_year` to `HKFact` and extract per-year

**Files:**
- Modify: `edgarpack/hk/extract.py`.

- [ ] **Step 1: Add `fiscal_year` field to HKFact**

Change the dataclass:

```python
@dataclass(frozen=True)
class HKFact:
    metric: str
    concept: str
    value: int | float
    unit: str
    section_id: str
    extraction_method: ExtractionMethod
    matched_label: str
    fiscal_year: int = 0
```

- [ ] **Step 2: Rewrite `extract_with_regex` to iterate every detected year**

Replace the body of `extract_with_regex` with:

```python
def extract_with_regex(
    text: str,
    section_id: str,
    standard: AccountingStandard,
) -> list[HKFact]:
    if section_id not in _FINANCIAL_SECTIONS:
        return []

    metrics = _SECTION_METRICS.get(section_id, [])
    if not metrics:
        return []

    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", text[:500])]
    if not years:
        return []

    interleaved = _is_interleaved(text)
    n_years = len(years)
    multiplier = _detect_multiplier(text)

    out: list[HKFact] = []
    for fy_idx, year in enumerate(years):
        for metric in metrics:
            fact = _extract_metric_from_section(
                text, section_id, metric, fy_idx, interleaved, n_years
            )
            if fact is None:
                continue
            scaled_val = fact.value * multiplier
            if fact.metric in _MUST_BE_POSITIVE and scaled_val < 0:
                continue
            out.append(
                HKFact(
                    metric=fact.metric,
                    concept=fact.concept,
                    value=scaled_val,
                    unit=fact.unit,
                    section_id=fact.section_id,
                    extraction_method=fact.extraction_method,
                    matched_label=fact.matched_label,
                    fiscal_year=year,
                )
            )
    return out
```

- [ ] **Step 3: Thread `fiscal_year` into `extract_facts_from_pack`**

In the nested-assembly block, use `fact.fiscal_year` (falling back to manifest `fy` when 0):

```python
    nested: dict = {standard.lower(): {}}
    for fact in all_facts:
        concept_key = fact.concept
        fact_unit = fact.unit if fact.unit == "headcount" else currency
        fact_fy = fact.fiscal_year or fy
        nested[standard.lower()].setdefault(
            concept_key,
            {"label": concept_key, "units": {}},
        )
        nested[standard.lower()][concept_key]["units"].setdefault(fact_unit, []).append(
            {
                "start": f"{fact_fy}-01-01",
                "end": f"{fact_fy}-12-31",
                "val": fact.value,
                "fy": fact_fy,
                "fp": "FY",
                "form": "Annual Report",
                "accn": accession,
                "extraction_method": fact.extraction_method,
                "section_id": fact.section_id,
            }
        )
```

### Task 3.2: Tests for multi-year extraction

**Files:**
- Create: `tests/test_hk_multi_year.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests that extract_with_regex emits one HKFact per disclosed year."""

from __future__ import annotations

from edgarpack.hk.extract import extract_with_regex

_SYNTHETIC_INCOME = """Year ended 31 December
2022 2023 2024
in thousands
Revenue 1,000 2,000 3,000
"""


def test_extracts_three_years_of_revenue():
    facts = extract_with_regex(_SYNTHETIC_INCOME, "hkex_income_statement", "HKFRS")
    revenues = [f for f in facts if f.metric == "revenue"]
    years = sorted(f.fiscal_year for f in revenues)
    assert years == [2022, 2023, 2024]
    by_year = {f.fiscal_year: f.value for f in revenues}
    assert by_year[2022] == 1_000_000
    assert by_year[2023] == 2_000_000
    assert by_year[2024] == 3_000_000


def test_two_year_disclosure_is_handled():
    text = "Year ended 31 December\n2023 2024\nin thousands\nRevenue 2,000 3,000\n"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    revenues = [f for f in facts if f.metric == "revenue"]
    years = sorted(f.fiscal_year for f in revenues)
    assert years == [2023, 2024]
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_hk_multi_year.py -v`
Expected: PASS (after Task 3.1's implementation).

### Task 3.3: Update `_query_hkex_pack` to route through `select_period`

**Files:**
- Modify: `edgarpack/query/financials.py` (the `_query_hkex_pack` function, current lines 666-760).

- [ ] **Step 1: Replace the single-point loop with a multi-period aggregation**

Replace the metric-build block (starting at `for standard_key, concepts in data["facts"].items():`) with:

```python
    from .periods import select_period

    # Build facts dict in SEC-like shape for select_period compatibility.
    sec_shape: dict[str, dict[str, Any]] = {}
    taxonomy_key = "ifrs-full"  # HKFRS facts live under an IFRS-shaped namespace
    for _standard_key, concepts in data["facts"].items():
        sec_shape.setdefault(taxonomy_key, {})
        for concept, info in concepts.items():
            sec_shape[taxonomy_key][concept] = info

    from .concepts import METRIC_MAP as _CONCEPT_MAP
    from .metric_map import CANONICAL_METRICS

    if requested is None:
        requested = set(CANONICAL_METRICS)

    for metric in requested:
        meta = _CONCEPT_MAP.get(metric)
        if meta is None:
            continue
        # Look up the first concept present in facts.
        resolved_concept = None
        for candidate in meta.concepts:
            if candidate in sec_shape[taxonomy_key]:
                resolved_concept = candidate
                break
        if resolved_concept is None:
            result_metrics[metric] = None
            continue

        value = select_period(
            sec_shape,
            resolved_concept,
            metric,
            meta,
            company=data.get("company", ""),
            cik=resolved.hk_stock_code or "",  # type: ignore[attr-defined]
            period=period,
            taxonomy=taxonomy_key,
        )
        result_metrics[metric] = value
```

(Light adaptation may be needed; the existing function's CitedValue shape must round-trip through the SEC-path selection.)

- [ ] **Step 2: Run HKEX query tests**

Run: `.venv/bin/python -m pytest tests/test_china_query_hk.py tests/test_china_query_eval.py -v 2>&1 | tail -20`
Expected: green on FY24 queries; new passing invocation shapes (e.g., `--period annual:3`).

### Task 3.4: Extend `MetricMeta.components` with per-component period offsets

**Files:**
- Modify: `edgarpack/query/concepts.py`.

- [ ] **Step 1: Change the `components` field type to accept offset tuples**

```python
@dataclass(frozen=True)
class MetricMeta:
    """Metadata about a normalized metric."""

    concepts: tuple[str, ...]
    duration: bool
    derived: bool = False
    formula: str | None = None
    # Either a bare metric name (offset=0) or a (name, offset) tuple.
    components: tuple[str | tuple[str, int], ...] = ()
    ifrs_concepts: tuple[str, ...] = ()
```

- [ ] **Step 2: Add a normalizer helper (same file)**

```python
def _normalize_component(comp: str | tuple[str, int]) -> tuple[str, int]:
    return comp if isinstance(comp, tuple) else (comp, 0)
```

### Task 3.5: Extend `select_period` to honor `period_offset`

**Files:**
- Modify: `edgarpack/query/periods.py`.

- [ ] **Step 1: Add `period_offset` kwarg to `select_period`**

Change the signature:

```python
def select_period(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    period: str = "lfy",
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    period_offset: int = 0,
) -> CitedValue | DerivedValue | list[CitedValue] | None:
```

- [ ] **Step 2: When `period_offset != 0` and `period == "lfy"`, shift the target year**

At the top of the function, after `period = period.strip().lower()`, add:

```python
    if period_offset != 0 and period == "lfy":
        # Pick the fiscal year N positions back from the latest.
        from .models import CitedValue as _CV
        points = facts.get(taxonomy, {}).get(concept, {}).get("units", {})
        flat: list[tuple[int, dict]] = []
        for _unit, items in points.items():
            for p in items:
                if p.get("fp") == "FY" and "fy" in p:
                    flat.append((p["fy"], p))
        if not flat:
            return None
        flat.sort(key=lambda t: t[0], reverse=True)
        target_idx = -period_offset  # offset=-1 => 1 back => index 1
        if target_idx < 0 or target_idx >= len(flat):
            return None
        _fy, chosen = flat[target_idx]
        # Build a CitedValue from `chosen` using the same helper the rest of
        # the file uses (locate _build_cited_value or equivalent and call it).
        return _build_cited_value(chosen, concept, metric, meta, company, cik, taxonomy)
```

(`_build_cited_value` is the helper already used by `select_lfy`; if the file names it differently, reuse whatever `select_lfy` calls.)

### Task 3.6: Extend `_compute_derived` to pass offsets

**Files:**
- Modify: `edgarpack/query/financials.py`.

- [ ] **Step 1: Normalize components and propagate offset**

In `_compute_derived`, change the component-resolution loop. Where it currently does:

```python
    for comp_name in meta.components:
        comp_meta = METRIC_MAP.get(comp_name)
```

replace with:

```python
    from .concepts import _normalize_component

    for raw_comp in meta.components:
        comp_name, comp_offset = _normalize_component(raw_comp)
        comp_meta = METRIC_MAP.get(comp_name)
```

And propagate `comp_offset` into the `select_period` call:

```python
            value = select_period(
                facts,
                concept,
                comp_name,
                comp_meta,
                company,
                cik,
                period,
                taxonomy=taxonomy,
                doc_map=doc_map,
                period_offset=comp_offset,
            )
```

- [ ] **Step 2: Adapt cross-year validation**

The existing validation `fiscal_years = {comp.fiscal_year for comp in components.values()}` will now legitimately differ between current-year and prior-year components. Update to skip fiscal-year validation when any component has a nonzero offset:

```python
    any_shifted = any(
        isinstance(c, tuple) and len(c) == 2 and c[1] != 0
        for c in meta.components
    )
    if not any_shifted:
        fiscal_years = {comp.fiscal_year for comp in components.values()}
        if len(fiscal_years) > 1:
            in_progress.discard(metric)
            # ... existing cross-year diagnostic ...
```

### Task 3.7: Wire four derivations

**Files:**
- Modify: `edgarpack/query/concepts.py`.

- [ ] **Step 1: Add derived entries to `METRIC_MAP`**

Add these entries near the other derived metrics (`ebitda`, `gross_margin`, etc.):

```python
    "revenue_growth_yoy": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="(revenue[fy] / revenue[fy-1]) - 1",
        components=(("revenue", 0), ("revenue", -1)),
    ),
    "gross_margin_trend": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="gross_margin[fy] - gross_margin[fy-1]",
        components=(("gross_margin", 0), ("gross_margin", -1)),
    ),
    "r_and_d_intensity": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="rd_expense / revenue",
        components=(("rd_expense", 0), ("revenue", 0)),
    ),
    "revenue_per_employee": MetricMeta(
        concepts=(),
        duration=True,
        derived=True,
        formula="revenue / headcount",
        components=(("revenue", 0), ("headcount", 0)),
    ),
```

- [ ] **Step 2: Register `rd_expense` if not already present**

Verify `rd_expense` is in `METRIC_MAP`. If not, add:

```python
    "rd_expense": MetricMeta(
        concepts=("ResearchAndDevelopmentExpense",),
        duration=True,
        ifrs_concepts=("ResearchAndDevelopmentExpense",),
    ),
```

- [ ] **Step 3: Update `CANONICAL_METRICS` in `metric_map.py`** (if not already from Slice 2)

Ensure `revenue_per_employee` is present:

```python
CANONICAL_METRICS = (
    # ...
    "headcount",
    "revenue_per_employee",
    "r_and_d_intensity",
    "revenue_growth_yoy",
    "gross_margin_trend",
)
```

Add corresponding empty entries under each standard dict in `metric_map.py::METRIC_MAP`.

### Task 3.8: Tests for YoY derivations

**Files:**
- Create: `tests/test_query_derivations.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for period-offset derivations (YoY growth, intensity ratios)."""

from __future__ import annotations

import asyncio

from edgarpack.query.financials import financials


def test_minimax_revenue_growth_yoy_present():
    res = asyncio.run(financials(company="minimax", metrics="revenue_growth_yoy", period="lfy"))
    val = res.metrics.get("revenue_growth_yoy")
    assert val is not None
    # MiniMax revenue grew materially between FY23 and FY24.
    assert val.value > 0.5


def test_zhipu_rd_intensity_reasonable():
    res = asyncio.run(financials(company="zhipu", metrics="r_and_d_intensity", period="lfy"))
    val = res.metrics.get("r_and_d_intensity")
    assert val is not None
    # AI lab R&D intensity ranges 30%-300% of revenue.
    assert 0.3 <= val.value <= 3.0


def test_revenue_per_employee_present():
    res = asyncio.run(
        financials(company="minimax", metrics="revenue_per_employee", period="lfy")
    )
    val = res.metrics.get("revenue_per_employee")
    assert val is not None
    assert val.unit == "USD"
    # 385 employees, positive revenue in USD.
    assert val.value > 1_000


def test_missing_prior_year_returns_none_gracefully():
    # A company with only FY24 disclosed (e.g., hypothetical or truncated fixture)
    # should return None for revenue_growth_yoy without raising.
    # Skip if no such fixture exists; this is a guardrail for future filings.
    pass
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_query_derivations.py -v`
Expected: three tests PASS (after fixture regeneration in 3.10). The missing-prior-year case is a placeholder; implement concretely once we have a 1-year fixture.

### Task 3.9: Compare renderer formats growth as signed percent

**Files:**
- Modify: `edgarpack/compare.py`.

- [ ] **Step 1: Extend the per-cell formatter**

After the `unit == "headcount"` short-circuit from Task 2.7, add a growth-metric branch:

```python
    _GROWTH_METRICS = {"revenue_growth_yoy", "gross_margin_trend"}
    _RATIO_METRICS = {"r_and_d_intensity", "gross_margin", "operating_margin"}

def _format_cell_value(value, target_currency):
    if value is None:
        return "n/a"
    if value.unit == "headcount":
        return f"{int(value.value):,}"
    if value.metric in _GROWTH_METRICS:
        pct = value.value * 100
        if abs(pct) >= 10:
            return f"{pct:+.0f}%"
        return f"{pct:+.1f}%"
    if value.metric in _RATIO_METRICS:
        return f"{value.value * 100:.0f}%"
    # ... existing FX + currency rendering ...
```

- [ ] **Step 2: Run compare tests**

Run: `.venv/bin/python -m pytest tests/test_compare.py -v 2>&1 | tail -20`
Expected: green.

### Task 3.10: Regenerate fixtures and extend golden harness

**Files:**
- Modify: `tests/fixtures/china_packs/minimax_2024/facts.json`.
- Modify: `tests/fixtures/china_packs/zhipu_2024/facts.json`.
- Modify: `tests/eval/china_golden.yaml`.

- [ ] **Step 1: Regenerate with multi-year extraction**

```bash
.venv/bin/python -c "
from pathlib import Path
from edgarpack.hk.extract import extract_facts_from_pack
for name in ('minimax_2024', 'zhipu_2024'):
    extract_facts_from_pack(Path(f'tests/fixtures/china_packs/{name}'), llm_fallback=False)
    print('regenerated', name)
"
```

- [ ] **Step 2: Verify multi-year entries present**

```bash
.venv/bin/python -c "
import json
for name in ('minimax_2024', 'zhipu_2024'):
    data = json.load(open(f'tests/fixtures/china_packs/{name}/facts.json'))
    revenue = data['facts']['hkfrs'].get('Revenue', {})
    currency = list(revenue.get('units', {}).keys())[0]
    years = sorted(p['fy'] for p in revenue['units'][currency])
    print(name, 'revenue years:', years)
    assert len(years) >= 2, f'{name}: expected multi-year, got {years}'
"
```

- [ ] **Step 3: Add golden rows**

Append to `tests/eval/china_golden.yaml`:

```yaml
- company: minimax
  metric: revenue
  period: "annual:3"
  expected_series:
    - {fy: 2022, value: <from-prospectus>, tolerance_pct: 1}
    - {fy: 2023, value: <from-prospectus>, tolerance_pct: 1}
    - {fy: 2024, value: <from-prospectus>, tolerance_pct: 1}
  unit: USD
- company: minimax
  metric: revenue_growth_yoy
  period: lfy
  expected_value: <computed>
  tolerance_pct: 2
  unit: ratio
- company: minimax
  metric: r_and_d_intensity
  period: lfy
  expected_value: <computed>
  tolerance_pct: 2
  unit: ratio
- company: minimax
  metric: revenue_per_employee
  period: lfy
  expected_value: <computed>
  tolerance_pct: 2
  unit: USD
# mirror for zhipu
```

Fill in the `<...>` placeholders by reading the regenerated facts.json and computing expected values against the prospectus tables.

- [ ] **Step 4: Run golden harness**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -v 2>&1 | tail -30`
Expected: all rows green.

- [ ] **Step 5: Full suite lint + test**

Run:

```bash
ruff check . && ruff format --check .
.venv/bin/python -m pytest tests/ --ignore=tests/test_stress.py -q
```

Expected: lint clean; 680+ tests pass (exact count shifts with new tests).

### Task 3.11: Commit Slice 3

- [ ] **Step 1: Stage and commit**

```bash
cd /Users/samaydhawan/edgarpack
git add edgarpack/hk/extract.py edgarpack/query/concepts.py \
  edgarpack/query/financials.py edgarpack/query/periods.py \
  edgarpack/query/metric_map.py edgarpack/compare.py \
  tests/test_hk_multi_year.py tests/test_query_derivations.py \
  tests/eval/china_golden.yaml \
  tests/fixtures/china_packs/minimax_2024/facts.json \
  tests/fixtures/china_packs/zhipu_2024/facts.json
git commit -m "$(cat <<'EOF'
feat(query): multi-year HKEX extraction + YoY derivations

Generalizes the HKEX extractor to emit one HKFact per disclosed
fiscal year. Extends MetricMeta.components with per-component
period offsets so _compute_derived can express (x[fy] / x[fy-1]).
Wires four derivations: revenue_growth_yoy, gross_margin_trend,
r_and_d_intensity, revenue_per_employee.

Compare renderer formats growth metrics as signed percent
(+50%, -12%) and ratios as unsigned percent.

Closes: edgarpack-ej1
EOF
)"
```

- [ ] **Step 2: Close bead**

Run: `bd close edgarpack-ej1`

- [ ] **Step 3: Sync beads**

Run: `bd sync`

- [ ] **Step 4: Push**

Run: `git push`

---

## Self-Review Summary

- Spec coverage: Slice 1 covers edgarpack-483 (Tasks 1.1-1.4). Slice 2 covers edgarpack-ws7 including SEC and HKEX headcount paths (Tasks 2.1-2.9). Slice 3 covers edgarpack-ej1 multi-year + YoY + rev/employee (Tasks 3.1-3.11).
- Type consistency: `HKFact` gains `fiscal_year: int = 0` in 3.1; used in 3.1 step 3. `MetricMeta.components` type change in 3.4; honored in 3.5 and 3.6.
- Placeholder scan: The only intentional placeholder is the `<from-prospectus>` in Task 3.10 Step 3 — the engineer fills those in from the regenerated facts.json (the values cannot be known before the regeneration runs).
- Risk items surfaced in the spec are addressed: false-merges (Task 1.1 negative case), text-scan flakiness (Task 2.6 returns None gracefully), missing prior year (Task 3.8 placeholder + 3.6's existing None-return path).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-15-china-lens-extraction-yoy.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks, fastest iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans with checkpoints.

Which approach?
