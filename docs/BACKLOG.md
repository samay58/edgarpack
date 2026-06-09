# EdgarPack Backlog

Project-local backlog. Items moved here from phoenix `tasks.md` on 2026-04-21 during the bloat reduction pass, per the rule: project sub-tasks live in the project, not in the global task pile.

This file is the task tracker (beads was retired 2026-06-02). Keep it lightweight: add genuine outstanding work, delete items when shipped.

---

## Better LTM Drill-Down (UX Design Question)

Surfaced during Apr 10 scrub smoke test. Running `edgarpack query NVDA revenue --period ltm` shows the formula (`LTM = mrp[C2] + lfy[C3] - mrp_prior[C4]`) and links components to a citation footer. Fine for verification; not great for inspecting values.

Current workarounds: `--audit` flag (exists, worth checking how deep it goes) and `--format json-full` (has everything but reads as JSON).

Open design question: what is the right CLI affordance for "show me the full LTM breakdown inline with values and sources"? Directions:
1. Make `--audit` render a compact component table.
2. Add `--explain` that walks through the computation.
3. Let single-metric `query ... --period ltm` default to showing components.

Defer until demo v2 conversation; web UI can solve this with click-to-expand where the CLI is stuck with text.

---

## Known query bugs (P1): all closed as of 2026-06-09

The three carried-over bugs are fixed with regression tests: per-share LTM routes to annual values (now with an `ltm_degraded` diagnostic), annual-only LTM-1 skips stubs, and the Q4 early-return only accepts full-fiscal-year entries (a standalone Q4 stub falls through to three-component math). The same fix run closed the silent-degrade family found by the 2026-06-09 review: strict-mode recursion over derived components, exact prior-FY requirement for LTM, fail-closed ltm-N/mrq-N, mrp offset routing, and the inert self-heal verification path. See the fix(query) commit from that date for the full list.

---

## Diff engine precision findings (2026-06-09 ground-truth audit)

Audited diff output against raw section markdown for three same-form pairs (FIG 10-Q, CRWV 10-Q, RDDT 10-K). No hidden changes found: in every case tested, changed text appeared in a visible delta, and section alignment was clean in all three pairs. The weak edge is precision of the per-paragraph labels:

1. **`added` label overclaims on reordered/re-split text.** 10 of 11 CRWV "added" Risk Factors paragraphs had matching text present in the before filing. The DP alignment in `diff/text_diff.py` is order-preserving, so reordered paragraphs become added+removed pairs. Possible fix: an order-free rescue pass that re-matches leftover added/removed paragraphs by Jaccard before final labeling, relabeling matched pairs as `moved`.
2. **Page-break artifacts leak into paragraph deltas.** Standalone "Table of Contents" lines and bare page numbers ("45") survive inside 10-Q section markdown (parse-pipeline issue, observed in CRWV and FIG packs) and then show up as "added" paragraphs and mid-paragraph noise. Degenerate table-header rows ("Three Months Ended March 31, / ..." repeated) also appear as added paragraphs in MD&A. Fix belongs upstream in html_clean/md_polish; any change bumps PARSER_VERSION and fixtures.
3. **Forced-marriage pairings via the overlap rescue.** `match_score = max(sim, overlap * 0.8)` admits topically unrelated pairs whose reported Jaccard is below the 0.5 threshold (observed at 0.38-0.48: disaster-recovery paired with sustainability, tariffs with supplier concentration). Content is not lost, but the old/new presentation is misleading. Consider a floor on reported Jaccard for the `modified` label, or a distinct `replaced` label.

Audit-method caveat worth keeping: an order-free Jaccard baseline used during the audit itself produced a false "novel" verdict on a paragraph that exists verbatim in the before filing (paragraph-granularity mismatch crushed the score). Similarity scoring at any granularity is a lead generator, not ground truth. The reliable arbiter for "is this language new" is a literal normalized substring search against the before pack's `filing.full.md` (not a single section file, since language migrates between sections).

User-facing mitigation until fixed: before quoting an "added" paragraph as new language, grep the before `filing.full.md` for a distinctive phrase; zero hits means genuinely new.

