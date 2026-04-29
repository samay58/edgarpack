# SaaS Evolution EdgarPack Research Spec

Date: 2026-04-29
Status: Approved direction, ready for writing plan
Scope: Research workflow and report design, not product implementation

## Purpose

Use EdgarPack as the main research instrument for an investor-grade report on how public SaaS companies evolved over the last 10 to 15 years. The report should prove what EdgarPack unlocks: cited multi-period financials, cleaned filing packs, company-specific KPI discovery, source-linked metric definitions, and a visible record of where the tool needs to improve.

The report should not read like a SaaS market overview. It should make filing-backed claims about how the public SaaS contract changed: from recurring-revenue growth and net retention toward a more mature mix of backlog durability, free cash flow, product breadth, cloud migration, usage exposure, dilution discipline, and AI-era monetization.

## Main Question

How did the public SaaS business model change from roughly 2014 to 2026, and which filing-backed signals still tell investors something useful?

The report should answer six linked questions:

- What did public SaaS companies ask investors to underwrite in the mid-2010s?
- Which companies became larger, more profitable platform suites rather than narrow applications?
- Where did the model split into seats, subscription suites, cloud migration, usage-based consumption, and transaction-adjacent revenue?
- Which metrics aged well, and which became less comparable across companies?
- How did the 2021 peak and 2022 reset change the premium for growth versus free cash flow?
- How is AI changing packaging and monetization in actual disclosures, not in generic commentary?

## Recommended Frame

The report should be called:

```text
The SaaS Contract Changed
```

The subtitle should make the EdgarPack angle explicit:

```text
A filing-backed study of how public SaaS moved from recurring revenue to backlog, cash flow, usage, and AI packaging.
```

The core thesis to test:

Public SaaS did not simply mature from growth to profitability. It fragmented into different economic machines. Salesforce, ServiceNow, Adobe, and Workday look like enterprise subscription and backlog machines. Atlassian is a cloud-migration story. Shopify mixes subscription and merchant economics. Datadog, Snowflake, and MongoDB expose the strengths and weaknesses of usage-based expansion. Zoom shows seat-based pull-forward and normalization. HubSpot shows SMB SaaS becoming a customer platform. AI then pushes the model again, from seats toward credits, usage, and work-unit packaging.

## Primary Cohort

Use an 11-company cohort:

```text
CRM
NOW
ADBE
TEAM
SHOP
DDOG
SNOW
MDB
ZM
HUBS
WDAY
```

This cohort is deliberately small. It is large enough to show model diversity and small enough to keep the evidence layer inspectable.

Do not expand the first report to every public SaaS company. A broader benchmark can be a follow-up issue after the first bundle proves the workflow.

## Time Frame

Use three anchor periods:

- Baseline: 2014 or 2015, depending on filing availability.
- Midpoint: 2020, capturing pre-reset scale and pandemic-period context.
- Current: latest 2025 or 2026 annual filing or latest available annual results release.

When a company was not public at the baseline, use its S-1 or first observable public filing and mark the row as `ipo_or_first_observable`.

## Evidence Policy

EdgarPack and primary documents are the evidence base. Deep research and market reports are allowed only for framing valuation regimes, benchmark language, and external context.

Use this hierarchy:

1. EdgarPack `query` JSON and citation records for standardized financials.
2. EdgarPack `build` packs and `optional/chunks.ndjson` for filing text, KPI evidence, and source excerpts.
3. EdgarPack `which` output for company-specific KPIs such as RPO, NRR, customer counts, GMV, Atlas mix, and enterprise-customer thresholds.
4. SEC filings and company IR releases when the needed disclosure is not yet captured cleanly by EdgarPack.
5. External sources such as Bessemer, OpenView, Meritech, Battery, SaaS Metrics Standards Board, McKinsey, and practitioner pricing reports for context only.

No report claim about a company belongs in the narrative unless it maps to a row in an evidence table or source ledger.

## Output Bundle

Create a new bundle:

```text
reports/saas-evolution/
```

Expected files:

```text
README.md
cohort.csv
filing-selection-notes.md
edgarpack-run-log.md
edgarpack-friction-log.md
standard-financials.csv
business-model-table.csv
kpi-disclosure-table.csv
metric-definition-table.csv
ai-packaging-table.csv
valuation-context-table.csv
source-ledger.csv
saas-evolution-report.md
```

The bundle is both a report and a product proof. `edgarpack-run-log.md` should show the actual commands used. `edgarpack-friction-log.md` should record tool gaps, confusing output, missing citations, slow paths, and follow-up issues to file.

