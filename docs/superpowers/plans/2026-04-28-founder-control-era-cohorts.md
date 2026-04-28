# Founder Control Era Cohorts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a citation-backed research bundle comparing founder control across earlier-era and current dominant public-company cohorts.

**Architecture:** This is a research workflow, not an EdgarPack product change. It uses a cited cohort source to freeze S&P 500 top-20 cohorts, uses EdgarPack to resolve issuers and build primary SEC filing packs, then writes auditable CSV and Markdown outputs under `reports/founder-control-era/`. The evidence table is the source of truth; the report is derived from it.

**Tech Stack:** EdgarPack CLI via `uv run`, SEC EDGAR filings, local pack artifacts under `packs/`, Markdown, CSV, shell commands, and focused manual evidence review. Required environment: `EDGARPACK_USER_AGENT`.

---

## Scope Check

The spec covers one research bundle. It intentionally separates the first founder-control report from a later governance, operating-profile, and KPI extension. The plan does not add a command, dashboard, database migration, extractor subsystem, or dependency.

## File Structure

- Create: `reports/founder-control-era/README.md`
  - Bundle index, research question, source policy, and verification log.
- Create: `reports/founder-control-era/cohorts.csv`
  - Frozen cohort rows for 1996 primary, 2026 primary, and 1989 context.
- Create: `reports/founder-control-era/company-life-arc.csv`
  - IPO or first-observable public-filing basis per company.
- Create: `reports/founder-control-era/filing-selection-notes.md`
  - Notes for filing choices, missing exact-year filings, predecessor mappings, and left-censored life arcs.
- Create: `reports/founder-control-era/founder-control-era-table.csv`
  - Authoritative evidence table for founder-control claims.
- Create: `reports/founder-control-era/founder-control-era-report.md`
  - Narrative synthesis derived from the evidence table.
- Create: `reports/founder-control-era/extension-notes.md`
  - Explicitly scoped future governance, operating-profile, and KPI expansion notes.
- Create: `reports/founder-control-era/search-notes/`
  - Optional compact notes for companies where ownership sections are hard to locate.
- Modify: none in application code.
- Test: no code tests unless application code changes. Use artifact QA in Tasks 1, 3, 5, 6, and 7.

## External Sources

- Historical and current S&P 500 top-20 cohort source: `https://www.finhacker.cz/en/top-20-sp-500-companies-by-market-cap/`
- Current tech context source: `https://companiesmarketcap.com/tech/largest-tech-companies-by-market-cap/`
- EDGAR availability source: `https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data`

## Data Flow

```text
Cohort sources
  -> cohorts.csv
  -> EdgarPack identity + filing discovery
  -> selected SEC packs with chunks
  -> targeted ownership/governance review
  -> company-life-arc.csv
  -> founder-control-era-table.csv
  -> founder-control-era-report.md
  -> extension-notes.md
```

## Task 1: Bundle Setup And Cohort Freeze

**Files:**
- Create: `reports/founder-control-era/README.md`
- Create: `reports/founder-control-era/cohorts.csv`
- Create: `reports/founder-control-era/company-life-arc.csv`
- Create: `reports/founder-control-era/filing-selection-notes.md`
- Create: `reports/founder-control-era/founder-control-era-table.csv`
- Create: `reports/founder-control-era/extension-notes.md`

- [ ] **Step 1: Confirm repo and SEC user agent**

Run:

```bash
git rev-parse --show-toplevel
printenv EDGARPACK_USER_AGENT
```

Expected:

```text
/Users/samaydhawan/Projects/active/edgarpack
```

`EDGARPACK_USER_AGENT` should print a contact string. If it is empty, run:

```bash
export EDGARPACK_USER_AGENT="Samay Dhawan samay58@gmail.com"
```

- [ ] **Step 2: Create the bundle directory**

Run:

```bash
mkdir -p reports/founder-control-era/search-notes
```

Expected: command exits 0 and `reports/founder-control-era/search-notes/` exists.

- [ ] **Step 3: Write the README**

Create `reports/founder-control-era/README.md` with:

