# Founder Control Research Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a citation-backed research bundle showing how founder control changed across 2026, 2016, and 2006 for the current top ten technology companies.

**Architecture:** This is a research execution plan, not an EdgarPack product feature. It uses existing `edgarpack identify`, `list`, `build`, `index`, `search`, and `diff` surfaces, then writes auditable artifacts under `reports/founder-control/`. The final CSV is the source of truth; the narrative report is derived from the CSV.

**Tech Stack:** EdgarPack CLI via `uv run`, SEC EDGAR filings, local pack artifacts under `packs/`, Markdown, CSV, shell commands, and manual evidence review. Required external access: SEC endpoints through EdgarPack and one current market-cap source page for cohort freeze. Required environment: `EDGARPACK_USER_AGENT`.

---

## Scope Check

The approved spec is focused on one research workflow. It does not cover independent software subsystems, so it does not need to be split into separate implementation plans.

This plan intentionally avoids new code. If repeated manual extraction becomes the bottleneck after the pilot, open a follow-up bead for a narrow governance extractor with fixtures from this research bundle.

## File Structure

- Create: `reports/founder-control/README.md`
  - Purpose: research bundle index, source policy, and command log summary.
- Create: `reports/founder-control/cohort.csv`
  - Purpose: frozen top-ten cohort, market-cap source, retrieval date, and EdgarPack identity fields.
- Create: `reports/founder-control/filing-selection-notes.md`
  - Purpose: short notes for non-obvious filing choices, missing exact-year filings, ADR/20-F source differences, and fallback decisions.
- Create: `reports/founder-control/founder-control-table.csv`
  - Purpose: authoritative research table. Every factual claim in the report must map to this file.
- Create: `reports/founder-control/founder-control-report.md`
  - Purpose: readable synthesis derived from the CSV.
- Create as needed: `reports/founder-control/search-notes/$TICKER.md`
  - Purpose: compact search/read notes for companies where source sections are hard to locate.
- Create as needed: `reports/founder-control/$TICKER-control-change.html`
  - Purpose: optional EdgarPack diff report for comparable filing pairs.
- Modify: none in `edgarpack/`.
- Test: no code tests. Use evidence QA gates in Tasks 2, 4, 6, and 8.

## External Dependencies

- `EDGARPACK_USER_AGENT`: required by SEC for network fetches.
- Market-cap source: use `https://companiesmarketcap.com/tech/largest-tech-companies-by-market-cap/` unless it is unavailable. If unavailable, use another current market-cap ranking source and record the URL and retrieval date in `cohort.csv` and `README.md`.
- No Anthropic, DeepInfra, or other LLM API key is required for this research workflow.

## Data Flow

```text
Current market-cap source
  -> cohort.csv
  -> EdgarPack identity + filing discovery
  -> built packs with chunks
  -> search + section review
  -> founder-control-table.csv
  -> founder-control-report.md
  -> optional HTML diffs
```

## Important Constraints

- Do not use `edgarpack query` for founder control. Founder control is not an XBRL metric.
- Do not use `edgarpack which` as the core workflow. `which` is for recurring operating KPIs and skips DEF 14A; use `search`, section files, and `filing.full.md`.
- Do not treat search misses as evidence of absence.
- Do not invent founder identity. Use only what the filing supports.
- Do not add non-SEC source acquisition in this run.

### Task 1: Research Bundle Setup And Cohort Freeze

**Files:**
- Create: `reports/founder-control/README.md`
- Create: `reports/founder-control/cohort.csv`
- Create: `reports/founder-control/filing-selection-notes.md`

- [ ] **Step 1: Confirm repo and environment**

Run:

```bash
git rev-parse --show-toplevel
printenv EDGARPACK_USER_AGENT
```

Expected:

```text
/Users/samaydhawan/Projects/active/edgarpack
Samay Dhawan samay58@gmail.com
```

If `EDGARPACK_USER_AGENT` is empty, set it before continuing:

```bash
export EDGARPACK_USER_AGENT="Samay Dhawan samay58@gmail.com"
```

- [ ] **Step 2: Create the research directories**

Run:

```bash
mkdir -p reports/founder-control/search-notes
```

Expected: command exits 0 and `reports/founder-control/search-notes/` exists.

- [ ] **Step 3: Write the bundle README skeleton**

