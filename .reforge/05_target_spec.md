# Target Spec

## Product Purpose

EdgarPack should be a CLI-first evidence compiler for public-company filings: it builds deterministic Packs from primary documents and returns cited facts, formulas, diffs, and comparisons without inventing unsupported claims.

## Primary User

Financial researcher or agent who needs primary-source-backed answers and reusable filing artifacts.

## Core User Journeys

1. Build a Pack from an SEC filing.
   - Input: ticker/name/CIK plus form/accession.
   - Output: `manifest.json`, `filing.md`, `sections/*.md`, `facts.json`, and `citations.json`.
   - Required proof: deterministic hashes and stable section IDs.
   - vNext note: reserve `llms.txt` in manifest metadata, but do not generate it in slice one.

2. Query a metric.
   - Input: ticker/name/CIK, metrics, period.
   - Output: table/JSON with values, citations, formulas, warnings, and links.
   - Required proof: every non-null value is a `CitedValue` or `DerivedValue` with source provenance.

3. Compare companies.
   - Input: multiple companies, metrics, period, currency mode.
   - Output: side-by-side table with fiscal-year/currency warnings.
   - Required proof: HKEX and SEC paths preserve native source provenance.

4. Diff filings.
   - Input: latest/prior filing packs or explicit pack paths.
   - Output: ranked section/paragraph changes, with noise suppression.
   - Required proof: fixture tests and manual diff smoke.

5. Chinese filing support.
   - HKEX/SSE only where a primary document or committed fixture exists.
   - Unsupported findings must stay unsupported.
   - Required proof: golden fixtures and chunk-backed citations.
   - vNext note: China Lens is not in the first clean-rewrite slice.

## Core Agent Journeys

- Start with `AGENTS.md`, `README.md`, `docs/TESTING.md`, and `docs/learn/README.md`.
- Use `bd ready` / `bd show` for issue context.
- Add failing tests before behavioral changes.
- Run scoped tests plus full `pytest -q` when changing shared query/pack behavior.
- Keep demo or generated facts out of source unless they come from committed fixtures.

## Core Domain Objects

- Filing identity: CIK/accession/form/filing date/company, plus stock code/exchange for non-SEC.
- Pack: primary source URL, full markdown, sections, hashes, llms.txt, optional chunks/assets/XBRL.
- Citation: source filing, concept/section/chunk, filing URL or evidence chunk ID, period metadata.
- Metric result: `CitedValue`, `DerivedValue`, list of values for series, diagnostics.
- Evidence chunk: document ID, page range, source text, translated text, extraction method, confidence.
- Finding: claim text, claim type, key numbers, citations, support status.

## Required Behaviors

- No supported finding without citations.
- Numeric claims require numeric overlap with cited evidence.
- Missing facts return `None`/diagnostics, not guessed values.
- LTM values must carry `mrp`, `lfy`, and `mrp_prior` component citations when non-null.
- Pack builds must remain deterministic.
- Network SEC access must respect User-Agent and cache/rate-limit behavior.
- HKEX annual-report support must not be claimed until annual-report fixtures exist.

## Explicit Non-Goals

- Free-form uncited claim generation.
- Production China Lens workspace unless explicitly revived.
- Web demo mode with hardcoded supported claims.
- Rewrite-by-volume without evidence, behavior tests, or cutover gates.
- Strict mypy as a release gate until a scoped baseline is chosen.

## UX Principles

- CLI output should make verification easy: citations, formulas, warnings, and reproduction commands should be close to the value.
- Empty or unsupported states should say what is missing and how to fix it.
- vNext command names should be task-literal from a user's point of view:
  - `filings`: inspect available filings.
  - `pack`: build deterministic pack artifacts.
  - `cite`: return cited facts and diagnostics.
  - `audit`: inspect pack integrity.
  - Later `compare` and `trace` should keep the same evidence-verb grammar.
- Do not optimize vNext around compatibility aliases in the first slice. Add aliases only after the new grammar proves itself.
- Avoid exposing implementation names as the primary interface. Names like `learned`, `which`, and `comps` are evidence about what confused the current surface, not names to carry forward by default.
- Web stays out of the alpha. The API, if present, is a thin wrapper over the same core contracts.

## Reliability And Privacy Constraints

- Use primary documents and committed fixtures.
- Do not call model providers in tests without explicit gating and keys.
- Use cache directories under writable paths in sandboxed/agent runs.
- Avoid new dependencies unless they reduce real complexity.

## What Should Be Removed Or Quarantined

- Web sample data that embeds supported claims outside fixture provenance.
- Stale backlog statements that contradict current code.
- Any future generated finding flow that can publish without chunk IDs.
