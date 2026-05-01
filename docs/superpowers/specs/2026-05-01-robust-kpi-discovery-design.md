# Robust KPI discovery design

**Date**: 2026-05-01
**Status**: Approved for SEM-34 implementation planning
**Issue**: SEM-34, "Fix KPI discovery prompt truncation hiding later HOOD 10-K metrics"
**Scope**: SEC `edgarpack which` discovery for 10-K and 10-Q packs. The same architecture should be portable to HKEX/SSE later, but China Lens implementation is out of scope for this issue.

## Problem

`edgarpack which` currently treats KPI discovery as one large model task per filing. It selects likely sections, concatenates their markdown, trims the first roughly 60,000 characters, asks an LLM to find every operating KPI, validates source substrings, and persists rows to `company_kpis`.

That shape fails for real filings. In HOOD, the later 10-Ks contain Funded Customers, Total Platform Assets or Assets Under Custody, Net Deposits, ARPU, MAU, and other recurring metrics. The command still showed only FY2021 because the only successful cache rows came from the 2022-filed 10-K. The later annual packs were valid, but discovery did not turn their text into normalized rows.

The specific local root cause was prompt starvation. Newer HOOD Item 1 sections are large enough to consume the entire prompt budget before the MD&A KPI tables reach the model. A simple section reorder helps, but it is not robust enough. It still relies on one prompt, one model call, and one chance for the model to search, classify, extract, normalize, and reconcile.

## Goal

Replace single-prompt KPI discovery with a staged, evidence-first pipeline:

```text
pack sections
  -> deterministic evidence locator
  -> bounded candidate windows
  -> model extraction/classification
  -> validation firewall
  -> cross-filing slug reconciler
  -> company_kpis rows and diagnostics
```

The key shift: models should reason over small, grounded evidence windows. They should not be responsible for finding the evidence inside a full filing slice.

## Non-goals

- Do not loosen citation requirements. Every persisted KPI value still needs a source substring that exists in the pack text.
- Do not invent company facts, fixtures, or fallback values.
- Do not auto-build missing packs from `which`.
- Do not make nested agent execution part of extraction. KPI discovery needs a text-in/text-out model backend.
- Do not replace `query` period logic or discovered-KPI lookup semantics except where diagnostics need to reflect the new cache state.
- Do not add a vector database or embeddings for SEM-34. They are not needed for this failure mode.

## Success Criteria

1. A long low-signal section cannot crowd out a later KPI table or MD&A KPI paragraph.
2. HOOD-style annual filings produce a progression-shaped output when the source filings contain recurring KPIs.
3. A model timeout or malformed response on one candidate window does not mark the whole filing as permanently empty.
4. `--format json` explains coverage at every stage: candidate count, model attempts, accepted rows, rejected rows, retryable failures, and final contributing filings.
5. The table view remains human-readable and keeps the partial-coverage note from SEM-19 and SEM-33.
6. Existing cached `company_kpis` rows remain readable.

## Architecture

### Filing Preflight

`discover_kpis` still walks eligible pack records from `PackRegistry`. `_discover_pack` becomes an orchestrator for one accession:

1. Load `manifest.json`.
2. Check cache state for the current discovery version.
3. Run or replay the locator output.
4. Run model extraction only for uncached candidate windows.
5. Validate and persist accepted KPI rows.
6. Return a structured `PackDiscoveryResult`.

The current `company_kpis` table remains the final row store. New intermediate state lives beside it in `LearnedRegistry`, not in pack directories.

### Evidence Locator

Add a deterministic locator that reads selected section files and returns `KpiCandidateWindow` objects. It does not decide final KPI identity. It only says, "this text region is likely to contain operating KPI evidence."

Candidate signals:

- Section IDs or titles containing `key metric`, `key performance`, `operating data`, `segment`, `management discussion`, or `business metrics`.
- Table-like rows with a non-GAAP label plus one or more numeric cells.
- Prose sentences near phrases such as users, customers, subscribers, accounts, assets, deposits, bookings, volume, retention, stores, locations, active, paying, funded, platform, marketplace, cohort, take rate, ARPU, AUC, MAU, DAU, ARR, NRR, RPO.
- Repeated labels across periods or adjacent filings.
- Definition paragraphs that introduce a metric name followed by values in the same or nearby section.

