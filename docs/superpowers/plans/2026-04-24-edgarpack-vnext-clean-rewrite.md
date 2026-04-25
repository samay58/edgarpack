# EdgarPack vNext Clean Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first clean-rewrite vertical slice as `edgarpack_next` plus `edgarpack-next`: deterministic SEC packs, cited analyst facts, simple derived metrics, S-1 selected-financial-data extraction, CLI commands, and a minimal API wrapper.

**Architecture:** Build a new package beside the old implementation. Core services own behavior; CLI and API are adapters. Old `edgarpack` code may be imported only for reviewed leaf SEC transport/discovery utilities and HTML cleaning primitives.

**Tech Stack:** Python 3.11+, Pydantic v2, Typer, Rich, FastAPI for the minimal API, pytest, ruff, scoped mypy for `edgarpack_next`.

---

## Safety Rules

- Work in an isolated git worktree and branch.
- Do not replace the existing `edgarpack` command in this plan.
- Do not call old `edgarpack.cli`, old pack builders, old query orchestrators, old renderers, old sectionizer, old period engine, or old self-heal code from vNext.
- Write the failing test before production code for each behavior.
- Run the exact focused command after each task.
- Commit after each green task.
- Stop if fixture source material for NVDA, AAPL, or Cerebras is insufficient.

## File Map

- Modify: `pyproject.toml` — add Typer/Rich runtime dependencies, API/dev dependencies, and `edgarpack-next` entry point.
- Create: `edgarpack_next/__init__.py` — package metadata.
- Create: `edgarpack_next/cli.py` — Typer CLI adapter.
- Create: `edgarpack_next/api.py` — FastAPI adapter.
- Create: `edgarpack_next/models.py` — public Pydantic contracts for filings, artifacts, citations, metric results, API results.
- Create: `edgarpack_next/sec/source.py` — vNext wrappers over approved old SEC leaf utilities.
- Create: `edgarpack_next/sec/html.py` — vNext source-to-markdown and section extraction primitives.
- Create: `edgarpack_next/artifacts/writer.py` — deterministic artifact writer.
- Create: `edgarpack_next/core/filings.py` — filings use case.
- Create: `edgarpack_next/core/pack.py` — pack build use case.
- Create: `edgarpack_next/core/cite.py` — cited fact use case.
- Create: `edgarpack_next/core/audit.py` — artifact/citation audit use case.
- Create: `edgarpack_next/metrics/registry.py` — explicit metric registry.
- Create: `edgarpack_next/metrics/resolve.py` — direct and search-gated concept resolution.
- Create: `edgarpack_next/metrics/search.py` — experimental unverified concept search lane.
- Create: `edgarpack_next/metrics/derive.py` — derived metric engine.
- Create: `edgarpack_next/sec/s1_tables.py` — fixture-backed S-1 selected-financial-data parser.
- Create: `edgarpack_next/testing/fixtures.py` — fixture loader used by tests and fixture-mode services.
- Create: `scripts/capture_vnext_fixtures.py` — live SEC fixture capture helper for frozen companyfacts.
- Create: `tests/fixtures/vnext/index.json` — fixture index pointing to real source material.
- Create: `tests/vnext/` test suite.
- Update: `.reforge/09_agent_operating_manual.md` — record vNext build rules once implementation decisions are real.

## Task 0: Isolated Worktree And Baseline

**Files:**
- No code files.

- [ ] **Step 1: Verify current status**

Run:

```bash
git status --short --untracked-files=all
```

Expected: current dirty state is visible, including pre-existing `uv.lock` and planning artifacts. Do not reset or clean it.

- [ ] **Step 2: Check worktree directory convention**

Run:

```bash
ls -d .worktrees 2>/dev/null || true
ls -d worktrees 2>/dev/null || true
grep -i "worktree.*director" CLAUDE.md 2>/dev/null || true
git check-ignore -q .worktrees && echo ".worktrees ignored"
```

Expected: either `.worktrees ignored` prints, or the command exits nonzero.

If `.worktrees` is not ignored, add exactly this line to `.gitignore`:

```gitignore
.worktrees/
```

Then commit only `.gitignore`:

```bash
git add .gitignore
git commit -m "chore: ignore local worktrees"
```

- [ ] **Step 3: Create the worktree**

Run:

```bash
git worktree add .worktrees/vnext-clean-rewrite -b reforge/vnext-clean-rewrite
cd .worktrees/vnext-clean-rewrite
```

Expected: new worktree on branch `reforge/vnext-clean-rewrite`.

- [ ] **Step 4: Install baseline dependencies**

Run:

```bash
uv pip install -e ".[dev,china]"
```

Expected: install succeeds. If `uv.lock` changes, keep the diff and report it; this rebuild intentionally changes dependency posture.

- [ ] **Step 5: Baseline checks**

Run:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest tests/test_layer_zero.py -q
./.venv/bin/ruff check .
```

Expected: focused baseline test and ruff pass. If unrelated failures appear before vNext edits, report them before continuing.

## Task 1: Bootstrap vNext Package, Dependencies, And CLI Contract

**Files:**
- Modify: `pyproject.toml`
- Create: `edgarpack_next/__init__.py`
- Create: `edgarpack_next/cli.py`
- Create: `tests/vnext/test_cli_contract.py`

- [ ] **Step 1: Write the failing CLI contract test**

Create `tests/vnext/test_cli_contract.py`:

```python
from __future__ import annotations

from typer.testing import CliRunner

from edgarpack_next.cli import app


def test_cli_exposes_evidence_verbs() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("filings", "pack", "cite", "audit"):
        assert command in result.output


def test_version_flag_is_available() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "edgarpack-next" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_cli_contract.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'edgarpack_next'` or missing `typer` if dependencies have not been added yet.

- [ ] **Step 3: Add dependencies and entry point**

Modify `pyproject.toml`:

```toml
dependencies = [
    "pydantic>=2.0",
    "rich>=13.7",
    "tiktoken>=0.7",
    "typer>=0.12",
]

[project.optional-dependencies]
api = [
    "fastapi>=0.111",
    "uvicorn>=0.30",
]
china = [
    "fastapi>=0.111",
    "uvicorn>=0.30",
    "httpx>=0.27",
    "psycopg[binary]>=3.2",
    "pypdf>=4.0",
    "pyyaml>=6.0",
]
sse = [
    "pymupdf4llm>=0.0.17",
    "pypinyin>=0.53",
    "httpx>=0.27",
]
vlm = ["anthropic>=0.40"]
dev = [
    "fastapi>=0.111",
    "httpx>=0.27",
    "mypy>=1.10",
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "uvicorn>=0.30",
    "psycopg[binary]>=3.2",
    "pypdf>=4.0",
]

[project.scripts]
edgarpack = "edgarpack.cli:app"
edgarpack-next = "edgarpack_next.cli:main"
```

Run:

```bash
uv pip install -e ".[dev,api,china]"
```

Expected: install succeeds. `uv.lock` may update because Typer/Rich are new runtime dependencies.

- [ ] **Step 4: Add minimal CLI implementation**

Create `edgarpack_next/__init__.py`:

```python
"""Clean-rewrite vNext package for EdgarPack."""

from __future__ import annotations

__version__ = "0.1.0-alpha.0"
```

Create `edgarpack_next/cli.py`:

```python
from __future__ import annotations

import typer

from . import __version__

app = typer.Typer(
    add_completion=False,
    help="Evidence-first filing compiler for primary-source-backed company research.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"edgarpack-next {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show edgarpack-next version.",
    ),
) -> None:
    return None


@app.command()
def filings(company: str, form: str = "10-K", limit: int = 10) -> None:
    """Inspect available filings for a company."""
    raise typer.Exit(code=2)


@app.command()
def pack(company: str, form: str = "10-K", out: str = "packs-next") -> None:
    """Build deterministic pack artifacts from primary filings."""
    raise typer.Exit(code=2)


@app.command()
def cite(company: str, metrics: str, period: str = "lfy") -> None:
    """Return cited facts and diagnostics."""
    raise typer.Exit(code=2)


@app.command()
def audit(path: str) -> None:
    """Inspect pack and citation integrity."""
    raise typer.Exit(code=2)


def main() -> None:
    app()
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_cli_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add pyproject.toml uv.lock edgarpack_next/__init__.py edgarpack_next/cli.py tests/vnext/test_cli_contract.py
git commit -m "feat(vnext): bootstrap clean rewrite CLI"
```

## Task 2: Public Models And Citation Invariants

**Files:**
- Create: `edgarpack_next/models.py`
- Create: `tests/vnext/test_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/vnext/test_models.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from edgarpack_next.models import (
    CitationStatus,
    CitedFact,
    CompanyIdentity,
    DerivedFact,
    FilingIdentity,
    MissingFact,
)


