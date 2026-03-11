# Citation Provenance + CLI Audit UX Spec

Status: Drafted for implementation in `edgarpack-snn`  
Last updated: 2026-03-10

## 1. Summary

EdgarPack already returns citation-capable values, but the default CLI experience still separates numbers from evidence and collapses derived traces into prose. This spec upgrades trust and audit speed by:

- adding stable citation and calculation IDs (`C#`, `D#`, `L#`)
- making link selection explicit (`anchor_url` > `viewer_url` > `filing_url`)
- showing warnings where the value appears (not only in JSON)
- introducing structured LTM/LTM-1 audit blocks
- keeping JSON backward-compatible through additive fields only

Primary target: answer both questions in seconds:

1. Where did this number come from?
2. How was this LTM number constructed?

## 2. Current-State Critique (Code-Referenced)

### 2.1 CLI table output is citation-detached

- `query` table prints metric values first and appends a detached `Sources:` footer at the end.
- Source dedupe is text-based (`seen_citations` set of prose strings), not fact-identity-based.
- References:
  - `edgarpack/cli.py` lines 495-530
  - `edgarpack/query/comps.py` lines 65-107

Impact: auditors must map numbers back to sources manually, especially painful with multiple metrics or series.

### 2.2 LTM provenance is prose, not a structured trace

- `DerivedValue.citation` renders LTM lineage as a semicolon-joined sentence.
- No stable role-tagged representation in CLI.
- References:
  - `edgarpack/query/models.py` lines 160-165
  - `edgarpack/query/periods.py` lines 530-577 (actual formula inputs exist but are not rendered structurally in CLI)

Impact: users mentally reconstruct `mrp + lfy - mrp_prior`.

### 2.3 Lean JSON LTM trace is too thin

- `ltm_components` currently exposes only `value` and `accession`.
- Missing component fiscal labels, date windows, form/filed metadata, and preferred links.
- References:
  - `edgarpack/query/models.py` lines 178-187

Impact: downstream audit tooling has insufficient context for fast verification.

### 2.4 Deep links exist but CLI has no explicit link strategy

- Model already supports `filing_url`, `concept_url`, `viewer_url`, `document_url`, `anchor_url`.
- CLI currently emits `viewer_url` only in source footer for single-company output.
- References:
  - `edgarpack/query/models.py` lines 50-130
  - `edgarpack/cli.py` lines 514, 523, 529
  - `docs/QUERY.md` deep-link section (does not document `anchor_url`)

Impact: users cannot predict which URL type they will get, and may miss the best deep link.

### 2.5 Warning surfacing is too distant

- Warnings are computed (`split contamination`, scope caveats, debt sanity) but table output does not surface them near values.
- References:
  - `edgarpack/query/periods.py` lines 545-553
  - `edgarpack/query/financials.py` lines 216-229, 291-299
  - `edgarpack/cli.py` query table branch lacks warning rendering

Impact: high-risk caveats are easy to miss during manual review.

### 2.6 Additional gap found during implementation pass

- Lean auto-component inclusion skipped only `fiscal_period == "LTM"`, so `LTM-1` could leak pseudo-metrics (`mrp`, `lfy`, `mrp_prior`) into top-level metrics.
- Filing records could carry synthetic `fiscal_period` labels (e.g., `LTM-1`) for real accessions when sourced from a derived value.
- References:
  - `edgarpack/query/models.py` lines 271-274 (pre-change)
  - `edgarpack/query/models.py` lines 245-254 (pre-change)

Impact: audit JSON looked noisier and less literal than underlying filings.

## 3. Proposed Citation Model Revision

## 3.1 Stable IDs and registries

Add additive top-level registries in both lean and full JSON:

- `citations`: `{ "C1": {...}, "C2": {...} }`
- `calculations`: `{ "D1": {...}, "L1": {...} }`

Per metric payloads reference IDs, not duplicated prose:

- direct metric: `citation_ids: ["C#"]`
- derived metric: `citation_ids`, `calculation_id: "D#|L#"`, `component_citation_ids`

ID assignment rule:

- `C#` deduped by structural key (CIK + accession + concept + period window + value + fact_id + taxonomy)
- `D#` for non-LTM derived formula records
- `L#` for LTM/LTM-1 records

## 3.2 Best-in-class fields: direct metrics

Each citation record should include:

- filing identity: `accession`, `form_type`, `filed`, `company`, `cik`
- metric identity: `metric`, `concept`, `taxonomy`, `value`, `unit`
- period identity: `period_start`, `period_end`, `period`, `fiscal_year`, `fiscal_period`, `fiscal_label`
- human text: legacy `citation`
- links: `primary_link`, `primary_link_type`, `links` map
- warnings (if present)

## 3.3 Best-in-class fields: derived metrics

