# Rebuild Plan

## Current Decision

The rebuild path is now a full clean rewrite in parallel with the current implementation.

This supersedes the earlier Reforge assessment recommendation for a hybrid targeted refactor. That earlier recommendation was technically conservative because the existing CLI/core test suite is healthy. The user has explicitly chosen a clean rewrite to cut accidental architecture and AI-generated slop while preserving validated learning.

Approved design spec:

- `docs/superpowers/specs/2026-04-24-edgarpack-vnext-clean-rewrite-design.md`

## Chosen Path

Clean rebuild in an isolated worktree and branch:

1. Create a new `edgarpack_next` package beside the existing `edgarpack` package.
2. Add a new `edgarpack-next` console command.
3. Treat old code as evidence, not the vNext architecture.
4. Reuse only reviewed leaf utilities such as SEC transport/cache helpers, URL helpers, HTML cleaning primitives, and token counters.
5. Preserve behavior through fixture/golden tests, live SEC smoke, and selected old-behavior parity checks before any cutover.

## Why This Beats Alternatives

- The goal has changed from conservative stabilization to deliberate product-quality reset.
- A clean package avoids dragging the old `cli.py`, query orchestrator, self-heal paths, API/demo workflows, and mixed command grammar into the new design.
- Parallel vNext keeps the current validated product usable while the rewrite earns trust.
- The rebuild still respects Reforge discipline: no behavior is ported without evidence and validation.

Rejected alternatives:

- In-place refactor: too likely to preserve old architectural grooves.
- Hybrid command-ergonomics pass only: useful, but no longer ambitious enough for the user's stated goal.
- Replacing the current `edgarpack` command immediately: too risky before vNext passes hard gates.
- Separate repo: cleaner isolation, but weaker access to current fixtures, tests, and migration evidence.

## vNext Product Surface

Primary surface: CLI-first evidence compiler.

Temporary command:

- `edgarpack-next`

Package:

- `edgarpack_next`

Command language:

- `filings`: inspect filings.
- `pack`: build deterministic pack artifacts.
- `cite`: return cited facts.
- `audit`: inspect pack and citation integrity.
- Later: `compare`, `trace`, corpus search.

Secondary surface:

- Minimal API wrapper over the same core services.
- API may create pack builds, read build status/results, and query cited facts.
- API must not own business logic or publish seeded/demo claims.

## First Vertical Slice

Scope:

- SEC 10-K, 10-Q, and S-1.
- NVDA, AAPL, and Cerebras S-1 canonical fixtures.
- Deterministic pack artifacts:
  - `manifest.json`
  - `filing.md`
  - `sections/*.md`
  - `facts.json`
  - `citations.json`
- Analyst performance bundle:
  - revenue
  - gross profit
  - operating income
  - net income
  - operating cash flow
  - capital expenditures
  - cash and equivalents
  - debt
  - shares
- Same-period derived metrics:
  - ratio metrics such as gross margin and operating margin
  - simple arithmetic rollups such as free cash flow
- S-1 selected-financial-data extraction only when fixture-backed.

Explicitly out of scope:

- Next.js web.
- China Lens finding workflow.
- HKEX/SSE/CNINFO.
- `llms.txt` generation.
- OCR/vector/auth.
- LLM-generated claims.
- Learned/self-heal promotion workflow.
- Compatibility aliases for old commands.

## Validation Gates

Offline gates:

- Fixture/golden pack tests for NVDA, AAPL, and Cerebras S-1.
- Pack determinism tests.
- Citation invariant tests.
- Metric registry tests.
- Derived metric component-citation tests.
- Missing derived metric diagnostics tests.
- S-1 selected-financial-data extraction tests.
- CLI JSON contract tests.
- API contract tests.
- Ruff.
- Scoped mypy for `edgarpack_next`.

Live gates:

- Resolve NVDA and AAPL via live SEC data.
- Fetch latest relevant 10-K or 10-Q metadata.
- Build or dry-run one live pack.
- Query one cited live metric.
- Verify cache and `EDGARPACK_USER_AGENT` behavior is explicit.

Cutover gates:

- All vNext offline and live gates pass.
- Selected old-behavior parity checks pass.
- User explicitly approves replacing `edgarpack` with vNext.

## First Implementation Milestone

Milestone 1: vNext spine scaffolding and deterministic artifact/citation contracts.

Deliverables:

- Isolated worktree/branch.
- `edgarpack_next` package.
- `edgarpack-next` entry point.
- Initial Pydantic models for filings, packs, citations, metrics, and build/audit results.
- Fixture loader scaffold for `tests/fixtures/vnext/`.
- Failing tests first for determinism and citation invariants.

Stop before implementation if:

- Fixture source material is insufficient for NVDA, AAPL, or Cerebras.
- Adding Typer/Rich introduces dependency churn that cannot be justified by tests.
- New evidence shows the first slice is too broad and must be split.

## Exact Next Prompt For Implementation Planning

Use this:

```text
Use Superpowers writing-plans for the approved Reforge clean rewrite. Write the implementation plan for docs/superpowers/specs/2026-04-24-edgarpack-vnext-clean-rewrite-design.md. The plan must be TDD-first, create edgarpack_next and edgarpack-next in an isolated worktree, preserve the old implementation as evidence only, and implement the first vertical slice: SEC 10-K/10-Q/S-1 fixtures, deterministic pack artifacts, cited analyst performance metrics, simple derived metrics with component citations, S-1 selected-financial-data extraction, CLI commands filings/pack/cite/audit, and a minimal API wrapper. Include exact files, test commands, expected failures, validation gates, and stop points.
```

## China/HK Gold-Standard Track - 2026-04-27

This track should be treated as a separate hardening lane from the clean SEC-first vNext slice above. China/HK should not be bolted onto SEC CompanyFacts as an afterthought. It needs a shared citation/provenance contract that can represent SEC, HKEX, SSE, and CNINFO documents without fake source identifiers.

## China/HK Path Decision

Recommended path: harden the current CLI-first China/HK vertical slice before reviving China Lens API/web.

Why:

- The MiniMax/Zhipu HKEX fixture path already proves valuable analyst output.
- The critical gap is trust presentation: source provenance and citation rendering, not UI.
- SSE sectionization/translation is useful, but it must be connected to the same cited facts/query contract before it becomes analyst-grade.
- API/web still contains seeded mock/demo evidence and should not be the next trust surface.

## Target China Pack Contract

Every China/HK extracted fact should carry:

- `exchange`: `HKEX`, `SSE`, `SZSE`, `CNINFO`, or similar source family.
- `issuer_id`: stock code or filing-system identifier.
- `filing_type`: prospectus, annual report, interim report, circular, or equivalent.
- `source_url` or local source file pointer.
- `source_document_title`.
- `reporting_currency` and `accounting_standard`.
- `section_id`.
- `chunk_id`.
- `page_start` and `page_end` when available.
- matched source label or short text span.
- extracted numeric value and normalized numeric value.
- extraction method: regex, table parser, OCR, LLM fallback, or manual fixture.
- confidence/status and validation warnings.

CLI citation output should render these fields directly. It should not manufacture SEC archive URLs, fake CIK-style IDs, or placeholder filing dates for HKEX/SSE documents.

## China/HK Fixture Ladder

Use a small but representative ladder:

1. MiniMax HKEX IPO prospectus, already committed.
2. Zhipu HKEX IPO prospectus, already committed.
3. Tencent HKEX annual report.
4. Meituan HKEX annual report.
5. One SSE/STAR prospectus.
6. Optional later: one CNINFO annual or interim report.

Each fixture should have goldens for:

- section boundaries.
- extracted financial facts.
- reporting currency/accounting standard.
- page/chunk-backed citations.
- derived metric component citations.
- CLI query output.
- compare output when cross-company comparison is expected.
- translation numeric/table preservation when translation is involved.

## First China/HK Milestone

Milestone 1: HKEX citation/provenance repair for MiniMax and Zhipu.

Deliverables:

- Add or extend China citation/fact models without changing unrelated SEC behavior.
- Enrich existing HKEX `facts.json` generation or fixture metadata with source document, page/section/chunk provenance.
- Update HKEX query output so MiniMax/Zhipu citations are HKEX-native and auditable.
- Keep existing numeric outputs stable for MiniMax/Zhipu.
- Add tests that fail on SEC-style HKEX citation URLs and placeholder filing dates.
- Fix the `r_and_d_expense` alias gap or explicitly mark it out of scope with a bead.

Validation:

- `uv run pytest tests/test_china_query_hk.py tests/test_china_query_eval.py tests/test_hk_extract.py tests/test_hk_multi_year.py -q`
- Manual `uv run edgarpack query minimax ... --citations footer`
- Manual `uv run edgarpack query zhipu ... --citations footer`
- Manual `uv run edgarpack compare minimax zhipu ... --currency both`

Milestone 2: mature HKEX annual report shape.

Deliverables:

- Add Tencent and Meituan annual-report fixtures.
- Support annual-report sectioning and financial table extraction separately from prospectus assumptions.
- Query core analyst metrics with HKEX-native citations.

Milestone 3: SSE facts/query parity.

Deliverables:

- Add one real SSE/STAR fixture pack.
- Extract the same core analyst metric bundle where disclosed.
- Render citations through the same China Pack contract.
- Keep translation validators in the publishing gate.

## Exact Next Prompt For China/HK Planning

Use this:

```text
Use Reforge assessment context and write the implementation plan for China/HK gold-standard hardening in EdgarPack. Do not revive the web/API first. Plan milestone 1 only: repair HKEX MiniMax/Zhipu citation/provenance so query output is HKEX-native, page/section/chunk-backed, and no longer renders fake SEC archive URLs or placeholder filing dates. Preserve existing numeric outputs. Include exact files, failing tests first, fixture updates, CLI checks, validation gates, and any bead follow-ups for out-of-scope work.
```
