# Founder Control Era Cohorts Research Workflow

Date: 2026-04-28
Status: Approved for research execution
Scope: Research workflow, not product feature implementation

## Purpose

Use EdgarPack to compare founder control across dominant public-company cohorts from an earlier market era and today. This supersedes the narrower "current top ten tech companies traced backward" framing. The better question is not only whether today's tech giants changed over time, but whether dominant companies now tend to retain founder influence differently from the dominant companies of the earlier era.

The first report should stay focused on founder control. It should also be structured so a later report can expand into governance, operating profile, and KPI comparison without having to redo the cohort work.

## Research Question

How did founder control differ between dominant public companies of the earlier market era and dominant public companies today, both at the moment of market dominance and across comparable public-company life-arc points?

The report should answer two related questions:

1. Dominance-year comparison: among the largest companies in an earlier era versus today, how much control did founders retain at the time those companies were dominant?
2. Life-arc comparison: at comparable stages after IPO or first observable public filing, how much founder control was present or still visible?

## Key Design Decision

The primary cohort should be dominant public companies, not only technology companies. A tech-only lens is useful as an overlay, but making it the core sample would hide the bigger historical shift: the earlier dominant-company set included energy, consumer staples, pharmaceuticals, industrials, telecom, finance, and emerging technology, while today's dominant-company set is much more concentrated in technology and platform businesses.

The primary sample should use S&P 500 top-20 cohorts because they are easier to compare with SEC filings, reduce global source-form gaps, and reach back to 1989 in an available historical market-cap series. ADR and 20-F companies remain valid for a global or tech-only extension, but the first high-confidence pass should not depend on non-U.S. annual-report availability.

## Cohort Design

Primary cohorts:

- Earlier-era cohort: top 20 S&P 500 companies by market capitalization in 1996.
- Current-era cohort: top 20 S&P 500 companies by market capitalization in 2026, frozen at execution time.

Context cohorts:

- 1989 or 1990 top 20 S&P 500 companies by market capitalization, used to show the 30-40 year historical backdrop.
- Current global top technology companies, used only as a comparison lens when the report needs to explain why "dominant public companies" and "dominant technology companies" diverge.

The 1996 cohort is the primary earlier-era evidence set because SEC EDGAR starts in 1994/1995. A 1989 or 1990 roster can be cited for context, but founder-control claims for pre-EDGAR years should not be inferred unless a primary filing is available.

Candidate cohort sources:

- Historical S&P 500 top-20 source: `https://www.finhacker.cz/en/top-20-sp-500-companies-by-market-cap/`
- Current tech/global context source: `https://companiesmarketcap.com/tech/largest-tech-companies-by-market-cap/`
- EDGAR availability source: `https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data`

Cohort sources are allowed to be non-SEC. Founder-control, governance, operating-profile, and KPI claims must come from primary filings whenever possible.

## Unit Of Analysis

The core row should be:

```text
company x cohort x comparison_point
```

Comparison points:

- `dominance_year`: the filing nearest the company's cohort year, usually 1996 or 2026.
- `first_observable_public`: IPO registration statement when available, otherwise first available EDGAR governance or annual filing.
- `public_plus_10`: filing nearest 10 years after IPO or first observable public filing.
- `public_plus_20`: filing nearest 20 years after IPO or first observable public filing.
- `latest`: the latest proxy or annual governance filing when it is not already the dominance-year filing.

For older companies whose IPO or founding period predates EDGAR, mark the life-arc as left-censored. Do not pretend EDGAR can reconstruct the full public-company arc before 1994/1995.

## Source Policy

Use primary SEC filings first:

```text
DEF 14A proxy statement
20-F annual report for ADR or foreign private issuer
10-K Part III disclosure when proxy is unavailable or incorporated
S-1 or F-1 registration statement for first-public or IPO-stage rows
8-K only for narrow governance events when the annual/proxy filing points there
```

Use non-SEC sources only for:

- cohort membership and market-cap rank,
- IPO date or predecessor mapping when the filing does not state it clearly,
- context that is explicitly labeled as context and not treated as a filing-backed claim.

ADRs and 20-F issuers may be included in the context or extension cohorts when EdgarPack can cite primary SEC filings. Do not add non-SEC global acquisition to this first report.

## Output Artifacts

Create a new bundle so the earlier current-top-ten report remains intact:

```text
reports/founder-control-era/README.md
reports/founder-control-era/cohorts.csv
reports/founder-control-era/filing-selection-notes.md
reports/founder-control-era/company-life-arc.csv
reports/founder-control-era/founder-control-era-table.csv
reports/founder-control-era/founder-control-era-report.md
reports/founder-control-era/extension-notes.md
```

The CSV files are the source of truth. The narrative report should summarize the CSVs and cite the underlying rows. It should not introduce uncited facts.

## Table Fields

The exact schema can stay lean, but the evidence table must carry enough information to audit each claim:

```text
company
ticker
cik
sector_or_industry
cohort_name
cohort_year
cohort_rank
cohort_market_cap
comparison_point
life_arc_basis
life_arc_year
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
founder_control_signal
evidence_section_id
evidence_chunk_ids
evidence_excerpt
confidence
notes
```

Guidance:

