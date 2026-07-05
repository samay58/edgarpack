# Packet: hk-extract-fixes (trust-critical; blocks build-hk-construct's facts layer)

Goal: fix the three extractor defects and add the garble gate the construction prototype proved against four real large-cap ARs. The dominant bug currently yields half-right/half-wrong values (one fiscal year correct by coincidence, the other a note-reference number), which is the exact failure class this project exists to kill.

Files owned: `edgarpack/hk/extract.py`, new text fixtures under `tests/fixtures/hkex_statements/`, tests. Nothing else.
Evidence: the hk-construct-prototype report; artifacts under session scratchpad `hk-construct-prototype/` (notably `extract_results.json` and the four downloaded ARs: `meituan_3690_ar2025.pdf`, `byd_1211_ar2025.pdf`, `anta_2020_ar2025.pdf`, plus `hkex-spike/tencent_ar2025.pdf`).

## Fixes

1. `year-header-anchor` (the mechanism bug). `extract_with_regex` counts year columns via `re.findall(r'\b(20\d\d)\b', text[:500])`: a window scan that inhales boilerplate ("Annual Report 2025", "For the year ended 31 December 2025") and overcounts n_years (Tencent 4 vs real 2). Downstream, correct 2-column rows are dropped (count mismatch) while rows carrying a leading note-reference digit coincidentally match the inflated count and the extractor reads the NOTE NUMBER as the value (verified: Meituan rd_expense FY2025 extracted as 7, the note number; Anta cash extracted as 19). Anchor year detection to the actual standalone header row: a line consisting only of 20XX tokens and whitespace (optionally followed by the Note/currency-unit row), and derive n_years from THAT line only. Regression tests from real text: the prototype's four issuers' statement pages, where correct rows must extract with both years right and note-ref rows must not yield the note number.
2. `revenues-plural`. `_PROSE_LABELS['revenue']` matches `^\s*revenue\b`, which cannot match "Revenues" (three of four issuers' actual first line). Add the plural.
3. `million-shorthand`. `_detect_multiplier` recognizes "in millions"/"in thousands"/'000 but not the `RMB’million` header shorthand (Anta, and Tencent's summary tables), so values land six orders of magnitude small. Recognize the apostrophe-million form (both apostrophe variants).
4. `garble-gate`. HSBC-class PDFs (subsetted font, no usable ToUnicode CMap) extract as cipher text with digits as control characters, identically in pypdf and pymupdf: no downstream fix can recover them. Before regex extraction, gate on a garble heuristic (control characters in the 0x00-0x18 range inside candidate table lines, or a printable-ratio floor over the section text) and raise a typed `HKExtractionBlockedError` naming the cause. Never emit values from garbled text. The prototype's own heuristic had false negatives; yours must at minimum flag the committed HSBC excerpt fixture and must NOT flag the four clean issuers' fixtures. OCR support is explicitly out of scope (follow-up, per the prototype's recommendation).

## Fixtures

Commit TEXT excerpts, not PDFs (the repo deliberately untracked fixture PDFs): extract the relevant statement pages from the four clean ARs plus a garbled HSBC statement page into `tests/fixtures/hkex_statements/*.txt` using pypdf, and golden the extraction results against them (per-metric expected values, hand-verified against the PDFs; the prototype's `extract_results.json` documents the wrong values, so derive expecteds from the PDFs' actual numbers, e.g. Meituan R&D FY2025 = 25,998,265 thousand).

## Constraints

The existing MiniMax/Zhipu fixture packs and `tests/eval/china_golden.yaml` must stay green untouched: the header-anchor fix must not change extraction on the committed prospectus-style fixtures. If it does, that is a finding to report, not a golden to edit.

## Done definition

Four-issuer goldens green (both fiscal years correct per extracted metric, zero note-number values); HSBC fixture raises the typed error; china goldens and full offline suite green.
