# Packet: trust-tightening

Goal: close the four trust and maintainability seams left by the July 5
streamline stack without changing the product shape. The product promise stays
simple: cited values, explicit gaps, no invented provenance, no half-written
packs pretending to be queryable.

This is a tightening packet, not a new feature phase.

## Files owned

- New module: `edgarpack/china/pack_store.py`
- New module: `edgarpack/china/build_if_needed.py`
- `edgarpack/hk/adapter.py`
- `edgarpack/hk/extract.py`
- `edgarpack/cli.py` only to remove orchestration
- `edgarpack/query/financials.py` only to consume the new pack store
- `edgarpack/query/registration/integrate.py`
- Tests covering HK build/extract, China build-if-needed, S-1 registration

Do not touch parser behavior, metric definitions, live acquisition selectors, or
the starter universe unless a failing test proves it is required.

## Fixes

### 1. `hk-atomic-pack-build`

Problem: HK builds write directly into the final pack directory. A failed or
interrupted build can leave PDF, section files, chunks, or manifest fragments in
place. `_write_sections()` does not clear stale section files, so a later facts
extraction can scan old sections beside a new manifest.

Fix: make HK pack publication atomic.

- Build under a temp directory created inside the target parent directory.
- Download, section, write chunks, write manifest, and extract facts inside the
  temp directory.
- Only after `facts.json` is valid, rename the finished temp directory into
  `packs/hk/<code>/<code>_<year>`.
- If facts extraction is blocked, keep the sectioned temp pack only when the
  explicit `build-hk` command needs to show a debug path; query auto-build must
  not publish a non-queryable pack.
- Existing final directories are replaced only after the new build succeeds.

Design note: mirror the SSE build-if-needed temp-dir pattern. Do not invent a
separate HK lifecycle.

### 2. `hk-blocked-means-blocked`

Problem: `extract_with_regex()` raises `HKExtractionBlockedError` for garbled
statement text, but `extract_facts_from_pack()` catches that per section,
continues, and can write an empty `facts.json`.

Fix: a blocked financial statement blocks the facts file.

- Collect blocked section ids and messages while scanning sections.
- If any required financial statement is blocked, raise
  `HKExtractionBlockedError` before writing `facts.json`.
- Do not write an empty standard block such as `{"facts": {"hkfrs": {}}}`.
- If a clean filing simply has no extractable target rows, return `None` or a
  typed no-facts result. Do not make that look like a successful facts file.

Tests:

- A pack with one garbled `hkex_income_statement.md` raises the typed error and
  leaves no `facts.json`.
- `build-hk` still prints a useful "sectioned pack written, facts blocked"
  message when run explicitly.
- Query auto-build treats the same case as non-queryable and stops.

### 3. `registration-no-fabricated-dates`

Problem: S-1 snapshot conversion still fabricates dates. When a registration
pack has no filing date, `_filed_date_for_candidate()` falls back to
`fact.period_end`, then to today's date. The no-API-key placeholder path also
uses today's date for both `filed` and `period_end`.

Fix: missing provenance stays missing.

- Make registration cited-value assembly accept `filed: date | None`.
- Return `None` when the pack filing date is absent and no real date was passed.
- For no-API-key placeholders, set `filed=None` and `period_end=None`.
- Preserve `fiscal_year=0` on placeholders.
- Do not use `date.today()` anywhere in registration provenance.

Tests:

- A snapshot candidate with `filing_date=date.min`, `filed=None`, and empty
  `period_end` produces `CitedValue.filed is None`.
- A no-API-key placeholder has `filed is None` and `period_end is None`.
- Existing happy-path S-1 query tests keep their real filing dates.

### 4. `one-china-pack-store`

Problem: China/HK pack discovery lives inside `query/financials.py`, while query
auto-build orchestration lives in `cli.py`. SSE has a "built without facts"
status; HK does not. This is why HK can publish a sectioned-but-unqueryable pack
and why CLI has grown another policy branch.

Fix: introduce one canonical pack-store boundary.

`edgarpack/china/pack_store.py` owns:

- `discover_china_pack(resolved, pack_root) -> Path | None`
- `classify_china_pack(resolved, pack_root) -> ChinaPackStatus`
- `ChinaPackStatus.kind` values: `queryable`, `missing`, `built_without_facts`
- exchange-specific path variants for SSE and HKEX
- the `EDGARPACK_CHINA_PACK_ROOT` override warning

Then:

- `query/financials.py` imports the public store functions and deletes
  `_discover_china_pack_dir()` / `sse_pack_status()`.
- `cli.py` no longer imports private query helpers.
- HK and SSE use the same status vocabulary.

Keep the store boring. It should read filesystem state and return typed facts;
it should not fetch, build, render, or print.

### 5. `build-if-needed-service`

Problem: `cli.py` owns too much policy: resolve, classify local packs, fetch
latest reports, run builders, handle blocked facts, and decide whether query
continues.

Fix: move build-if-needed into `edgarpack/china/build_if_needed.py`.

The service owns:

- `ensure_china_pack_for_query(args/resolved inputs...) -> EnsurePackResult`
- SSE latest annual acquisition and temp-dir publication
- HK latest annual acquisition and temp-dir publication
- mapping blocked/no-facts/missing statuses to stable error messages

The CLI owns only:

- argument parsing
- calling the service before `financials()`
- printing `EnsurePackResult.message` when present
- returning the result code

Done means deleting code from `cli.py`, not moving the same mess behind a
larger wrapper. If the CLI line count does not fall meaningfully, the packet
missed the point.

## Constraints

- No invented dates, currencies, fiscal years, or filing dates.
- No empty `facts.json` counts as queryable.
- No private helper imports from `query/financials.py` into `cli.py`.
- Keep live fetch selectors unchanged unless their current tests fail.
- Preserve current user-facing command names and default behavior.
- Do not add dependencies.

## Verification

Run:

```bash
EDGARPACK_USER_AGENT="Codex Trust Tightening codex@example.com" \
  uv run --extra dev --extra china --extra sse pytest \
  tests/test_hk_extract_ar_goldens.py \
  tests/test_cli_build_hk.py \
  tests/test_cli_china_build_if_needed.py \
  tests/test_s1_financials_registration_refactor.py \
  tests/test_s1_financials_query_integration.py \
  -q

EDGARPACK_USER_AGENT="Codex Trust Tightening codex@example.com" \
  scripts/symphony_quality_gate.sh
```

If HK/SSE/FX files change, also run the China golden lane:

```bash
EDGARPACK_USER_AGENT="Codex Trust Tightening codex@example.com" \
  SYMPHONY_CHINA_GOLDEN=1 scripts/symphony_quality_gate.sh
```

## Done definition

- HK build publication is atomic.
- Garbled HK financial statements cannot produce a queryable empty facts file.
- Registration fallback paths never use today's date as provenance.
- China pack discovery is one typed module, used by CLI and query.
- Query build-if-needed orchestration is out of `cli.py`.
- Targeted tests and the repo quality gate are green.