- Keep economic ownership and voting power separate.
- Prefer disclosed voting power over computed estimates.
- Compute only when all share-class inputs are present in the filing.
- `founder_control_signal` should be conservative: `strong`, `visible`, `limited`, `none_found`, or `unresolved`.
- `none_found` requires review of the relevant ownership or governance section; search misses alone are not evidence.
- Use `notes` for predecessor names, mergers, spinoffs, missing exact-year filings, source-form differences, and left-censored life arcs.

## Narrative Shape

The report should be concise and evidence-backed:

- Explain the cohort choice and EDGAR boundary.
- Compare dominance-year founder control in the 1996 and 2026 cohorts.
- Compare life-arc patterns where filings allow it.
- Separate observed facts from interpretation.
- Name the limits: pre-EDGAR history, predecessor identities, companies with no meaningful founder concept, and source-form differences.
- Include potential broader insights only when the founder-control data supports them.

Potential insights to watch for, not force:

- earlier dominant companies often reached dominance long after founder era;
- current dominant companies more often reached dominance while founder influence, dual-class voting, or founder executive roles were still visible;
- technology concentration may matter more than simple company age;
- founder influence can persist through board roles, trusts, family ownership, or high-vote share classes even when economic ownership is smaller;
- founder absence can be as meaningful as founder control when the dominant company is an old-line institution.

## Extension Path

If the founder-control report is strong, expand the same cohort bundle into a broader "dominant companies then versus now" comparison. Do not design that expansion as a separate project yet; preserve the hooks now.

Possible extension dimensions:

- governance: board independence, classified board, dual-class or unequal voting, poison pill or anti-takeover provisions, insider ownership, controlled-company status, auditor tenure where disclosed;
- operating profile: revenue scale, revenue growth, operating margin, gross margin where meaningful, R&D intensity, capex intensity, employee count, geographic or segment mix;
- capital allocation: buybacks, dividends, cash balance, debt, acquisitions;
- KPI evolution: recurring company-specific KPIs discovered from 10-Ks and annual reports with EdgarPack `which` or targeted section review.

The later extension should reuse:

- `cohorts.csv`,
- `company-life-arc.csv`,
- filing selection notes,
- built packs,
- evidence discipline from the founder-control table.

## Workflow

Freeze the primary and context cohorts with cited source URLs and retrieval dates.

Resolve each company to EdgarPack identity:

```bash
uv run edgarpack identify <company-or-ticker>
```

List candidate filings:

```bash
uv run edgarpack list <company-or-ticker> --form "DEF 14A" --limit 60
uv run edgarpack list <company-or-ticker> --form "10-K" --limit 60
uv run edgarpack list <company-or-ticker> --form "S-1" --limit 20
uv run edgarpack list <company-or-ticker> --form "20-F" --limit 30
uv run edgarpack list <company-or-ticker> --form "F-1" --limit 20
```

Build selected filings with chunks:

```bash
uv run edgarpack build <company-or-ticker> --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build <company-or-ticker> --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build <company-or-ticker> --form "S-1" --with-chunks
```

Index packs:

```bash
uv run edgarpack index --packs ./packs --incremental
```

Search only as a locator:

```bash
uv run edgarpack search '"beneficial ownership" "voting power"' --ticker <ticker>
uv run edgarpack search '"principal stockholders"' --ticker <ticker>
uv run edgarpack search '"Class B" "voting power"' --ticker <ticker>
uv run edgarpack search '"controlled company"' --ticker <ticker>
uv run edgarpack search '"security ownership"' --ticker <ticker>
```

Extract only after reading the relevant filing section or full filing text.

## Validation Slice

Before extracting the full top-20 sample, validate the method on six companies:

```text
Earlier-era founder-visible or founder-adjacent: Microsoft, Walmart, Intel
Earlier-era no-founder or institution-like: Exxon Mobil, Coca-Cola, General Electric
Current founder-visible: Nvidia, Alphabet, Meta
Current lower-founder or founder-absent: Apple, Microsoft, Broadcom or JPMorgan
```

The validation slice succeeds when the table can show both positive and negative founder-control cases without uncited claims.

## Success Criteria

The workflow succeeds when:

- cohort sources and retrieval dates are documented;
- every included company has an EdgarPack identity or an explicit exclusion reason;
- every evidence row has an accession and section or chunk evidence;
- left-censored older-company life arcs are labeled clearly;
- dominance-year and life-arc comparisons are separated;
- the narrative makes only claims derivable from the CSVs;
- extension notes identify the highest-value governance, operating, and KPI comparisons without requiring them in the founder-control report.

## Not Building

- No new `edgarpack founder-control` command.
- No dashboard.
- No automated founder identity inference beyond what filings support.
- No normalized founder-control score.
- No non-SEC global filing acquisition.
- No broad governance/KPI report until the founder-control report earns the expansion.

## Failure Modes

Historical source ambiguity: keep the cohort source explicit, and do not blend multiple rankings unless the report labels the difference.

Pre-EDGAR life arcs: mark rows as left-censored rather than reconstructing from memory or secondary summaries.

Company predecessor complexity: document the predecessor mapping and avoid false continuity when mergers or spinoffs change the issuer.

Founder concept does not apply cleanly: record `none_found` or `unresolved` with evidence from ownership/governance sections.

Dual-class voting disclosed without economic ownership: record voting power and leave economic ownership blank.

Search finds stale or irrelevant text: inspect the section before extracting.

The founder-control findings become too thin: complete the dominance-year comparison first, then decide whether life-arc extraction is worth expanding.
