# Chinese AI labs in the public comparison set (design)

Issue: edgarpack-2yg follow-up
Date: 2026-04-14
Status: approved, pre-plan
Reference: builds on `docs/superpowers/specs/2026-04-14-china-query-performance-design.md`

## Problem

The China parity foundation that just merged treats MiniMax as private. It is not. MiniMax and Zhipu both IPO'd on HKEX in early 2026; both are pure-play LLM labs with public financials and rich IPO prospectuses. Other Chinese AI labs (Moonshot, 01.AI, Baichuan, DeepSeek) may also be public; they need verification, not assumption. The CLI today exits with "private company" for MiniMax and "HKEX not yet supported" for Tencent / Meituan. Neither serves the goal of a real, citable, USD-normalized comparison of Chinese AI labs against domestic incumbents.

This spec absorbs the deferred HKEX-extraction follow-up alongside the universe correction. The done-def is a `compare` subcommand that produces a screenshot-quality three-way comp of MiniMax, Zhipu, and Baidu.

## Scope

In scope:

- Universe correction. Drop the `MINIMAX-PRIVATE` placeholder. Add MiniMax and Zhipu with their verified HKEX stock codes. Verify Moonshot, 01.AI, Baichuan, DeepSeek and add the demonstrably public ones.
- HKEX prospectus extraction. Parse the IPO prospectus PDFs to populate `facts.json` per pack. Heuristic regex first, Claude API fallback for misses, on-disk cache for offline CI.
- Lab-relevant metrics in `metric_map.py`: cash burn, runway, R and D intensity, revenue growth, gross margin trend.
- `edgarpack compare` subcommand. Side-by-side table across two or more companies. USD-normalized. Period-footnoted per column. Twitter-shareable artifact.
- Eval harness. Independent golden fixtures from sell-side and press coverage, 1 percent tolerance on line items, exact match on share counts.

Out of scope:

- Annual report ingestion for FY25. Filings do not exist yet; separate task once they do.
- Cross-border `compare` like MiniMax vs Anthropic. Anthropic is private. The framing is intentionally domestic.
- Real-time prospectus refresh automation. v1 downloads PDFs once into the fixtures directory; refresh is a manual script.
- A markdown narrative-report generator beyond a clean `--format markdown` table.

## Universe correction

`universe.toml` loses `MINIMAX-PRIVATE` entirely. New entries land alongside Tencent and Meituan:

```toml
[[companies]]
ticker = "XXXX.HK"            # MiniMax actual code, looked up from HKEX before write
listing = "HKEX"
aliases = ["minimax", "minimax ai"]
hk_stock_code = "0XXXX"

[[companies]]
ticker = "YYYY.HK"            # Zhipu actual code, looked up from HKEX before write
listing = "HKEX"
aliases = ["zhipu", "zhipu ai", "glm", "chatglm"]
hk_stock_code = "0YYYY"
```

Stock codes get filled in from a primary source (HKEX listings page or company IR) before the implementer writes universe.toml. No assumption-based filling.

The four additional candidate labs (Moonshot, 01.AI, Baichuan, DeepSeek) get a single verification task: for each, confirm public listing status from a primary source. If public, add to universe with the same shape. If private, file a follow-up note and skip. The `MINIMAX-was-private` mistake does not repeat.

The `private` field on `CompanySpec` stays in place. Other genuinely private companies will use it. The `MINIMAX-PRIVATE` test in `tests/test_china_identity.py` flips: `test_live_universe_minimax_is_private` becomes `test_minimax_routes_to_hkex` and asserts `private=False`, `source="HKEX"`. The CLI test for the private-company exit path either points at a different genuinely private entry or gets deleted; the model-level test in `test_china_identity.py` already covers the path.

## HKEX prospectus extraction

The new module is `edgarpack/hk/extract.py`. It takes a pack built by `edgarpack/hk/adapter.py` (which already produces sections and chunks from the PDF) and emits a `facts.json` next to `chunks.ndjson`. Shape mirrors the SEC `facts.json` so the query layer does not fork.

Pass 1 is heuristic regex. For each canonical metric in `METRIC_MAP["HKFRS"]`, the extractor scopes regex patterns to the financial-statement sections (`hkex_income_statement`, `hkex_balance_sheet`, `hkex_cash_flow`). Patterns target table-row formats like `Revenue\s+(?:CNY|RMB)\s+([\d,]+)` or `Total\s+revenue.*?(\d{1,3}(?:,\d{3})*)`. Each hit produces a candidate fact with `extraction_method="regex"` plus the matched line label.

