# Testing

Six lanes, in order of how often you'll run them:

- Fast local regression (every commit)
- Live SEC smoke (before merging query or parse changes)
- Expanded live SEC coverage (before refactors or releases)
- China golden harness (when touching the HKEX extraction pipeline)
- China Lens local loop (when touching ingestion, search, or storage)
- Web release gate (when touching `web/` or preparing a demo)

## Prerequisites

Install the test dependencies:

```bash
uv pip install -e ".[dev,china]"
```

Live SEC tests require a compliant user agent:

```bash
export EDGARPACK_USER_AGENT="Your Name your.email@example.com"
```

## 1. Fast Local Regression

Use this before most commits. It stays offline and exercises the unit-heavy coverage already in the repo.

```bash
uv run ruff check .
uv run pytest -q
```

Unattended agents should use the repo-owned wrapper so the default
cache behavior is explicit:

```bash
scripts/symphony_quality_gate.sh
```

For release or web-facing work, opt into the web build from the same wrapper:

```bash
SYMPHONY_WEB=1 scripts/symphony_quality_gate.sh
```

What this covers:

- query period selection and LTM math
- citation and JSON serialization
- pack builder determinism under mocks
- markdown render structural fixes (nested lists, colspan/rowspan, link cleanup, inline spacing)
- markdown polish rules (TOC spam, bold noise, bullet-table recovery, heading normalization, complex table simplification, whitespace normalization) and idempotency
- China Lens service, API, and storage adapters

With `SYMPHONY_WEB=1`, the same gate also runs `npm --prefix web run lint` and
`npm --prefix web run build`, installing `web` dependencies first when needed.

## 2. Live SEC Smoke Tests

Use this when you want to verify the query layer and parser path against real SEC data without paying for the full matrix.

```bash
uv run pytest tests/test_live_sec_integration.py -q --run-live-sec
```

What this does:

- validates live `financials()` audit JSON for `AAPL`, `MSFT`, `NVDA`, and `AMD`
- validates `comps()` citation/calculation rendering for `NVDA` vs `AMD`
- builds real packs for a six-filing smoke set across `10-K`, `10-Q`, and `8-K`

This is the best first live check when you want to answer, "does the useful product surface still work against real filings?"

## 3. Expanded Live SEC Coverage

Use this before larger refactors to the fetch, parse, pack, or query layers.

```bash
uv run pytest tests/test_live_sec_integration.py -q --run-live-sec --live-sec-full
```

What this does:

- runs the same live query/comps coverage as smoke mode
- builds packs across a 30-filing matrix:
  - `AAPL`, `MSFT`, `NVDA`, `AMD`, `AMZN`, `META`, `GOOGL`, `ORCL`, `CSCO`, `INTC`
  - each across latest `10-K`, `10-Q`, and `8-K`

This is the current comprehensive real-filings lane.

## 4. Determinism Check Against SEC

Use this when touching the pack builder or parse pipeline and you need to confirm repeatable output from the same filing.

```bash
uv run pytest tests/test_determinism.py -q --run-live-sec --run-slow
```

This builds the same live filing twice and compares the resulting artifacts byte-for-byte, ignoring only the manifest timestamp field that is expected to differ in-memory before serialization.

## 5. China Golden Harness

Use this when touching `edgarpack/hk/*`, `edgarpack/query/financials.py` HKEX routing, or `edgarpack/compare.py` currency normalization. The harness pins numeric answers against a hand-built golden YAML so regressions in HKEX extraction or currency math fail loudly.

```bash
# Full harness: structural smoke + numeric regression against the golden YAML
uv run pytest tests/test_china_query_hk.py tests/test_china_query_eval.py -q

# Just the structural smoke checks (fast, no golden comparison)
uv run pytest tests/test_china_query_hk.py -q
```

What this covers:

- MiniMax and Zhipu packs under `tests/fixtures/china_packs/` resolve to CIKless HKEX identities without hitting the network.
- `financials()` reads from `facts.json` (not companyfacts) and returns `reporting_currency`, `accounting_standard`, and `fiscal_year` correctly.
- Numeric values in the golden YAML (`tests/eval/china_golden.yaml`) match the extracted facts within tolerance; currency-normalized values round-trip through the FX layer.

