# Query Layer

EdgarPack's query system pulls financial metrics directly from SEC EDGAR's XBRL data, resolves the right GAAP/IFRS concept for each company, and returns values with full citation provenance. Every number traces back to a specific filing, accession number, and SEC URL.

## Architecture

```
Ticker/CIK
  -> resolve_ticker()          # SEC company search
  -> fetch_company_facts()     # XBRL companyfacts JSON
  -> resolve_concept()         # Map "revenue" to the GAAP tag this company uses
  -> select_period()           # Pick LFY, MRQ, MRP, LTM/LTM-1, or series
  -> CitedValue / DerivedValue # Every value carries its provenance
```

Single-company queries go through `financials()`. Multi-company comparisons use `comps()`, which runs queries in parallel via `asyncio.gather`.

## Design Choices

Metric concept mappings live in code, not config files, so changes get reviewed with the rest of query logic.

Missing or invalid inputs return `None` instead of guesses. Period math is explicit (especially LTM) so every component can be cited and checked. Filing metadata ships on every value object by default. Audit trails are not optional.

## CLI Reference

### Single company

```bash
# Last fiscal year revenue
edgarpack query NVDA revenue

# Multiple metrics
edgarpack query AAPL revenue,net_income,gross_margin

# All metrics (omit the metric argument)
edgarpack query MSFT

# LTM with lean JSON output
edgarpack query NVDA revenue --period ltm --format json
# Prior-year trailing twelve months
edgarpack query NVDA revenue --period ltm-1 --format json

# Structured LTM audit block in table output
edgarpack query NVDA revenue --period ltm --audit

# Control citation placement and link verbosity
edgarpack query NVDA revenue --citations inline --show-links primary

# Full JSON with all provenance fields
edgarpack query NVDA revenue --format json-full

# Reject self-healed mappings, use only hardcoded concepts
edgarpack query NVDA revenue --strict
```

### Comparisons

```bash
# Side-by-side table
edgarpack comps NVDA AAPL MSFT --metrics revenue,net_income,gross_margin

# Lean JSON output
edgarpack comps NVDA AAPL --metrics revenue,eps_diluted --format json

# Different period
edgarpack comps NVDA AMD --metrics revenue --period ltm
edgarpack comps NVDA AMD --metrics revenue --period ltm-1

# Table output with explicit audit/citation controls
edgarpack comps NVDA AMD --metrics revenue,gross_margin --period ltm --audit
```

### Multi-period grid (single company)

`query` accepts a comma-separated list of scalar period selectors to render a
metrics x periods grid. Rows are metrics in the caller's order. Columns are
the periods, newest on the LEFT (matches the order typed on the CLI).

```bash
# Three-year annual performance view
edgarpack query NVDA revenue,net_income,gross_margin --period lfy,lfy-1,lfy-2

# Trailing windows
edgarpack query NVDA revenue --period ltm,ltm-1,ltm-2

# Same quarter, three years back (YoY anchor)
edgarpack query NVDA revenue --period mrq,mrq-1,mrq-2

# Mix (allowed: all scalar selectors)
edgarpack query NVDA revenue --period lfy,ltm,mrq
```

Rules for the CSV form:

- Scalar selectors only. `annual:N` and `quarterly:N` are series selectors and
  cannot be combined with anything else.
- `lfy-0`, `ltm-0`, `mrq-0` canonicalize to `lfy` / `ltm` / `mrq`. Duplicates
  are removed while preserving first-seen order.
- Default `--citations` becomes `footer` for multi-period grids (inline markers
  get noisy in a table). Pass `--citations inline` or `off` to override.

### Preset metric packs

`--preset perf` expands to a curated analyst panel. Combines with `--metrics`
(preset first, explicit metrics appended, duplicates removed):

```bash
edgarpack query NVDA --preset perf --period lfy,lfy-1,lfy-2

# Preset plus extras
edgarpack query NVDA --preset perf --metrics fcf_to_net_income,rule_of_40
```

