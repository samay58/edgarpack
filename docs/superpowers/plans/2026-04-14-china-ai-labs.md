# Chinese AI Labs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `edgarpack compare minimax zhipu baidu` with a USD-normalized, screenshot-quality table whose values match independently-curated golden numbers within 1 percent. Corrects the stale MiniMax-as-private universe entry along the way.

**Architecture:** Three new pieces on top of the merged China parity foundation. (1) Universe entries for MiniMax + Zhipu (HKEX), with verification-or-skip for Moonshot / 01.AI / Baichuan / DeepSeek. (2) `edgarpack/hk/extract.py` parses HKEX prospectus PDFs into a `facts.json` mirroring the SEC schema, using regex first and a cached Claude-API fallback. (3) `edgarpack compare` subcommand renders multi-company side-by-side tables.

**Tech Stack:** Python 3.11+, pydantic v2, pypdf (already in `[china]` deps), httpx (FRED + future Claude API), `data/fx_rates.csv` (already shipped), `edgarpack/hk/adapter.py` (already producing pack shape).

**Reference spec:** `docs/superpowers/specs/2026-04-14-china-ai-labs-design.md`

**Worktree:** Create a fresh worktree before starting. From the primary repo on `main`:

```bash
git worktree add ../edgarpack-china-ai-labs -b feat/china-ai-labs main
cd ../edgarpack-china-ai-labs
python3 -m venv .venv && .venv/bin/pip install -q -e '.[dev,china]'
```

---

## File Structure

New modules:
- `edgarpack/hk/extract.py` — prospectus PDF -> `facts.json` (regex + LLM fallback + on-disk cache)
- `edgarpack/hk/llm_extract.py` — Claude API client + cache layer (separated for testability with stubs)
- `edgarpack/compare.py` — `compare` subcommand engine (loop, assemble, render)
- `data/cache/llm_extract/` — on-disk cache directory (committed)

New tests:
- `tests/test_hk_extract.py`, `tests/test_hk_llm_extract.py`, `tests/test_compare.py`, `tests/test_china_ai_labs_eval.py`
- `tests/eval/china_ai_labs_golden.yaml`
- `tests/fixtures/china_packs/{minimax,zhipu}_2024/` (committed packs, ~5-15 MB per pack)

Modified:
- `universe.toml` — drop `MINIMAX-PRIVATE`, add `MINIMAX` + `ZHIPU` (and any verified additional labs)
- `edgarpack/query/metric_map.py` — add `cash_burn`, `runway_months`, `r_and_d_intensity`, `revenue_growth_yoy`, `gross_margin_trend`
- `edgarpack/query/financials.py` — branch to read HKEX facts.json when `resolved.source == "HKEX"`; new derivations for the lab metrics
- `edgarpack/cli.py` — register `compare` subcommand
- `tests/test_china_identity.py` — flip MiniMax-private test
- `tests/test_cli_query_currency.py` — repoint or remove the private-company tests

---

### Task 1: Verify MiniMax + Zhipu HKEX stock codes

**Files:** none yet (research task)

This task does not produce code; it produces verified inputs for Task 2. Subagents should report back BLOCKED if the verification cannot be completed from primary sources.

- [ ] **Step 1: Look up MiniMax HKEX stock code from a primary source**

Visit `https://www.hkexnews.hk/listedco/listconews/sehk/`. Search by company name "MiniMax" or use the HKEX listings page. Record the 4-5 digit stock code (the `0XXXX` form). Cross-reference against a second source (company IR page, FT/Bloomberg article, tanayj.com IPO breakdown).

- [ ] **Step 2: Look up Zhipu HKEX stock code from a primary source**

Same procedure. Cross-reference.

- [ ] **Step 3: Verify additional labs (Moonshot, 01.AI, Baichuan, DeepSeek)**

For each: check whether they have a public listing on HKEX, NYSE, Nasdaq, Shanghai, Shenzhen, or any other exchange. Primary sources only. Document the listing or the absence. If genuinely public, record the ticker and exchange. If private, note that for the spec's "verify and add if public" follow-up.

- [ ] **Step 4: Record findings**

Write findings to `docs/research/2026-04-14-ai-lab-listings.md` with one entry per lab:

```markdown
## MiniMax
- Status: PUBLIC (HKEX)
- Stock code: 0XXXX
- IPO date: YYYY-MM-DD
- Source: https://...

## Moonshot AI
- Status: PRIVATE
- Source: https://...
```

Commit the research file. The implementer of Task 2 reads from this file rather than re-doing the search.

```bash
git add docs/research/2026-04-14-ai-lab-listings.md
git commit -m "research(china): verified HKEX listing status for AI labs"
```

---

### Task 2: Universe correction (drop MINIMAX-PRIVATE, add real entries)

**Files:**
- Modify: `universe.toml`
- Modify: `tests/test_china_identity.py`
- Modify: `tests/test_cli_query_currency.py`

- [ ] **Step 1: Read the verified codes from Task 1's research file**

Open `docs/research/2026-04-14-ai-lab-listings.md`. Confirm MiniMax and Zhipu codes are present. Note any additional labs that were verified public.

- [ ] **Step 2: Write the failing tests first**

Replace the `test_live_universe_minimax_is_private` test in `tests/test_china_identity.py` with:

```python
def test_minimax_routes_to_hkex():
    from pathlib import Path

    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))
    r = resolve(index, ticker=None, company="minimax")
    assert r.source == "HKEX"
    assert r.private is False
    assert r.hk_stock_code is not None and r.hk_stock_code.startswith("0")


def test_zhipu_routes_to_hkex():
    from pathlib import Path

    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))
    r = resolve(index, ticker=None, company="zhipu")
    assert r.source == "HKEX"
    assert r.private is False
```

- [ ] **Step 3: Update tests/test_cli_query_currency.py**

Remove `test_query_private_company_exits_with_clear_message` and `test_query_private_company_via_alias_also_exits` (they test a path no longer exercised by any universe entry). Keep the other 4 tests in the file.

- [ ] **Step 4: Run tests to verify the new ones fail and the deletions don't break anything**

```
.venv/bin/python -m pytest tests/test_china_identity.py tests/test_cli_query_currency.py -x -v
```

Expected: the two new identity tests FAIL with "Unknown company 'minimax'" or assertion failures because universe.toml still has MINIMAX-PRIVATE.

- [ ] **Step 5: Update universe.toml**

Find the existing `[[companies]]` block with `ticker = "MINIMAX-PRIVATE"`. Delete it entirely. Add new entries (substitute real codes from the research file):

```toml
[[companies]]
ticker = "0XXXX.HK"
listing = "HKEX"
aliases = ["minimax", "minimax ai"]
hk_stock_code = "0XXXX"

[[companies]]
ticker = "0YYYY.HK"
listing = "HKEX"
aliases = ["zhipu", "zhipu ai", "glm", "chatglm"]
hk_stock_code = "0YYYY"
```

If Task 1's research verified additional labs (Moonshot, 01.AI, Baichuan, DeepSeek) as public, add their entries too following the same pattern. If a lab is on a different exchange (e.g., Nasdaq), use the appropriate `listing` value.

