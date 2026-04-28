# Dominant Company Architecture Research Bundle

Date started: 2026-04-28

## Question

How did the architecture of dominant public companies change between the earlier market era and today?

## Scope

The primary comparison is S&P 500 top-20 companies by market capitalization in 1996 versus 2026. The 1989 S&P 500 top-20 roster is context only unless primary filings support a claim.

## Evidence Policy

Control, governance, operating profile, capital allocation, and KPI claims must trace to primary filings or clearly labeled raw SEC line anchors. Cohort membership and rank can trace to the market-cap source listed below. Search results can locate sections but are not evidence by themselves.

## Cohort Sources

- Historical and current S&P 500 top-20 source: https://www.finhacker.cz/en/top-20-sp-500-companies-by-market-cap/
- Current tech context source: https://companiesmarketcap.com/tech/largest-tech-companies-by-market-cap/
- EDGAR availability source: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- Retrieved at: 2026-04-28

## Artifact Index

- `cohorts.csv`: frozen cohort rows and identity fields
- `company-life-arc.csv`: IPO or first-observable public-filing basis
- `filing-selection-notes.md`: filing choices, predecessor mapping, raw SEC routing, and exclusions
- `control-table.csv`: founder, family, institutional, professional-manager, and other control evidence
- `governance-table.csv`: share-class, board, committee, election, takeover-defense, and auditor evidence
- `operating-profile-table.csv`: revenue, margins, R&D, capex, employees, segment mix, and geography
- `capital-allocation-table.csv`: dividends, repurchases, cash, securities, debt, acquisitions, and posture
- `kpi-disclosure-table.csv`: recurring company-specific operating KPIs
- `architecture-archetypes.csv`: evidence-derived company archetype assignments
- `evidence-ledger.csv`: audit map from report claims to evidence rows
- `dominant-company-architecture-report.md`: narrative synthesis derived from the tables

## Execution Rule

Fill evidence tables first. Assign archetypes after evidence extraction. Write the report last.