```markdown
# Founder Control Era Cohorts Research Bundle

Date started: 2026-04-28

## Question

How did founder control differ between dominant public companies of the earlier market era and dominant public companies today, both at the time of market dominance and across comparable public-company life-arc points?

## Scope

This bundle supersedes the narrower current-top-ten-technology-company framing. The primary sample is S&P 500 top-20 companies in 1996 and 2026. A 1989 S&P 500 top-20 roster is included as context for the 30-40 year historical backdrop.

## Source Policy

Founder-control claims must come from primary SEC filings built or inspected through EdgarPack. Cohort membership can come from cited market-cap sources. Secondary sources may be used for IPO-date or predecessor context only when the notes label them as context.

## Cohort Sources

- Historical and current S&P 500 top-20 source: https://www.finhacker.cz/en/top-20-sp-500-companies-by-market-cap/
- Current tech context source: https://companiesmarketcap.com/tech/largest-tech-companies-by-market-cap/
- EDGAR availability source: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- Retrieved at: 2026-04-28

## Artifact Index

- `cohorts.csv`: frozen cohort rows and identity fields
- `company-life-arc.csv`: IPO or first-observable public-filing basis per company
- `filing-selection-notes.md`: filing choice notes and limitations
- `founder-control-era-table.csv`: authoritative evidence table
- `founder-control-era-report.md`: narrative synthesis derived from the evidence table
- `extension-notes.md`: future governance, operating-profile, and KPI expansion notes
- `search-notes/`: focused source-location notes when needed

## Evidence Rule

Every factual founder-control claim in the narrative report must map to a row in `founder-control-era-table.csv` with accession and section or chunk evidence.
```

- [ ] **Step 4: Write the frozen cohort file**

Create `reports/founder-control-era/cohorts.csv` with this header:

```csv
cohort_name,cohort_year,cohort_role,rank,company,ticker,market_cap,sector_or_industry,cohort_source_url,cohort_retrieved_at,edgarpack_input,cik,edgarpack_source,identity_notes
```

Add rows from the source exactly as listed below. Leave `cik`, `edgarpack_source`, and `identity_notes` empty for now.

Earlier-era primary cohort, 1996:

```text
Coca-Cola, Exxon Mobil, Intel, Microsoft, General Electric, Merck, IBM, Procter & Gamble, Johnson & Johnson, Walmart, Bristol-Myers Squibb, Pfizer, Walt Disney, PepsiCo, Chevron, AIG, Cisco Systems, Eli Lilly, Fannie Mae, JPMorgan Chase
```

Current-era primary cohort, 2026:

```text
NVIDIA, Alphabet, Apple, Microsoft, Amazon, Broadcom, Meta Platforms, Tesla, Berkshire Hathaway, Walmart, JPMorgan Chase, Eli Lilly, Exxon Mobil, Visa, Micron Technology, Advanced Micro Devices, Johnson & Johnson, Oracle, Mastercard, Costco Wholesale
```

Thirty-to-forty-year context cohort, 1989:

```text
Exxon Mobil, IBM, General Electric, Bristol-Myers Squibb, Merck, Coca-Cola, Walmart, Procter & Gamble, Verizon Communications, Johnson & Johnson, Eli Lilly, PepsiCo, Walt Disney, AT&T, 3M, AIG, Boeing, McDonald's, Pfizer, Schlumberger
```

Use these `cohort_role` values:

```text
primary
primary
context
```

Expected: `cohorts.csv` has 61 lines: one header plus 60 cohort rows.

- [ ] **Step 5: Initialize the life-arc file**

Create `reports/founder-control-era/company-life-arc.csv` with:

```csv
company,ticker,cik,ipo_or_public_basis,basis_source,basis_source_url,first_observable_public_year,public_plus_10_year,public_plus_20_year,left_censored,notes
```

Expected: the file has exactly one header row at this step.

- [ ] **Step 6: Initialize the filing notes**

Create `reports/founder-control-era/filing-selection-notes.md` with:

```markdown
# Filing Selection Notes

Use this file for judgment calls: missing exact-year filings, predecessor mappings, S-1 or 10-K fallback, left-censored public-company life arcs, and companies where "founder" is not a meaningful filing concept.

## Notes
```

- [ ] **Step 7: Initialize the evidence table**

Create `reports/founder-control-era/founder-control-era-table.csv` with:

```csv
company,ticker,cik,sector_or_industry,cohort_name,cohort_year,cohort_rank,cohort_market_cap,comparison_point,life_arc_basis,life_arc_year,filing_form,filing_date,accession,source_path,founder_names,founder_executive_role,founder_board_role,founder_economic_ownership_pct,founder_voting_power_pct,dual_class_or_control_mechanism,controlled_company_status,founder_control_signal,evidence_section_id,evidence_chunk_ids,evidence_excerpt,confidence,notes
```

Expected: the file has exactly one header row at this step.

- [ ] **Step 8: Initialize extension notes**

Create `reports/founder-control-era/extension-notes.md` with:

```markdown
# Extension Notes

The founder-control report should earn the broader comparison before this expands. Preserve reusable observations here without turning them into report claims unless they are backed by primary filing evidence.

## Potential Governance Expansion

- Board independence and committee structure
- Classified board or staggered director terms
- Dual-class or unequal voting provisions
- Insider ownership and controlled-company disclosures
- Takeover defenses where filings disclose them

## Potential Operating-Profile Expansion

- Revenue scale and growth
- Operating margin and gross margin where meaningful
- R&D intensity and capex intensity
- Employee count
- Segment and geographic mix
- Buybacks, dividends, cash, debt, and acquisition activity

## Potential KPI Expansion

- Company-specific KPIs discoverable from 10-Ks and annual reports
- Recurring operating metrics suitable for EdgarPack `which`
- KPI changes across public-company life arc
```

- [ ] **Step 9: Run artifact QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path
base = Path("reports/founder-control-era")
required = [
    "README.md",
    "cohorts.csv",
    "company-life-arc.csv",
    "filing-selection-notes.md",
    "founder-control-era-table.csv",
    "extension-notes.md",
]
missing = [p for p in required if not (base / p).exists()]
if missing:
    raise SystemExit(f"missing files: {missing}")
with (base / "cohorts.csv").open(newline="") as f:
    rows = list(csv.DictReader(f))
if len(rows) != 60:
    raise SystemExit(f"expected 60 cohort rows, found {len(rows)}")
roles = {}
for row in rows:
    roles[row["cohort_role"]] = roles.get(row["cohort_role"], 0) + 1
if roles != {"primary": 40, "context": 20}:
    raise SystemExit(f"unexpected role counts: {roles}")
print("artifact QA passed: cohort_rows=60 primary=40 context=20")
PY
```

Expected:

```text
artifact QA passed: cohort_rows=60 primary=40 context=20
```

- [ ] **Step 10: Commit setup artifacts**

Run:

```bash
git add reports/founder-control-era
git commit -m "research: freeze founder control era cohorts"
```

Expected: commit succeeds. Unrelated untracked files outside `reports/founder-control-era/` remain untouched.

## Task 2: Identity Resolution And Filing Discovery

**Files:**
- Modify: `reports/founder-control-era/cohorts.csv`
- Modify: `reports/founder-control-era/company-life-arc.csv`
- Modify: `reports/founder-control-era/filing-selection-notes.md`

- [ ] **Step 1: Resolve every unique company**

Run `identify` once per unique company in `cohorts.csv`:

```bash
uv run edgarpack identify "Microsoft"
uv run edgarpack identify "NVIDIA"
uv run edgarpack identify "Alphabet"
uv run edgarpack identify "Coca-Cola"
```

Continue for every remaining unique company. Update `cohorts.csv`:

- `cik`: CIK returned by EdgarPack.
- `edgarpack_source`: `SEC` when the issuer resolves to SEC filings.
- `identity_notes`: predecessor, ticker ambiguity, or no SEC identity.

Expected: every primary-cohort row has `edgarpack_source` populated or an exclusion note.

- [ ] **Step 2: List governance and annual filings for the validation slice**

Run:

```bash
uv run edgarpack list MSFT --form "DEF 14A" --limit 60
uv run edgarpack list WMT --form "DEF 14A" --limit 60
uv run edgarpack list INTC --form "DEF 14A" --limit 60
uv run edgarpack list XOM --form "DEF 14A" --limit 60
uv run edgarpack list KO --form "DEF 14A" --limit 60
uv run edgarpack list GE --form "DEF 14A" --limit 60
uv run edgarpack list NVDA --form "DEF 14A" --limit 60
uv run edgarpack list GOOGL --form "DEF 14A" --limit 60
uv run edgarpack list META --form "DEF 14A" --limit 60
uv run edgarpack list AAPL --form "DEF 14A" --limit 60
uv run edgarpack list AVGO --form "DEF 14A" --limit 60
uv run edgarpack list JPM --form "DEF 14A" --limit 60
```

Expected: filing lists show 1996 or near-1996 proxy coverage for older validation companies and latest proxy coverage for current validation companies.

- [ ] **Step 3: List IPO-stage filings for the validation slice**

Run:

```bash
uv run edgarpack list MSFT --form "S-1" --limit 20
uv run edgarpack list WMT --form "S-1" --limit 20
uv run edgarpack list INTC --form "S-1" --limit 20
uv run edgarpack list NVDA --form "S-1" --limit 20
uv run edgarpack list GOOGL --form "S-1" --limit 20
uv run edgarpack list META --form "S-1" --limit 20
uv run edgarpack list AAPL --form "S-1" --limit 20
uv run edgarpack list AVGO --form "S-1" --limit 20
```

Expected: post-EDGAR IPO companies have S-1 coverage when applicable. Older companies may have no S-1 because their IPO predates EDGAR; record that as left-censored.

- [ ] **Step 4: Fill life-arc basis for validation companies**

Populate `company-life-arc.csv` for the validation slice. Use `S-1` filing year when available. For older pre-EDGAR companies, use the first available EDGAR governance filing year as `first_observable_public_year` and set `left_censored=true`.

Expected: validation companies have `first_observable_public_year`, `public_plus_10_year`, `public_plus_20_year`, `left_censored`, and notes.

- [ ] **Step 5: Record filing discovery notes**

Append notes only for actual judgment calls using this format:

```markdown
### MSFT validation slice

