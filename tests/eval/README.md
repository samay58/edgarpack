# China Golden Fixtures

`china_golden.yaml` holds hand-verified query values for Chinese company packs committed under `tests/fixtures/china_packs/`. The harness at `tests/test_china_query_eval.py` loads this file at collection time and parametrizes over `(ticker, period, metric, currency)`. Native assertions are exact. USD assertions use 2% relative tolerance and go through `edgarpack.fx.convert.convert` against the rate table at `data/fx_rates.csv`.

## Schema (version 1)

```yaml
version: 1
companies:
  - ticker: "<STOCKCODE.HK or SEC ticker>"
    company: "<human-readable name>"
    accounting_standard: <US-GAAP | IFRS | HKFRS | CAS>
    reporting_currency: <USD | CNY | HKD>
    fiscal_year: <int>
    metrics:
      <metric_name>:
        <period_name>:        # lfy | ltm
          native: <int | null>
          usd: <int | null>
          fx_rate: <float>     # informational, not asserted
          fx_convention: <spot | average | identity>
          source: "<free-form citation, IR filing + page>"
          xfail: "<bead-id>"   # optional; marks tuple as strict xfail
```

## Adding a new company

1. Build a pack under `tests/fixtures/china_packs/<ticker>_<fy>/` (or use an existing one).
2. Run `edgarpack query <ticker> --period lfy --format json` and record the native values.
3. Open the filing PDF, hand-verify each metric against the primary statement (P&L, balance sheet, or cash flow). Note the page number in the `source` string.
4. Compute USD: CNY or HKD -> USD via the month-end row in `data/fx_rates.csv`. Use `spot_end` for balance-sheet items, `period_average` for P&L and cash flow. Integer rounding.
5. Append a new `- ticker: ...` block to `companies:` in `china_golden.yaml`. Include both `lfy` and `ltm` period blocks. For annual-only filers, `ltm` mirrors `lfy`.
6. Run `.venv/bin/python -m pytest tests/test_china_query_eval.py -v` and iterate until green.

## Fixing an xfail

When the underlying extraction bug (tracked by `xfail: edgarpack-XXX`) is fixed, the harness will go red with `XPASS` for that row. To clear:

1. Re-run `edgarpack query <ticker> <metric> --period lfy --format json` to get the now-extracted native value.
2. Verify against the cited IR page.
3. Compute USD.
4. Delete the `xfail:` and `null` fields in the YAML row; replace with the real `native` and `usd` integers plus `fx_rate` and `fx_convention`.
5. Commit with a reference to the closed bead.

## Tolerance policy

- Native: exact integer match. Extraction is deterministic against a committed pack, so drift means a parser regression.
- USD: 2% relative tolerance (`math.isclose(actual, expected, rel_tol=0.02)`). Absorbs FX rate refreshes of reasonable magnitude. If a single metric legitimately breaks 2% after a rate refresh, widen the tolerance per-row through a schema extension rather than loosening the global default.

## Do not

- Do not auto-regenerate golden values from current CLI output. If a value changes, a human re-reads the IR filing and updates the `source` field with the current page. Auto-regeneration masks regressions.
- Do not add entries for ADRs (BIDU, PDD, BABA, JD) here until a separate fixture harvest pass lands 20-F packs under `tests/fixtures/china_packs/`. That work is a separate P2.
