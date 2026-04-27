# Generalized Company Resolver

Date: 2026-04-27
Status: Draft, awaiting user review
Owners: edgarpack maintainers

## Problem

`edgarpack identify <name>` and the rest of the CLI (`build`, `query`, `which`, `comps`, `compare`, `diff`, `timeline`) share `_resolve_cli_company`. Today that resolver only knows three things: aliases hand-curated in `universe.toml`, SEC's `company_tickers.json` plus EDGAR issuer-name search, and a 6-digit-A-share-code shortcut that verifies the code via a live CNINFO call.

So `identify "Anker Innovations"`, `identify "Insta360"`, `identify "Roborock"`, `identify "Arashi Vision"`, and any other A-share or HKEX filer not pre-aliased in `universe.toml` returns `Status: unknown`. The same brittleness shows up the moment a user reaches for `query Anker revenue` or `build "Insta360" --form 10-K`. The fix today is to hand-edit `universe.toml`, which does not scale and is surprising for first-time users.

The resolver needs to work for any listed A-share or HKEX company without per-company curation, stay fast on the happy path, and avoid breaking the existing `universe.toml` contract.

## Goals

- A first-time user can type `edgarpack identify "Anker Innovations"`, `edgarpack identify "Tencent"`, or `edgarpack identify 300866` and get a working next-step command back, with no hand-edits required.
- Every CLI entry point that takes a positional company argument inherits this behavior, not just `identify`.
- Happy-path performance stays cold-start cheap. SEC-resolvable tickers (NVDA, AAPL) pay zero overhead.
- `universe.toml` semantics do not change. Project-curated aliases still win.
- Offline use stays viable. Live network calls during resolution are opt-out, not required.

## Non-goals

- Chinese-language input matching. Snapshot rows carry Chinese names for display, but resolver inputs are stock code + ticker + English name only. Pinyin abbreviations are out of scope for this iteration.
- Auto-mutating `universe.toml`. Successful auto-resolutions land in a per-user disk cache, not in the checked-in config.
- Cross-listed market-cap tie-breaking. Ambiguity raises `AmbiguousCompany` and asks the user to disambiguate by code.
- New SEC issuer-name index. SEC resolution stays as it is.

## Approach

Two bundled JSON snapshots, a lazy in-memory index, an extended resolver chain, and a refresh script.

### Snapshot data

Two new files live next to `data/fx_rates.csv` and load through the same `Path(__file__).resolve().parents[2] / "data" / ...` pattern already used by `edgarpack/query/currency.py`:

- `data/cn_stock_listings.json` covers every SSE and SZSE A-share listing.
- `data/hk_stock_listings.json` covers every HKEX-listed equity.

Each file is a JSON object with a `snapshot_date` header and a `rows` array. Each row carries:

```json
{
  "code": "300866",
  "source": "SZSE",
  "market": "ChiNext",
  "name_zh": "安克创新",
  "name_en": "Anker Innovations",
  "aliases": ["anker", "anker innovations"]
}
```

`source` is one of `SSE`, `SZSE`, `HKEX`. `market` is the board within the source (Main, STAR, ChiNext, GEM, etc.). `name_en` is the official English name when the exchange publishes one. `aliases` are normalized lowercase forms generated at refresh time; this is where the resolver indexes from.

For ~5300 A-share + ~2700 HKEX rows at roughly 150 bytes per row, the combined snapshot lands near 1.2 MB on disk. That ships in the wheel.

### Resolver chain

`_resolve_cli_company` in `edgarpack/cli.py` grows two new steps. The full ordering becomes:

1. `universe.toml` exact alias or ticker match (existing).
2. 6-digit A-share code shape check, looked up in the bundled snapshot first; CNINFO live verify only if the snapshot misses.
3. **New:** bundled CN/HK snapshot, English-name normalized exact match.
4. **New:** bundled CN/HK snapshot, English-name fuzzy match via `difflib.get_close_matches` at cutoff 0.85.
5. SEC `company_tickers.json` ticker / CIK / name match (existing).
6. EDGAR issuer-name search for pre-IPO filers (existing).
7. **New:** live CNINFO + HKEX search (default on, disabled by `--offline` or `EDGARPACK_OFFLINE=1`), 5-second timeout, no retry.
8. `UnknownCompany` with snapshot-based "did you mean" suggestions (existing shape, broader corpus).

