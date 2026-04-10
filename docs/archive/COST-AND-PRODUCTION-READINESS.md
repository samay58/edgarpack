# Cost Model and Production Readiness Analysis

Last updated: 2026-02-17

## Request Flow Per Query Type

### Single query (`edgarpack query NVDA revenue`)

| Step | Endpoint | Cache TTL | Cold Size |
|------|----------|-----------|-----------|
| 1. Resolve ticker | `sec.gov/files/company_tickers.json` | 24h | ~800KB |
| 2. Fetch companyfacts | `data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` | 24h | 2-5MB |
| 3. Compute | Local: concept lookup, period selection, arithmetic | N/A | 0 |

Cold cache: **2 HTTP requests**, ~3-6MB bandwidth
Warm cache: **0 HTTP requests**, 0 bandwidth

### Comps query (`edgarpack comps NVDA AMD INTC AVGO --metrics revenue,net_income`)

| Step | Requests | Notes |
|------|----------|-------|
| Tickers lookup | 1 | Shared across all companies (same URL = same cache key) |
| Companyfacts | N (one per company) | Parallel via asyncio.gather, rate-limited to 10 req/s |
| Compute | 0 | All local |

Cold cache for 4 companies: **5 HTTP requests**, ~13-21MB bandwidth
Warm cache: **0 requests**
Mixed (tickers cached, one new company): **1 request**

### Observed companyfacts sizes from cache

| Company | CIK | Cached Size |
|---------|-----|-------------|
| NVIDIA | 0001045810 | 4.2MB |
| AMD | 0000002488 | 3.9MB |
| Intel (050863) | 0000050863 | 4.6MB |
| C3.ai (1730168) | 0001730168 | 2.4MB |

Average: ~3.8MB per company. Apple and other mega-filers will be larger (10-15MB). Young companies will be smaller (500KB-2MB).

## Cost to Serve

### SEC EDGAR API: $0

Free public API. No auth tokens, no billing, no usage tiers. The only constraint is the rate limit (10 req/s per User-Agent) and a required `User-Agent` header identifying who you are.

### Compute per query: negligible

The work is: parse JSON, look up a dict, do arithmetic, format output. Sub-10ms on any modern CPU after cache hit. Even on cold cache, the compute portion is <50ms; the rest is network I/O.

### Bandwidth

| Scenario | Bandwidth per query |
|----------|-------------------|
| Single company, warm cache | 0 |
| Single company, cold cache | ~4MB |
| 4-company comps, warm | 0 |
| 4-company comps, cold | ~16MB |
| S&P 500 pre-warm (one-time) | ~1.9GB |

At moderate scale (1000 queries/day, mostly cache hits): a few GB/month at most.

### Storage (disk cache)

Current cache for ~4 companies + associated filings: 46MB. At S&P 500 scale: ~1.9GB. At full SEC coverage (~10K active filers): ~38GB. Trivial by modern standards.

### Downstream token processing: the variable cost

If you feed query output into any token-priced text system, this is where variable cost appears.
A single `QueryResult` with 5 metrics is ~500-1000 tokens in JSON format.
A 4-company comps table with 5 metrics is ~2000-4000 tokens.

At a reference price of $3 per million input tokens, a 4-company comps query costs about $0.006-0.012 downstream.
The EdgarPack query itself is free.

## Rate Limit: The Hard Constraint

SEC enforces **10 requests per second** per source IP / User-Agent combination. This is the binding constraint at scale.

### Throughput math

| Scenario | Requests needed | Time at 10 req/s |
|----------|----------------|-------------------|
| 1 company, cold | 2 | 0.2s |
| 4 companies, cold | 5 | 0.5s |
| 20 companies, cold | 21 | 2.1s |
| S&P 500 pre-warm | 501 | 50s |

With warm cache (the steady state): 0 requests, instant response.

### The multi-tenant problem

The 10 req/s limit is **global per IP**. If 10 users simultaneously request data for companies not in cache, they're all competing for the same 10 req/s budget. The current rate limiter is per-process; it has no visibility into what other processes on the same machine (or other machines behind the same IP) are doing.