def test_cited_fact_requires_source_provenance() -> None:
    company = CompanyIdentity(cik="0001045810", ticker="NVDA", name="NVIDIA CORP")
    filing = FilingIdentity(
        cik="0001045810",
        accession="0001045810-26-000021",
        form="10-K",
        filing_date="2026-02-25",
        primary_document="nvda-20260125.htm",
    )

    fact = CitedFact(
        metric="revenue",
        value=130497000000,
        unit="USD",
        period="lfy",
        status=CitationStatus.CITED,
        company=company,
        filing=filing,
        concept="Revenues",
        source_url="https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm",
        evidence_ref="us-gaap:Revenues@0001045810-26-000021",
    )

    assert fact.status is CitationStatus.CITED
    assert fact.source_url.startswith("https://www.sec.gov/")


def test_cited_fact_rejects_missing_source_url() -> None:
    company = CompanyIdentity(cik="0001045810", ticker="NVDA", name="NVIDIA CORP")
    filing = FilingIdentity(
        cik="0001045810",
        accession="0001045810-26-000021",
        form="10-K",
        filing_date="2026-02-25",
        primary_document="nvda-20260125.htm",
    )

    with pytest.raises(ValidationError):
        CitedFact(
            metric="revenue",
            value=130497000000,
            unit="USD",
            period="lfy",
            status=CitationStatus.CITED,
            company=company,
            filing=filing,
            concept="Revenues",
            source_url="",
            evidence_ref="us-gaap:Revenues@0001045810-26-000021",
        )


def test_missing_derived_fact_reports_missing_components() -> None:
    missing = MissingFact(
        metric="free_cash_flow",
        period="lfy",
        status=CitationStatus.MISSING,
        reason="missing required component",
        missing_components=("capital_expenditures",),
    )
    derived = DerivedFact(
        metric="free_cash_flow",
        period="lfy",
        status=CitationStatus.MISSING,
        formula="operating_cash_flow - capital_expenditures",
        components=[],
        missing=missing,
    )

    assert derived.value is None
    assert derived.missing is not None
    assert derived.missing.missing_components == ("capital_expenditures",)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_models.py -q
```

Expected: FAIL with imports missing from `edgarpack_next.models`.

- [ ] **Step 3: Implement models**

Create `edgarpack_next/models.py`:

```python
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CitationStatus(StrEnum):
    CITED = "cited"
    UNVERIFIED_CITED = "unverified_cited"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class CompanyIdentity(BaseModel):
    cik: str
    ticker: str = ""
    name: str

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value: str) -> str:
        digits = value.strip().lstrip("0")
        if not digits.isdigit():
            raise ValueError("CIK must contain digits")
        return digits.zfill(10)


class FilingIdentity(BaseModel):
    cik: str
    accession: str
    form: str
    filing_date: str
    primary_document: str
    period_of_report: str | None = None

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value: str) -> str:
        digits = value.strip().lstrip("0")
        if not digits.isdigit():
            raise ValueError("CIK must contain digits")
        return digits.zfill(10)


class SectionArtifact(BaseModel):
    section_id: str
    title: str
    path: str
    sha256: str


class PackManifest(BaseModel):
    schema_version: Literal["vnext.1"] = "vnext.1"
    company: CompanyIdentity
    filing: FilingIdentity
    artifacts: dict[str, str]
    sections: list[SectionArtifact]
    warnings: tuple[str, ...] = ()
    reserved_artifacts: tuple[str, ...] = ("llms.txt",)
    content_sha256: str


class CitedFact(BaseModel):
    metric: str
    value: int | float | str
    unit: str
    period: str
    status: CitationStatus
    company: CompanyIdentity
    filing: FilingIdentity
    concept: str
    source_url: str
    evidence_ref: str
    match_reason: str | None = None
    match_score: float | None = None

    @model_validator(mode="after")
    def enforce_provenance(self) -> CitedFact:
        if self.status in {CitationStatus.CITED, CitationStatus.UNVERIFIED_CITED}:
            if not self.source_url.strip():
                raise ValueError("cited values require source_url")
            if not self.evidence_ref.strip():
                raise ValueError("cited values require evidence_ref")
            if not self.concept.strip():
                raise ValueError("cited values require concept")
        if self.status is CitationStatus.UNVERIFIED_CITED:
            if not self.match_reason:
                raise ValueError("unverified cited values require match_reason")
            if self.match_score is None:
                raise ValueError("unverified cited values require match_score")
        return self


class MissingFact(BaseModel):
    metric: str
    period: str
    status: Literal[CitationStatus.MISSING, CitationStatus.UNSUPPORTED]
    reason: str
    missing_components: tuple[str, ...] = ()


class DerivedFact(BaseModel):
    metric: str
    period: str
    status: CitationStatus
    formula: str
    components: list[CitedFact]
    value: int | float | None = None
    unit: str | None = None
    missing: MissingFact | None = None

    @model_validator(mode="after")
    def enforce_derived_status(self) -> DerivedFact:
        if self.status is CitationStatus.CITED:
            if self.value is None:
                raise ValueError("cited derived facts require value")
            if not self.components:
                raise ValueError("cited derived facts require components")
        if self.status is CitationStatus.MISSING and self.missing is None:
            raise ValueError("missing derived facts require missing diagnostics")
        for component in self.components:
            if component.status is not CitationStatus.CITED:
                raise ValueError("derived facts require curated cited components")
        return self


MetricFact = CitedFact | DerivedFact | MissingFact


class BuildResult(BaseModel):
    manifest_path: Path
    manifest: PackManifest


class AuditResult(BaseModel):
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack_next/models.py tests/vnext/test_models.py
git commit -m "feat(vnext): add public evidence models"
```

## Task 3: Fixture Index And Loader

**Files:**
- Create: `tests/fixtures/vnext/index.json`
- Create: `edgarpack_next/testing/fixtures.py`
- Create: `tests/vnext/test_fixture_loader.py`

- [ ] **Step 1: Write failing fixture loader test**

Create `tests/vnext/test_fixture_loader.py`:

```python
from __future__ import annotations

from edgarpack_next.testing.fixtures import load_fixture_index


def test_fixture_index_names_canonical_sources() -> None:
    index = load_fixture_index()

    assert set(index) == {"nvda_10k_2026", "aapl_10k_2025", "cerebras_s1_2024"}
    assert index["nvda_10k_2026"].ticker == "NVDA"
    assert index["aapl_10k_2025"].ticker == "AAPL"
    assert index["cerebras_s1_2024"].form == "S-1"


def test_fixture_source_files_exist() -> None:
    index = load_fixture_index()

    for fixture in index.values():
        assert fixture.source_path.exists(), fixture.source_path
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_fixture_loader.py -q
```

Expected: FAIL with missing `edgarpack_next.testing.fixtures`.

- [ ] **Step 3: Add fixture index**

Create `tests/fixtures/vnext/index.json`:

```json
{
  "nvda_10k_2026": {
    "ticker": "NVDA",
    "cik": "0001045810",
    "company_name": "NVIDIA CORP",
    "accession": "0001045810-26-000021",
    "form": "10-K",
    "filing_date": "2026-02-25",
    "primary_document": "nvda-20260125.htm",
    "source_path": "benchmarks/artifacts/NVDA_10K_0001045810-26-000021/raw.htm",
    "companyfacts_path": "tests/fixtures/vnext/companyfacts/nvda_0001045810.json"
  },
  "aapl_10k_2025": {
    "ticker": "AAPL",
    "cik": "0000320193",
    "company_name": "Apple Inc.",
    "accession": "0000320193-25-000079",
    "form": "10-K",
    "filing_date": "2025-10-31",
    "primary_document": "aapl-20250927.htm",
    "source_path": "benchmarks/artifacts/AAPL_10K_0000320193-25-000079/raw.htm",
    "companyfacts_path": "tests/fixtures/vnext/companyfacts/aapl_0000320193.json"
  },
  "cerebras_s1_2024": {
    "ticker": "",
    "cik": "0002021728",
    "company_name": "Cerebras Systems Inc.",
    "accession": "0001628280-24-041596",
    "form": "S-1",
    "filing_date": "2024-09-30",
    "primary_document": "cerebras-s1.md",
    "source_path": "tests/fixtures/cerebras_s1_sample.md",
    "selected_financial_data_path": "tests/fixtures/cerebras_selected_financial_data.md"
  }
}
```

- [ ] **Step 4: Add loader**

Create `edgarpack_next/testing/__init__.py`:

```python
"""Testing helpers for vNext."""
```

Create `edgarpack_next/testing/fixtures.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_INDEX = REPO_ROOT / "tests" / "fixtures" / "vnext" / "index.json"


class VNextFixture(BaseModel):
    ticker: str
    cik: str
    company_name: str
    accession: str
    form: str
    filing_date: str
    primary_document: str
    source_path: Path
    companyfacts_path: Path | None = None
    selected_financial_data_path: Path | None = None

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> VNextFixture:
        data = dict(payload)
        for key in ("source_path", "companyfacts_path", "selected_financial_data_path"):
            value = data.get(key)
            if isinstance(value, str):
                data[key] = REPO_ROOT / value
        return cls.model_validate(data)


