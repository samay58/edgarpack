# Getting Started

This is the first-run guide. It assumes you have never used EdgarPack before and may not know the SEC filing vocabulary yet.

EdgarPack does two jobs:

1. It turns SEC filings into clean local packs: markdown, sections, hashes, citations, and optional chunks.
2. It answers financial questions from primary filings with citations, instead of asking you to trust a model summary.

The simple mental model:

- Use `query` when you want a number.
- Use `build` when you want the filing cleaned up into local source files.
- Use `which` when you want to know which company-specific KPIs are available.
- Use `diff` or `timeline` when you want to know what changed between filings.
- Use JSON output when another tool or agent needs to consume the result.

## 1. Install EdgarPack

If you are installing the package as a normal user:

```bash
pip install edgarpack
```

If you are inside this repo and developing locally:

```bash
uv pip install -e ".[dev,china,vlm]"
```

The rest of this guide shows commands as `edgarpack ...`. If your shell says `command not found: edgarpack` and you are inside this repo, run the same command with `uv run` in front:

```bash
uv run edgarpack query NVDA revenue --period ltm
```

## 2. Set the SEC user agent

The SEC requires every automated request to identify who is making it. Use your name and email:

```bash
export EDGARPACK_USER_AGENT="Your Name your.email@example.com"
```

Check it:

```bash
test -n "$EDGARPACK_USER_AGENT" && echo "EDGARPACK_USER_AGENT is set"
```

Optional, but useful if you want all cache files in one predictable place:

```bash
export EDGARPACK_CACHE_DIR="$HOME/.edgarpack/cache"
```

## 3. Optional: set Anthropic for harder extraction

Most public-company `query` commands do not need an LLM. They use SEC companyfacts or deterministic pack extraction.

Some workflows do benefit from an Anthropic key:

- `which` can use an LLM pass to discover company-specific KPIs from MD&A.
- Some S-1 table shapes need a VLM fallback when deterministic parsing cannot read the table.
- Unsupported disclosure extraction should fail empty rather than reuse stale numbers.

Install the VLM extra if you have not already:

```bash
uv pip install -e ".[dev,china,vlm]"
```

Set the key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Check that your current shell sees it:

```bash
test -n "$ANTHROPIC_API_KEY" && echo "ANTHROPIC_API_KEY is set"
```

That command only prints whether the variable exists. It does not print the secret.

## 4. Ask one cited financial question

Start with NVIDIA revenue:

```bash
edgarpack query NVDA revenue --period ltm
```

You should see a number and a citation marker. For LTM revenue, EdgarPack computes the value from three filings:

```text
LTM = most recent year-to-date quarter + latest fiscal year - prior-year matching quarter
```

The answer matters, but the source trail matters more. The output tells you which filings it used.

Useful next queries:

```bash
# Multiple metrics in one run
edgarpack query NVDA revenue,net_income,gross_margin --period ltm

# Annual history, newest first
edgarpack query NVDA revenue,net_income,gross_margin --period lfy,lfy-1,lfy-2

# A broader operating panel
edgarpack query NVDA --preset perf --period lfy,lfy-1,lfy-2

# Show the LTM formula and components
edgarpack query NVDA revenue --period ltm --audit

# Return structured data for another tool
edgarpack query NVDA revenue --period ltm --format json-full
```

Company input is forgiving. Ticker, CIK, and company name all work:

```bash
edgarpack query 0001045810 revenue
edgarpack query "NVIDIA" revenue
edgarpack query "apple inc" revenue
```

## 5. Build your first filing pack

`query` can answer many public-company questions without building a pack first. `build` is what you run when you want the filing itself as clean source material.

```bash
edgarpack build NVDA --form 10-K
```

That writes a folder under `packs/<CIK>/<accession>/`:

```text
filing.full.md       # full cleaned filing
sections/*.md        # one file per detected section
manifest.json        # filing metadata, section offsets, hashes
llms.txt             # compact entry point for tools and models
optional/            # chunks.ndjson and xbrl.json when requested
```

Build more history when you want timelines, `which`, or local search:

```bash
edgarpack build NVDA --form 10-K --last 3
edgarpack build META --accession 0001326801-19-000009
edgarpack list "NVIDIA" --form 10-K --limit 10
```

## 6. Find company-specific KPIs