This is the single biggest production gap.

## Production Readiness Assessment

### What works today

- Correct financial data extraction with full citation provenance
- GAAP concept fallback logic (handles different reporting tags across companies)
- LTM calculation using standard methodology
- Aggressive disk caching (24h TTL, SHA256-keyed)
- SEC-compliant rate limiting (per-process)
- Parallel company fetching within rate limit
- Graceful degradation (missing metrics return None, failed companies return empty)
- Deterministic output (same input = same result within cache window)

### What's missing for production

**P0 (must have)**

1. **Shared rate limiter.** The per-process token bucket doesn't work with multiple instances. Need a distributed rate limiter (Redis-based, or a centralized fetcher service) to stay within SEC's 10 req/s.

2. **Shared cache layer.** Disk cache is per-machine. A second instance or a cold deploy re-fetches everything. Need Redis or S3-backed cache so all instances share warmth.

3. **HTTP API layer.** It's a CLI tool. Need a FastAPI/Starlette wrapper to serve over HTTP. Straightforward to add since all the logic is already async.

**P1 (should have)**

4. **Cache warming job.** A nightly cron that pre-fetches companyfacts for the S&P 500 (or whatever your coverage universe is). Cost: 501 requests = 50 seconds. This makes steady-state queries instant.

5. **Ticker map singleton.** The ticker map is re-parsed from cache on every call. In a long-running server, it should be an in-memory singleton refreshed on a timer.

6. **Circuit breaker.** If SEC returns 5xx or times out, stop hammering and fail fast. The current retry logic (3 attempts with backoff) is fine for CLI use but will burn rate limit budget under load.

7. **Structured logging and metrics.** Cache hit rate, request latency, SEC error rate, concept resolution miss rate. Without these you're flying blind.

**P2 (nice to have)**

8. **Streaming/partial JSON parse.** Apple's companyfacts is 10-15MB. Loading it all into memory is fine for CLI, less so for a high-concurrency server. Could stream-parse to extract only the needed concepts.

9. **Background cache refresh.** Serve stale data while refreshing in the background, instead of blocking on TTL expiry.

10. **Coverage reporting.** Which metrics are available for which companies? The concept fallback list covers the common cases, but some companies use non-standard tags that aren't mapped.

### What's NOT a concern

