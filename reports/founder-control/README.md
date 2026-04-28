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

- `cohort.csv`: frozen cohort and EdgarPack identity fields
- `filing-selection-notes.md`: notes for non-obvious source filing decisions
- `founder-control-table.csv`: authoritative evidence table
- `founder-control-report.md`: narrative synthesis derived from the table
- `search-notes/`: compact search/read notes for hard-to-locate evidence
- `$TICKER-control-change.html`: optional diff reports for comparable filing pairs

## Evidence Rule

Every factual claim in the narrative report must map to a row in `founder-control-table.csv` with accession and section or chunk evidence.
