# Packet: harvest-china-sse

Goal: China coverage stops being frozen. `edgarpack harvest` grows an SSE lane: universe entries with `listing = "SSE"` get their latest annual report planned, acquired from CNINFO, built, and registered, so the daily refresh keeps A-share coverage current the same way it does SEC filings.

Files owned: `edgarpack/harvest/` (planner.py, runner.py, registry.py incl. a schema migration), tests (`tests/test_planner_registration.py` patterns, `tests/test_harvest_registry.py`, new modules fine).
Explicitly out of scope: HKEX lane (waits on build-hk; leave an interface note, not code), translation during harvest (never), any change to SEC lane behavior (several tests pin it).

## Pre-made design decisions

- Planner: entries with `listing == "SSE"` and a `stock_code` yield one plan item per filer with form `ANNUAL-REPORT`. A filer-level failure stays a `PlanError` item (the planner's existing resilience model), never an exception out of `plan_harvest`.
- Runner: for SSE items, resolve the latest annual via the Phase 2 CNINFO selection (`find_latest_annual_report`, which already carries the staleness floor and 英文版 exclusion), then build via the same internals as `build-sse --latest-annual`, honoring the existing 1 rps CNINFO pacing. Do not add concurrency beyond what the SEC lane already uses for its own fetches; CNINFO gets at most one in-flight download.
- Refresh semantics: skip an SSE filer when the registry already holds a pack whose filing date equals the selected latest filing's date; `--refresh` forces re-selection but still skips when the selected filing is already registered (same spirit as the SEC lane).
- Registry: China packs have no CIK or accession. Migration adds nullable `market` (e.g. "SSE") and `stock_code` columns following the existing incremental-migration pattern in registry.py; the natural key for an SSE pack is (stock_code, filing_date). SEC rows leave both columns null. `list_companies` and existing queries must keep working for SEC rows unchanged.
- Errors: acquisition/build failures land in `harvest_errors` with the existing logging path (stage stays 'build'); the run summary counts SSE successes/failures separately in its printout.

## Tests

- Planner: an SSE universe entry produces an ANNUAL-REPORT plan item; a malformed entry produces a PlanError, not a raise.
- Runner (all network mocked): happy path registers a pack with market/stock_code populated; CNINFO LookupError logs to harvest_errors and the run continues to the next filer; already-registered filing date is skipped without a build call.
- Registry: migration adds the columns idempotently (run twice); registering an SSE pack round-trips; SEC-row queries unaffected (extend the existing registry tests).

## Done definition

All tests green; a mocked end-to-end harvest over a universe containing one SEC and one SSE filer builds/registers both lanes; full offline suite green.