- Forms checked: DEF 14A, 10-K, S-1
- Dominance-year target: 1996
- Life-arc basis: first available EDGAR governance filing when IPO predates EDGAR
- Limitation: left-censored before 1994/1995 if no S-1 is available
```

Expected: the notes explain limitations without repeating obvious exact-year filing selections.

- [ ] **Step 6: Commit identity and discovery work**

Run:

```bash
git add reports/founder-control-era/cohorts.csv reports/founder-control-era/company-life-arc.csv reports/founder-control-era/filing-selection-notes.md
git commit -m "research: resolve era cohort filing candidates"
```

Expected: commit succeeds.

## Task 3: Validation Slice Pack Build And Evidence Extraction

**Files:**
- Modify: `reports/founder-control-era/founder-control-era-table.csv`
- Modify: `reports/founder-control-era/filing-selection-notes.md`
- Create pack artifacts under: `packs/`

- [ ] **Step 1: Build validation dominance-year filings**

Run the selected build commands after confirming filing availability. Use nearest available proxy when exact-year proxy is missing:

```bash
uv run edgarpack build MSFT --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build WMT --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build INTC --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build XOM --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build KO --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build GE --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build NVDA --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build GOOGL --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build META --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build AAPL --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build AVGO --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build JPM --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
```

Expected: each successful build produces a pack directory under `packs/`.

- [ ] **Step 2: Build validation IPO or first-observable filings**

Run S-1 builds for post-EDGAR IPO companies where available:

```bash
uv run edgarpack build NVDA --form "S-1" --with-chunks
uv run edgarpack build GOOGL --form "S-1" --with-chunks
uv run edgarpack build META --form "S-1" --with-chunks
uv run edgarpack build AVGO --form "S-1" --with-chunks
```

For older companies without S-1 coverage, use the first available proxy or 10-K found in Task 2 and record the left-censored basis in `filing-selection-notes.md`.

Expected: each validation company has at least one dominance-year or first-observable source filing.

- [ ] **Step 3: Index the validation packs**

Run:

```bash
uv run edgarpack index --packs ./packs --incremental
```

Expected: command exits 0 and search can locate pack chunks.

- [ ] **Step 4: Locate ownership evidence**

Run targeted searches for each validation company:

```bash
uv run edgarpack search '"beneficial ownership" "voting power"' --ticker MSFT
uv run edgarpack search '"principal stockholders"' --ticker MSFT
uv run edgarpack search '"security ownership"' --ticker MSFT
uv run edgarpack search '"controlled company"' --ticker MSFT
```

Repeat for `WMT`, `INTC`, `XOM`, `KO`, `GE`, `NVDA`, `GOOGL`, `META`, `AAPL`, `AVGO`, and `JPM`.

Expected: search results identify candidate sections or chunks. Search results are locators only; read the source section before writing evidence rows.

- [ ] **Step 5: Extract validation evidence rows**

For each validation company, add at least one `dominance_year` row and one life-arc row when filings allow it. Use `founder_control_signal` values:

```text
strong
visible
limited
none_found
unresolved
```

Expected: the validation slice includes positive founder-control cases, weak or absent founder-control cases, and at least one left-censored older-company row.

- [ ] **Step 6: Run validation QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path
path = Path("reports/founder-control-era/founder-control-era-table.csv")
with path.open(newline="") as f:
    rows = list(csv.DictReader(f))
if not rows:
    raise SystemExit("no evidence rows")
required = ["company", "comparison_point", "filing_form", "filing_date", "accession", "source_path", "founder_control_signal", "confidence"]
missing = []
for i, row in enumerate(rows, start=2):
    for col in required:
        if not row.get(col):
            missing.append((i, col))
    if not (row.get("evidence_section_id") or row.get("evidence_chunk_ids")):
        missing.append((i, "evidence_section_id_or_chunk_ids"))
if missing:
    raise SystemExit(f"missing required evidence fields: {missing[:20]}")
signals = {row["founder_control_signal"] for row in rows}
if not ({"strong", "visible"} & signals):
    raise SystemExit(f"expected at least one positive founder signal, found {signals}")
if not ({"none_found", "limited"} & signals):
    raise SystemExit(f"expected at least one weak or absent founder signal, found {signals}")
print(f"validation QA passed: evidence_rows={len(rows)} signals={sorted(signals)}")
PY
```

