# Packet: s1-core

Goal: make the S-1/F-1 snapshot extraction honest: no permanent LLM suppression, no lying error statuses, no poisoned caches, no fabricated currency/audit/period metadata, and diagnostics everywhere the path goes quiet today. This is the design-sensitive core packet.

Files owned: `edgarpack/query/s1_financials.py` (except `has_registration_pack_for_cik`, ~1219-1231, owned by registration-periphery: do not edit that function), `edgarpack/query/formatting.py`, `edgarpack/cli.py` (only the no_api_key hint text ~3458 and its rendering call sites ~2545-2557), tests (`tests/test_s1_financials_*.py`, `tests/test_cli_registration_shortcut.py`).
`edgarpack/query/models.py`: read-only. The `no_api_key` source handling at models.py:93-94 stays; new statuses live in the snapshot layer, not in CitedValue.source vocabulary, unless a fix below says otherwise; if you believe a models.py change is required, mark the fix blocked with the question.

## Status taxonomy (pre-made decision)

Snapshot `extraction_status` values after this packet: `ok`, `no_api_key` (ONLY missing key / anthropic ImportError), `llm_call_failed` (any runtime API failure, carries the exception text in a `detail` field), `llm_parse_failed`, `no_financial_data_found`. The last three are retryable: cache them with a `retry_after` timestamp (30 minutes); a read within the cooldown serves the cached failure, a read after it re-attempts extraction. `ok` snapshots never expire (invalidated by hash/schema only). Bump the snapshot `schema_version` 8 -> 9 (this alone re-extracts existing caches, which is intended).

## Fixes

1. `merge-extraction`. `extract_or_load_snapshot` (~956) returns the moment the deterministic table parser yields ANY fact, so the LLM never fills slugs the deterministic label map cannot see; the map (~427-472) has no branch for cash_and_equivalents, total_assets, stockholders_equity, or shares_outstanding_basic, so on Cerebras itself the balance-sheet metrics are N/A forever. Merge: deterministic facts win per-slug; the LLM is invoked only for slugs still missing; results union into one snapshot whose per-fact provenance records which extractor produced it (existing model field). Tests currently asserting "deterministic success means the LLM is never called" enshrined the bug: rewrite them to assert the LLM is called only for the missing slugs.

2. `error-taxonomy`. The bare `except Exception` at ~971 maps 429s, outages, and model retirement to `no_api_key`, and the CLI hint (~3458) then tells the user to set a key they may already have. Split per the taxonomy above; update the CLI hint per status (missing key: install/export instructions; call failed: the detail text and "retry shortly").

3. `retryable-cache`. Failure snapshots are currently served forever from cache (~906-916, ~985-998); recovery requires a pack rebuild. Implement the `retry_after` cooldown above. Also attempt partial-array salvage on truncated JSON before declaring `llm_parse_failed`: trim to the last complete object in the array and parse that; salvage success plus at least one valid row is `ok` with a `truncated: true` marker in the snapshot.

4. `model-config`. `MODEL_ID` (~765) and `_MAX_OUTPUT_TOKENS` (~766) are hardcoded. Env overrides `EDGARPACK_S1_MODEL` and `EDGARPACK_S1_MAX_TOKENS`, defaults unchanged; one retry with a short backoff (2s) on transient API errors before surfacing `llm_call_failed`.

5. `currency-honesty`. The deterministic parser stamps `currency="USD"` unconditionally (~613). Detect presentation currency from the section context ("expressed in thousands of RMB", "in millions of EUR", RMB/EUR/SEK/GBP/JPY/HKD symbols and codes); when a non-USD presentation marker is present, emit facts with that ISO code; when a marker is present but unparseable, refuse deterministic emission for that table (fail closed, let the LLM path handle it). LLM-path `currency` (~831) gets ISO-4217 validation (3 uppercase letters from a small accepted set; invalid -> row rejected).

6. `audited-honesty`. `is_audited=True` is stamped on every deterministic fact (~614) including interim columns, and `mrp` selection (~1296) filters on `is_audited`, working today only BECAUSE the flag is wrong. Set `is_audited` truthfully (annual columns of audited statements true; interim/stub columns false) and fix the `mrp` selection in tandem so interim periods remain selectable for `mrp` (that is what mrp means). Add a regression test proving `mrp` still resolves after the flag is honest.

7. `real-period-ends`. `_summary_period_from_context` (~312-338) falls through to `("FY", f"{year}-12-31")` for any unrecognized context: "year ended March 31, 2026" is cited with period_end 2026-12-31, and "three months ended January 31, 2026" becomes a full FY. Carry the actual month-day when the context states one; recognize month names generally, not just Mar/Jun/Sep/Dec; refuse FY classification when the context says three/six/nine months, classifying as the right interim instead; when nothing is parseable, emit no period metadata rather than a fabricated one (which for snapshot rows means the fact is dropped with a warning: an uncited period is a guess). Also `_compact_summary_columns` (~526-531) hardcodes surplus interim columns to `("Q1", "-03-31")`: derive from the actual column label or drop the column.

8. `full-hash`. Snapshot invalidation hashes only the first 50KB of `filing.full.md` (`_SOURCE_SCAN_CHARS`, ~856): a parser fix or amendment past byte 50,000 never invalidates. Hash the full file. Covered by the schema bump above; keep `_SOURCE_SCAN_CHARS` gone, not enlarged.

9. `diagnostics`. The registration path emits zero `Diagnostic`s. Emit them following the existing patterns in `query/` for: an unsupported period selector on a registration-only filer (ltm/mrq/annual:N currently return silent None), latest-pack snapshot empty while an older pack has a cached snapshot (~1595-1596), and any `extraction_status != ok` (status and detail in the diagnostic).

10. `magnitude-gates`. LLM rows pass with no scale sanity checks; one Haiku arithmetic slip becomes a cited value. Gates: where both present in the same period, revenue >= gross_profit and total_assets >= cash_and_equivalents; adjacent-year same-metric ratio outside [1/500, 500] rejects the newer row; non-numeric or negative-where-impossible (revenue, total_assets) rejected. Gated rows drop with a diagnostic, never a guess.

## Done definition

All ten fixes tested (each with at least one named regression test); the rewritten LLM-suppression tests are called out in the report; snapshot schema 9; full offline suite green.