Create `reports/founder-control/README.md` with this content:

```markdown
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
```

- [ ] **Step 4: Freeze the cohort**

Open the cohort source URL from the README. Copy the current top ten technology companies into `reports/founder-control/cohort.csv` using this exact header:

```csv
rank,company,ticker,country,market_cap,cohort_source_url,cohort_retrieved_at,edgarpack_input,cik,edgarpack_source,identity_notes
```

For each row:

- `rank`: rank shown by the cohort source.
- `company`: company name shown by the cohort source.
- `ticker`: ticker shown by the cohort source.
- `country`: country shown by the cohort source.
- `market_cap`: market cap shown by the cohort source.
- `cohort_source_url`: full URL used.
- `cohort_retrieved_at`: `2026-04-28`.
- `edgarpack_input`: the ticker or company string to pass to `edgarpack identify`.
- `cik`: leave empty until Task 2.
- `edgarpack_source`: leave empty until Task 2.
- `identity_notes`: leave empty unless identity resolution is ambiguous.

Expected: `cohort.csv` has 11 lines: one header plus ten company rows.

- [ ] **Step 5: Start filing-selection notes**

Create `reports/founder-control/filing-selection-notes.md`:

```markdown
# Filing Selection Notes

Use this file only for judgment calls: missing exact-year filings, ambiguous share classes, ADR/20-F treatment, S-1/F-1 fallback, or companies where the nearest available filing changes the interpretation.

## Notes
```

- [ ] **Step 6: Commit setup artifacts**

Run:

```bash
git add reports/founder-control/README.md reports/founder-control/cohort.csv reports/founder-control/filing-selection-notes.md
git commit -m "research: freeze founder control cohort"
```

Expected: commit succeeds. Unrelated untracked files outside `reports/founder-control/` remain untouched.

### Task 2: Identity Resolution And Filing Discovery

**Files:**
- Modify: `reports/founder-control/cohort.csv`
- Modify: `reports/founder-control/filing-selection-notes.md`
- Create as needed: `reports/founder-control/search-notes/$TICKER.md`

- [ ] **Step 1: Resolve each company through EdgarPack**

For each `edgarpack_input` in `cohort.csv`, run:

```bash
uv run edgarpack identify "$EDGARPACK_INPUT"
```

For each company, update `cohort.csv`:

- `cik`: CIK when EdgarPack returns one.
- `edgarpack_source`: `SEC`, `HKEX`, `SSE`, `private`, or `unknown` as returned by the command.
- `identity_notes`: ambiguity, ADR mapping, duplicate share class, or non-SEC limitation.

Expected: every row has an `edgarpack_source`. SEC and ADR/20-F rows have a CIK when EdgarPack can resolve one.

- [ ] **Step 2: List candidate filings for each SEC/ADR row**

Run the relevant commands per company. Use the company ticker or name that resolved correctly in Step 1.

```bash
uv run edgarpack list "$EDGARPACK_INPUT" --form "DEF 14A" --limit 40
uv run edgarpack list "$EDGARPACK_INPUT" --form "20-F" --limit 25
uv run edgarpack list "$EDGARPACK_INPUT" --form "10-K" --limit 25
uv run edgarpack list "$EDGARPACK_INPUT" --form "S-1" --limit 10
uv run edgarpack list "$EDGARPACK_INPUT" --form "F-1" --limit 10
```

Expected: for most U.S. companies, DEF 14A and 10-K lists are available; for ADR or foreign private issuers, 20-F may be the relevant source.

- [ ] **Step 3: Note non-obvious filing choices only**

Append to `reports/founder-control/filing-selection-notes.md` only when a filing choice requires judgment. Use this format:

```markdown
### $TICKER $ANCHOR_YEAR

- Candidate forms checked: DEF 14A, 20-F, 10-K, S-1, F-1
- Selected filing: $FORM filed $FILING_DATE accession $ACCESSION
- Reason: nearest exact governance disclosure available for the anchor year
- Limitation: missing exact-year coverage, ADR source-form difference, S-1/F-1 fallback, or no limitation
```

Expected: obvious exact-year proxy selections do not need notes; exceptions are documented clearly.

- [ ] **Step 4: Commit identity and filing notes**

Run:

```bash
git add reports/founder-control/cohort.csv reports/founder-control/filing-selection-notes.md reports/founder-control/search-notes
git commit -m "research: resolve founder control filing candidates"
```

