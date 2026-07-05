# Packet: build-hk-acquire

Goal: a working, tested HKEX acquisition module for ANY listed issuer: ticker to stockId to English annual report PDF on disk, plus filing-derived currency/standard metadata. Module + tests only; the `build-hk` CLI command ships with the construction packet after the prototype (see hk-construct-prototype.md).

Files owned: `edgarpack/hk/acquire.py` (full rewrite), new fixtures under `tests/fixtures/hkex_search/`, tests. Do not touch `hk/adapter.py` / `hk/extract.py` (construction packet territory).

Everything below is live-verified evidence from the 2026-07-05 spike (artifacts: session scratchpad `hkex-spike/`, notably `hkex_summary.json` and the saved endpoint JS). Treat it as the contract; where reality disagrees at implementation time, report the divergence, do not improvise.

## The acquisition flow (spec directly; all verified live for 0700, 9988, 3690, 1211, 0005)

1. Warm-up, once per session object: `GET https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en` keeping a cookie jar (Akamai issues bm_s/bm_so/TS* cookies). Subsequent calls send the cookie jar plus a Referer of that page. Skipping either does NOT error: requests return HTTP 200 with an EMPTY body.
2. Resolve code to stockId: `GET /search/partial.do?lang=EN&type=A&name=<code>&market=SEHK&callback=callback` (JSONP; strip the callback wrapper). `lang=EN` exactly: `lang=E` silently fails HERE, while step 3 requires `lang=E` and fails with `EN`. The match is a SUBSTRING over all exchange codes including warrants/CBBCs (querying 700 returned 33 candidates): filter to the exact zero-padded code yourself; zero exact matches is a typed not-found error listing near misses.
3. List annual reports: `GET /search/titleSearchServlet.do` with `sortDir=0&sortByOptions=DateTime&category=0&market=SEHK&stockId=<id>&documentType=-1&fromDate=YYYYMMDD&toDate=YYYYMMDD&title=&searchType=1&t1code=40000&t2Gcode=-1&t2code=40100&rowRange=100&lang=E`. Dates strictly YYYYMMDD (slashed dates silently return empty). The response JSON's `result` field is a JSON STRING: parse twice. Row fields: NEWS_ID, TITLE, DATE_TIME (DD/MM/YYYY HH:MM), FILE_LINK (relative), FILE_INFO, STOCK_CODE (dual-counter codes joined by `<br/>`, e.g. `00700<br/>80700`: split and match either).
4. Download: `GET https://www1.hkexnews.hk<FILE_LINK>` with the same session. Sizes 1-38MB observed.

Category codes worth constants with comments: annual report = t1code 40000 / t2code 40100 (one English PDF per fiscal year, count verified equal to TOTAL_COUNT for all five tickers); final-results announcement = t1code 10000 / t2Gcode 3 / t2code 13300 (lands ~3 weeks before the AR; expose a `list_results_announcements` sibling, not used by build yet).

## Defensive posture (non-negotiable, spike-derived)

- An empty response body is AMBIGUOUS (blocked vs zero results), never "no filings". Raise a typed `HKEXSearchBlocked` error telling the user to retry; assert non-empty on the warm-up too.
- Politeness: reuse the repo's pacing idiom at 1 req/s; ~30 requests at that pace drew zero 429s in the spike.
- Staleness floor mirroring CNINFO's: selected AR older than 18 months relative to the newest row in the payload raises LookupError with what was found and why rejected.

## Metadata from the filing (replaces the hardcoded dict at construction time)

Provide `extract_filing_metadata(pdf_path) -> HKFilingMeta(currency, accounting_standard, legal_name)`: pypdf text over the cover page and the first notes pages, anchored on the two disclosures IAS 1/HKAS 1 mandates: basis of preparation ("in accordance with ... IFRS Accounting Standards" or "... Hong Kong Financial Reporting Standards") and presentation currency ("presents its ... financial statements in RMB/HK dollars/USD..."). Normalize currency to ISO (RMB -> CNY). Both anchors missing: typed error, NO defaults (the Phase 2 unknown-filer rule). Note for the report: Tencent's own filing states IFRS while the legacy `_COMPANY_META` says HKFRS; do not "fix" adapter.py here, just flag it.

## Tests

Offline: recorded fixtures for partial.do (including the 33-candidate substring case), the doubly-encoded servlet response (including a dual-counter STOCK_CODE row), empty-body -> HKEXSearchBlocked, staleness rejection, callback-wrapper stripping, metadata extraction from 2-3 saved text excerpts (IFRS/RMB, HKFRS/HKD, missing-anchor failure). Live (gated behind the repo's live-test lane): one end-to-end resolve+list for 0700 asserting a nonzero AR count.

## Done definition

Module rewritten with the flow above; all offline tests green; live test passes when run; full offline suite green. No CLI wiring, no adapter changes.