When a golden comparison fails, the diff is the signal: decide whether the extractor drifted (regression) or the fixture needs updating, then regenerate the YAML by hand with filed-prospectus citations.

## 6. Manual CLI Audit Checks

These are the quickest useful manual checks for the query UX. Tickers, CIKs, and company names are all accepted on input:

```bash
edgarpack query AAPL revenue
edgarpack query "NVIDIA" revenue --period ltm --audit
edgarpack query NVDA gross_margin --period ltm --audit --citations inline --show-links primary
edgarpack query NVDA --preset perf --period lfy,lfy-1,lfy-2
edgarpack comps NVDA AMD --metrics revenue,gross_margin --period ltm --audit
edgarpack compare NVDA BIDU BABA --metrics revenue --currency usd
edgarpack which FIG                    # requires one or more built FIG packs
edgarpack query "Cerebras Systems" revenue,gross_profit,net_income,operating_cash_flow,capex,free_cash_flow --period lfy,lfy-1
edgarpack query "Cerebras Systems" capital_expenditures --period lfy,lfy-1
edgarpack query NVDA revenue --period ltm --format json
edgarpack query NVDA revenue --period ltm --format json-full
```

If you are running from this repo and the shell cannot find `edgarpack`, prefix these with `uv run`.

What to verify manually:

- direct metrics show inline citation markers
- warnings appear directly under the value they qualify
- `--audit` renders a readable formula/component block for derived and LTM metrics
- LTM values always carry `{mrp, lfy, mrp_prior}` citations; a scalar LTM without components means something regressed
- `compare --currency usd` shows USD values with a footnote naming each column's native reporting currency
- `which` renders a metric-by-period matrix; the build hint appears if no packs are registered
- Cerebras S-1 output uses the 2026 S-1 for FY2025/FY2024 and does not fall back to the older 2024 filing
- lean and full JSON both expose `citations` and `calculations`

## 7. China Lens Local Workflow Check

This is the fastest useful backend loop for China Lens today:

```bash
export EDGARPACK_CHINA_STORAGE_BACKEND=json
export EDGARPACK_CHINA_STORAGE_DIR="$PWD/.local/china-repo"
export EDGARPACK_CHINA_OBJECT_STORE_DIR="$PWD/.local/china-objects"
edgarpack api --host 127.0.0.1 --port 8000
```

In another shell:

```bash
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/api/v1/companies
curl "http://127.0.0.1:8000/api/v1/documents?company_id=cmp_tencent_0700"
curl -X POST http://127.0.0.1:8000/api/v1/evidence/search \
  -H "content-type: application/json" \
  -d '{"company_id":"cmp_tencent_0700","query":"top customers"}'
curl -X POST http://127.0.0.1:8000/api/v1/packs \
  -H "content-type: application/json" \
  -d '{"company_id":"cmp_tencent_0700"}'
```

If you want ingestion rather than just seeded fixtures:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/connectors/cninfo/sync \
  -H "content-type: application/json" \
  -d '{"company_id":"cmp_tencent_0700","manifest_path":"./cninfo-manifest.json","clear_existing":true}'
```

## 8. Web Release Gate

Use this when touching `web/`, the Observatory, or demo-ready UX.

```bash
npm --prefix web ci
npm --prefix web run lint
npm --prefix web run build
```

For asset smoke tests, run the built or dev server first, then check the routes:

```bash
npm --prefix web run dev
BASE_URL=http://localhost:3000 npm --prefix web run smoke:assets
```

The smoke script intentionally fails fast with a setup message if nothing is
serving at `BASE_URL`.

## Choosing The Right Lane

- Use fast local regression for routine commits.
- Use live SEC smoke tests before merging query, pack, parse, or SEC-client changes.
- Use expanded live SEC coverage before larger refactors or releases.
- Use the China golden harness when touching HKEX extraction, HKEX-path routing in `financials()`, or `compare` currency logic.
- Use the China Lens loop when touching ingestion, search, citations, pack generation, or storage.
- Use the web release gate when touching `web/` or preparing screenshot/demo surfaces.
