# Chinese company query parity (design)

Issue: edgarpack-2yg
Date: 2026-04-14
Status: approved, pre-plan

## Problem

`edgarpack query` works for US tickers today. Six target Chinese names (BIDU, PDD, BABA, JD, Tencent, Meituan) have filings across two regimes (SEC 20-F, HKEX annual) in two currencies (CNY, HKD). A seventh target, MiniMax, is private. The goal is CLI parity: same flags, same output shape, USD-normalized numbers that match a trusted source within 2 percent.

Evaluation is part of the goal, not an afterthought. Golden-fixture tests for all six public targets are written up front, alongside the adapter and FX code.

## Scope

In scope:

- US-listed ADR 20-Fs for BIDU, PDD, BABA, JD.
- HKEX annuals for Tencent 0700.HK, Meituan 3690.HK, and the HK legs of BABA 9988.HK and JD 9618.HK.
- A bundled FX rate table with spot and period-average rates.
- An identity layer that resolves `--ticker` and `--company` across both regimes.
- Golden-fixture evaluation harness with the full fundamental metric set for all six public targets.
- A scaffold-only MiniMax path: CLI exits with a clean private-company message.

Out of scope:

- A-shares via CNINFO. Owned by edgarpack-lb1.11 and lb1.12.
- Accounting reconciliation across US-GAAP, IFRS, HKFRS, and CAS. Values are reported as filed with a standard flag.
- Cross-corpus diff and timeline. Those live on the existing engines and are a separate follow-up.
- MiniMax alt-data ingestion. A separate issue will own press releases, leaked decks, and employer disclosures.

## Identity model

`universe.toml` grows two fields on `[[companies]]`:

```toml
[[companies]]
ticker = "BABA"
listing = "NYSE"
aliases = ["alibaba", "alibaba group"]
alt_tickers = ["9988.HK"]

[[companies]]
ticker = "0700.HK"
listing = "HKEX"
aliases = ["tencent", "tencent holdings"]
hk_stock_code = "00700"
```

A new module `edgarpack/identity.py` owns resolution. Its public API:

```python
def resolve(ticker: str | None, company: str | None) -> ResolvedCompany
```

Rules:

- `--ticker BIDU` resolves to `(ticker=BIDU, listing=NASDAQ, source=SEC, cik=0001329099)` as today.
- `--ticker 0700.HK` resolves by suffix to `(ticker=0700.HK, listing=HKEX, source=HKEX, hk_stock_code=00700)`.
- `--ticker 9988.HK` resolves to the HK leg of BABA, routing to HKEX.
- `--company tencent` resolves via alias table to the primary listing for that company, which is `0700.HK` for Tencent and `BABA` for Alibaba.
- Unknown tickers and unknown aliases exit with a suggestion list built from the universe.

Ambiguous matches (two aliases collide) raise at config-load time, not at query time.

## Corpus adapters

A thin protocol isolates regime-specific code from the query and pack-builder layers:

```python
class FilingSource(Protocol):
    def harvest(self, company: ResolvedCompany, forms: list[str]) -> list[FilingRef]: ...
    def build_pack(self, filing: FilingRef, out_dir: Path) -> PackRef: ...
```

Two implementations:

`edgarpack/sec/` is the existing code. The 20-F harvest and parse paths already work end-to-end. The query flow has a known annual-only-filer bug tracked on a separate P1 issue (`eux` in project memory: annual-only filer LTM-1 picks stubs). This spec declares a hard dependency on that fix landing first. With it landed, the only work on the SEC side is adding `reporting_currency` (USD for 20-F filers that report in USD, or the filer's functional currency when different) and `accounting_standard` (`US-GAAP` or `IFRS`, picked up from filing metadata) to the pack manifest.

`edgarpack/hk/` is new and small. It calls through to the already-built `edgarpack/china/acquire/` and `edgarpack/china/extract/pdf_extract.py`. Its responsibilities:

- Fetch the HKEX annual report PDF for a given stock code and fiscal year from hkexnews.hk.
- Route the PDF through the existing OCR and text-extract pipeline.
- Emit a pack with the standard on-disk shape: `manifest.json`, `sections/*.md`, `chunks.ndjson`, `facts.json`.
- Set `reporting_currency` (typically `CNY` for Tencent and Meituan), `accounting_standard` (`HKFRS` or `IFRS`), and `source=HKEX` in the manifest.

The HK adapter does not build its own sectionizer. It reuses the existing one, with a small per-source config (`edgarpack/hk/sections.yaml`) mapping HK annual-report conventions (Chairman's Statement, Management Discussion and Analysis, Consolidated Statement of Profit or Loss) to the same canonical section IDs the SEC adapter produces.

## FX layer

`edgarpack/fx/` owns currency conversion.

Storage: `data/fx_rates.csv` ships in the repo with monthly spot and monthly average rates for `CNY/USD`, `HKD/USD`, and `USD/USD` (identity). Seeded from FRED series DEXCHUS and DEXHKUS. Columns: `ccy_pair`, `month_end_date`, `spot_end`, `period_average`.

Refresh: `scripts/refresh_fx.py` pulls from FRED, writes the CSV, and leaves it for a human to commit. Determinism is the point. No live API in the query path.

Public API:

```python
def convert(
    value: Decimal,
    from_ccy: str,
    to_ccy: str,
    as_of: date,
    convention: Literal["spot", "average"],
    period_end: date | None = None,  # for average convention
) -> ConvertedValue
```

`ConvertedValue` carries the rate used and its source row. Every converted figure in query output shows the rate.

Convention rules, following ASC 830:

- Balance-sheet items (assets, liabilities, cash, equity): `spot` at the balance-sheet date.
- Income-statement items (revenue, net income, operating income): `average` across the reporting period.
- Share counts and per-share figures: no conversion; the currency lives on the numerator only.

## Accounting standard flag

Every `CitedValue` gains `accounting_standard`. The formatter prints it inline when the value is non-US-GAAP:

```
Revenue FY23 (Tencent 0700.HK, HKFRS): CNY 609.0B
                                       USD 85.9B  (period-avg HKD/USD 0.1278, CNY/USD 0.1411)
```

No reconciliation. Users comparing Tencent operating income to BIDU operating income see both accounting standards surfaced and can judge whether the comparison is valid.

## Query CLI

The command shape does not change:

```
edgarpack query '<metric>' --ticker <ticker>
edgarpack query '<metric>' --company <name>
```

New flag:

```
--currency {native,usd,both}   default: both
```

Output, `both` default:

```
Revenue FY23 (Tencent 0700.HK, HKFRS): CNY 609.0B
                                       USD 85.9B  (period-avg HKD/USD 0.1278)
```

Output, `--currency usd`:

```
Revenue FY23 (Tencent 0700.HK): USD 85.9B
```

Output, `--currency native`:

```
Revenue FY23 (Tencent 0700.HK, HKFRS): CNY 609.0B
```

For US ADRs that already report in USD (BIDU, PDD), `--currency native` and `--currency usd` collapse to the same output; `both` drops the redundant line.

## Metrics

v1 supports the full fundamental set across both corpora:

- Top line: revenue (FY, LTM), gross profit, gross margin.
- Operating: operating income, operating margin, EBITDA.
- Bottom line: net income (FY, LTM), EPS basic, EPS diluted.
- Balance sheet: total assets, total liabilities, total equity, cash and equivalents, total debt.
- Share counts: shares outstanding basic, shares outstanding diluted.

Mapping lives in `edgarpack/query/metric_map.py` with per-standard dictionaries:

```python
METRIC_MAP: dict[AccountingStandard, dict[CanonicalMetric, list[str]]] = {
    "US-GAAP": {"revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", ...], ...},
    "IFRS":    {"revenue": ["Revenue", "RevenueFromContracts", ...], ...},
    "HKFRS":   {"revenue": ["Revenue", "Turnover", ...], ...},
}
```

Unknown canonical keys fail fast with a suggestion list. Unknown line items in a filing log a warning and get skipped.

LTM on HKEX filers: HK companies file a half-year interim, not quarterlies. v1 constructs LTM as `FY_prior + (H1_current - H1_prior)` and labels the output `LTM (H1-proxy)`. This matches how sell-side analysts model it. US ADRs keep the existing LTM path through quarterlies.

## Tests, written up front

Three dedicated test files, all green before the task closes.

`tests/test_china_identity.py`. Exercises ticker and company resolution for every target:

- `BIDU`, `PDD`, `BABA`, `JD` resolve to SEC source.
- `0700.HK`, `3690.HK`, `9988.HK`, `9618.HK` resolve to HKEX source.
- `--company tencent`, `--company meituan`, `--company alibaba`, `--company jd`, `--company baidu`, `--company pinduoduo` resolve to primary listings.
- `--company alibaba` with explicit `--listing HKEX` resolves to 9988.HK.
- `--company minimax` resolves but flags `private=True`.
- Unknown inputs exit with suggestion list.

`tests/test_china_fx.py`. Pins the FX convention against a frozen fixture:

- Balance-sheet conversion uses `spot_end` at period end.
- P&L conversion uses `period_average` across the full fiscal period.
- Rate source is logged on every converted value.
- Missing rate for an as-of date raises a clear error, does not silently interpolate.

`tests/eval/china_golden.yaml` plus `tests/test_china_query_eval.py`. Hand-curated golden values from IR filings for all six public targets, most recent FY plus LTM, for the full metric set above. Tolerance: 2 percent. Example fixture shape:

```yaml
- ticker: 0700.HK
  company: Tencent
  accounting_standard: HKFRS
  reporting_currency: CNY
  fy: 2023
  source: "Tencent 2023 Annual Report, page 142"
  metrics:
    revenue_fy: { native: 609015000000, usd: 85881000000, fx_avg: 0.1411 }
    net_income_fy: { native: 115216000000, usd: 16244000000, fx_avg: 0.1411 }
    total_assets_fy: { native: 1576000000000, usd: 221776000000, fx_spot: 0.1407 }
    cash_fy: { native: 166999000000, usd: 23498000000, fx_spot: 0.1407 }
    ...
```

The test invokes the CLI through a subprocess (or the same entry function) and asserts every metric within 2 percent. Failures print the fixture value, the computed value, the FX rate used, and the filing citation.

`tests/test_china_private_minimax.py`. Asserts the private-company path:

- `edgarpack query 'revenue' --company minimax` exits with status 2.
- stderr contains "private company", "no public filings", and points at a follow-up issue ID.
- No pack is fetched, no network call is made.

Test selection: all four files are marked `@pytest.mark.eval` and run under `.venv/bin/python -m pytest tests/ -m eval -x -v`. Network-touching fixtures (golden values) are offline; filings are pre-harvested into a test pack directory committed to the repo at `tests/fixtures/china_packs/`.

## Done definition

- `edgarpack query 'revenue LTM' --ticker BIDU` returns within 2 percent of the golden BIDU value.
- `edgarpack query 'revenue LTM' --ticker 0700.HK` returns within 2 percent of the golden Tencent value, labeled `LTM (H1-proxy)`, with CNY and USD both shown and the FX rate disclosed.
- All three test files green in CI.
- Golden fixtures cover Tencent, Alibaba, Baidu, JD, Pinduoduo, Meituan for FY and LTM across the full metric set.
- MiniMax scaffold test green.
- Spec updated with any learnings before issue close.

## Risk and mitigations

OCR recall on older HKEX PDFs could miss balance-sheet line items. Mitigation: pre-flight the six target filings through the extract pipeline before writing adapters. If recall is below 95 percent on the metric set, trim HKEX v1 coverage to the five most prominent line items (revenue, net income, total assets, cash, shares outstanding) and file a follow-up for the rest.

HK stock codes use a 4-digit or 5-digit form depending on context (0700 vs 00700). `identity.py` normalizes to the 5-digit form internally and accepts both at the CLI.

FX rate staleness. The repo ships with monthly rates. For queries on filings more than a month after the last refresh, the CLI warns on stdout and proceeds using the latest available period-average.

Dual-listed filing divergence. BABA reports to the SEC under US-GAAP and to HKEX under IFRS. Values can differ. Tests explicitly check both legs resolve to their own filing source and return their own numbers; the spec does not attempt to reconcile.

## Open questions parked for follow-up

- A-share corpus lives on the China Lens epic. A later spec can unify the query surface across all three corpora once that epic ships.
- Cross-corpus diff (Tencent FY24 vs BIDU FY24) needs section mapping and accounting-framework normalization. Separate spec.
- MiniMax alt-data ingestion is a separate track and a separate issue, to be filed when this spec ships.