`perf` contents: `revenue`, `revenue_growth_yoy`, `revenue_cagr_3y`,
`gross_margin`, `operating_margin`, `net_margin`, `r_and_d_intensity`,
`sga_intensity`, `fcf_margin`.

## Period Selectors

| Selector | Meaning | Use Case |
|----------|---------|----------|
| `lfy` | Last fiscal year (most recent 10-K/20-F) | Annual comparisons, default |
| `lfy-N` | Fiscal year N positions back from the latest | Multi-year annual history |
| `mrq` | Most recent quarter (standalone 3-month) | Latest quarterly performance |
| `mrq-N` | Same fiscal quarter, N years back (YoY anchor) | Year-over-year quarterly comparison |
| `mrp` | Most recent period (whatever was filed last) | Freshest available data point |
| `ltm` | Last twelve months (trailing) | Apples-to-apples comparison across fiscal calendars |
| `ltm-N` | Trailing twelve months, N years back | TTM growth baselines; `ltm-1` is the one-year-back window |
| `annual:N` | Last N fiscal years | Revenue trends, multi-year analysis |
| `quarterly:N` | Last N quarters (standalone) | Quarterly trend analysis |

The CSV form on `--period` (``lfy,lfy-1,lfy-2``) accepts any scalar selector
above and renders a metrics x periods grid. Staleness is auto-skipped for any
offset selector with N >= 1 (`lfy-N`, `ltm-N`, `mrq-N`).

### LTM Methodology

For duration metrics (P&L, cash flow):

```
LTM = MRP_cumulative + LFY_annual - MRP_prior_year_cumulative
```

Where MRP is the most recent quarterly cumulative value, LFY is the last full fiscal year, and MRP_prior is the same quarter from the prior fiscal year. When the MRP is Q4/FY, `ltm` returns it directly (no formula needed). For Q1, cumulative and standalone are identical, so the formula still works.

`ltm-1` uses the same formula, but shifts the quarter anchor one fiscal year back before computing the window. Unlike `ltm`, `ltm-1` does not short-circuit on a shifted Q4/FY anchor when full formula components are available.

For instant metrics (balance sheet): both `ltm` and `ltm-1` return the most recent reported value.

For per-share metrics (for example `eps_basic`, `eps_diluted`): `ltm` and `ltm-1` use annual fallbacks (`LFY` / `LFY-1`) instead of additive LTM math, because per-share values are non-additive across periods.

### LTM-1 Fallback Behavior

`ltm-1` is anchored one fiscal year behind the latest quarter. If SEC history is missing required prior-year components for the full formula window, the selector degrades gracefully to the best anchored reported value instead of raising an error or fabricating values.

## Concept Resolution

Different companies use different XBRL tags for the same economic concept. Apple reports revenue as `RevenueFromContractWithCustomerExcludingAssessedTax`, NVIDIA uses `Revenues`. The concept resolver handles this by:

1. Looking up the metric name in `METRIC_MAP` to get a priority-ordered list of candidate GAAP concepts
2. Checking which concepts exist in the company's `companyfacts` data
3. Scoring each by recency (highest fiscal year among annual entries wins)
4. Falling back to `ifrs-full` taxonomy for non-US filers (20-F) if `us-gaap` has no matches

This means `edgarpack query AAPL revenue` and `edgarpack query NVDA revenue` both work correctly despite the companies using different XBRL tags.

## Data Quality Guards

Three guards run on every metric to filter out misleading values before they reach the caller.

### Staleness Guard

Values whose fiscal year is too far behind the current calendar year are rejected as stale and returned as `None`. The default threshold is 2 fiscal years. `ltm-1` uses 3 years (it naturally references one year back). Series selectors (`annual:N`, `quarterly:N`) skip the check entirely since the caller explicitly requests historical data.

Staleness applies to both direct metrics and derived-metric components. If any component of a derived metric is stale, the whole derived value is `None`.