Shipped 2026-06-09 (display layer, `diff/html_report.py`): the HTML report now filters whole-artifact paragraphs (`---`, "Table of Contents", bare page numbers) at render time, renders modified pairs with reported Jaccard >= 0.5 as a single inline word-level redline (merged from the existing opcode spans), and renders sub-0.5 pairs stacked with a "rewritten · N% similar" badge so overlap-rescued marriages stop masquerading as redlines. Engine items 1-3 above remain open; the JSON output is unchanged.

---

## Deferred findings from the 2026-06-09 whole-project adversarial review

Five review agents swept the codebase (query core, parse/pack, sec client, observatory, China Lens). Everything fixable offline without changing pack bytes was fixed and committed that day. What remains is below; every item was verified against the code (most by repro), so treat the file:line pointers as confirmed, not hypotheses.

### Parse pipeline batch (one PARSER_VERSION bump + fixture regen, do together)

1. **Sectionizer: repeated benign TOC header rows disarm the state machine** (`parse/sectionize.py:572-590`). Multi-part TOCs (Part I table, blank line, Part II table with its own "Page" header) leak their remaining rows as real headings, and the TOC fragment steals the canonical section id while the real section gets `_1`. Fix: when armed and the row is a benign header, `continue` unconditionally.
2. **`## INDEX` heading form never arms the TOC machine** (`parse/sectionize.py:557-559`); the fullmatch only accepts a bare `INDEX` line. Same clean-id theft. Fix: allow optional `#`/bold prefixes in the fullmatch.
3. **Page-break artifacts** (the diff-audit item above, located precisely): `_TOC_HEADING_RE` in md_polish only strips heading-form TOC lines, and `_strip_broken_anchors` runs second-to-last, after `_strip_toc_spam`, so the bare "Table of Contents" text it produces survives. Bare page-number lines have no removal rule at all. Fix: a `_strip_page_artifacts()` pass after `_strip_broken_anchors`; gate bare-number removal on adjacency to a TOC marker (md_polish legitimately emits plain numeric lines when collapsing single-column tables).
4. **Tokenizer fallback is environment-dependent** (`parse/tokenize.py:48-55`, `pack/chunks.py:167`): a cold tiktoken cache offline silently switches the whole chunking algorithm to the len//4 estimate, changing chunks.ndjson bytes. Fix: fail loudly or stamp tokenizer provenance into the manifest.
5. **Registration-pack asset downloads that fail are silently dropped from filing.full.md** (`pack/assets.py:78-80`): markdown bytes depend on network flakiness. Fix: thread failures into build warnings or raise.
6. Smaller, same batch: manifest section offsets are not byte-faithful to section content (strip drift, `sectionize.py:921`); md_polish splits table rows on unescaped pipes (`md_polish.py:121,317`) while md_render escapes them; `_simplify_complex_tables` duplicates header-only tables (`md_polish.py:334`); non-force rebuilds do not clear manifest-less pack dirs, stranding orphan sections (`pack/build.py:215-230`); manifest writes are not atomic; llms.txt same-date ordering tie (`pack/llms_txt.py:131,156`); dead `strip_ixbrl_selectolax`.

### China Lens correctness (the cited-value promise)

7. **HK LLM-fallback facts are never unit-scaled** (`hk/llm_extract.py:102-115`): the regex path multiplies by the detected `'000`/millions multiplier, the LLM path persists the raw model number, 1000x off, next to correctly scaled facts. Fix: pass the section multiplier into the LLM path and reject non-numeric values.
8. **Fabricated fiscal periods for non-December HK fiscal years** (`hk/extract.py:577-578`): every fact gets synthesized Jan-Dec bounds; a Mar-FYE filer (Alibaba is in `_COMPANY_META`) gets December FX rates and wrong period dates. Fix: carry the real period end or leave dates absent.
9. **FX "period average" is one month's average applied to annual flows** (`fx/convert.py:71-73`): annual revenue converts at the FYE month's average, not the fiscal-year average. Fix: average monthly rows across the period for `convention="average"`.
10. **Chinese sectionizer has no TOC guard** (`sse/sectionize_cn.py:77-80`): TOC entries with dot leaders become canonical sections, real sections get `_1`, and the translation router's section-keyed prompts never fire. Fix: drop matches whose title ends in dot-leaders plus page number. Changes SSE pack bytes; coordinate with the batch above.
11. Smaller: unknown HKEX filers default to CNY/HKFRS instead of failing (`hk/adapter.py:133-140`); China facts fall back to a fabricated `filed` date of Dec 31 (`query/financials.py:2092-2098`, a test enshrines it); the committed china fixture manifest carries a dead absolute `file:///Users/...` pdf_url and production probes `tests/fixtures/` paths (`query/financials.py:1995-2007`); per-FY provenance cross-wiring when two statements carry the same metric (`query/financials.py:2371-2383`); SSE annual facts have no 万元 unit detection (`sse/annual_facts.py`); SSE PDF cache is non-atomic and never validated as PDF (`sse/client.py:38-56`); DeepInfra client returns input text on empty choices and ignores `finish_reason=length` (validators currently backstop it); the API seeds fabricated Tencent evidence unless `EDGARPACK_CHINA_SEED_FIXTURES=0` (flip the default); dead code listed in the review (hk `_parse` helpers, router/provider orphans).

