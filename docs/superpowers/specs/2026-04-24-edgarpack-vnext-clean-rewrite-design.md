# EdgarPack vNext Clean Rewrite Design

## Status

This spec supersedes the earlier `.reforge/08_rebuild_plan.md` recommendation to avoid a clean rewrite. The assessment recommendation was technically conservative because the existing test suite is strong. The user has now made an explicit product decision: the next phase is a clean rebuild whose purpose is to preserve validated learning while cutting accidental architecture and AI-generated slop.

The old implementation remains evidence. It is not the base layer for vNext.

## Goal

Build `edgarpack_next`, a clean CLI-first evidence compiler for public-company filings. The first version should ingest real SEC primary documents, produce deterministic packs, and return cited financial facts through both a sharp CLI and a minimal API wrapper.

The rebuild is successful only if it is more elegant, more explicit, and harder to misuse than the current implementation. It must not merely re-skin the old architecture.

## Product Surface

### Primary Surface: CLI

The vNext command should be installed as `edgarpack-next` while it lives beside the existing `edgarpack` command.

The command language should use evidence verbs, not generic CRUD or internal module names:

```bash
edgarpack-next filings AAPL --form 10-K
edgarpack-next pack AAPL --form 10-K --last 3
edgarpack-next cite AAPL revenue,gross_margin --period lfy
edgarpack-next compare NVDA AMD INTC --on revenue,gross_margin
edgarpack-next trace AAPL risk-factors --since 2020
edgarpack-next audit packs/AAPL/2024-10K
```

Slice one does not need to implement every command above. It must establish the grammar and implement the smallest useful spine:

- `filings`: inspect available filings for a company.
- `pack`: build deterministic pack artifacts.
- `cite`: return cited facts from the new evidence model.
- `audit`: inspect pack validity and citation integrity.

`compare`, `trace`, and corpus search can follow after the pack and citation spine is proven.

### Secondary Surface: Minimal API

The API is included in vNext alpha, but it is a wrapper over the core. It must not become a second product brain.

Allowed endpoints for slice one:

- Create a pack build using the same core service as `edgarpack-next pack`.
- Read build status and result.
- Query cited facts using the same core service as `edgarpack-next cite`.

Forbidden in slice one:

- Seeded demo claims.
- API-owned fact generation.
- Simulated job pipelines that do not reflect real core work.
- China Lens finding endpoints.
- Web UI work.

The API returns the same Pydantic contracts as CLI JSON output.

## Explicit Non-Goals For vNext Alpha

- No Next.js web rebuild.
- No hardcoded demo claims.
- No model-generated supported findings.
- No OCR provider integration.
- No vector database.
- No authentication or workspace collaboration.
- No learned/self-healing metric promotion workflow.
- No old command compatibility aliases until the new command model is stable.
- No `llms.txt` generation in slice one.

These can be revisited after the core evidence model earns trust.

## Package And Isolation

vNext lives in a new package:

- Python package: `edgarpack_next`
- Console command: `edgarpack-next`

Implementation should happen in an isolated git worktree and branch. The existing `edgarpack` package remains available for reference and selected compatibility checks.

The old package can be imported only for reviewed leaf utilities. It must not be used as the vNext architecture.

Allowed reuse:

- SEC HTTP/cache transport helpers.
- Filing URL/accession helpers.
- HTML cleaning primitives.
- Token counting helpers.

Forbidden reuse:

- Old `edgarpack.cli` orchestration.
- Old pack builders.
- Old query orchestrator.
- Old period engine.
- Old self-heal/learned mapping system.
- Old sectionizer as the vNext section contract.
- Old renderers.
- Old China Lens services.

## Stack

Language: Python 3.11+.

Allowed modern stack:

- Pydantic v2 for boundary and artifact models. This is already a runtime dependency.
- Typer for the vNext CLI grammar.
- Rich for tables, warnings, and human-readable errors.

Typer and Rich are not current runtime dependencies, so adding them must be explicit in the implementation plan and justified by tests. They are allowed because the rewrite is intentionally improving human and agent ergonomics.

Avoid:

- Dependency injection containers.
- Plugin systems.
- Abstract factories.
- Framework-shaped code before there is framework pressure.

## Source Scope

Slice one supports SEC filings:

- 10-K
- 10-Q
- S-1

10-K and 10-Q support pack building and cited financial facts through SEC filing/companyfacts evidence.

