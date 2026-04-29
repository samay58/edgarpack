# SaaS Evolution EdgarPack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an EdgarPack-heavy research bundle and investor memo showing how public SaaS companies evolved from recurring-revenue growth stories into distinct backlog, usage, cash-flow, platform, and AI-packaging machines.

**Architecture:** This is a research-production workflow, not an application-code change. The work creates `reports/saas-evolution/`, captures raw EdgarPack outputs, fills evidence tables first, writes the narrative only after the tables are source-backed, and files beads for EdgarPack friction discovered while behaving like a demanding user.

**Tech Stack:** EdgarPack CLI via `uv run`, SEC EDGAR filings, local packs under `packs/`, company IR pages only when EdgarPack cannot capture a disclosure cleanly, Markdown, CSV, JSON, Python standard library QA, and `bd` for follow-up issue tracking. Required environment: `EDGARPACK_USER_AGENT`.

---

## Scope Check

The spec covers one cohesive research bundle with five evidence modules and one narrative memo. It does not require a new EdgarPack command, dashboard, package dependency, database, or frontend.

Keep external deep research small. Use Bessemer, OpenView, Meritech, Battery, SaaS Metrics Standards Board, and McKinsey only to frame valuation and metric regimes. Company-specific claims must come from EdgarPack outputs, SEC filings, company IR releases, or source URLs recorded in `source-ledger.csv`.

If the full 11-company cohort becomes too large, ship the first report around the six-company evidence spine `CRM`, `ADBE`, `NOW`, `DDOG`, `SNOW`, and `ZM`, while keeping `cohort.csv` complete and filing follow-up beads for the rest.

## File Structure

- Create: `reports/saas-evolution/README.md`
  - Bundle index, question, source hierarchy, execution rule, and artifact map.
- Create: `reports/saas-evolution/cohort.csv`
  - The fixed 11-company cohort with model hypotheses and anchor-period rules.
- Create: `reports/saas-evolution/filing-selection-notes.md`
  - Filing choices, S-1 substitutions, missing periods, source fallbacks, and confidence notes.
- Create: `reports/saas-evolution/edgarpack-run-log.md`
  - Every EdgarPack command used for report evidence, with timestamp, output path, and observed issue.
- Create: `reports/saas-evolution/edgarpack-friction-log.md`
  - Product gaps, confusing behavior, slow paths, and follow-up bead IDs.
- Create: `reports/saas-evolution/edgarpack-investor-product-recommendations.md`
  - Clear, non-incremental product recommendations from using EdgarPack like an investor.
- Create: `reports/saas-evolution/standard-financials.csv`
  - Cited multi-period financial rows from EdgarPack query outputs.
- Create: `reports/saas-evolution/business-model-table.csv`
  - Filing-backed classification of each company-period economic machine.
- Create: `reports/saas-evolution/kpi-disclosure-table.csv`
  - Company-specific KPIs discovered through `which` and filing reads.
- Create: `reports/saas-evolution/metric-definition-table.csv`
  - Exact definitions and comparability warnings for ARR, RPO, cRPO, NRR, FCF, and usage metrics.
- Create: `reports/saas-evolution/ai-packaging-table.csv`
  - Disclosed AI monetization, pricing, units, and cost/margin signals.
- Create: `reports/saas-evolution/valuation-context-table.csv`
  - Narrow external-market context table.
- Create: `reports/saas-evolution/source-ledger.csv`
  - Audit map from report claims and table rows to source locators.
- Create: `reports/saas-evolution/saas-evolution-report.md`
  - Final investor memo derived from tables.
- Create: `reports/saas-evolution/raw/edgarpack/`
  - Raw JSON and text outputs from EdgarPack commands.
- Create: `reports/saas-evolution/raw/external/`
  - Saved excerpts or notes from external framing sources.
- Create: `reports/saas-evolution/search-notes/`
  - Compact source-review notes for hard company-specific disclosures.
- Modify: no application code unless a blocking EdgarPack defect must be fixed.
- Test: artifact QA by default. If application code changes, run targeted pytest and ruff gates before closeout.

## Task 1: Bundle Setup

**Files:**
- Create: `reports/saas-evolution/README.md`
- Create: `reports/saas-evolution/cohort.csv`
- Create: `reports/saas-evolution/filing-selection-notes.md`
- Create: `reports/saas-evolution/edgarpack-run-log.md`
- Create: `reports/saas-evolution/edgarpack-friction-log.md`
- Create: `reports/saas-evolution/edgarpack-investor-product-recommendations.md`
- Create: `reports/saas-evolution/standard-financials.csv`
- Create: `reports/saas-evolution/business-model-table.csv`
- Create: `reports/saas-evolution/kpi-disclosure-table.csv`
- Create: `reports/saas-evolution/metric-definition-table.csv`
- Create: `reports/saas-evolution/ai-packaging-table.csv`
- Create: `reports/saas-evolution/valuation-context-table.csv`
- Create: `reports/saas-evolution/source-ledger.csv`
- Create: `reports/saas-evolution/raw/edgarpack/`
- Create: `reports/saas-evolution/raw/external/`
- Create: `reports/saas-evolution/search-notes/`

- [ ] **Step 1: Confirm repo and environment**

Run:

```bash
git rev-parse --show-toplevel
printenv EDGARPACK_USER_AGENT
```

Expected:

```text
/Users/samaydhawan/Projects/active/edgarpack
```

`EDGARPACK_USER_AGENT` must print a contact string. If it is empty for the shell running the plan, run:

```bash
export EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com"
```

- [ ] **Step 2: Create bundle directories**

Run:

```bash
mkdir -p reports/saas-evolution/raw/edgarpack reports/saas-evolution/raw/external reports/saas-evolution/search-notes
```

Expected: the three directories exist.

- [ ] **Step 3: Create bundle README**

Create `reports/saas-evolution/README.md` with:

```markdown
# SaaS Evolution Research Bundle

Date started: 2026-04-29

## Question

How did the public SaaS business model change from roughly 2014 to 2026, and which filing-backed signals still tell investors something useful?

## Scope

The cohort is fixed at CRM, NOW, ADBE, TEAM, SHOP, DDOG, SNOW, MDB, ZM, HUBS, and WDAY. The anchor periods are 2014 or 2015, 2020, and the latest 2025 or 2026 annual filing or annual results release.

## Evidence Policy

EdgarPack is the primary research instrument. Use `query`, `build`, `which`, local packs, and cited source URLs before using company IR pages directly. External market research is allowed only for valuation and metric-regime context.

## Artifact Index

- `cohort.csv`: fixed company set and model hypotheses
- `filing-selection-notes.md`: filing choices and source fallbacks
- `edgarpack-run-log.md`: command log for report evidence
- `edgarpack-friction-log.md`: product gaps and follow-up bead IDs
- `edgarpack-investor-product-recommendations.md`: larger investor-product recommendations
- `standard-financials.csv`: cited financial metrics
- `business-model-table.csv`: economic-machine classification
- `kpi-disclosure-table.csv`: company-specific KPI evidence
- `metric-definition-table.csv`: metric definitions and comparability warnings
- `ai-packaging-table.csv`: AI monetization and packaging evidence
- `valuation-context-table.csv`: narrow market context
- `source-ledger.csv`: report-claim audit map
- `saas-evolution-report.md`: narrative memo derived from the tables
- `raw/edgarpack/`: raw EdgarPack command outputs
- `raw/external/`: source notes for external context
- `search-notes/`: company-specific evidence notes

## Execution Rule

Fill evidence tables first. Write the report last. File follow-up beads for EdgarPack friction instead of silently working around product gaps.
```

- [ ] **Step 4: Create cohort file**

Create `reports/saas-evolution/cohort.csv` with:

```csv
company,ticker,cik_hint,model_hypothesis,baseline_anchor,midpoint_anchor,current_anchor,notes
Salesforce,CRM,0001108524,enterprise_subscription_suite,2015,2020,latest_annual,"Use RPO/cRPO, attrition, Data Cloud and AI ARR where disclosed."
ServiceNow,NOW,0001373715,workflow_platform,2015,2020,latest_annual,"Use subscription revenue, cRPO, RPO, Now Assist or AI Agent disclosures."
Adobe,ADBE,0000796343,license_to_subscription_transition,2014,2020,latest_annual,"Use Creative Cloud ARR baseline and Digital Media ARR current state."
Atlassian,TEAM,0001650372,cloud_migration,ipo_or_first_observable,2020,latest_annual,"Use F-1 license/subscription baseline and Cloud/Data Center/Server mix."
Shopify,SHOP,0001594805,subscription_plus_transactions,ipo_or_first_observable,2020,latest_annual,"Use subscription solutions, merchant solutions, MRR, and GMV."
Datadog,DDOG,0001561550,usage_based_data_platform,ipo_or_first_observable,2020,latest_annual,"Use NRR, large-customer counts, revenue, FCF, and SBC."
Snowflake,SNOW,0001640147,usage_based_data_platform,ipo_or_first_observable,2020,latest_annual,"Use product revenue, NRR, RPO caveats, and million-dollar customers."
MongoDB,MDB,0001441816,usage_based_data_platform,ipo_or_first_observable,2020,latest_annual,"Use Atlas mix, ARR definition, revenue, and customer metrics."
Zoom,ZM,0001585521,seat_based_collaboration,ipo_or_first_observable,2020,latest_annual,"Use enterprise revenue share, net dollar expansion, and churn."
HubSpot,HUBS,0001404655,smb_customer_platform,ipo_or_first_observable,2020,latest_annual,"Use customer count, average subscription revenue per customer, and subscription retention."
Workday,WDAY,0001327811,human_capital_backlog_platform,2015,2020,latest_annual,"Use subscription revenue backlog, total backlog, and FCF."
```

- [ ] **Step 5: Initialize notes files**

Create `reports/saas-evolution/filing-selection-notes.md` with:

```markdown
# Filing Selection Notes

Use this file for exact filing choices, missing baseline periods, S-1 substitutions, annual results-release fallbacks, source URLs, and confidence limits.

## Rules

- Prefer annual 10-K, 20-F, or F-1/S-1 filings built through EdgarPack.
- Use company IR releases only when the latest annual filing is unavailable or a current metric is disclosed only in the release.
- Mark baseline rows as `ipo_or_first_observable` when the company was not public in 2014 or 2015.
- Record every direct SEC or IR source URL used outside EdgarPack.

## Notes
```

Create `reports/saas-evolution/edgarpack-run-log.md` with:

```markdown
# EdgarPack Run Log

Record every EdgarPack command that contributes evidence to the bundle.

| timestamp_et | command | output_path | result | notes |
| --- | --- | --- | --- | --- |
```

Create `reports/saas-evolution/edgarpack-friction-log.md` with:

```markdown
# EdgarPack Friction Log

Record product friction from using EdgarPack heavily. File follow-up beads for material issues.

| category | command_or_file | observed_behavior | expected_behavior | impact | bead_id | status |
| --- | --- | --- | --- | --- | --- | --- |
```

Create `reports/saas-evolution/edgarpack-investor-product-recommendations.md` with:

```markdown
# EdgarPack Investor Product Recommendations

This file is not a bug list. It captures larger product recommendations from using EdgarPack heavily for an investor-grade SaaS research workflow.

## Recommendation Standard

A recommendation belongs here only if it would materially change the quality, speed, or repeatability of real investor work.

Each recommendation must include:

- Investor problem: what a real investor is trying to decide.
- Research moment: where the SaaS evolution workflow exposed the need.
- Proposed product shape: the non-incremental capability EdgarPack should grow toward.
- Proof path: how the current bundle demonstrates the need.
- Candidate beads: concrete follow-up issues that break the direction into work.

## Recommendations
```

- [ ] **Step 6: Initialize CSV headers**

Run:

```bash
python3 -B - <<'PY'
from pathlib import Path

root = Path("reports/saas-evolution")
tables = {
    "standard-financials.csv": "company,ticker,cik,period_anchor,fiscal_year,filing_form,filing_date,accession,revenue,gross_margin,operating_margin,free_cash_flow,free_cash_flow_margin,r_and_d_intensity,sales_and_marketing_intensity,stock_based_compensation,stock_based_compensation_as_pct_revenue,citation_ids,source_url,confidence,notes\n",
    "business-model-table.csv": "company,ticker,period_anchor,model_type,revenue_model_summary,deployment_or_packaging_summary,usage_or_transaction_exposure,enterprise_or_smb_motion,platform_breadth_signal,evidence_locator,source_url,confidence,notes\n",
    "kpi-disclosure-table.csv": "company,ticker,period_anchor,kpi_name,kpi_value,kpi_unit,kpi_definition,kpi_category,section_id,chunk_id,source_excerpt,source_url,confidence,notes\n",
    "metric-definition-table.csv": "company,ticker,metric_name,definition_text,included_items,excluded_items,measurement_window,comparability_warning,source_locator,source_url,confidence,notes\n",
    "ai-packaging-table.csv": "company,ticker,ai_product_or_package,pricing_or_packaging_model,unit_of_value,disclosed_arr_acv_or_usage,margin_or_cost_commentary,source_type,source_url,confidence,notes\n",
    "valuation-context-table.csv": "source_name,source_date,regime,metric,value,context,source_url,confidence,notes\n",
    "source-ledger.csv": "artifact,row_id,company,ticker,claim_type,claim_text,evidence_type,evidence_locator,source_url,accession,confidence,notes\n",
}
for name, header in tables.items():
    (root / name).write_text(header)
PY
```