Candidate window shape:

```python
@dataclass(frozen=True)
class KpiCandidateWindow:
    candidate_id: str
    cik: str
    accession: str
    section_id: str | None
    chunk_id: str | None
    window_text: str
    label_hint: str | None
    value_hints: tuple[str, ...]
    signal_names: tuple[str, ...]
    char_start: int
    char_end: int
```

Window size should be bounded, roughly 1,500 to 4,000 characters. A filing can have many windows, but each model prompt stays small. Candidate IDs are stable hashes of accession, section ID, offsets, and locator version.

The locator should use `optional/chunks.ndjson` when present. If chunks are missing, section offsets and section IDs are still valid evidence locators.

### Model Extraction

Add a model client abstraction used by both catalog extraction and free-form discovery:

```python
class KpiModelClient(Protocol):
    def complete_json(self, prompt: str, *, timeout: int) -> str | None:
        ...
```

The default backend must be non-agentic. Acceptable backends:

- Direct API backend when configured, using an explicit extraction model and strict JSON output.
- `claude --bare --tools "" -p` as a local CLI backend.
- `codex exec` only if this environment exposes a pure text mode that disables tools. If not, it should be treated as unavailable for KPI extraction.

Model extraction prompt:

- Input: one or a small batch of candidate windows.
- Output: strict JSON with extracted KPI items and rejection reasons.
- Task: classify operating KPIs, normalize names and units, extract values, cite exact substrings, and label confidence.
- Constraint: no outside knowledge, no computations unless the value appears directly in the window, no GAAP-only line items.

The model should not receive full filings. If a window is too broad, the locator is at fault.

### Validation Firewall

Every model item passes through deterministic validation before persistence:

- `source_substring` must normalize-match inside the candidate window.
- The numeric value or value string must be present inside `source_substring` or in the same table row window.
- `section_id` must be one of the selected source sections when provided.
- `unit` and `magnitude` must be in the allowed enums.
- Period metadata comes from the pack unless the cited source explicitly names a different period.
- Duplicate slugs inside one filing collapse to the highest-confidence row unless they represent distinct metrics.

Rejected rows are counted in diagnostics. They are not silently ignored.

### Cross-Filing Reconciler

After per-filing extraction, run a company-level reconciler over the candidate metric names and accepted extracted rows. This is where model intelligence is useful.

Inputs:

- Existing company slugs from `company_kpis`.
- New extracted display names and definitions.
- Units, magnitudes, value ranges, form types, fiscal periods.
- Aliases already attached to aggregates.

Outputs:

- Stable slug for each accepted row.
- Alias list for naming drift.
- Merge decisions with reasons.
- Rejection when two names look similar but units or definitions conflict.

Examples:

- `Assets Under Custody (AUC)` and `Total Platform Assets` may map to one stable company KPI only if the definitions or source wording support the continuity.
- `Monthly Active Users` and `Funded Customers` must never merge just because both are counts.
- `ARPU` and `Average Revenues Per User` should merge when source wording supports it.

The reconciler can be deterministic first, model-assisted second. Deterministic normalization covers obvious acronym/name pairs. The model-assisted path should operate on compact metadata, not source filings.

### Cache Model

Keep `company_kpis` as the final table. Add intermediate cache tables:

```text
company_kpi_discovery_runs
  cik
  accession
  discovery_version
  pack_fingerprint
  locator_status
  extractor_status
  reconciler_status
  started_at
  completed_at
  retryable

company_kpi_candidates
  cik
  accession
  discovery_version
  candidate_id
  section_id
  chunk_id
  label_hint
  value_hints_json
  signal_names_json
  window_text
  char_start
  char_end

company_kpi_rejections
  cik
  accession
  discovery_version
  candidate_id
  stage
  reason
  raw_payload
```

Negative results should be versioned. A `__no_kpis_found__` sentinel is valid only when:

- The locator found no candidate windows, or
- The locator found candidates, model extraction completed, and every candidate was rejected for deterministic reasons.

A timeout, backend failure, parse failure, or model unavailability is not an empty filing. It is retryable.

### CLI and JSON Diagnostics

