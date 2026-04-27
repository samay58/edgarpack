# KPI Discovery Demo Notes - 2026-04-27

Context: `uv run edgarpack which NVDA` produced a strong cross-year table of NVIDIA operating KPIs from local filing packs. This is worth including in the EdgarPack demo because it shows a primary-document workflow that goes beyond standard financial statement line items.

## What Happened

The command:

```bash
uv run edgarpack which NVDA
```

Resolved NVIDIA to CIK `0001045810`, loaded registered local packs, selected eligible 10-K / 10-Q filings, and ran KPI discovery on the packs with valid manifests.

Observed run shape:

```text
Loading up to 13 registered pack(s)
Running KPI discovery on filing 1/7 ...
Discovery summary: 3 analyzed, 4 skipped (manifest missing; run `edgarpack build <ticker>`)
```

Even with only three valid analyzed filings, the output surfaced a dense table of recurring operating disclosures: CUDA developers, employee counts, workforce mix, renewable energy matched, turnover, TOP500 / Green500 presence, supported applications, RTX AI application counts, and similar non-GAAP / non-XBRL metrics.

## Why It Worked

This was not a generic "ask an LLM about NVIDIA" flow. The LLM pass succeeded because EdgarPack constrained the job tightly:

1. The filings had already been converted from noisy SEC HTML into clean markdown packs.
2. `which` selected only likely KPI-bearing sections such as Item 1 Business, MD&A, segment sections, key metrics, operating data, and key performance sections.
3. The prompt asked for recurring business / operating KPIs, while excluding GAAP line items, one-off numbers, forward-looking targets, competitor figures, and simple GAAP ratios.
4. Every LLM-returned item had to include a verbatim `source_substring`.
5. EdgarPack rejected any row whose source substring did not appear in the selected filing text.
6. Results were normalized into stable slugs, cached by CIK + accession, and aggregated across filings into a period matrix.

The core insight: the LLM did the semantic recognition, but the product value came from clean source material plus a narrow extraction contract plus deterministic validation and aggregation.

## Demo Framing

Use this as a "qualitative KPI discovery" moment:

```bash
uv run edgarpack which NVDA --max-periods 8
```

Then show that a discovered KPI can become queryable:

```bash
uv run edgarpack query NVDA cuda_developers --period lfy
```

Good narrative:

- `query` answers standard financial questions with citations.
- `which` asks what the company itself repeatedly discloses as operating metrics.
- The result is not a model summary. It is a filing-backed KPI inventory.
- Clean packs make the LLM useful because it sees the right source text, not raw SEC markup.
- The hallucination firewall requires a verbatim excerpt before a KPI survives.

## Demo Caveats

- `which` depends on built, registered packs. Missing manifests reduce coverage.
- The first run can be slower because it may run one LLM call per filing.
- Subsequent runs replay from cache unless `--no-cache` is passed.
- Discovery is only as good as the selected sections and the filing's actual disclosures.
- For demo polish, rebuild missing packs before presenting a company.

Suggested prep:

```bash
uv run edgarpack build NVDA --form 10-K --last 4
uv run edgarpack build NVDA --form 10-Q --last 8
uv run edgarpack which NVDA --no-cache --max-periods 8
uv run edgarpack which NVDA --max-periods 8
```

The final command should be the fast cached demo path.

## Other High-Profile Companies To Try

Start with companies that likely disclose operational metrics in prose:

```bash
uv run edgarpack build META --form 10-K --last 4
uv run edgarpack which META --max-periods 8
```

```bash
uv run edgarpack build TSLA --form 10-K --last 4
uv run edgarpack which TSLA --max-periods 8
```

```bash
uv run edgarpack build AMZN --form 10-K --last 4
uv run edgarpack which AMZN --max-periods 8
```

```bash
uv run edgarpack build CRM --form 10-K --last 4
uv run edgarpack which CRM --max-periods 8
```

For structured capture:

```bash
uv run edgarpack which NVDA --format json
```

## One-Line Takeaway

EdgarPack makes the LLM useful by shrinking the search space to clean, cited, section-addressable primary text, then only keeping extracted KPIs that can be tied back to verbatim filing evidence.
