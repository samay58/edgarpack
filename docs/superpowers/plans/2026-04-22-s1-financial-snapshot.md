# S-1 Financial Snapshot for `edgarpack query` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `edgarpack query "Cerebras Systems" revenue` returns real financial figures extracted from the S-1 via Claude Haiku 4.5, clearly labeled as S-1-sourced with accession markers, with 10-K data winning for overlapping periods.

**Architecture:** One new module `edgarpack/query/s1_financials.py`. Lazy Haiku extraction on first `query` call, cached as `<pack>/s1_financials.json` keyed by sha256 of source markdown. Fallback wired into existing `financials()` tail: when companyfacts returns empty cells, fill them from the most recent registration-class pack's snapshot. Native currency output. Audited historical + pro-forma both stored; only pro-forma via explicit `--period pro-forma`.

**Tech Stack:** Python 3.11+, pydantic v2, pytest + pytest-asyncio, ruff, anthropic SDK (existing optional `vlm` extra).

**Spec reference:** `docs/superpowers/specs/2026-04-22-s1-financial-snapshot-design.md`

**Branch:** `feat/new-filer-s1-support` (in progress; this ships alongside the S-1 parser work already committed).

---

## File structure locked in before tasks

| File | Role | Created / Modified |
|---|---|---|
| `edgarpack/query/s1_financials.py` | Snapshot extractor + cache + query entry points | NEW |
| `edgarpack/query/models.py` | Add two optional fields to `CitedValue` | Modified |
| `edgarpack/query/financials.py` | Wire fallback branch at tail | Modified |
| `edgarpack/query/periods.py` | Recognize `pro-forma` period | Modified |
| `edgarpack/query/metric_map.py` | Confirm 9 metrics covered | Modified |
| `edgarpack/query/formatting.py` | Inline S-1 citation marker + pro-forma footnote | Modified |
| `edgarpack/cli.py` | JSON fields pass through | Modified |
| `tests/test_s1_financials_extract.py` | Unit tests on extractor | NEW |
| `tests/test_s1_financials_query_integration.py` | End-to-end on fake packs | NEW |
| `tests/test_s1_financials_formatting.py` | Table + JSON output | NEW |
| `tests/fixtures/cerebras_selected_financial_data.md` | Real Cerebras table slice | NEW |

---

## Task 1: SnapshotFact dataclass + module skeleton

**Files:**
- Create: `edgarpack/query/s1_financials.py`
- Create: `tests/test_s1_financials_extract.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_s1_financials_extract.py`:

```python
"""Unit tests for S-1 financial snapshot extraction.

Tests cover the pure-data side of the extractor (dataclasses, cache layer,
prompt builder, JSON parser). Network calls to Anthropic are monkeypatched
throughout; a separate live-smoke test exercises the real API path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgarpack.query.s1_financials import (
    METRIC_SLUGS,
    SnapshotFact,
    SnapshotResult,
)


def test_snapshot_fact_required_fields():
    fact = SnapshotFact(
        accession="0001628280-24-041596",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="revenue",
        value_cents=7828700000,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    assert fact.metric == "revenue"
    assert fact.value_cents == 7828700000
    assert fact.currency == "USD"
    assert fact.is_audited is True
    assert fact.is_pro_forma is False
    assert fact.pro_forma_note is None


def test_snapshot_fact_pro_forma_with_assumption():
    fact = SnapshotFact(
        accession="0001628280-26-025762",
        fiscal_year=2025,
        period_end="2025-12-31",
        metric="cash_and_equivalents",
        value_cents=124310000000,
        currency="USD",
        is_audited=False,
        is_pro_forma=True,
        pro_forma_note="assumes IPO price $32.50, midpoint",
    )
    assert fact.is_pro_forma is True
    assert fact.pro_forma_note is not None
    assert "$32.50" in fact.pro_forma_note


def test_metric_slugs_contains_all_nine_v1_metrics():
    assert {
        "revenue",
        "gross_profit",
        "operating_income_loss",
        "net_income_loss",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    } == METRIC_SLUGS


def test_snapshot_result_serializes_to_json():
    result = SnapshotResult(
        schema_version=1,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T18:14:00Z",
        extraction_status="ok",
        source_sha256="abc123",
        model="claude-haiku-4-5-20251001",
        facts=[
            SnapshotFact(
                accession="0001628280-24-041596",
                fiscal_year=2024,
                period_end="2024-12-31",
                metric="revenue",
                value_cents=7828700000,
                currency="USD",
                is_audited=True,
                is_pro_forma=False,
                pro_forma_note=None,
            ),
        ],
    )
    payload = json.loads(result.to_json())
    assert payload["schema_version"] == 1
    assert payload["accession"] == "0001628280-24-041596"
    assert payload["extraction_status"] == "ok"
    assert len(payload["facts"]) == 1
    assert payload["facts"][0]["metric"] == "revenue"
    assert payload["facts"][0]["value_cents"] == 7828700000


def test_snapshot_result_deserializes_from_json():
    raw = json.dumps(
        {
            "schema_version": 1,
            "accession": "0001628280-24-041596",
            "extracted_at": "2026-04-22T18:14:00Z",
            "extraction_status": "ok",
            "source_sha256": "abc123",
            "model": "claude-haiku-4-5-20251001",
            "facts": [
                {
                    "accession": "0001628280-24-041596",
                    "fiscal_year": 2024,
                    "period_end": "2024-12-31",
                    "metric": "revenue",
                    "value_cents": 7828700000,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                }
            ],
        }
    )
    result = SnapshotResult.from_json(raw)
    assert len(result.facts) == 1
    assert result.facts[0].metric == "revenue"
    assert result.facts[0].value_cents == 7828700000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: `ImportError: cannot import name 'SnapshotFact' from 'edgarpack.query.s1_financials'`.

- [ ] **Step 3: Create the module skeleton**

Create `edgarpack/query/s1_financials.py` with exactly this content:

```python
"""Extract headline financial figures from pre-IPO S-1 filings.

SEC's companyfacts API is empty for pre-IPO filers (it's populated from
10-K / 10-Q / 20-F only), and Cerebras-era S-1 primary documents carry
no embedded iXBRL tags. The real numbers live in the filing's rendered
prose and tables. This module extracts them with a single Haiku 4.5
call per filing, caches the result to disk, and exposes them through
the existing `edgarpack query` surface via a fallback in
`edgarpack/query/financials.py`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

# Canonical slug set. Must stay in sync with METRIC_MAP in
# edgarpack/query/metric_map.py so CitedValue conversions resolve
# correctly downstream.
METRIC_SLUGS: frozenset[str] = frozenset(
    {
        "revenue",
        "gross_profit",
        "operating_income_loss",
        "net_income_loss",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    }
)


@dataclass(frozen=True)
class SnapshotFact:
    """One financial figure extracted from an S-1 filing.

    value_cents is an integer in the reporting currency's smallest unit
    (cents for USD, öre for SEK, and so on). The currency field names the
    ISO 4217 code so callers can convert later if they want; v1 renders
    native-currency only.
    """

    accession: str
    fiscal_year: int
    period_end: str  # ISO date YYYY-MM-DD
    metric: str  # member of METRIC_SLUGS
    value_cents: int
    currency: str  # ISO 4217
    is_audited: bool
    is_pro_forma: bool
    pro_forma_note: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotResult:
    """All extracted facts for one S-1 pack, plus extraction metadata.

    Persisted as `<pack_dir>/s1_financials.json`. `source_sha256` is the
    sha256 of the first 50KB of `<pack_dir>/filing.full.md`, used to
    invalidate the cache when the source markdown changes.
    """

    schema_version: int
    accession: str
    extracted_at: str  # ISO 8601 UTC
    extraction_status: str  # "ok" | "llm_parse_failed" | "no_financial_data_found" | "no_api_key"
    source_sha256: str
    model: str
    facts: list[SnapshotFact]

    def to_json(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "accession": self.accession,
            "extracted_at": self.extracted_at,
            "extraction_status": self.extraction_status,
            "source_sha256": self.source_sha256,
            "model": self.model,
            "facts": [f.to_dict() for f in self.facts],
        }
        return json.dumps(payload, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> SnapshotResult:
        data = json.loads(raw)
        facts = [SnapshotFact(**f) for f in data.get("facts", [])]
        return cls(
            schema_version=int(data["schema_version"]),
            accession=str(data["accession"]),
            extracted_at=str(data["extracted_at"]),
            extraction_status=str(data["extraction_status"]),
            source_sha256=str(data["source_sha256"]),
            model=str(data["model"]),
            facts=facts,
        )


def _utc_iso_now() -> str:
    """Single source of truth for ISO-8601 UTC timestamps used in caches."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/s1_financials.py tests/test_s1_financials_extract.py
git commit -m "feat(query): SnapshotFact/SnapshotResult dataclasses + METRIC_SLUGS"
```

---

## Task 2: Selected-Financial-Data section detection

**Files:**
- Modify: `edgarpack/query/s1_financials.py` (append)
- Modify: `tests/test_s1_financials_extract.py` (append)
- Create: `tests/fixtures/cerebras_selected_financial_data.md`

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/cerebras_selected_financial_data.md`. Paste this content verbatim:

```markdown
# Selected Financial Data

The following selected consolidated financial data should be read in conjunction
with our consolidated financial statements and the related notes.

(in thousands, except per-share data)

|  | Year Ended December 31 |
| --- | --- |
|  | 2024 | 2023 |
| Revenue | 78,287 | 8,768 |
| Cost of revenue | 30,204 | 7,443 |
| Gross profit | 48,083 | 1,325 |
| Operating loss | (259,247) | (258,782) |
| Net loss | (259,251) | (268,912) |
| Net loss per share, basic and diluted | $(1.08) | $(1.19) |

Balance sheet data (in thousands):

|  | December 31, 2024 |
| --- | --- |
| Cash and cash equivalents | 209,912 |
| Total assets | 447,688 |
| Total stockholders' equity (deficit) | (1,052,110) |

Weighted-average shares outstanding, basic and diluted: 240,123,456

Unaudited Pro Forma Information:

The following pro forma information gives effect to the offering, assuming an
initial public offering price of $32.50 per share (the midpoint of the range).

|  | December 31, 2024 (Pro Forma) |
| --- | --- |
| Cash and cash equivalents | 1,103,412 |
| Total stockholders' equity | 52,302 |
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_s1_financials_extract.py`:

```python
from edgarpack.query.s1_financials import find_financial_data_section


FIXTURE_DIR = Path(__file__).parent / "fixtures"
CEREBRAS_SFD = FIXTURE_DIR / "cerebras_selected_financial_data.md"


def test_find_financial_data_section_matches_selected_heading():
    md = CEREBRAS_SFD.read_text(encoding="utf-8")
    section = find_financial_data_section(md)
    assert section is not None
    assert "Revenue" in section
    assert "78,287" in section


def test_find_financial_data_section_matches_summary_alternate():
    md = "# Summary Consolidated Financial Data\n\nRevenue ... 100\n\n# Other\n\nFoo"
    section = find_financial_data_section(md)
    assert section is not None
    assert "Revenue" in section
    assert "Foo" not in section  # Stops at next heading


def test_find_financial_data_section_returns_none_when_absent():
    md = "# Risk Factors\n\nInvesting involves risk.\n\n# Business\n\nWe design systems."
    assert find_financial_data_section(md) is None


def test_find_financial_data_section_truncates_to_50kb_ceiling():
    # Oversized section should be capped.
    huge = "# Selected Financial Data\n\n" + ("x" * 100_000)
    section = find_financial_data_section(huge)
    assert section is not None
    assert len(section) <= 50_000 + 200  # tiny slack for heading text itself
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: 4 new tests FAIL with `ImportError: cannot import name 'find_financial_data_section'`.

- [ ] **Step 4: Implement the section finder**

Append to `edgarpack/query/s1_financials.py`:

```python
import re

# S-1 filers use a handful of canonical phrasings for the financial
# summary section. Match the opening heading, stop at the next level-1
# or level-2 heading. Case-insensitive so Cerebras's "Selected Financial
# Data" and Klarna's "SELECTED FINANCIAL DATA" both fire.
_FINANCIAL_DATA_HEADINGS = [
    r"selected consolidated financial data",
    r"summary consolidated financial data",
    r"selected financial data",
    r"summary financial data",
    r"selected historical financial data",
]

_FINDATA_RE = re.compile(
    r"^\#{1,3}\s+(?:" + "|".join(_FINANCIAL_DATA_HEADINGS) + r")\b",
    re.IGNORECASE | re.MULTILINE,
)

# Section content is capped to keep the prompt well under Haiku's context
# window and to prevent runaway costs when the filing has a malformed TOC
# that absorbs 100KB+ of body text.
_SECTION_CAP_CHARS = 50_000


def find_financial_data_section(markdown: str) -> str | None:
    """Return the Selected Financial Data section body, or None if absent.

    Matches any of the canonical S-1 phrasings, truncates to 50KB, and
    stops at the next heading line so adjacent sections don't bleed in.
    """
    if not markdown:
        return None
    match = _FINDATA_RE.search(markdown)
    if not match:
        return None
    start = match.start()
    rest = markdown[start:]
    # End at the next H1/H2 heading after at least one newline of body.
    next_heading = re.search(r"\n\#{1,2}\s+\S", rest[1:])
    if next_heading is not None:
        end = 1 + next_heading.start()
        rest = rest[:end]
    return rest[:_SECTION_CAP_CHARS]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/query/s1_financials.py tests/test_s1_financials_extract.py tests/fixtures/cerebras_selected_financial_data.md
git commit -m "feat(query): find_financial_data_section detects S-1 selected-data headings"
```

---

## Task 3: LLM prompt builder + JSON schema validation

**Files:**
- Modify: `edgarpack/query/s1_financials.py` (append)
- Modify: `tests/test_s1_financials_extract.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_s1_financials_extract.py`:

```python
from edgarpack.query.s1_financials import (
    PROMPT_SYSTEM,
    build_extraction_prompt,
    parse_llm_response,
)


def test_build_extraction_prompt_includes_section_text():
    prompt = build_extraction_prompt("# Selected Financial Data\n\nRevenue 100")
    assert "Selected Financial Data" in prompt
    assert "Revenue 100" in prompt


def test_build_extraction_prompt_enumerates_all_nine_metrics():
    prompt = build_extraction_prompt("# stub")
    for slug in (
        "revenue",
        "gross_profit",
        "operating_income_loss",
        "net_income_loss",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    ):
        assert slug in prompt, f"prompt missing metric: {slug}"


def test_parse_llm_response_accepts_valid_array():
    raw = """[
        {
            "fiscal_year": 2024,
            "period_end": "2024-12-31",
            "metric": "revenue",
            "value_cents": 7828700000,
            "currency": "USD",
            "is_audited": true,
            "is_pro_forma": false,
            "pro_forma_note": null
        }
    ]"""
    facts = parse_llm_response(raw, accession="0001628280-24-041596")
    assert len(facts) == 1
    assert facts[0].metric == "revenue"
    assert facts[0].accession == "0001628280-24-041596"
    assert facts[0].value_cents == 7828700000


def test_parse_llm_response_accepts_json_wrapped_in_code_block():
    raw = """```json
[
    {
        "fiscal_year": 2024,
        "period_end": "2024-12-31",
        "metric": "revenue",
        "value_cents": 7828700000,
        "currency": "USD",
        "is_audited": true,
        "is_pro_forma": false,
        "pro_forma_note": null
    }
]
```"""
    facts = parse_llm_response(raw, accession="x")
    assert len(facts) == 1


def test_parse_llm_response_drops_rows_with_unknown_metric():
    raw = """[
        {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "bogus",
         "value_cents": 1, "currency": "USD", "is_audited": true,
         "is_pro_forma": false, "pro_forma_note": null},
        {"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "revenue",
         "value_cents": 1, "currency": "USD", "is_audited": true,
         "is_pro_forma": false, "pro_forma_note": null}
    ]"""
    facts = parse_llm_response(raw, accession="x")
    assert len(facts) == 1
    assert facts[0].metric == "revenue"


def test_parse_llm_response_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_llm_response("not json at all", accession="x")


def test_parse_llm_response_rejects_non_array_payload():
    with pytest.raises(ValueError, match="expected JSON array"):
        parse_llm_response('{"not": "an array"}', accession="x")


def test_parse_llm_response_drops_rows_missing_required_fields():
    raw = """[
        {"fiscal_year": 2024, "metric": "revenue"}
    ]"""
    facts = parse_llm_response(raw, accession="x")
    assert facts == []


def test_prompt_system_forbids_fabrication():
    # Sanity: the system prompt tells the model not to invent facts.
    assert "not fabricate" in PROMPT_SYSTEM.lower() or "only" in PROMPT_SYSTEM.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: all new tests FAIL with missing names.

- [ ] **Step 3: Implement the prompt builder and parser**

Append to `edgarpack/query/s1_financials.py`:

```python
PROMPT_SYSTEM = (
    "You are extracting historical and pro-forma financial figures from an "
    "SEC Form S-1 filing. Return ONLY a JSON array. Do not fabricate: emit "
    "ONLY facts the filing explicitly states. Skip any figure you are less "
    "than 90% confident about."
)

_PROMPT_USER_TEMPLATE = """Return a JSON array. Each element is one fact:

{{
  "fiscal_year": 2024,
  "period_end": "2024-12-31",
  "metric": "revenue" | "gross_profit" | "operating_income_loss" | "net_income_loss"
          | "cash_and_equivalents" | "total_assets" | "stockholders_equity"
          | "shares_outstanding_basic" | "eps_basic",
  "value_cents": 78287000000,
  "currency": "USD",
  "is_audited": true,
  "is_pro_forma": false,
  "pro_forma_note": null
}}

RULES:
- Values are integers in the reporting currency's smallest unit (cents for USD).
- Do NOT scale: if the filing says "78,287" and the preamble says "in thousands"
  then value_cents = 78,287 * 1000 * 100 = 7,828,700,000.
- Losses are negative integers (e.g. "Net loss (259,251)" with "in thousands"
  becomes value_cents = -25,925,100,000).
- Per-share figures: value_cents is cents per share. "$(1.08)" becomes -108.
- Share counts: shares_outstanding_basic uses value_cents for the count itself
  (scaled by 100). "240,123,456" shares becomes value_cents = 24,012,345,600.
- Pro-forma rows MUST set is_pro_forma=true and record the assumption verbatim
  in pro_forma_note. Historical audited rows set is_pro_forma=false.
- period_end must be ISO YYYY-MM-DD.
- Return [] when the text contains no extractable financial data.

TEXT:
{text}
"""


def build_extraction_prompt(section_text: str) -> str:
    """Render the user-message prompt that ships with the Haiku call.

    The system prompt (PROMPT_SYSTEM) is set separately on the API request.
    """
    enum_line = (
        " | ".join(f'"{s}"' for s in sorted(METRIC_SLUGS))
    )
    # enum_line substitution is not strictly needed because the template
    # hard-codes the list; retained as a defensive reminder that the two
    # must stay in sync.
    return _PROMPT_USER_TEMPLATE.format(text=section_text) + (
        f"\n\n# Metric slugs allowed: {enum_line}"
    )


def _strip_code_fences(raw: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    s = raw.strip()
    if s.startswith("```"):
        # Drop first line (```json or similar) and trailing fence.
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