Expected: commit succeeds.

### Task 3: Pilot Pack Build

**Files:**
- Modify: `reports/founder-control/filing-selection-notes.md`
- Create pack artifacts under: `packs/`

- [ ] **Step 1: Select the pilot companies**

Use:

```text
META: strong founder-control case
AAPL or MSFT: likely weak or changed founder-control case
TSM or ASML: ADR or 20-F case if included in the frozen top ten
```

If TSM or ASML is not in the frozen top ten, select the highest-ranked ADR/20-F company in `cohort.csv`. If there is no ADR/20-F company in the frozen top ten, record that in `filing-selection-notes.md` and run only the two U.S. pilot cases.

- [ ] **Step 2: Build exact selected filings with chunks**

For each selected pilot filing from Task 2, prefer accession-specific builds:

```bash
uv run edgarpack build "$EDGARPACK_INPUT" --accession "$ACCESSION" --with-chunks
```

Expected:

```text
✓ Pack built
  Output: packs/$CIK/$ACCESSION
```

If an accession-specific build fails because the identity resolver needs a CIK, use:

```bash
uv run edgarpack build "$CIK" --accession "$ACCESSION" --with-chunks
```

- [ ] **Step 3: Use date-window builds only when exact accession selection is not possible**

Run this form only for a single-company anchor when Task 2 did not surface a clean accession:

```bash
uv run edgarpack build "$EDGARPACK_INPUT" --form "DEF 14A" --after 2025-01-01 --before 2026-12-31 --with-chunks
```

Expected: zero or more packs are built. If zero packs are built, record the missing coverage in `filing-selection-notes.md`.

- [ ] **Step 4: Run pack doctor on pilot companies**

For each pilot company:

```bash
uv run edgarpack doctor "$EDGARPACK_INPUT"
```

Expected: pack manifests are readable. If a pack lacks chunks, rebuild that accession with `--with-chunks` or record the limitation.

- [ ] **Step 5: Commit pilot packs registry changes and notes**

Run:

```bash
git status --short
git add reports/founder-control/filing-selection-notes.md
git commit -m "research: build founder control pilot packs"
```

Expected: commit succeeds if notes changed. If only ignored cache/pack artifacts changed and no tracked files changed, skip the commit and record that in the final handoff.

### Task 4: Pilot Extraction

**Files:**
- Create: `reports/founder-control/founder-control-table.csv`
- Create as needed: `reports/founder-control/search-notes/$TICKER.md`

- [ ] **Step 1: Create the authoritative table**

Create `reports/founder-control/founder-control-table.csv` with this header:

```csv
company,ticker,cik,anchor_year,filing_form,filing_date,accession,source_path,founder_names,founder_executive_role,founder_board_role,founder_economic_ownership_pct,founder_voting_power_pct,dual_class_or_control_mechanism,controlled_company_status,control_summary,evidence_section_id,evidence_chunk_ids,evidence_excerpt,confidence,notes
```

Expected: file exists with exactly one header line.

- [ ] **Step 2: Index the built packs**

Run:

```bash
uv run edgarpack index --packs ./packs --incremental
```

Expected: command exits 0. If a pack was built without chunks, search may be weaker; use section files and record the limitation.

- [ ] **Step 3: Search for governance evidence**

For each pilot ticker, run targeted searches:

```bash
uv run edgarpack search '"beneficial ownership" "voting power"' --ticker "$TICKER"
uv run edgarpack search '"Class B" "voting power"' --ticker "$TICKER"
uv run edgarpack search '"controlled company"' --ticker "$TICKER"
uv run edgarpack search '"principal stockholders"' --ticker "$TICKER"
uv run edgarpack search '"security ownership" "voting"' --ticker "$TICKER"
```

Expected: at least one relevant hit for founder-control-positive cases. Search misses do not prove absence.

- [ ] **Step 4: Read the local source material**

For each promising search hit, open the local pack source:

```bash
ls "packs/$CIK/$ACCESSION/sections"
sed -n '1,220p' "packs/$CIK/$ACCESSION/filing.full.md"
```

When a relevant section file is obvious, read that section instead:

```bash
sed -n '1,260p' "packs/$CIK/$ACCESSION/sections/$SECTION_FILE"
```

