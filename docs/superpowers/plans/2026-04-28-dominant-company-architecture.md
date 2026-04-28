# Dominant Company Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a citation-backed research bundle and investor-style report comparing the architecture of dominant public companies in 1996 versus 2026.

**Architecture:** This is a research-production workflow, not an EdgarPack code change. It reuses the existing founder-control validation slice as the control-module seed, creates a new `reports/dominant-company-architecture/` bundle, fills separate evidence tables for control, governance, operating profile, capital allocation, and KPI disclosure, then assigns archetypes only after the evidence tables are populated. The narrative report is derived from the tables and must cite row-level evidence.

**Tech Stack:** EdgarPack CLI via `uv run`, SEC EDGAR filings, local packs under `packs/`, Markdown, CSV, shell commands, Python standard library CSV QA, and manual filing review. Required environment: `EDGARPACK_USER_AGENT`.

---

## Scope Check

The spec covers one cohesive research bundle with five evidence modules. It does not require a new command, dashboard, database schema, package dependency, or extractor subsystem. If the research pass becomes too large, ship the minimal version defined in Task 7: complete control and governance tables, operating profile for the key numeric fields, capital allocation for cash-flow posture, and KPI rows only where the filing foregrounds recurring metrics.

## File Structure

- Create: `reports/dominant-company-architecture/README.md`
  - Bundle index, source policy, evidence rules, and execution log.
- Create: `reports/dominant-company-architecture/cohorts.csv`
  - Copy of the frozen primary and context cohorts from `reports/founder-control-era/cohorts.csv`.
- Create: `reports/dominant-company-architecture/company-life-arc.csv`
  - Copy of life-arc rows from the founder-control bundle, extended as new companies are validated.
- Create: `reports/dominant-company-architecture/filing-selection-notes.md`
  - Judgment calls for filing choices, predecessor mappings, raw SEC anchors, exclusions, and confidence limits.
- Create: `reports/dominant-company-architecture/control-table.csv`
  - Founder, family, institutional, professional-manager, and other control evidence.
- Create: `reports/dominant-company-architecture/governance-table.csv`
  - Share-class, board, committee, director-election, proxy-access, takeover-defense, and auditor evidence.
- Create: `reports/dominant-company-architecture/operating-profile-table.csv`
  - Revenue, margin, R&D, capex, employees, segment mix, and geography.
- Create: `reports/dominant-company-architecture/capital-allocation-table.csv`
  - Dividends, repurchases, cash, securities, debt, acquisitions, and cash-flow posture.
- Create: `reports/dominant-company-architecture/kpi-disclosure-table.csv`
  - Recurring company-specific operating KPIs discovered from filings.
- Create: `reports/dominant-company-architecture/architecture-archetypes.csv`
  - Evidence-derived company archetype assignments.
- Create: `reports/dominant-company-architecture/evidence-ledger.csv`
  - Row-level audit map from table rows to chunks, raw SEC line anchors, or cohort citations.
- Create: `reports/dominant-company-architecture/search-notes/`
  - Compact notes for companies with difficult filing sections or predecessor issues.
- Create: `reports/dominant-company-architecture/dominant-company-architecture-report.md`
  - Investor-style narrative report derived from the tables.
- Modify: no application code.
- Test: no code tests unless application code changes. Use artifact QA in every task.

## Task 1: Bundle Setup And Seed Data

**Files:**
- Create: `reports/dominant-company-architecture/README.md`
- Create: `reports/dominant-company-architecture/cohorts.csv`
- Create: `reports/dominant-company-architecture/company-life-arc.csv`
- Create: `reports/dominant-company-architecture/filing-selection-notes.md`
- Create: `reports/dominant-company-architecture/control-table.csv`
- Create: `reports/dominant-company-architecture/governance-table.csv`
- Create: `reports/dominant-company-architecture/operating-profile-table.csv`
- Create: `reports/dominant-company-architecture/capital-allocation-table.csv`
- Create: `reports/dominant-company-architecture/kpi-disclosure-table.csv`
- Create: `reports/dominant-company-architecture/architecture-archetypes.csv`
- Create: `reports/dominant-company-architecture/evidence-ledger.csv`
- Create: `reports/dominant-company-architecture/search-notes/`

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

`EDGARPACK_USER_AGENT` must print a contact string. If it is empty, run:

```bash
export EDGARPACK_USER_AGENT="Samay Dhawan samay58@gmail.com"
```

- [ ] **Step 2: Create the bundle directory**

Run:

```bash
mkdir -p reports/dominant-company-architecture/search-notes
```

Expected: `reports/dominant-company-architecture/search-notes/` exists.

- [ ] **Step 3: Seed cohort and life-arc files**

Run:

```bash
cp reports/founder-control-era/cohorts.csv reports/dominant-company-architecture/cohorts.csv
cp reports/founder-control-era/company-life-arc.csv reports/dominant-company-architecture/company-life-arc.csv
```

Expected:

```bash
wc -l reports/dominant-company-architecture/cohorts.csv
wc -l reports/dominant-company-architecture/company-life-arc.csv
```

`cohorts.csv` should print `61`. `company-life-arc.csv` should print at least `13`.

- [ ] **Step 4: Write the README**

Create `reports/dominant-company-architecture/README.md` with:

```markdown
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
```

- [ ] **Step 5: Write filing notes header**

Create `reports/dominant-company-architecture/filing-selection-notes.md` with:

```markdown
# Filing Selection Notes

Use this file for judgment calls: missing exact-year filings, predecessor mappings, raw SEC line anchors, companies with no meaningful founder concept, annual-report fallbacks, and table confidence limits.

## Existing Limitation

The founder-control validation pass found that several pre-2000 SEC `.txt` filings build as directory-listing packs. Until `edgarpack-eob` is fixed, use `raw_sec_txt` anchors for those rows and record them in `evidence-ledger.csv`.

## Notes
```

- [ ] **Step 6: Initialize table headers**

Run:

```bash
python3 -B - <<'PY'
from pathlib import Path

root = Path("reports/dominant-company-architecture")
tables = {
    "control-table.csv": "company,ticker,cik,cohort_name,cohort_year,comparison_point,filing_form,filing_date,accession,source_path,control_type,founder_or_family_names,founder_executive_role,founder_board_role,economic_ownership_pct,voting_power_pct,control_mechanism,controlled_company_status,control_signal,evidence_chunk_ids,evidence_excerpt,confidence,notes\n",
    "governance-table.csv": "company,ticker,cohort_name,cohort_year,filing_form,filing_date,accession,share_classes,director_election_structure,board_independence_signal,committee_independence_signal,classified_board_or_staggered_terms,proxy_access_or_shareholder_nomination_rights,takeover_defense_signal,auditor,evidence_chunk_ids,evidence_excerpt,confidence,notes\n",
    "operating-profile-table.csv": "company,ticker,cohort_name,cohort_year,filing_form,filing_date,accession,revenue,operating_income,net_income,gross_margin,operating_margin,r_and_d_expense,r_and_d_intensity,capex,capex_intensity,employees,segment_mix_summary,geographic_mix_summary,evidence_chunk_ids,evidence_excerpt,confidence,notes\n",
    "capital-allocation-table.csv": "company,ticker,cohort_name,cohort_year,filing_form,filing_date,accession,dividends,share_repurchases,cash_and_equivalents,marketable_securities,total_debt,major_acquisition_signal,capital_allocation_summary,evidence_chunk_ids,evidence_excerpt,confidence,notes\n",
    "kpi-disclosure-table.csv": "company,ticker,cohort_name,cohort_year,filing_form,filing_date,accession,kpi_name,kpi_value,kpi_unit,kpi_section,kpi_category,evidence_chunk_ids,evidence_excerpt,confidence,notes\n",
    "architecture-archetypes.csv": "company,ticker,cohort_name,cohort_year,assigned_archetype,control_rationale,governance_rationale,operating_rationale,capital_allocation_rationale,kpi_rationale,evidence_row_refs,confidence,notes\n",
    "evidence-ledger.csv": "table_name,row_company,row_ticker,row_cohort_name,row_comparison_point,claim_type,evidence_type,evidence_locator,source_path,accession,claim_text,confidence,notes\n",
}
for name, header in tables.items():
    (root / name).write_text(header)
PY
```

Expected: every CSV listed above has exactly one header row.

- [ ] **Step 7: Seed control rows from the validation slice**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

src = Path("reports/founder-control-era/founder-control-era-table.csv")
dst = Path("reports/dominant-company-architecture/control-table.csv")

control_type_by_signal = {
    ("Microsoft", "1996", "dominance_year"): "founder_operator_influence",
    ("Intel", "1996", "dominance_year"): "founder_operator_influence",
    ("Walmart", "1996", "dominance_year"): "founder_family_control",
    ("Exxon Mobil", "1996", "dominance_year"): "professional_manager_control",
    ("Coca-Cola", "1996", "dominance_year"): "professional_manager_control",
    ("General Electric", "1996", "dominance_year"): "professional_manager_control",
    ("NVIDIA", "2026", "dominance_year"): "founder_operator_influence",
    ("Alphabet", "2026", "dominance_year"): "founder_voting_control",
    ("Meta Platforms", "2026", "dominance_year"): "founder_voting_control",
    ("Apple", "2026", "dominance_year"): "institutional_single_class",
    ("Microsoft", "2026", "dominance_year"): "institutional_single_class",
    ("Broadcom", "2026", "dominance_year"): "predecessor_founder_continuity",
    ("JPMorgan Chase", "2026", "dominance_year"): "professional_manager_control",
    ("NVIDIA", "2026", "ipo_or_first_observable"): "founder_operator_influence",
    ("Google", "2026", "ipo_or_first_observable"): "founder_voting_control",
    ("Meta Platforms", "2026", "ipo_or_first_observable"): "founder_voting_control",
}

with src.open(newline="") as f:
    rows = list(csv.DictReader(f))