### Segment Filtering

SEC companyfacts sometimes contains both consolidated and segment-level entries for the same filing period. Without filtering, double-counted segment values can bleed into results.

The filter groups entries by `(accession, fy, fp, start, end)` and, when duplicates exist, prefers entries that carry a `frame` field (SEC's marker for consolidated/aggregated data). When no entry has a frame, the largest absolute value is kept as a conservative fallback.

### Concept Scope Warnings

Some XBRL concepts are broader or narrower than what the metric name implies. When the concept resolver lands on one of these, a scope warning is appended to the value's `warnings` list. Current warnings cover:

- `CostOfGoodsAndServicesSold` (may be broader than cost of revenue, affecting gross profit)
- `CashCashEquivalentsAndShortTermInvestments` (overstates pure cash position)
- `LongTermDebtAndCapitalLeaseObligations` (includes lease obligations alongside financial debt)
- `LiabilitiesAndStockholdersEquity` (combined total, not pure liabilities)

Scope warnings propagate to derived metrics when a flagged concept is used as a component.

## Derived Metrics

Some metrics are computed from other metrics rather than read directly from XBRL:

| Metric | Formula | Unit |
|--------|---------|------|
| `gross_margin` | gross_profit / revenue | ratio |
| `operating_margin` | operating_income / revenue | ratio |
| `net_margin` | net_income / revenue | ratio |
| `ebitda` | operating_income + depreciation_amortization | currency |
| `free_cash_flow` | operating_cash_flow - capex | currency |
| `working_capital` | current_assets - current_liabilities | currency |
| `roe` | net_income / stockholders_equity | ratio |
| `roa` | net_income / total_assets | ratio |
| `current_ratio` | current_assets / current_liabilities | ratio |
| `debt_to_equity` | total_debt / stockholders_equity | ratio |

### Growth, trend, intensity, and quality

| Metric | Formula | Unit |
|--------|---------|------|
| `revenue_growth_yoy` | revenue / revenue_prev1 - 1 | ratio |
| `net_income_growth_yoy` | net_income / net_income_prev1 - 1 | ratio |
| `operating_income_growth_yoy` | operating_income / operating_income_prev1 - 1 | ratio |
| `eps_growth_yoy` | eps_diluted / eps_diluted_prev1 - 1 | ratio |
| `gross_margin_trend` | gross_margin - gross_margin_prev1 | ratio |
| `operating_margin_trend` | operating_margin - operating_margin_prev1 | ratio |
| `net_margin_trend` | net_margin - net_margin_prev1 | ratio |
| `r_and_d_intensity` | rd_expense / revenue | ratio |
| `sga_intensity` | sga_expense / revenue | ratio |
| `sm_intensity` | sm_expense / revenue | ratio (best-effort) |
| `capex_intensity` | capex / revenue | ratio |
| `fcf_to_net_income` | free_cash_flow / net_income | ratio |
| `rule_of_40` | revenue_growth_yoy + fcf_margin | ratio |

`sm_expense` resolves `SellingAndMarketingExpense`, `MarketingExpense`, and
related tags. It returns `None` for filers that only tag aggregate SG&A; no
silent substitution.

### CAGR

| Metric | Formula | Unit |
|--------|---------|------|
| `revenue_cagr_3y` / `revenue_cagr_5y` | `(revenue / revenue[-N]) ^ (1/N) - 1` | ratio |
| `net_income_cagr_3y` / `net_income_cagr_5y` | `(net_income / net_income[-N]) ^ (1/N) - 1` | ratio |
| `eps_diluted_cagr_3y` / `eps_diluted_cagr_5y` | `(eps_diluted / eps_diluted[-N]) ^ (1/N) - 1` | ratio |
| `fcf_cagr_3y` / `fcf_cagr_5y` | `(fcf / fcf[-N]) ^ (1/N) - 1` | ratio |

CAGR metrics are FY-anchored regardless of the parent period. When `--period`
is `ltm` / `ltm-N` / `mrq` / `mrq-N`, the CAGR endpoints substitute to the
nearest fiscal-year equivalent (`ltm` -> `lfy`, `ltm-2` -> `lfy-2`, etc.) so
the math stays over annual values. CAGR returns `None` when either endpoint
is missing, the starting value is zero, or the signs flip across the window
(crossing zero makes CAGR meaningless).

Cross-year validation: if the numerator and denominator come from different fiscal years (stale data for one concept), the derived metric returns `None` rather than producing a misleading ratio.

Division by zero: if the denominator is zero, the result is `None`.

Recursive derivation: EBITDA resolves its components (operating_income, depreciation_amortization) independently, so a company missing D&A data gets `None` for EBITDA rather than a crash.

## JSON Output Formats

### Lean (`--format json`)

Compact output format. It deduplicates filing metadata, auto-includes component metrics for derived values, and includes a permalink for reproducibility.

Additive auditability fields:

- top-level `citations` registry (`C#`)
- top-level `calculations` registry (`D#`, `L#`)
- metric-level `citation_ids`
- derived metric `calculation_id` + `component_citation_ids`
- enriched `ltm_components` metadata (fiscal labels, periods, links, citation IDs)

```json
{
  "company": "NVIDIA CORP",
  "cik": "0001045810",
  "period": "lfy",
  "permalink": "edgarpack query 0001045810 revenue,gross_margin --period lfy",
  "filings": {
    "0001045810-25-000001": {
      "form_type": "10-K",
      "filed": "2025-02-18",
      "fiscal_year": 2025,
      "fiscal_period": "FY",
      "url": "https://www.sec.gov/Archives/edgar/data/1045810/...-index.htm",
      "viewer_url": "https://www.sec.gov/ix?doc=/Archives/edgar/data/1045810/.../nvda-20250126.htm"
    }
  },
  "metrics": {
    "revenue": {
      "value": 60922000000,
      "unit": "USD",
      "concept": "Revenues",
      "period": "2024-01-29/2025-01-26",
      "accession": "0001045810-25-000001",
      "concept_url": "https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/us-gaap/Revenues.json"
    },
    "gross_margin": {
      "value": 0.7355,
      "unit": "pure",
      "concept": "gross_profit / revenue",
      "period": "2024-01-29/2025-01-26",
      "accession": "0001045810-25-000001",
      "derived": true,
      "formula": "gross_profit / revenue",
      "components": ["gross_profit", "revenue"]
    }
  }
}
```

### Full (`--format json-full`)

Every metric carries its complete provenance: filing URL, citation string, all fields from `CitedValue`. Derived metrics include full component objects. Useful for audit trails and downstream systems that need every field.

## Non-US Filer Support

Companies filing on form 20-F (non-US filers) typically use IFRS taxonomy instead of US-GAAP. The system handles this transparently:

1. Concept resolution tries `us-gaap` first
2. Falls back to `ifrs-full` taxonomy if no GAAP match
3. IFRS-specific concept names (e.g., `Revenue` instead of `Revenues`) are tried first within the IFRS taxonomy
4. Currency unit is preserved from the filing (EUR, GBP, JPY, etc.)
5. Formatting applies the correct currency symbol

## Deep Linking

Every value carries up to five URLs for tracing back to the source. Each tier gives progressively more targeted access to the underlying data.

| URL | What It Points To | Extra API Calls |
|-----|-------------------|-----------------|
| `filing_url` | SEC EDGAR filing detail page (`-index.htm`) | 0 |
| `concept_url` | SEC XBRL companyconcept API (full concept history as JSON) | 0 |
| `viewer_url` | SEC Inline XBRL Viewer with highlighted/clickable tags | 1 (submissions, cached 1hr) |
| `document_url` | Filing HTML scrolled to the concept via `#:~:text=` fragment | 1 (submissions, cached 1hr) |
| `anchor_url` | Filing HTML anchored to stable inline XBRL fact id (`#f-...`) | 1 (submissions + filing HTML, cached) |

`filing_url` is always present. `concept_url` is present for direct XBRL metrics but `None` for derived metrics (formulas like `gross_profit / revenue` have no single concept). `viewer_url` and `document_url` require the filing's `primaryDocument` filename from the SEC submissions API; they degrade to `None` if the submissions call fails.

CLI primary-link preference is explicit:

1. `anchor_url` when fact IDs are available
2. else `viewer_url`
3. else `filing_url`

The `permalink` field in JSON output provides the exact CLI command to reproduce the query.

### How It Works

The submissions API (`data.sec.gov/submissions/CIK{cik}.json`) returns `primaryDocument` filenames for all recent filings. `financials()` calls this once per query, builds a `{accession: primaryDocument}` lookup, and threads it through all period selectors. The call is cached for 1 hour by the same disk cache the rest of the SEC client uses. If it fails, all values still resolve; they just lack `viewer_url` and `document_url`.

The `document_url` uses Chrome/Edge text fragment scrolling (`#:~:text=Net%20Income%20Loss`) by converting the camelCase XBRL concept to a space-separated label.

## Metric Reference

### Income Statement
`revenue`, `cost_of_revenue`, `gross_profit`, `operating_income`, `net_income`, `eps_basic`, `eps_diluted`, `rd_expense`, `sga_expense`, `ebitda`*, `depreciation_amortization`

### Balance Sheet
`total_assets`, `current_assets`, `total_liabilities`, `current_liabilities`, `stockholders_equity`, `cash`, `total_debt`, `short_term_debt`, `marketable_securities`, `inventory`, `accounts_receivable`, `accounts_payable`, `working_capital`*

### EV Bridge
`short_term_debt`, `marketable_securities`, `operating_lease_liabilities`, `noncontrolling_interests`, `preferred_stock`, `equity_method_investments`

### Cash Flow
`operating_cash_flow`, `capex`, `free_cash_flow`*

### Per Share
`shares_outstanding`, `shares_diluted`, `dividends_per_share`

### Ratios
`gross_margin`*, `operating_margin`*, `net_margin`*, `ebitda_margin`*, `fcf_margin`*, `roe`*, `roa`*, `current_ratio`*, `debt_to_equity`*

\* = derived metric (computed from components)

## Self-Heal and Learned Mappings

When a company uses an XBRL concept that is not in the hardcoded `METRIC_MAP`, the query layer can resolve it through a self-heal path: fuzzy matching against available concepts, or LLM-assisted resolution. Successful resolutions are persisted in a `learned_concepts` registry so subsequent queries skip the discovery step.

The `learned` command inspects and manages this registry:

```bash
# List all learned mappings
edgarpack learned list

# Filter by company or metric
edgarpack learned list --cik 0001045810
edgarpack learned list --metric revenue

# Filter by resolution source
edgarpack learned list --source fuzzy
edgarpack learned list --unverified

# Show one mapping in detail
edgarpack learned show 0001045810 revenue

# Promote an unverified mapping to verified
edgarpack learned verify 0001045810 revenue

# Clear mappings
edgarpack learned clear --cik 0001045810
edgarpack learned clear --all
```

The `--strict` flag on `query` and `comps` rejects any value that was resolved through the self-heal path. Only hardcoded `METRIC_MAP` resolutions are returned. Use this when you need guaranteed concept provenance.

## What This System Is Good At

**Citation provenance**: every value traces to a filing, accession, and URL. No black-box estimates.

**Cross-company normalization**: handles the XBRL concept zoo (20+ revenue tags across filers) so you can compare Apple and NVIDIA without knowing their specific tags.

**Compact output**: lean JSON avoids repeating filing metadata across metrics, auto-includes component values, and keeps token counts low.

**Zero external dependencies**: uses only stdlib HTTP, pydantic for validation, and tiktoken for counting. Runs in sandboxed/serverless environments.