def load_fixture_index(path: Path = FIXTURE_INDEX) -> dict[str, VNextFixture]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: VNextFixture.from_json(value) for key, value in raw.items()}
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_fixture_loader.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add edgarpack_next/testing tests/fixtures/vnext/index.json tests/vnext/test_fixture_loader.py
git commit -m "test(vnext): add canonical fixture index"
```

## Task 4: Capture Frozen Companyfacts Fixtures

**Files:**
- Create: `scripts/capture_vnext_fixtures.py`
- Create: `tests/vnext/test_companyfacts_fixtures.py`
- Generate: `tests/fixtures/vnext/companyfacts/nvda_0001045810.json`
- Generate: `tests/fixtures/vnext/companyfacts/aapl_0000320193.json`

- [ ] **Step 1: Write failing companyfacts fixture test**

Create `tests/vnext/test_companyfacts_fixtures.py`:

```python
from __future__ import annotations

import json

from edgarpack_next.testing.fixtures import load_fixture_index


def test_mature_filer_companyfacts_fixtures_exist_and_have_us_gaap() -> None:
    index = load_fixture_index()

    for fixture_id in ("nvda_10k_2026", "aapl_10k_2025"):
        fixture = index[fixture_id]
        assert fixture.companyfacts_path is not None
        payload = json.loads(fixture.companyfacts_path.read_text(encoding="utf-8"))
        assert payload["cik"] == int(fixture.cik)
        assert "facts" in payload
        assert "us-gaap" in payload["facts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_companyfacts_fixtures.py -q
```

Expected: FAIL because companyfacts fixture files do not exist.

- [ ] **Step 3: Add capture script**

Create `scripts/capture_vnext_fixtures.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from edgarpack.sec.xbrl import fetch_company_facts


TARGETS = {
    "nvda": "0001045810",
    "aapl": "0000320193",
}


CONCEPTS = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "LongTermDebtCurrent",
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "DebtCurrent",
    "CommonStocksIncludingAdditionalPaidInCapital",
    "EntityCommonStockSharesOutstanding",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "ResearchAndDevelopmentExpense",
}