Expected:

```text
validation QA passed: evidence_rows=<count> signals=<signals>
```

- [ ] **Step 7: Commit validation slice**

Run:

```bash
git add reports/founder-control-era/founder-control-era-table.csv reports/founder-control-era/filing-selection-notes.md
git commit -m "research: extract founder control validation slice"
```

Expected: commit succeeds.

## Task 4: Full Primary-Cohort Dominance-Year Extraction

**Files:**
- Modify: `reports/founder-control-era/founder-control-era-table.csv`
- Modify: `reports/founder-control-era/filing-selection-notes.md`
- Create pack artifacts under: `packs/`

- [ ] **Step 1: Build missing 1996 primary-cohort dominance filings**

For every 1996 primary cohort company not already covered by validation, build the selected nearest proxy or fallback annual filing:

```bash
uv run edgarpack build MRK --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build IBM --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build PG --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build JNJ --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build BMY --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build PFE --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build DIS --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build PEP --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build CVX --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build AIG --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build CSCO --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build LLY --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build FNMA --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
uv run edgarpack build JPM --form "DEF 14A" --after 1996-01-01 --before 1997-12-31 --with-chunks
```

If EdgarPack cannot build a ticker because of a predecessor identity, document the mapping and build the correct CIK or company string.

- [ ] **Step 2: Build missing 2026 primary-cohort dominance filings**

For every 2026 primary cohort company not already covered by validation, build the selected latest proxy or fallback annual filing:

```bash
uv run edgarpack build AMZN --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build BRK.B --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build LLY --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build XOM --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build V --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build MU --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build AMD --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build JNJ --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build ORCL --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build MA --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
uv run edgarpack build COST --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
```

Expected: every primary-cohort company has a dominance-year source or a documented exclusion.

- [ ] **Step 3: Extract dominance-year rows**

Add one `dominance_year` row per primary-cohort company where a source filing is available. For companies in both cohorts, include one row for 1996 and one row for 2026.

Expected: the evidence table has at least 40 `dominance_year` rows minus documented exclusions.

- [ ] **Step 4: Run dominance-year QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path
path = Path("reports/founder-control-era/founder-control-era-table.csv")
with path.open(newline="") as f:
    rows = list(csv.DictReader(f))
dominance = [r for r in rows if r["comparison_point"] == "dominance_year"]
counts = {}
for row in dominance:
    key = (row["cohort_name"], row["cohort_year"])
    counts[key] = counts.get(key, 0) + 1
if not dominance:
    raise SystemExit("no dominance-year rows")
for row in dominance:
    if not row["accession"]:
        raise SystemExit(f"missing accession for {row['company']} {row['cohort_year']}")