fieldnames = dst.read_text().strip().split(",")
with dst.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        key = (r["company"], r["cohort_year"], r["comparison_point"])
        writer.writerow({
            "company": r["company"],
            "ticker": r["ticker"],
            "cik": r["cik"],
            "cohort_name": r["cohort_name"],
            "cohort_year": r["cohort_year"],
            "comparison_point": r["comparison_point"],
            "filing_form": r["filing_form"],
            "filing_date": r["filing_date"],
            "accession": r["accession"],
            "source_path": r["source_path"],
            "control_type": control_type_by_signal[key],
            "founder_or_family_names": r["founder_names"],
            "founder_executive_role": r["founder_executive_role"],
            "founder_board_role": r["founder_board_role"],
            "economic_ownership_pct": r["founder_economic_ownership_pct"],
            "voting_power_pct": r["founder_voting_power_pct"],
            "control_mechanism": r["dual_class_or_control_mechanism"],
            "controlled_company_status": r["controlled_company_status"],
            "control_signal": r["founder_control_signal"],
            "evidence_chunk_ids": r["evidence_chunk_ids"],
            "evidence_excerpt": r["evidence_excerpt"],
            "confidence": r["confidence"],
            "notes": r["notes"],
        })
PY
```

Expected: `control-table.csv` has 17 lines: one header plus 16 seeded rows.

- [ ] **Step 8: Run setup QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

root = Path("reports/dominant-company-architecture")
expected = {
    "cohorts.csv": 60,
    "control-table.csv": 16,
    "governance-table.csv": 0,
    "operating-profile-table.csv": 0,
    "capital-allocation-table.csv": 0,
    "kpi-disclosure-table.csv": 0,
    "architecture-archetypes.csv": 0,
    "evidence-ledger.csv": 0,
}
for name, expected_rows in expected.items():
    with (root / name).open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == expected_rows, (name, len(rows), expected_rows)
print("dominant-company-architecture setup QA passed")
PY
```

Expected:

```text
dominant-company-architecture setup QA passed
```

- [ ] **Step 9: Commit setup**

Run:

```bash
git add reports/dominant-company-architecture
git commit -m "research: seed dominant company architecture bundle"
```

Expected: commit succeeds.

## Task 2: Complete The Control Module

**Files:**
- Modify: `reports/dominant-company-architecture/control-table.csv`
- Modify: `reports/dominant-company-architecture/company-life-arc.csv`
- Modify: `reports/dominant-company-architecture/filing-selection-notes.md`
- Modify: `reports/dominant-company-architecture/evidence-ledger.csv`
- Create: `reports/dominant-company-architecture/search-notes/*.md`

- [ ] **Step 1: Identify missing primary control rows**

Run:

```bash
python3 -B - <<'PY'
import csv

cohorts = []
with open("reports/dominant-company-architecture/cohorts.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["cohort_role"] == "primary":
            cohorts.append((r["company"], r["ticker"], r["cohort_name"], r["cohort_year"]))

existing = set()
with open("reports/dominant-company-architecture/control-table.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["comparison_point"] == "dominance_year":
            existing.add((r["company"], r["ticker"], r["cohort_name"], r["cohort_year"]))

for row in cohorts:
    if row not in existing:
        print(",".join(row))
PY
```

Expected: the command prints the primary cohort rows that still need dominance-year control evidence. Use this printed list as the Task 2 work queue.

- [ ] **Step 2: Resolve identity for each missing row**

For each printed row, run:

```bash
uv run edgarpack identify "<company-or-ticker>"
```

Replace `<company-or-ticker>` with the ticker when `cohorts.csv` has one; otherwise use the company name.

Record the resolved CIK in `cohorts.csv` and `control-table.csv`. If EdgarPack returns multiple plausible identities, add a note to `filing-selection-notes.md` naming the selected CIK and why it maps to the cohort company.

- [ ] **Step 3: Locate the nearest dominance-year control filing**

For 1996 cohort rows, run:

```bash
uv run edgarpack list <ticker> --form "DEF 14A" --limit 60
uv run edgarpack list <ticker> --form "10-K" --limit 60
```

For 2026 cohort rows, run:

```bash
uv run edgarpack list <ticker> --form "DEF 14A" --limit 20
uv run edgarpack list <ticker> --form "10-K" --limit 20
```

Choose the proxy nearest the cohort year. If no proxy is usable, choose the 10-K with Part III ownership disclosure or proxy incorporation note. Record the accession, filing form, and filing date in `filing-selection-notes.md`.

- [ ] **Step 4: Build or inspect the filing**

For a selected filing in the packable range, run:

```bash
uv run edgarpack build <ticker> --form "<form>" --after <start-date> --before <end-date> --with-chunks
```

Use:

```text
1996 row date window: 1995-01-01 to 1997-12-31
2026 row date window: 2025-01-01 to 2026-12-31
```

If the built pack contains a directory listing instead of filing text, use the raw SEC `.txt` URL from the accession and record `raw_sec_txt` in `evidence-ledger.csv`.

- [ ] **Step 5: Locate control evidence**

Use search as a locator:

```bash
uv run edgarpack search '"beneficial ownership" "voting power"' --ticker <ticker>
uv run edgarpack search '"principal stockholders"' --ticker <ticker>
uv run edgarpack search '"Class B" "voting power"' --ticker <ticker>
uv run edgarpack search '"controlled company"' --ticker <ticker>
uv run edgarpack search '"security ownership"' --ticker <ticker>
```

Open the relevant `filing.full.md` or `optional/chunks.ndjson` section and read the surrounding text. Do not populate a row from search snippets alone.

- [ ] **Step 6: Add one control-table row per missing dominance-year row**

Append each completed row to `reports/dominant-company-architecture/control-table.csv`.