Pass 2 is Claude API fallback for metrics still unfilled after Pass 1. Per metric, send a focused prompt: the section text plus an instruction to extract the FY2024 value, return JSON with the number and the line-item label. Cache the response by SHA256 of the tuple `(accession, section_id, metric, prompt_text)` to `data/cache/llm_extract/{cache_key}.json`. The cache commits to the repo so CI runs offline. If a metric still has no value after both passes, log a warning and skip; do not fabricate.

Each fact carries `extraction_method` (`regex` or `learned:llm`). Query output annotates LLM-extracted values the same way the existing SEC self-heal annotates `learned:fuzzy`. Users see when a value came from the LLM path and can drill into the source.

The query path (`edgarpack/query/financials.py`) gains a small branch: when `resolved.source == "HKEX"`, read facts from `tests/fixtures/china_packs/{stock_code}_{fy}/facts.json` instead of calling EDGAR's companyfacts API. Same `CitedValue` shape downstream. FX conversion runs in the formatter as already designed; the CitedValue carries `reporting_currency="CNY"` and `accounting_standard="HKFRS"`.

## Lab-specific metrics

Five new entries land in `CANONICAL_METRICS`:

```python
"cash_burn",                # |operating_cash_flow + capex| when negative; absolute value reported
"runway_months",            # cash_and_equivalents / (cash_burn / 12)
"r_and_d_intensity",        # research_and_development_expense / revenue
"revenue_growth_yoy",       # (revenue_t / revenue_{t-1}) - 1
"gross_margin_trend",       # gross_margin_t - gross_margin_{t-1}
```

The first three need new tag mappings in `METRIC_MAP`. `cash_burn` requires `CashFlowsFromOperatingActivities` and `PaymentsForPropertyPlantAndEquipment` for HKFRS / IFRS, plus the US-GAAP equivalents. `r_and_d_intensity` requires `ResearchAndDevelopmentExpense` (US-GAAP) and `ResearchCostsRecognisedAsExpense` or similar (IFRS / HKFRS).

The two derived metrics (`runway_months`, `revenue_growth_yoy`, `gross_margin_trend`) plug into the existing derivation framework in `edgarpack/query/financials.py::_compute_derived`. New rules in that function consume already-extracted line items.

Counter-pattern note: when `cash_burn` is positive (the company is cash-flow positive), `runway_months` is undefined and returns `n/a` with a footnote `"company is cash-flow positive"`.

## `compare` subcommand

New CLI parser:

```
edgarpack compare COMPANY [COMPANY ...] [--metrics M,M,M] [--period P]
                  [--currency {native,usd,both}] [--format {table,json,markdown}]
```

Defaults:
- Two or more positional companies, no upper bound.
- Default metric set is the lab-relevant subset: `revenue,gross_margin,r_and_d_intensity,operating_income,cash_burn,runway_months,cash_and_equivalents`.
- Default period is each company's latest available filing, footnoted per column.
- Default currency is `both` because the comp's whole point is cross-currency normalization.
- Default format is `table`.

Implementation: loop over companies, route each through identity then financials, assemble a column-major table, render. `markdown` format emits a screenshot-quality GitHub-flavored table. `json` format dumps `{"companies": [{"ticker": ..., "period": ..., "metrics": {...}}, ...]}`. The renderer footnotes period mismatches inline: `"MiniMax: FY24 (most recent available) | Baidu: FY25"`.

Error model:
- Any company resolving to `private=True` causes exit 2 naming the company.
- A metric not available for one company shows `n/a` with a footnote describing which path failed (regex miss, no LLM fallback hit, period not yet filed).
- FX conversion failure exits 2 with the rate-not-found error.

## Currency, period, alignment

Currency follows the existing `--currency {native,usd,both}` semantics from the foundation spec. Period alignment defaults to each company's latest available; mismatches get footnoted. `--period FY24` forces alignment. If any company is missing the requested period, that cell shows `n/a` with a footnote `"FY24 not yet filed; latest available is FY23"`. The CLI does not silently fall back to a different period.

FX rates pull from `data/fx_rates.csv` (already shipped). The output displays both the converted USD value and the rate used, per the foundation spec's formatter rules.

## Tests

Three new test files plus updates to existing tests.

`tests/test_hk_extract.py` (new). Unit tests for the regex extractor against frozen fixture text snippets pulled from the MiniMax and Zhipu prospectuses. Asserts each canonical metric resolves to the expected value with `extraction_method="regex"`. A second test exercises the Claude-fallback path with a stubbed API client (no real network), verifies cache-write on first call and cache-hit on second call, and asserts the cache file exists at the expected path.

