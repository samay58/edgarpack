# Founder-Control Research Workflow

Date: 2026-04-28
Status: Approved for spec-only handoff
Scope: Research workflow, not product feature implementation

## Purpose

Use EdgarPack to investigate how founder control has changed among the current top ten technology companies across three anchor years: 2026, 2016, and 2006. The output is a citation-backed research table plus a narrative report. The workflow should prove that EdgarPack can support governance research from primary filings before any reusable `founder-control` command is built.

This is a primary-document workflow. Every factual claim must trace to a filing accession and either a section ID or chunk ID. If a claim cannot be tied to evidence, it remains unresolved rather than becoming prose.

## Approved Decisions

The workflow is research-first. It does not add a new CLI command, dashboard, extractor subsystem, or product surface.

The cohort is the current top ten technology companies, frozen at execution time from one cited market-cap source, then tracked backward to the two historical anchor years. This answers how founder control changed among today's giants. It does not answer which companies dominated each historical era.

The source policy is SEC-first. Include ADRs and foreign private issuers when EdgarPack can cite primary SEC filings such as 20-F or F-1. Do not add non-SEC global acquisition in this version.

The output is a table plus a narrative report. The table is the source of truth; the report summarizes patterns found in that table.

## Not Building

- No `edgarpack founder-control` command.
- No dashboard or browser UI.
- No uncited claim generation.
- No global non-SEC source acquisition.
- No normalized founder-control score.
- No automated founder identity inference beyond what the filing supports.

## Unit Of Analysis

Each record represents one company at one anchor year:

```text
company x anchor_year
```

Anchor years:

```text
2026
2016
2006
```

For each company and anchor year, choose the best available primary filing in this order:

```text
DEF 14A proxy statement
20-F annual report for ADR or foreign private issuer
10-K Part III disclosure when proxy is unavailable or incorporated
S-1 or F-1 only when the company was not yet public at that anchor
```

If no exact-year filing exists, choose the nearest relevant filing and record the selection reason in `notes`.

## Output Artifacts

```text
reports/founder-control/founder-control-table.csv
reports/founder-control/founder-control-report.md
reports/founder-control/<ticker>-control-change.html
```

The CSV is authoritative. The Markdown report is derived from it. The optional HTML diff files are supporting evidence for companies with comparable filing pairs.

## Table Schema

```text
company
ticker
cik
anchor_year
filing_form
filing_date
accession
source_path
founder_names
founder_executive_role
founder_board_role
founder_economic_ownership_pct
founder_voting_power_pct
dual_class_or_control_mechanism
controlled_company_status
control_summary
evidence_section_id
evidence_chunk_ids
evidence_excerpt
confidence
notes
```

Rules:

- `founder_economic_ownership_pct` is the disclosed ownership percentage when available.
- `founder_voting_power_pct` is the disclosed voting power when available.
- Prefer exact disclosed voting power over computed estimates.
- Compute voting power only when the filing provides all required share-class inputs.
- `dual_class_or_control_mechanism` stores the mechanism, not an interpretation score.
- `controlled_company_status` is factual only when disclosed or clearly negated in the filing.
- `confidence` is `high`, `medium`, or `low`, based on evidence clarity.
- `notes` may contain unresolved context, but unresolved context must not be repeated as fact in the report.

## Workflow

Freeze the cohort and record the source used for the current top ten technology-company list. The cohort source must be cited in the narrative report.

Resolve each company to its EdgarPack identity:

```bash
uv run edgarpack identify <company-or-ticker>
```

List likely governance filings:

```bash
uv run edgarpack list META --form "DEF 14A" --limit 40
uv run edgarpack list TSM --form "20-F" --limit 25
uv run edgarpack list META --form "10-K" --limit 25
uv run edgarpack list <company> --form "S-1" --limit 10
uv run edgarpack list <company> --form "F-1" --limit 10
```

Build anchor filings with chunks:

```bash
uv run edgarpack build META --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build META --form "DEF 14A" --after 2015-01-01 --before 2016-12-31 --with-chunks
uv run edgarpack build META --form "DEF 14A" --after 2005-01-01 --before 2006-12-31 --with-chunks
```