## Research Flow

```text
Company cohort
  -> EdgarPack identify/list
  -> EdgarPack query JSON for standard metrics
  -> EdgarPack build packs with chunks
  -> EdgarPack which for KPI discovery
  -> Targeted pack reads and source excerpts
  -> Evidence tables and source ledger
  -> Narrative report
  -> Friction log and follow-up beads
```

The report should be written last. Fill the evidence tables first.

## Core Tables

### Standard Financials

Use EdgarPack `query` as the first path.

Required fields:

```text
company
ticker
cik
period_anchor
fiscal_year
filing_form
filing_date
accession
revenue
gross_margin
operating_margin
free_cash_flow
free_cash_flow_margin
r_and_d_intensity
sales_and_marketing_intensity
stock_based_compensation
stock_based_compensation_as_pct_revenue
citation_ids
source_url
confidence
notes
```

Use cited base metrics first. Compute cross-year deltas in the research table rather than trusting derived growth outputs blindly, because early planning found offset-period derived growth can be misleading in some JSON outputs.

### Business Model Table

Classify the economic machine after evidence extraction.

Required fields:

```text
company
ticker
period_anchor
model_type
revenue_model_summary
deployment_or_packaging_summary
usage_or_transaction_exposure
enterprise_or_smb_motion
platform_breadth_signal
evidence_locator
source_url
confidence
notes
```

Controlled vocabulary for `model_type`:

```text
enterprise_subscription_suite
workflow_platform
license_to_subscription_transition
cloud_migration
subscription_plus_transactions
usage_based_data_platform
seat_based_collaboration
smb_customer_platform
human_capital_backlog_platform
```

### KPI Disclosure Table

Use EdgarPack `which` first, then targeted filing reads.

Required fields:

```text
company
ticker
period_anchor
kpi_name
kpi_value
kpi_unit
kpi_definition
kpi_category
section_id
chunk_id
source_excerpt
source_url
confidence
notes
```

KPI categories:

```text
arr
rpo
crpo
backlog
net_retention
gross_retention
customer_count
large_customer_count
gmv_or_transaction_volume
usage_or_consumption
deployment_mix
ai_arr_or_acv
employee_count
none_disclosed
unresolved
```

### Metric Definition Table

This table is essential because SaaS metrics are not naturally comparable.

Required fields:

```text
company
ticker
metric_name
definition_text
included_items
excluded_items
measurement_window
comparability_warning
source_locator
source_url
confidence
notes
```

Examples of definitions that must be captured when disclosed:

- Adobe ARR definition during Creative Cloud transition.
- Salesforce RPO and cRPO definitions.
- ServiceNow cRPO definition.
- Snowflake net revenue retention and RPO caveats.
- MongoDB Atlas ARR usage windows.
- Datadog free cash flow definition.

### AI Packaging Table

This table should separate disclosed monetization from AI theater.

Required fields:

```text
company
ticker
ai_product_or_package
pricing_or_packaging_model
unit_of_value
disclosed_arr_acv_or_usage
margin_or_cost_commentary
source_type
source_url
confidence
notes
```

Start with Salesforce Agentforce, ServiceNow Now Assist or AI Agents, Adobe Firefly or Creative Cloud Pro, Atlassian Rovo, and GitLab Duo only if the source quality remains strong. The table should not imply every company has comparable AI monetization.

### Valuation Context Table

This is the only table where external sources can be primary evidence.

Required fields:

```text
source_name
source_date
regime
metric
value
context
source_url
confidence
notes
```

Allowed source families:

- Bessemer State of the Cloud and State of AI.
- OpenView SaaS benchmarks.
- Meritech public software pulse.
- Battery OpenCloud.
- SaaS Metrics Standards Board.
- McKinsey Rule of 40 note.

Keep this table narrow. It should frame the market regime, not become the report's center.

## Narrative Report

`saas-evolution-report.md` should read like an investment memo. It should have a point of view and show the evidence.

Required sections:

- Opening thesis: what changed in the SaaS contract.
- The 2014 to 2015 baseline: what SaaS companies asked investors to believe.
- The platforming phase: suite expansion, enterprise backlog, cloud migration, and transaction adjacency.
- The reset: why growth remained valuable but stopped being enough.
- The metric audit: ARR, NRR, RPO, cRPO, FCF, Rule of 40, SBC, and where each breaks.
- The AI packaging shift: seat add-ons, credits, usage, work units, and inference-cost pressure.
- Company cases that break the simple story.
- What EdgarPack made easy, what it made possible, and what needs hardening.