Expected: `cohort.csv` has the approved 11-company cohort; each evidence CSV has one header row and parses.

- [ ] **Step 7: Verify CSV headers parse**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

root = Path("reports/saas-evolution")
cohort = list(csv.DictReader((root / "cohort.csv").open(newline="")))
assert len(cohort) == 11, "cohort.csv should contain exactly 11 company rows"
assert {row["ticker"] for row in cohort} == {"CRM", "NOW", "ADBE", "TEAM", "SHOP", "DDOG", "SNOW", "MDB", "ZM", "HUBS", "WDAY"}

for path in sorted(root.glob("*.csv")):
    if path.name == "cohort.csv":
        print(f"ok {path}")
        continue
    with path.open(newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 1, f"{path} should contain header only"
    assert all(cell for cell in rows[0]), f"{path} contains an empty header cell"
    print(f"ok {path}")
PY
```

Expected: every `reports/saas-evolution/*.csv` prints `ok`, with `cohort.csv` validated for the approved populated cohort.

- [ ] **Step 8: Commit setup**

Run:

```bash
git add reports/saas-evolution
git commit -m "Add SaaS evolution research bundle scaffold"
```

Expected: commit succeeds with only `reports/saas-evolution/` files staged.

## Task 2: EdgarPack Identity, Filing Availability, And Run Log

**Files:**
- Modify: `reports/saas-evolution/filing-selection-notes.md`
- Modify: `reports/saas-evolution/edgarpack-run-log.md`
- Create: `reports/saas-evolution/raw/edgarpack/identify-*.txt`
- Create: `reports/saas-evolution/raw/edgarpack/list-*-10k.txt`

- [ ] **Step 1: Identify every cohort company**

Run:

```bash
for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do
  uv run edgarpack identify "$ticker" | tee "reports/saas-evolution/raw/edgarpack/identify-${ticker}.txt"
done
```

Expected: each output identifies a public SEC filer with a company name and CIK. If any ticker does not resolve, append a row to `edgarpack-friction-log.md` with category `identity`.

- [ ] **Step 2: List annual filings for every cohort company**

Run:

```bash
for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do
  uv run edgarpack list "$ticker" --form 10-K --limit 15 | tee "reports/saas-evolution/raw/edgarpack/list-${ticker}-10k.txt"
done
```

Expected: U.S. 10-K filers show recent annual filings. For companies where the baseline comes from F-1, S-1, 20-F, or an IR release, the 10-K list may not cover the baseline and that limitation must be recorded in filing notes.

- [ ] **Step 3: Add initial filing-selection notes**

Append this section to `reports/saas-evolution/filing-selection-notes.md`, replacing no prior content:

```markdown

## Initial Filing Availability Pass

- CRM: annual SEC path available through EdgarPack; use 10-Ks for current, 2020, and baseline where available.
- NOW: annual SEC path available through EdgarPack; use 10-Ks for current, 2020, and baseline where available.
- ADBE: annual SEC path available through EdgarPack; use 2014 or 2015 10-K for subscription-transition baseline.
- TEAM: use F-1 for baseline if no 2014 or 2015 10-K is available; use annual filings for 2020 and current.
- SHOP: use IPO/S-1 or first observable public-company filing for baseline; use annual filings or company IR releases where EdgarPack coverage is incomplete.
- DDOG: use S-1 for baseline; use annual filings for 2020 and current.
- SNOW: use S-1 or first observable public-company filing for baseline; use annual filings and IR release disclosures for current consumption metrics.
- MDB: use S-1 or first observable public-company filing for baseline; use annual filings and IR releases for Atlas mix where needed.
- ZM: use S-1 or first observable public-company filing for baseline; use annual filings for pandemic and current normalization.
- HUBS: use S-1 for baseline; use annual filings and IR releases for current customer-platform metrics where needed.
- WDAY: annual SEC path available through EdgarPack; use subscription revenue backlog and total backlog where disclosed.
```

- [ ] **Step 4: Update run log for identity and list commands**

Append rows to `reports/saas-evolution/edgarpack-run-log.md` for the two command loops:

```markdown
| 2026-04-29 | `for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do uv run edgarpack identify "$ticker"; done` | `raw/edgarpack/identify-*.txt` | pending review | Identity pass for full cohort. |
| 2026-04-29 | `for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do uv run edgarpack list "$ticker" --form 10-K --limit 15; done` | `raw/edgarpack/list-*-10k.txt` | pending review | Annual filing availability pass. |
```

- [ ] **Step 5: Commit availability pass**

Run:

```bash
git add reports/saas-evolution
git commit -m "Record SaaS cohort filing availability"
```

Expected: commit succeeds.

## Task 3: Standard Financials From EdgarPack Query

**Files:**
- Modify: `reports/saas-evolution/standard-financials.csv`
- Modify: `reports/saas-evolution/source-ledger.csv`
- Modify: `reports/saas-evolution/edgarpack-run-log.md`
- Modify: `reports/saas-evolution/edgarpack-friction-log.md`
- Create: `reports/saas-evolution/raw/edgarpack/query-*.json`
- Create: `reports/saas-evolution/search-notes/standard-financials.md`

- [ ] **Step 1: Query annual base metrics for the full cohort**

Run:

```bash
for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do
  uv run edgarpack query "$ticker" revenue,gross_margin,operating_margin,free_cash_flow,fcf_margin,r_and_d_intensity --period lfy,lfy-5,lfy-10 --format json > "reports/saas-evolution/raw/edgarpack/query-${ticker}-annual-core.json"
done
```

Expected: each command writes JSON. If a company lacks `lfy-10` because it was not public, keep the raw output and mark baseline as `ipo_or_first_observable` in later rows.

- [ ] **Step 2: Query current public SaaS comparison metrics**

Run:

```bash
uv run edgarpack comps CRM NOW ADBE WDAY --metrics revenue,gross_margin,operating_margin,free_cash_flow --period lfy --format json > reports/saas-evolution/raw/edgarpack/comps-enterprise-suites-lfy.json
uv run edgarpack comps DDOG SNOW MDB ZM --metrics revenue,gross_margin,operating_margin,free_cash_flow --period lfy --format json > reports/saas-evolution/raw/edgarpack/comps-usage-and-seat-lfy.json
```

Expected: both files contain JSON comparisons. If a metric is missing, keep the missing value and record it as an EdgarPack coverage gap only if the underlying filing clearly discloses it.

- [ ] **Step 3: Create standard-financials working note**

Create `reports/saas-evolution/search-notes/standard-financials.md` with:

```markdown
# Standard Financials Extraction Notes

Use raw EdgarPack query JSON under `raw/edgarpack/query-*-annual-core.json`.

Rules:

- Prefer values such as `metrics.revenue.lfy` when the JSON shape is a period map.
- Prefer values such as `metrics.revenue[]` when the JSON shape is a series.
- Carry over `company`, `cik`, `fiscal_year`, `fiscal_period`, `accession`, `form_type`, `filed`, `primary_link`, and `citation_ids`.
- Compute cross-year growth outside EdgarPack only after the source values are copied. Do not use derived offset-period growth outputs without checking components.
- If stock-based compensation is not available through this query pass, leave the field blank and fill it in Task 6 from filings or company releases.
```

- [ ] **Step 4: Populate `standard-financials.csv`**

For each ticker, add rows for these period anchors where the source JSON provides data:

```text
baseline
midpoint
current
```

Use this row convention:

```csv
company,ticker,cik,period_anchor,fiscal_year,filing_form,filing_date,accession,revenue,gross_margin,operating_margin,free_cash_flow,free_cash_flow_margin,r_and_d_intensity,sales_and_marketing_intensity,stock_based_compensation,stock_based_compensation_as_pct_revenue,citation_ids,source_url,confidence,notes
```

Rules:

- `source_url` must be the JSON value's `primary_link` when present.
- `citation_ids` must preserve EdgarPack citation IDs such as `C1;C4;D2`.
- Use `high` confidence when EdgarPack provides accession, filing date, source URL, and citation IDs.
- Use `medium` confidence when the value is sourced from a company IR release rather than an EdgarPack query citation.
- Do not invent missing values.

- [ ] **Step 5: Add source-ledger rows for standard financials**

For every row added to `standard-financials.csv`, add one corresponding row to `source-ledger.csv` with:

```text
artifact=standard-financials.csv
row_id=CRM-current
claim_type=standard_financial
evidence_type=edgarpack_query_json
evidence_locator=raw/edgarpack/query-CRM-annual-core.json
```

Expected: every standard-financial row has a ledger row.

- [ ] **Step 6: Log command outputs**

Append these rows to `reports/saas-evolution/edgarpack-run-log.md`:

```markdown
| 2026-04-29 | `for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do uv run edgarpack query "$ticker" revenue,gross_margin,operating_margin,free_cash_flow,fcf_margin,r_and_d_intensity --period lfy,lfy-5,lfy-10 --format json; done` | `raw/edgarpack/query-*-annual-core.json` | pending table extraction | Standard financial evidence. |
| 2026-04-29 | `uv run edgarpack comps CRM NOW ADBE WDAY --metrics revenue,gross_margin,operating_margin,free_cash_flow --period lfy --format json` | `raw/edgarpack/comps-enterprise-suites-lfy.json` | pending review | Current enterprise-suite comparison. |
| 2026-04-29 | `uv run edgarpack comps DDOG SNOW MDB ZM --metrics revenue,gross_margin,operating_margin,free_cash_flow --period lfy --format json` | `raw/edgarpack/comps-usage-and-seat-lfy.json` | pending review | Current usage and seat comparison. |
```

- [ ] **Step 7: Run CSV parse check**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

for name in ["standard-financials.csv", "source-ledger.csv"]:
    path = Path("reports/saas-evolution") / name
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"{name}: {len(rows)} rows")
    if name == "standard-financials.csv":
        for row in rows:
            assert row["ticker"], row
            assert row["period_anchor"], row
            assert row["accession"] or row["notes"], row
            assert row["source_url"] or row["notes"], row
PY
```

Expected: prints row counts and exits 0.

- [ ] **Step 8: Commit standard financials**

Run:

```bash
git add reports/saas-evolution
git commit -m "Add SaaS standard financial evidence"
```

Expected: commit succeeds.

## Task 4: Build Packs And Discover Company-Specific KPIs

**Files:**
- Modify: `reports/saas-evolution/kpi-disclosure-table.csv`
- Modify: `reports/saas-evolution/source-ledger.csv`
- Modify: `reports/saas-evolution/edgarpack-run-log.md`
- Modify: `reports/saas-evolution/edgarpack-friction-log.md`
- Create: `reports/saas-evolution/raw/edgarpack/build-*.txt`
- Create: `reports/saas-evolution/raw/edgarpack/which-*.json`
- Create: `reports/saas-evolution/search-notes/kpi-discovery.md`

- [ ] **Step 1: Build recent annual packs with chunks**

Run:

```bash
for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do
  uv run edgarpack build "$ticker" --form 10-K --last 3 --with-chunks | tee "reports/saas-evolution/raw/edgarpack/build-${ticker}-10k-last3.txt"
done
```

Expected: each command builds or skips already registered packs. If a ticker needs a form other than 10-K for baseline evidence, record that in `filing-selection-notes.md` and handle it through targeted source reads.

- [ ] **Step 2: Run KPI discovery**

Run:

```bash
for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do
  uv run edgarpack which "$ticker" --format json > "reports/saas-evolution/raw/edgarpack/which-${ticker}.json"
done
```

Expected: each file contains JSON. If a `which` output has `source_substring` but no `chunk_id`, record the behavior in `edgarpack-friction-log.md` because chunk-backed evidence is better for the report.

- [ ] **Step 3: Create KPI extraction notes**

Create `reports/saas-evolution/search-notes/kpi-discovery.md` with:

```markdown
# KPI Discovery Notes

Use `raw/edgarpack/which-*.json` first.

Target KPIs by company:

- CRM: attrition, RPO, cRPO, Data Cloud and AI ARR, employees.
- NOW: subscription revenue, cRPO, RPO, Now Assist or AI ACV, customer-count thresholds.
- ADBE: Creative Cloud subscriptions, Creative ARR, Digital Media ARR, Firefly or AI credit packaging.
- TEAM: Cloud/Data Center/Server revenue mix, Marketplace or other revenue.
- SHOP: MRR, GMV, subscription solutions, merchant solutions.
- DDOG: dollar-based net retention, customers above $100K ARR, customers above $1M ARR.
- SNOW: product revenue, NRR, RPO, customers above $1M product revenue.
- MDB: Atlas revenue mix, Atlas ARR definition, customer metrics.
- ZM: enterprise revenue share, net dollar expansion, online churn.
- HUBS: customer count, average subscription revenue per customer, subscription dollar retention.
- WDAY: subscription revenue backlog, total subscription backlog.

If `which` misses a target KPI, use built filing sections or company IR pages and record the fallback in `source-ledger.csv`.
```

- [ ] **Step 4: Populate KPI table**

Add rows to `kpi-disclosure-table.csv` for all target KPIs found through `which` or targeted filing reads.

Rules:

- `section_id` comes from `which` output when available.
- `chunk_id` comes from `which` output when available. Leave blank only if the source lacks chunk ID and record the limitation in `notes`.
- `source_excerpt` must be a short excerpt or paraphrase from `source_substring` or the filing section.
- `source_url` must be the SEC, IR, or local pack source that allows review.
- `confidence` is `high` for primary filing or company IR evidence, `medium` for external context, and `low` only for rows kept as unresolved leads.

- [ ] **Step 5: Add source-ledger rows for KPIs**

For each KPI row, add one row to `source-ledger.csv` with:

```text
artifact=kpi-disclosure-table.csv
row_id=CRM-current-rpo
claim_type=kpi_disclosure
evidence_type=edgarpack_which_json OR filing_section OR company_ir_release
evidence_locator=raw/edgarpack/which-CRM.json
```

Expected: no KPI row lacks a source-ledger row.

- [ ] **Step 6: Log KPI commands**

Append rows to `edgarpack-run-log.md`:

```markdown
| 2026-04-29 | `for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do uv run edgarpack build "$ticker" --form 10-K --last 3 --with-chunks; done` | `raw/edgarpack/build-*-10k-last3.txt` | pending review | Built recent annual packs for source reading and KPI discovery. |
| 2026-04-29 | `for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do uv run edgarpack which "$ticker" --format json; done` | `raw/edgarpack/which-*.json` | pending table extraction | Company-specific KPI discovery. |
```

- [ ] **Step 7: Run KPI table QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

path = Path("reports/saas-evolution/kpi-disclosure-table.csv")
with path.open(newline="") as f:
    rows = list(csv.DictReader(f))
print(f"kpi rows: {len(rows)}")
for row in rows:
    assert row["ticker"], row
    assert row["kpi_name"], row
    assert row["kpi_category"], row
    assert row["source_excerpt"] or row["notes"], row
    assert row["source_url"] or row["notes"], row
PY
```

Expected: prints row count and exits 0.

- [ ] **Step 8: Commit KPI evidence**

Run:

```bash
git add reports/saas-evolution
git commit -m "Add SaaS KPI disclosure evidence"
```

Expected: commit succeeds.

## Task 5: Business Model And Metric Definition Evidence

**Files:**
- Modify: `reports/saas-evolution/business-model-table.csv`
- Modify: `reports/saas-evolution/metric-definition-table.csv`
- Modify: `reports/saas-evolution/source-ledger.csv`
- Modify: `reports/saas-evolution/filing-selection-notes.md`
- Create: `reports/saas-evolution/search-notes/metric-definitions.md`

- [ ] **Step 1: Create metric-definition notes**

Create `reports/saas-evolution/search-notes/metric-definitions.md` with:

```markdown
# Metric Definition Notes

Capture exact definitions and comparability warnings from primary sources.

Required definitions:

- Adobe ARR: paid subscriptions times average monthly price times 12 plus annual ETLA contract value, plus Adobe's warning not to combine ARR with revenue, deferred revenue, or unbilled deferred revenue.
- Salesforce RPO/cRPO: future revenue under contract, affected by renewals, contract duration, FX, acquisitions, and billing structure.
- ServiceNow cRPO: contract revenue expected to be recognized in the next 12 months.
- Snowflake NRR and RPO caveat: product revenue consumption timing means RPO is not necessarily indicative of future product revenue growth.
- MongoDB Atlas ARR: annualized recent actual usage, with Direct Sales Atlas based on the prior 90 days and self-serve based on the prior 30 days where disclosed.
- Datadog FCF: operating cash flow less capex and capitalized software development costs where disclosed.
```

- [ ] **Step 2: Fill business-model rows**

Populate `business-model-table.csv` with at least one current row per cohort company and one baseline row where evidence is available.

Use this model mapping unless the filings contradict it:

```text
CRM -> enterprise_subscription_suite
NOW -> workflow_platform
ADBE -> license_to_subscription_transition
TEAM -> cloud_migration
SHOP -> subscription_plus_transactions
DDOG -> usage_based_data_platform
SNOW -> usage_based_data_platform
MDB -> usage_based_data_platform
ZM -> seat_based_collaboration
HUBS -> smb_customer_platform
WDAY -> human_capital_backlog_platform
```

Rules:

- `revenue_model_summary` must name the revenue streams the filing or IR source discloses.
- `deployment_or_packaging_summary` must describe seats, cloud, server, data center, usage, or transaction mix where disclosed.
- `evidence_locator` must point to a raw EdgarPack output, filing section, pack path, or source URL.
- Add one source-ledger row per business-model row.

- [ ] **Step 3: Fill metric-definition rows**

Populate `metric-definition-table.csv` with one row per required definition from Step 1 where source evidence is found.

Rules:

- Copy or closely paraphrase definitions without long quotation.
- `comparability_warning` must explain why the metric cannot be blindly compared across SaaS companies.
- `source_locator` must point to an EdgarPack pack section, raw `which` output, SEC source, or IR source.
- Add one source-ledger row per metric-definition row.

- [ ] **Step 4: Update filing-selection notes with fallback sources**

Append a section to `filing-selection-notes.md`:

```markdown

## Metric Definition Fallbacks

Definitions that were not captured cleanly by EdgarPack are sourced directly from the linked SEC or IR pages and recorded in `metric-definition-table.csv` plus `source-ledger.csv`.
```

Below that sentence, list each direct fallback source actually used in bullet form.

- [ ] **Step 5: Run business-model and definition QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

checks = {
    "business-model-table.csv": ["ticker", "period_anchor", "model_type", "evidence_locator", "source_url"],
    "metric-definition-table.csv": ["ticker", "metric_name", "definition_text", "comparability_warning", "source_locator", "source_url"],
}
for name, required in checks.items():
    path = Path("reports/saas-evolution") / name
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"{name}: {len(rows)} rows")
    for row in rows:
        for col in required:
            assert row[col] or row["notes"], f"{name} missing {col}: {row}"
PY
```

Expected: prints row counts and exits 0.

- [ ] **Step 6: Commit business model and definitions**

Run:

```bash
git add reports/saas-evolution
git commit -m "Add SaaS business model and metric definitions"
```

Expected: commit succeeds.

## Task 6: AI Packaging And Valuation Context

**Files:**
- Modify: `reports/saas-evolution/ai-packaging-table.csv`
- Modify: `reports/saas-evolution/valuation-context-table.csv`
- Modify: `reports/saas-evolution/source-ledger.csv`
- Create: `reports/saas-evolution/raw/external/ai-packaging-sources.md`
- Create: `reports/saas-evolution/raw/external/valuation-context-sources.md`

- [ ] **Step 1: Create AI packaging source note**

Create `reports/saas-evolution/raw/external/ai-packaging-sources.md` with:

```markdown
# AI Packaging Sources

Use these sources only for AI packaging and monetization framing. Do not let them override primary filing evidence.

- Salesforce pricing update 2025: https://www.salesforce.com/news/stories/pricing-update-2025/
- Salesforce FY2026 Q3 release: https://investor.salesforce.com/news/news-details/2025/Salesforce-Delivers-Record-Third-Quarter-Fiscal-2026-Results-Driven-by-Agentforce--Data-360/default.aspx
- ServiceNow FY2024 Q4 release: https://newsroom.servicenow.com/press-releases/details/2025/ServiceNow-Reports-Fourth-Quarter-and-Full-Year-2024-Financial-Results-01-29-2025-traffic/default.aspx
- ServiceNow agentic AI release: https://newsroom.servicenow.com/press-releases/details/2025/ServiceNow-announces-new-agentic-AI-innovations-to-autonomously-solve-the-most-complex-enterprise-challenges-01-29-2025-traffic/default.aspx
- Adobe Firefly plans: https://www.adobe.com/products/firefly/plans.html
- Adobe Creative Cloud Pro announcement: https://blog.adobe.com/en/publish/2025/05/15/meet-creative-cloud-pro-new-tools-expansive-creative-controls
- Atlassian Rovo usage limits: https://support.atlassian.com/rovo/docs/rovo-usage-limits/
- Atlassian Rovo Dev pricing: https://www.atlassian.com/software/rovo-dev/pricing
- GitLab Duo Pro pricing release: https://about.gitlab.com/press/releases/2024-01-17-gitlab-announces-pricing-of-gitlab-duo-pro/
- GitLab pricing: https://about.gitlab.com/pricing/
- OpenView usage-based pricing: https://openviewpartners.com/usage-based-pricing/
- Bessemer State of AI 2025: https://www.bvp.com/atlas/the-state-of-ai-2025
```

- [ ] **Step 2: Populate AI packaging table**

Add rows for:

```text
Salesforce Agentforce / Flex Credits
ServiceNow Now Assist or AI Agents
Adobe Firefly / Creative Cloud Pro credits
Atlassian Rovo / Rovo Dev credits
GitLab Duo / GitLab Credits
```

Rules:

- `pricing_or_packaging_model` must name whether the source describes seat add-on, credit bucket, usage/consumption, included bundle, or hybrid.
- `unit_of_value` must name user, credit, token, query, job, developer, or work unit when disclosed.
- `disclosed_arr_acv_or_usage` must be blank unless the source gives ARR, ACV, deal count, token count, or customer count.
- `source_type` must be `company_pricing_page`, `company_ir_release`, `company_blog`, or `external_practitioner_context`.
- Add one source-ledger row per AI packaging row.

- [ ] **Step 3: Create valuation context source note**

Create `reports/saas-evolution/raw/external/valuation-context-sources.md` with:

```markdown
# Valuation Context Sources

Use these sources for market-regime context only.

- Bessemer State of the Cloud 2022: https://www.bvp.com/atlas/state-of-the-cloud-2022
- OpenView 2023 SaaS Benchmarks: https://openviewpartners.com/2023-saas-benchmarks-report/
- Meritech Software Pulse, 2024-03-07: https://www.meritechcapital.com/blog/meritech-software-pulse-or-07-mar-2024
- Battery OpenCloud 2024: https://www.battery.com/blog/opencloud-2024/
- Battery OpenCloud 2024 PDF: https://www.battery.com/wp-content/uploads/2024/11/Battery-OpenCloud-Report-2024_vFINAL_v2.pdf
- SaaS Metrics Standards Board ARR: https://www.saasmetricsboard.com/annual-recurring-revenue
- SaaS Metrics Standards Board NRR: https://www.saasmetricsboard.com/net-revenue-retention
- SaaS Metrics Standards Board Gross Retention: https://www.saasmetricsboard.com/gross-revenue-retention
- SaaS Metrics Standards Board CAC Payback: https://www.saasmetricsboard.com/cac-payback-period
- SaaS Metrics Standards Board Blended CAC Ratio: https://www.saasmetricsboard.com/blended-cac-ratio
- SaaS Metrics Standards Board Rule of 40: https://www.saasmetricsboard.com/rule-of-40
- McKinsey SaaS Rule of 40: https://www.mckinsey.com/industries/technology-media-and-telecommunications/our-insights/saas-and-the-rule-of-40-keys-to-the-critical-value-creation-metric
```

- [ ] **Step 4: Populate valuation context table**

Add concise rows for these regime facts:

```text
2021 cloud peak and 2022 reset
2023 growth slowdown and profitability shift
2024 public SaaS multiple stabilization
Rule of 40 composition and growth/profitability weighting
NRR/expansion weakening
AI-native gross margin pressure
```

Rules:

- One row per sourced fact.
- Keep `context` short enough to support the report, not reproduce the source.
- Add one source-ledger row per valuation-context row.

- [ ] **Step 5: Run context table QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

for name in ["ai-packaging-table.csv", "valuation-context-table.csv"]:
    path = Path("reports/saas-evolution") / name
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"{name}: {len(rows)} rows")
    for row in rows:
        assert row["source_url"], row
        assert row["confidence"], row
PY
```

Expected: prints row counts and exits 0.

- [ ] **Step 6: Commit AI and valuation context**

Run:

```bash
git add reports/saas-evolution
git commit -m "Add SaaS AI packaging and valuation context"
```

Expected: commit succeeds.

## Task 7: Write The Investor Memo From Evidence Tables

**Files:**
- Create: `reports/saas-evolution/saas-evolution-report.md`
- Modify: `reports/saas-evolution/source-ledger.csv`

- [ ] **Step 1: Draft report skeleton**

Create `reports/saas-evolution/saas-evolution-report.md` with:

```markdown
# The SaaS Contract Changed

Date: 2026-04-29

## Opening Thesis

## The Baseline: What SaaS Asked Investors To Believe

## The Platforming Phase

## The Reset

## The Metric Audit

## The AI Packaging Shift

## Cases That Break The Simple Story

## What EdgarPack Proved

## What EdgarPack Needs Next
```

- [ ] **Step 2: Write opening thesis**

Write the opening thesis using only claims already present in:

```text
standard-financials.csv
business-model-table.csv
kpi-disclosure-table.csv
metric-definition-table.csv
ai-packaging-table.csv
valuation-context-table.csv
```

Required content:

- State that SaaS fragmented into multiple economic machines.
- Name at least one enterprise-suite example, one cloud-migration example, one usage-based example, one seat-based normalization example, and one AI-packaging example.
- Add source-ledger rows for any new synthesis claim with `artifact=saas-evolution-report.md` and `claim_type=narrative_synthesis`.

- [ ] **Step 3: Write baseline section**

Write `## The Baseline: What SaaS Asked Investors To Believe`.

Required content:

- Adobe subscription-transition evidence.
- Shopify subscription-plus-merchant evidence if source-backed.
- HubSpot or Datadog IPO/S-1 metric evidence if source-backed.
- Explain why ARR, customer count, retention, and early platform expansion were the baseline investor language.

- [ ] **Step 4: Write platforming section**

Write `## The Platforming Phase`.

Required content:

- Salesforce or ServiceNow backlog/RPO/cRPO evidence.
- Atlassian cloud migration evidence.
- Workday backlog evidence if source-backed.
- Show how platform breadth changed what investors had to monitor.

- [ ] **Step 5: Write reset section**

Write `## The Reset`.

Required content:

- Valuation-context rows for 2021 peak, 2022 reset, and 2024 stabilization.
- Tie the external market reset back to filing-backed free cash flow, operating margin, and growth evidence.
- Avoid broad claims about all SaaS companies unless the table supports them.

- [ ] **Step 6: Write metric audit section**

Write `## The Metric Audit`.

Required content:

- ARR is not GAAP revenue, bookings, or backlog.
- NRR definitions vary and usage-based models complicate it.
- RPO/cRPO is useful but can mislead when contract duration, renewals, FX, or consumption timing move.
- Rule of 40 and FCF margin need SBC and definition scrutiny.
- Use Snowflake, MongoDB, Datadog, Salesforce, and ServiceNow as examples where available.

- [ ] **Step 7: Write AI packaging section**

Write `## The AI Packaging Shift`.

Required content:

- Salesforce Agentforce/Flex Credits.
- ServiceNow consumption posture.
- Adobe Firefly or Creative Cloud Pro credits.
- Atlassian or GitLab credit model.
- Explain the investor question: whether AI is price increase, retention bundle, usage monetization, or margin pressure.

- [ ] **Step 8: Write story-breaking cases**

Write `## Cases That Break The Simple Story`.

Required cases:

- Snowflake: usage consumption makes RPO less comparable to classic enterprise backlog.
- Zoom: enterprise mix can improve while net expansion falls below 100%.
- Shopify: SaaS plus merchant/transaction economics is not a pure seat SaaS model.
- Adobe: license-to-subscription transition created a different baseline than cloud-native SaaS.

- [ ] **Step 9: Write EdgarPack proof and next-work sections**

Write `## What EdgarPack Proved` and `## What EdgarPack Needs Next`.

Required content:

- Mention cited multi-period financials.
- Mention cleaned filing packs and `which` KPI discovery.
- Mention metric-definition work and source-ledger discipline.
- Mention friction from `edgarpack-friction-log.md`.
- Mention larger product recommendations from `edgarpack-investor-product-recommendations.md`.
- Do not claim a feature worked unless the run log supports it.

- [ ] **Step 10: Run uncited-claim review**

Run:

```bash
python3 -B - <<'PY'
from pathlib import Path

report = Path("reports/saas-evolution/saas-evolution-report.md").read_text()
required_strings = [
    "standard-financials.csv",
    "business-model-table.csv",
    "kpi-disclosure-table.csv",
    "metric-definition-table.csv",
    "ai-packaging-table.csv",
    "valuation-context-table.csv",
    "source-ledger.csv",
]
missing = [s for s in required_strings if s not in report]
if missing:
    print("Report should explicitly point readers to evidence tables:", missing)
    raise SystemExit(1)
print("report evidence-table references present")
PY
```

Expected: exits 0. If it fails, add a short evidence-method paragraph that names the tables.

- [ ] **Step 11: Commit report draft**

Run:

```bash
git add reports/saas-evolution
git commit -m "Write SaaS evolution report"
```

Expected: commit succeeds.

## Task 8: Friction Beads And Final Verification

**Files:**
- Modify: `reports/saas-evolution/edgarpack-friction-log.md`
- Modify: `reports/saas-evolution/edgarpack-investor-product-recommendations.md`
- Modify: `reports/saas-evolution/source-ledger.csv`
- Modify: `.beads` state through `bd`

- [ ] **Step 1: Review friction log and investor-product opportunities**

Open `reports/saas-evolution/edgarpack-friction-log.md` and identify every material issue with impact `blocks_report`, `weakens_evidence`, or `slows_workflow`.

Material categories:

```text
derived_metric_correctness
missing_kpi_chunk_ids
missing_saas_metric_preset
manual_source_ledger_overhead
identity_or_filing_selection_gap
report_export_gap
```

Then open `reports/saas-evolution/edgarpack-investor-product-recommendations.md` and add 3 to 6 larger recommendations. Use this structure for each recommendation:

```markdown
### SaaS metric pack with ARR, RPO, cRPO, NRR, and SBC semantics

Investor problem: A public-software investor needs to compare SaaS quality without treating ARR, RPO, NRR, FCF, and SBC as if every company defines them the same way.

Research moment: The SaaS bundle required separate `standard-financials.csv`, `kpi-disclosure-table.csv`, and `metric-definition-table.csv` work because no single EdgarPack preset captured the investor metric pack.

Proposed product shape: Add a SaaS research preset that returns core financials, company-specific SaaS KPIs, definitions, warnings, and citation-backed comparability notes in one structured output.

Proof path: `reports/saas-evolution/standard-financials.csv`, `reports/saas-evolution/kpi-disclosure-table.csv`, `reports/saas-evolution/metric-definition-table.csv`, and `reports/saas-evolution/edgarpack-run-log.md`.

Candidate beads:

- Add a SaaS preset spanning ARR, RPO, cRPO, NRR, FCF, SBC, and sales efficiency.
- Add comparability warnings for SaaS metrics whose definitions vary across companies.
```

Expected recommendation themes to consider:

```text
SaaS metric pack with ARR/RPO/cRPO/NRR/SBC semantics
Research bundle generator with source-ledger automation
Investor memo mode that refuses uncited company claims
Filing-backed KPI definition registry by company and metric
Disclosure-change timeline for business-model and metric-definition changes
Company archetype comparator for business-model cohorts
```

Do not add a recommendation unless the SaaS workflow produced evidence for it.

- [ ] **Step 2: File beads for material issues and recommendation seeds**

For each material issue, run a `bd create` command. Use this template:

```bash
bd create "Improve SaaS research workflow: preserve chunk IDs in KPI discovery" --type task --priority 3 --description "Repro command:
uv run edgarpack which CRM --format json

Observed:
Some KPI rows include source_substring and section_id but no chunk_id.

Expected:
KPI discoveries from built packs should include chunk IDs when the source text comes from a chunked pack.

Impact:
The SaaS research bundle can cite source excerpts, but evidence auditability is weaker than the rest of EdgarPack's citation model."
```

Expected: each command prints a bead ID.

For each larger recommendation, file at least one seed bead if no existing bead already captures it:

```bash
bd create "Investor workflow: SaaS metric pack with definitions and warnings" --type task --priority 2 --description "Investor problem:
A public-software investor needs to compare SaaS quality without treating ARR, RPO, cRPO, NRR, FCF, and SBC as if every company defines them the same way.

Research evidence:
reports/saas-evolution/standard-financials.csv
reports/saas-evolution/kpi-disclosure-table.csv
reports/saas-evolution/metric-definition-table.csv
reports/saas-evolution/edgarpack-run-log.md

Proposed product direction:
Add a SaaS research preset that returns core financials, discovered SaaS KPIs, metric definitions, source URLs, citation IDs, and comparability warnings.

First shippable slice:
Extend `edgarpack query --preset perf` or add a new preset that includes FCF, SBC, sales-and-marketing intensity, and RPO/cRPO when available, with explicit missing-value diagnostics."
```

- [ ] **Step 3: Add bead IDs to friction log and recommendations**

For every filed friction bead, update the matching `edgarpack-friction-log.md` row:

```text
bead_id=edgarpack-abc
status=filed
```

For every recommendation seed bead, add the bead ID under the relevant recommendation in `edgarpack-investor-product-recommendations.md`.

- [ ] **Step 4: Parse all CSV artifacts**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

root = Path("reports/saas-evolution")
for path in sorted(root.glob("*.csv")):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"{path.name}: {len(rows)} data rows")
    assert csv.DictReader(path.open(newline="")).fieldnames, path
PY
```

Expected: every CSV parses and prints a row count.

- [ ] **Step 5: Check source-ledger coverage**

Run:

```bash
python3 -B - <<'PY'
import csv
from collections import Counter
from pathlib import Path

ledger = Path("reports/saas-evolution/source-ledger.csv")
with ledger.open(newline="") as f:
    rows = list(csv.DictReader(f))
assert rows, "source-ledger.csv has no data rows"
missing = [r for r in rows if not r["source_url"] and not r["evidence_locator"]]
assert not missing, missing[:3]
print(Counter(r["artifact"] for r in rows))
PY
```

Expected: prints artifact coverage and exits 0.

- [ ] **Step 6: Check report exists and names friction log**

Run:

```bash
python3 -B - <<'PY'
from pathlib import Path

report = Path("reports/saas-evolution/saas-evolution-report.md")
text = report.read_text()
assert "What EdgarPack Proved" in text
assert "What EdgarPack Needs Next" in text
assert "edgarpack-friction-log.md" in text
assert "edgarpack-investor-product-recommendations.md" in text
print("report closeout sections present")
PY
```

Expected: exits 0.

- [ ] **Step 7: Commit verification and beads**

Run:

```bash
git add reports/saas-evolution
bd sync
git add .beads
git commit -m "Record SaaS research follow-up beads"
```

Expected: commit succeeds. If `.beads` is gitignored and `git add .beads` stages nothing, commit only the report artifact changes and mention that `bd sync` handled bead state.

- [ ] **Step 8: Final repo closeout**

Run:

```bash
git pull --rebase
bd sync
git push
git status
```

Expected:

- Pull/rebase succeeds or reports branch already up to date.
- `bd sync` succeeds.
- Push succeeds.
- `git status` reports no uncommitted changes except unrelated pre-existing untracked files that were present before this plan.

## Self-Review

Spec coverage:

- The bundle path and required files are covered in Task 1.
- EdgarPack-heavy workflow is covered in Tasks 2, 3, and 4.
- The 11-company cohort and anchor periods are covered in Task 1 and Task 2.
- Standard financials, business model, KPI, metric-definition, AI-packaging, valuation-context, and source-ledger tables are covered in Tasks 3 through 6.
- The investor memo is covered in Task 7.
- Follow-up beads and friction capture are covered in Task 8.
- Artifact QA and no-code-default verification are covered in Tasks 1, 3, 4, 5, 6, 7, and 8.

Placeholder scan:

- The plan uses concrete commands, file paths, row conventions, and acceptance rules.
- Where exact source values depend on live EdgarPack output, the plan specifies the command, output path, row convention, and acceptance rule.

Type and path consistency:

- All artifact paths live under `reports/saas-evolution/`.
- All CSV names match the spec.
- Raw EdgarPack outputs live under `reports/saas-evolution/raw/edgarpack/`.
- External framing notes live under `reports/saas-evolution/raw/external/`.