S-1 support is first-class for pack building and selected financial data extraction, but narrowly scoped. vNext may extract S-1 financial facts only from recognized selected-financial-data or summary-financial-data table shapes backed by real fixtures. If the table is not recognized, S-1 facts are missing, not guessed.

HKEX, SSE, CNINFO, OCR, and translated China Lens workflows are out of scope for slice one.

## Canonical Fixtures

The first fixture set should use real primary-source material:

- NVDA mature filer path.
- AAPL mature filer path.
- Cerebras S-1 path.

Fixture-first does not mean fake data. The fixtures should include real SEC source material such as filing metadata, primary HTML or extracted source text, and companyfacts JSON. Existing generated `packs/` can be used as migration evidence, but not as golden truth.

Live SEC smoke is required before signing off a milestone. The live path must use explicit cache and user-agent handling.

## Artifact Contract

Slice one pack output is deterministic and minimal:

```text
manifest.json
filing.md
sections/*.md
facts.json
citations.json
```

Rules:

- Stable output paths.
- Stable section IDs.
- Stable manifest hashes.
- No generated claims.
- No timestamps that break deterministic builds unless normalized.
- `llms.txt` is reserved in the manifest as a future artifact but not generated in slice one.
- `chunks.ndjson` is not required in slice one.

`filing.md` and `sections/*.md` are source-derived artifacts. They do not need per-sentence citations because the artifact itself is a representation of the source filing.

Any extracted fact, metric, comparison cell, API result, or answer must carry structured provenance.

## Citation Contract

No public value without citation provenance.

A cited value must carry:

- Company identity.
- Filing identity.
- Source document URL or local source reference.
- Filing form and date.
- Period metadata.
- Concept or table/section reference.
- Evidence anchor when available.
- Extraction status.

Allowed statuses:

- `cited`: registry-approved concept or fixture-approved table extraction with source provenance.
- `unverified_cited`: search-resolved concept value with source provenance, match reason, score, and warning.
- `missing`: no acceptable source value.
- `unsupported`: source exists but cannot support the requested claim or formula.

`unverified_cited` values are allowed only behind an explicit experimental option. They must not silently render as normal facts, and they must not feed derived metrics in slice one.

## Metric Model

The metric registry is explicit and curated. It is the authority for normal public values.

Slice one supports an analyst performance bundle:

- revenue
- gross profit
- operating income
- net income
- operating cash flow
- capital expenditures
- cash and equivalents
- debt
- shares

The registry must model direct and derived metrics from day one.

Direct metrics:

- Resolve through approved concepts or approved S-1 table extractors.
- Return `cited`, `unverified_cited`, `missing`, or `unsupported`.

Derived metrics allowed in slice one:

- Same-period ratios from directly cited components, such as gross margin and operating margin.
- Simple same-period arithmetic rollups, such as free cash flow from operating cash flow minus capital expenditures.

Derived metric rules:

- Every component must have its own citation.
- If any required component is missing, the derived metric is `missing`.
- Missing derived metrics include formula, missing components, and any available component citations.
- No partial derived values.
- No LTM or trailing-period calculations in slice one.

## Concept Resolution

Concept resolution has two lanes.

### Curated Lane

The curated registry maps metrics to approved concepts, aliases, units, expected sign, and allowed statement context. This lane produces normal `cited` values.

### Search Lane

Concept search may return values only as `unverified_cited`, and only behind an explicit experimental option. Search-resolved values include:

- Matched concept.
- Match reason.
- Match score or rank.
- Source fact citation.
- Warning that the value is not registry-approved.

Search-resolved values cannot feed derived metrics in slice one. Promotion to curated mappings is a later feature and must require tests and review.

LLM-assisted concept mapping is not implemented in slice one. The architecture may leave an interface for later resolvers, but the implementation must not include dormant fake behavior.

## Core Architecture

vNext should have a small typed core with boring adapters.

Suggested package shape:

```text
edgarpack_next/
  __init__.py
  cli.py
  api.py
  core/
    identity.py
    filings.py
    pack.py
    cite.py
    audit.py
  sec/
    client.py
    source.py
    companyfacts.py
    s1_tables.py
  artifacts/
    models.py
    writer.py
    manifest.py
  metrics/
    registry.py
    resolve.py
    derive.py
  render/
    tables.py
    errors.py
  testing/
    fixtures.py
```

Core services own behavior:

- `FilingsService`: resolve identity and list filings.
- `PackService`: build deterministic artifacts from source documents.
- `CitationService`: resolve direct and derived metric results.
- `AuditService`: validate pack structure and citation integrity.

