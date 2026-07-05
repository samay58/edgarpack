# Packet: sweep-fixes (pre-wave; unlocks the coverage gate)

Goal: the 25-filer sweep found zero wrong values but only 4/25 filers yielding facts, and traced the misses to a handful of small, localized gaps. This packet fixes the five evidence-backed ones. Estimated effect: ~4/25 to ~21/25 filers with cited values.

Files owned: `edgarpack/sse/annual_facts.py`, `edgarpack/sse/sectionize_cn.py`, `edgarpack/config.py` (PARSER_VERSION line only), `edgarpack/query/financials.py` (ONLY the China fact-to-CitedValue provenance construction region), tests.
Evidence source: the 2026-07-05 sweep report; artifacts under session scratchpad `sweep-25/` (packs, build logs, per-filer query JSON) if you want real-world shapes for fixtures.

## Fixes

1. `unit-in-label` (killed 10/25 filers). SZSE/ChiNext-template key tables carry the unit as a row-label suffix (`营业收入（元）`, Midea uses `（千元）`) with NO `单位：` line, so the unit gate skips every row (gate at `annual_facts.py:328`). Recognize `（元）`/`（千元）`/`（万元）`/`（百万元）` label suffixes (full-width and half-width parens) as row-level unit bearers: strip the suffix before label matching, apply that row's multiplier, and let a row-level unit satisfy the fail-closed gate when no table-level marker exists. A row-level unit conflicting with a table-level marker: row wins for that row (it is the more specific disclosure). Regression tests: a （元）-labeled table with no 单位 line extracts at x1; the （千元） variant scales x1e3; an unmarked table still fails closed.

2. `unit-row-in-table` (killed 7/25). SSE-template tables carry the marker as a row INSIDE the table between title and year header: `|单位：元<br>币种：人民币|||||`. `_find_unit_scale` (`annual_facts.py:147-159`) breaks at the first table line above the header, so it never sees it. Scan 单位 markers out of table rows too (parse cell contents, handle `<br>`-joined fragments) instead of breaking on them. Regression: a synthetic SSE-template table with the in-table unit row extracts correctly.

3. `identical-duplicate-dedupe` (P2, cost Yangtze Power its FY2024). Headers with two identical-year columns (调整后/调整前) whose VALUES are identical get dropped as an equal-priority conflict by `_resolve_candidates` (`annual_facts.py:189-195`). Dedupe candidates by (concept, fy, value) before conflict detection; genuinely differing values still drop with the warning. Regression: identical duplicate columns yield the point; differing duplicates still fail closed.

4. `bold-heading-sectionize` (killed 3/25, fixes 1: CMB). Body headings like `**第一章 公司简介**` never match `_SECTION_PATTERN` (`sectionize_cn.py:78-81`, optional `#` prefix only). Strip bold markers and surrounding whitespace before pattern matching; the TOC guard applies to the stripped form. Bump PARSER_VERSION 0.2.2 to 0.2.3 (same verified-safe rationale as the 0.2.2 bump; restate it in the commit body). Known limitation to RECORD, not fix: fully designed layouts with no numbered headings at all (Ping An 601318, Zijin 601899) still fail closed to `unknown_01`; note it in your report and leave a one-line comment at the pattern site.

5. `provenance-mapping` (P2, citation-completeness). `--format json-full` renders `form: null, filing_date: null` for China facts even though facts.json points carry `"form": "ANNUAL-REPORT"` and `"filed"`. In the China CitedValue construction region of `financials.py` (the provenance-normalization area around `_normalize_china_fact_provenance`), thread `form` and `filed` through, respecting the Phase 2 optional-filed rules (real parseable date or None, never fabricated). Regression: fixture-pack query asserts form and filed present in json-full output.

## NOT in this packet (recorded so they are not lost)

Page-break row splits (Kingsoft OCF label split across pages) belong to the parse-pipeline batch in docs/BACKLOG.md (PARSER_VERSION-coupled fixture regen batch). The YoY validator's pp-delta misread (`减少3.49个百分点` parsed as a percent) is latent with zero observed cost: add it to docs/BACKLOG.md China section in this packet's commit, one line, do not fix.

## Done definition

All regression tests green; PARSER_VERSION 0.2.3; full offline suite green. The real gate runs after merge: a re-sweep over the cached 25-filer corpus must reach at least 20/25 filers with cited values and keep 0 wrong values. You do not run the re-sweep; the orchestrator does. Your bar is the tests plus honest notes on anything the sweep evidence contradicts.