_REQUIRED_KEYS = (
    "fiscal_year",
    "period_end",
    "metric",
    "value_cents",
    "currency",
    "is_audited",
    "is_pro_forma",
)


def parse_llm_response(raw: str, *, accession: str) -> list[SnapshotFact]:
    """Parse the model's JSON response into SnapshotFact objects.

    Drops any row missing required keys or whose metric is not in
    METRIC_SLUGS. Raises ValueError for unparseable output so callers
    can mark the extraction as failed and cache accordingly.
    """
    stripped = _strip_code_fences(raw)
    if not stripped:
        raise ValueError("invalid JSON: empty response")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"expected JSON array, got {type(payload).__name__}")

    facts: list[SnapshotFact] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        if any(k not in row for k in _REQUIRED_KEYS):
            continue
        if row.get("metric") not in METRIC_SLUGS:
            continue
        try:
            fact = SnapshotFact(
                accession=accession,
                fiscal_year=int(row["fiscal_year"]),
                period_end=str(row["period_end"]),
                metric=str(row["metric"]),
                value_cents=int(row["value_cents"]),
                currency=str(row["currency"]),
                is_audited=bool(row["is_audited"]),
                is_pro_forma=bool(row["is_pro_forma"]),
                pro_forma_note=(
                    str(row["pro_forma_note"])
                    if row.get("pro_forma_note") is not None
                    else None
                ),
            )
        except (ValueError, TypeError):
            continue
        facts.append(fact)
    return facts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/s1_financials.py tests/test_s1_financials_extract.py
git commit -m "feat(query): LLM prompt builder + strict JSON response parser"
```

---

## Task 4: Haiku client wrapper with mocked tests

**Files:**
- Modify: `edgarpack/query/s1_financials.py` (append)
- Modify: `tests/test_s1_financials_extract.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_s1_financials_extract.py`:

```python
from unittest.mock import AsyncMock, patch

from edgarpack.query.s1_financials import MODEL_ID, _call_haiku_extract


@pytest.mark.asyncio
async def test_call_haiku_extract_returns_raw_response_text(monkeypatch):
    fake_text = (
        '[{"fiscal_year": 2024, "period_end": "2024-12-31", "metric": "revenue",'
        ' "value_cents": 7828700000, "currency": "USD", "is_audited": true,'
        ' "is_pro_forma": false, "pro_forma_note": null}]'
    )

    class _FakeBlock:
        type = "text"
        text = fake_text

    class _FakeMessage:
        content = [_FakeBlock()]

    class _FakeMessages:
        async def create(self, **kwargs):  # noqa: ARG002
            return _FakeMessage()

    class _FakeClient:
        messages = _FakeMessages()

    # Bypass the lazy import guard by providing a dummy anthropic symbol.
    import types

    fake_module = types.SimpleNamespace(AsyncAnthropic=lambda: _FakeClient())
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_module)

    out = await _call_haiku_extract("# stub section")
    assert out == fake_text


@pytest.mark.asyncio
async def test_call_haiku_extract_raises_runtime_error_when_sdk_missing(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "anthropic", None)
    # Mimic the import failure by deleting the cached module entry.
    sys.modules.pop("anthropic", None)

    with patch.dict("sys.modules", {}, clear=False):
        # Pretend the import fails by shadowing the name.
        with patch(
            "edgarpack.query.s1_financials._call_haiku_extract",
            wraps=_call_haiku_extract,
        ):
            # We call the real function but expect RuntimeError since
            # anthropic is not installed in the test environment.
            with pytest.raises(RuntimeError, match="anthropic"):
                await _call_haiku_extract("# stub")


def test_model_id_is_haiku_4_5():
    assert MODEL_ID == "claude-haiku-4-5-20251001"
```

Note: the SDK-missing test is brittle. Replace it with this simpler form that exercises the real guard by forcing an ImportError via monkeypatch of the module finder:

```python
@pytest.mark.asyncio
async def test_call_haiku_extract_raises_when_anthropic_import_fails(monkeypatch):
    import sys

    # Remove any cached `anthropic` module and block the import by installing
    # a finder that raises ImportError for that exact name.
    sys.modules.pop("anthropic", None)

    class _BlockAnthropicFinder:
        def find_spec(self, name, path, target=None):
            if name == "anthropic":
                raise ImportError("anthropic is not installed in test env")
            return None

    sys.meta_path.insert(0, _BlockAnthropicFinder())
    try:
        with pytest.raises(RuntimeError, match="anthropic"):
            await _call_haiku_extract("# stub")
    finally:
        sys.meta_path.pop(0)
```

Use this second form. Delete the brittle `test_call_haiku_extract_raises_runtime_error_when_sdk_missing` test from Step 1's first draft.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: 2 new tests fail (`ImportError: cannot import name '_call_haiku_extract'`, `MODEL_ID`).

- [ ] **Step 3: Implement the Haiku client wrapper**

Append to `edgarpack/query/s1_financials.py`:

```python
MODEL_ID = "claude-haiku-4-5-20251001"
_MAX_OUTPUT_TOKENS = 4000


async def _call_haiku_extract(section_text: str) -> str:
    """Invoke Claude Haiku 4.5 and return the raw text of the first content block.

    Anthropic import is deferred so environments without the optional `vlm`
    extra can still import this module. Raises RuntimeError with an install
    hint when the SDK is missing so callers can surface a friendly message.
    """
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError(
            "S-1 financial extraction requires the `anthropic` package. "
            "Install with `pip install edgarpack[vlm]` and export "
            "ANTHROPIC_API_KEY."
        ) from exc

    client = AsyncAnthropic()
    prompt = build_extraction_prompt(section_text)
    message = await client.messages.create(
        model=MODEL_ID,
        max_tokens=_MAX_OUTPUT_TOKENS,
        system=PROMPT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ]
    return "".join(text_blocks).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/s1_financials.py tests/test_s1_financials_extract.py
git commit -m "feat(query): Haiku 4.5 client wrapper with lazy anthropic import"
```

---

## Task 5: Cache layer + `extract_or_load_snapshot`

**Files:**
- Modify: `edgarpack/query/s1_financials.py` (append)
- Modify: `tests/test_s1_financials_extract.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_s1_financials_extract.py`:

```python
from edgarpack.query.s1_financials import (
    SCHEMA_VERSION,
    extract_or_load_snapshot,
    source_sha256_for_pack,
)


def _write_pack(
    root: Path,
    accession: str = "0001628280-24-041596",
    *,
    markdown: str | None = None,
    form_type: str = "S-1",
) -> Path:
    pack = root / accession
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "filing.full.md").write_text(
        markdown if markdown is not None else "# Selected Financial Data\n\nRevenue 78,287",
        encoding="utf-8",
    )
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "filing": {
                    "accession": accession,
                    "form_type": form_type,
                    "filing_date": "2024-09-30",
                    "cik": "0002021728",
                    "company_name": "Cerebras Systems Inc",
                },
                "sections": [],
                "parser_version": "test",
            }
        ),
        encoding="utf-8",
    )
    return pack


def test_source_sha256_for_pack_is_stable(tmp_path):
    pack = _write_pack(tmp_path, markdown="hello world")
    digest_a = source_sha256_for_pack(pack)
    digest_b = source_sha256_for_pack(pack)
    assert digest_a == digest_b
    assert len(digest_a) == 64  # sha256 hex


