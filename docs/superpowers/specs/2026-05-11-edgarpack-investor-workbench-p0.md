# EdgarPack Investor Workbench P0 Brief

Date: 2026-05-11
Priority: P0
Target start: 2026-05-12
Status: Saved for spec and execution

## Why This Is P0

Recent EdgarPack research runs finally exposed the real product shape.

The strongest value is not generic financial Q&A. EdgarPack makes primary filings usable. It turns massive EDGAR documents into readable packs, comparable sections, queryable evidence, and cited outputs. That let us find material filing-only insights across Lime, Cerebras, Meta, NVIDIA, Snap, Robinhood, and the SaaS cohort work.

The product gap is now clear too. The tool is useful enough to reveal what investors want, but not yet disciplined enough to be the default research workbench. The next build cycle should focus on that gap.

## Product Position

EdgarPack should be a filing workbench for investors.

It should help a user:

- find the right filings
- build the right packs
- extract financials and KPIs safely
- normalize tables
- preserve exact evidence
- warn when a number may be unsafe
- export a thread, memo, or research bundle grounded in citations

It should not pretend to be a black-box analyst. The edge is primary-document evidence, not confident prose.

## What We Learned From Real Use

Across the recent runs, EdgarPack made hard-to-find disclosures obvious:

- Lime: revenue per vehicle per day, vehicle payback, Uber dependency, city fleet-cap increases, going-concern language, and the free-cash-flow reconciliation.
- Cerebras: the OpenAI warrant, customer-story rewrite from G42 to OpenAI/G42/MBZUAI/AWS, 20-vote Class B structure, and S-1 rewrite intensity.
- NVIDIA: 22% customer concentration, indirect OpenAI revenue language, H20 inventory charge, and tighter AI infrastructure positioning.
- Meta: mission rewrite, Reality Labs operating drag, EU regulatory pressure, and specific key-person risk language.
- Snap: subscription pivot, unnamed AI platform partner, equity dilution risk, and unused tax asset stack.
- Robinhood: stablecoin balance-sheet disclosure, DTA valuation allowance release, Robinhood Chain, and product-surface expansion.
- SaaS cohort: the need for period-safe annual history, metric definitions, KPI tables, and source-ledger-backed memos.

The lesson: EdgarPack did not manufacture the insight. It made the evidence findable fast enough for a human to reason from it.

## P0 Product Themes

### Investor Research Mode

One command should create the skeleton of a credible research bundle:

- filing selections
- raw command log
- source ledger
- standard financials table
- KPI table
- key section map
- friction log
- memo or thread outline

The report should be evidence-first. Narrative comes last.

### Strict Evidence Mode

Every generated claim needs evidence. Every derived metric needs component citations. If components come from mismatched periods, mismatched tables, stale extraction, or uncertain parsing, EdgarPack should block the result or mark it unsafe.

Lime is the anchor example. A computed free-cash-flow query crossed annual and interim capex data. The filing reconciliation was right. EdgarPack should make that kind of mismatch obvious.

### Table Normalization

Financial tables, KPI tables, debt tables, cap tables, and reconciliations need first-class structured extraction.

This is probably the highest-leverage upgrade for investor users. Today, duplicated pipe-text tables are readable enough for narrative analysis and too weak for serious financial analysis.

### S-1 Mode

Registration filings need their own workflow. S-1s are not normal 10-Ks.

A useful S-1 mode should surface:

- offering status and blanks
- use of proceeds
- debt maturity
- going-concern language
- related-party transactions
- lock-ups
- principal stockholders
- conversion terms
- interim and annual financials
- filing-defined non-GAAP reconciliations
- changes across S-1 amendments

### Resumable KPI Discovery

`which` should behave like a reliable batch job:

- progress events
- timeout controls
- resume state
- per-filing skip reasons
- stable evidence locators
- clean JSON output

KPI discovery is where filings become investor research. It cannot be slow, opaque, or locator-unstable.

### Annual Discovery Mode

Investors do not think in form families. They ask for annual history.

`edgarpack annuals <company>` should walk 10-K, 20-F, 40-F, S-1, F-1, and issuer-transition history, then return a chronological source-linked filing set with explicit gaps.

### Thread And Memo Export

The tool should create a publishable evidence pack for threads and memos:

- claims
- source sections
- citation links
- exact accession URLs
- uncertainty flags
- suggested narrative order

The writer still writes. EdgarPack assembles the evidence surface.

## Tomorrow's Spec Work

The May 12 session should turn this brief into an implementation plan.

Recommended order:

1. Decide the first shippable surface. The strongest candidate is `edgarpack research init` or an investor bundle generator, because it can wrap existing capabilities while exposing gaps clearly.
2. Split product work into implementation slices:
   - research bundle scaffolding
   - strict evidence and derived-metric guards
   - financial table normalization
   - S-1 profile mode
   - resumable `which`
   - annual filing discovery
   - export/thread pack
3. Pick one P0 slice for immediate implementation. Do not try to build all seven at once.
4. Create Linear child issues only after the slices are named and scoped.
5. Define validation around real filings, not mocks:
   - Lime / Neutron S-1
   - Cerebras S-1 to S-1 refile
   - Snap or Robinhood 10-K diff
   - SaaS cohort annual-history case

## Suggested First Slice

Start with the investor research bundle generator.

Reason: it is the most product-shaped improvement and can be built without solving every parser problem first. It gives users a better workflow immediately while creating natural places to plug in strict evidence, table normalization, S-1 mode, and KPI discovery improvements.

Possible command shape:

```bash
uv run edgarpack research init lime-s1 --company "Neutron Holdings" --form S-1 --accession 0001628280-26-032523 --template investor-s1
```

Initial output:

```text
reports/<slug>/
  README.md
  filing-selection-notes.md
  edgarpack-run-log.md
  source-ledger.csv
  financials.csv
  kpi-table.csv
  section-map.md
  friction-log.md
  memo-outline.md
```

Done means a user can run one command, get the evidence-bundle structure, and continue research without inventing the folder layout or QA process manually.

## Related Saved Artifacts

- `reports/edgarpack-feedback-synthesis.md`
- `reports/lime-s1-analysis/thread-highlights.md`
- `reports/lime-s1-analysis/lime-s1-investor-read.md`
- `reports/lime-s1-analysis/revel-shutdown-research.md`
- `reports/threads/lime-s1-thread-v2.md`
- `reports/saas-evolution/edgarpack-friction-log.md`
- `reports/saas-evolution/edgarpack-investor-product-recommendations.md`
- `reports/threads/cerebras-s1-thread-notes.md`
- `reports/threads/nvda-meta-thread-notes.md`
- `reports/threads/snap-hood-thread-notes.md`

## Non-Negotiables

- Evidence first, prose last.
- No uncited generated claims.
- No silent period substitutions.
- No derived metrics without component citations.
- No JSON mode that writes non-JSON to stdout.
- No investor workflow that requires the user to know SEC form families up front.
- Real-filing validation before calling the feature done.
