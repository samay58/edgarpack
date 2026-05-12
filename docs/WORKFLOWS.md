# Workflows

This is the practical guide: what to run when you are trying to get work done.

EdgarPack is not a generic finance chatbot. It is a primary-document tool. The best use pattern is:

1. Pull the cited numbers you need.
2. Build packs for filings worth reading.
3. Discover company-specific KPIs from those packs.
4. Compare companies only after checking period and currency context.
5. Use filing diffs to inspect disclosure changes.

## Workflow 1: Public-company first pass

Use this when you are looking at a normal public company with 10-K / 10-Q history.

```bash
# Latest trailing revenue with citations
edgarpack query NVDA revenue --period ltm

# Annual trend
edgarpack query NVDA revenue,net_income,gross_margin --period lfy,lfy-1,lfy-2

# Broader operating panel
edgarpack query NVDA --preset perf --period lfy,lfy-1,lfy-2

# Audit the LTM formula and filings used
edgarpack query NVDA revenue --period ltm --audit
```

What to look for:

- Citation markers on every value.
- Period labels: FY, quarter, or LTM.
- Warnings about stale values, concept scope, fiscal-year mismatch, or incomplete formulas.

When you need the raw data shape:

```bash
edgarpack query NVDA revenue --period ltm --format json-full
```

## Workflow 2: Build a local filing corpus

Use this when you want to read, search, diff, or feed filings into another tool.

```bash
# Build recent annual filings
edgarpack build NVDA --form 10-K --last 3

# Build one exact historical filing
edgarpack build META --accession 0001326801-19-000009

# See what is available before building
edgarpack list NVDA --form 10-K --limit 10
```

Then inspect the output:

```bash
open ./packs/0001045810
```

The important files:

- `filing.full.md`: the full cleaned filing.
- `sections/*.md`: section-level source material.
- `manifest.json`: section offsets, hashes, filing metadata.
- `llms.txt`: compact entry point for tools and models.

If you want local search:

```bash
edgarpack index --packs ./packs --incremental
edgarpack search "export controls" --topic risk:export
```

## Workflow 3: Find non-GAAP and operating KPIs

Use this when the company has business metrics that do not fit the standard XBRL catalog: ARR, NRR, paid seats, GMV, systems deployed, dollar retention, customer counts.

```bash
edgarpack build FIG --form 10-K --last 3
edgarpack which FIG
```

Use the flags when you want a narrower view:

```bash
# Only the free-form KPIs discovered in the filings
edgarpack which FIG --only discovered

# Re-run discovery instead of reading the cache
edgarpack which FIG --no-cache

# Machine-readable matrix
edgarpack which FIG --format json
```

Once a KPI has been discovered, query can use it:

```bash
edgarpack query FIG net_dollar_retention_rate --period lfy
```

The right mental model: `which` teaches EdgarPack what this company discloses. `query` then retrieves the specific value.

## Workflow 4: Compare companies

Use `comps` for a quick SEC-to-SEC table:

```bash
edgarpack comps NVDA AMD INTC --metrics revenue,net_income,ebitda --period ltm
```

Use `compare` when the table spans SEC and HKEX filers, or when you want currency normalization:

```bash
edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --period lfy --currency both
edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --period lfy --currency usd
```

What to check before trusting the table:

- Period header: if fiscal years differ, the output says so.
- Currency footers: native vs USD-normalized amounts.
- Missing values: EdgarPack should show gaps rather than guess.
- Warnings block: diagnostics matter more than table neatness.

## Workflow 5: Pre-IPO / S-1 company

Use this when the company has filed S-1s but has not filed a 10-K yet.

```bash
edgarpack build "Cerebras Systems" --form S-1 --last 2
edgarpack query "Cerebras Systems" revenue,gross_profit,net_income --period lfy,lfy-1
```

For the cash-flow bridge:

```bash
edgarpack query "Cerebras Systems" operating_cash_flow,capex,free_cash_flow --period lfy,lfy-1
edgarpack query "Cerebras Systems" capital_expenditures --period lfy,lfy-1
```

The S-1 path is different from the 10-K path:

- SEC companyfacts is usually empty.
- EdgarPack reads built S-1 packs.
- Supported selected/summary financial table shapes parse deterministically.
- Unsupported shapes may use `ANTHROPIC_API_KEY` if you have it set.
- Empty newest extraction must stay empty. It should not silently fall back to an older S-1.
- Public query names stay human: use `net_income`, not `net_income_loss`; use `capital_expenditures` or `capex`, not an internal table label.