`tests/test_compare.py` (new). End-to-end on the `compare` subcommand:
- `compare minimax zhipu baidu --metrics revenue,gross_margin` produces a 3-column table with all three values and per-column period footnotes.
- `compare minimax baidu --period FY24` works for both, or shows `n/a` with footnote if Baidu is missing FY24.
- `compare BIDU GOOGL --currency usd` (both USD-reporting) produces clean output with no FX-rate columns since both currencies are USD.
- A genuinely private company in the args list forces exit 2 with a clear message.
- `--format json` and `--format markdown` produce parseable / pasteable output.

`tests/eval/china_ai_labs_golden.yaml` (new) plus `tests/test_china_ai_labs_eval.py`. Golden values hand-curated from independent sources: the tanayj.com IPO breakdown, FT or Bloomberg coverage of the MiniMax and Zhipu listings, plus Tencent and Meituan FY24 figures from sell-side coverage. Per the user-confirmed scope: 1 percent tolerance on line items, exact match on share counts. Fixture shape mirrors the existing `china_golden.yaml` template.

Updated tests:
- `tests/test_china_identity.py::test_live_universe_minimax_is_private` flips to `test_minimax_routes_to_hkex` asserting `private=False, source="HKEX"`. The new test still covers the case that genuinely private entries route through the private-company error path; use a placeholder if no other private company is in universe.toml yet.
- `tests/test_cli_query_currency.py::test_query_private_company_exits_with_clear_message` and its alias variant either repoint at the placeholder private entry or get removed (the path is exercised by the identity-level test). Removal is acceptable.

Test selection: all eval tests carry `@pytest.mark.eval`. Run via `.venv/bin/python -m pytest tests/ -m eval -v`. Cached Claude responses commit to the repo. CI stays offline.

## Done definition

- `edgarpack query MINIMAX revenue --period FY24` returns a USD-normalized cited value within 1 percent of the tanayj.com number ($71.2M).
- `edgarpack query ZHIPU revenue --period FY24` returns within 1 percent of $54M.
- `edgarpack compare minimax zhipu baidu --metrics revenue,gross_margin,operating_income,cash_burn,runway_months,cash_and_equivalents` produces a three-column comp table that screenshots well, with FX rates and periods footnoted.
- All eval tests green in `pytest -m eval`.
- Universe correction is live. The stale `MINIMAX-PRIVATE` entry no longer exists.
- A separate sweep adds Moonshot, 01.AI, Baichuan, DeepSeek if and only if each is verified public. Otherwise their absence is documented in a follow-up issue.
- The Twitter-launch artifact (the screenshot of the MiniMax / Zhipu / Baidu comp) is reproducible from the CLI by anyone who clones the repo.

## Risks and mitigations

HKEX prospectus PDFs vary in formatting. Regex recall on first pass may be 60 to 80 percent. Mitigation: the Claude-fallback path catches the rest. If fallback also misses, the metric returns `n/a` rather than guessing. The eval harness flags any miss-rate above 5 percent of the canonical metric set as a release blocker.

Claude-fallback caching makes the system deterministic per cache state. New metrics or new filings require fresh API calls. CI stays offline only as long as the cache covers everything tested. The contributor workflow: run the extraction locally, commit the cache, push. Cache invalidation is manual (delete the file).

Period alignment for `compare`: MiniMax FY24 vs Baidu FY25 is a 12-month offset. The footnote is honest but may confuse a casual reader. The launch tweet should call out the period mismatch explicitly. The default-to-latest-available behavior trades alignment rigor for "you can always get a number out."

Stock-code drift on HKEX. Codes occasionally renumber (mergers, delistings, reorganizations). `universe.toml` needs verification at build time, not just at config-load time. A future `bd doctor`-style check belongs on a separate issue.

LLM-extracted values must be flagged distinctly in output. The existing `learned:fuzzy` annotation pattern is the template. Users seeing `[learned:llm]` in a citation should know to verify against the source. Trust is earned by surfacing the path, not by hiding it.

## Open questions parked for follow-up

- Annual-report ingestion for FY25 once those filings land.
- Same `compare` UX extended cleanly to SEC-only comps. BIDU vs GOOGL works today via individual queries but lacks the pretty side-by-side. Easy follow-on after this lands.
- A `bd doctor`-style stock-code freshness check.
- Markdown narrative-report generator beyond table format. Resist; that is analyst work, not tooling work.