Use these controlled values for `control_type`:

```text
founder_voting_control
founder_operator_influence
founder_family_control
predecessor_founder_continuity
professional_manager_control
institutional_single_class
state_or_other_control
unresolved
```

Use these controlled values for `control_signal`:

```text
strong
visible
limited
none_found
unresolved
```

For `none_found`, the row must cite the ownership or security-ownership section that was reviewed.

- [ ] **Step 7: Add evidence-ledger rows for control claims**

For every control-table row added in this task, append one row to `evidence-ledger.csv` with:

```text
table_name=control-table.csv
claim_type=control
evidence_type=chunk_id or raw_sec_txt
evidence_locator=<chunk IDs joined by semicolon, or raw line anchors>
claim_text=<same substance as evidence_excerpt>
```

- [ ] **Step 8: Run control QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from collections import Counter

with open("reports/dominant-company-architecture/cohorts.csv", newline="") as f:
    primary = [r for r in csv.DictReader(f) if r["cohort_role"] == "primary"]
with open("reports/dominant-company-architecture/control-table.csv", newline="") as f:
    control = list(csv.DictReader(f))

dominance = [r for r in control if r["comparison_point"] == "dominance_year"]
keys = {(r["company"], r["ticker"], r["cohort_name"], r["cohort_year"]) for r in dominance}
missing = [
    (r["company"], r["ticker"], r["cohort_name"], r["cohort_year"])
    for r in primary
    if (r["company"], r["ticker"], r["cohort_name"], r["cohort_year"]) not in keys
]
assert not missing, missing
allowed_types = {
    "founder_voting_control",
    "founder_operator_influence",
    "founder_family_control",
    "predecessor_founder_continuity",
    "professional_manager_control",
    "institutional_single_class",
    "state_or_other_control",
    "unresolved",
}
allowed_signals = {"strong", "visible", "limited", "none_found", "unresolved"}
for r in control:
    assert r["control_type"] in allowed_types, r
    assert r["control_signal"] in allowed_signals, r
    assert r["accession"], r
    assert r["evidence_chunk_ids"], r
    assert r["evidence_excerpt"], r
print("control rows", len(control))
print("dominance rows", len(dominance))
print("control types", dict(Counter(r["control_type"] for r in dominance)))
print("control QA passed")
PY
```

Expected: `dominance rows 40` and `control QA passed`.

- [ ] **Step 9: Commit control module**

Run:

```bash
git add reports/dominant-company-architecture
git commit -m "research: complete dominant company control module"
```

Expected: commit succeeds.

## Task 3: Build The Governance Table

**Files:**
- Modify: `reports/dominant-company-architecture/governance-table.csv`
- Modify: `reports/dominant-company-architecture/evidence-ledger.csv`
- Modify: `reports/dominant-company-architecture/filing-selection-notes.md`

- [ ] **Step 1: Use control filings as the initial governance filing set**

Run:

```bash
python3 -B - <<'PY'
import csv

with open("reports/dominant-company-architecture/control-table.csv", newline="") as f:
    rows = [r for r in csv.DictReader(f) if r["comparison_point"] == "dominance_year"]
for r in rows:
    print(f'{r["ticker"]},{r["cohort_year"]},{r["filing_form"]},{r["filing_date"]},{r["accession"]},{r["source_path"]}')
PY
```

Expected: 40 filing candidates print.

- [ ] **Step 2: Locate governance sections**

For each candidate filing, search the built pack or raw text for:

```text
class a common stock
class b common stock
vote per share
director independence
classified board
staggered board
proxy access
shareholder nominations
takeover
poison pill
audit committee
independent registered public accounting firm
```

Use `rg` against pack files first:

```bash
rg -n "Class A|Class B|vote per share|director independence|classified board|staggered|proxy access|shareholder nominations|takeover|poison pill|audit committee|independent registered public accounting firm" <source_path> -S
```

For raw SEC text rows, use the downloaded `.txt` file or SEC URL line anchors and record `raw_sec_txt` in the ledger.

- [ ] **Step 3: Append one governance-table row per primary dominance row**

Append exactly one row for each primary dominance-year company. Use these values when the filing does not disclose a field:

```text
not_disclosed
```

Use these values when a field is explicitly disclosed as absent:

```text
absent
```

Use `share_classes` examples like:

```text
single_class_common
dual_class_common
multi_class_common_with_nonvoting_class
not_disclosed
```

- [ ] **Step 4: Add evidence-ledger rows for governance claims**

For each governance row, append one evidence-ledger row with:

```text
table_name=governance-table.csv
claim_type=governance
evidence_type=chunk_id or raw_sec_txt
evidence_locator=<chunk IDs joined by semicolon, or raw line anchors>
claim_text=<summary of the governance row>
```

- [ ] **Step 5: Run governance QA**

Run:

```bash
python3 -B - <<'PY'
import csv

with open("reports/dominant-company-architecture/governance-table.csv", newline="") as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 40, len(rows)
for r in rows:
    for field in ["company", "ticker", "cohort_name", "cohort_year", "filing_form", "filing_date", "accession", "share_classes", "evidence_chunk_ids", "evidence_excerpt", "confidence"]:
        assert r[field], (field, r)
    for field in ["director_election_structure", "board_independence_signal", "committee_independence_signal", "classified_board_or_staggered_terms", "proxy_access_or_shareholder_nomination_rights", "takeover_defense_signal", "auditor"]:
        assert r[field] != "", (field, r)