Some important metrics are not standard XBRL concepts. Figma discloses paid customers and net dollar retention. A marketplace may disclose GMV. A usage-based software company may disclose customer cohorts.

`which` answers: what does this company actually disclose?

```bash
edgarpack build FIG --form 10-K --last 3
edgarpack which FIG
```

The output shows slugs you can query later. Example:

```bash
edgarpack query FIG net_dollar_retention_rate --period lfy
```

If `which` says it found no qualifying KPIs, that does not mean the company has no numbers at all. It means EdgarPack did not find recurring operating KPIs in the built filings. You can still use catalog metrics like `revenue`, `net_income`, `gross_margin`, and `free_cash_flow`.

## 7. Compare companies

Use `comps` for SEC-to-SEC comps:

```bash
edgarpack comps NVDA AMD INTC --metrics revenue,net_income,ebitda --period ltm
```

Use `compare` when the table spans SEC and HKEX filers, or when you want currency normalization:

```bash
edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --period lfy --currency usd
```

Read the period header and footnotes. If fiscal years or currencies differ, EdgarPack should say so instead of pretending every column is perfectly comparable.

## 8. Review what changed between filings

For quick triage:

```bash
edgarpack diff --ticker NVDA --form 10-K
```

For the better reading surface:

```bash
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

Open `./reports/nvda-10k.html` in a browser. It is a static local file with changed sections, changed paragraphs, collapsed context, SEC source links, and local pack links.

If you already know the two packs:

```bash
edgarpack diff \
  --before ./packs/0001045810/0001045810-24-000029 \
  --after ./packs/0001045810/0001045810-25-000023 \
  --format html \
  --out ./reports/nvda-pair.html
```

## 9. Work with pre-IPO S-1 filers

Pre-IPO companies often have no 10-K and no SEC companyfacts. Their numbers live in S-1 tables, so you need built S-1 packs.

```bash
edgarpack build "Cerebras Systems" --form S-1 --last 2
edgarpack query "Cerebras Systems" revenue,gross_profit,net_income,operating_cash_flow,capex,free_cash_flow --period lfy,lfy-1
```

`capital_expenditures` also works as an alias for `capex`:

```bash
edgarpack query "Cerebras Systems" capital_expenditures --period lfy,lfy-1
```

Use `which` to see any discovered operating KPIs and cached S-1 financial metrics:

```bash
edgarpack which "Cerebras Systems"
```

For the full registration chain:

```bash
edgarpack timeline \
  --series registration \
  --cik 0002021728 \
  --packs ./packs \
  --format html \
  --out ./reports/cerebras-s1
```

That writes an `index.html` plus one pair report per S-1 / S-1-A / 424B transition. Start at the index. Click into the pair reports with the highest change intensity.

## 10. The strongest first workflow

If you want to get the most out of EdgarPack on a new company, run this loop:

```bash
# 1. Pull the headline numbers with citations.
edgarpack query FIG revenue,net_income,gross_margin,free_cash_flow --period lfy

# 2. Build filings so you have clean source material.
edgarpack build FIG --form 10-K --last 3

# 3. Ask what company-specific KPIs exist.
edgarpack which FIG

# 4. Compare against peers.
edgarpack comps FIG ADBE MDB --metrics revenue,gross_margin,free_cash_flow --period lfy

# 5. Inspect disclosure changes when you have at least two filings.
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html

# 6. Give another tool structured output instead of a terminal table.
edgarpack query FIG revenue,gross_margin,free_cash_flow --period lfy --format json-full
```

That loop gives you cited values, cleaned filings, issuer-specific KPIs, peer context, disclosure changes, and machine-readable output.

The diff example uses NVIDIA because it has enough 10-K history for a useful report. Swap in your company once you have at least two local packs for the same form.

## 11. Where to go next

- [`WORKFLOWS.md`](WORKFLOWS.md): practical recipes for common research jobs.
- [`QUERY.md`](QUERY.md): metrics, period selectors, citations, JSON formats, derived metrics.
- [`OBSERVATORY.md`](OBSERVATORY.md): filing diffs, HTML reports, registration timelines.
- [`TESTING.md`](TESTING.md): how to validate local changes.
- [`learn/README.md`](learn/README.md): code-level trails for engineers and agents.