The tone should be direct. Avoid generic claims like "SaaS companies increasingly prioritize efficiency." Say which companies, which metrics, which filings, and what changed.

## EdgarPack Proof Requirements

The first execution pass must use these commands or close equivalents:

```bash
uv run edgarpack identify CRM
uv run edgarpack query ADBE revenue,gross_margin,operating_margin,fcf_margin --period lfy,lfy-5,lfy-10 --format json
uv run edgarpack query CRM --preset perf --period lfy,lfy-1,lfy-2 --format json
uv run edgarpack build CRM --form 10-K --last 3 --with-chunks
uv run edgarpack which CRM --format json
uv run edgarpack comps CRM NOW ADBE WDAY --metrics revenue,gross_margin,operating_margin,free_cash_flow --period lfy --format json
```

The exact command set can expand during execution, but every run used for the report should be logged in `edgarpack-run-log.md`.

## Follow-Up Issues

Execution should file beads for EdgarPack gaps that materially affect the research workflow. Expected categories:

- Derived metric correctness or confusing offset-period behavior.
- Missing chunk IDs in `which` output when source substrings are present.
- Better SaaS preset metrics, including RPO, cRPO, SBC, sales and marketing intensity, and enterprise customer thresholds.
- A first-class research bundle generator if the manual table workflow proves repetitive.
- Better report export or source-ledger generation if citation wiring is too manual.

Do not fix these during the first report unless they block completion. File them as follow-up issues with concrete repro commands.

## Testing And Verification

This is a research-production workflow, so verification is artifact QA plus any code tests required by follow-up fixes.

Required checks:

- Every company claim in the report maps to `source-ledger.csv`.
- Every standard financial value has an accession, source URL, and citation ID where EdgarPack provides one.
- Every KPI row has a source excerpt, section ID, source URL, and confidence value.
- CSV files parse with Python's standard `csv` module.
- The narrative contains no uncited company claims.
- `edgarpack-friction-log.md` distinguishes user error, missing source data, and tool gaps.
- If code changes are made during execution, run the repo's relevant pytest and ruff gates before closeout.

## Dependencies

Required:

- `EDGARPACK_USER_AGENT`, already available in this environment during planning.
- Network access to SEC and company IR pages when packs or source pages are not already cached.
- `uv run edgarpack` from the repo checkout.
- `bd` for follow-up issue tracking.

Not required:

- No paid API key.
- No DeepInfra or Anthropic key.
- No new package dependency.
- No database migration.
- No frontend or dashboard work.

## Risk And Deformation

The most fragile assumption is that EdgarPack can cover enough of the 11-company cohort through `query`, `build`, and `which` without too much manual source extraction. If that fails, do not broaden the research. Narrow the first report to the companies where the tool produces strong evidence, then file precise hardening issues for the failures.

Dependency failure: if live SEC or IR access fails, use cached local packs where available and mark missing rows as `source_unavailable_in_run`.

Scale explosion: if 11 companies becomes too much, keep the cohort list but ship a strong first-pass table for CRM, ADBE, NOW, DDOG, SNOW, and ZM, then file follow-up beads for the remaining companies.

Rollback cost: all outputs are report artifacts. Rolling back means removing `reports/saas-evolution/` and the spec or reverting the report commit. No application data changes are involved.

## Not Building

Do not build a new EdgarPack command in the first pass.

Do not build a dashboard.

Do not write a generic SaaS market map.

Do not let external deep research outrank primary filings.

Do not expand into private-company SaaS benchmarks except as valuation context.

Do not make uncited claims about AI disruption.

## Approved Design Summary

Building: an EdgarPack-heavy research bundle and investor memo that uses public SaaS filings to show how the business model changed across subscription, platform, usage, backlog, cash-flow, and AI-packaging regimes.

Not building: new product surfaces, dashboards, broad benchmark automation, or a generic web-sourced SaaS essay.

Approach: use EdgarPack as the primary research engine, write evidence tables before narrative, keep external research to valuation and metric framing, and turn real tool friction into follow-up beads.

Key decisions:

- Keep the cohort at 11 companies to preserve evidence quality.
- Use 2014 or 2015, 2020, and latest 2025 or 2026 as anchor periods.
- Treat metric definitions as first-class evidence because SaaS comparability is the central problem.
- Record EdgarPack friction as product evidence, not as side commentary.
- File hardening issues instead of interrupting the report to fix every tool gap.

Unknowns: none block the writing plan. The exact accession for each company-period row will be selected during execution and recorded in `filing-selection-notes.md`.