Table output should stay compact. JSON should expose the full audit trail:

```json
{
  "diagnostics": {
    "partial": true,
    "coverage_note": "...",
    "filings": [
      {
        "accession": "...",
        "status": "discovered",
        "candidate_count": 12,
        "model_attempts": 3,
        "accepted_rows": 7,
        "rejected_rows": 5,
        "retryable": false,
        "resume_action": null
      }
    ]
  }
}
```

The default table can include only the existing coverage note. A future `--debug-discovery` flag can print candidate and rejection summaries, but SEM-34 does not need a new CLI flag if JSON diagnostics are clear.

## Implementation Plan

### Phase A: Preserve Current Behavior While Adding Boundaries

- Add dataclasses for candidate windows, extraction payloads, and stage diagnostics.
- Add the model-client abstraction.
- Keep the current prompt path available behind the same public API while tests for the new path are introduced.

### Phase B: Build the Locator

- Implement section ordering as a small prerequisite.
- Add table/prose candidate scanning.
- Add dedupe by overlapping offsets and repeated labels.
- Add tests where a long Item 1 section appears before a later MD&A KPI table. The locator must still return the MD&A candidate.

### Phase C: Extract From Candidates

- Replace full-slice discovery prompts with candidate-window prompts.
- Batch nearby windows conservatively to reduce model calls without making prompts large.
- Add strict JSON parser and rejection accounting.
- Ensure backend selection refuses agentic `codex exec` unless a pure text mode is available.

### Phase D: Reconcile Slugs Across Filings

- Add deterministic alias matching.
- Add model-assisted reconciliation for ambiguous naming drift.
- Persist aliases and merge reasons.
- Add HOOD-style tests for AUC / Total Platform Assets, ARPU / Average Revenues Per User, and non-merges like MAU vs Funded Customers.

### Phase E: Cache and Diagnostics

- Add registry migrations for runs, candidates, and rejections.
- Version cache keys by `discovery_version` and pack fingerprint.
- Update `DiscoveryFilingStatus.to_json`.
- Keep existing `company_kpis` consumers working.

### Phase F: Verification

- Focused tests:
  - Locator catches KPI rows beyond the old 60k head trim.
  - Model extraction never persists a value without an exact substring.
  - Model timeout is retryable, not empty.
  - Reconciler merges supported aliases and rejects unsupported merges.
  - JSON diagnostics expose stage-level counts.
- Fixture tests:
  - Use committed primary-source snippets from HOOD annual filings with accession and section provenance.
  - Do not invent real-company KPI facts.
- Full gate:
  - `scripts/symphony_quality_gate.sh`
  - `uv run edgarpack which HOOD --format json` smoke against local packs when model backend is available, reported as non-blocking if credentials/backend are unavailable.

## Risks and Design Responses

**Risk: Candidate locator over-selects noisy finance rows.**
Response: The locator is allowed to over-select. The model classifier and deterministic GAAP exclusions filter candidates before persistence. Diagnostics count rejected candidates.

**Risk: Model calls become too many.**
Response: Cache locator candidates and extraction results per candidate ID. Batch windows by section when small. Cap attempts per filing with a diagnostic that says extraction was incomplete.

**Risk: Naming reconciliation merges unlike metrics.**
Response: Require compatible units, source wording, and either deterministic alias confidence or model-assisted rationale. Preserve separate slugs on uncertainty.

**Risk: Stronger model access varies by machine.**
Response: Backend is configurable. Extraction can fail retryably without poisoning cache. Tests mock the model path and do not depend on live credentials.

**Risk: Cache migrations complicate rollback.**
Response: Existing `company_kpis` remains the final source for query resolution. New tables are additive. Rolling back code leaves old final rows readable.

## Out-of-Scope Follow-ups

- HKEX/SSE candidate locator adaptation.
- Direct API provider selection UI.
- Embedding-backed metric search.
- Human review UI for accepted and rejected candidates.
- Automatic pack rebuild with chunks.

## Approval Bar

This design is approved when we agree on three choices:

1. `which` should become a staged discovery system rather than a better single prompt.
2. Models should classify and reconcile bounded evidence windows, not search whole filing slices.
3. Agentic CLI backends are not acceptable for extraction unless tools can be disabled.