print(f"dominance QA passed: rows={len(dominance)} counts={counts}")
PY
```

Expected:

```text
dominance QA passed: rows=<count> counts=<counts>
```

- [ ] **Step 5: Commit dominance-year extraction**

Run:

```bash
git add reports/founder-control-era/founder-control-era-table.csv reports/founder-control-era/filing-selection-notes.md
git commit -m "research: extract dominance-year founder control rows"
```

Expected: commit succeeds.

## Task 5: Life-Arc Extraction

**Files:**
- Modify: `reports/founder-control-era/company-life-arc.csv`
- Modify: `reports/founder-control-era/founder-control-era-table.csv`
- Modify: `reports/founder-control-era/filing-selection-notes.md`

- [ ] **Step 1: Complete life-arc basis for primary-cohort companies**

For each unique primary-cohort company, fill `company-life-arc.csv`:

- `ipo_or_public_basis`: `S-1`, `first_edgar_proxy`, `first_edgar_10k`, or `secondary_ipo_context`.
- `basis_source`: filing form or secondary source name.
- `first_observable_public_year`: year of the basis.
- `public_plus_10_year`: basis year plus 10.
- `public_plus_20_year`: basis year plus 20.
- `left_censored`: `true` when the company was public before EDGAR and no IPO filing is available in EDGAR.

Expected: every primary-cohort company has exactly one life-arc row.

- [ ] **Step 2: Build missing plus-10 and plus-20 filings where useful**

Build proxy filings nearest `public_plus_10_year` and `public_plus_20_year` for founder-visible companies and representative founder-absent companies. Prioritize companies where the life-arc comparison can change the interpretation:

```text
NVDA, GOOGL, META, TSLA, AMZN, ORCL, MSFT, INTC, CSCO, WMT
```

Expected: life-arc extraction covers enough cases to support a trend without forcing low-value rows for every old-line company.

- [ ] **Step 3: Extract life-arc rows**

Add `first_observable_public`, `public_plus_10`, and `public_plus_20` rows where filings support them. Use `unresolved` when a filing exists but does not disclose enough ownership detail.

Expected: the table includes life-arc rows for founder-visible current companies and selected earlier-era comparators.

- [ ] **Step 4: Run life-arc QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path
table = Path("reports/founder-control-era/founder-control-era-table.csv")
life = Path("reports/founder-control-era/company-life-arc.csv")
with table.open(newline="") as f:
    rows = list(csv.DictReader(f))
with life.open(newline="") as f:
    life_rows = list(csv.DictReader(f))
primary_companies = {r["company"] for r in life_rows if r["company"]}
life_points = [r for r in rows if r["comparison_point"] in {"first_observable_public", "public_plus_10", "public_plus_20"}]
if len(primary_companies) < 20:
    raise SystemExit(f"life-arc basis too thin: {len(primary_companies)} companies")
if len(life_points) < 15:
    raise SystemExit(f"life-arc evidence too thin: {len(life_points)} rows")
for row in life_points:
    if not row["accession"]:
        raise SystemExit(f"missing accession for life-arc row: {row['company']} {row['comparison_point']}")
print(f"life-arc QA passed: companies={len(primary_companies)} evidence_rows={len(life_points)}")
PY
```

Expected:

```text
life-arc QA passed: companies=<count> evidence_rows=<count>
```

- [ ] **Step 5: Commit life-arc extraction**

Run:

```bash
git add reports/founder-control-era/company-life-arc.csv reports/founder-control-era/founder-control-era-table.csv reports/founder-control-era/filing-selection-notes.md
git commit -m "research: add founder control life-arc rows"
```

Expected: commit succeeds.

## Task 6: Narrative Report And Extension Notes

**Files:**
- Create: `reports/founder-control-era/founder-control-era-report.md`
- Modify: `reports/founder-control-era/extension-notes.md`
- Modify: `reports/founder-control-era/README.md`

- [ ] **Step 1: Summarize the evidence table**

Run:

```bash
python3 -B - <<'PY'
import csv
from collections import Counter, defaultdict
from pathlib import Path
path = Path("reports/founder-control-era/founder-control-era-table.csv")
with path.open(newline="") as f:
    rows = list(csv.DictReader(f))
by_cohort = defaultdict(Counter)
by_point = Counter()
for row in rows:
    by_cohort[(row["cohort_name"], row["cohort_year"])][row["founder_control_signal"]] += 1
    by_point[row["comparison_point"]] += 1
print("signals_by_cohort")
for key, counts in sorted(by_cohort.items()):
    print(key, dict(counts))
print("rows_by_point", dict(by_point))
PY
```