def _trim_companyfacts(payload: dict[str, Any]) -> dict[str, Any]:
    facts = payload.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    trimmed_concepts: dict[str, Any] = {}
    for concept in sorted(CONCEPTS):
        if concept in us_gaap:
            trimmed_concepts[concept] = us_gaap[concept]
    return {
        "cik": payload.get("cik"),
        "entityName": payload.get("entityName"),
        "facts": {"us-gaap": trimmed_concepts},
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/vnext/companyfacts"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name, cik in TARGETS.items():
        payload = await fetch_company_facts(cik, force=args.force)
        trimmed = _trim_companyfacts(payload)
        path = args.out / f"{name}_{cik}.json"
        path.write_text(json.dumps(trimmed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Capture fixtures from live SEC**

Run:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python scripts/capture_vnext_fixtures.py --force
```

Expected:

```text
wrote tests/fixtures/vnext/companyfacts/nvda_0001045810.json
wrote tests/fixtures/vnext/companyfacts/aapl_0000320193.json
```

If the command fails because `EDGARPACK_USER_AGENT` is not set, export a real user agent and rerun.

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_companyfacts_fixtures.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add scripts/capture_vnext_fixtures.py tests/vnext/test_companyfacts_fixtures.py tests/fixtures/vnext/companyfacts
git commit -m "test(vnext): freeze companyfacts fixtures"
```

## Task 5: SEC Source Wrapper For Filings And Companyfacts

**Files:**
- Create: `edgarpack_next/sec/__init__.py`
- Create: `edgarpack_next/sec/source.py`
- Create: `edgarpack_next/core/filings.py`
- Create: `tests/vnext/test_sec_source.py`

- [ ] **Step 1: Write failing source tests**

Create `tests/vnext/test_sec_source.py`:

```python
from __future__ import annotations

import pytest

from edgarpack_next.core.filings import FilingsService
from edgarpack_next.sec.source import FixtureSourceProvider
from edgarpack_next.testing.fixtures import load_fixture_index


@pytest.mark.asyncio
async def test_fixture_provider_lists_filings_without_network() -> None:
    provider = FixtureSourceProvider(load_fixture_index())
    service = FilingsService(provider)

    filings = await service.list_filings("NVDA", form="10-K", limit=5)

    assert len(filings) == 1
    assert filings[0].accession == "0001045810-26-000021"
    assert filings[0].form == "10-K"


@pytest.mark.asyncio
async def test_fixture_provider_reads_companyfacts() -> None:
    provider = FixtureSourceProvider(load_fixture_index())

    facts = await provider.companyfacts("0001045810")

    assert "us-gaap" in facts["facts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_sec_source.py -q
```

Expected: FAIL with missing `edgarpack_next.sec.source`.

- [ ] **Step 3: Implement source wrappers**

Create `edgarpack_next/sec/__init__.py`:

```python
"""SEC source adapters for vNext."""
```

Create `edgarpack_next/sec/source.py`:

```python
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from edgarpack.sec.submissions import list_filings as old_list_filings
from edgarpack.sec.tickers import resolve_company as old_resolve_company
from edgarpack.sec.client import get_client as old_get_client
from edgarpack.sec.xbrl import fetch_company_facts as old_fetch_company_facts

from edgarpack_next.models import CompanyIdentity, FilingIdentity
from edgarpack_next.testing.fixtures import VNextFixture


class SourceProvider(Protocol):
    async def resolve_company(self, company: str) -> CompanyIdentity: ...
    async def list_filings(self, company: str, form: str, limit: int) -> list[FilingIdentity]: ...
    async def companyfacts(self, cik: str) -> dict[str, object]: ...
    async def source_text(self, filing: FilingIdentity) -> str: ...


class FixtureSourceProvider:
    def __init__(self, fixtures: Mapping[str, VNextFixture]):
        self.fixtures = dict(fixtures)

    async def resolve_company(self, company: str) -> CompanyIdentity:
        needle = company.strip().upper()
        for fixture in self.fixtures.values():
            if needle in {fixture.ticker.upper(), fixture.cik, fixture.company_name.upper()}:
                return CompanyIdentity(
                    cik=fixture.cik,
                    ticker=fixture.ticker,
                    name=fixture.company_name,
                )
        raise ValueError(f"unknown fixture company: {company}")

    async def list_filings(self, company: str, form: str, limit: int) -> list[FilingIdentity]:
        identity = await self.resolve_company(company)
        wanted = form.upper()
        matches: list[FilingIdentity] = []
        for fixture in self.fixtures.values():
            if fixture.cik == identity.cik and fixture.form.upper() == wanted:
                matches.append(
                    FilingIdentity(
                        cik=fixture.cik,
                        accession=fixture.accession,
                        form=fixture.form,
                        filing_date=fixture.filing_date,
                        primary_document=fixture.primary_document,
                    )
                )
        return matches[:limit]

    async def companyfacts(self, cik: str) -> dict[str, object]:
        normalized = cik.lstrip("0").zfill(10)
        for fixture in self.fixtures.values():
            if fixture.cik == normalized and fixture.companyfacts_path is not None:
                return json.loads(fixture.companyfacts_path.read_text(encoding="utf-8"))
        raise ValueError(f"no companyfacts fixture for CIK {normalized}")

    async def source_text(self, filing: FilingIdentity) -> str:
        for fixture in self.fixtures.values():
            if fixture.accession == filing.accession:
                return fixture.source_path.read_text(encoding="utf-8", errors="replace")
        raise ValueError(f"no source fixture for accession {filing.accession}")

    def selected_financial_data_path(self, filing: FilingIdentity) -> Path | None:
        for fixture in self.fixtures.values():
            if fixture.accession == filing.accession:
                return fixture.selected_financial_data_path
        return None


class LiveSECSourceProvider:
    async def resolve_company(self, company: str) -> CompanyIdentity:
        cik, ticker, name = await old_resolve_company(company)
        return CompanyIdentity(cik=cik, ticker=ticker, name=name)

    async def list_filings(self, company: str, form: str, limit: int) -> list[FilingIdentity]:
        identity = await self.resolve_company(company)
        filings = await old_list_filings(identity.cik, form_type=form, limit=limit)
        return [
            FilingIdentity(
                cik=item.cik,
                accession=item.accession,
                form=item.form_type,
                filing_date=item.filing_date.isoformat(),
                primary_document=item.primary_document,
                period_of_report=item.period_of_report.isoformat() if item.period_of_report else None,
            )
            for item in filings
        ]

    async def companyfacts(self, cik: str) -> dict[str, object]:
        return await old_fetch_company_facts(cik)

    async def source_text(self, filing: FilingIdentity) -> str:
        cik_int = str(int(filing.cik))
        accession_nodash = filing.accession.replace("-", "")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
            f"{accession_nodash}/{filing.primary_document}"
        )
        client = await old_get_client()
        raw, _headers = await client.fetch(url)
        return raw.decode("utf-8", errors="replace")
```

Create `edgarpack_next/core/__init__.py`:

```python
"""Core vNext use cases."""
```

Create `edgarpack_next/core/filings.py`:

```python
from __future__ import annotations

from edgarpack_next.models import FilingIdentity
from edgarpack_next.sec.source import SourceProvider


class FilingsService:
    def __init__(self, source: SourceProvider):
        self.source = source

    async def list_filings(self, company: str, form: str, limit: int) -> list[FilingIdentity]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        return await self.source.list_filings(company, form=form, limit=limit)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_sec_source.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack_next/sec edgarpack_next/core tests/vnext/test_sec_source.py
git commit -m "feat(vnext): add source provider boundary"
```

## Task 6: Deterministic Pack Writer

**Files:**
- Create: `edgarpack_next/sec/html.py`
- Create: `edgarpack_next/artifacts/__init__.py`
- Create: `edgarpack_next/artifacts/writer.py`
- Create: `edgarpack_next/core/pack.py`
- Create: `tests/vnext/test_pack_writer.py`

- [ ] **Step 1: Write failing pack determinism test**

Create `tests/vnext/test_pack_writer.py`:

```python
from __future__ import annotations

import json

import pytest

from edgarpack_next.core.pack import PackService
from edgarpack_next.sec.source import FixtureSourceProvider
from edgarpack_next.testing.fixtures import load_fixture_index


@pytest.mark.asyncio
async def test_pack_build_is_deterministic(tmp_path) -> None:
    source = FixtureSourceProvider(load_fixture_index())
    service = PackService(source)

    first = await service.build("NVDA", form="10-K", out=tmp_path / "first")
    second = await service.build("NVDA", form="10-K", out=tmp_path / "second")

    assert first.manifest.content_sha256 == second.manifest.content_sha256
    assert first.manifest.sections
    assert (first.manifest_path.parent / "filing.md").exists()
    assert (first.manifest_path.parent / "facts.json").exists()
    assert (first.manifest_path.parent / "citations.json").exists()

    manifest_payload = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["schema_version"] == "vnext.1"
    assert "llms.txt" in manifest_payload["reserved_artifacts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_pack_writer.py -q
```

Expected: FAIL with missing `edgarpack_next.core.pack`.

- [ ] **Step 3: Implement minimal HTML and section primitives**

Create `edgarpack_next/sec/html.py`:

```python
from __future__ import annotations

import html
import re
from hashlib import sha256

from edgarpack.parse.html_clean import clean_html

from edgarpack_next.models import SectionArtifact

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_ITEM_RE = re.compile(
    r"(?im)^\s*(?:#+\s*)?(item\s+(?:1a|1|7a|7|8|9a|9b|10|11|12|13|14|15)\b[^\n]{0,120})$"
)


def source_to_markdown(source: str) -> str:
    if "<" in source and ">" in source:
        source = clean_html(source)
        source = _TAG_RE.sub("\n", source)
    text = html.unescape(source)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    kept = [line for line in lines if line]
    return "\n\n".join(kept) + "\n"


def section_id(title: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"{slug[:80]}_{index:02d}"


def split_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(_ITEM_RE.finditer(markdown))
    if not matches:
        return [("full_filing", markdown.strip() + "\n")]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        title = match.group(1).strip()
        body = markdown[start:end].strip() + "\n"
        sections.append((title, body))
    return sections


def digest_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def artifact_for_section(section_title: str, path: str, content: str, index: int) -> SectionArtifact:
    return SectionArtifact(
        section_id=section_id(section_title, index),
        title=section_title,
        path=path,
        sha256=digest_text(content),
    )
```

- [ ] **Step 4: Implement pack writer and service**

Create `edgarpack_next/artifacts/__init__.py`:

```python
"""Artifact writing for vNext."""
```

Create `edgarpack_next/artifacts/writer.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from edgarpack_next.models import BuildResult, CompanyIdentity, FilingIdentity, PackManifest
from edgarpack_next.sec.html import artifact_for_section, digest_text, split_sections


class PackWriter:
    def write(
        self,
        out: Path,
        company: CompanyIdentity,
        filing: FilingIdentity,
        markdown: str,
    ) -> BuildResult:
        pack_dir = out / company.cik / filing.accession
        sections_dir = pack_dir / "sections"
        sections_dir.mkdir(parents=True, exist_ok=True)

        filing_path = pack_dir / "filing.md"
        filing_path.write_text(markdown, encoding="utf-8")

        sections = []
        for index, (title, content) in enumerate(split_sections(markdown)):
            section_path = sections_dir / f"{artifact_for_section(title, '', content, index).section_id}.md"
            section_path.write_text(content, encoding="utf-8")
            rel_path = section_path.relative_to(pack_dir).as_posix()
            sections.append(artifact_for_section(title, rel_path, content, index))

        (pack_dir / "facts.json").write_text("{}\n", encoding="utf-8")
        (pack_dir / "citations.json").write_text("[]\n", encoding="utf-8")

        manifest = PackManifest(
            company=company,
            filing=filing,
            artifacts={
                "filing": "filing.md",
                "facts": "facts.json",
                "citations": "citations.json",
            },
            sections=sections,
            content_sha256=digest_text(markdown),
        )
        manifest_path = pack_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return BuildResult(manifest_path=manifest_path, manifest=manifest)
```

Create `edgarpack_next/core/pack.py`:

```python
from __future__ import annotations

from pathlib import Path

from edgarpack_next.artifacts.writer import PackWriter
from edgarpack_next.models import BuildResult
from edgarpack_next.sec.html import source_to_markdown
from edgarpack_next.sec.source import SourceProvider


class PackService:
    def __init__(self, source: SourceProvider, writer: PackWriter | None = None):
        self.source = source
        self.writer = writer or PackWriter()

    async def build(self, company: str, form: str, out: Path) -> BuildResult:
        identity = await self.source.resolve_company(company)
        filings = await self.source.list_filings(company, form=form, limit=1)
        if not filings:
            raise ValueError(f"no {form} filing found for {company}")
        filing = filings[0]
        source_text = await self.source.source_text(filing)
        markdown = source_to_markdown(source_text)
        return self.writer.write(out=out, company=identity, filing=filing, markdown=markdown)
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_pack_writer.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add edgarpack_next/sec/html.py edgarpack_next/artifacts edgarpack_next/core/pack.py tests/vnext/test_pack_writer.py
git commit -m "feat(vnext): write deterministic packs"
```

## Task 7: Metric Registry And Direct Citation Resolver

**Files:**
- Create: `edgarpack_next/metrics/__init__.py`
- Create: `edgarpack_next/metrics/registry.py`
- Create: `edgarpack_next/metrics/resolve.py`
- Create: `edgarpack_next/core/cite.py`
- Create: `tests/vnext/test_metric_resolver.py`

- [ ] **Step 1: Write failing metric resolver tests**

Create `tests/vnext/test_metric_resolver.py`:

```python
from __future__ import annotations

import pytest

from edgarpack_next.core.cite import CitationService
from edgarpack_next.models import CitationStatus
from edgarpack_next.sec.source import FixtureSourceProvider
from edgarpack_next.testing.fixtures import load_fixture_index


@pytest.mark.asyncio
async def test_citation_service_returns_curated_cited_revenue() -> None:
    service = CitationService(FixtureSourceProvider(load_fixture_index()))

    result = await service.cite("NVDA", metrics=["revenue"], period="lfy")

    fact = result["revenue"]
    assert fact.status is CitationStatus.CITED
    assert fact.metric == "revenue"
    assert fact.source_url.startswith("https://www.sec.gov/")
    assert fact.evidence_ref


@pytest.mark.asyncio
async def test_unknown_metric_is_missing_not_exception() -> None:
    service = CitationService(FixtureSourceProvider(load_fixture_index()))

    result = await service.cite("NVDA", metrics=["not_a_metric"], period="lfy")

    fact = result["not_a_metric"]
    assert fact.status is CitationStatus.MISSING
    assert "not in registry" in fact.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_metric_resolver.py -q
```

Expected: FAIL with missing `edgarpack_next.core.cite`.

- [ ] **Step 3: Implement registry**

Create `edgarpack_next/metrics/__init__.py`:

```python
"""Metric registry and resolution for vNext."""
```

Create `edgarpack_next/metrics/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSpec:
    name: str
    concepts: tuple[str, ...] = ()
    duration: bool = True
    unit: str = "USD"
    formula: str | None = None
    components: tuple[str, ...] = ()

    @property
    def derived(self) -> bool:
        return bool(self.formula)


REGISTRY: dict[str, MetricSpec] = {
    "revenue": MetricSpec(
        name="revenue",
        concepts=(
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
        ),
    ),
    "gross_profit": MetricSpec(name="gross_profit", concepts=("GrossProfit",)),
    "operating_income": MetricSpec(name="operating_income", concepts=("OperatingIncomeLoss",)),
    "net_income": MetricSpec(name="net_income", concepts=("NetIncomeLoss", "ProfitLoss")),
    "operating_cash_flow": MetricSpec(
        name="operating_cash_flow",
        concepts=("NetCashProvidedByUsedInOperatingActivities",),
    ),
    "capital_expenditures": MetricSpec(
        name="capital_expenditures",
        concepts=("PaymentsToAcquirePropertyPlantAndEquipment",),
    ),
    "cash_and_equivalents": MetricSpec(
        name="cash_and_equivalents",
        concepts=(
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        duration=False,
    ),
    "debt": MetricSpec(
        name="debt",
        concepts=("LongTermDebt", "LongTermDebtCurrent", "LongTermDebtNoncurrent", "DebtCurrent"),
        duration=False,
    ),
    "shares": MetricSpec(
        name="shares",
        concepts=("EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"),
        duration=False,
        unit="shares",
    ),
    "gross_margin": MetricSpec(
        name="gross_margin",
        formula="gross_profit / revenue",
        components=("gross_profit", "revenue"),
        unit="ratio",
    ),
    "operating_margin": MetricSpec(
        name="operating_margin",
        formula="operating_income / revenue",
        components=("operating_income", "revenue"),
        unit="ratio",
    ),
    "free_cash_flow": MetricSpec(
        name="free_cash_flow",
        formula="operating_cash_flow - capital_expenditures",
        components=("operating_cash_flow", "capital_expenditures"),
    ),
}
```

- [ ] **Step 4: Implement direct resolver and citation service**

Create `edgarpack_next/metrics/resolve.py`:

```python
from __future__ import annotations

from typing import Any

from edgarpack_next.metrics.registry import MetricSpec
from edgarpack_next.models import CitationStatus, CitedFact, CompanyIdentity, FilingIdentity, MissingFact


def _candidate_units(metric: MetricSpec) -> tuple[str, ...]:
    if metric.unit == "shares":
        return ("shares",)
    return ("USD", "usd", "USD/shares")


def _source_url(filing: FilingIdentity) -> str:
    cik_int = str(int(filing.cik))
    accession_nodash = filing.accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
        f"{accession_nodash}/{filing.primary_document}"
    )


def resolve_direct_fact(
    facts: dict[str, Any],
    metric: MetricSpec,
    company: CompanyIdentity,
    filing: FilingIdentity,
    period: str,
) -> CitedFact | MissingFact:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in metric.concepts:
        concept_payload = us_gaap.get(concept)
        if not isinstance(concept_payload, dict):
            continue
        units = concept_payload.get("units", {})
        for unit in _candidate_units(metric):
            values = units.get(unit)
            if not isinstance(values, list):
                continue
            for value in reversed(values):
                if value.get("accn") != filing.accession:
                    continue
                if metric.duration and not value.get("start"):
                    continue
                if not metric.duration and value.get("start"):
                    continue
                raw = value.get("val")
                if raw is None:
                    continue
                return CitedFact(
                    metric=metric.name,
                    value=raw,
                    unit=unit,
                    period=period,
                    status=CitationStatus.CITED,
                    company=company,
                    filing=filing,
                    concept=concept,
                    source_url=_source_url(filing),
                    evidence_ref=f"us-gaap:{concept}@{filing.accession}",
                )
    return MissingFact(
        metric=metric.name,
        period=period,
        status=CitationStatus.MISSING,
        reason="no registry-approved concept value found for filing",
    )
```

Create `edgarpack_next/core/cite.py`:

```python
from __future__ import annotations

from edgarpack_next.metrics.registry import REGISTRY
from edgarpack_next.metrics.resolve import resolve_direct_fact
from edgarpack_next.models import CitationStatus, MetricFact, MissingFact
from edgarpack_next.sec.source import SourceProvider


class CitationService:
    def __init__(self, source: SourceProvider):
        self.source = source

    async def cite(self, company: str, metrics: list[str], period: str) -> dict[str, MetricFact]:
        identity = await self.source.resolve_company(company)
        filings = await self.source.list_filings(company, form="10-K", limit=1)
        if not filings:
            return {
                metric: MissingFact(
                    metric=metric,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="no 10-K filing available",
                )
                for metric in metrics
            }
        filing = filings[0]
        facts = await self.source.companyfacts(identity.cik)

        result: dict[str, MetricFact] = {}
        for metric_name in metrics:
            spec = REGISTRY.get(metric_name)
            if spec is None:
                result[metric_name] = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="metric not in registry",
                )
                continue
            if spec.derived:
                result[metric_name] = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="derived metric engine not yet enabled",
                    missing_components=spec.components,
                )
                continue
            result[metric_name] = resolve_direct_fact(facts, spec, identity, filing, period)
        return result
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_metric_resolver.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add edgarpack_next/metrics edgarpack_next/core/cite.py tests/vnext/test_metric_resolver.py
git commit -m "feat(vnext): resolve curated cited metrics"
```

## Task 8: Derived Metrics With Component Citations

**Files:**
- Create: `edgarpack_next/metrics/derive.py`
- Modify: `edgarpack_next/core/cite.py`
- Create: `tests/vnext/test_derived_metrics.py`

- [ ] **Step 1: Write failing derived metric tests**

Create `tests/vnext/test_derived_metrics.py`:

```python
from __future__ import annotations

import pytest

from edgarpack_next.core.cite import CitationService
from edgarpack_next.models import CitationStatus, DerivedFact
from edgarpack_next.sec.source import FixtureSourceProvider
from edgarpack_next.testing.fixtures import load_fixture_index


@pytest.mark.asyncio
async def test_gross_margin_uses_component_citations() -> None:
    service = CitationService(FixtureSourceProvider(load_fixture_index()))

    result = await service.cite("NVDA", metrics=["gross_margin"], period="lfy")

    fact = result["gross_margin"]
    assert isinstance(fact, DerivedFact)
    assert fact.status is CitationStatus.CITED
    assert fact.formula == "gross_profit / revenue"
    assert {component.metric for component in fact.components} == {"gross_profit", "revenue"}
    assert all(component.evidence_ref for component in fact.components)


@pytest.mark.asyncio
async def test_missing_component_withholds_derived_value() -> None:
    service = CitationService(FixtureSourceProvider(load_fixture_index()))

    result = await service.cite("AAPL", metrics=["free_cash_flow"], period="lfy")

    fact = result["free_cash_flow"]
    if fact.status is CitationStatus.MISSING:
        assert fact.value is None
        assert fact.missing is not None
        assert fact.missing.missing_components
    else:
        assert isinstance(fact, DerivedFact)
        assert all(component.status is CitationStatus.CITED for component in fact.components)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_derived_metrics.py -q
```

Expected: FAIL because derived metric engine is not enabled.

- [ ] **Step 3: Implement derived engine**

Create `edgarpack_next/metrics/derive.py`:

```python
from __future__ import annotations

from edgarpack_next.metrics.registry import MetricSpec
from edgarpack_next.models import CitationStatus, CitedFact, DerivedFact, MissingFact


def derive_metric(spec: MetricSpec, components: dict[str, CitedFact | MissingFact], period: str) -> DerivedFact:
    missing = tuple(
        name
        for name in spec.components
        if not isinstance(components.get(name), CitedFact)
        or components[name].status is not CitationStatus.CITED
    )
    cited_components = [components[name] for name in spec.components if isinstance(components.get(name), CitedFact)]
    if missing:
        return DerivedFact(
            metric=spec.name,
            period=period,
            status=CitationStatus.MISSING,
            formula=spec.formula or "",
            components=[item for item in cited_components if isinstance(item, CitedFact)],
            missing=MissingFact(
                metric=spec.name,
                period=period,
                status=CitationStatus.MISSING,
                reason="missing required component",
                missing_components=missing,
            ),
        )

    values = {name: float(components[name].value) for name in spec.components if isinstance(components[name], CitedFact)}
    if spec.formula == "gross_profit / revenue":
        value = values["gross_profit"] / values["revenue"]
    elif spec.formula == "operating_income / revenue":
        value = values["operating_income"] / values["revenue"]
    elif spec.formula == "operating_cash_flow - capital_expenditures":
        value = values["operating_cash_flow"] - values["capital_expenditures"]
    else:
        return DerivedFact(
            metric=spec.name,
            period=period,
            status=CitationStatus.UNSUPPORTED,
            formula=spec.formula or "",
            components=[item for item in cited_components if isinstance(item, CitedFact)],
            missing=MissingFact(
                metric=spec.name,
                period=period,
                status=CitationStatus.UNSUPPORTED,
                reason="formula not supported",
            ),
        )
    return DerivedFact(
        metric=spec.name,
        period=period,
        status=CitationStatus.CITED,
        formula=spec.formula or "",
        components=[item for item in cited_components if isinstance(item, CitedFact)],
        value=value,
        unit=spec.unit,
    )
```

- [ ] **Step 4: Wire derived metrics into citation service**

Modify `edgarpack_next/core/cite.py` so derived metrics resolve their direct components first:

```python
from __future__ import annotations

from edgarpack_next.metrics.derive import derive_metric
from edgarpack_next.metrics.registry import REGISTRY
from edgarpack_next.metrics.resolve import resolve_direct_fact
from edgarpack_next.models import CitationStatus, MetricFact, MissingFact
from edgarpack_next.sec.source import SourceProvider


class CitationService:
    def __init__(self, source: SourceProvider):
        self.source = source

    async def cite(self, company: str, metrics: list[str], period: str) -> dict[str, MetricFact]:
        identity = await self.source.resolve_company(company)
        filings = await self.source.list_filings(company, form="10-K", limit=1)
        if not filings:
            return {
                metric: MissingFact(
                    metric=metric,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="no 10-K filing available",
                )
                for metric in metrics
            }
        filing = filings[0]
        facts = await self.source.companyfacts(identity.cik)

        direct_cache: dict[str, MetricFact] = {}

        def direct(metric_name: str) -> MetricFact:
            if metric_name in direct_cache:
                return direct_cache[metric_name]
            spec = REGISTRY.get(metric_name)
            if spec is None:
                value: MetricFact = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="metric not in registry",
                )
            elif spec.derived:
                value = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="component cannot be derived in slice one",
                    missing_components=spec.components,
                )
            else:
                value = resolve_direct_fact(facts, spec, identity, filing, period)
            direct_cache[metric_name] = value
            return value

        result: dict[str, MetricFact] = {}
        for metric_name in metrics:
            spec = REGISTRY.get(metric_name)
            if spec is None:
                result[metric_name] = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="metric not in registry",
                )
            elif spec.derived:
                components = {component: direct(component) for component in spec.components}
                result[metric_name] = derive_metric(spec, components, period)
            else:
                result[metric_name] = direct(metric_name)
        return result
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_derived_metrics.py tests/vnext/test_metric_resolver.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add edgarpack_next/metrics/derive.py edgarpack_next/core/cite.py tests/vnext/test_derived_metrics.py
git commit -m "feat(vnext): derive metrics from cited components"
```

## Task 8A: Experimental Concept Search Lane

**Files:**
- Create: `edgarpack_next/metrics/search.py`
- Create: `tests/vnext/test_concept_search.py`

- [ ] **Step 1: Write failing search-lane tests**

Create `tests/vnext/test_concept_search.py`:

```python
from __future__ import annotations

from edgarpack_next.metrics.search import search_unverified_fact
from edgarpack_next.models import CitationStatus, CompanyIdentity, FilingIdentity


def test_concept_search_returns_unverified_cited_fact() -> None:
    company = CompanyIdentity(cik="0001045810", ticker="NVDA", name="NVIDIA CORP")
    filing = FilingIdentity(
        cik="0001045810",
        accession="0001045810-26-000021",
        form="10-K",
        filing_date="2026-02-25",
        primary_document="nvda-20260125.htm",
    )
    facts = {
        "facts": {
            "us-gaap": {
                "ResearchAndDevelopmentExpense": {
                    "label": "Research and Development Expense",
                    "units": {
                        "USD": [
                            {
                                "accn": "0001045810-26-000021",
                                "form": "10-K",
                                "start": "2025-01-27",
                                "end": "2026-01-25",
                                "val": 12914000000,
                            }
                        ]
                    },
                }
            }
        }
    }

    fact = search_unverified_fact(
        facts=facts,
        metric_name="research_development_expense",
        company=company,
        filing=filing,
        period="lfy",
    )

    assert fact is not None
    assert fact.status is CitationStatus.UNVERIFIED_CITED
    assert fact.match_score is not None
    assert fact.match_reason
    assert fact.evidence_ref == "us-gaap:ResearchAndDevelopmentExpense@0001045810-26-000021"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_concept_search.py -q
```

Expected: FAIL with missing `edgarpack_next.metrics.search`.

- [ ] **Step 3: Implement search lane**

Create `edgarpack_next/metrics/search.py`:

```python
from __future__ import annotations

import re
from typing import Any

from edgarpack_next.metrics.resolve import _source_url
from edgarpack_next.models import CitationStatus, CitedFact, CompanyIdentity, FilingIdentity


def _tokens(value: str) -> set[str]:
    return {token for token in re.sub(r"[^a-zA-Z0-9]+", " ", value).lower().split() if token}


def search_unverified_fact(
    facts: dict[str, Any],
    metric_name: str,
    company: CompanyIdentity,
    filing: FilingIdentity,
    period: str,
) -> CitedFact | None:
    wanted = _tokens(metric_name)
    if not wanted:
        return None
    best: tuple[float, str, dict[str, Any]] | None = None
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept, payload in us_gaap.items():
        if not isinstance(payload, dict):
            continue
        label = str(payload.get("label") or concept)
        haystack = _tokens(concept) | _tokens(label)
        score = len(wanted & haystack) / len(wanted)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, concept, payload)
    if best is None or best[0] < 0.5:
        return None

    score, concept, payload = best
    for unit, values in payload.get("units", {}).items():
        if not isinstance(values, list):
            continue
        for value in reversed(values):
            if value.get("accn") != filing.accession:
                continue
            raw = value.get("val")
            if raw is None:
                continue
            return CitedFact(
                metric=metric_name,
                value=raw,
                unit=str(unit),
                period=period,
                status=CitationStatus.UNVERIFIED_CITED,
                company=company,
                filing=filing,
                concept=concept,
                source_url=_source_url(filing),
                evidence_ref=f"us-gaap:{concept}@{filing.accession}",
                match_reason=f"concept/label token overlap for {metric_name}",
                match_score=score,
            )
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_concept_search.py tests/vnext/test_derived_metrics.py -q
```

Expected: PASS. This confirms search values are typed as `unverified_cited`; `DerivedFact` still rejects non-curated components.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack_next/metrics/search.py tests/vnext/test_concept_search.py scripts/capture_vnext_fixtures.py
git commit -m "feat(vnext): add experimental concept search lane"
```

## Task 9: S-1 Selected-Financial-Data Extraction

**Files:**
- Create: `edgarpack_next/sec/s1_tables.py`
- Modify: `edgarpack_next/core/cite.py`
- Create: `tests/vnext/test_s1_selected_financial_data.py`

- [ ] **Step 1: Write failing S-1 extraction test**

Create `tests/vnext/test_s1_selected_financial_data.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from edgarpack_next.core.cite import CitationService
from edgarpack_next.models import CitationStatus
from edgarpack_next.sec.source import FixtureSourceProvider
from edgarpack_next.sec.s1_tables import extract_selected_financial_data
from edgarpack_next.testing.fixtures import load_fixture_index


def test_cerebras_selected_financial_data_extracts_cited_revenue() -> None:
    path = Path("tests/fixtures/cerebras_selected_financial_data.md")

    facts = extract_selected_financial_data(path.read_text(encoding="utf-8"))

    revenue = facts["revenue"]
    assert revenue.value == 78_287_000
    assert revenue.unit == "USD"
    assert revenue.evidence_label == "Selected Financial Data"


@pytest.mark.asyncio
async def test_cerebras_s1_citation_service_returns_selected_financial_revenue() -> None:
    service = CitationService(FixtureSourceProvider(load_fixture_index()))

    result = await service.cite("Cerebras Systems Inc.", metrics=["revenue"], period="lfy", form="S-1")

    fact = result["revenue"]
    assert fact.status is CitationStatus.CITED
    assert fact.value == 78_287_000
    assert fact.concept == "SelectedFinancialData:revenue"
    assert fact.evidence_ref == "selected-financial-data:revenue@0001628280-24-041596"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_s1_selected_financial_data.py -q
```

Expected: FAIL with missing `edgarpack_next.sec.s1_tables`.

- [ ] **Step 3: Implement narrow table extractor**

Create `edgarpack_next/sec/s1_tables.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class S1TableFact:
    metric: str
    value: int
    unit: str
    evidence_label: str


_ROW_RE = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<value>\(?\$?[\d,]+\)?)\s*\|", re.MULTILINE)
_LABELS = {
    "Revenue": "revenue",
    "Cost of revenue": "cost_of_revenue",
    "Gross profit": "gross_profit",
    "Operating loss": "operating_income",
    "Net loss": "net_income",
    "Cash and cash equivalents": "cash_and_equivalents",
    "Total assets": "total_assets",
}


def _parse_amount(raw: str) -> int:
    text = raw.strip().replace("$", "").replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    value = int(text) * 1000
    return -value if negative else value


def extract_selected_financial_data(markdown: str) -> dict[str, S1TableFact]:
    if "Selected Financial Data" not in markdown:
        return {}
    result: dict[str, S1TableFact] = {}
    for match in _ROW_RE.finditer(markdown):
        label = match.group("label").strip()
        metric = _LABELS.get(label)
        if metric is None:
            continue
        result[metric] = S1TableFact(
            metric=metric,
            value=_parse_amount(match.group("value")),
            unit="USD",
            evidence_label="Selected Financial Data",
        )
    return result
```

- [ ] **Step 4: Wire S-1 extraction into citation service**

Modify `edgarpack_next/core/cite.py` so `CitationService.cite(..., form="S-1")` uses selected-financial-data fixtures:

```python
from __future__ import annotations

from pathlib import Path

from edgarpack_next.metrics.derive import derive_metric
from edgarpack_next.metrics.registry import REGISTRY
from edgarpack_next.metrics.resolve import resolve_direct_fact
from edgarpack_next.models import CitationStatus, CitedFact, MetricFact, MissingFact
from edgarpack_next.sec.s1_tables import extract_selected_financial_data
from edgarpack_next.sec.source import SourceProvider


class CitationService:
    def __init__(self, source: SourceProvider):
        self.source = source

    async def cite(
        self,
        company: str,
        metrics: list[str],
        period: str,
        form: str = "10-K",
    ) -> dict[str, MetricFact]:
        identity = await self.source.resolve_company(company)
        filings = await self.source.list_filings(company, form=form, limit=1)
        if not filings:
            return {
                metric: MissingFact(
                    metric=metric,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason=f"no {form} filing available",
                )
                for metric in metrics
            }
        filing = filings[0]

        if filing.form.upper().startswith("S-1"):
            selected_path = getattr(self.source, "selected_financial_data_path", lambda _filing: None)(filing)
            if isinstance(selected_path, Path):
                table_facts = extract_selected_financial_data(selected_path.read_text(encoding="utf-8"))
                return {
                    metric: (
                        CitedFact(
                            metric=metric,
                            value=table_facts[metric].value,
                            unit=table_facts[metric].unit,
                            period=period,
                            status=CitationStatus.CITED,
                            company=identity,
                            filing=filing,
                            concept=f"SelectedFinancialData:{metric}",
                            source_url=selected_path.as_posix(),
                            evidence_ref=f"selected-financial-data:{metric}@{filing.accession}",
                        )
                        if metric in table_facts
                        else MissingFact(
                            metric=metric,
                            period=period,
                            status=CitationStatus.MISSING,
                            reason="metric not found in selected financial data fixture",
                        )
                    )
                    for metric in metrics
                }
            return {
                metric: MissingFact(
                    metric=metric,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="S-1 selected financial data source unavailable",
                )
                for metric in metrics
            }

        facts = await self.source.companyfacts(identity.cik)
        direct_cache: dict[str, MetricFact] = {}

        def direct(metric_name: str) -> MetricFact:
            if metric_name in direct_cache:
                return direct_cache[metric_name]
            spec = REGISTRY.get(metric_name)
            if spec is None:
                value: MetricFact = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="metric not in registry",
                )
            elif spec.derived:
                value = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="component cannot be derived in slice one",
                    missing_components=spec.components,
                )
            else:
                value = resolve_direct_fact(facts, spec, identity, filing, period)
            direct_cache[metric_name] = value
            return value

        result: dict[str, MetricFact] = {}
        for metric_name in metrics:
            spec = REGISTRY.get(metric_name)
            if spec is None:
                result[metric_name] = MissingFact(
                    metric=metric_name,
                    period=period,
                    status=CitationStatus.MISSING,
                    reason="metric not in registry",
                )
            elif spec.derived:
                components = {component: direct(component) for component in spec.components}
                result[metric_name] = derive_metric(spec, components, period)
            else:
                result[metric_name] = direct(metric_name)
        return result
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_s1_selected_financial_data.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add edgarpack_next/sec/s1_tables.py edgarpack_next/core/cite.py tests/vnext/test_s1_selected_financial_data.py
git commit -m "feat(vnext): extract fixture-backed S-1 financial table"
```

## Task 10: Audit Service

**Files:**
- Create: `edgarpack_next/core/audit.py`
- Create: `tests/vnext/test_audit_service.py`

- [ ] **Step 1: Write failing audit tests**

Create `tests/vnext/test_audit_service.py`:

```python
from __future__ import annotations