Expected: evidence text is reviewed from local pack files, not from search snippets alone.

- [ ] **Step 5: Record search notes only when helpful**

When evidence is hard to locate, create `reports/founder-control/search-notes/$TICKER.md`:

```markdown
# $TICKER Search Notes

## Anchor $ANCHOR_YEAR

- Filing: $FORM filed $FILING_DATE accession $ACCESSION
- Useful searches:
  - "beneficial ownership" "voting power"
  - "Class B" "voting power"
- Reviewed source files:
  - packs/CIK/ACCESSION/filing.full.md
  - packs/CIK/ACCESSION/sections/SECTION.md
- Evidence decision: short explanation of what was extracted or why no factual row was added
```

Expected: notes are concise and only exist for companies where they reduce reviewer confusion.

- [ ] **Step 6: Add pilot rows to the CSV**

For each pilot company-year where evidence is available, append one row to `founder-control-table.csv`. Keep percentages as disclosed strings, such as `61.0%`, when exact normalization would lose meaning.

Expected for a factual row:

- `accession` is filled.
- `source_path` points to a local pack file.
- `evidence_section_id` or `evidence_chunk_ids` is filled.
- `evidence_excerpt` is short enough to audit.
- `confidence` is `high`, `medium`, or `low`.

- [ ] **Step 7: Pilot QA**

Run:

```bash
python3 - <<'PY'
import csv
from pathlib import Path

path = Path("reports/founder-control/founder-control-table.csv")
rows = list(csv.DictReader(path.open()))
required = ["company", "ticker", "anchor_year", "filing_form", "filing_date", "accession", "source_path", "evidence_excerpt", "confidence"]
bad = []
for i, row in enumerate(rows, start=2):
    missing = [field for field in required if not row.get(field, "").strip()]
    has_evidence_anchor = bool(row.get("evidence_section_id", "").strip() or row.get("evidence_chunk_ids", "").strip())
    if missing or not has_evidence_anchor:
        bad.append((i, missing, has_evidence_anchor))
print(f"rows={len(rows)}")
if bad:
    for item in bad:
        print(f"bad_row={item}")
    raise SystemExit(1)
PY
```

Expected: command prints the pilot row count and exits 0.

- [ ] **Step 8: Commit pilot extraction**

Run:

```bash
git add reports/founder-control/founder-control-table.csv reports/founder-control/search-notes
git commit -m "research: extract founder control pilot evidence"
```

Expected: commit succeeds.

### Task 5: Full Cohort Pack Build And Search

**Files:**
- Modify: `reports/founder-control/filing-selection-notes.md`
- Create as needed: `reports/founder-control/search-notes/$TICKER.md`
- Create pack artifacts under: `packs/`

- [ ] **Step 1: Build selected filings for the remaining cohort**

For each company-year selected in Task 2 and not already built in Task 3:

```bash
uv run edgarpack build "$EDGARPACK_INPUT" --accession "$ACCESSION" --with-chunks
```

If the build requires CIK:

```bash
uv run edgarpack build "$CIK" --accession "$ACCESSION" --with-chunks
```

Expected: every available selected filing has a local pack, or a missing-coverage note exists in `filing-selection-notes.md`.

- [ ] **Step 2: Re-index the corpus**

Run:

```bash
uv run edgarpack index --packs ./packs --incremental
```

Expected: command exits 0.

- [ ] **Step 3: Search each remaining company**

For each remaining ticker:

```bash
uv run edgarpack search '"beneficial ownership" "voting power"' --ticker "$TICKER"
uv run edgarpack search '"Class B" "voting power"' --ticker "$TICKER"
uv run edgarpack search '"controlled company"' --ticker "$TICKER"
uv run edgarpack search '"principal stockholders"' --ticker "$TICKER"
uv run edgarpack search '"security ownership" "voting"' --ticker "$TICKER"
```

Expected: relevant source areas are located or the reviewer inspects the ownership/governance sections directly.

- [ ] **Step 4: Commit full-build notes**

Run:

```bash
git add reports/founder-control/filing-selection-notes.md reports/founder-control/search-notes
git commit -m "research: build founder control cohort packs"
```

Expected: commit succeeds if tracked notes changed. If only ignored pack/cache artifacts changed, skip the commit and record that in the final handoff.

### Task 6: Full Table Extraction