Expected: printed counts for founder-control signals by cohort and comparison point.

- [ ] **Step 2: Write the narrative report**

Create `reports/founder-control-era/founder-control-era-report.md` with these sections:

```markdown
# Founder Control Across Dominant Company Eras

Date: 2026-04-28

## Executive Takeaway

## Method

## Cohorts

## Dominance-Year Comparison

## Life-Arc Comparison

## What Changed

## Limits

## Evidence Table
```

Rules:

- Cite cohort source URLs in `Method`.
- Cite EDGAR boundary in `Method`.
- Every company-specific claim must cite the row identifier from `founder-control-era-table.csv` and the accession or source path.
- Keep interpretation separate from observed facts.
- Mention 1989 only as context unless there is filing-backed evidence.

- [ ] **Step 3: Update extension notes from observed evidence**

Append to `extension-notes.md` only observations that the founder-control work made more interesting. Keep them framed as future research leads, not claims.

Expected: extension notes identify the best next governance, operating-profile, and KPI comparisons without bloating the founder-control report.

- [ ] **Step 4: Update README verification section**

Append:

```markdown
## Verification

- Code changed: no
- Cohort QA: passed
- Validation slice QA: passed
- Dominance-year QA: passed
- Life-arc QA: passed
- Narrative report: derived from `founder-control-era-table.csv`
```

Adjust only if a QA step did not pass; do not claim a pass that did not happen.

- [ ] **Step 5: Commit report artifacts**

Run:

```bash
git add reports/founder-control-era/README.md reports/founder-control-era/founder-control-era-report.md reports/founder-control-era/extension-notes.md
git commit -m "research: write founder control era report"
```

Expected: commit succeeds.

## Task 7: Final QA, Beads, And Push

**Files:**
- Modify: `.beads/issues.jsonl` only if a follow-up issue is filed.

- [ ] **Step 1: Run final artifact QA**

Run:

```bash
python3 -B - <<'PY'
import csv
from pathlib import Path
base = Path("reports/founder-control-era")
required = [
    "README.md",
    "cohorts.csv",
    "company-life-arc.csv",
    "filing-selection-notes.md",
    "founder-control-era-table.csv",
    "founder-control-era-report.md",
    "extension-notes.md",
]
missing = [p for p in required if not (base / p).exists()]
if missing:
    raise SystemExit(f"missing files: {missing}")
with (base / "founder-control-era-table.csv").open(newline="") as f:
    rows = list(csv.DictReader(f))
if not rows:
    raise SystemExit("no evidence rows")
bad = []
for i, row in enumerate(rows, start=2):
    if not row["accession"]:
        bad.append((i, "accession"))
    if not row["source_path"]:
        bad.append((i, "source_path"))
    if not (row["evidence_section_id"] or row["evidence_chunk_ids"]):
        bad.append((i, "evidence"))
    if not row["evidence_excerpt"]:
        bad.append((i, "evidence_excerpt"))
if bad:
    raise SystemExit(f"evidence QA failed: {bad[:20]}")
print(f"final artifact QA passed: evidence_rows={len(rows)}")
PY
```

Expected:

```text
final artifact QA passed: evidence_rows=<count>
```

- [ ] **Step 2: File follow-up beads for unfinished product work**

If repeated manual extraction was the bottleneck, run:

```bash
bd create "Build narrow governance ownership extractor from founder-control fixtures" --type task --priority 3 --description "Founder-control era research required repeated manual extraction from ownership/proxy sections. Build a narrow extractor only after using completed fixtures from reports/founder-control-era/."
```

If older proxy sectionization produced poor chunks, run:

```bash
bd create "Improve proxy ownership sectionization for older DEF 14A filings" --type task --priority 3 --description "Founder-control era research exposed older DEF 14A packs where ownership tables or sections were difficult to cite. Use reports/founder-control-era fixtures to improve section/chunk quality."
```

Expected: follow-up beads exist only for real unfinished work observed during execution.

- [ ] **Step 3: Sync and push**

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

Unrelated untracked files that existed before this plan may remain visible; do not remove them.