import pytest

from edgarpack_next.core.audit import AuditService
from edgarpack_next.core.pack import PackService
from edgarpack_next.sec.source import FixtureSourceProvider
from edgarpack_next.testing.fixtures import load_fixture_index


@pytest.mark.asyncio
async def test_audit_accepts_pack_with_required_artifacts(tmp_path) -> None:
    pack = await PackService(FixtureSourceProvider(load_fixture_index())).build(
        "NVDA",
        form="10-K",
        out=tmp_path,
    )

    audit = AuditService().audit(pack.manifest_path.parent)

    assert audit.ok is True
    assert audit.errors == ()


def test_audit_rejects_missing_manifest(tmp_path) -> None:
    audit = AuditService().audit(tmp_path)

    assert audit.ok is False
    assert "manifest.json missing" in audit.errors
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_audit_service.py -q
```

Expected: FAIL with missing `edgarpack_next.core.audit`.

- [ ] **Step 3: Implement audit service**

Create `edgarpack_next/core/audit.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from edgarpack_next.models import AuditResult


class AuditService:
    def audit(self, pack_dir: Path) -> AuditResult:
        errors: list[str] = []
        warnings: list[str] = []

        manifest_path = pack_dir / "manifest.json"
        if not manifest_path.exists():
            return AuditResult(ok=False, errors=("manifest.json missing",))

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for artifact in ("filing.md", "facts.json", "citations.json"):
            if not (pack_dir / artifact).exists():
                errors.append(f"{artifact} missing")
        sections = payload.get("sections", [])
        if not sections:
            errors.append("no sections recorded")
        for section in sections:
            path = section.get("path", "")
            if path and not (pack_dir / path).exists():
                errors.append(f"section missing: {path}")
        if "llms.txt" not in payload.get("reserved_artifacts", []):
            warnings.append("llms.txt not reserved")

        return AuditResult(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_audit_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack_next/core/audit.py tests/vnext/test_audit_service.py
git commit -m "feat(vnext): audit pack artifacts"
```

## Task 11: CLI Commands With JSON Output

**Files:**
- Modify: `edgarpack_next/cli.py`
- Create: `tests/vnext/test_cli_commands.py`

- [ ] **Step 1: Write failing CLI command tests**

Create `tests/vnext/test_cli_commands.py`:

```python
from __future__ import annotations

import json

from typer.testing import CliRunner

from edgarpack_next.cli import app


def test_filings_command_returns_json() -> None:
    result = CliRunner().invoke(app, ["filings", "NVDA", "--form", "10-K", "--fixture"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["accession"] == "0001045810-26-000021"


def test_cite_command_returns_json_with_status() -> None:
    result = CliRunner().invoke(app, ["cite", "NVDA", "revenue", "--fixture", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["revenue"]["status"] == "cited"
    assert payload["revenue"]["evidence_ref"]


def test_cite_command_supports_s1_fixture_form() -> None:
    result = CliRunner().invoke(
        app,
        ["cite", "Cerebras Systems Inc.", "revenue", "--form", "S-1", "--fixture", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["revenue"]["concept"] == "SelectedFinancialData:revenue"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_cli_commands.py -q
```

Expected: FAIL because commands still exit with code 2.

- [ ] **Step 3: Implement command adapters**

Replace `edgarpack_next/cli.py` with:

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .core.audit import AuditService
from .core.cite import CitationService
from .core.filings import FilingsService
from .core.pack import PackService
from .sec.source import FixtureSourceProvider, LiveSECSourceProvider, SourceProvider
from .testing.fixtures import load_fixture_index

app = typer.Typer(
    add_completion=False,
    help="Evidence-first filing compiler for primary-source-backed company research.",
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"edgarpack-next {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show edgarpack-next version.",
    ),
) -> None:
    return None


def _source(fixture: bool) -> SourceProvider:
    if fixture:
        return FixtureSourceProvider(load_fixture_index())
    return LiveSECSourceProvider()


@app.command()
def filings(
    company: str,
    form: str = typer.Option("10-K", "--form"),
    limit: int = typer.Option(10, "--limit"),
    fixture: bool = typer.Option(False, "--fixture", help="Use vNext frozen fixtures."),
) -> None:
    """Inspect available filings for a company."""
    result = asyncio.run(FilingsService(_source(fixture)).list_filings(company, form=form, limit=limit))
    typer.echo(json.dumps([item.model_dump(mode="json") for item in result], indent=2, sort_keys=True))


@app.command()
def pack(
    company: str,
    form: str = typer.Option("10-K", "--form"),
    out: Path = typer.Option(Path("packs-next"), "--out"),
    fixture: bool = typer.Option(False, "--fixture", help="Use vNext frozen fixtures."),
) -> None:
    """Build deterministic pack artifacts from primary filings."""
    result = asyncio.run(PackService(_source(fixture)).build(company, form=form, out=out))
    typer.echo(result.manifest.model_dump_json(indent=2))


@app.command()
def cite(
    company: str,
    metrics: str,
    form: str = typer.Option("10-K", "--form"),
    period: str = typer.Option("lfy", "--period"),
    fixture: bool = typer.Option(False, "--fixture", help="Use vNext frozen fixtures."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Return cited facts and diagnostics."""
    metric_names = [item.strip() for item in metrics.split(",") if item.strip()]
    result = asyncio.run(CitationService(_source(fixture)).cite(company, metric_names, period=period, form=form))
    payload = {key: value.model_dump(mode="json") for key, value in result.items()}
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for metric, value in payload.items():
        console.print(f"{metric}: {value.get('status')}")


@app.command()
def audit(path: Path) -> None:
    """Inspect pack and citation integrity."""
    result = AuditService().audit(path)
    typer.echo(result.model_dump_json(indent=2))


def main() -> None:
    app()
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_cli_contract.py tests/vnext/test_cli_commands.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack_next/cli.py tests/vnext/test_cli_commands.py
git commit -m "feat(vnext): expose evidence CLI commands"
```

## Task 12: Minimal API Wrapper

**Files:**
- Create: `edgarpack_next/api.py`
- Create: `tests/vnext/test_api_contract.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/vnext/test_api_contract.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from edgarpack_next.api import app


def test_api_cites_fixture_metric() -> None:
    client = TestClient(app)

    response = client.get("/vnext/cite", params={"company": "NVDA", "metrics": "revenue", "fixture": "true"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["revenue"]["status"] == "cited"
    assert payload["revenue"]["evidence_ref"]


def test_api_cites_s1_fixture_metric() -> None:
    client = TestClient(app)

    response = client.get(
        "/vnext/cite",
        params={"company": "Cerebras Systems Inc.", "metrics": "revenue", "form": "S-1", "fixture": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["revenue"]["concept"] == "SelectedFinancialData:revenue"


def test_api_builds_fixture_pack(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(app)

    response = client.post("/vnext/packs", json={"company": "NVDA", "form": "10-K", "fixture": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["filing"]["accession"] == "0001045810-26-000021"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_api_contract.py -q
```

Expected: FAIL with missing `edgarpack_next.api`.

- [ ] **Step 3: Implement API wrapper**

Create `edgarpack_next/api.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from edgarpack_next.core.cite import CitationService
from edgarpack_next.core.pack import PackService
from edgarpack_next.sec.source import FixtureSourceProvider, LiveSECSourceProvider, SourceProvider
from edgarpack_next.testing.fixtures import load_fixture_index

app = FastAPI(title="EdgarPack vNext API")


class PackRequest(BaseModel):
    company: str
    form: str = "10-K"
    fixture: bool = False
    out: str = "packs-next"


def _source(fixture: bool) -> SourceProvider:
    if fixture:
        return FixtureSourceProvider(load_fixture_index())
    return LiveSECSourceProvider()


@app.get("/vnext/cite")
async def cite(
    company: str,
    metrics: str,
    form: str = "10-K",
    period: str = "lfy",
    fixture: bool = False,
) -> dict[str, object]:
    metric_names = [item.strip() for item in metrics.split(",") if item.strip()]
    result = await CitationService(_source(fixture)).cite(company, metric_names, period=period, form=form)
    return {key: value.model_dump(mode="json") for key, value in result.items()}


@app.post("/vnext/packs")
async def build_pack(request: PackRequest) -> dict[str, object]:
    result = await PackService(_source(request.fixture)).build(
        request.company,
        form=request.form,
        out=Path(request.out),
    )
    return result.model_dump(mode="json")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_api_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add edgarpack_next/api.py tests/vnext/test_api_contract.py
git commit -m "feat(vnext): add minimal API wrapper"
```

## Task 13: Live SEC Smoke

**Files:**
- Create: `tests/vnext/test_live_sec_smoke.py`

- [ ] **Step 1: Write gated live smoke tests**

Create `tests/vnext/test_live_sec_smoke.py`:

```python
from __future__ import annotations

import pytest

from edgarpack_next.core.cite import CitationService
from edgarpack_next.core.filings import FilingsService
from edgarpack_next.core.pack import PackService
from edgarpack_next.models import CitationStatus
from edgarpack_next.sec.source import LiveSECSourceProvider

pytestmark = [
    pytest.mark.slow,
    pytest.mark.live_sec,
    pytest.mark.usefixtures("_require_slow", "_require_live_sec"),
]


@pytest.mark.asyncio
async def test_live_sec_resolves_nvda_and_lists_10k() -> None:
    source = LiveSECSourceProvider()
    filings = await FilingsService(source).list_filings("NVDA", form="10-K", limit=1)

    assert filings
    assert filings[0].form in {"10-K", "10-K/A"}


@pytest.mark.asyncio
async def test_live_sec_builds_nvda_pack(tmp_path) -> None:
    source = LiveSECSourceProvider()
    result = await PackService(source).build("NVDA", form="10-K", out=tmp_path)

    assert result.manifest_path.exists()
    assert result.manifest.sections
    assert result.manifest.filing.form in {"10-K", "10-K/A"}


@pytest.mark.asyncio
async def test_live_sec_cites_aapl_revenue() -> None:
    source = LiveSECSourceProvider()
    result = await CitationService(source).cite("AAPL", metrics=["revenue"], period="lfy")

    assert result["revenue"].status in {CitationStatus.CITED, CitationStatus.MISSING}
```

- [ ] **Step 2: Run default lane to verify tests are gated**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext/test_live_sec_smoke.py -q
```

Expected: skipped tests because `--run-slow --run-live-sec` were not passed.

- [ ] **Step 3: Run live lane**

Run:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest tests/vnext/test_live_sec_smoke.py --run-slow --run-live-sec -q
```

Expected: PASS when `EDGARPACK_USER_AGENT` is set. This covers live filing discovery, live primary-document pack build, and live cited-query behavior. If the environment lacks a user agent, expected result is SKIP with the existing conftest message requiring `EDGARPACK_USER_AGENT`.

- [ ] **Step 4: Commit**

Run:

```bash
git add tests/vnext/test_live_sec_smoke.py
git commit -m "test(vnext): add live SEC smoke gate"
```

## Task 14: Update Agent Operating Manual

**Files:**
- Modify: `.reforge/09_agent_operating_manual.md`

- [ ] **Step 1: Add vNext operating rules**

Append this section to `.reforge/09_agent_operating_manual.md`:

```markdown
## vNext Clean Rewrite Rules

- vNext lives in `edgarpack_next` and is exposed as `edgarpack-next`.
- The current `edgarpack` package is evidence, not the vNext base layer.
- vNext may reuse reviewed SEC leaf utilities, but must not call old CLI, pack builders, query orchestration, period engine, self-heal, old renderers, old sectionizer, or China Lens services.
- All public values must be `cited`, `unverified_cited`, `missing`, or `unsupported`.
- `unverified_cited` values require an explicit experimental option and must not feed derived metrics.
- Run vNext focused tests before full-suite checks:
  `./.venv/bin/python -m pytest tests/vnext -q`
  `./.venv/bin/ruff check edgarpack_next tests/vnext`
  `./.venv/bin/mypy edgarpack_next`
```

- [ ] **Step 2: Commit**

Run:

```bash
git add .reforge/09_agent_operating_manual.md
git commit -m "docs(reforge): record vnext operating rules"
```

## Task 15: Final Verification

**Files:**
- No new code files.

- [ ] **Step 1: Run focused vNext tests**

Run:

```bash
./.venv/bin/python -m pytest tests/vnext -q
```

Expected: PASS, with live smoke skipped unless live flags are present.

- [ ] **Step 2: Run style and scoped typing**

Run:

```bash
./.venv/bin/ruff check edgarpack_next tests/vnext scripts/capture_vnext_fixtures.py
./.venv/bin/ruff format --check edgarpack_next tests/vnext scripts/capture_vnext_fixtures.py
./.venv/bin/mypy edgarpack_next
```

Expected: PASS.

- [ ] **Step 3: Run full regression lane**

Run:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest -q
```

Expected: PASS or known skips/xfails. If live SEC network is blocked, rerun with approval because this repo has tests that hit SEC unless fully isolated.

- [ ] **Step 4: Run live smoke with explicit flags**

Run:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest tests/vnext/test_live_sec_smoke.py --run-slow --run-live-sec -q
```

Expected: PASS when `EDGARPACK_USER_AGENT` is set. SKIP for missing user agent is acceptable only if reported clearly.

- [ ] **Step 5: Inspect diff**

Run:

```bash
git status --short --untracked-files=all
git diff --stat
```

Expected: only vNext package, vNext tests, fixture files, dependency files, scripts, and `.reforge/09` changed.

- [ ] **Step 6: Commit verification fixes**

If verification required small fixes, commit them:

```bash
git add edgarpack_next tests/vnext tests/fixtures/vnext scripts/capture_vnext_fixtures.py pyproject.toml uv.lock .reforge/09_agent_operating_manual.md
git commit -m "chore(vnext): pass clean rewrite verification"
```

If no fixes were needed, do not create an empty commit.

## Completion Handoff

Report:

- Worktree path and branch.
- Commits created.
- Focused vNext test result.
- Ruff result.
- Scoped mypy result.
- Full pytest result.
- Live SEC smoke result.
- Any skipped gate and exact reason.
- Whether `uv.lock` changed and why.

Do not claim `edgarpack-next` is ready to replace `edgarpack`. Cutover requires the separate cutover gate from the design spec and explicit user approval.
