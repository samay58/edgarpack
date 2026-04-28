# Founder Control Research Bundle

Date started: 2026-04-28

## Question

How has founder control changed among the current top ten technology companies across 2026, 2016, and 2006?

## Source Policy

This bundle is SEC-first. Use DEF 14A, 20-F, 10-K Part III, S-1, and F-1 filings where EdgarPack can build citation-backed packs. Non-SEC sources are not used for founder-control claims in this version.

## Cohort Source

- Source URL: https://companiesmarketcap.com/tech/largest-tech-companies-by-market-cap/
- Retrieved at: 2026-04-28
- Rule: freeze the current top ten technology companies from the source at retrieval time, then track those companies backward.

## Artifact Index

- `cohort.csv`: frozen cohort and EdgarPack identity fields. Samsung is retained in the cohort but marked `unknown` because EdgarPack did not resolve SEC/20-F coverage.
- `filing-selection-notes.md`: notes for non-obvious source filing decisions, predecessor identity mappings, fallback filings, and the TSM 2006 build limitation.
- `founder-control-table.csv`: authoritative evidence table with 27 evidence rows.
- `founder-control-report.md`: narrative synthesis derived from the table.
- `search-notes/`: no separate notes were required; the CSV carries the source paths, section IDs, chunk IDs, and limitations.
- `*-control-change.html`: no optional HTML diffs were generated. The useful comparisons are captured in the CSV/report; several issuer histories cross proxy, S-1, and 20-F boundaries where a diff would be misleading.

## Evidence Rule

Every factual claim in the narrative report must map to a row in `founder-control-table.csv` with accession and section or chunk evidence.

## Verification

- Code changed: no
- Quality gates: artifact integrity checks in Task 8 passed
- Baseline tests: `uv run --extra dev --extra china --extra sse python -m pytest -q` passed before research changes (`1382 passed, 50 skipped, 12 xfailed`)
- SEC pack builds: see `filing-selection-notes.md` for missing or fallback filings
- Narrative report: derived from `founder-control-table.csv`