Each calculation record should include:

- `id`, `kind` (`derived` or `ltm`)
- `metric`, `formula`
- result payload (`value`, `unit`, `citation_id`)
- component array with role + component citation IDs + value/unit/fiscal/period/accession metadata
- `warnings` (if any)

## 3.4 Best-in-class fields: LTM / LTM-1

For `L#` records, include:

- `ltm_variant`: `ltm` or `ltm-1`
- canonical formula: `mrp + lfy - mrp_prior`
- window: `{start, end}`
- method: `computed` vs fallback modes
- role-tagged component metadata (`mrp`, `lfy`, `mrp_prior`) including fiscal label and preferred link

## 3.5 Link strategy

CLI primary link policy:

1. `anchor_url` when `fact_id` is present
2. else `viewer_url`
3. else `filing_url`

When to show which:

- default table: `primary_link` only
- `--show-links all`: include `anchor_url`, `viewer_url`, `filing_url`, `concept_url`, `document_url` when available
- `--show-links none`: suppress links in human table output

`concept_url` remains important for API/history inspection, not primary for numeric audit.

## 3.6 Backward compatibility

- keep existing keys (`citation`, `filing_url`, `components`, `ltm_components`, etc.)
- add new keys only (no renames/removals)
- keep existing output formats (`json`, `json-full`)
- no mandatory new format for v1

## 4. Proposed CLI Rendering Model Revision

## 4.1 `edgarpack query` default behavior

Default (`--citations inline --show-links primary`):

- render value and marker on same line (`Revenue: $... [C1]` or `[L1]`)
- render warning lines immediately beneath the metric
- render compact inline evidence summary beneath each metric
- for LTM/LTM-1, render compact formula trace with role-tagged citation IDs

## 4.2 Explicit audit mode

`--audit` expands derived/LTM details:

- formula
- calculation window
- per-component rows with value/unit/fiscal label/date range/accession
- preferred deep link
- warnings near relevant component/result

## 4.3 `edgarpack comps` citation ergonomics

Recommended default:

- compact table cells with markers (`[C#]`, `[D#]`, `[L#]`)
- deduped citation registry below table
- deduped calculation registry below table
- warning marker in-cell (`!`) and warning registry below

Avoid full per-cell verbose blocks by default to keep table readable.

## 4.4 Narrow-terminal behavior

When terminal width is narrow:

- switch from wide matrix to company-stacked output
- preserve markers and citation/calculation registries
- wrap long lines with hanging indent (copy/paste safe)

## 4.5 Flag recommendations

Add to `query` and `comps`:

- `--audit` (bool, default `false`)
- `--show-links {primary,all,none}` (default `primary`)
- `--citations {inline,footer,off}` (default `inline`)

Legacy/transition:

- `--citations footer` approximates current detached-sources behavior.

## 5. Concrete CLI Mockups

Values below are schematic fixture-style examples for UX shape, not live market facts.

### 5.1 Direct metric (`edgarpack query AAPL revenue`)

```text
$ edgarpack query AAPL revenue
APPLE INC (CIK: 0000320193)

Revenue: $391.0B [C1]
  [C1] 10-K FY2025 | period 2024-09-29/2025-09-27 | accn 0000320193-25-000010 | filed 2025-11-01
       link(anchor_url): https://www.sec.gov/Archives/.../aapl-20250927.htm#f-1287

Reproduce: edgarpack query 0000320193 revenue --period lfy
```

### 5.2 LTM metric (`edgarpack query NVDA revenue --period ltm --audit`)

```text
$ edgarpack query NVDA revenue --period ltm --audit
NVIDIA CORP (CIK: 0001045810)

Revenue: $95.0B [L1]
  [L1] LTM = mrp[C2] + lfy[C3] - mrp_prior[C4]
     window: 2024-01-29..2025-04-27
     mrp[C2] value=35.1B USD | Q1 FY2026
     lfy[C3] value=60.9B USD | FY FY2025
     mrp_prior[C4] value=26.0B USD | Q1 FY2025
  [C2] 10-Q Q1 FY2026 | period 2025-01-27/2025-04-27 | accn ...-25-000020 | filed 2025-06-01
       link(anchor_url): https://www.sec.gov/Archives/.../nvda-20250427.htm#f-901
  [C3] 10-K FY FY2025 | period 2024-01-29/2025-01-26 | accn ...-25-000001 | filed 2025-02-18
       link(viewer_url): https://www.sec.gov/ix?doc=/Archives/...
  [C4] 10-Q Q1 FY2025 | period 2024-01-29/2024-04-28 | accn ...-24-000010 | filed 2024-06-01
       link(viewer_url): https://www.sec.gov/ix?doc=/Archives/...
```