The existing `universe.toml`-wins contract is preserved by step 1. The 30-day on-disk cache is consulted before step 7 and written after a successful step 7 resolution.

### Lazy snapshot index

The snapshot files do not parse on every CLI invocation. The `CompanyIndex` is a separate object from `IdentityIndex` (which reads `universe.toml` today), built lazily on first miss in steps 1, 2, 5, or 6. SEC-resolvable tickers like `NVDA` pay zero snapshot cost.

When the index does build, JSON parse plus alias normalization is a one-shot ~30-50ms cost. The CLI dies after one command, so eager parse on every invocation would burn that cost on every operation; lazy parse pushes it to the calls that actually need it.

The index exposes:

- `by_code: dict[str, CompanyRow]`. Maps `"300866"` to its row. HKEX codes are zero-padded to five digits to match `universe.toml`.
- `by_alias: dict[str, list[CompanyRow]]`. Normalized lowercase alias to a list of rows. Lists, not single rows, because cross-listed names are valid.
- `all_aliases: tuple[str, ...]`. Source for `difflib` fuzzy fallback.

### Cross-listed tie-breaking

If `by_alias["china construction bank"]` returns rows for both `601939` (SSE) and `00939` (HKEX), the resolver raises `AmbiguousCompany` listing both candidates with their codes and source labels. The user disambiguates by typing the code. Same pattern as today's `universe.toml` collision check, applied to the snapshot.

### Live fallback

`edgarpack/china/acquire/cninfo.py` already has `fetch_cninfo_announcements` for code-based lookups. Live name search adds one new function in the same module, plus a parallel HKEX search helper in a new `edgarpack/hk/search.py`. Both honor a 5-second timeout, perform no retries, and run only when the snapshot misses.

A successful live resolution writes a row into `~/.edgarpack/cache/identity/<sha256-of-input>.json` with a 30-day TTL. The cache key is the normalized input string; the value is the `CompanyRow` plus a `resolved_at` timestamp. Subsequent identical inputs hit the cache before the live call.

`--offline` on `identify`, `query`, `which`, `comps`, `compare`, `build`, `diff`, `timeline` skips step 7. `EDGARPACK_OFFLINE=1` does the same globally, useful for CI and reproducible test runs.

### Identify output

For a snapshot-only resolution (not in `universe.toml`), the output mirrors the existing A-share-code path: resolved name on line 1, status on line 2, code on line 3, working build command on line 4. No nag line about adding to `universe.toml`. The cache write is invisible.

```
Anker Innovations
Status: public A-share / SZSE
Stock Code: 300866
Next: edgarpack build-sse 300866 --latest-annual --with-chunks
```

For HKEX:

```
Tencent Holdings Limited
Status: public HKEX listing
Stock Code: 00700
Next: build or import the HKEX pack, then run edgarpack which/query.
```

### Refresh script

`scripts/refresh_cn_listings.py` is a new standalone script. It:

1. Calls the CNINFO stock-list endpoint for SSE main + STAR + SZSE main + ChiNext.
2. Calls HKEX's published securities-list endpoint.
3. Normalizes each row to the snapshot schema. Generates `aliases` from `name_en` (lowercase, suffix-stripped: "Inc", "Ltd", "Limited", "Holdings", "Co., Ltd", "Corporation").
4. Writes `data/cn_stock_listings.json` and `data/hk_stock_listings.json` with a fresh `snapshot_date`.

The script depends only on `httpx` (already in the `china` extra). No new third-party data services. Refresh is run on demand by a maintainer; a weekly CI cron is a natural extension but is not part of this scope. The snapshot date is surfaced in `edgarpack identify --snapshot-info` so users can tell when they should pull a fresh package.

### Module layout

```
edgarpack/
  resolve/                   # new package
    __init__.py
    snapshot.py              # CompanyRow, CompanyIndex, lazy loader
    aliases.py               # English-name normalization rules
    live.py                  # CNINFO + HKEX live search adapters
    cache.py                 # ~/.edgarpack/cache/identity/ read/write
data/
  cn_stock_listings.json     # bundled snapshot
  hk_stock_listings.json     # bundled snapshot
scripts/
  refresh_cn_listings.py     # snapshot regenerator
```

