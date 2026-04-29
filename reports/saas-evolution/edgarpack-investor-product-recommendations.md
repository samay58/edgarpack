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

### 1. Investor Annual Discovery Mode

Investor problem: a public-company history is not a form-type problem. A real SaaS investor wants "give me the annual evidence history for Shopify or Atlassian," not "guess whether this issuer used 10-K, 20-F, 40-F, S-1, or F-1 in each period."

Research moment: SHOP and TEAM looked thin under a 10-K-only workflow until the run explicitly queried 40-F / 20-F / F-1 history. That is not an analyst insight; it is avoidable product friction.

Proposed product shape: `edgarpack annuals <ticker>` or an investor mode inside `list` that walks form families, issuer transitions, IPO/F-1/S-1 roots, foreign-issuer filings, and current 10-K adoption. Output should be chronological, source-linked, and explicit about gaps.

Proof path: `filing-selection-notes.md` exists because the CLI did not collapse this into one investor-grade annual filing set.

Candidate bead: `edgarpack-9mb.1`.

### 2. Machine-Grade JSON Contract

Investor problem: if EdgarPack is going to power repeatable research, JSON output has to be safe to redirect, parse, diff, and feed into source-ledger generation.

Research moment: `which --format json` files contained progress/resolver text before JSON, so the bundle needed cleanup before it could validate evidence.

Proposed product shape: all `--format json` commands write only machine-readable JSON to stdout, with logs/progress on stderr. Add contract tests that redirect stdout to a file and immediately parse it.

Proof path: `raw/edgarpack/which-*.json` had to be normalized before the KPI table could pass QA.

Candidate bead: `edgarpack-9mb.2`.

### 3. SaaS Metric Registry / Investor Metric Pack

Investor problem: ARR, RPO, cRPO, NRR, GMV, subscription backlog, FCF, SBC, and AI credits are not interchangeable. The hard work is not extracting the number; it is extracting the definition, exclusions, measurement window, and comparability warning.

Research moment: the report only became useful once it separated Salesforce RPO/cRPO, Adobe ARR, Snowflake NRR/RPO caveats, MongoDB Atlas ARR annualization, Shopify payments GMV, and Workday subscription backlog.

Proposed product shape: a SaaS metric pack that emits a definition table with included items, excluded items, measurement window, confidence, chunk ID, and "do not compare blindly" warnings. This should be a first-class investor artifact, not a side effect of generic search.

Proof path: `metric-definition-table.csv`, `kpi-disclosure-table.csv`, and `source-ledger.csv` are the manual prototype.

Candidate bead: `edgarpack-9mb.3`.

### 4. Strict Historical Period Semantics

Investor problem: cohort work needs period truth. A sparse 10-year lookback must not silently become "whatever recent fact the system found."

Research moment: early `lfy,lfy-5,lfy-10` query output could have produced false baselines. The final bundle switched to annual-series extraction and caveated earliest/closest rows.

Proposed product shape: every query row should expose `requested_period`, `returned_fiscal_year`, `period_match_status`, and `substitution_reason`. Investor mode should support fail-closed semantics for missing lookbacks.

Proof path: `search-notes/standard-financials.md` documents the deviation; baseline rows in `standard-financials.csv` now carry caveats where annual history is incomplete.

Candidate bead: `edgarpack-9mb.4`.

### 5. Resumable KPI Discovery With Citation Guarantees

Investor problem: KPI discovery is where filings become investment research. It has to run across a cohort without hanging, and every emitted KPI must carry a stable evidence pointer.

Research moment: full `which` runs stalled and required targeted fallbacks; some useful KPI rows still had section-level locators instead of chunk IDs.

Proposed product shape: a cohort `which` runner with progress events, per-filing timeouts, resume state, skip reasons, and a citation contract: `chunk_id` or structured `no_chunk_reason`.

Proof path: `edgarpack-friction-log.md` records runtime and locator failures; several KPI/business-model rows are labeled fallback or medium confidence.

Candidate bead: `edgarpack-9mb.5`.

### 6. Investor Research Bundle Generator

Investor problem: the artifact investors need is not a chatbot answer. It is a research bundle: cohort file, filing selections, raw command captures, evidence tables, source ledger, friction log, and citation-gated memo.

Research moment: the SaaS report became credible only because the bundle forced table-first evidence and row-level citations before narrative.

Proposed product shape: `edgarpack research init --template investor-saas` plus a generator that can populate standard financials, KPI tables, metric definitions, source ledger, and memo scaffolding. Memo generation should refuse uncited findings.

Proof path: `reports/saas-evolution/` is the working prototype.

Candidate bead: `edgarpack-9mb.6`.
