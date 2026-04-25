# Target Architecture

## Chosen Path

Full clean rewrite in parallel with the current implementation.

This supersedes the earlier conservative recommendation for targeted refactor. The old implementation passed broad tests and contains validated domain learning, but it also carries accumulated surface area, parked prototypes, and command/architecture drift. vNext should preserve the learning, not the shape.

## Package Boundary

Create a new package and command:

- Package: `edgarpack_next`
- Command: `edgarpack-next`

The existing `edgarpack` package remains available as:

- behavioral reference
- fixture source
- parity oracle
- reviewed leaf-utility source

It must not become the vNext orchestration layer.

## Layers

`edgarpack_next.models`

- Pydantic contracts for company identity, filings, packs, sections, citations, metrics, derived facts, missing facts, audit results, and build results.

`edgarpack_next.sec`

- SEC source adapters.
- Fixture provider for deterministic tests.
- Live provider wrapping reviewed old SEC client/cache/submissions/companyfacts leaves.
- Narrow HTML-to-markdown and S-1 selected-financial-data helpers.

`edgarpack_next.artifacts`

- Deterministic pack writer.
- Stable artifact layout:
  - `manifest.json`
  - `filing.md`
  - `sections/*.md`
  - `facts.json`
  - `citations.json`

`edgarpack_next.metrics`

- Curated metric registry.
- Direct companyfacts resolver.
- Derived metric engine with component citations.
- Experimental concept search returning only `unverified_cited` values.

`edgarpack_next.core`

- Use-case services:
  - filings
  - pack
  - cite
  - audit

`edgarpack_next.cli`

- Thin Typer command adapter.
- Commands: `filings`, `pack`, `cite`, `audit`.
- Rich may be used for human output; JSON output remains deterministic.

`edgarpack_next.api`

- Minimal FastAPI wrapper over the same services.
- No independent fact generation, seeded claims, or web-demo path.

## Allowed Reuse

KEEP/PORT IDEA:

- SEC client/cache behavior.
- SEC ticker/submissions/companyfacts helpers.
- URL construction patterns.
- HTML cleaning primitives.
- Token-counting utilities if needed.
- Existing fixtures and expected edge cases.

REWRITE:

- CLI command surface.
- pack compiler orchestration.
- query/citation service orchestration.
- period/metric presentation surface.
- API layer.

DELETE/PARK:

- Web/demo claims from the alpha path.
- old sectionizer/query renderers as vNext dependencies.
- China Lens services from the first slice.
- learned/self-healing promotion workflow until after curated registry behavior is proven.

## Data Flow

Pack build:

1. Resolve company through fixture or live source provider.
2. Select filing by form/accession/latest policy.
3. Fetch primary document text.
4. Normalize to markdown.
5. Split into stable sections.
6. Write deterministic artifacts and manifest.

Citation:

1. Resolve company and filing.
2. Load companyfacts or S-1 selected-financial-data fixture.
3. Resolve only registry-approved metrics by default.
4. Return `cited`, `derived`, `missing`, `unsupported`, or explicit `unverified_cited`.
5. Derived metrics require all components to be cited or derived from cited components.

## Source Scope

First slice:

- SEC 10-K
- SEC 10-Q
- SEC S-1
- NVDA fixture
- AAPL fixture
- Cerebras S-1 fixture

Out of scope:

- HKEX/SSE/CNINFO.
- China Lens findings.
- web UI.
- OCR/vector/auth.
- `llms.txt` generation.

## Command Grammar

Use evidence verbs:

- `edgarpack-next filings AAPL --form 10-K`
- `edgarpack-next pack AAPL --form 10-K --last 3`
- `edgarpack-next cite AAPL revenue --period lfy`
- `edgarpack-next audit packs/AAPL/2024-10K`

Later:

- `edgarpack-next compare NVDA AMD INTC --on revenue,gross_margin`
- `edgarpack-next trace AAPL risk-factors --since 2020`

Do not carry forward unclear names just for continuity. Add compatibility aliases only after the new grammar is stable and tested.

## Validation

Offline gates:

- vNext unit tests.
- fixture-backed pack golden tests.
- citation invariant tests.
- S-1 table extraction tests.
- CLI JSON contract tests.
- API contract tests.
- ruff for vNext code.
- scoped mypy for `edgarpack_next`.

Live gates:

- SEC company resolution.
- latest 10-K/10-Q filing metadata.
- one live primary-document pack build.
- one live cited metric query.
- explicit User-Agent/cache behavior.

Cutover gates:

- vNext gates pass.
- selected old parity checks pass.
- old implementation remains callable until explicit user approval.
- user approves replacing `edgarpack` with vNext.