print("governance QA passed")
PY
```

Expected:

```text
governance QA passed
```

- [ ] **Step 6: Commit governance module**

Run:

```bash
git add reports/dominant-company-architecture
git commit -m "research: add dominant company governance table"
```

Expected: commit succeeds.

## Task 4: Build Operating Profile And Capital Allocation Tables

**Files:**
- Modify: `reports/dominant-company-architecture/operating-profile-table.csv`
- Modify: `reports/dominant-company-architecture/capital-allocation-table.csv`
- Modify: `reports/dominant-company-architecture/evidence-ledger.csv`
- Modify: `reports/dominant-company-architecture/filing-selection-notes.md`

- [ ] **Step 1: Select annual filings for each primary row**

For every primary cohort row, list annual filings:

```bash
uv run edgarpack list <ticker> --form "10-K" --limit 80
uv run edgarpack list <ticker> --form "20-F" --limit 40
```

Choose the annual filing nearest the cohort year. For 1996 rows, prefer fiscal year 1995 or 1996. For 2026 rows, prefer the latest annual filing available in 2025 or 2026. Record selection notes in `filing-selection-notes.md`.

- [ ] **Step 2: Build selected annual filings with chunks**

Run for each selected annual filing:

```bash
uv run edgarpack build <ticker> --form "<form>" --after <start-date> --before <end-date> --with-chunks
```

Use:

```text
1996 row date window: 1995-01-01 to 1997-12-31
2026 row date window: 2025-01-01 to 2026-12-31
```

- [ ] **Step 3: Extract operating profile fields**

For each annual filing, locate:

```text
consolidated statements of operations
consolidated statements of income
revenues
operating income
net income
research and development
capital expenditures
property and equipment
employees
segments
geographic
```

Use `rg` against the pack:

```bash
rg -n "Consolidated Statements|revenues|operating income|net income|research and development|capital expenditures|property and equipment|employees|segments|geographic" <source_path> -S
```

Append one `operating-profile-table.csv` row per primary company. If a value is not disclosed in the selected filing, write `not_disclosed`. If a field is not meaningful for the company type, write `not_meaningful` and explain in `notes`.

- [ ] **Step 4: Record derived metrics**

When computing margins or intensities, use:

```text
operating_margin = operating_income / revenue
r_and_d_intensity = r_and_d_expense / revenue
capex_intensity = capex / revenue
```

Record the calculation in `notes` as:

```text
derived from same-period filing values: numerator / revenue
```

Do not compute a metric when either numerator or denominator is missing.

- [ ] **Step 5: Extract capital allocation fields**

For the same annual filing, locate:

```text
dividends
share repurchases
stock repurchases
cash and cash equivalents
marketable securities
total debt
long-term debt
acquisitions
business combinations
```

Use:

```bash
rg -n "dividends|share repurchases|stock repurchases|cash and cash equivalents|marketable securities|total debt|long-term debt|acquisitions|business combinations" <source_path> -S
```

Append one `capital-allocation-table.csv` row per primary company. Use `not_disclosed` and `not_meaningful` with notes under the same rules as Step 3.

- [ ] **Step 6: Add evidence-ledger rows**

For each operating and capital-allocation row, append ledger rows:

```text
table_name=operating-profile-table.csv
claim_type=operating_profile
```

and:

```text
table_name=capital-allocation-table.csv
claim_type=capital_allocation
```

Use `chunk_id` when the source is a pack chunk. Use `raw_sec_txt` for old filing line anchors.

- [ ] **Step 7: Run operating and capital QA**

Run:

```bash
python3 -B - <<'PY'
import csv

for path in [
    "reports/dominant-company-architecture/operating-profile-table.csv",
    "reports/dominant-company-architecture/capital-allocation-table.csv",
]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 40, (path, len(rows))
    for r in rows:
        for field in ["company", "ticker", "cohort_name", "cohort_year", "filing_form", "filing_date", "accession", "evidence_chunk_ids", "evidence_excerpt", "confidence"]:
            assert r[field], (path, field, r)