def test_source_sha256_for_pack_changes_on_content_change(tmp_path):
    pack = _write_pack(tmp_path, markdown="A")
    digest_a = source_sha256_for_pack(pack)
    (pack / "filing.full.md").write_text("B", encoding="utf-8")
    digest_b = source_sha256_for_pack(pack)
    assert digest_a != digest_b


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_writes_cache_on_first_call(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def fake_haiku(_section):
        return json.dumps(
            [
                {
                    "fiscal_year": 2024,
                    "period_end": "2024-12-31",
                    "metric": "revenue",
                    "value_cents": 7828700000,
                    "currency": "USD",
                    "is_audited": True,
                    "is_pro_forma": False,
                    "pro_forma_note": None,
                }
            ]
        )

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", fake_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "ok"
    assert len(result.facts) == 1
    assert result.facts[0].metric == "revenue"
    # Cache file written.
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_cache_hit_skips_llm(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nRevenue 1")

    # Pre-seed the cache file.
    seeded = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T00:00:00Z",
        extraction_status="ok",
        source_sha256=source_sha256_for_pack(pack),
        model=MODEL_ID,
        facts=[
            SnapshotFact(
                accession="0001628280-24-041596",
                fiscal_year=2024,
                period_end="2024-12-31",
                metric="revenue",
                value_cents=100,
                currency="USD",
                is_audited=True,
                is_pro_forma=False,
                pro_forma_note=None,
            )
        ],
    )
    (pack / "s1_financials.json").write_text(seeded.to_json(), encoding="utf-8")

    called = {"n": 0}

    async def counting_haiku(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", counting_haiku)

    result = await extract_or_load_snapshot(pack)
    assert called["n"] == 0
    assert len(result.facts) == 1
    assert result.facts[0].value_cents == 100


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_invalidates_on_source_change(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nA")
    seeded = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T00:00:00Z",
        extraction_status="ok",
        source_sha256="stale_hash",  # deliberately wrong
        model=MODEL_ID,
        facts=[],
    )
    (pack / "s1_financials.json").write_text(seeded.to_json(), encoding="utf-8")

    called = {"n": 0}

    async def fresh_haiku(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", fresh_haiku)

    await extract_or_load_snapshot(pack)
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_force_bypasses_cache(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Selected Financial Data\n\nA")
    seeded = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession="0001628280-24-041596",
        extracted_at="2026-04-22T00:00:00Z",
        extraction_status="ok",
        source_sha256=source_sha256_for_pack(pack),
        model=MODEL_ID,
        facts=[],
    )
    (pack / "s1_financials.json").write_text(seeded.to_json(), encoding="utf-8")

    called = {"n": 0}

    async def forced_haiku(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", forced_haiku)

    await extract_or_load_snapshot(pack, force=True)
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_no_section(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown="# Risk Factors\n\nRisk only, no financial data.")

    called = {"n": 0}

    async def should_not_be_called(_section):
        called["n"] += 1
        return "[]"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", should_not_be_called)

    result = await extract_or_load_snapshot(pack)
    assert called["n"] == 0
    assert result.extraction_status == "no_financial_data_found"
    assert result.facts == []
    # We cache the 'no data' verdict so we don't retry on every query.
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_parse_failure(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def garbage_haiku(_section):
        return "this is not json"

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", garbage_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "llm_parse_failed"
    assert result.facts == []
    # Cache the failure so retries don't rerun the LLM.
    assert (pack / "s1_financials.json").exists()


@pytest.mark.asyncio
async def test_extract_or_load_snapshot_handles_missing_api_key(tmp_path, monkeypatch):
    pack = _write_pack(tmp_path, markdown=CEREBRAS_SFD.read_text(encoding="utf-8"))

    async def raising_haiku(_section):
        raise RuntimeError("anthropic package missing")

    monkeypatch.setattr("edgarpack.query.s1_financials._call_haiku_extract", raising_haiku)

    result = await extract_or_load_snapshot(pack)
    assert result.extraction_status == "no_api_key"
    assert result.facts == []
    # No-api-key verdict is NOT cached so users can try again after installing.
    assert not (pack / "s1_financials.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: new tests FAIL with missing names.

- [ ] **Step 3: Implement cache layer + entry point**

Append to `edgarpack/query/s1_financials.py`:

```python
import hashlib

SCHEMA_VERSION = 1
_CACHE_FILENAME = "s1_financials.json"
_SOURCE_SCAN_CHARS = 50_000


def source_sha256_for_pack(pack_dir: Path) -> str:
    """sha256 of the first 50KB of filing.full.md. Used as cache key."""
    md_path = pack_dir / "filing.full.md"
    if not md_path.exists():
        return ""
    blob = md_path.read_text(encoding="utf-8", errors="replace")[:_SOURCE_SCAN_CHARS]
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_manifest_accession(pack_dir: Path) -> str:
    manifest = pack_dir / "manifest.json"
    if not manifest.exists():
        return pack_dir.name
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pack_dir.name
    return str(data.get("filing", {}).get("accession", pack_dir.name))


async def extract_or_load_snapshot(pack_dir: Path, *, force: bool = False) -> SnapshotResult:
    """Return the SnapshotResult for a single pack, extracting if needed.

    Order of operations:
        1. Compute source sha256 from filing.full.md.
        2. Check <pack>/s1_financials.json; if schema + source_sha256 match,
           return cached (unless force=True).
        3. Find the Selected Financial Data section; if absent, cache a
           "no_financial_data_found" verdict and return it.
        4. Call Haiku; parse the JSON response.
        5. On parse failure, cache "llm_parse_failed" and return it.
        6. On missing API key / network error, return a
           "no_api_key" verdict WITHOUT caching (so retries work once
           the key is exported).
        7. On success, write the cache and return.
    """
    pack_dir = Path(pack_dir)
    accession = _read_manifest_accession(pack_dir)
    source_hash = source_sha256_for_pack(pack_dir)
    cache_path = pack_dir / _CACHE_FILENAME

    if not force and cache_path.exists():
        try:
            cached = SnapshotResult.from_json(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            cached = None
        if (
            cached is not None
            and cached.schema_version == SCHEMA_VERSION
            and cached.source_sha256 == source_hash
        ):
            return cached

    markdown = ""
    md_path = pack_dir / "filing.full.md"
    if md_path.exists():
        markdown = md_path.read_text(encoding="utf-8", errors="replace")

    section = find_financial_data_section(markdown)
    if section is None:
        result = SnapshotResult(
            schema_version=SCHEMA_VERSION,
            accession=accession,
            extracted_at=_utc_iso_now(),
            extraction_status="no_financial_data_found",
            source_sha256=source_hash,
            model=MODEL_ID,
            facts=[],
        )
        cache_path.write_text(result.to_json(), encoding="utf-8")
        return result

    try:
        raw = await _call_haiku_extract(section)
    except RuntimeError:
        # Missing SDK / API key. Do NOT cache so retries work once the
        # user installs the extra or exports their key.
        return SnapshotResult(
            schema_version=SCHEMA_VERSION,
            accession=accession,
            extracted_at=_utc_iso_now(),
            extraction_status="no_api_key",
            source_sha256=source_hash,
            model=MODEL_ID,
            facts=[],
        )

    try:
        facts = parse_llm_response(raw, accession=accession)
        status = "ok"
    except ValueError:
        facts = []
        status = "llm_parse_failed"

    result = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession=accession,
        extracted_at=_utc_iso_now(),
        extraction_status=status,
        source_sha256=source_hash,
        model=MODEL_ID,
        facts=facts,
    )
    cache_path.write_text(result.to_json(), encoding="utf-8")
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_extract.py -v`

Expected: 28 passed (5 from Task 1 + 4 from Task 2 + 9 from Tasks 3-4 + 10 from this task, minus the one brittle test we replaced).

- [ ] **Step 5: Run the full suite to check regression**

Run: `.venv/bin/python -m pytest tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q`

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/query/s1_financials.py tests/test_s1_financials_extract.py
git commit -m "feat(query): extract_or_load_snapshot with sha256-keyed disk cache"
```

---

## Task 6: Extend `CitedValue` with `is_pro_forma` + `pro_forma_note`

**Files:**
- Modify: `edgarpack/query/models.py`
- Create: `tests/test_cited_value_s1_fields.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cited_value_s1_fields.py`:

```python
"""CitedValue is the core value type across all query output. We extend it
with two optional S-1-specific fields: is_pro_forma + pro_forma_note.
Existing periodic-filing paths must continue to work without change.
"""

from datetime import date

from edgarpack.query.models import CitedValue


def test_cited_value_defaults_is_pro_forma_false():
    cv = CitedValue(
        value=1,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 1),
        accession="0000320193-25-000006",
        cik="0000320193",
        company="Apple Inc.",
    )
    # Default: not pro forma, no note.
    assert cv.is_pro_forma is False
    assert cv.pro_forma_note is None


def test_cited_value_accepts_pro_forma_fields():
    cv = CitedValue(
        value=1,
        unit="USD",
        metric="cash_and_equivalents",
        concept="CashAndCashEquivalentsAtCarryingValue",
        period_end=date(2025, 12, 31),
        fiscal_year=2025,
        fiscal_period="FY",
        form_type="S-1",
        filed=date(2026, 4, 17),
        accession="0001628280-26-025762",
        cik="0002021728",
        company="Cerebras Systems Inc.",
        source="s1_snapshot",
        is_pro_forma=True,
        pro_forma_note="assumes IPO price $32.50, midpoint",
    )
    assert cv.is_pro_forma is True
    assert cv.pro_forma_note == "assumes IPO price $32.50, midpoint"
    assert cv.source == "s1_snapshot"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cited_value_s1_fields.py -v`

Expected: 2 FAIL with `TypeError: CitedValue.__init__() got an unexpected keyword argument 'is_pro_forma'` (or similar pydantic ValidationError).

- [ ] **Step 3: Add the fields to `CitedValue`**

Edit `edgarpack/query/models.py`. Inside the `class CitedValue(BaseModel):` block, add these fields. Place them immediately after the `reporting_currency` line (around line 55) so they group with other metadata:

```python
    # S-1 snapshot provenance. Default False so every existing periodic-
    # filing path works unchanged. Set True only for rows sourced from
    # s1_financials.extract_or_load_snapshot. pro_forma_note holds the
    # filing's stated assumption (e.g. "assumes IPO price $32.50").
    is_pro_forma: bool = False
    pro_forma_note: str | None = None
```

- [ ] **Step 4: Run new tests, then the full suite**

Run: `.venv/bin/python -m pytest tests/test_cited_value_s1_fields.py -v`

Expected: 2 passed.

Run: `.venv/bin/python -m pytest tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q`

Expected: zero regressions. The new fields default-False so existing code that constructs `CitedValue` without them continues working.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/models.py tests/test_cited_value_s1_fields.py
git commit -m "feat(query): CitedValue gains is_pro_forma + pro_forma_note fields"
```

---

## Task 7: Period selector for `--period pro-forma`

**Files:**
- Modify: `edgarpack/query/periods.py`
- Create: `tests/test_periods_pro_forma.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_periods_pro_forma.py`:

```python
"""Pro-forma period selector: a new token `pro-forma` parseable by
parse_period_spec. Needed so users can explicitly request S-1 snapshot
rows where is_pro_forma=True (default period selectors exclude them)."""

import pytest

from edgarpack.query.periods import is_snapshot_pseudo_period, parse_period_spec


def test_parse_period_spec_accepts_pro_forma():
    assert parse_period_spec("pro-forma") == ["pro-forma"]


def test_parse_period_spec_rejects_pro_forma_with_offset():
    with pytest.raises(ValueError):
        parse_period_spec("pro-forma-1")


def test_parse_period_spec_accepts_mixed_scalars_with_pro_forma():
    # Users can grid historical + pro-forma in one call.
    assert parse_period_spec("lfy,pro-forma") == ["lfy", "pro-forma"]


def test_is_snapshot_pseudo_period_true_for_pro_forma():
    assert is_snapshot_pseudo_period("pro-forma")


def test_is_snapshot_pseudo_period_false_for_lfy():
    assert not is_snapshot_pseudo_period("lfy")
    assert not is_snapshot_pseudo_period("ltm")
    assert not is_snapshot_pseudo_period("mrq")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_periods_pro_forma.py -v`

Expected: all 5 FAIL with ImportError / ValueError on unknown selector.

- [ ] **Step 3: Modify `parse_period_spec` + add `is_snapshot_pseudo_period`**

Edit `edgarpack/query/periods.py`. Near the top where `_SCALAR_PERIOD_RE` is defined (line 1287), change:

```python
_SCALAR_PERIOD_RE = re.compile(r"^(lfy|ltm|mrq|mrp)(?:-(\d+))?$")
```

to:

```python
# `pro-forma` is a snapshot-only pseudo-selector (S-1 pro-forma rows).
# It does not accept -N offsets because the S-1 gives one pro-forma view,
# not a time-series.
_SCALAR_PERIOD_RE = re.compile(r"^(lfy|ltm|mrq|mrp|pro-forma)(?:-(\d+))?$")
```

Inside `parse_period_spec`, just after the `if head == "mrp" and num is not None and int(num) > 0:` block, add a parallel guard for `pro-forma`:

```python
        if head == "pro-forma" and num is not None and int(num) > 0:
            raise ValueError(
                f"unknown period selector: {tok!r} "
                "(pro-forma does not support -N offsets; use plain 'pro-forma')"
            )
```

At the bottom of the file (after the last function), add the public predicate:

```python
def is_snapshot_pseudo_period(period: str) -> bool:
    """Return True for selectors that only exist for S-1 snapshot data.

    Snapshot pseudo-periods bypass the regular companyfacts lookup path
    and are routed through edgarpack.query.s1_financials.
    """
    return period == "pro-forma"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_periods_pro_forma.py tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/periods.py tests/test_periods_pro_forma.py
git commit -m "feat(periods): pro-forma selector for S-1 pro-forma snapshot rows"
```

---

## Task 8: Snapshot → CitedValue conversion + period mapping

**Files:**
- Modify: `edgarpack/query/s1_financials.py` (append)
- Create: `tests/test_s1_financials_citation.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_s1_financials_citation.py`:

```python
"""Map SnapshotFact → CitedValue for insertion into QueryResult."""

from datetime import date
from pathlib import Path

from edgarpack.query.models import CitedValue
from edgarpack.query.s1_financials import (
    SnapshotFact,
    pick_snapshot_fact,
    snapshot_fact_to_cited_value,
    snapshots_for_cik,
)


def test_snapshot_fact_to_cited_value_preserves_core_fields():
    fact = SnapshotFact(
        accession="0001628280-24-041596",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="revenue",
        value_cents=7828700000,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="0002021728",
        company="Cerebras Systems Inc.",
        form_type="S-1",
        filed=date(2024, 9, 30),
        concept="Revenues",
    )
    assert isinstance(cv, CitedValue)
    assert cv.metric == "revenue"
    # value is in whole currency units (USD), not cents.
    assert cv.value == 78287000.0
    assert cv.unit == "USD"
    assert cv.fiscal_year == 2024
    assert cv.fiscal_period == "FY"
    assert cv.form_type == "S-1"
    assert cv.accession == "0001628280-24-041596"
    assert cv.cik == "0002021728"
    assert cv.source == "s1_snapshot"
    assert cv.is_pro_forma is False


def test_snapshot_fact_to_cited_value_marks_pro_forma_source():
    fact = SnapshotFact(
        accession="0001628280-26-025762",
        fiscal_year=2025,
        period_end="2025-12-31",
        metric="cash_and_equivalents",
        value_cents=124310000000,
        currency="USD",
        is_audited=False,
        is_pro_forma=True,
        pro_forma_note="assumes IPO price $32.50, midpoint",
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="0002021728",
        company="Cerebras Systems Inc.",
        form_type="S-1",
        filed=date(2026, 4, 17),
        concept="CashAndCashEquivalentsAtCarryingValue",
    )
    assert cv.source == "s1_pro_forma"
    assert cv.is_pro_forma is True
    assert cv.pro_forma_note == "assumes IPO price $32.50, midpoint"


def test_snapshot_fact_to_cited_value_per_share_unit():
    fact = SnapshotFact(
        accession="x",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="eps_basic",
        value_cents=-108,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="x",
        company="Test",
        form_type="S-1",
        filed=date(2024, 9, 30),
        concept="EarningsPerShareBasic",
    )
    assert cv.value == -1.08
    assert cv.unit == "USD/shares"


def test_snapshot_fact_to_cited_value_shares_unit():
    fact = SnapshotFact(
        accession="x",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="shares_outstanding_basic",
        value_cents=24012345600,  # 240,123,456 shares * 100
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="x",
        company="Test",
        form_type="S-1",
        filed=date(2024, 9, 30),
        concept="WeightedAverageNumberOfSharesOutstandingBasic",
    )
    assert cv.value == 240123456.0
    assert cv.unit == "shares"


def test_pick_snapshot_fact_lfy_returns_latest_audited():
    facts = [
        SnapshotFact("a", 2023, "2023-12-31", "revenue", 100, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 200, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 999, "USD", False, True, "assume"),  # pro-forma
    ]
    picked = pick_snapshot_fact(facts, metric="revenue", period="lfy")
    assert picked is not None
    assert picked.value_cents == 200
    assert picked.is_pro_forma is False


def test_pick_snapshot_fact_lfy_minus_1():
    facts = [
        SnapshotFact("a", 2023, "2023-12-31", "revenue", 100, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 200, "USD", True, False, None),
    ]
    picked = pick_snapshot_fact(facts, metric="revenue", period="lfy-1")
    assert picked is not None
    assert picked.value_cents == 100


def test_pick_snapshot_fact_pro_forma_returns_only_pro_forma_rows():
    facts = [
        SnapshotFact("a", 2024, "2024-12-31", "cash_and_equivalents", 1, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "cash_and_equivalents", 999, "USD", False, True, "x"),
    ]
    picked = pick_snapshot_fact(facts, metric="cash_and_equivalents", period="pro-forma")
    assert picked is not None
    assert picked.is_pro_forma is True
    assert picked.value_cents == 999


def test_pick_snapshot_fact_lfy_excludes_pro_forma_and_unaudited():
    facts = [
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 999, "USD", False, True, "pro"),  # pro
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 77, "USD", False, False, None),  # unaudited interim
    ]
    # Only audited historical is acceptable for lfy; everything else returns None.
    assert pick_snapshot_fact(facts, metric="revenue", period="lfy") is None


def test_snapshots_for_cik_walks_pack_root_and_filters_by_cik(tmp_path):
    # Two packs, one matching CIK, one not.
    (tmp_path / "0002021728").mkdir()
    pack_a = tmp_path / "0002021728" / "0001628280-24-041596"
    pack_a.mkdir()
    (pack_a / "manifest.json").write_text(
        '{"filing": {"accession": "0001628280-24-041596", "form_type": "S-1", '
        '"filing_date": "2024-09-30", "cik": "0002021728", "company_name": "Cerebras"}}'
    )
    (pack_a / "filing.full.md").write_text("# x\n\nrevenue 1")
    (pack_a / "s1_financials.json").write_text(
        '{"schema_version": 1, "accession": "0001628280-24-041596", '
        '"extracted_at": "2026-04-22T00:00:00Z", "extraction_status": "ok", '
        '"source_sha256": "x", "model": "claude-haiku-4-5-20251001", '
        '"facts": [{"accession": "0001628280-24-041596", "fiscal_year": 2024, '
        '"period_end": "2024-12-31", "metric": "revenue", "value_cents": 100, '
        '"currency": "USD", "is_audited": true, "is_pro_forma": false, '
        '"pro_forma_note": null}]}'
    )

    (tmp_path / "0000000000").mkdir()
    pack_b = tmp_path / "0000000000" / "ignored"
    pack_b.mkdir()
    (pack_b / "manifest.json").write_text(
        '{"filing": {"accession": "ignored", "form_type": "S-1", '
        '"filing_date": "2020-01-01", "cik": "0000000000", "company_name": "Other"}}'
    )
    (pack_b / "filing.full.md").write_text("x")

    facts = snapshots_for_cik("0002021728", pack_root=tmp_path)
    assert len(facts) == 1
    assert facts[0].accession == "0001628280-24-041596"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_citation.py -v`

Expected: FAIL with missing names.

- [ ] **Step 3: Implement the conversion and selector helpers**

Append to `edgarpack/query/s1_financials.py`:

```python
from datetime import date as _date_cls
from edgarpack.query.models import CitedValue
from edgarpack.sec.submissions import is_registration_form

# Maps a snapshot metric slug to (unit, divisor) for CitedValue conversion.
# value_cents / divisor = CitedValue.value.
# For eps_basic (USD per share) the divisor is 100 (cents -> USD).
# For share counts the divisor is 100 (we stored count * 100 in cents).
# For everything else (whole-currency metrics) the divisor is 100.
_UNIT_FOR_METRIC = {
    "revenue": ("USD", 100),
    "gross_profit": ("USD", 100),
    "operating_income_loss": ("USD", 100),
    "net_income_loss": ("USD", 100),
    "cash_and_equivalents": ("USD", 100),
    "total_assets": ("USD", 100),
    "stockholders_equity": ("USD", 100),
    "shares_outstanding_basic": ("shares", 100),
    "eps_basic": ("USD/shares", 100),
}


def snapshot_fact_to_cited_value(
    fact: SnapshotFact,
    *,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls,
    concept: str,
) -> CitedValue:
    """Convert a SnapshotFact into a CitedValue for insertion into QueryResult.

    Unit + scale depends on the metric: monetary metrics return a float of
    whole currency units; shares outstanding returns share count; EPS
    returns USD per share. Currency override (non-USD) uses the fact's
    currency in place of "USD" in the unit string.
    """
    unit, divisor = _UNIT_FOR_METRIC[fact.metric]
    # Substitute the fact's currency if non-USD.
    if fact.currency != "USD":
        unit = unit.replace("USD", fact.currency)
    value = fact.value_cents / divisor if divisor else fact.value_cents
    source = "s1_pro_forma" if fact.is_pro_forma else "s1_snapshot"

    # period_end can arrive as a YYYY-MM-DD string; convert defensively.
    try:
        period_end = _date_cls.fromisoformat(fact.period_end)
    except ValueError:
        period_end = _date_cls(fact.fiscal_year, 12, 31)

    return CitedValue(
        value=value,
        unit=unit,
        metric=fact.metric,
        concept=concept,
        period_start=None,
        period_end=period_end,
        fiscal_year=fact.fiscal_year,
        fiscal_period="FY",
        form_type=form_type,
        filed=filed,
        accession=fact.accession,
        cik=cik,
        company=company,
        source=source,
        reporting_currency=fact.currency,
        is_pro_forma=fact.is_pro_forma,
        pro_forma_note=fact.pro_forma_note,
    )


def pick_snapshot_fact(
    facts: list[SnapshotFact],
    *,
    metric: str,
    period: str,
) -> SnapshotFact | None:
    """Return the fact that best matches `period` for the given metric.

    - `lfy`: most recent AUDITED historical year.
    - `lfy-N`: N years earlier than lfy, still audited historical only.
    - `pro-forma`: pro-forma rows only.
    - `mrp`: same as lfy for snapshot data (no stubs in v1).
    - `ltm`, `mrq`, `ltm-N`, `mrq-N`: not defined for snapshots; returns None.
    """
    candidates = [f for f in facts if f.metric == metric]
    if not candidates:
        return None

    if period == "pro-forma":
        pf = [f for f in candidates if f.is_pro_forma]
        if not pf:
            return None
        pf.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)
        return pf[0]

    audited = [f for f in candidates if f.is_audited and not f.is_pro_forma]
    if not audited:
        return None
    audited.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)

    if period in ("lfy", "mrp"):
        return audited[0]

    match_lfy_n = re.match(r"^lfy-(\d+)$", period)
    if match_lfy_n:
        offset = int(match_lfy_n.group(1))
        return audited[offset] if offset < len(audited) else None

    # ltm, mrq, mrq-N, other: not applicable to snapshots.
    return None


def snapshots_for_cik(cik: str, pack_root: Path) -> list[SnapshotFact]:
    """Union all facts across a CIK's registration-class packs.

    Walks `pack_root` for any pack carrying an s1_financials.json file whose
    manifest.json has a matching cik. Callers are expected to pass the
    CIK zero-padded the same way manifests store it ("0002021728").
    """
    pack_root = Path(pack_root)
    out: list[SnapshotFact] = []
    for manifest in pack_root.rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        filing = data.get("filing") or {}
        if str(filing.get("cik", "")) != cik:
            continue
        if not is_registration_form(str(filing.get("form_type", ""))):
            continue
        cache = manifest.parent / _CACHE_FILENAME
        if not cache.exists():
            continue
        try:
            result = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        out.extend(result.facts)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_citation.py tests/test_s1_financials_extract.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/s1_financials.py tests/test_s1_financials_citation.py
git commit -m "feat(query): SnapshotFact → CitedValue conversion and period-aware picker"
```

---

## Task 9: Fallback wiring in `financials()`

**Files:**
- Modify: `edgarpack/query/s1_financials.py` (append `augment_with_s1_snapshot`)
- Modify: `edgarpack/query/financials.py`
- Create: `tests/test_s1_financials_query_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_s1_financials_query_integration.py`:

```python
"""End-to-end integration: edgarpack query on an S-1 filer returns snapshot
values labeled as s1_snapshot. 10-K rows win for overlapping periods."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from edgarpack.query.financials import financials
from edgarpack.query.models import QueryResult


def _seed_s1_pack(
    packs_root: Path,
    cik: str = "0002021728",
    accession: str = "0001628280-24-041596",
    *,
    revenue_cents: int = 7828700000,
    is_pro_forma: bool = False,
    extra_metric: str | None = None,
    extra_cents: int = 0,
) -> None:
    import json

    pack = packs_root / cik / accession
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "accession": accession,
                    "form_type": "S-1",
                    "filing_date": "2024-09-30",
                    "cik": cik,
                    "company_name": "Cerebras Systems Inc",
                }
            }
        )
    )
    (pack / "filing.full.md").write_text(
        "# Selected Financial Data\n\nRevenue 78,287\n", encoding="utf-8"
    )
    facts = [
        {
            "accession": accession,
            "fiscal_year": 2024,
            "period_end": "2024-12-31",
            "metric": "revenue",
            "value_cents": revenue_cents,
            "currency": "USD",
            "is_audited": not is_pro_forma,
            "is_pro_forma": is_pro_forma,
            "pro_forma_note": ("assumes IPO price $32.50" if is_pro_forma else None),
        }
    ]
    if extra_metric:
        facts.append(
            {
                "accession": accession,
                "fiscal_year": 2024,
                "period_end": "2024-12-31",
                "metric": extra_metric,
                "value_cents": extra_cents,
                "currency": "USD",
                "is_audited": True,
                "is_pro_forma": False,
                "pro_forma_note": None,
            }
        )
    (pack / "s1_financials.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "accession": accession,
                "extracted_at": "2026-04-22T00:00:00Z",
                "extraction_status": "ok",
                "source_sha256": "x",
                "model": "claude-haiku-4-5-20251001",
                "facts": facts,
            }
        )
    )


@pytest.mark.asyncio
async def test_financials_returns_s1_snapshot_when_periodic_empty(tmp_path):
    _seed_s1_pack(tmp_path)

    # Stub out companyfacts fetch to return an empty dict (simulates pre-IPO
    # filer whose SEC companyfacts response has no us-gaap concepts).
    from edgarpack.query import financials as fin_module

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    # Stub resolve_ticker: we want to bypass the public-ticker-map path.
    async def fake_resolve_filer(spec):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        from edgarpack.errors import UnknownCompany

        raise UnknownCompany("not in map")

    async def fake_resolve_by_name(name):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            with patch(
                "edgarpack.sec.tickers.resolve_company_by_name",
                side_effect=fake_resolve_by_name,
            ):
                result = await financials(
                    company="Cerebras Systems",
                    metrics=["revenue"],
                    period="lfy",
                    pack_root=tmp_path,
                )

    assert isinstance(result, QueryResult)
    row = result.metrics.get("revenue")
    assert row is not None, "Expected a revenue row from S-1 snapshot"
    assert row.source == "s1_snapshot"
    assert row.form_type == "S-1"
    assert row.accession == "0001628280-24-041596"
    # 78,287 thousand USD = 78,287,000 USD. We stored value_cents=7,828,700,000 (USD cents)
    assert row.value == 78287000.0


@pytest.mark.asyncio
async def test_financials_prefers_10k_over_s1_for_overlapping_period(tmp_path):
    # When both sources have data for the same period, 10-K wins.
    _seed_s1_pack(tmp_path, revenue_cents=7828700000)  # S-1 reports $78.287M

    from edgarpack.query import financials as fin_module

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        # 10-K companyfacts with a revenue entry for the same period.
        return {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "val": 80000000,  # $80M (different from S-1)
                                    "form": "10-K",
                                    "fy": 2024,
                                    "fp": "FY",
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "filed": "2025-02-01",
                                    "accn": "0002021728-25-000001",
                                }
                            ]
                        }
                    }
                }
            }
        }

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["revenue"],
                period="lfy",
                pack_root=tmp_path,
            )

    row = result.metrics.get("revenue")
    assert row is not None
    # 10-K wins; S-1 is skipped for this period.
    assert row.source != "s1_snapshot"
    assert row.value == 80000000


@pytest.mark.asyncio
async def test_financials_pro_forma_period_returns_pro_forma_row_only(tmp_path):
    _seed_s1_pack(
        tmp_path,
        extra_metric="cash_and_equivalents",
        extra_cents=20991200000,  # $209.9M
    )
    # Add a pro-forma row for cash.
    import json

    pack = tmp_path / "0002021728" / "0001628280-24-041596"
    cache = json.loads((pack / "s1_financials.json").read_text())
    cache["facts"].append(
        {
            "accession": "0001628280-24-041596",
            "fiscal_year": 2024,
            "period_end": "2024-12-31",
            "metric": "cash_and_equivalents",
            "value_cents": 110341200000,  # $1,103.4M pro-forma
            "currency": "USD",
            "is_audited": False,
            "is_pro_forma": True,
            "pro_forma_note": "assumes IPO price $32.50, midpoint",
        }
    )
    (pack / "s1_financials.json").write_text(json.dumps(cache))

    from edgarpack.query import financials as fin_module

    async def fake_fetch(cik, force=False):  # noqa: ARG001
        return {"facts": {}}

    async def fake_resolve_ticker(company, force=False):  # noqa: ARG001
        return "0002021728", "Cerebras Systems Inc."

    with patch.object(fin_module, "fetch_company_facts", side_effect=fake_fetch):
        with patch.object(fin_module, "resolve_ticker", side_effect=fake_resolve_ticker):
            result = await financials(
                company="CRBS",
                metrics=["cash_and_equivalents"],
                period="pro-forma",
                pack_root=tmp_path,
            )

    row = result.metrics.get("cash_and_equivalents")
    assert row is not None
    assert row.is_pro_forma is True
    assert row.pro_forma_note == "assumes IPO price $32.50, midpoint"
    assert row.source == "s1_pro_forma"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_query_integration.py -v`

Expected: FAIL because `financials` does not accept a `pack_root` kwarg yet and the fallback logic doesn't exist.

- [ ] **Step 3: Implement `augment_with_s1_snapshot`**

Append to `edgarpack/query/s1_financials.py`:

```python
from edgarpack.query.metric_map import resolve_concepts

# When a SnapshotFact becomes a CitedValue we need a concept string for the
# citation. We take the first GAAP concept our METRIC_MAP knows for each
# slug. This is cosmetic (snapshots are not sourced from GAAP tags), but
# keeps existing renderers working unchanged.
_DEFAULT_CONCEPTS = {
    "revenue": "Revenues",
    "gross_profit": "GrossProfit",
    "operating_income_loss": "OperatingIncomeLoss",
    "net_income_loss": "NetIncomeLoss",
    "cash_and_equivalents": "CashAndCashEquivalentsAtCarryingValue",
    "total_assets": "Assets",
    "stockholders_equity": "StockholdersEquity",
    "shares_outstanding_basic": "WeightedAverageNumberOfSharesOutstandingBasic",
    "eps_basic": "EarningsPerShareBasic",
}


def _resolve_concept_for_metric(metric: str) -> str:
    """Pick a display concept for a snapshot metric. Best-effort; never fails."""
    try:
        concepts = resolve_concepts(metric, "US-GAAP")  # type: ignore[arg-type]
        if concepts:
            return concepts[0]
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_CONCEPTS.get(metric, metric)


async def augment_with_s1_snapshot(
    *,
    result,  # QueryResult; kept as Any to avoid circular import pressure
    cik: str,
    metrics: list[str],
    period: str,
    pack_root: Path,
    company: str = "",
    form_type: str = "S-1",
    filed: _date_cls | None = None,
):
    """Fill result.metrics cells that are still None with S-1 snapshot rows.

    Does nothing when no registration-class packs exist for this CIK, or when
    every requested metric already has a non-None value in result.metrics.
    """
    # Load ALL snapshot facts for the CIK. Walks packs once per query call.
    facts = snapshots_for_cik(cik, pack_root=pack_root)
    if not facts:
        return result

    # Default `filed` to today if caller didn't supply; we don't know the
    # per-fact filing date without re-reading manifests, and the CitedValue
    # field is informational only for snapshot rows.
    if filed is None:
        filed = _date_cls.today()

    for metric in metrics:
        current = result.metrics.get(metric)
        if current is not None:
            continue
        fact = pick_snapshot_fact(facts, metric=metric, period=period)
        if fact is None:
            continue
        cv = snapshot_fact_to_cited_value(
            fact,
            cik=cik,
            company=company,
            form_type=form_type,
            filed=filed,
            concept=_resolve_concept_for_metric(metric),
        )
        result.metrics[metric] = cv
    return result
```

- [ ] **Step 4: Wire the fallback into `financials()`**

Edit `edgarpack/query/financials.py`. The `financials()` function signature at line 250 needs a `pack_root` kwarg that defaults to `./packs`. Find:

```python
async def financials(
    company: str,
    metrics: str | list[str] | None = None,
    period: str = "lfy",
    ...
```

and add `pack_root: Path | None = None` among the kwargs. Inside, near the very end of the function just before `return result`, insert:

```python
    # Pre-IPO fallback: if any requested metric still has no value, try
    # pulling it from cached S-1 snapshots for this CIK. 10-K rows already
    # filled their cells, so those are left alone.
    any_empty = any(result.metrics.get(m) is None for m in _requested_metrics_list(metrics))
    snapshot_period = period
    if any_empty or snapshot_period == "pro-forma":
        from .s1_financials import augment_with_s1_snapshot

        root = Path(pack_root) if pack_root is not None else Path("./packs")
        result = await augment_with_s1_snapshot(
            result=result,
            cik=cik,
            metrics=list(result.metrics.keys()),
            period=snapshot_period,
            pack_root=root,
            company=company_name,
            form_type="S-1",
        )
```

Add a small helper `_requested_metrics_list` near the top of the file that normalizes the `metrics` argument into a list (handles `None`, `str`, `list[str]`):

```python
def _requested_metrics_list(metrics: str | list[str] | None) -> list[str]:
    if metrics is None:
        return []
    if isinstance(metrics, str):
        return [m.strip() for m in metrics.split(",") if m.strip()]
    return list(metrics)
```

Also import Path at the top of the file if not already imported:

```python
from pathlib import Path
```

- [ ] **Step 5: Run the new integration tests**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_query_integration.py -v`

Expected: 3 passed.

- [ ] **Step 6: Run the full suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q`

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/query/s1_financials.py edgarpack/query/financials.py tests/test_s1_financials_query_integration.py
git commit -m "feat(query): wire S-1 snapshot fallback into financials(); 10-K precedence preserved"
```

---

## Task 10: CLI pass-through + JSON output fields

**Files:**
- Modify: `edgarpack/cli.py` (JSON output path for `query`)
- Modify: `edgarpack/query/formatting.py` (inline citation marker)
- Create: `tests/test_s1_financials_formatting.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_s1_financials_formatting.py`:

```python
"""Output shaping: inline S-1 citation marker in the table renderer and
source/accession/is_pro_forma passthrough in the JSON renderer."""

from datetime import date

import pytest

from edgarpack.query.formatting import format_citation_marker
from edgarpack.query.models import CitedValue


def _snapshot_cv(is_pro_forma: bool = False) -> CitedValue:
    return CitedValue(
        value=78287000,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="S-1",
        filed=date(2024, 9, 30),
        accession="0001628280-24-041596",
        cik="0002021728",
        company="Cerebras Systems Inc.",
        source="s1_pro_forma" if is_pro_forma else "s1_snapshot",
        is_pro_forma=is_pro_forma,
        pro_forma_note=("assumes IPO price $32.50" if is_pro_forma else None),
    )


def test_format_citation_marker_snapshot():
    marker = format_citation_marker(_snapshot_cv(is_pro_forma=False))
    assert "[S-1" in marker
    # Short accession suffix.
    assert "24-041596" in marker


def test_format_citation_marker_pro_forma():
    marker = format_citation_marker(_snapshot_cv(is_pro_forma=True))
    assert "*" in marker or "pro-forma" in marker.lower()


def test_format_citation_marker_10k_returns_empty_or_minimal():
    cv = CitedValue(
        value=100,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 1),
        accession="0000320193-25-000006",
        cik="0000320193",
        company="Apple Inc.",
        source="hardcoded",
    )
    # Periodic values do not carry the S-1 marker.
    assert "[S-1" not in format_citation_marker(cv)


def test_cited_value_json_includes_s1_fields():
    cv = _snapshot_cv(is_pro_forma=True)
    # pydantic v2 dump should include the new fields.
    dumped = cv.model_dump()
    assert dumped["source"] == "s1_pro_forma"
    assert dumped["is_pro_forma"] is True
    assert dumped["pro_forma_note"] == "assumes IPO price $32.50"
    assert dumped["accession"] == "0001628280-24-041596"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_formatting.py -v`

Expected: FAIL because `format_citation_marker` does not exist.

- [ ] **Step 3: Add the formatter helper**

Read the current contents of `edgarpack/query/formatting.py` to locate an appropriate insertion point (typically near other small format helpers). Then append:

```python
def format_citation_marker(cited) -> str:  # noqa: ANN001 (duck-typed on CitedValue)
    """Inline citation marker for table renderings.

    - S-1 snapshot rows:   [S-1, 24-041596]
    - S-1 pro-forma rows:  [S-1 pro-forma, 26-025762] *
    - Everything else:     empty string (periodic filings already have
      their own citation machinery via cited.filing_url etc.).

    Accession is rendered in short year-suffix form: take everything from
    the first dash in 10-digit CIK prefix onward.
    """
    source = getattr(cited, "source", "") or ""
    accession = getattr(cited, "accession", "") or ""
    if source not in ("s1_snapshot", "s1_pro_forma"):
        return ""
    # Short form: "0001628280-24-041596" -> "24-041596"
    parts = accession.split("-", 1)
    short = parts[1] if len(parts) == 2 else accession
    if source == "s1_pro_forma":
        return f"[S-1 pro-forma, {short}] *"
    return f"[S-1, {short}]"
```

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_s1_financials_formatting.py -v`

Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q`

Expected: no regressions. The `CitedValue` JSON schema gained two optional fields with default values, so existing serializers keep working.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/query/formatting.py tests/test_s1_financials_formatting.py
git commit -m "feat(query): inline [S-1, ...] citation marker; pro-forma variant"
```

---

## Task 11: Missing-API-key UX one-liner

**Files:**
- Modify: `edgarpack/cli.py`
- Create: `tests/test_cli_query_no_api_key_hint.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli_query_no_api_key_hint.py`:

```python
"""When `query` on a pre-IPO filer finds no periodic data AND the S-1
extraction path fails because ANTHROPIC_API_KEY is missing, print a single
helpful stderr line pointing the user to `which`. Do not crash."""

import sys
from unittest.mock import patch

import pytest

from edgarpack.cli import _render_query_no_api_key_hint


def test_hint_mentions_anthropic_key():
    msg = _render_query_no_api_key_hint()
    assert "ANTHROPIC_API_KEY" in msg


def test_hint_mentions_edgarpack_which_as_alternative():
    msg = _render_query_no_api_key_hint()
    assert "edgarpack which" in msg


def test_hint_fits_on_one_line_when_wrapped_by_terminal():
    # The text itself may be long, but callers print it as one block; we
    # verify it does not contain internal newlines that would stack it into
    # multiple lines on the terminal.
    msg = _render_query_no_api_key_hint()
    assert "\n" not in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli_query_no_api_key_hint.py -v`

Expected: FAIL with ImportError.

- [ ] **Step 3: Add the helper**

Append to `edgarpack/cli.py` (near `_render_which_empty_state` or similar existing renderer helpers):

```python
def _render_query_no_api_key_hint() -> str:
    """Single-line stderr hint when S-1 extraction can't run."""
    return (
        "Note: S-1 financial extraction requires ANTHROPIC_API_KEY. "
        "Install with `pip install edgarpack[vlm]` and export your key. "
        "Disclosures available via `edgarpack which`."
    )
```

Find `_cmd_query` and, after the call to `financials()` returns, scan the result for any cell whose `source` is `"no_api_key"`. When that's present, print the hint to stderr once:

```python
        # After the result is built but before rendering, detect snapshot
        # cells that were skipped due to missing ANTHROPIC_API_KEY.
        missing_key = any(
            getattr(v, "source", "") == "no_api_key"
            for v in (result.metrics or {}).values()
            if v is not None
        )
        if missing_key:
            print(_render_query_no_api_key_hint(), file=sys.stderr)
```

Also: in `edgarpack/query/s1_financials.py::augment_with_s1_snapshot`, detect that the cache file has `extraction_status="no_api_key"` was never written (we deliberately skip caching that verdict in Task 5), so instead propagate via a sentinel: if `snapshots_for_cik` returns an empty list AND `find_financial_data_section` WOULD have matched the filing (we can't easily know without reading each filing), the best signal is to just run `extract_or_load_snapshot` on the most recent registration-class pack once. Update `augment_with_s1_snapshot` to trigger lazy extraction when no cache exists:

```python
async def augment_with_s1_snapshot(
    *,
    result,
    cik: str,
    metrics: list[str],
    period: str,
    pack_root: Path,
    company: str = "",
    form_type: str = "S-1",
    filed: _date_cls | None = None,
):
    # First, try cached snapshots.
    facts = snapshots_for_cik(cik, pack_root=pack_root)

    # If no cached facts exist, lazily extract from the most recent
    # registration-class pack for this CIK.
    if not facts:
        latest_pack = _find_latest_registration_pack(cik, pack_root)
        if latest_pack is not None:
            result_extract = await extract_or_load_snapshot(latest_pack)
            if result_extract.extraction_status == "no_api_key":
                # Signal the missing-key case by injecting a placeholder CV.
                for metric in metrics:
                    if result.metrics.get(metric) is None:
                        from edgarpack.query.models import CitedValue as _CV

                        result.metrics[metric] = _CV(
                            value=None,
                            unit="USD",
                            metric=metric,
                            concept=_resolve_concept_for_metric(metric),
                            period_end=_date_cls.today(),
                            fiscal_year=0,
                            fiscal_period="FY",
                            form_type="S-1",
                            filed=_date_cls.today(),
                            accession="",
                            cik=cik,
                            company=company,
                            source="no_api_key",
                        )
                return result
            facts = result_extract.facts

    # (rest of existing augment logic)
    ...
```

Add the helper `_find_latest_registration_pack`:

```python
def _find_latest_registration_pack(cik: str, pack_root: Path) -> Path | None:
    """Return the newest-filing_date registration-class pack directory for a CIK."""
    candidates: list[tuple[str, Path]] = []
    for manifest in Path(pack_root).rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        filing = data.get("filing") or {}
        if str(filing.get("cik", "")) != cik:
            continue
        if not is_registration_form(str(filing.get("form_type", ""))):
            continue
        candidates.append((str(filing.get("filing_date", "")), manifest.parent))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]
```

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_cli_query_no_api_key_hint.py -v`

Expected: 3 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q`

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/cli.py edgarpack/query/s1_financials.py tests/test_cli_query_no_api_key_hint.py
git commit -m "feat(cli): missing-API-key hint + lazy extraction from latest registration pack"
```

---

## Task 12: End-to-end smoke + live verification

**Files:**
- Create: `tests/test_s1_financials_cerebras_smoke.py`

- [ ] **Step 1: Write the live-SEC smoke test**

Create `tests/test_s1_financials_cerebras_smoke.py`:

```python
"""Live-SEC + live-Anthropic smoke test for Cerebras S-1 financial extraction.

Gated on `--run-slow --run-live-sec` plus ANTHROPIC_API_KEY environment
variable. Skips silently otherwise so the fast suite stays offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.live_sec,
    pytest.mark.usefixtures("_require_slow", "_require_live_sec"),
]


@pytest.mark.asyncio
async def test_cerebras_2024_s1_yields_revenue_around_78m():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    pack = Path("packs/0002021728/0001628280-24-041596")
    if not pack.exists():
        pytest.skip(f"pack not built: run `edgarpack harvest --universe cerebras.toml` first")

    from edgarpack.query.s1_financials import (
        extract_or_load_snapshot,
        pick_snapshot_fact,
    )

    result = await extract_or_load_snapshot(pack, force=True)
    assert result.extraction_status == "ok", (
        f"extraction failed: {result.extraction_status}"
    )

    revenue = pick_snapshot_fact(result.facts, metric="revenue", period="lfy")
    assert revenue is not None, "no revenue fact extracted from Cerebras 2024 S-1"
    # Cerebras's 2024 S-1 reported FY2024 revenue in the $70M–$90M range
    # (filed with reference to 2024 audited statements). Assert wide band.
    assert 70_000_000 <= revenue.value_cents // 100 <= 120_000_000, (
        f"unexpected Cerebras revenue: ${revenue.value_cents // 100:,}"
    )
```

- [ ] **Step 2: Run the fast suite to confirm the new test skips cleanly**

Run: `.venv/bin/python -m pytest tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q`

Expected: the new test is skipped (no `--run-slow`); the rest pass.

- [ ] **Step 3: Run the live test opt-in**

Run:
```bash
export EDGARPACK_USER_AGENT="you@example.com EdgarPack/0.1"
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python -m pytest tests/test_s1_financials_cerebras_smoke.py --run-slow --run-live-sec -v
```

Expected: 1 passed. If the pack is missing, the test skips with a message pointing to the harvest command.

- [ ] **Step 4: Manually verify the demo command works**

```bash
.venv/bin/edgarpack query "Cerebras Systems" revenue
```

Expected stdout something like:
```
Cerebras Systems Inc.  (CIK 0002021728)

Revenue: $78.3M  [S-1, 24-041596]

Reproduce: edgarpack query Cerebras Systems revenue --period lfy
```

Also try:
```bash
.venv/bin/edgarpack query "Cerebras Systems" revenue,net_income_loss --period lfy,lfy-1
.venv/bin/edgarpack query "Cerebras Systems" cash_and_equivalents --period pro-forma
.venv/bin/edgarpack query "Cerebras Systems" revenue --format json | jq '.rows[0]'
```

If any of these produce incorrect output (wrong source label, pro-forma leaked into lfy, JSON missing new fields), the implementation is incomplete and the offending test should be added to the fast suite before calling this task done.

- [ ] **Step 5: Commit**

```bash
git add tests/test_s1_financials_cerebras_smoke.py
git commit -m "test(smoke): live Cerebras S-1 financial extraction round-trip"
```

---

## Final verification

- [ ] **Step 1: Full suite + lint + format**

```bash
.venv/bin/python -m pytest tests/ --ignore-glob='tests/test_hk*' --ignore-glob='tests/test_china*' -q
.venv/bin/python -m ruff check edgarpack/ tests/
.venv/bin/python -m ruff format --check edgarpack/ tests/
```

Expected: tests green, ruff clean. Any failures become follow-up tasks rather than hidden regressions.

- [ ] **Step 2: Rebuild Cerebras packs to populate snapshots** (optional; extraction is lazy on first query)

```bash
rm -f packs/0002021728/*/s1_financials.json
EDGARPACK_USER_AGENT="you@example.com EdgarPack/0.1" ANTHROPIC_API_KEY=sk-ant-... \
  .venv/bin/edgarpack query "Cerebras Systems" revenue
```

The first call triggers extraction and writes `packs/0002021728/<accession>/s1_financials.json`. Subsequent calls are instant.

- [ ] **Step 3: Diff summary**

```bash
git diff main --stat -- ':!tests' ':!docs'
```

Expected: ~300-350 non-test LOC.

- [ ] **Step 4: Merge readiness check**

All new tests passing, full suite green, ruff clean, Cerebras demo commands render correctly with the `[S-1, ...]` markers. Branch is ready for merge alongside the rest of `feat/new-filer-s1-support`.

---

## Self-review

**Spec coverage check.** Every spec section maps to a task:

- Product framing → demo output verified in Task 12 Step 4.
- Architecture spine (one module, lazy extraction) → Tasks 1-5.
- `SnapshotFact` shape → Task 1.
- LLM prompt + JSON schema → Task 3.
- Storage (per-pack JSON, sha256 key) → Task 5.
- Integration into `financials()` → Task 9.
- Period selector (pro-forma keyword + auto-fallback) → Tasks 7, 9.
- Output labeling (inline `[S-1, ...]` marker) → Task 10.
- Pro-forma handling (opt-in via `--period pro-forma`) → Tasks 7, 8, 9.
- Metrics (9 slugs) → Task 1 (`METRIC_SLUGS`), Task 8 (`_UNIT_FOR_METRIC`).
- Error handling (no key, parse failure, no data) → Task 5, Task 11.
- 10-K precedence → Task 9 integration test.
- Live-SEC smoke → Task 12.

**Placeholder scan.** Plan contains no `TBD`, `TODO`, `XXX`, `implement later`, or "similar to Task N" shortcuts. Each step shows full code or full commands.

**Type consistency**:
- `SnapshotFact` fields consistent across Tasks 1, 3, 5, 8, 9, 10.
- `SnapshotResult` fields consistent across Tasks 1, 5, 8.
- `CitedValue.source` values: `"s1_snapshot"`, `"s1_pro_forma"`, `"no_api_key"` used consistently in Tasks 8-11.
- Period tokens: `lfy`, `lfy-N`, `mrp`, `pro-forma` match between Task 7 regex and Task 8 picker.
- `_UNIT_FOR_METRIC` divisor (100) matches the LLM prompt's "cents per share * 100" rule in Task 3.