**Files:**
- Modify: `reports/founder-control/founder-control-table.csv`
- Modify as needed: `reports/founder-control/search-notes/$TICKER.md`

- [ ] **Step 1: Add all available company-year rows**

For each company-year:

- Use the selected filing from `filing-selection-notes.md` or the obvious exact-year proxy/annual filing.
- Read local `sections/*.md` first when sections are useful.
- Fall back to `filing.full.md` when sectionization is broad.
- Add one CSV row only when the evidence standard is met.

Expected: the table has up to 30 rows. Fewer rows are acceptable only when missing coverage is documented in `filing-selection-notes.md`.

- [ ] **Step 2: Preserve separate control dimensions**

When filling rows:

- Put founder economic ownership in `founder_economic_ownership_pct`.
- Put founder voting power in `founder_voting_power_pct`.
- Put dual-class, founder trust, family entity, voting agreement, or controlled-company mechanism in `dual_class_or_control_mechanism`.
- Put the founder's management role in `founder_executive_role`.
- Put the founder's board role in `founder_board_role`.

Expected: the CSV does not collapse control into a single score.

- [ ] **Step 3: QA every CSV row**

Run:

```bash
python3 - <<'PY'
import csv
from pathlib import Path

path = Path("reports/founder-control/founder-control-table.csv")
rows = list(csv.DictReader(path.open()))
required = ["company", "ticker", "anchor_year", "filing_form", "filing_date", "accession", "source_path", "evidence_excerpt", "confidence"]
bad = []
for i, row in enumerate(rows, start=2):
    missing = [field for field in required if not row.get(field, "").strip()]
    has_evidence_anchor = bool(row.get("evidence_section_id", "").strip() or row.get("evidence_chunk_ids", "").strip())
    confidence_ok = row.get("confidence", "").strip() in {"high", "medium", "low"}
    if missing or not has_evidence_anchor or not confidence_ok:
        bad.append((i, missing, has_evidence_anchor, row.get("confidence", "")))
print(f"rows={len(rows)}")
if len(rows) == 0:
    raise SystemExit("no rows extracted")
if bad:
    for item in bad:
        print(f"bad_row={item}")
    raise SystemExit(1)
PY
```

Expected: command exits 0.

- [ ] **Step 4: Commit full table**

Run:

```bash
git add reports/founder-control/founder-control-table.csv reports/founder-control/search-notes
git commit -m "research: complete founder control evidence table"
```

Expected: commit succeeds.

### Task 7: Narrative Report And Optional Diffs

**Files:**
- Create: `reports/founder-control/founder-control-report.md`
- Create as needed: `reports/founder-control/$TICKER-control-change.html`

- [ ] **Step 1: Generate useful HTML diffs only where comparable**

For companies with comparable older and newer filing packs:

```bash
uv run edgarpack diff \
  --before "packs/$CIK/$OLDER_ACCESSION" \
  --after "packs/$CIK/$NEWER_ACCESSION" \
  --format html \
  --out "reports/founder-control/$TICKER-control-change.html"
```

Expected: HTML file is written. Skip diff generation when filings are not comparable, such as proxy vs S-1 or 20-F vs DEF 14A.

- [ ] **Step 2: Write the report from the CSV**

Create `reports/founder-control/founder-control-report.md`. Keep the Method and Evidence Files sections factual. Write Findings, Company Notes, and Source Limitations from `founder-control-table.csv` and `filing-selection-notes.md`.

```markdown
# Founder Control Across Today's Top Technology Companies

Date: 2026-04-28

## Method

This report uses the current top ten technology companies frozen in `cohort.csv`, then tracks each company across 2026, 2016, and 2006 where primary SEC filings are available. The authoritative evidence table is `founder-control-table.csv`.

The source priority is DEF 14A, then 20-F for ADR or foreign private issuer cases, then 10-K Part III, then S-1 or F-1 only when the company was not yet public at the anchor year.

## Findings

Summarize only patterns supported by rows in `founder-control-table.csv`.

## Company Notes

Use this section for concise per-company observations and source limitations.

## Source Limitations

List missing exact-year filings, ADR/20-F differences, S-1/F-1 fallback cases, and rows with medium or low confidence.

## Evidence Files

- `cohort.csv`
- `filing-selection-notes.md`
- `founder-control-table.csv`
- `search-notes/`
```