print("operating and capital QA passed")
PY
```

Expected:

```text
operating and capital QA passed
```

- [ ] **Step 8: Commit operating and capital modules**

Run:

```bash
git add reports/dominant-company-architecture
git commit -m "research: add operating and capital allocation tables"
```

Expected: commit succeeds.

## Task 5: Build KPI Disclosure Table

**Files:**
- Modify: `reports/dominant-company-architecture/kpi-disclosure-table.csv`
- Modify: `reports/dominant-company-architecture/evidence-ledger.csv`
- Modify: `reports/dominant-company-architecture/search-notes/*.md`

- [ ] **Step 1: Run KPI discovery for each primary ticker**

For each primary ticker, run:

```bash
uv run edgarpack which <ticker> --query "operating metrics key performance indicators users customers units stores production capacity segment metrics"
```

If `which` is not available for the selected pack, use:

```bash
uv run edgarpack search '"key performance indicators" OR "users" OR "customers" OR "stores" OR "units" OR "production" OR "capacity" OR "segment"' --ticker <ticker>
```

Record useful locator output in `reports/dominant-company-architecture/search-notes/<ticker>-kpis.md`.

- [ ] **Step 2: Validate KPI candidates in the filing**

Open the relevant annual filing section. A KPI qualifies only if the filing presents it as a recurring business or segment metric, not as a one-off sentence.

Use these `kpi_category` values:

```text
user_or_customer_scale
unit_volume
store_or_location_count
production_or_capacity
advertising_or_platform_metric
financial_services_metric
segment_metric
none_disclosed
unresolved
```

- [ ] **Step 3: Add KPI rows**

Append one row per validated KPI. If no recurring KPI is disclosed after section review, add one row with:

```text
kpi_name=none_disclosed
kpi_value=not_disclosed
kpi_unit=not_disclosed
kpi_section=<section reviewed>
kpi_category=none_disclosed
```

Every primary company must have at least one KPI row.

- [ ] **Step 4: Add evidence-ledger rows**

For each KPI row, append a ledger row with:

```text
table_name=kpi-disclosure-table.csv
claim_type=kpi_disclosure
evidence_type=chunk_id or raw_sec_txt
evidence_locator=<chunk IDs joined by semicolon, or raw line anchors>
claim_text=<KPI name and value, or none_disclosed after reviewed section>
```

- [ ] **Step 5: Run KPI QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from collections import defaultdict

allowed = {
    "user_or_customer_scale",
    "unit_volume",
    "store_or_location_count",
    "production_or_capacity",
    "advertising_or_platform_metric",
    "financial_services_metric",
    "segment_metric",
    "none_disclosed",
    "unresolved",
}
with open("reports/dominant-company-architecture/cohorts.csv", newline="") as f:
    primary = [(r["ticker"], r["cohort_name"], r["cohort_year"]) for r in csv.DictReader(f) if r["cohort_role"] == "primary"]
with open("reports/dominant-company-architecture/kpi-disclosure-table.csv", newline="") as f:
    rows = list(csv.DictReader(f))
seen = defaultdict(int)
for r in rows:
    assert r["kpi_category"] in allowed, r
    assert r["evidence_chunk_ids"], r
    assert r["evidence_excerpt"], r
    seen[(r["ticker"], r["cohort_name"], r["cohort_year"])] += 1
missing = [k for k in primary if seen[k] == 0]
assert not missing, missing
print("kpi rows", len(rows))
print("KPI QA passed")
PY
```

Expected:

```text
KPI QA passed
```

- [ ] **Step 6: Commit KPI module**

Run:

```bash
git add reports/dominant-company-architecture
git commit -m "research: add dominant company KPI disclosure table"
```

Expected: commit succeeds.

## Task 6: Assign Architecture Archetypes

**Files:**
- Modify: `reports/dominant-company-architecture/architecture-archetypes.csv`
- Modify: `reports/dominant-company-architecture/evidence-ledger.csv`

- [ ] **Step 1: Generate an evidence summary for each primary company**

Run:

```bash
python3 -B - <<'PY'
import csv
from collections import defaultdict

bundle = "reports/dominant-company-architecture"
tables = {
    "control": "control-table.csv",
    "governance": "governance-table.csv",
    "operating": "operating-profile-table.csv",
    "capital": "capital-allocation-table.csv",
    "kpi": "kpi-disclosure-table.csv",
}
rows = defaultdict(dict)
for label, filename in tables.items():
    with open(f"{bundle}/{filename}", newline="") as f:
        for r in csv.DictReader(f):
            key = (r["company"], r["ticker"], r["cohort_name"], r["cohort_year"])
            rows[key].setdefault(label, []).append(r)

for key in sorted(rows):
    company, ticker, cohort_name, cohort_year = key
    print(f"\n## {company} ({ticker}) {cohort_name} {cohort_year}")
    for label in ["control", "governance", "operating", "capital", "kpi"]:
        for r in rows[key].get(label, []):
            excerpt = r.get("evidence_excerpt", "")
            print(f"- {label}: {excerpt[:240]}")
PY
```

Expected: the command prints grouped evidence summaries for all primary company rows.

- [ ] **Step 2: Assign archetypes after reading the evidence summaries**

Append one row per primary company to `architecture-archetypes.csv`.

Use these archetypes:

```text
founder_controlled_platform
founder_led_not_founder_controlled
founder_origin_institutional_tech
founder_or_family_controlled_non_tech
manager_controlled_old_line_incumbent
predecessor_founder_continuity
professional_manager_financial_or_services
unresolved
```

Use `evidence_row_refs` in this format:

```text
control:<ticker>:<cohort_year>; governance:<ticker>:<cohort_year>; operating:<ticker>:<cohort_year>; capital:<ticker>:<cohort_year>; kpi:<ticker>:<cohort_year>
```

- [ ] **Step 3: Run archetype QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from collections import Counter

allowed = {
    "founder_controlled_platform",
    "founder_led_not_founder_controlled",
    "founder_origin_institutional_tech",
    "founder_or_family_controlled_non_tech",
    "manager_controlled_old_line_incumbent",
    "predecessor_founder_continuity",
    "professional_manager_financial_or_services",
    "unresolved",
}
with open("reports/dominant-company-architecture/architecture-archetypes.csv", newline="") as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 40, len(rows)
for r in rows:
    assert r["assigned_archetype"] in allowed, r
    for field in ["control_rationale", "governance_rationale", "operating_rationale", "capital_allocation_rationale", "kpi_rationale", "evidence_row_refs", "confidence"]:
        assert r[field], (field, r)
print("archetypes", dict(Counter(r["assigned_archetype"] for r in rows)))
print("archetype QA passed")
PY
```

Expected:

```text
archetype QA passed
```

- [ ] **Step 4: Commit archetype layer**

Run:

```bash
git add reports/dominant-company-architecture
git commit -m "research: classify dominant company archetypes"
```

Expected: commit succeeds.

## Task 7: Write The Narrative Report

**Files:**
- Create: `reports/dominant-company-architecture/dominant-company-architecture-report.md`
- Modify: `reports/dominant-company-architecture/evidence-ledger.csv`

- [ ] **Step 1: Create the report skeleton**

Create `reports/dominant-company-architecture/dominant-company-architecture-report.md` with:

```markdown
# Dominant Company Architecture: Then vs Now

Date: 2026-04-28

## Opening Thesis

## What Changed In Who Controls Dominance

## What Changed In The Governance Bargain

## What Changed In The Operating Machine

## What Changed In Capital Allocation

## What Changed In What Investors Are Asked To Track

## Company Archetypes

## Cases That Break The Simple Story

## Limits And Next Work
```

- [ ] **Step 2: Write from tables, not memory**

Before drafting each section, run the relevant table view:

```bash
python3 -B - <<'PY'
import csv

for path in [
    "reports/dominant-company-architecture/control-table.csv",
    "reports/dominant-company-architecture/governance-table.csv",
    "reports/dominant-company-architecture/operating-profile-table.csv",
    "reports/dominant-company-architecture/capital-allocation-table.csv",
    "reports/dominant-company-architecture/kpi-disclosure-table.csv",
    "reports/dominant-company-architecture/architecture-archetypes.csv",
]:
    print(f"\n# {path}")
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows[:8]:
        print({k: r[k] for k in list(r)[:6]})
PY
```

Use the full CSVs for actual drafting. The command above is only a sanity view.

- [ ] **Step 3: Draft the opening thesis**

Write a thesis that is supported by the completed tables. If the evidence supports the spec hypothesis, use this as the starting point and edit it to fit the data:

```markdown
The shift from 1996 to 2026 is not just a shift from old economy to technology. It is a shift from mature, manager-controlled institutions toward a mixed regime: institutionally governed mega-cap technology on one side, and founder-controlled or founder-led platforms on the other. The public investor bargain changed from owning dispersed claims on mature corporate machines to owning claims on companies where control, reinvestment, and disclosed KPIs vary much more sharply by business model.
```

If the completed tables contradict this thesis, write the contradiction directly and cite the rows that changed the conclusion.

- [ ] **Step 4: Draft the evidence sections**

Each major section must include:

```text
one paragraph of argument
one compact table or bullet list naming the companies that support it
one paragraph naming exceptions or weak evidence
```

Use inline row references like:

```text
(control-table: META 2026; governance-table: META 2026)
```

Do not cite raw chunk IDs in the prose unless the claim is unusually important. Keep chunk IDs in the CSVs and evidence ledger.

- [ ] **Step 5: Draft cases that break the simple story**

Include at least these case types if the evidence still supports them:

```text
Microsoft appears in both eras and shows a same-company transition.
Nvidia is founder-led but not founder-controlled.
Walmart is founder-family control outside technology.
Broadcom is predecessor-founder continuity rather than clean founder control.
Old-line companies with no founder signal may be old rather than anti-founder.
```

- [ ] **Step 6: Draft limits and next work**

Include these limits when supported by the evidence ledger:

```text
pre-2000 raw SEC text routing for affected filings
left-censored life arcs for older companies
modern governance disclosure not always comparable to 1996 proxy language
operating metrics differ by business model
global ADR and 20-F extension not included in this version
```

- [ ] **Step 7: Add report claims to the evidence ledger**

For each major interpretive claim in the report, append one ledger row with:

```text
table_name=dominant-company-architecture-report.md
claim_type=narrative_interpretation
evidence_type=table_rows
evidence_locator=<table refs used in prose>
claim_text=<claim sentence or compact paraphrase>
```

- [ ] **Step 8: Run report writing-quality scan**

Run:

```bash
python3 -B - <<'PY'
from pathlib import Path

terms = [
    chr(8212),
    "Fur" + "thermore",
    "Add" + "itionally",
    "More" + "over",
    "del" + "ve",
    "land" + "scape",
    "rob" + "ust",
    "sea" + "mless",
    "un" + "lock",
    "fos" + "ter",
    "lev" + "erage",
    "best" + "-in-class",
    "world" + "-class",
    "cutting" + "-edge",
    "It is important to " + "note",
    "In con" + "clusion",
    "In sum" + "mary",
]
path = Path("reports/dominant-company-architecture/dominant-company-architecture-report.md")
text = path.read_text()
matches = [(term, line_no) for term in terms for line_no, line in enumerate(text.splitlines(), 1) if term in line]
assert not matches, matches
print("report writing-quality scan passed")
PY
```

Expected:

```text
report writing-quality scan passed
```

Rewrite any matching line.

- [ ] **Step 9: Run report evidence QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

report = Path("reports/dominant-company-architecture/dominant-company-architecture-report.md").read_text()
required_sections = [
    "## Opening Thesis",
    "## What Changed In Who Controls Dominance",
    "## What Changed In The Governance Bargain",
    "## What Changed In The Operating Machine",
    "## What Changed In Capital Allocation",
    "## What Changed In What Investors Are Asked To Track",
    "## Company Archetypes",
    "## Cases That Break The Simple Story",
    "## Limits And Next Work",
]
for section in required_sections:
    assert section in report, section
with open("reports/dominant-company-architecture/evidence-ledger.csv", newline="") as f:
    ledger = list(csv.DictReader(f))
assert any(r["table_name"] == "dominant-company-architecture-report.md" for r in ledger), "missing narrative ledger rows"
print("report evidence QA passed")
PY
```

Expected:

```text
report evidence QA passed
```

- [ ] **Step 10: Commit report**

Run:

```bash
git add reports/dominant-company-architecture
git commit -m "research: write dominant company architecture report"
```

Expected: commit succeeds.

## Task 8: Final Artifact QA, Beads, And Push

**Files:**
- Modify: `reports/dominant-company-architecture/*` only if QA exposes issues
- Modify: `.beads/issues.jsonl` only if filing follow-up issues

- [ ] **Step 1: Run full bundle QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

root = Path("reports/dominant-company-architecture")
expected_counts = {
    "cohorts.csv": 60,
    "control-table.csv": 43,
    "governance-table.csv": 40,
    "operating-profile-table.csv": 40,
    "capital-allocation-table.csv": 40,
    "architecture-archetypes.csv": 40,
}
for name, expected in expected_counts.items():
    with (root / name).open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == expected, (name, len(rows), expected)
with (root / "kpi-disclosure-table.csv").open(newline="") as f:
    kpi_rows = list(csv.DictReader(f))
assert len(kpi_rows) >= 40, len(kpi_rows)
with (root / "evidence-ledger.csv").open(newline="") as f:
    ledger_rows = list(csv.DictReader(f))
assert len(ledger_rows) >= 216, len(ledger_rows)
print("full bundle QA passed")
PY
```

Expected:

```text
full bundle QA passed
```

The expected `control-table.csv` count is 43 because it includes 40 primary dominance-year rows plus the 3 seeded IPO or first-observable rows for Nvidia, Google, and Meta.

- [ ] **Step 2: Check CSV parse and evidence fields**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path

root = Path("reports/dominant-company-architecture")
for path in root.glob("*.csv"):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
        assert f.closed is False
    if path.name not in {"cohorts.csv", "company-life-arc.csv"}:
        for r in rows:
            if "evidence_chunk_ids" in r:
                assert r["evidence_chunk_ids"], (path.name, r)
            if "evidence_excerpt" in r:
                assert r["evidence_excerpt"], (path.name, r)
print("CSV parse and evidence fields QA passed")
PY
```

Expected:

```text
CSV parse and evidence fields QA passed
```

- [ ] **Step 3: Run markdown and whitespace checks**

Run:

```bash
git diff --check
python3 -B - <<'PY'
from pathlib import Path

terms = ["T" + "BD", "TO" + "DO", "X" * 3, "place" + "holder", "fix " + "later"]
paths = [
    Path("reports/dominant-company-architecture"),
    Path("docs/superpowers/plans/2026-04-28-dominant-company-architecture.md"),
]
matches = []
for path in paths:
    files = path.rglob("*") if path.is_dir() else [path]
    for file_path in files:
        if file_path.is_file():
            text = file_path.read_text(errors="ignore")
            for line_no, line in enumerate(text.splitlines(), 1):
                for term in terms:
                    if term in line:
                        matches.append((str(file_path), line_no, term))
assert not matches, matches
print("markdown scan passed")
PY
```

Expected: `git diff --check` exits 0 and the Python command prints:

```text
markdown scan passed
```

- [ ] **Step 4: File follow-up beads for unfinished work**

If the final report ships with known unresolved work beyond the existing `edgarpack-eob` old-filing ingestion issue, file one bead per concrete follow-up:

```bash
bd create "<short title>" --type task --priority P3 --labels research,dominant-company-architecture --description "<specific evidence-backed gap>" --acceptance "<observable completion condition>"
bd sync
```

Do not file broad follow-ups like "improve report." File only concrete gaps such as a missing predecessor mapping, a source-form limitation, or an extraction bug.

- [ ] **Step 5: Commit final fixes or bead updates**

If Step 4 changed `.beads/issues.jsonl` or QA fixes changed report files, run:

```bash
git add reports/dominant-company-architecture .beads/issues.jsonl
git commit -m "research: finalize dominant company architecture artifacts"
```

Expected: commit succeeds when there are changes. If there are no changes, `git status --short` should show only unrelated pre-existing untracked files.

- [ ] **Step 6: Required repo closeout**

Run:

```bash
git pull --rebase
bd sync
git push
git status --short --branch
```

Expected:

```text
## main...origin/main
```

Unrelated untracked files may remain. Do not stage or delete them unless the user explicitly says they belong to this work.
