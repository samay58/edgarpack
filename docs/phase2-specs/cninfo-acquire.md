# Packet: cninfo-acquire

Goal: make CNINFO "latest annual report" selection trustworthy and declare the hidden OCR dependency. The Phase 0 spike had `--latest-annual` build Wuliangye's FY2005 scanned filing as "latest".

Files owned: `edgarpack/china/acquire/cninfo.py`, `edgarpack/sse/pdf_to_md.py`, `edgarpack/sse/client.py`; tests (`tests/test_cninfo_latest_annual.py`, new modules fine).

## Fixes

1. `stock-param`. `fetch_cninfo_announcements` queries `hisAnnouncement/query` with `searchkey=<code>` (full-text search), which for 000858 returned two 2006-era announcements. The endpoint accepts a `stock=<code>,<orgId>` parameter that returns the full filing history (verified live: `stock=000858,gssz0000858` returns 62 announcements including the FY2025 annual report). Implement orgId resolution: CNINFO's `www.cninfo.com.cn/new/information/topSearch/query` (POST, keyword=code) returns records carrying `orgId`; investigate the exact shape and mock it in tests. Use `stock=` when orgId resolution succeeds; fall back to the current `searchkey=` behavior when it fails (log a warning). All network calls mocked in tests.

2. `english-version`. `_is_full_annual_report` does not exclude 英文版, so an English-PDF edition can win selection (Wuliangye's newest full-AR candidate under the fixed query is the 英文版). Exclude titles containing 英文版, and on a same-date tie between editions prefer the Chinese one deterministically.

3. `staleness-floor`. `find_latest_annual_report` returning a years-old filing is an acquisition failure, not a result. Reject a selected filing older than 18 months from the newest announcement date in the payload (not wall-clock: scripts must stay reproducible against recorded payloads; state this reasoning in a comment). Raise `LookupError` naming what was found, its date, and why it was rejected.

4. `ocr-guard`. pymupdf4llm silently shells out to system Tesseract on image-heavy pages; on a host without `chi_sim` tessdata it injected junk (`~~ee~~`) into a pack. In the pdf-to-markdown path, detect the conditions under which OCR ran or would run (pymupdf4llm exposes page/image info; if detection is only possible post-hoc, detect OCR-junk signatures in output) and emit one prominent `warnings.warn` naming the `tesseract` + `chi_sim` dependency and the affected page count. Do not hard-fail builds of modern text-embedded filings.

## Done definition

Existing `test_cninfo_latest_annual.py` behavior is extended, not weakened: the current payload-parsing tests still pass. New tests: orgId path selected when resolution succeeds, searchkey fallback on failure, 英文版 excluded, zh-preferred on ties, staleness rejection with the explanatory error, OCR warning fires on a synthetic trigger. Full offline suite green.
