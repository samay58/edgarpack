# Packet: fx-average

Goal: make `convention="average"` mean the average over the period, not over one month. Today `edgarpack/fx/convert.py:71-73` converts a full fiscal-year flow at the fiscal-year-END month's average rate; every cross-market `--currency usd` annual value is wrong by construction, absorbed by the china golden 2% tolerance.

Files owned: `edgarpack/fx/` (convert.py, rates.py), `tests/eval/china_golden.yaml`, `tests/test_china_query_eval.py`, new fx unit tests. `data/fx_rates.csv` is read-only reference.
Interface contract: you exclusively own `china_golden.yaml` this phase; other packets are forbidden from editing it. Native-currency golden values must not change; only USD expectations move.

## Fixes

1. `fy-average`. For `convention="average"`, average the monthly rate rows across the period's months, start to end inclusive, from the rates table. Any missing month inside the period fails closed: no conversion, a diagnostic-friendly `None`/error consistent with how conversion failures surface today. Never present a partial average as the period average.

2. `golden-update`. The corrected math changes USD values in `tests/eval/china_golden.yaml`. Recompute each affected expectation with a hand-derived oracle and show the work in YAML comments next to the value: which monthly rows from `data/fx_rates.csv` participate, their mean to 6 decimals, and the native value times/divided by that mean. A reviewer must be able to re-check each number with a calculator. Tighten the tolerance if the fix allows (it should); do not relax any tolerance.

3. `unit-tests`. Direct `convert()` tests against a small synthetic rates table with hand-computed expectations: a calendar fiscal year, a partial-year period (e.g. Apr-Sep), a single-month period (equals that month's average), and the missing-month fail-closed case.

## Done definition

Unit tests plus updated goldens pass; every changed golden number carries its derivation comment; full offline suite green.