Adapters translate:

- CLI parses user intent and renders output.
- API validates request/response and calls the same services.

Adapters must not contain financial logic, source parsing logic, metric formulas, or citation rules.

## Error And Missing-State Design

Errors should distinguish:

- Invalid user input.
- Unknown company.
- Filing not found.
- Source fetch failure.
- Unsupported filing shape.
- Metric not in registry.
- Metric present only through experimental concept search.
- Missing component for derived metric.
- Citation integrity failure.

CLI output should be terse but explanatory. JSON/API output should be structured enough for agents to recover without scraping text.

## Validation Gates

Every vNext behavior must be covered offline first, then live-smoked before milestone sign-off.

Required offline gates for slice one:

- Fixture/golden pack tests for NVDA, AAPL, and Cerebras S-1.
- Pack determinism test: same fixture input produces byte-stable artifact hashes.
- Citation invariant tests: public values are `cited`, `unverified_cited`, `missing`, or `unsupported`; no raw number escapes without provenance.
- Metric registry tests for the analyst performance bundle.
- Derived metric component-citation tests.
- Missing derived metric diagnostics tests.
- S-1 selected-financial-data fixture extraction tests.
- CLI JSON contract tests for `filings`, `pack`, `cite`, and `audit`.
- API contract tests for build and cite endpoints.
- Ruff for changed code.
- Mypy scoped to `edgarpack_next`.

Required live gates for slice one:

- Resolve NVDA and AAPL through live SEC data.
- Fetch latest relevant 10-K or 10-Q metadata.
- Build or dry-run one pack using live source material.
- Query one cited metric from live source/companyfacts.
- Confirm cache and `EDGARPACK_USER_AGENT` requirements are explicit.

The existing full test suite remains useful for regression awareness, but vNext cutover depends on vNext-specific gates plus selected old-behavior parity checks.

## Cutover Rule

`edgarpack-next` can replace `edgarpack` only after hard gates pass:

- NVDA, AAPL, and Cerebras fixture/golden tests pass.
- Live SEC smoke passes.
- Citation invariants pass.
- Pack determinism passes.
- CLI and API JSON contracts pass.
- Ruff passes.
- Scoped mypy for `edgarpack_next` passes.
- Selected old behavior parity checks pass.
- The user explicitly approves cutover.

Until then, both commands coexist.

## Migration Philosophy

The old implementation is a case study, not a template.

Preserve:

- Deterministic packs.
- Primary-source orientation.
- Cited values and derived component citations.
- SEC cache/user-agent discipline.
- Useful CLI workflows.
- Existing fixture lessons.

Cut:

- Flat, crowded command grammar.
- API/web/demo surfaces that publish hardcoded supported claims.
- Self-heal behavior that silently changes trust status.
- Large orchestrators that mix source fetch, business logic, rendering, and diagnostics.
- Model or LLM flows that can generate uncited claims.
- Compatibility for its own sake.

## Implementation Sequence

1. Create isolated worktree and branch.
2. Add `edgarpack_next` package and `edgarpack-next` entry point.
3. Add fixture scaffolding for NVDA, AAPL, and Cerebras S-1.
4. Write failing artifact model and determinism tests.
5. Implement minimal pack writer.
6. Write failing metric registry and citation model tests.
7. Implement direct metric citation for mature SEC filers.
8. Add derived metric tests and implementation for ratios and simple arithmetic.
9. Add S-1 selected-financial-data fixture tests and implementation.
10. Add Typer CLI commands and Rich rendering.
11. Add minimal API wrapper over the same services.
12. Add live SEC smoke.
13. Run vNext gates and selected full-suite checks.

No production code should be written before a failing test for that behavior.

## Open Decisions For The Implementation Plan

These are narrow enough to decide while writing the implementation plan:

- Exact fixture file layout under `tests/fixtures/vnext/`.
- Whether the API lives at `edgarpack_next/api.py` initially or a small `edgarpack_next/api/` package.
- Exact Typer command nesting for API startup.
- Whether Typer and Rich are main dependencies or an optional `vnext` extra during the proving phase.

These are not open:

- vNext is a clean rewrite.
- vNext package is `edgarpack_next`.
- vNext command is `edgarpack-next`.
- CLI-first evidence compiler is the product surface.
- Minimal API wrapper is included.
- Web/demo/LLM-heavy surfaces are parked.
- NVDA, AAPL, and Cerebras S-1 are the first canonical fixtures.
- No uncited public values.