`edgarpack/cli.py::_resolve_cli_company` extends to call into `edgarpack.resolve` between the existing `universe.toml` check and the SEC fallback. `edgarpack/identity.py` is untouched. `_cmd_identify` keeps its current output shape.

### Error handling

- `UnknownCompany` is raised only after the full chain misses. The exception's `Did you mean` suggestions now draw from `universe.toml` aliases plus snapshot aliases plus SEC ticker/name candidates, in that order, capped at three.
- `AmbiguousCompany` is raised on cross-listed alias collisions inside the snapshot, with the same shape used today for `universe.toml` collisions.
- Live CNINFO/HKEX search timeouts and HTTP errors are caught silently and treated as a miss. The chain falls through to step 8.
- Snapshot file missing or malformed: `CompanyIndex.load()` returns an empty index, logs a warning, and the chain continues with `universe.toml` + SEC only. Resolver does not crash on a corrupt snapshot.

### Testing

Three lanes:

1. **Offline unit tests** for the resolver chain, using a fixture snapshot under `tests/fixtures/snapshots/` with ~10 rows (Anker, Insta360, Tencent, two cross-listed banks, a name collision, an SEC ticker for path comparison). Mocked CNINFO/HKEX live calls. Covers steps 1 through 8, ambiguity, fuzzy fallback, cache hits, `--offline` behavior.
2. **Live `--run-live-cn` lane** in `tests/test_live_cn_integration.py`, mirroring the existing `--run-live-sec` pattern. Hits real CNINFO and HKEX search endpoints for a small canary set. Run before snapshot refreshes.
3. **Snapshot smoke** that asserts the bundled JSON loads, has a recent `snapshot_date`, and contains a known canary row (e.g., 300866 / Anker Innovations). Cheap. Runs on every CI invocation.

Existing tests:

- `test_cli_identify.py::test_identify_a_share_code_verifies_via_cninfo` retargets to assert snapshot-based resolution. The `_find_latest_sse_annual_report` mock moves out of `identify`'s call path and stays in the `build-sse` lane where it belongs.
- `test_cli_identify.py::test_identify_unknown_a_share_code_does_not_try_sec` keeps its semantics: a 6-digit code with no snapshot match and no live verify still returns `Status: unknown China A-share code`.
- `test_cli_identify.py::test_identify_laifen_uses_private_universe_entry_without_sec` is unchanged. `universe.toml` private entries still win.
- `test_cli_identify.py::test_identify_sse_alias_shows_a_share_next_step` is unchanged. `universe.toml` aliases still win.

### Performance contract

- Cold start, NVDA query: snapshot never loads. Same speed as today.
- Cold start, "Anker" query: snapshot loads once (~30-50ms), name resolves in O(1). No network.
- Cold start, brand-new IPO not in snapshot: snapshot loads, misses, cache misses, live CNINFO+HKEX search fires, 5-second timeout cap. Result cached for 30 days.
- Memory: snapshot index sits at 3-5 MB after parse.
- Wheel size: snapshot adds ~1.2 MB uncompressed, ~300 KB compressed.

## Open Questions

None. Tie-breaking, write-back, scope, ordering, refresh, loading, language matching, timeout, TTL, output, and test lanes were all resolved during the brainstorming session captured above.

## Out of Scope

- Pinyin / Chinese-character input matching.
- Auto-writing resolved rows to `universe.toml`.
- Market-cap-based tie-breaking on ambiguous names.
- A `--snapshot-update` command that downloads a fresh snapshot at runtime. Snapshot ships with the wheel; updates ship with releases.
- Bundling SEC issuer names into a snapshot. SEC resolution stays unchanged.

## Migration

No public-API breakage. `universe.toml` schema is unchanged. Existing aliases continue to win in step 1. The new code paths are additive and live behind the existing `_resolve_cli_company` entry point. CLI flags `--offline` and `--snapshot-info` are new but optional.

A pre-existing test relies on `_find_latest_sse_annual_report` being called during `identify`. That assertion shifts to the snapshot-resolution path; the underlying behavior (verifying that a 6-digit code maps to a real company before printing a build hint) is preserved, just via a faster path.
