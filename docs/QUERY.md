# Query Layer

EdgarPack's query system pulls financial metrics directly from SEC EDGAR's XBRL data, resolves the right GAAP/IFRS concept for each company, and returns values with full citation provenance. Every number traces back to a specific filing, accession number, and SEC URL.

## Architecture

```
Ticker/CIK
  -> resolve_ticker()          # SEC company search
  -> fetch_company_facts()     # XBRL companyfacts JSON
  -> resolve_concept()         # Map "revenue" to the GAAP tag this company uses
  -> select_period()           # Pick LFY, MRQ, LTM, or series
  -> CitedValue / DerivedValue # Every value carries its provenance
```

Single-company queries go through `financials()`. Multi-company comparisons use `comps()`, which runs queries in parallel via `asyncio.gather`.

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

# Full JSON with all provenance fields
edgarpack query NVDA revenue --format json-full
```

### Comparisons

```bash
# Side-by-side table
edgarpack comps NVDA AAPL MSFT --metrics revenue,net_income,gross_margin

# Lean JSON output
edgarpack comps NVDA AAPL --metrics revenue,eps_diluted --format json

# Different period
edgarpack comps NVDA AMD --metrics revenue --period ltm
```

## Period Selectors

| Selector | Meaning | Use Case |
|----------|---------|----------|
| `lfy` | Last fiscal year (most recent 10-K/20-F) | Annual comparisons, default |
| `mrq` | Most recent quarter (standalone 3-month) | Latest quarterly performance |
| `mrp` | Most recent period (whatever was filed last) | Freshest available data point |
| `ltm` | Last twelve months (trailing) | Apples-to-apples comparison across fiscal calendars |
| `annual:N` | Last N fiscal years | Revenue trends, multi-year analysis |
| `quarterly:N` | Last N quarters (standalone) | Quarterly trend analysis |

### LTM Methodology

For duration metrics (P&L, cash flow):

```
LTM = MRP_cumulative + LFY_annual - MRP_prior_year_cumulative
```

Where MRP is the most recent quarterly cumulative value, LFY is the last full fiscal year, and MRP_prior is the same quarter from the prior fiscal year. When the MRP is Q4/FY, LTM returns it directly (no formula needed). For Q1, cumulative and standalone are identical, so the formula still works.

For instant metrics (balance sheet): LTM returns the most recent reported value.

## Concept Resolution

Different companies use different XBRL tags for the same economic concept. Apple reports revenue as `RevenueFromContractWithCustomerExcludingAssessedTax`, NVIDIA uses `Revenues`. The concept resolver handles this by:

1. Looking up the metric name in `METRIC_MAP` to get a priority-ordered list of candidate GAAP concepts
2. Checking which concepts exist in the company's `companyfacts` data
3. Scoring each by recency (highest fiscal year among annual entries wins)
4. Falling back to `ifrs-full` taxonomy for non-US filers (20-F) if `us-gaap` has no matches

This means `edgarpack query AAPL revenue` and `edgarpack query NVDA revenue` both work correctly despite the companies using different XBRL tags.

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

Cross-year validation: if the numerator and denominator come from different fiscal years (stale data for one concept), the derived metric returns `None` rather than producing a misleading ratio.

Division by zero: if the denominator is zero, the result is `None`.

Recursive derivation: EBITDA resolves its components (operating_income, depreciation_amortization) independently, so a company missing D&A data gets `None` for EBITDA rather than a crash.

## JSON Output Formats

### Lean (`--format json`)

Optimized for LLM consumption. Deduplicates filings, auto-includes component metrics for derived values, and includes a permalink for reproducibility.

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
      "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000001/0001045810-25-000001-index.htm"
    }
  },
  "metrics": {
    "revenue": {
      "value": 60922000000,
      "unit": "USD",
      "concept": "Revenues",
      "period": "2024-01-29/2025-01-26",
      "accession": "0001045810-25-000001"
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

Filing URLs point to the SEC EDGAR filing detail page (`{accession}-index.htm`), which shows company name, form type, filing date, and links to all filing documents. This is more useful than the raw directory listing.

The `permalink` field in JSON output provides the exact CLI command to reproduce the query.

## Metric Reference

### Income Statement
`revenue`, `cost_of_revenue`, `gross_profit`, `operating_income`, `net_income`, `eps_basic`, `eps_diluted`, `rd_expense`, `sga_expense`, `ebitda`*, `depreciation_amortization`

### Balance Sheet
`total_assets`, `current_assets`, `total_liabilities`, `current_liabilities`, `stockholders_equity`, `cash`, `total_debt`, `inventory`, `accounts_receivable`, `accounts_payable`, `working_capital`*

### Cash Flow
`operating_cash_flow`, `capex`, `free_cash_flow`*

### Per Share
`shares_outstanding`, `shares_diluted`, `dividends_per_share`

### Ratios
`gross_margin`*, `operating_margin`*, `net_margin`*, `roe`*, `roa`*, `current_ratio`*, `debt_to_equity`*

\* = derived metric (computed from components)

## What This System Is Good At

**Citation provenance**: every value traces to a filing, accession, and URL. No black-box estimates.

**Cross-company normalization**: handles the XBRL concept zoo (20+ revenue tags across filers) so you can compare Apple and NVIDIA without knowing their specific tags.

**LLM-friendly output**: lean JSON avoids repeating filing metadata across metrics, auto-includes component values, and keeps token counts low.

**Zero external dependencies**: uses only stdlib HTTP, pydantic for validation, and tiktoken for counting. Runs in sandboxed/serverless environments.