### Observatory

12. **Boilerplate suppression can hide substantive numeric changes** (`diff/text_diff.py:61-74,123`): the boilerplate token class includes any 1-4 digit number, so a $26.0B to $35.1B revenue sentence can be suppressed entirely from diff output. Fix: narrow the numeric class to date-like tokens and never treat $- or %-adjacent numbers as boilerplate. Note the 2026-06-09 distinctive-token work in `diff/` may have changed this surface; re-verify before fixing. Bump `_DIFF_CACHE_VERSION`.
13. Smaller: timeline counts raw deltas while pair diffs filter boilerplate, so pure date-rollover sections show MODIFIED in timelines (`diff/timeline.py:86-105`); report paragraph stream is change-type-ordered, not document-ordered, so context grouping cannot work (`diff/report_builder.py:397`); per-pair Jaccard recomputes normalization 4x (36s on an 800-paragraph synthetic section; precompute word sets); `harvest/runner.py:145` swallows registry exceptions from `gather(return_exceptions=True)`; `list_companies` GROUP BY picks an arbitrary ticker label after renames (`harvest/registry.py`); registry migrations and incremental indexing have zero test coverage (verified working manually; should be tests).

### SEC layer

14. Smaller: `SECRateLimitError.cooldown_seconds` reports the sleep-clamped Retry-After (60s cap) instead of the real value (`sec/client.py:140,150,233`); no negative caching for 404 companyfacts, so S-1 query sessions re-hit SEC every time (`sec/xbrl.py:72-73`); a `edgarpack cache prune --older-than` subcommand would give the unbounded cache (8.8 GB observed) a story beyond rm -rf; dead skip-patterns in `sec/archives.py:134-135`.

### Query core residue (from the 2026-06-09 fix run; see that commit for what landed)

15. Deferred flattening: `_select_metric_period_value`'s structural no-op `_filter_to_expected_fiscal_years` call and unreachable scalar-merge branch (`query/financials.py:523-551`); `comps.py:58-85` compat wrappers used only by one test; `metric_map.py` METRIC_MAP name collision with `concepts.METRIC_MAP` (rename to STANDARD_CONCEPT_MAP or fold into hk/); learned-registry migration ladder could take `BEGIN IMMEDIATE`; comps whole-company failures and self-heal misses still surface no diagnostic (P2-6, P2-7 in the review).

### Distill

16. Findings' evidence `section_id` holds an invented prose label ("prospectus summary / business") in the same field where metric evidence carries real manifest section ids; upstream `FramingHit`/`DisclosureHit` offsets are discarded in `registration_profile.py:143-148`. Fix: leave findings' section_id empty, carry the topic guess in its own field, thread real offsets through.

---

## Deferred cli.py decomposition (from the 2026-06-02 tech-debt pass)

The single-period query renderer was already extracted to `query/render.py`. The remaining "cli.py is wiring, not logic" moves, each a self-contained, test-covered commit when wanted:

- `_cmd_translate_sse` (~400 lines) into `china/translate/pipeline.py` (covered by `tests/test_translate_sse_artifacts.py`).
- `_render_registration_timeline` into `diff/timeline.py` (covered by `tests/test_cli_registration_timeline_render.py`).
- The `which` render cluster (~640 lines) into `query/kpi_render.py`.
- Period-selector regex centralization in `query/periods.py` (medium risk, lower payoff).
