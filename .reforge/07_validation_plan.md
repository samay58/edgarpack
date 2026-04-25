# Validation Plan

## Existing Tests To Preserve As Reference

The current suite is evidence, not the vNext completion gate. Preserve it as a parity oracle and regression backstop:

- Full regression: `EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest -q`.
- Ruff: `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Query/period core: `pytest tests/test_periods.py tests/test_financials.py tests/test_stress.py -q`.
- Pack determinism and build: `pytest tests/test_pack_build.py tests/test_build_pack_range.py tests/test_determinism.py -q`.
- China/HKEX/SSE tests remain reference coverage for old paths, not first-slice vNext scope.

## Current Gate Status

- Full pytest passed only after:
  - `EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache`
  - network approval for SEC lookups
- Ruff check passed.
- Ruff format check passed.
- Global mypy failed with 1293 errors and should not be treated as a repo-wide completion gate.

## vNext Offline Gates

Add these before claiming the rewrite slice works:

- Model contract tests for filing, pack, citation, metric, derived, missing, and audit objects.
- Fixture manifest tests for NVDA, AAPL, and Cerebras S-1.
- Deterministic pack writer tests.
- Citation invariant tests: no public value without structured provenance.
- Metric registry tests for the analyst bundle.
- Derived metric tests requiring component citations.
- Missing derived-component diagnostics tests.
- Experimental concept search tests that return only `unverified_cited` and cannot feed derived metrics.
- S-1 selected-financial-data extraction tests.
- CLI JSON contract tests for `filings`, `pack`, `cite`, and `audit`.
- API contract tests proving the API wraps core services rather than generating facts.

Required commands:

```bash
./.venv/bin/python -m pytest tests/vnext -q
./.venv/bin/ruff check edgarpack_next tests/vnext
./.venv/bin/mypy edgarpack_next
```

## vNext Live Gates

Live is required before signoff:

- Resolve NVDA and AAPL through live SEC data.
- Fetch latest relevant 10-K or 10-Q metadata.
- Build or dry-run one live pack from a primary SEC document.
- Query one live cited metric.
- Verify cache and `EDGARPACK_USER_AGENT` behavior is explicit.

Required command:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache ./.venv/bin/python -m pytest tests/vnext/test_live_sec_smoke.py --run-slow --run-live-sec -q
```

Expected result:

- PASS when `EDGARPACK_USER_AGENT` is set.
- SKIP with an explicit message when the environment lacks the required user agent.

## Manual Smoke Checklist

- `edgarpack-next filings NVDA --form 10-K --fixture`
  - Check JSON accession and form.
- `edgarpack-next pack NVDA --form 10-K --fixture --out /tmp/edgarpack-vnext-smoke`
  - Check deterministic manifest and sections.
- `edgarpack-next cite NVDA revenue,gross_margin --fixture --json`
  - Check citations, formulas, and component provenance.
- `edgarpack-next cite "Cerebras Systems Inc." revenue --form S-1 --fixture --json`
  - Check S-1 selected-financial-data citation.
- `edgarpack-next audit /tmp/edgarpack-vnext-smoke/<cik>/<accession>`
  - Check required artifacts and warnings.

## Behavior To Preserve

- Deterministic pack layout and manifest hashing.
- Citation-bearing query outputs.
- Missing facts return structured diagnostics, not guesses.
- LTM/derived values require component citations.
- SEC User-Agent, rate-limit, and cache behavior.
- Unsupported status for uncited or numerically unmatched findings in old China Lens paths.

## Behavior To Intentionally Change

- Replace old command grammar with evidence verbs in vNext.
- Keep API thin and out of fact-generation ownership.
- Remove hardcoded web sample supported claims from any future production path.
- Keep `llms.txt` reserved but not generated in slice one.
- Scope mypy to `edgarpack_next` until global cleanup is a separate project.

## Behavior Needing User Decision

- Exact parity checks required before replacing the old `edgarpack` command.
- Whether `compare` and `trace` are milestone two or later.
- Whether old command aliases should be added after vNext stabilizes.
- Whether China Lens gets revived after the SEC-first clean slice.