- **SEC API cost**: $0, always.
- **SEC API uptime**: SEC EDGAR has excellent availability. Multi-hour outages are rare.
- **Data freshness**: Companyfacts updates within hours of filings. 24h cache TTL is fine for comps analysis (you're not doing HFT with SEC data).
- **Legal/TOS**: SEC data is public domain. Their fair access policy asks for reasonable rate limiting, which we implement. Commercial use is explicitly allowed.
- **Compute cost**: The query logic is trivially cheap. A $5/month VM could serve thousands of queries per day.

## Cost Summary Table

| Component | Cost | Notes |
|-----------|------|-------|
| SEC API | $0 | Free forever |
| Compute | ~$20-50/month | Small VM or Lambda |
| Cache storage | ~$1-5/month | Redis or S3, <2GB for S&P 500 |
| Bandwidth | ~$1-5/month | Mostly cache hits in steady state |
| **Total infrastructure** | **~$25-60/month** | |
| Downstream token processing | $0.006-0.012/query | Variable cost if routed into token-priced systems |

Infrastructure cost is mostly fixed. The marginal cost of an extra query is $0 on cache hit, then rises only if downstream systems charge by token.
SEC data is free.

## Capabilities and Limitations

An honest assessment of what the query layer can and cannot do for investment banking-grade analysis.

### What works today

**Period selectors (CLI + Python API):**

| Selector | Description | Status |
|----------|-------------|--------|
| `lfy` | Last Fiscal Year (most recent 10-K annual) | Works |
| `mrq` | Most Recent Quarter (standalone 3-month value) | Works (fixed: now filters by duration to avoid cumulative YTD) |
| `mrp` | Most Recent Period (whatever was filed last) | Works |
| `ltm` | Last Twelve Months (MRP_cumulative + LFY - MRP_prior_cumulative) | Works (fixed: now picks cumulative values for the formula) |
| `ltm-1` | Prior-Year Last Twelve Months (same formula, one-year-shifted anchor) | Works (with graceful fallback to anchored reported value when shifted history is incomplete) |
| `annual:N` | Last N fiscal years | Works |
| `quarterly:N` | Last N standalone quarters | Works (fixed: same duration filtering as MRQ) |

**Metrics (33 total across 5 categories):**

- Income Statement: revenue, cost_of_revenue, gross_profit, operating_income, net_income, eps_basic, eps_diluted, rd_expense, sga_expense, depreciation_amortization
- Balance Sheet: total_assets, current_assets, total_liabilities, current_liabilities, stockholders_equity, cash, total_debt, inventory, accounts_receivable, accounts_payable
- Cash Flow: operating_cash_flow, capex
- Derived (computed from other metrics): ebitda, free_cash_flow, working_capital, gross_margin, operating_margin, net_margin, roe, roa, current_ratio, debt_to_equity
- Per Share: shares_outstanding, shares_diluted, dividends_per_share

**Concept fallback.** Revenue alone has 6 GAAP tag variants across different filers. The system tries each in priority order until it finds data.

**Output modes:** `--format table` (human-readable with citations footer) and `--format json` (full provenance on every value including filing URL, accession number, concept, and period).

### What's NOT possible with this data source

These are fundamental constraints of the SEC companyfacts API, not bugs.

**Non-GAAP metrics: not available.** SEC companyfacts contains only GAAP-tagged XBRL data. Adjusted EBITDA, Non-GAAP EPS, Adjusted Operating Income, and stock-based compensation add-backs appear in narrative filing text and supplemental tables, not in structured companyfacts data. This is the biggest gap for IB-grade comps. The data is present in filing markdown, but the query layer does not expose a programmatic extractor for it.

**Market data: not available.** SEC provides no share prices. Without price data, you cannot compute market cap, enterprise value, EV/Revenue, EV/EBITDA, P/E ratio, or any valuation multiple. These are table stakes for comps.

**Segment data: not available through this API.** Revenue by geography, by product line, by business unit. Some segment data is XBRL-tagged (especially after the SEC's 2023 segment reporting rules), but the companyfacts API doesn't expose it cleanly. Accessing it would require parsing full XBRL instance documents.

**Forward estimates and consensus: not available.** SEC only has historical actuals. No analyst estimates, no consensus, no guidance. These require a third-party provider (FactSet, Bloomberg, Visible Alpha).

**Company-specific KPIs: mostly not available.** Monthly Active Users, Annual Recurring Revenue, Net Revenue Retention, Remaining Performance Obligations. Some (like RPO) are XBRL-tagged and theoretically reachable, but the concept map doesn't cover them. The system is extensible here (you can add concepts), but it requires knowing the exact XBRL tag name per company, which varies.

### Cumulative vs. Standalone Quarter Handling

SEC companyfacts frequently contains both cumulative YTD and standalone 3-month entries for the same quarter. For example, NVIDIA's Q3 FY2025 has:

| Entry | Start | End | Duration | Value |
|-------|-------|-----|----------|-------|
| 9-month cumulative | 2025-01-27 | 2025-10-26 | 272 days | $147.8B |
| 3-month standalone | 2025-07-28 | 2025-10-26 | 90 days | $57.0B |

Both carry `fp=Q3, form=10-Q`. The query layer handles this by filtering on duration:

- **MRQ / quarterly:N**: Picks entries with duration <= 100 days (standalone). The 100-day threshold accommodates fiscal quarters that aren't exactly 90 days (4-4-5 calendars, etc.).
- **LTM / LTM-1**: Picks entries with the longest duration (cumulative YTD), since the formula `MRP + LFY - MRP_prior` requires cumulative values.
- **Q1 values**: Cumulative and standalone are identical for Q1 (both ~90 days from fiscal year start), so no ambiguity exists.
