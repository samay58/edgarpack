# Getting Started

This is the fastest path from zero to useful EdgarPack output.

EdgarPack does two jobs:

1. It turns filings into clean local packs: markdown, sections, hashes, citations, and optional chunks.
2. It answers financial questions from primary documents with citations, instead of asking you to trust a black-box summary.

If you only remember one thing: use `query` when you want a number, use `build` when you want the filing as clean source material, use `which` when you want company-specific KPIs, and use `diff` when you want to know what changed.

## 1. Install and set your SEC user agent

```bash
pip install edgarpack

# SEC requires this on every request.
export EDGARPACK_USER_AGENT="Your Name your.email@example.com"

# Optional, but useful when you want a predictable cache location.
export EDGARPACK_CACHE_DIR="$HOME/.edgarpack/cache"
```

For local development in this repo:

```bash
uv pip install -e ".[dev,china]"
```

## 2. Ask one cited financial question

```bash
edgarpack query NVDA revenue --period ltm
```

You should see a value plus a citation marker. For LTM revenue, EdgarPack computes the number from three filings:

```text
LTM = most recent year-to-date quarter + latest fiscal year - prior-year matching quarter
```

The point is not just the answer. The point is that the output tells you which filings it used.

Useful variations:

```bash
# Multiple metrics in one run
edgarpack query NVDA revenue,net_income,gross_margin --period ltm

# Three-year view
edgarpack query NVDA revenue,net_income,gross_margin --period lfy,lfy-1,lfy-2

# Analyst-style preset
edgarpack query NVDA --preset perf --period lfy,lfy-1,lfy-2

# More provenance in the terminal
edgarpack query NVDA revenue --period ltm --audit

# Machine-readable output
edgarpack query NVDA revenue --period ltm --format json-full
```

Company input is forgiving: ticker, CIK, and company name all work.

```bash
edgarpack query 0001045810 revenue
edgarpack query "NVIDIA" revenue
edgarpack query "apple inc" revenue
```

## 3. Compare companies

Use `comps` for SEC-to-SEC comps:

```bash
edgarpack comps NVDA AMD INTC --metrics revenue,net_income,ebitda --period ltm
```

Use `compare` when you want the cross-market path and currency normalization:

```bash
edgarpack compare NVDA BIDU BABA --metrics revenue,gross_margin --period lfy --currency usd
```

Read the period header. If fiscal years differ, EdgarPack says so instead of pretending every column is directly comparable.

## 4. Build a filing pack

`query` can use SEC companyfacts directly. `build` is for when you want the filing itself as clean local source material.

```bash
edgarpack build NVDA --form 10-K
```

That writes a pack under `packs/<CIK>/<accession>/`:

```text
filing.full.md       # full polished markdown
sections/*.md        # one file per detected section
manifest.json        # filing metadata, section offsets, hashes
llms.txt             # compact index for LLM/tool use
optional/            # chunks.ndjson and xbrl.json when requested
```

Build more history when you want timelines, `which`, or local search to have enough context:

```bash
edgarpack build NVDA --form 10-K --last 3
edgarpack build META --accession 0001326801-19-000009
edgarpack list "NVIDIA" --form 10-K --limit 10
```

## 5. Find the KPIs a company actually discloses

Some metrics are not standard GAAP/XBRL concepts. Figma may disclose paid seats. A SaaS company may disclose ARR or NRR. A marketplace may disclose GMV. `which` answers: what does this company actually talk about in its filings?

First build packs:

```bash
edgarpack build FIG --form 10-K --last 3
```

Then ask:

```bash
edgarpack which FIG
```

The first run may use an LLM scan over MD&A sections. The result is cached by accession, so later runs are cheap. Once a KPI is discovered, you can query it by slug:

```bash
edgarpack query FIG paid_seats --period lfy
```

## 6. Review what changed between filings

For quick triage:

```bash
edgarpack diff --ticker NVDA --form 10-K
```

For a real reading surface:

```bash
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

Open the generated HTML file in your browser. It is static and local. It shows changed sections, changed paragraphs, collapsed context, SEC source links, and local pack links.

If you already know the two packs:

```bash
edgarpack diff \
  --before ./packs/0001045810/0001045810-24-000029 \
  --after ./packs/0001045810/0001045810-25-000023 \
  --format html \
  --out ./reports/nvda-pair.html
```

## 7. Work with pre-IPO S-1 filers

Pre-IPO companies often have no 10-K and no SEC companyfacts. Their numbers live in S-1 tables.

```bash
edgarpack build "Cerebras Systems" --form S-1 --last 2
edgarpack query "Cerebras Systems" revenue --period lfy,lfy-1
```

For the filing chain:

```bash
edgarpack timeline \
  --series registration \
  --cik 0002021728 \
  --packs ./packs \
  --format html \
  --out ./reports/cerebras-s1
```

That writes an `index.html` plus one pair report per S-1 / S-1-A / 424B transition. This is the best way to inspect how the registration statement changed without reading every draft from scratch.

Some S-1 financial table shapes are deterministic. Others require `ANTHROPIC_API_KEY` for extraction. If EdgarPack cannot extract a supported table, it should return missing data, not stale numbers from an older filing.

## 8. Where to go next

- [`WORKFLOWS.md`](WORKFLOWS.md): practical recipes for common research jobs.
- [`QUERY.md`](QUERY.md): metrics, period selectors, citations, JSON formats, derived metrics.
- [`OBSERVATORY.md`](OBSERVATORY.md): filing diffs, HTML reports, registration timelines.
- [`learn/README.md`](learn/README.md): code-level trails for engineers and agents.