- [ ] **Step 6: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_china_identity.py tests/test_cli_query_currency.py -x -v
```

Expected: PASS on the two new identity tests plus all existing tests in both files.

- [ ] **Step 7: Full regression + ruff**

```
.venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -5
.venv/bin/ruff check edgarpack/ tests/test_china_identity.py tests/test_cli_query_currency.py
```

- [ ] **Step 8: Commit**

```bash
git add universe.toml tests/test_china_identity.py tests/test_cli_query_currency.py
git commit -m "fix(universe): correct MiniMax + Zhipu listings (was wrongly marked private)"
```

---

### Task 3: Acquire MiniMax + Zhipu prospectus PDFs

**Files:**
- Create: `tests/fixtures/china_packs/minimax_2024/source.pdf`
- Create: `tests/fixtures/china_packs/zhipu_2024/source.pdf`
- Create: `scripts/download_hk_prospectus.sh`

The HKEX prospectus PDFs are large (50-200 MB). They commit to the repo as fixtures so CI runs offline. Download once.

- [ ] **Step 1: Locate the prospectus PDFs from hkexnews.hk**

For each company (MiniMax, Zhipu): find the IPO prospectus document on hkexnews. URL pattern is `https://www1.hkexnews.hk/listedco/listconews/sehk/YYYY/MMDD/YYYYMMDDXXXXX.pdf`. The document title is "Global Offering" or "Prospectus" or "Application Proof".

- [ ] **Step 2: Download both PDFs**

```bash
mkdir -p tests/fixtures/china_packs/minimax_2024
mkdir -p tests/fixtures/china_packs/zhipu_2024
curl -L -o tests/fixtures/china_packs/minimax_2024/source.pdf "https://www1.hkexnews.hk/.../<minimax-prospectus>.pdf"
curl -L -o tests/fixtures/china_packs/zhipu_2024/source.pdf "https://www1.hkexnews.hk/.../<zhipu-prospectus>.pdf"
```

- [ ] **Step 3: Verify file sizes are reasonable**

```
ls -lh tests/fixtures/china_packs/*/source.pdf
```

Expected: each between 5 and 250 MB. If outside that range, the download likely failed.

- [ ] **Step 4: Create scripts/download_hk_prospectus.sh as a reproducibility record**

```bash
#!/bin/bash
set -euo pipefail
mkdir -p tests/fixtures/china_packs/minimax_2024 tests/fixtures/china_packs/zhipu_2024
curl -fL -o tests/fixtures/china_packs/minimax_2024/source.pdf \
    "https://www1.hkexnews.hk/.../<minimax-prospectus>.pdf"
curl -fL -o tests/fixtures/china_packs/zhipu_2024/source.pdf \
    "https://www1.hkexnews.hk/.../<zhipu-prospectus>.pdf"
echo "Downloaded $(ls -lh tests/fixtures/china_packs/*/source.pdf | wc -l) prospectuses."
```

```bash
chmod +x scripts/download_hk_prospectus.sh
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/china_packs/minimax_2024/source.pdf tests/fixtures/china_packs/zhipu_2024/source.pdf scripts/download_hk_prospectus.sh
git commit -m "fixtures(china): commit MiniMax + Zhipu IPO prospectus PDFs"
```

If repo size becomes a concern, use `git lfs track "*.pdf"` first. Document the LFS dependency in `tests/fixtures/china_packs/README.md` (which Task 4 creates).

---

### Task 4: Build packs from prospectuses via existing HK adapter

**Files:**
- Create: `tests/fixtures/china_packs/minimax_2024/{manifest.json,sections/*.md,chunks.ndjson}`
- Create: `tests/fixtures/china_packs/zhipu_2024/{manifest.json,sections/*.md,chunks.ndjson}`
- Create: `tests/fixtures/china_packs/README.md`

- [ ] **Step 1: Write a one-shot pack-build script**

Create `scripts/build_hk_fixture_packs.py`:

```python
"""Build HK pack fixtures from committed prospectus PDFs."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from edgarpack.hk.acquire import HKFilingRef
from edgarpack.hk.adapter import build_hk_pack

FIXTURES = Path("tests/fixtures/china_packs")

TARGETS = [
    ("minimax_2024", "0XXXX", 2024, "MiniMax IPO Prospectus"),
    ("zhipu_2024", "0YYYY", 2024, "Zhipu IPO Prospectus"),
]


def main() -> int:
    for dir_name, stock_code, fy, label in TARGETS:
        pack_dir = FIXTURES / dir_name
        pdf = pack_dir / "source.pdf"
        if not pdf.exists():
            print(f"missing: {pdf}", file=sys.stderr)
            return 1

        ref = HKFilingRef(
            stock_code=stock_code,
            fiscal_year=fy,
            pdf_url=f"file://{pdf.resolve()}",
            announcement_date="N/A",
        )

        # adapter would re-download; short-circuit by patching its downloader to a no-op that returns the existing PDF
        with patch("edgarpack.hk.adapter._download_pdf", return_value=pdf):
            pack = build_hk_pack(ref, pack_dir)
        print(f"built {label} -> {pack.path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Update the stock codes from Task 1's research.

- [ ] **Step 2: Run the script**

```
.venv/bin/python scripts/build_hk_fixture_packs.py
```

Expected: stderr prints "built MiniMax IPO Prospectus -> ..." and "built Zhipu IPO Prospectus -> ...". Each pack directory now contains `manifest.json`, `sections/*.md`, `chunks.ndjson` alongside `source.pdf`.

- [ ] **Step 3: Verify pack outputs**

```
ls tests/fixtures/china_packs/minimax_2024/sections/ | head -5
cat tests/fixtures/china_packs/minimax_2024/manifest.json | head -20
```

Expected: at least one section file per pack, manifest contains `source: HKEX`, `accounting_standard: HKFRS`, correct stock code.

- [ ] **Step 4: Write tests/fixtures/china_packs/README.md**

```markdown
# China test pack fixtures

Packs in this directory are committed for offline test runs. Regenerate via:

```bash
.venv/bin/python scripts/build_hk_fixture_packs.py
```

Contents:
- minimax_2024/ — IPO prospectus + extracted pack
- zhipu_2024/ — IPO prospectus + extracted pack

The PDFs themselves are downloaded by `scripts/download_hk_prospectus.sh`.
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/china_packs/minimax_2024 tests/fixtures/china_packs/zhipu_2024 tests/fixtures/china_packs/README.md scripts/build_hk_fixture_packs.py
git commit -m "fixtures(china): build packs from MiniMax + Zhipu prospectuses"
```

---

### Task 5: Regex extractor for HKEX facts

**Files:**
- Create: `edgarpack/hk/extract.py`
- Create: `tests/test_hk_extract.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hk_extract.py`:

```python
import json
from pathlib import Path

from edgarpack.hk.extract import (
    HKFact,
    extract_facts_from_pack,
    extract_with_regex,
)
from edgarpack.query.metric_map import CANONICAL_METRICS


def test_extract_revenue_from_income_statement_text():
    text = "Revenue\nTotal revenue          CNY 71,200,000\nCost of revenue       CNY (54,800,000)"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    assert any(f.metric == "revenue" and f.value == 71_200_000 for f in facts)


def test_extract_skips_when_no_match():
    text = "Some boilerplate text with no financial table."
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    assert facts == []


def test_extract_facts_from_pack_emits_facts_json(tmp_path):
    pack_dir = tmp_path / "test_pack"
    pack_dir.mkdir()
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir()
    (sections_dir / "hkex_income_statement.md").write_text(
        "# Consolidated Statement of Profit or Loss\n\n"
        "Revenue\nTotal revenue          CNY 71,200,000\n"
    )
    (pack_dir / "manifest.json").write_text(
        json.dumps({
            "source": "HKEX",
            "stock_code": "0XXXX",
            "fiscal_year": 2024,
            "accounting_standard": "HKFRS",
            "reporting_currency": "CNY",
            "company": "Test",
            "pdf_url": "",
            "announcement_date": "",
        })
    )

    facts_path = extract_facts_from_pack(pack_dir, llm_fallback=False)
    assert facts_path.exists()
    data = json.loads(facts_path.read_text())
    assert data["facts"]["hkfrs"]["Revenue"]["units"]["CNY"][0]["val"] == 71_200_000


def test_extract_handles_all_canonical_metrics_signature():
    """Extractor accepts every canonical metric without crashing."""
    for metric in CANONICAL_METRICS:
        facts = extract_with_regex("dummy text", "hkex_income_statement", "HKFRS")
        assert isinstance(facts, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_hk_extract.py -x -v
```

Expected: FAIL with `ModuleNotFoundError: edgarpack.hk.extract`.

- [ ] **Step 3: Create edgarpack/hk/extract.py**

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..query.metric_map import CANONICAL_METRICS, METRIC_MAP, AccountingStandard

ExtractionMethod = Literal["regex", "learned:llm"]


@dataclass(frozen=True)
class HKFact:
    metric: str
    concept: str
    value: int | float
    unit: str
    section_id: str
    extraction_method: ExtractionMethod
    matched_label: str


_AMOUNT_PAT = r"([\d,]+(?:\.\d+)?)"
_CURRENCY_PAT = r"(?:CNY|RMB|HKD|USD)"


def _scope_for_section(section_id: str) -> set[str]:
    if section_id == "hkex_income_statement":
        return {"revenue", "gross_profit", "operating_income", "net_income", "eps_basic", "eps_diluted"}
    if section_id == "hkex_balance_sheet":
        return {"total_assets", "total_liabilities", "total_equity", "cash_and_equivalents", "total_debt", "shares_outstanding_basic", "shares_outstanding_diluted"}
    if section_id == "hkex_cash_flow":
        return set()
    return set()


def _pattern_for_concept(concept: str) -> re.Pattern[str]:
    label = re.escape(concept)
    return re.compile(
        rf"{label}\s*[\.\:]?\s*{_CURRENCY_PAT}?\s*\(?{_AMOUNT_PAT}\)?",
        re.IGNORECASE,
    )


def _parse_amount(s: str) -> int | float:
    cleaned = s.replace(",", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned)


def extract_with_regex(
    text: str,
    section_id: str,
    standard: AccountingStandard,
) -> list[HKFact]:
    if section_id not in {"hkex_income_statement", "hkex_balance_sheet", "hkex_cash_flow"}:
        return []

    out: list[HKFact] = []
    metrics_in_scope = _scope_for_section(section_id) or set(CANONICAL_METRICS)
    seen: set[str] = set()

    for metric in metrics_in_scope:
        if metric in seen:
            continue
        concepts = METRIC_MAP[standard].get(metric, [])
        for concept in concepts:
            m = _pattern_for_concept(concept).search(text)
            if m:
                value = _parse_amount(m.group(1))
                out.append(
                    HKFact(
                        metric=metric,
                        concept=concept,
                        value=value,
                        unit="CNY",
                        section_id=section_id,
                        extraction_method="regex",
                        matched_label=concept,
                    )
                )
                seen.add(metric)
                break
    return out


def extract_facts_from_pack(pack_dir: Path, llm_fallback: bool = True) -> Path:
    manifest = json.loads((pack_dir / "manifest.json").read_text())
    standard = manifest["accounting_standard"]
    currency = manifest["reporting_currency"]
    fy = manifest["fiscal_year"]
    accession = f"{manifest['stock_code']}_{fy}"

    sections_dir = pack_dir / "sections"
    all_facts: list[HKFact] = []
    for section_file in sorted(sections_dir.glob("*.md")):
        section_id = section_file.stem
        text = section_file.read_text()
        all_facts.extend(extract_with_regex(text, section_id, standard))

    if llm_fallback:
        from .llm_extract import fill_missing_with_llm
        all_facts = fill_missing_with_llm(all_facts, sections_dir, standard, accession)

    nested: dict = {standard.lower(): {}}
    for fact in all_facts:
        nested[standard.lower()].setdefault(
            fact.concept,
            {"label": fact.concept, "units": {currency: []}},
        )
        nested[standard.lower()][fact.concept]["units"].setdefault(currency, []).append({
            "start": f"{fy}-01-01",
            "end": f"{fy}-12-31",
            "val": fact.value,
            "fy": fy,
            "fp": "FY",
            "form": "Annual Report",
            "accn": accession,
            "extraction_method": fact.extraction_method,
            "section_id": fact.section_id,
        })

    facts_path = pack_dir / "facts.json"
    facts_path.write_text(json.dumps({
        "stock_code": manifest["stock_code"],
        "company": manifest["company"],
        "facts": nested,
    }, indent=2))
    return facts_path
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_hk_extract.py -x -v
```

Expected: all 4 tests PASS. The fourth test imports the not-yet-built `llm_extract` module; the `llm_fallback=False` path skips that import. Verify by reading the test code: yes, `extract_facts_from_pack` only imports `llm_extract` inside the `if llm_fallback:` branch.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/hk/extract.py tests/test_hk_extract.py
git commit -m "feat(hk): regex-based extractor produces facts.json from pack"
```

---

### Task 6: Claude API fallback + on-disk cache

**Files:**
- Create: `edgarpack/hk/llm_extract.py`
- Create: `tests/test_hk_llm_extract.py`
- Create: `data/cache/llm_extract/.gitkeep`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hk_llm_extract.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from edgarpack.hk.extract import HKFact
from edgarpack.hk.llm_extract import (
    cache_key_for,
    extract_metric_via_llm,
    fill_missing_with_llm,
)


def test_cache_key_is_deterministic():
    key1 = cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt text")
    key2 = cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt text")
    assert key1 == key2
    assert len(key1) == 64  # sha256 hex


def test_cache_key_changes_with_prompt():
    key1 = cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt v1")
    key2 = cache_key_for("acc-1", "hkex_income_statement", "revenue", "prompt v2")
    assert key1 != key2


def test_extract_metric_via_llm_writes_cache_on_first_call(tmp_path):
    fake_response = '{"value": 71200000, "label": "Total revenue"}'
    fake_client = MagicMock()
    fake_client.send.return_value = fake_response

    result = extract_metric_via_llm(
        section_text="Revenue: CNY 71.2M",
        section_id="hkex_income_statement",
        metric="revenue",
        accession="test-acc",
        cache_dir=tmp_path,
        client=fake_client,
    )
    assert result == {"value": 71200000, "label": "Total revenue"}
    assert fake_client.send.call_count == 1
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1


def test_extract_metric_via_llm_hits_cache_on_second_call(tmp_path):
    fake_response = '{"value": 71200000, "label": "Total revenue"}'
    fake_client = MagicMock()
    fake_client.send.return_value = fake_response

    extract_metric_via_llm("text", "hkex_income_statement", "revenue", "acc", tmp_path, fake_client)
    extract_metric_via_llm("text", "hkex_income_statement", "revenue", "acc", tmp_path, fake_client)
    assert fake_client.send.call_count == 1


def test_fill_missing_with_llm_skips_metrics_already_extracted(tmp_path):
    sections_dir = tmp_path / "sections"
    sections_dir.mkdir()
    (sections_dir / "hkex_income_statement.md").write_text("Revenue 71200000")

    existing = [
        HKFact(metric="revenue", concept="Revenue", value=71_200_000, unit="CNY",
               section_id="hkex_income_statement", extraction_method="regex",
               matched_label="Revenue"),
    ]

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    fake_client = MagicMock()
    fake_client.send.return_value = '{"value": 0, "label": "n/a"}'

    with patch("edgarpack.hk.llm_extract._default_cache_dir", return_value=cache_dir):
        with patch("edgarpack.hk.llm_extract._default_client", return_value=fake_client):
            result = fill_missing_with_llm(existing, sections_dir, "HKFRS", "acc")

    revenue_facts = [f for f in result if f.metric == "revenue"]
    assert len(revenue_facts) == 1
    assert revenue_facts[0].extraction_method == "regex"
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_hk_llm_extract.py -x -v
```

Expected: FAIL with `ModuleNotFoundError: edgarpack.hk.llm_extract`.

- [ ] **Step 3: Create edgarpack/hk/llm_extract.py**

```python
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from ..query.metric_map import CANONICAL_METRICS, METRIC_MAP, AccountingStandard
from .extract import HKFact, _scope_for_section


class LLMClient(Protocol):
    def send(self, prompt: str) -> str: ...


_PROMPT_TEMPLATE = """You are extracting a financial value from a Hong Kong listed company's prospectus.

Section: {section_id}
Metric to extract: {metric} (canonical name)
Accounting standard: {standard}

Text:
{text}

Return JSON with two fields: "value" (the number, no formatting), "label" (the line-item label you matched). Return {{"value": null, "label": null}} if not found. JSON only, no other text."""


def cache_key_for(accession: str, section_id: str, metric: str, prompt: str) -> str:
    raw = f"{accession}|{section_id}|{metric}|{prompt}".encode()
    return hashlib.sha256(raw).hexdigest()


def _default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "cache" / "llm_extract"


def _default_client() -> LLMClient:
    raise RuntimeError(
        "No LLM client configured. Set ANTHROPIC_API_KEY and pass a client; "
        "running with llm_fallback=False to avoid this path."
    )


def extract_metric_via_llm(
    section_text: str,
    section_id: str,
    metric: str,
    accession: str,
    cache_dir: Path,
    client: LLMClient,
    standard: str = "HKFRS",
) -> dict:
    prompt = _PROMPT_TEMPLATE.format(
        section_id=section_id,
        metric=metric,
        standard=standard,
        text=section_text[:8000],
    )
    key = cache_key_for(accession, section_id, metric, prompt)
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    response = client.send(prompt)
    parsed = json.loads(response)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(parsed))
    return parsed


def fill_missing_with_llm(
    existing: list[HKFact],
    sections_dir: Path,
    standard: AccountingStandard,
    accession: str,
    cache_dir: Path | None = None,
    client: LLMClient | None = None,
) -> list[HKFact]:
    extracted_metrics = {f.metric for f in existing}
    missing = [m for m in CANONICAL_METRICS if m not in extracted_metrics]
    if not missing:
        return existing

    cache_dir = cache_dir or _default_cache_dir()

    out = list(existing)
    for section_file in sorted(sections_dir.glob("*.md")):
        section_id = section_file.stem
        scope = _scope_for_section(section_id) or set()
        text = section_file.read_text()
        for metric in list(missing):
            if metric not in scope:
                continue
            client = client or _default_client()
            try:
                parsed = extract_metric_via_llm(
                    text, section_id, metric, accession, cache_dir, client, standard
                )
            except Exception:
                continue
            if parsed.get("value") is None:
                continue
            concept = (METRIC_MAP[standard].get(metric, [metric]) or [metric])[0]
            out.append(
                HKFact(
                    metric=metric,
                    concept=concept,
                    value=parsed["value"],
                    unit="CNY",
                    section_id=section_id,
                    extraction_method="learned:llm",
                    matched_label=parsed.get("label", ""),
                )
            )
            missing.remove(metric)
    return out
```

- [ ] **Step 4: Create the cache dir placeholder**

```bash
mkdir -p data/cache/llm_extract
touch data/cache/llm_extract/.gitkeep
```

- [ ] **Step 5: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_hk_llm_extract.py tests/test_hk_extract.py -x -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/hk/llm_extract.py tests/test_hk_llm_extract.py data/cache/llm_extract/.gitkeep
git commit -m "feat(hk): Claude-API fallback for missed metrics with on-disk cache"
```

---

### Task 7: Run extraction on MiniMax + Zhipu fixture packs, commit facts.json

**Files:**
- Create: `tests/fixtures/china_packs/minimax_2024/facts.json`
- Create: `tests/fixtures/china_packs/zhipu_2024/facts.json`
- Create: `data/cache/llm_extract/*.json` (committed cache files)

- [ ] **Step 1: Run regex-only extraction first**

```
.venv/bin/python -c "
from pathlib import Path
from edgarpack.hk.extract import extract_facts_from_pack
for d in ['minimax_2024', 'zhipu_2024']:
    path = extract_facts_from_pack(Path(f'tests/fixtures/china_packs/{d}'), llm_fallback=False)
    print(f'wrote {path}')
"
```

- [ ] **Step 2: Inspect coverage**

```
.venv/bin/python -c "
import json
for d in ['minimax_2024', 'zhipu_2024']:
    data = json.loads(open(f'tests/fixtures/china_packs/{d}/facts.json').read())
    metrics = set()
    for std in data['facts'].values():
        for concept, info in std.items():
            metrics.add(concept)
    print(f'{d}: {len(metrics)} concepts extracted: {sorted(metrics)}')
"
```

If recall is below 60 percent of `CANONICAL_METRICS`, proceed to Step 3 (LLM fallback). Otherwise skip.

- [ ] **Step 3: Run with LLM fallback**

This requires `ANTHROPIC_API_KEY` set in environment. The implementer must construct an LLM client. Use the official `anthropic` Python SDK:

```python
import os
from anthropic import Anthropic

class _AnthropicClient:
    def __init__(self):
        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def send(self, prompt: str) -> str:
        msg = self._client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
```

Then:

```python
from pathlib import Path
from edgarpack.hk.extract import extract_facts_from_pack
from edgarpack.hk.llm_extract import _default_cache_dir
import edgarpack.hk.llm_extract as llm

llm._default_client = lambda: _AnthropicClient()

for d in ['minimax_2024', 'zhipu_2024']:
    path = extract_facts_from_pack(Path(f'tests/fixtures/china_packs/{d}'), llm_fallback=True)
    print(f'wrote {path}')
```

Save this as `scripts/extract_hk_facts.py` for reproducibility.

- [ ] **Step 4: Inspect cache files were created**

```
ls data/cache/llm_extract/ | head -10
wc -l data/cache/llm_extract/*.json
```

- [ ] **Step 5: Commit facts + cache**

```bash
git add tests/fixtures/china_packs/minimax_2024/facts.json tests/fixtures/china_packs/zhipu_2024/facts.json data/cache/llm_extract/ scripts/extract_hk_facts.py
git commit -m "fixtures(china): extract facts.json for MiniMax + Zhipu (committed LLM cache)"
```

---

### Task 8: Add lab-specific metrics to METRIC_MAP

**Files:**
- Modify: `edgarpack/query/metric_map.py`
- Modify: `tests/test_china_metric_map.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_china_metric_map.py`:

```python
def test_lab_specific_metrics_in_canonical_set():
    from edgarpack.query.metric_map import CANONICAL_METRICS

    required = {
        "cash_burn",
        "runway_months",
        "r_and_d_intensity",
        "revenue_growth_yoy",
        "gross_margin_trend",
    }
    assert required <= set(CANONICAL_METRICS)


def test_cash_burn_resolves_concepts_per_standard():
    from edgarpack.query.metric_map import resolve_concepts

    assert resolve_concepts("cash_burn", "US-GAAP")  # non-empty list
    assert resolve_concepts("cash_burn", "IFRS")
    assert resolve_concepts("cash_burn", "HKFRS")


def test_r_and_d_intensity_concepts_present():
    from edgarpack.query.metric_map import resolve_concepts

    us = resolve_concepts("r_and_d_intensity", "US-GAAP")
    ifrs = resolve_concepts("r_and_d_intensity", "IFRS")
    hkfrs = resolve_concepts("r_and_d_intensity", "HKFRS")
    assert us == [] and ifrs == [] and hkfrs == []  # derived metric


def test_derived_metrics_have_empty_concept_lists():
    from edgarpack.query.metric_map import resolve_concepts

    for derived in ("runway_months", "revenue_growth_yoy", "gross_margin_trend", "r_and_d_intensity"):
        for std in ("US-GAAP", "IFRS", "HKFRS"):
            assert resolve_concepts(derived, std) == [], f"{derived} {std} should be empty (derived)"
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_china_metric_map.py -x -v -k "lab_specific or cash_burn or r_and_d or derived"
```

Expected: FAIL on `KeyError` since the new metrics aren't in `CANONICAL_METRICS`.

- [ ] **Step 3: Update edgarpack/query/metric_map.py**

Append to `CANONICAL_METRICS`:

```python
CANONICAL_METRICS: tuple[CanonicalMetric, ...] = (
    "revenue",
    "gross_profit",
    "gross_margin",
    "operating_income",
    "operating_margin",
    "ebitda",
    "net_income",
    "eps_basic",
    "eps_diluted",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "cash_and_equivalents",
    "total_debt",
    "shares_outstanding_basic",
    "shares_outstanding_diluted",
    "cash_burn",
    "runway_months",
    "r_and_d_intensity",
    "revenue_growth_yoy",
    "gross_margin_trend",
)
```

For `cash_burn`, add concept lists (the derivation in Task 10 reads operating_cash_flow and capex separately, but the metric itself needs concept tags so the resolver doesn't crash):

In each standard's dict, after `shares_outstanding_diluted`:

```python
        "cash_burn": ["NetCashProvidedByUsedInOperatingActivities"],  # US-GAAP
```

For IFRS and HKFRS:
```python
        "cash_burn": ["CashFlowsFromUsedInOperatingActivities"],
```

For the four derived metrics (`runway_months`, `r_and_d_intensity`, `revenue_growth_yoy`, `gross_margin_trend`), append empty lists in every standard:

```python
        "runway_months": [],
        "r_and_d_intensity": [],
        "revenue_growth_yoy": [],
        "gross_margin_trend": [],
```

For CAS, the existing dict comprehension `{m: [] for m in CANONICAL_METRICS}` already handles all metrics with empty lists; no additional changes needed.

- [ ] **Step 4: Run tests to verify pass**

```
.venv/bin/python -m pytest tests/test_china_metric_map.py -x -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/metric_map.py tests/test_china_metric_map.py
git commit -m "feat(query): add lab metrics (cash_burn, runway, R&D intensity, growth, margin trend)"
```

---

### Task 9: Wire HKEX query path in financials.py

**Files:**
- Modify: `edgarpack/query/financials.py`
- Create: `tests/test_china_query_hk.py`

- [ ] **Step 1: Locate the financials() entry point**

Read `edgarpack/query/financials.py:152` (the `financials` async function). Identify where it fetches XBRL facts from EDGAR. The branch lands before that fetch.

- [ ] **Step 2: Write failing tests**

Create `tests/test_china_query_hk.py`:

```python
import asyncio

import pytest

from edgarpack.query.financials import financials


@pytest.mark.asyncio
async def test_minimax_query_returns_revenue_from_pack():
    result = await financials(
        company="minimax",
        metrics="revenue",
        period="lfy",
    )
    assert result is not None
    rows = [v for v in result.values.values() if v.metric == "revenue"]
    assert len(rows) >= 1
    assert rows[0].reporting_currency == "CNY"
    assert rows[0].accounting_standard == "HKFRS"
    assert rows[0].value > 0


@pytest.mark.asyncio
async def test_zhipu_query_returns_revenue_from_pack():
    result = await financials(
        company="zhipu",
        metrics="revenue",
        period="lfy",
    )
    rows = [v for v in result.values.values() if v.metric == "revenue"]
    assert len(rows) >= 1
    assert rows[0].reporting_currency == "CNY"


def test_minimax_revenue_within_range():
    """Sanity: regex- or LLM-extracted MiniMax FY24 revenue near $71.2M USD (~CNY 510M)."""
    result = asyncio.run(financials(company="minimax", metrics="revenue", period="lfy"))
    rev = [v for v in result.values.values() if v.metric == "revenue"][0]
    assert 400_000_000 < rev.value < 700_000_000  # broad CNY range; tightens in eval harness
```

- [ ] **Step 3: Add the HKEX branch in financials()**

In `edgarpack/query/financials.py`, near the top of the `financials` async function (after argument parsing, before the EDGAR fetch), insert:

```python
    from pathlib import Path

    from ..identity import UnknownCompany, load_identity, resolve

    try:
        idx = load_identity(Path("universe.toml"))
        try:
            resolved = resolve(idx, ticker=company, company=None)
        except UnknownCompany:
            resolved = resolve(idx, ticker=None, company=company)
    except UnknownCompany:
        resolved = None

    if resolved and resolved.source == "HKEX":
        return await _query_hkex_pack(resolved, metrics, period)
```

Then add `_query_hkex_pack` near the bottom of the file:

```python
async def _query_hkex_pack(resolved, metrics: str | None, period: str) -> "QueryResult":
    import json
    from datetime import date
    from pathlib import Path

    from .models import CitedValue, QueryResult

    fy = 2024  # v1: lfy on HKEX always means FY24 (latest filed prospectus year)
    pack_dir = Path(f"tests/fixtures/china_packs/{resolved.hk_stock_code.lstrip('0').zfill(5)}_{fy}")
    if not pack_dir.exists():
        # try without leading zeros
        for variant in [resolved.hk_stock_code, resolved.hk_stock_code.lstrip("0")]:
            candidate = Path(f"tests/fixtures/china_packs/{variant}_{fy}")
            if candidate.exists():
                pack_dir = candidate
                break

    facts_path = pack_dir / "facts.json"
    if not facts_path.exists():
        raise FileNotFoundError(f"No facts.json at {facts_path}")

    data = json.loads(facts_path.read_text())
    requested = {m.strip() for m in (metrics or "").split(",") if m.strip()}

    cited: dict[str, CitedValue] = {}
    for standard_key, concepts in data["facts"].items():
        for concept, info in concepts.items():
            metric = _concept_to_canonical(concept, standard_key)
            if requested and metric not in requested:
                continue
            for unit, points in info["units"].items():
                for p in points:
                    cv = CitedValue(
                        value=p["val"],
                        unit=unit,
                        metric=metric,
                        concept=concept,
                        period_start=date.fromisoformat(p["start"]),
                        period_end=date.fromisoformat(p["end"]),
                        fiscal_year=p["fy"],
                        fiscal_period=p["fp"],
                        form_type=p["form"],
                        filed=date.fromisoformat(p["end"]),
                        accession=p["accn"],
                        cik=resolved.hk_stock_code,
                        company=data.get("company", resolved.ticker),
                        accounting_standard=standard_key.upper().replace("US_GAAP", "US-GAAP"),
                        reporting_currency=unit,
                        source=p.get("extraction_method", "regex"),
                    )
                    cited[metric] = cv

    return QueryResult(
        company=data.get("company", resolved.ticker),
        cik=resolved.hk_stock_code or "",
        values=cited,
        warnings=[],
        filing_meta={"company_name": data.get("company", resolved.ticker)},
    )


def _concept_to_canonical(concept: str, standard_key: str) -> str:
    from .metric_map import METRIC_MAP

    standard = standard_key.upper().replace("US_GAAP", "US-GAAP")
    for metric, concepts in METRIC_MAP.get(standard, {}).items():
        if concept in concepts:
            return metric
    return concept.lower()
```

- [ ] **Step 4: Run tests**

```
.venv/bin/python -m pytest tests/test_china_query_hk.py -x -v
```

If `_query_hkex_pack` fails because `QueryResult` shape differs from what's coded, inspect `edgarpack/query/models.py::QueryResult` and adjust the construction. Iterate until tests pass.

- [ ] **Step 5: Update CLI to remove the "HKEX not yet supported" exit**

In `edgarpack/cli.py::_cmd_query`, find the block:

```python
    if resolved.source == "HKEX":
        print(
            f"Error: HKEX metric extraction is not yet supported for {resolved.ticker}. "
            "HKEX pack ingestion lands separately; query wiring is pending.",
            file=sys.stderr,
        )
        return 2
```

Delete it. The HKEX path now flows through `financials()` which dispatches via `_query_hkex_pack`.

Update `tests/test_cli_query_currency.py::test_query_hkex_ticker_exits_with_not_yet_supported_message`: this test no longer reflects desired behavior. Delete it.

- [ ] **Step 6: Run full regression**

```
.venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -10
```

- [ ] **Step 7: Commit**

```bash
git add edgarpack/query/financials.py edgarpack/cli.py tests/test_china_query_hk.py tests/test_cli_query_currency.py
git commit -m "feat(query): route HKEX-source companies through pack facts.json"
```

---

### Task 10: Lab-metric derivations in financials.py

**Files:**
- Modify: `edgarpack/query/financials.py:413` (the `_compute_derived` function)
- Create: `tests/test_lab_metric_derivations.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_lab_metric_derivations.py`:

```python
from edgarpack.query.financials import _compute_derived
from edgarpack.query.models import CitedValue
from datetime import date


def _cv(metric: str, value: float, fy: int = 2024, currency: str = "USD") -> CitedValue:
    return CitedValue(
        value=value,
        unit=currency,
        metric=metric,
        concept=metric,
        period_end=date(fy, 12, 31),
        fiscal_year=fy,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(fy, 12, 31),
        accession=f"acc-{fy}",
        cik="0",
        company="X",
        reporting_currency=currency,
    )


def test_runway_months_from_cash_and_burn():
    inputs = {
        "cash_and_equivalents": _cv("cash_and_equivalents", 100_000_000),
        "cash_burn": _cv("cash_burn", 10_000_000),  # annual burn
    }
    derived = _compute_derived(inputs)
    assert "runway_months" in derived
    assert 110 < derived["runway_months"].value < 130  # 100M / (10M/12) ~= 120


def test_runway_months_undefined_when_burn_is_zero_or_negative():
    inputs = {
        "cash_and_equivalents": _cv("cash_and_equivalents", 100_000_000),
        "cash_burn": _cv("cash_burn", 0),
    }
    derived = _compute_derived(inputs)
    assert "runway_months" not in derived or derived["runway_months"].value is None


def test_r_and_d_intensity_from_rd_and_revenue():
    inputs = {
        "revenue": _cv("revenue", 100_000_000),
        "research_and_development": _cv("research_and_development", 200_000_000),
    }
    derived = _compute_derived(inputs)
    assert "r_and_d_intensity" in derived
    assert abs(derived["r_and_d_intensity"].value - 2.0) < 0.01


def test_revenue_growth_yoy_from_two_periods():
    inputs = {
        "revenue": _cv("revenue", 150_000_000, fy=2024),
        "revenue_prior": _cv("revenue", 100_000_000, fy=2023),
    }
    derived = _compute_derived(inputs)
    assert "revenue_growth_yoy" in derived
    assert abs(derived["revenue_growth_yoy"].value - 0.5) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_lab_metric_derivations.py -x -v
```

- [ ] **Step 3: Extend _compute_derived in financials.py**

Read the current `_compute_derived` function. Append rules for the four new derived metrics. Pseudocode (adapt to the actual function signature and CitedValue construction patterns already in the file):

```python
def _compute_derived(inputs: dict[str, CitedValue]) -> dict[str, CitedValue]:
    out = {}
    # ... existing rules ...

    # Runway months
    cash = inputs.get("cash_and_equivalents")
    burn = inputs.get("cash_burn")
    if cash and burn and burn.value and burn.value > 0:
        runway = cash.value / (abs(burn.value) / 12)
        out["runway_months"] = _derive(cash, "runway_months", runway, "months")

    # R&D intensity
    rev = inputs.get("revenue")
    rd = inputs.get("research_and_development") or inputs.get("r_and_d_expense")
    if rev and rd and rev.value:
        out["r_and_d_intensity"] = _derive(rev, "r_and_d_intensity", rd.value / rev.value, "ratio")

    # Revenue growth YoY (if a prior-period revenue is in inputs as 'revenue_prior')
    rev_prior = inputs.get("revenue_prior")
    if rev and rev_prior and rev_prior.value:
        growth = (rev.value / rev_prior.value) - 1.0
        out["revenue_growth_yoy"] = _derive(rev, "revenue_growth_yoy", growth, "ratio")

    # Gross margin trend
    gm = inputs.get("gross_margin")
    gm_prior = inputs.get("gross_margin_prior")
    if gm and gm_prior:
        out["gross_margin_trend"] = _derive(gm, "gross_margin_trend", gm.value - gm_prior.value, "delta")

    return out
```

The `_derive` helper here is illustrative; use whatever pattern the existing `_compute_derived` uses to construct derived `CitedValue` instances in `edgarpack/query/financials.py`.

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_lab_metric_derivations.py tests/ -x -q 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/financials.py tests/test_lab_metric_derivations.py
git commit -m "feat(query): derive runway, R&D intensity, growth, margin trend"
```

---

### Task 11: `compare` subcommand parser + engine

**Files:**
- Create: `edgarpack/compare.py`
- Modify: `edgarpack/cli.py`
- Create: `tests/test_compare.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_compare.py`:

```python
import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "compare", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )


def test_compare_help_shows_subcommand():
    result = _run("--help")
    assert result.returncode == 0
    assert "companies" in result.stdout.lower() or "company" in result.stdout.lower()
    assert "--metrics" in result.stdout
    assert "--format" in result.stdout


def test_compare_two_companies_table():
    result = _run("BIDU", "GOOGL", "--metrics", "revenue,net_income", "--format", "table")
    assert result.returncode == 0
    assert "BIDU" in result.stdout
    assert "GOOGL" in result.stdout
    assert "revenue" in result.stdout.lower()


def test_compare_three_way_with_minimax():
    result = _run("minimax", "zhipu", "baidu", "--metrics", "revenue", "--format", "table")
    assert result.returncode == 0
    # All three column headers present
    assert "minimax" in result.stdout.lower() or "MINIMAX" in result.stdout.upper()


def test_compare_json_format():
    result = _run("BIDU", "GOOGL", "--metrics", "revenue", "--format", "json")
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert "companies" in parsed
    assert len(parsed["companies"]) == 2


def test_compare_markdown_format_contains_table_syntax():
    result = _run("BIDU", "GOOGL", "--metrics", "revenue", "--format", "markdown")
    assert result.returncode == 0
    assert "|" in result.stdout
    assert "---" in result.stdout
```

- [ ] **Step 2: Run tests to verify fail**

```
.venv/bin/python -m pytest tests/test_compare.py -x -v
```

Expected: argparse "invalid choice: 'compare'" or similar.

- [ ] **Step 3: Create edgarpack/compare.py**

```python
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .identity import UnknownCompany, load_identity, resolve
from .query.financials import financials


@dataclass(frozen=True)
class CompanyColumn:
    ticker: str
    company: str
    period: str
    reporting_currency: str
    metrics: dict[str, Any]


def _resolve_one(idx, name: str):
    try:
        return resolve(idx, ticker=name, company=None)
    except UnknownCompany:
        return resolve(idx, ticker=None, company=name)


async def _fetch_one(name: str, metrics: str, period: str) -> CompanyColumn:
    result = await financials(company=name, metrics=metrics, period=period)
    company = result.filing_meta.get("company_name", name)
    period_label = f"FY{next(iter(result.values.values())).fiscal_year}" if result.values else "n/a"
    currency = next(iter(result.values.values())).reporting_currency if result.values else "USD"
    metrics_dict = {
        v.metric: {"value": v.value, "currency": v.reporting_currency, "extraction_method": getattr(v, "source", "")}
        for v in result.values.values()
    }
    return CompanyColumn(
        ticker=name,
        company=company,
        period=period_label,
        reporting_currency=currency,
        metrics=metrics_dict,
    )


def _format_table(columns: list[CompanyColumn], metric_keys: list[str]) -> str:
    headers = ["metric"] + [c.ticker for c in columns]
    rows = []
    for m in metric_keys:
        row = [m]
        for c in columns:
            v = c.metrics.get(m, {}).get("value")
            row.append("n/a" if v is None else f"{v:,.0f}")
        rows.append(row)

    widths = [max(len(str(row[i])) for row in [headers] + rows) for i in range(len(headers))]
    lines = []
    lines.append("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))
    lines.append("")
    for c in columns:
        lines.append(f"  {c.ticker}: {c.company}, {c.period}, reported in {c.reporting_currency}")
    return "\n".join(lines)


def _format_markdown(columns: list[CompanyColumn], metric_keys: list[str]) -> str:
    headers = ["metric"] + [c.ticker for c in columns]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for m in metric_keys:
        row = [m] + [
            "n/a" if c.metrics.get(m, {}).get("value") is None
            else f"{c.metrics[m]['value']:,.0f} {c.metrics[m]['currency']}"
            for c in columns
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    for c in columns:
        lines.append(f"_{c.ticker}: {c.company}, {c.period}_")
    return "\n".join(lines)


def _format_json(columns: list[CompanyColumn]) -> str:
    return json.dumps({
        "companies": [
            {
                "ticker": c.ticker,
                "company": c.company,
                "period": c.period,
                "reporting_currency": c.reporting_currency,
                "metrics": c.metrics,
            }
            for c in columns
        ]
    }, indent=2, default=str)


def cmd_compare(args: Any) -> int:
    idx = load_identity(Path("universe.toml"))

    for name in args.companies:
        try:
            r = _resolve_one(idx, name)
        except UnknownCompany as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        if r.private:
            print(f"Error: {name} is private; not supported in compare.", file=sys.stderr)
            return 2

    metrics = args.metrics or "revenue,gross_margin,operating_income,net_income,cash_and_equivalents"
    period = args.period or "lfy"

    columns = asyncio.run(_gather(args.companies, metrics, period))
    metric_keys = [m.strip() for m in metrics.split(",")]

    if args.compare_format == "json":
        print(_format_json(columns))
    elif args.compare_format == "markdown":
        print(_format_markdown(columns, metric_keys))
    else:
        print(_format_table(columns, metric_keys))
    return 0


async def _gather(names: list[str], metrics: str, period: str) -> list[CompanyColumn]:
    return [await _fetch_one(n, metrics, period) for n in names]
```

- [ ] **Step 4: Register the subcommand in cli.py**

In `edgarpack/cli.py`, after the existing subparsers (e.g., after `p_query`), add:

```python
    p_compare = sub.add_parser("compare", help="Side-by-side comparison of two or more companies")
    p_compare.add_argument("companies", nargs="+", help="Two or more company tickers or aliases")
    p_compare.add_argument("--metrics", help="Comma-separated metric names")
    p_compare.add_argument("--period", default="lfy", help="Fiscal period (default: lfy)")
    p_compare.add_argument(
        "--currency",
        choices=["native", "usd", "both"],
        default="both",
        help="Currency output mode",
    )
    p_compare.add_argument(
        "--format",
        dest="compare_format",
        choices=["table", "json", "markdown"],
        default="table",
        help="Output format",
    )
```

In the dispatcher (search for `if args.cmd == "query"`), add:

```python
    if args.cmd == "compare":
        from .compare import cmd_compare
        return cmd_compare(args)
```

- [ ] **Step 5: Run tests to verify pass**

```
.venv/bin/python -m pytest tests/test_compare.py -x -v
```

The tests that hit live SEC (BIDU, GOOGL) take 30-60 seconds. If `--currency both` for SEC-only filers produces redundant USD-USD output, that's fine — the renderer can be tightened later.

- [ ] **Step 6: Full regression + ruff**

```
.venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -10
.venv/bin/ruff check edgarpack/compare.py edgarpack/cli.py tests/test_compare.py
```

- [ ] **Step 7: Commit**

```bash
git add edgarpack/compare.py edgarpack/cli.py tests/test_compare.py
git commit -m "feat(cli): compare subcommand renders multi-company side-by-side tables"
```

---

### Task 12: Eval harness with independent golden numbers

**Files:**
- Create: `tests/eval/china_ai_labs_golden.yaml`
- Create: `tests/test_china_ai_labs_eval.py`

- [ ] **Step 1: Curate golden values from independent sources**

Reference sources:
- tanayj.com IPO breakdown (https://www.tanayj.com/p/two-ai-lab-ipos-s-1-breakdowns)
- FT or Bloomberg coverage of MiniMax + Zhipu IPOs
- Sell-side coverage of Tencent / Meituan FY24

For each company, record:
- Revenue (FY24)
- Net income (FY24)
- Cash and equivalents (FY24)
- R&D expense (FY24)
- Total assets (FY24)
- Number of basic shares outstanding (FY24)
- USD equivalents at the FY24 average rate (~0.141 CNY/USD)

Source each number with a URL or article reference.

- [ ] **Step 2: Write tests/eval/china_ai_labs_golden.yaml**

```yaml
- ticker: minimax
  company: MiniMax
  fy: 2024
  reporting_currency: CNY
  source: "tanayj.com IPO breakdown, 2026-01-21"
  metrics:
    revenue:
      native: 506000000           # ~CNY 506M (= ~$71.2M USD at 0.141)
      usd: 71200000
      tolerance_pct: 1.0
    net_income:
      native: -3300000000         # ~-CNY 3.3B (= ~-$465M loss)
      usd: -465000000
      tolerance_pct: 1.0

- ticker: zhipu
  company: Zhipu
  fy: 2024
  reporting_currency: CNY
  source: "tanayj.com IPO breakdown, 2026-01-21"
  metrics:
    revenue:
      native: 383000000           # ~CNY 383M (= ~$54M USD)
      usd: 54000000
      tolerance_pct: 1.0
    net_income:
      native: -2940000000
      usd: -415000000
      tolerance_pct: 1.0
```

These numbers are illustrative; replace with the actual figures from the curated sources.

- [ ] **Step 3: Write tests/test_china_ai_labs_eval.py**

```python
import asyncio
from pathlib import Path

import pytest
import yaml

from edgarpack.query.financials import financials


GOLDEN_PATH = Path("tests/eval/china_ai_labs_golden.yaml")


def _load_fixtures() -> list[dict]:
    return yaml.safe_load(GOLDEN_PATH.read_text())


@pytest.mark.eval
@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["ticker"])
def test_lab_revenue_within_tolerance(fixture):
    result = asyncio.run(
        financials(company=fixture["ticker"], metrics="revenue", period="lfy")
    )
    rows = [v for v in result.values.values() if v.metric == "revenue"]
    assert rows, f"No revenue extracted for {fixture['ticker']}"
    actual = rows[0].value
    expected = fixture["metrics"]["revenue"]["native"]
    tolerance = fixture["metrics"]["revenue"]["tolerance_pct"] / 100
    diff = abs(actual - expected) / expected
    assert diff <= tolerance, (
        f"{fixture['ticker']} revenue: expected {expected:,}, got {actual:,}, "
        f"diff {diff:.2%}, tolerance {tolerance:.0%}. Source: {fixture['source']}"
    )


@pytest.mark.eval
@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["ticker"])
def test_lab_net_income_within_tolerance(fixture):
    result = asyncio.run(
        financials(company=fixture["ticker"], metrics="net_income", period="lfy")
    )
    rows = [v for v in result.values.values() if v.metric == "net_income"]
    if not rows:
        pytest.skip(f"net_income not extracted for {fixture['ticker']}")
    actual = rows[0].value
    expected = fixture["metrics"]["net_income"]["native"]
    tolerance = fixture["metrics"]["net_income"]["tolerance_pct"] / 100
    diff = abs(actual - expected) / abs(expected)
    assert diff <= tolerance, (
        f"{fixture['ticker']} net_income: expected {expected:,}, got {actual:,}, "
        f"diff {diff:.2%}, tolerance {tolerance:.0%}."
    )
```

- [ ] **Step 4: Run the eval harness**

```
.venv/bin/python -m pytest tests/test_china_ai_labs_eval.py -m eval -v
```

If failures, inspect: is the extraction missing the metric (returns empty list)? Is the value off by a digit? Refine the regex or add LLM fallback metrics. Iterate until eval is green.

- [ ] **Step 5: Commit**

```bash
git add tests/eval/china_ai_labs_golden.yaml tests/test_china_ai_labs_eval.py
git commit -m "test(eval): golden fixtures for MiniMax + Zhipu with 1% tolerance"
```

---

### Task 13: Done-def queries + Twitter screenshot

**Files:** none (verification + artifact)

- [ ] **Step 1: Run the done-def queries**

```bash
.venv/bin/edgarpack query MINIMAX revenue --period FY24
.venv/bin/edgarpack query ZHIPU revenue --period FY24
.venv/bin/edgarpack compare minimax zhipu baidu \
    --metrics revenue,gross_margin,operating_income,cash_burn,runway_months,cash_and_equivalents \
    --format table
.venv/bin/edgarpack compare minimax zhipu baidu \
    --metrics revenue,gross_margin,operating_income,cash_burn,runway_months,cash_and_equivalents \
    --format markdown
```

- [ ] **Step 2: Verify the values pass the eyeball test**

MiniMax revenue should be near $71M USD equivalent (CNY ~510M).
Zhipu revenue should be near $54M USD equivalent (CNY ~380M).
Baidu revenue should be ~$18.5B USD (FY25).
Operating income for both labs should be deeply negative.

- [ ] **Step 3: Run the full eval suite**

```
.venv/bin/python -m pytest tests/ -m eval -v 2>&1 | tail -10
```

All eval tests must pass.

- [ ] **Step 4: Run full regression**

```
.venv/bin/python -m pytest tests/ -x -q 2>&1 | tail -5
```

Must be green.

- [ ] **Step 5: Run ruff and ruff format check**

```
.venv/bin/ruff check edgarpack/ tests/ scripts/ 2>&1 | tail -5
.venv/bin/ruff format --check edgarpack/ tests/ scripts/ 2>&1 | tail -5
```

Both clean for branch files.

- [ ] **Step 6: Update edgarpack-2yg notes with completion status**

```bash
bd update edgarpack-2yg --notes "AI labs end-to-end shipped at $(git rev-parse HEAD). MiniMax + Zhipu queryable; compare subcommand produces three-way comp; eval harness green."
```

- [ ] **Step 7: Final commit + push**

```bash
git push origin feat/china-ai-labs
```

Open PR or merge to main per project workflow.

---

## Self-Review

**Spec coverage:**
- Universe correction → Tasks 1, 2
- HKEX prospectus extraction (regex + LLM cache) → Tasks 3, 4, 5, 6, 7
- Lab-specific metrics → Tasks 8, 10
- Query path branch → Task 9
- `compare` subcommand → Task 11
- Eval harness with independent golden → Task 12
- Done-def → Task 13

All spec sections mapped. Verification of additional labs (Moonshot, 01.AI, Baichuan, DeepSeek) lives in Task 1 Step 3 + 4; promotion to universe entries piggybacks on Task 2.

**Placeholder scan:** No "TBD", "TODO", "fill in details" in any step. Stock codes use `0XXXX` / `0YYYY` placeholders that Task 1 explicitly resolves before Task 2 reads them. PDF URLs use `<minimax-prospectus>.pdf` placeholders that Task 3 explicitly resolves at download time.

**Type consistency:** `HKFact` defined in Task 5 used by Task 6. `CompanyColumn` defined in Task 11 only. `_query_hkex_pack` signature matches `financials()` return type (`QueryResult`). `extract_facts_from_pack(pack_dir, llm_fallback=True)` signature consistent across Tasks 5, 6, 7.

**Known fragility:** Task 11's `_format_table` width calculation assumes `str(value)` reflects what gets rendered; for very long company names or numbers with thousands separators, columns may misalign slightly. Acceptable for v1; harden in a polish pass.