For the registration chain:

```bash
edgarpack timeline \
  --series registration \
  --cik 0002021728 \
  --packs ./packs \
  --format html \
  --out ./reports/cerebras-s1
```

Open `./reports/cerebras-s1/index.html`. Start at the index, then click into the pair reports with the highest intensity.

Use `which` as the quick inventory:

```bash
edgarpack which "Cerebras Systems"
```

For S-1 filers, `which` may show two different things: recurring operating KPIs if they exist, and cached queryable S-1 financial metrics from built registration packs. If no recurring operating KPIs are found, that is not a failed financial query. Use `query` for catalog financial metrics.

## Workflow 6: Distill one filing

Use this when a filing is too large and you want the compact substance with citations.

```bash
edgarpack distill run lime-s1 --pack packs/0001699963/0001628280-26-032523
edgarpack distill check reports/lime-s1
```

The useful files are:

- `index.md`: two-minute human scan.
- `findings.csv`: business, ownership, proceeds, risk, and other disclosure rows.
- `metrics.csv`: financial rows with period, unit, status, and evidence IDs.
- `evidence.jsonl`: compact evidence records for LLMs and downstream tools.
- `gaps.csv`: missing, ambiguous, or unsafe extraction areas.

`distill` reads existing packs only. Build the pack first, then distill it. It does not write memos or generate narrative.

## Workflow 7: Filing-change review

Use this when the question is not "what was revenue?" but "what changed in the disclosure?"

```bash
# Triage
edgarpack diff --ticker NVDA --form 10-K

# Paragraph-level terminal output
edgarpack diff --ticker NVDA --form 10-K --format full

# Static report for real reading
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

The diff engine filters out mechanical noise: table-of-contents links, date rollovers, financial statement tables, signatures, and cross-reference boilerplate. The output is meant to surface risk-factor rewrites, business-description changes, new regulatory language, and deleted sections.

For one section over time:

```bash
edgarpack timeline --ticker NVDA --section 10k_parti_item1a_risk_factors
```

## Workflow 8: Agent / LLM handoff

Use packs when you want another tool or model to read filings.

Best handoff files:

- `llms.txt`: entry point and compact index.
- `filing.full.md`: whole filing, cleaned.
- `sections/<section_id>.md`: targeted section reading.
- `manifest.json`: provenance, hashes, offsets.
- `optional/chunks.ndjson`: chunked evidence if you built with `--with-chunks`.

Build with chunks when you know the next step is retrieval:

```bash
edgarpack build NVDA --form 10-K --with-chunks
```

Use JSON when the next tool should not parse terminal tables:

```bash
edgarpack query NVDA revenue --period ltm --format json-full
edgarpack comps NVDA AMD --metrics revenue,gross_margin --period ltm --format json
edgarpack diff --ticker NVDA --form 10-K --format json
edgarpack distill run lime-s1 --pack packs/0001699963/0001628280-26-032523
```

The rule: make the model read cleaned source and citations, not raw SEC HTML and vibes.

## Workflow 9: Maximum-capability research loop

Use this when you are starting on a new company and want the full EdgarPack loop without getting lost.

```bash
# 1. Start with cited financials.
edgarpack query FIG revenue,net_income,gross_margin,free_cash_flow --period lfy

# 2. Build clean source material.
edgarpack build FIG --form 10-K --last 3

# 3. Discover issuer-specific KPIs.
edgarpack which FIG

# 4. Query a discovered KPI by slug.
edgarpack query FIG net_dollar_retention_rate --period lfy

# 5. Compare against peers.
edgarpack comps FIG ADBE MDB --metrics revenue,gross_margin,free_cash_flow --period lfy

# 6. Review disclosure changes when there are at least two filings.
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html

# 7. Hand structured output to another tool.
edgarpack query FIG revenue,gross_margin,free_cash_flow --period lfy --format json-full
```

What this gives you:

- `query`: cited values you can verify.
- `build`: cleaned primary-source files you can read, search, or hand to an LLM.
- `which`: the company's own operating vocabulary.
- `comps` / `compare`: peer context with period and currency warnings.
- `diff` / `timeline`: disclosure changes instead of just financial tables.
- JSON output: a clean handoff format for agents, notebooks, and downstream tools.

The diff example uses NVIDIA because it has enough 10-K history for a useful report. Swap in your company once you have at least two local packs for the same form.

The order matters. Pull the numbers first, then build the source, then let the filing text tell you which company-specific metrics are worth asking about.