### 5.3 Multi-company comps (`edgarpack comps NVDA AMD --metrics revenue,gross_margin --period ltm`)

```text
$ edgarpack comps NVDA AMD --metrics revenue,gross_margin --period ltm
Company                    Revenue          Gross Margin
------------------------  ---------------  ----------------
NVIDIA CORP               $95.0B [L1]      73.6% [D1]
ADVANCED MICRO DEVICES    $24.1B [L2]      49.2% [D2] !

Citations:
  [C1] NVDA 10-Q Q1 FY2026 | period ... | accn ... | filed ...
       link(anchor_url): ...
  [C2] NVDA 10-K FY FY2025 | period ... | accn ... | filed ...
       link(viewer_url): ...
  [C3] AMD 10-Q Q4 FY2025 | period ... | accn ... | filed ...
       link(viewer_url): ...

Calculations:
  [L1] revenue = mrp + lfy - mrp_prior
  [D1] gross_margin = gross_profit / revenue
  [L2] revenue = mrp + lfy - mrp_prior
  [D2] gross_margin = gross_profit / revenue

Warnings:
  - ADVANCED MICRO DEVICES gross_margin: CostOfGoodsAndServicesSold may be broader than CostOfRevenue...
```

## 6. JSON Strategy

## 6.1 Lean JSON (`--format json`)

Additive updates:

- new top-level: `citations`, `calculations`
- per metric: `citation_ids`, optional `calculation_id`, optional `component_citation_ids`
- enrich `ltm_components` with role + fiscal/date/form/accession/link metadata + `citation_id`
- include `warnings` on metrics when present

Keep all existing fields and semantics.

## 6.2 Full JSON (`--format json-full`)

Additive updates:

- same top-level registries (`citations`, `calculations`)
- per metric additive IDs (`citation_ids`, `calculation_id`, `component_citation_ids`)
- include `primary_link`, `primary_link_type`, `links`
- preserve legacy full component embedding

## 6.3 Need a new audit-focused format?

Recommendation: **No for v1**.

Reason:

- additive registries satisfy audit use cases
- avoids parser fragmentation
- retains compatibility for existing consumers

Revisit only if downstream systems require strict normalized schema with zero legacy fields.

## 7. Prioritized Implementation Plan

### Phase 1 (Must-have): Provenance structure + IDs

- Add citation/calculation registries and stable IDs in model serialization
- Implement preferred link selection
- Enrich LTM component metadata
- Ensure filing records reflect source filing periods (not synthetic derived labels)
- Prevent LTM-1 pseudo-component leakage into top-level lean metrics

### Phase 2 (Must-have): Query UX

- Add `--audit`, `--show-links`, `--citations`
- Inline markers + compact inline citation blocks by default
- Structured LTM calculation trace
- Warning placement directly under metric output

### Phase 3 (Must-have): Comps UX

- Cell markers with deduped citation/calculation registries
- Warning cues and warnings section
- Narrow-terminal stacked fallback

### Phase 4 (Nice-to-have): polish and docs

- Expand docs with before/after examples
- Evaluate optional color/styling hints while preserving plain text fidelity

## 8. Acceptance Criteria (Testable)

1. `edgarpack query AAPL revenue` table output shows citation marker inline with value and at least one citation summary block.
2. `edgarpack query NVDA revenue --period ltm --audit` shows explicit formula and role-tagged components (`mrp`, `lfy`, `mrp_prior`) with citation IDs.
3. Warnings for a metric appear directly below the metric line in table output.
4. `edgarpack comps ... --format table` includes cell markers and deduped citation/calculation sections.
5. Narrow terminal path produces readable stacked layout without truncating markers.
6. Lean JSON still includes prior keys and now includes additive `citations` + `calculations`.
7. Full JSON still includes prior keys and now includes additive `citations` + `calculations`.
8. LTM-1 lean output does not auto-inject `mrp`/`lfy`/`mrp_prior` as top-level component metrics.
9. Filing rows in lean JSON use real filing fiscal labels (e.g., `Q1`) even when originating metric is derived `LTM-1`.
10. Existing tests for legacy deep-link fields (`viewer_url`, `document_url`, `concept_url`) continue passing.

## 9. Risks, Tradeoffs, Backward Compatibility

### Risks

- Human table formatting changes can affect brittle text-based scripts.
- More JSON fields increase payload size.
- Deterministic ID assignment must stay stable to avoid flaky snapshots/tests.

### Tradeoffs

- Default inline citations favor audit speed over minimal output.
- `--citations off` and `--citations footer` preserve low-noise and legacy workflows.
- Keeping legacy prose `citation` duplicates information but eases migration.

### Backward compatibility notes

- No removals/renames in `json` or `json-full`.
- New fields are additive.
- Existing consumers that ignore unknown keys remain unaffected.