Expected: every report claim has a matching CSV row.

- [ ] **Step 3: Check report claims against CSV**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

report = Path("reports/founder-control/founder-control-report.md").read_text()
for forbidden in [
    "from memory",
    "unsupported by founder-control-table.csv",
]:
    if forbidden in report:
        raise SystemExit(f"report still contains drafting instruction: {forbidden}")
print("report source-discipline check passed")
PY
```

Expected: command exits 0.

- [ ] **Step 4: Commit report and diffs**

Run:

```bash
git add reports/founder-control/founder-control-report.md reports/founder-control/*-control-change.html
git commit -m "research: write founder control report"
```

Expected: commit succeeds if report or diff files changed.

### Task 8: Final QA And Handoff

**Files:**
- Modify: `reports/founder-control/README.md`

- [ ] **Step 1: Update README with final artifact status**

Edit `reports/founder-control/README.md` so the Artifact Index reflects which optional files exist and which companies have HTML diffs.

Expected: README accurately describes the produced bundle.

- [ ] **Step 2: Run final artifact checks**

Run:

```bash
python3 - <<'PY'
import csv
from pathlib import Path

base = Path("reports/founder-control")
required = [
    base / "README.md",
    base / "cohort.csv",
    base / "filing-selection-notes.md",
    base / "founder-control-table.csv",
    base / "founder-control-report.md",
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit(f"missing required artifacts: {missing}")

cohort_rows = list(csv.DictReader((base / "cohort.csv").open()))
table_rows = list(csv.DictReader((base / "founder-control-table.csv").open()))
if len(cohort_rows) != 10:
    raise SystemExit(f"expected 10 cohort rows, found {len(cohort_rows)}")
if not table_rows:
    raise SystemExit("founder-control-table.csv has no evidence rows")

for row in table_rows:
    if not row["accession"].strip():
        raise SystemExit(f"missing accession for {row}")
    if not (row["evidence_section_id"].strip() or row["evidence_chunk_ids"].strip()):
        raise SystemExit(f"missing evidence anchor for {row}")
print(f"cohort_rows={len(cohort_rows)} evidence_rows={len(table_rows)}")
PY
```

Expected: command exits 0 and prints cohort/evidence row counts.

- [ ] **Step 3: Record no-code test status**

Append this section to `reports/founder-control/README.md`:

```markdown
## Verification

- Code changed: no
- Quality gates: artifact integrity checks in Task 8 passed
- SEC pack builds: see `filing-selection-notes.md` for missing or fallback filings
- Narrative report: derived from `founder-control-table.csv`
```

- [ ] **Step 4: Commit final README**

Run:

```bash
git add reports/founder-control/README.md
git commit -m "research: finalize founder control bundle"
```

Expected: commit succeeds if README changed.

- [ ] **Step 5: Repo closeout**

Run:

```bash
git status --short
bd sync
git pull --rebase
git push
git status --short
```

Expected:

- `bd sync` succeeds.
- `git pull --rebase` succeeds.
- `git push` succeeds.
- Final `git status --short` shows no tracked changes from this workflow. Pre-existing unrelated untracked files may remain if they were present before execution.

## Self-Review

Spec coverage:

- Research-first, no product feature: Tasks 1-8 create research artifacts only.
- Current top ten tracked backward: Task 1 freezes `cohort.csv`; Tasks 2-6 track anchor years.
- SEC-first plus ADR/20-F: Tasks 2 and 3 include DEF 14A, 20-F, 10-K, S-1, and F-1 discovery and build paths.
- Citation-backed table plus narrative report: Tasks 4, 6, and 7 create and validate the table/report pair.
- Evidence standard: Tasks 4, 6, and 8 enforce accession plus section or chunk evidence.
- Fragile proxy sectionization assumption: Tasks 4 and 6 explicitly allow section or full-filing review when sectionization is weak.

Placeholder scan:

- The plan uses shell variables such as `$TICKER`, `$CIK`, and `$ACCESSION` only as execution variables populated by prior steps. They are not unspecified design gaps.
- No unresolved design placeholders remain.

Type consistency:

- Artifact names match the spec: `cohort.csv`, `filing-selection-notes.md`, `founder-control-table.csv`, `founder-control-report.md`, and optional `$TICKER-control-change.html`.
- CSV field names match the approved table schema.