Index the corpus:

```bash
uv run edgarpack index --packs ./packs --incremental
```

Search targeted governance phrases:

```bash
uv run edgarpack search '"beneficial ownership" "voting power"' --ticker META --form "DEF 14A"
uv run edgarpack search '"Class B" "voting power"' --ticker META
uv run edgarpack search '"controlled company"' --ticker META
uv run edgarpack search '"principal stockholders"' --ticker META
uv run edgarpack search '"security ownership" "voting"' --ticker META
```

Extract rows from the relevant filing sections or chunks. Do not rely on search results alone. Search is a locator; the filing text is the source.

Generate HTML diffs when comparable filing pairs exist:

```bash
uv run edgarpack diff \
  --before ./packs/<cik>/<older-accession> \
  --after ./packs/<cik>/<newer-accession> \
  --format html \
  --out ./reports/founder-control/<ticker>-control-change.html
```

Write the narrative report from the CSV. The report should separate observed evidence from interpretation, and it should call out companies where missing filings or source-form differences limit comparison.

## Evidence Standard

A row can make a factual claim only when it has:

```text
accession
evidence_section_id or evidence_chunk_ids
evidence_excerpt
```

If chunks are missing or low quality, section and accession evidence may carry the row. If sectionization fails and the pack collapses into a broad generic section, use `filing.full.md` plus accession evidence and record the limitation in `notes`.

Absence from search results is not evidence of absence. A row may say founder control was not found only after the relevant ownership, proxy, annual-report, or registration filing section has been inspected.

## Validation Slice

Before running the full cohort, validate the workflow on three cases:

```text
META: strong founder-control case
AAPL or MSFT: likely weak or changed founder-control case
TSM or ASML: ADR or 20-F case if included in the frozen top ten
```

For each pilot case:

- Build the relevant anchor filings with chunks.
- Extract at least one row per available anchor year.
- Verify every factual cell has accession plus section or chunk evidence.
- Confirm the row can be reviewed from the local pack files without external memory.
- Record missing exact-year filings explicitly.

## Architecture Fit

The workflow builds on existing EdgarPack surfaces:

- `build` creates deterministic filing packs.
- `list` reaches older filings through SEC submission pagination.
- `index` and `search` locate relevant evidence chunks.
- `sections/*.md`, `filing.full.md`, and `manifest.json` provide reviewable source material.
- `diff` creates optional HTML reports for disclosure-change review.

No query metric is added. Founder control is not an XBRL concept, and treating it as a normal financial metric would hide important governance semantics.

## Fragile Assumption

The plan assumes `DEF 14A`, 20-F, S-1, and F-1 packs produce enough section or chunk structure to support review. If proxy packs collapse into broad generic sections, the workflow remains valid through accession and full-filing evidence, but extraction becomes slower and the next product investment should be a narrow proxy/governance sectionizer.

## Failure Modes

Filing not available for an anchor year: choose the nearest relevant filing, record the reason, and avoid implying exact-year coverage.

Multiple founders or founder entities: record all disclosed founder holders and separate individual, trust, family, and entity control when the filing distinguishes them.

Dual-class voting disclosed without economic ownership: keep voting power and economic ownership as separate columns; do not infer the missing side.

ADR or foreign-private-issuer disclosures use different terminology: keep the company in scope only when primary SEC filing evidence supports the row, and flag source-form differences in `notes`.

Search finds stale or irrelevant sections: inspect the section text before extracting. The search hit is not itself a claim.

## Success Criteria

The workflow succeeds when:

- The cohort source is documented.
- Every available company-year row has a primary filing accession.
- Every factual claim has section or chunk evidence, or is excluded.
- The CSV can be audited without reading the narrative report.
- The report identifies broad changes in founder control while naming source limitations.
- The pilot cases expose whether a proxy/governance sectionizer is worth building next.

## Implementation Handoff

Implementation should be a research execution run, not a code change. If repeated manual extraction becomes the bottleneck after the pilot, open a bead for a narrow governance extractor with fixtures from the completed research bundle.
