# China Query Golden-Fixture Harness (design)

Issue: edgarpack-qhn
Date: 2026-04-15
Status: approved, pre-plan

## Problem

`edgarpack query` now works for HKEX AI-lab packs (MiniMax, Zhipu) and SEC ADR paths (BIDU, PDD, BABA, JD). What is working today is held together by about 45 lines of hand-rolled assertions in `tests/test_china_query_hk.py`. Three pieces of queued work can silently regress those values: Tencent and Meituan ingestion (`edgarpack-3yv`, closed 2026-04-20 with followup `edgarpack-sfi` for annual-report shape support), multi-year HKEX extraction (`edgarpack-ej1`), and headcount extraction (`edgarpack-ws7`). The goal is a regression gate that runs on every `pytest tests/` and anchors on hand-verified IR numbers, before any of those three lands.

## Scope

In scope: a YAML-backed golden fixture at `tests/eval/china_golden.yaml`, a parametrized pytest harness at `tests/test_china_query_eval.py`, initial coverage for MiniMax and Zhipu across LFY and LTM for the metrics currently extracted, and xfail-tagged rows for known bugs.

Out of scope: ADR 20-F golden entries (BIDU, PDD, BABA, JD); Tencent and Meituan entries; multi-year rows (FY22, FY23); subprocess CLI invocation; auto-regenerate tooling; bundled FX snapshot reform.

## Design

The golden file lives at `tests/eval/china_golden.yaml`. Each top-level entry is a company block keyed by ticker, carrying reporting metadata (`accounting_standard`, `reporting_currency`, `fiscal_year`) and a `metrics` map. Each metric entry carries one block per period (`lfy`, `ltm`). Each period block carries `native` (integer), `usd` (integer), `fx_rate` and `fx_convention` (informational, not asserted), `source` (per-metric free-form citation), and optional `xfail` (bead ID).

```yaml
version: 1
companies:
  - ticker: "00100.HK"
    company: "MiniMax Group Inc."
    accounting_standard: HKFRS
    reporting_currency: USD
    fiscal_year: 2024
    metrics:
      revenue:
        lfy:
          native: 30523000
          usd: 30523000
          fx_rate: 1.0
          fx_convention: identity
          source: "MiniMax Prospectus, Consolidated Statement of Profit or Loss, p. F-7"
        ltm:
          native: 30523000
          usd: 30523000
          fx_rate: 1.0
          fx_convention: identity
          source: "MiniMax Prospectus, Consolidated Statement of Profit or Loss, p. F-7 (LTM proxy: annual-only filer)"
      r_and_d_expense:
        lfy:
          native: null
          usd: null
          xfail: edgarpack-483
          source: "MiniMax Prospectus, p. F-8 (multi-line label extraction bug)"
```

The harness is a single file, `tests/test_china_query_eval.py`, that loads the YAML at collection time and parametrizes over `(ticker, period, metric, currency)` tuples. For each tuple it calls `asyncio.run(financials(company=ticker, metrics=metric, period=period))` and asserts the returned `CitedValue.value` against the golden entry. Native assertions are exact equality. USD assertions use `math.isclose(actual, expected, rel_tol=0.02)`. Rows carrying `xfail` apply `pytest.mark.xfail(strict=True, reason=bead_id)` to that parametrized case.

## Failure output

On assertion failure the harness prints a block with: ticker, period, metric, currency, golden value, actual value, absolute diff, percent diff, FX rate in use, and the `source` citation. The message flows through `pytest.fail(..., pytrace=False)` so test output points at the fixture row, not at pytest internals.

## Known-bug handling

An `xfail` field in a golden period block makes that tuple a strict xfail. When the bug closes and the value extracts correctly, the test unexpectedly-passes and the suite goes red with a clear signal to delete the `xfail` row and fill in real numbers. Bug closures become forced golden updates.

## Metric coverage (initial)

The golden ships with rows for the metrics currently extractable or known-broken on MiniMax and Zhipu: `revenue`, `net_income`, `cash_and_equivalents`, `operating_cash_flow`, `r_and_d_expense`. Each company gets LFY and LTM period blocks (mirroring is intentional for HKEX annual-only filers). Total initial rows: 2 companies by 5 metrics by 2 periods by 2 currencies, yielding 40 parametrized tests. `r_and_d_expense` carries `xfail: edgarpack-483` on MiniMax.

## Interaction with existing tests

`tests/test_china_query_hk.py` stays as targeted smoke assertions: ticker-form resolution (`00100.HK`), `reporting_currency` flag, `accounting_standard` flag, full-metric query returns more than one metric. Inline numeric values move to the golden and the smoke file checks structure only. `assert revenue.reporting_currency == "USD"` stays; `assert revenue.value == 30_523_000` moves to YAML. Net result is two thin layers: smoke file owns shape, golden owns values.

## Done definition

`pytest tests/test_china_query_eval.py -v` green. `pytest tests/` green, with no regression in the existing suite. `tests/eval/china_golden.yaml` committed with MiniMax and Zhipu entries including per-metric IR citations. `tests/test_china_query_hk.py` refactored to strip inline numbers; structure assertions preserved. `edgarpack-483` xfail present and firing. A README stub at `tests/eval/README.md` documents the YAML schema and the workflow for adding a new company (harvest pack into fixtures, hand-verify values from IR, add YAML block, commit).

## Risks

FX table refresh drifts USD values past 2 percent. Mitigation: tolerance was chosen against historical FRED CNY/USD monthly revision range (typically under 1 percent). If a refresh breaches 2 percent, widen for that metric with a per-row tolerance override, filed as a follow-up schema change.

YAML schema churn as Tencent, Meituan, and ADRs land. Mitigation: schema versioning via a top-level `version: 1` field; the loader asserts on mismatch and makes future migrations explicit.

Curator drift (values edited without citation update). Mitigation: the README specifies that every value change requires re-reading the cited page and updating `source` if the page moved. Not enforceable in CI, a review discipline.

## Open questions parked for follow-up

Tencent and Meituan golden rows land once `edgarpack-sfi` (followup to closed `edgarpack-3yv`) ships annual-report shape support in the HK pipeline. ADR 20-F golden rows (BIDU, PDD, BABA, JD) land as a separate P2 after a fixture harvest pass. Multi-year rows (FY22, FY23) land with `edgarpack-ej1`. Headcount metric rows land with `edgarpack-ws7`.
