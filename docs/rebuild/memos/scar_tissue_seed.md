# Scar tissue seed list

Load-bearing scar-tissue candidates pulled from the Phase 0 discovery corpus (edge_cases across all 15 slices), deduplicated to the highest-signal items. These are SEEDS, not removable code. Each one looks odd in isolation, encodes a real-world filing pathology or a deliberate invariant, and would silently break a downstream behavior if "cleaned up" without a parity case to catch the regression.

This list intentionally separates correct-but-weird scar tissue (preserve) from defects that happen to be load-bearing (preserve in the parity corpus first, fix later, both annotated under vNext implication). The known-bad defects from docs/BACKLOG.md belong in a separate known-bad memo; only the ones that double as scar tissue (a guard exists, or a test enshrines the wrong value) are included here.

---

## ST-001: font-size:0 alone must NOT hide an element

Location:
- edgarpack/parse/html_clean.py:84-100 (is_hidden_style; font-size guard at 95-99)
- tests/fixtures/s1_font_size_zero_wrapper.html

Looks weird because:
- font-size:0 is the textbook hidden-text / SEO-cloaking signal, yet the code explicitly refuses to treat it as hidden unless paired with width/height/opacity == 0. A separate guard also stops border-width:0 from triggering width:0 hiding.

Possible real-world reason:
- Modern SEC S-1 renderers (Cerebras-era, eToro) use font-size:0 as a CSS reset on the outer page-wrapper div while the visible body lives inside; border-width:0 similarly appears on wrappers holding the whole body. Treating either as hidden collapsed multi-megabyte filings to a few hundred chars.

Evidence:
- code: html_clean.py:95-99 ("font-size:0 is only a hide signal when paired with another zero-size cue") confirmed on disk
- tests: tests/test_html_clean_s1_wrapper.py (exact, offline); fixtures s1_font_size_zero_wrapper.html

Risk if removed:
- S-1/F-1 filings from modern renderers silently lose their entire body; query/distill/diff all see empty packs. A naive substring match on "width" would also hide border-width:0 wrappers.

Current coverage:
- Strong: tests/test_html_clean_s1_wrapper.py pins font-size:0 wrapper, border-width:0, width:0/height:0, plus classic cloaking still hidden.

Needed corpus/parity case:
- A registration pack built from the eToro/Cerebras-style wrapper HTML asserting non-empty filing.full.md, plus a negative case where classic display:none cloaking is still removed.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a named "page-wrapper reset" heuristic distinct from the hidden-element detector).

Confidence:
- high

---

## ST-002: Zero and out-of-range colspan in malformed financial tables

Location:
- edgarpack/parse/md_render.py:313-317 (_parse_span_attr), 358-377 (grid builder)
- tests/fixtures/tsm_2006_malformed_span_table.html

Looks weird because:
- _parse_span_attr clamps colspan/rowspan to max(1, int) and the grid builder tolerates colspan='0' and oversized colspans on rows with fewer real cells.

Possible real-world reason:
- A real TSM 2006 20-F filing carries <td colspan='0'> and mismatched colspans. Browsers render colspan=0 as 1; the renderer must not crash or mis-align the NT$/US$ currency columns under their headers.

Evidence:
- code: md_render.py:313-317
- tests: tests/test_md_render.py:119 (exact, offline); fixture tsm_2006_malformed_span_table.html (colspan='0' near line 28)

Risk if removed:
- Financial tables in older/foreign filings shift columns, putting numbers under the wrong currency/period header. This corrupts which value sits under which header, the worst failure for a cited-value product.

Current coverage:
- Good: tests/test_md_render.py:119 pins the malformed-span case.

Needed corpus/parity case:
- Pack-build parity over a malformed-span 20-F fixture asserting column-to-header alignment in the rendered markdown table.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an explicit table-grid normalizer with documented clamping rules).

Confidence:
- high

---

## ST-003: INDEX heading treated as Table of Contents (TOC state machine)

Location:
- edgarpack/parse/sectionize.py:605-607, 653-655 (INDEX fullmatch + arming)
- edgarpack/parse/md_polish.py:12-15 (_TOC_HEADING_RE)

Looks weird because:
- Two different heading words ("INDEX" and "Table of Contents") arm the same TOC-skip machinery, and INDEX is matched only as a full-line token.

Possible real-world reason:
- Some filers title their TOC "INDEX" rather than "Table of Contents". Matching INDEX too loosely would clobber a real "INDEX TO FINANCIAL STATEMENTS" section.

Evidence:
- code: sectionize.py:605-607 (re.fullmatch INDEX), md_polish.py:_TOC_HEADING_RE
- memory: MEMORY.md Sectionizer Gotchas ("Some filings use INDEX heading instead of Table of Contents")
- backlog: docs/BACKLOG.md item 2 flags the prefixed-INDEX miss as a deferred defect

Risk if removed:
- INDEX-style filings mint phantom sections from their TOC rows, or a real Index-to-Financial-Statements section is wrongly suppressed. Section ids drift, breaking diff section matching.

Current coverage:
- Partial: test_md_polish.py:30 (INDEX dedup); the sectionize INDEX-arming path and the "## INDEX" prefixed-heading miss have weaker coverage.

Needed corpus/parity case:
- Sectionize parity over a filing whose TOC is titled INDEX (bare and "## INDEX" forms) plus a filing with a real "INDEX TO FINANCIAL STATEMENTS" section, asserting canonical section ids.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a single TOC-marker vocabulary normalized before the state machine, fixing the prefixed-INDEX gap). Requires a PARSER_VERSION bump + fixture regen.

Confidence:
- high

---

## ST-004: TOC table header rows ("Page" / empty cells) tolerated so they do not disarm the state machine

Location:
- edgarpack/parse/sectionize.py:624-632 (benign-header branch)
- edgarpack/parse/sectionize.py:850-909 (_is_toc_stub / _filter_toc_stubs second pass)

Looks weird because:
- A special branch tolerates blank/Page-only rows before the first real TOC row, and a SECOND post-pass re-filters TOC-stub sections after find_sections already skipped the TOC.

Possible real-world reason:
- TOC tables often open with a header row of empty cells and a "Page" column; without tolerance the state machine treats it as content and stops skipping. The second filter exists because split tables and odd headers sometimes defeat the line-by-line skip, leaking ITEM headings from inside the TOC.

Evidence:
- code: sectionize.py:624-632, 850-909 (docstring: "when the TOC state machine failed to skip")
- tests: tests/test_sectionize.py:80 (header row + Page column), :117 (blockquote TOC rows do not mint duplicates)
- memory: MEMORY.md Sectionizer Gotchas

Risk if removed:
- Duplicate phantom sections minted from TOC entries; duplicate ids proliferate; diffs polluted by content-free TOC-row sections.

Current coverage:
- Header-row tolerance tested exactly; the stub filter is tested only indirectly via the blockquote case.

Needed corpus/parity case:
- A split/multi-part TOC fixture (Part I table, blank line, Part II table with its own Page header) asserting no phantom sections and stable canonical ids. This is also docs/BACKLOG.md item 1 (multi-part TOC disarm).

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a dedicated TOC-region detector rather than two cooperating passes).

Confidence:
- high

---

## ST-005: Cross-reference sentences rejected as ITEM titles

Location:
- edgarpack/parse/sectionize.py:479-545 (phrase blacklist + paren-citation + Regulation-S-K guards)

Looks weird because:
- A long phrase blacklist ("for additional information", "as discussed in", "of this annual report") plus paren-citation guards reject matches that the ITEM regex already accepted.

Possible real-world reason:
- Body prose like "See Item 1A. Risk Factors for additional information..." matches ITEM_PATTERN but is a sentence, not a heading. Promoting it creates a duplicate Risk Factors section with a garbage title.

Evidence:
- code: sectionize.py:479-545
- tests: tests/test_sectionize.py:216 (covers edgarpack-zfr cross-ref rejection), :141-163

Risk if removed:
- 10-K MD&A and Risk Factors sections get duplicated with cross-ref-fragment titles, corrupting diffs and citation-addressable ids.

Current coverage:
- Strong: tests/test_sectionize.py:216 (exact, offline).

Needed corpus/parity case:
- A 10-K with multiple in-body "See Item 1A..." cross-references asserting exactly one Risk Factors section with the canonical title.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a heading-vs-sentence classifier rather than a growing blacklist).

Confidence:
- high

---

## ST-006: Inline-flattened PART/ITEM concatenation recovery (min start offset 20)

Location:
- edgarpack/parse/sectionize.py:380-391 (_is_inline_heading_boundary), 741-756, 796-822

Looks weird because:
- Inline ITEM/PART scans skip matches in the first 20 chars and require a heuristic boundary (prev char lowercase/digit/punct, or PART before a roman numeral).

Possible real-world reason:
- When dense HTML divs are stripped, multiple headings collapse onto one line ("...InformationItem 1. Financial Statements"). The renderer cannot fully separate them; sectionize recovers them inline but must avoid re-matching the proper leading heading (start < 20) and avoid mid-word false hits.

Evidence:
- code: sectionize.py:380-391
- tests: tests/test_sectionize.py:41 (2Part I...Item 1 concatenation)

Risk if removed:
- Filings whose headings flatten onto one line lose all but the first section.

Current coverage:
- Exact: tests/test_sectionize.py:41.

Needed corpus/parity case:
- A filing whose div structure flattens multiple ITEM/PART headings onto a single line, asserting each becomes its own section.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later; ideally fix upstream so headings never flatten, making this recovery unnecessary.

Confidence:
- high

---

## ST-007: S1_ANCHOR_TITLES whitelist + TOC-anchor heading injection for headingless S-1 renderers

Location:
- edgarpack/parse/sectionize.py:73-135 (S1_ANCHOR_TITLES frozenset, curly-apostrophe normalization)
- edgarpack/parse/s1_headings.py:160 (inject_s1_headings, runs BEFORE clean_html)

Looks weird because:
- A hardcoded ~60-entry frozenset of prospectus section titles drives S-1 heading detection, and headings are reconstructed by reading TOC href=#anchor links and injecting <h2> before matching body ids, all before clean_html strips id attributes.

Possible real-world reason:
- Cerebras-era S-1 bodies use absolute-positioned divs with no large-font headings; the only structural cue is TOC anchors. Foreign-issuer F-1s use distinctive section names (Enforcement of Civil Liabilities, Operating and Financial Review and Prospects) absent from domestic S-1s. Curly apostrophes in "Management's" must match.

Evidence:
- code: sectionize.py:73-135, s1_headings.py:160 (and pack/build.py:113 ordering)
- tests: tests/test_sectionize_s1.py, tests/test_s1_headings.py (18 cases incl legacy <a name=> anchors, heading lift before enclosing <p>)

Risk if removed:
- F-1/20-F-style foreign filings and modern-renderer S-1s lose most or all sections; the financial-data section becomes unfindable. The step-order coupling (inject before clean) is itself load-bearing: clean_html strips the id/name attributes the injector targets.

Current coverage:
- Strong offline: test_sectionize_s1.py + test_s1_headings.py.

Needed corpus/parity case:
- A headingless modern-renderer S-1 (TOC-anchor only) and a foreign-issuer F-1 with non-domestic section names, asserting the expected section set. The active F-1 branch keeps expanding S1_ANCHOR_TITLES.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an authoritative prospectus-section vocabulary with a documented add-path, plus an explicit injector-before-clean stage contract).

Confidence:
- high

---

## ST-008: Per-share LTM degrades to annual rather than additive math

Location:
- edgarpack/query/periods.py:409 (_is_per_share_metric), 577-619 (per-share LTM degrade + ltm_degraded diagnostic)

Looks weird because:
- EPS/per-share LTM does NOT compute mrp + lfy - mrp_prior; it returns the latest annual value and emits ltm_degraded, breaking the usual three-component LTM contract.

Possible real-world reason:
- Per-share figures are non-additive; you cannot sum quarterly EPS across a split-adjusted boundary, so additive LTM would produce a mathematically wrong number.

Evidence:
- code: periods.py:409, 577-619
- tests: tests/test_periods.py:361, 2297, 2316
- backlog/memory: documented as a previously-shipped P1 bug that is now FIXED and pinned

Risk if removed:
- Reintroduces nonsense EPS LTM values; this is a fixed regression that the suite now guards.

Current coverage:
- Strong: tests/test_periods.py pins None-not-additive plus the ltm_degraded diagnostic.

Needed corpus/parity case:
- A real filer EPS LTM query asserting the annual value + ltm_degraded diagnostic, not an additive sum, including across a split-adjusted period.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a per-metric "additive" flag on MetricMeta driving the LTM path rather than a name heuristic).

Confidence:
- high

---

## ST-009: Balance-sheet LTM intentionally bypasses the LTM component-citation invariant

Location:
- edgarpack/query/periods.py:621-642 (instant-metric early return; sort by (end, filed))
- edgarpack/query/periods.py:483 (_assert_ltm_invariant it bypasses)

Looks weird because:
- For instant (non-duration) metrics, LTM returns the latest period-end balance which may carry fiscal_period Q1/Q2/Q3 and deliberately does NOT satisfy the {mrp, lfy, mrp_prior} invariant that an autouse test harness re-asserts suite-wide.

Possible real-world reason:
- Balance-sheet metrics are point-in-time instants; the latest balance IS the LTM-end balance, so no three-component flow math applies. Sorting by (end, filed) rather than (filed, end) keeps an amended old balance from displacing the latest.

Evidence:
- code: periods.py:621-642 (comment "intentionally bypass the LTM invariant")
- tests: test_ltm_instant_returns_latest, test_amended_old_balance_does_not_displace_latest
- contract: conftest.py:55 _ltm_citation_contract_harness enforces the invariant on every test, so the bypass must be explicit

Risk if removed:
- Mid-year balance-sheet LTM queries crash on the invariant assertion; or an amended prior balance displaces the current one.

Current coverage:
- Good: instant-return and amended-balance cases tested.

Needed corpus/parity case:
- A balance-sheet LTM query (e.g. total_assets) mid-fiscal-year asserting the latest instant value with no ltm_incomputable diagnostic, plus an amended-prior-period case.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (split the LTM contract into flow-LTM vs instant-LTM as two named code paths).

Confidence:
- high

---

## ST-010: Standalone-quarter threshold is 100 days and full-fiscal-year window is 350-380 days

Location:
- edgarpack/query/periods.py:379-406 (_is_standalone_quarter / _is_cumulative_quarter, 100-day threshold)
- edgarpack/query/periods.py:35-36, 316, 526 (_FULL_YEAR_MIN_DAYS=350 / _MAX=380, Q4 short-circuit)

Looks weird because:
- A "standalone ~3-month quarter" is defined as <= 100 days (not 90), and a "full fiscal year" is 350-380 days (not 365). Magic constants gate whether a Q4 short-circuits LTM to the annual value.

Possible real-world reason:
- 4-4-5 retail calendars and 13-week quarters produce quarters that are not exactly 90 days; 52/53-week fiscal years and leap years make a year span 364-371 days. SEC also files both 9-month-cumulative and 3-month-standalone entries for the same Q3 end date, which must be disambiguated.

Evidence:
- code: periods.py:379-406 (confirmed on disk), 526
- tests: test_mrq_picks_standalone_not_cumulative; test_ltm_q4_from_10k_short_circuits_to_annual; test_standalone_q4_stub_raises

Risk if removed:
- MRQ picks cumulative YTD as if it were a single quarter; the LTM subtrahend subtracts the wrong span; a 53-week year or transition-period filing is rejected as a stub, or a 9-month YTD stub is accepted as full-year LTM.

Current coverage:
- Strong across multiple periods tests.

Needed corpus/parity case:
- A 4-4-5 / 53-week filer (retailer) MRQ and LTM query, plus a transition-period or amended-stub filing, asserting standalone-vs-cumulative selection and the Q4 short-circuit.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (named fiscal-calendar tolerances with documented derivation, not bare magic numbers).

Confidence:
- high

---

## ST-011: mrq-N / annual-anchored selectors fail CLOSED when the exact target fiscal year is missing

Location:
- edgarpack/query/periods.py:443-470, 938 (_pick_anchor_quarter, mrq-N)
- edgarpack/query/financials.py:393 (exact FY matching, period_mismatch diagnostic)

Looks weird because:
- Returns None (plus period_mismatch / ltm_incomputable) rather than the nearest available quarter or fiscal year, even when a near-year value exists.

Possible real-world reason:
- Returning a nearer fiscal year under an ltm-2/mrq-3/lfy-N label silently mislabels a different window; the product promise forbids presenting a substitute as the requested period.

Evidence:
- code: periods.py:455 (docstring "Returning a nearer year here would mislabel"), financials.py:393
- tests: test_mrq_n_fails_closed_when_target_fy_missing; test_periods.py:1809, 1863, 2060
- history: this is the FIXED silent-degrade family from the 2026-06-09 review

Risk if removed:
- Reintroduces the silent-degrade bug class: a value labeled lfy-2 actually being the lfy-1 number.

Current coverage:
- Strong: multiple fail-closed tests.

Needed corpus/parity case:
- An offset query (ltm-2, mrq-3, lfy-N) against a filer that lacks the exact requested fiscal year, asserting None + a typed diagnostic, never a near-year substitute.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later; the fail-closed contract is core to None-not-guess.

Confidence:
- high

---

## ST-012: _extract_values breaks on the first non-empty unit in a fixed priority order (USD, shares, USD/shares, pure)

Location:
- edgarpack/query/periods.py:195-208 (_extract_values), 223 (_unit_for_concept mirror)

Looks weird because:
- It iterates a fixed unit priority and breaks on the first unit key with any values, ignoring all other units entirely; only if none of those four exist does it fall back to an arbitrary unit.

Possible real-world reason:
- SEC companyfacts can report the same concept under multiple units (a concept tagged both USD and pure). Picking one unit deterministically avoids mixing incompatible scales; USD-first matches the financial-statement default.

Evidence:
- code: periods.py:195-208, 223

Risk if removed:
- Could return shares-denominated values where USD is expected, or mix units across periods within one series.

Current coverage:
- Implicit only (passing tests); no explicit multi-unit-conflict test found. Coverage gap.

Needed corpus/parity case:
- A concept that legitimately reports under two units in companyfacts, asserting the USD-first deterministic pick and that no period mixes units.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an explicit unit-resolution policy with a test pinning the priority order).

Confidence:
- medium

---

## ST-013: Self-heal shape guards (forbidden-token lists, per-share rejection, contract-liability squash)

Location:
- edgarpack/query/self_heal.py:68-83 (_METRIC_SHAPE_RULES revenue forbidden set), 199-238 (_concept_shape_matches_metric, per-share + unit + squash checks)

Looks weird because:
- Long hardcoded forbidden-token sets (liability, deferred, unearned, obligation, segment, geographic) plus several "contractwithcustomerliability"-style squash string checks, plus a {per, share} rejection unless the metric is eps_/shares/_per_share.

Possible real-world reason:
- Real XBRL filings tag ContractWithCustomerLiabilityRevenueRecognized, RemainingPerformanceObligation, and segment/geographic revenue breakdowns. Fuzzy token matching on "revenue" would otherwise grab a deferred-revenue or single-segment number and confidently mislabel it as total revenue. Per-share concepts share token roots with absolute metrics.

Evidence:
- code: self_heal.py:68-83, 199-238
- tests: tests/test_self_heal.py (revenue rejects ContractWithCustomerLiabilityRevenueRecognized; gross_profit rejects balance-sheet gross); applied at BOTH discovery and cached-read time (self_heal.py:549)

Risk if removed:
- Self-heal returns economically-wrong values (deferred revenue as revenue, EPS as an absolute metric) under a clean citation, violating the citation-honesty promise. A poisoned cache row could resurface.

Current coverage:
- Strong: shape-guard rejection tests including the cached-read path.

Needed corpus/parity case:
- A filer (e.g. Alphabet, Robinhood) whose companyfacts contain the trap concepts, asserting self-heal returns None or the correct concept, never the trap, both on first discovery and on cache read.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a curated concept-economics ruleset rather than ad-hoc token lists).

Confidence:
- high

---

## ST-014: LLM self-heal backend is chosen by import-time PATH scan (codex preferred over claude)

Location:
- edgarpack/query/self_heal.py:351-355 (_LLM_CMD set by shutil.which at import), 416 (_llm_propose subprocess)

Looks weird because:
- A module-level constant decides whether self-heal can call an LLM and which one, based on what is installed on the host; the same query self-heals via LLM on one box and falls back to fuzzy/None on another.

Possible real-world reason:
- Designed to be optional/offline-friendly: no backend means fuzzy-only, which is deterministic. The constant is monkeypatchable so tests force a known state.

Evidence:
- code: self_heal.py:351-355, 416 (hallucination guard: output must appear in the candidate set)
- tests: tests/test_self_heal.py (no-backend None, valid parse, hallucination reject) with subprocess patched

Risk if removed:
- Non-reproducibility across machines: the registry's source column ('llm' vs 'fuzzy') and possibly the returned value differ by host. Removing the optionality breaks offline use.

Current coverage:
- Backend-available and no-backend branches tested; the real subprocess is never exercised offline.

Needed corpus/parity case:
- Pin fuzzy-only (backend absent) as the deterministic baseline for any parity corpus; treat the LLM path as a separate gated lane.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an explicit, injectable resolver provider with a declared offline default, decoupled from PATH).

Confidence:
- high

---

## ST-015: AXP/issuer "revenue" resolves to ASC-606 Revenues, not the headline top line

Location:
- edgarpack/query/concepts.py:66-78 (revenue MetricMeta, concept order Revenues first; no issuer override)

Looks weird because:
- query AXP revenue returns ~$41B (us-gaap:Revenues) not the reported ~$72B "total revenues net of interest expense"; the citation is honest but the metric label is misleading.

Possible real-world reason:
- Banks/card issuers report revenue net of interest expense on the income statement, a line with no single clean us-gaap tag. The generic Revenues tag exists but covers only contract revenue; METRIC_MAP has no per-filer override.

Evidence:
- memory: axp-revenue-metric-gotcha.md (AmEx CIK 0000004962, FY2025 $41.3B vs $72.2B)
- code: concepts.py:66-78 (no issuer override)

Risk if removed:
- This is existing behavior to preserve and flag, not remove. Provenance is correct; the interpretation diverges. A rewrite must consciously decide whether to add an issuer override.

Current coverage:
- None in tests (documented in memory only). Coverage gap.

Needed corpus/parity case:
- An AXP (or other card-issuer/bank) revenue query, pinning the current ASC-606 Revenues resolution and a scope-warning, so any future issuer-override is a deliberate change.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an issuer-class metric override + a scope warning surfaced to the user).

Confidence:
- high

---

## ST-016: Pre-IPO EDGAR name search hits an undocumented endpoint with an issuer-name substring guard

Location:
- edgarpack/sec/tickers.py:224 (_EDGAR_SEARCH_URL efts.sec.gov/LATEST/search-index), 225-230 (forms list omits S-1/A), 282-300 (content-only-match rejection)

Looks weird because:
- Resolution for pre-IPO filers uses entityName= (not q=) against an undocumented internal EDGAR search backend, deliberately omits S-1/A and F-1/A from the forms filter, and rejects any hit whose display_names do not contain the query as a substring.

Possible real-world reason:
- Pre-IPO filers have no company_tickers.json entry and no companyfacts; this search backend is the only programmatic name->CIK path. The slash in "S-1/A" breaks SEC's forms-list parser (HTTP 500), and SEC indexes amendments under their base form anyway. The substring guard stops EDGAR full-text content matches (a WhiteFiber S-1 mentioning Cerebras) from resolving "Cerebras" to WhiteFiber's CIK.

Evidence:
- code: tickers.py:224-300 (explicit comments warning against q= and against S-1/A in the forms list)
- tests: tests/test_tickers_name_resolution.py (content-only rejection); tests/test_resolve_live_identity.py (gated live, pins Cerebras/WhiteFiber/Klarna CIKs)

Risk if removed:
- Pre-IPO S-1 resolution breaks entirely; adding S-1/A zeroes out amendment-only issuers; dropping the substring guard reintroduces the WhiteFiber-instead-of-Cerebras wrong-CIK regression that silently flows into citations.

Current coverage:
- Mocked unit tests + a gated live regression test.

Needed corpus/parity case:
- Pin the WhiteFiber-vs-Cerebras content-only-rejection case offline (mocked EDGAR response), and document the live endpoint dependency as a gated lane.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (the undocumented endpoint dependency and the substring guard are an accepted long-term risk to revisit).

Confidence:
- high

---

## ST-017: companyfacts 404 maps to {} (no-XBRL) while every other failure raises XBRLFetchError

Location:
- edgarpack/sec/xbrl.py:29-82 (fetch_company_facts; 404 -> {}, else XBRLFetchError)

Looks weird because:
- Two outwardly-similar "no data" outcomes are deliberately kept distinguishable: a real SEC 404 returns an empty dict with no diagnostic, but a timeout/5xx/TLS/parse error raises and surfaces as a per-metric layer_a_fetch_error.

Possible real-world reason:
- A 404 means the filer genuinely has no XBRL (common for pre-IPO/S-1). A transport error means the value is unknown, not absent. Collapsing them into one N/A would let a network blip read as "this filer has no revenue".

Evidence:
- code: xbrl.py:68-76
- docs: ARCHITECTURE.md:88, CLAUDE.md ("No silent imputation")

Risk if removed:
- Violates the core no-silent-imputation invariant; a transient outage becomes indistinguishable from a real absence.

Current coverage:
- GAP: no dedicated offline unit test for the 404-vs-error split; only exercised indirectly by live tests. The single most load-bearing no-imputation boundary in the SEC slice is untested offline.

Needed corpus/parity case:
- An offline test that mocks a 404 (asserts {} and no diagnostic) and separately mocks a 500/timeout (asserts XBRLFetchError -> layer_a_fetch_error diagnostic), confirming the two never collapse.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later; this invariant deserves a first-class offline regression test it currently lacks.

Confidence:
- high

---

## ST-018: Submissions older-page fetch failures are logged-and-skipped, so "not found" only means "exhausted reachable pages"

Location:
- edgarpack/sec/submissions.py:243-254 (_iter_submission_pages skip-on-fault), 280-302 (get_latest_filing reads recent window only, no pagination)

Looks weird because:
- A failed older-page fetch is swallowed and skipped rather than raised, so an exhausted iterator is the not-found signal; and get_latest_filing deliberately never paginates, unlike list_filings.

Possible real-world reason:
- High-volume filers (META) age accessions out of the recent window within weeks. The no-imputation contract says callers must not assume every page was reachable. The "latest" of a periodic form is always in the recent window for an active filer, so paginating get_latest_filing would add latency for no benefit.

Evidence:
- code: submissions.py:243-254, 280-302
- tests: tests/test_submissions_pagination.py (recent-only, recent+older, fetch-failure skip)

Risk if removed:
- Conflating a skipped page with a genuine absence would falsely report a deep-paginated filing as missing; making get_latest_filing paginate would slow the hot path.

Current coverage:
- Good for the skip and pagination behaviors; the aged-out get_latest_filing case is not directly tested.

Needed corpus/parity case:
- A high-volume filer (META) aged-out accession lookup via list_filings (deep pagination) and a get_latest_filing recent-window case, asserting the not-found-vs-skipped distinction.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an explicit "pages_unreachable" signal distinct from "no match").

Confidence:
- high

---

## ST-019: Manifest source.fetched_at is the filing date, not the real fetch time

Location:
- edgarpack/pack/manifest.py:151-157, 175-178 (both generated_at and source.fetched_at forced to filing_date midnight UTC)

Looks weird because:
- A field literally named fetched_at does not record when bytes were fetched; it records the filing date at midnight UTC.

Possible real-world reason:
- Determinism: real fetch time would make every rebuild differ, breaking the byte-identical contract and the SHA256 cache keys that downstream caches rely on.

Evidence:
- code: manifest.py:151 (comment "Determinism: use a stable timestamp derived from the filing date")
- tests: test_create_manifest_uses_stable_timestamp (asserts both equal datetime(2024,1,15))

Risk if removed:
- Every rebuild produces a different manifest; the determinism test fails; caches keyed on manifest hash thrash.

Current coverage:
- Tested (test_pack_build.py).

Needed corpus/parity case:
- A double-build of the same filing asserting byte-identical manifest except a real (non-hashed) fetch timestamp if one is ever added separately.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (record a real fetch timestamp in a non-hashed sidecar field while keeping the deterministic stable timestamp).

Confidence:
- high

---

## ST-020: Token counts (and chunk boundaries) are non-deterministic when tiktoken's encoding asset availability differs

Location:
- edgarpack/parse/tokenize.py:48-55 (len//4 fallback when tiktoken/cl100k_base unavailable)
- edgarpack/pack/chunks.py:167 vs 181 (boundary algorithm branches on has_tiktoken())

Looks weird because:
- The same section yields different chunk boundaries (and thus different content-hashed chunk_ids and a different manifest tokens_total) depending on whether tiktoken's encoding asset is importable, silently switching the whole chunking algorithm.

Possible real-world reason:
- A graceful fallback for offline/sandboxed/CI environments where tiktoken cannot download its vocab; the alternative is a hard crash. tiktoken is a core dependency so in normal installs the fallback never fires.

Evidence:
- code: tokenize.py:48-55, chunks.py:167/181
- backlog/memory: docs/BACKLOG.md item 4 (tiktoken determinism) flagged as a deferred finding needing a PARSER_VERSION bump

Risk if removed:
- Removing the fallback breaks offline use; keeping it means chunks.ndjson and tokens_total are NOT byte-stable across environments. The live determinism test runs where tiktoken is always present, so it never catches this.

Current coverage:
- Both branches tested in isolation, but cross-branch equivalence is not, and there is no offline byte-determinism test feeding fixed input through all six parse steps.

Needed corpus/parity case:
- A determinism parity case that pins "tiktoken present" as a precondition, plus an explicit assertion that a cold-cache fallback produces different chunk bytes (so the precondition is documented, not assumed).

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (declare tiktoken a hard determinism precondition, or remove tokens_total from the hashed surface).

Confidence:
- high

---

## ST-021: _simplify_complex_tables reshapes wide/long financial tables into dot-leader blockquotes

Location:
- edgarpack/parse/md_polish.py:293-371 (>6 cols or >120-char rows converted to "> label .... value / value")

Looks weird because:
- Dense multi-period financial tables, the exact data query/distill want, are converted from GFM tables into label/value blockquote prose that downstream numeric extraction must re-parse.

Possible real-world reason:
- Dense tables blow past markdown table readability and token budgets; the blockquote form keeps label/value association and is more readable for humans/LLMs. A lossy, opinionated tradeoff.

Evidence:
- code: md_polish.py:293-371
- tests: tests/test_md_polish.py:206 (exact, offline)

Risk if removed:
- Wide tables render as unreadable 12-column GFM; but keeping the conversion makes S-1 financial extraction and diff parse the leader-dot prose, and column-to-value association can be ambiguous when cells are empty.

Current coverage:
- The conversion is tested; the downstream re-extraction cost is not measured.

Needed corpus/parity case:
- A wide financial table fixture asserting the blockquote form AND that the S-1 deterministic extractor still recovers the correct numbers from it.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (keep a structured table alongside the prose form so machine extraction does not re-parse leader dots).

Confidence:
- medium

---

## ST-022: HKEX column-count structural guard emits NO fact on a year-header mismatch (the column-shift P0)

Location:
- edgarpack/hk/extract.py:228-280 (_PLAIN_TOKEN_RE, _parse_columns_plain, note-ref column drop at 274-279)

Looks weird because:
- The plain-row parser juggles comma-less integers, parenthesized decimals, en-dash/hyphen dashes, label-date stripping, and a leading bare 1-2 digit note-reference column, with a hard column-count gate that silently returns None (no fact) when parsed columns != year-header count.

Possible real-world reason:
- Real HKEX/IFRS prospectus tables mix sub-1,000 values (no comma), parenthesized decimals, label hyphens ("TOTAL EQUITY - DEFICIT"), embedded dates ("ended 31 December 2024"), and bare-integer note references ("Revenue 4 57,409"). Any of these shifted every later year's value left/right under a clean citation, returning the WRONG year's number (reproduced twice live in Zhipu).

Evidence:
- code: extract.py:228-280 (note-ref drop confirmed on disk at 274-279)
- git: commit 8a3bb61 (2026-06-09 column-shift fix)
- tests: test_commaless_values_keep_year_alignment, test_parenthesized_decimal_is_negative, test_label_hyphen_is_not_a_dash_column, test_column_count_mismatch_emits_no_fact
- golden: tests/eval/china_golden.yaml:227 (Zhipu total_equity note: "prior value was the FY2023 figure")

Risk if removed:
- Silent financial misattribution under a trustworthy citation: a FY2024 query returns the FY2023 number. The single worst failure mode for a provenance product.

Current coverage:
- Strong: 9 regression tests + golden assertions pinning the corrected Zhipu series.

Needed corpus/parity case:
- The committed Zhipu/MiniMax HK packs already serve this; keep the golden total_equity series pinned and add a synthetic note-reference-column row.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (silence-over-misattribution is the right default; make the column-count contract a documented invariant).

Confidence:
- high

---

## ST-023: HKEX/SSE company currency and accounting standard come from a hardcoded dict, not the filing

Location:
- edgarpack/hk/adapter.py:12-43 (_COMPANY_META, 6 stock codes), 139-140 (unknown codes default to CNY/HKFRS)
- edgarpack/sse/annual_facts.py (4-metric extraction, source_document hardcoded)

Looks weird because:
- Reporting currency and accounting standard for the entire HKEX universe come from a literal 6-entry dict; unknown codes silently default to CNY/HKFRS. Alibaba/JD are tagged IFRS while the rest are HKFRS, so the distinction is load-bearing.

Possible real-world reason:
- HKEX prospectus PDFs expose no machine-readable currency/standard field; the author pinned the known demo filers by hand. MiniMax reports in USD, Zhipu in CNY, so a wrong default corrupts every value and FX conversion.

Evidence:
- code: adapter.py:12-43, 139-140
- tests: test_build_hk_pack_uses_meituan_metadata; no test for the unknown-code default
- backlog: docs/BACKLOG.md items 7-8 (HK LLM unit-scaling and fabricated non-Dec fiscal periods are adjacent metadata defects)

Risk if removed:
- A new HKEX filer in a non-CNY currency is silently mislabeled CNY, corrupting values and FX. The IFRS-vs-HKFRS split (Alibaba/JD) is also load-bearing for standard reporting.

Current coverage:
- Partial: known-filer metadata tested; the unknown-code default and the IFRS path are gaps.

Needed corpus/parity case:
- An unknown-stock-code HK build asserting it does NOT silently claim CNY/HKFRS, plus an IFRS filer (Alibaba/JD) asserting the standard, plus the MiniMax USD case.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (derive currency/standard from the filing or from universe.toml, not a hardcoded dict).

Confidence:
- medium

---

## ST-024: SSE/A-share 6-digit code routing short-circuits SEC resolution

Location:
- edgarpack/cli.py:115-133, 2447-2448, 3823-3824 (looks_like_china_a_share_code gate, _synthetic_sse_company)
- edgarpack/identity.py:66-81 (_source_for: ticker.isdigit() and len==6 and spec.stock_code)

Looks weird because:
- A 6-digit numeric token (688696, 301536) is routed to the SSE/CNINFO path and never tries SEC, even though some CIKs are numeric. Universe lookup runs before the A-share-code guard, and the first-digit (6 -> Shanghai, else Shenzhen) decides the CNINFO market.

Possible real-world reason:
- China A-share stock codes collide with numeric inputs; companyfacts will not exist for them, so the heuristic routes them to the SSE build path and tells the user to build an SSE pack. Registered SSE filers must route to their pack; only unregistered codes hit the "add to universe.toml" error.

Evidence:
- code: cli.py:115-133, identity.py:66-81
- tests: tests/test_cli_identify.py (China branch), test_cli_identity_fallthrough.py
- doc discrepancy: docs/research/2026-04-27-xgimi-china-filer-smoke.md records bare 688696 then treated as SEC CIK 0000688696 -> 404 -> N/A, while the later China tracker claims raw codes route correctly

Risk if removed:
- A genuine numeric CIK matching the A-share pattern could be misrouted; removing it sends A-share codes into a fruitless SEC lookup. The heuristic is load-bearing for cross-market routing.

Current coverage:
- Good for the routing branches; the docs-vs-docs discrepancy on current behavior is unresolved.

Needed corpus/parity case:
- Resolve which doc reflects current code, then pin: bare 688696 routes to SSE (not SEC CIK), a registered SSE filer routes to its pack, and an unregistered code yields the build-sse hint. Also confirm no real numeric CIK collides.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an explicit market-routing layer keyed on listing metadata rather than a numeric-shape heuristic).

Confidence:
- medium

---

## ST-025: Translation never delegates number magnitude to the LLM; fails closed on validation error

Location:
- edgarpack/china/translate/numbers.py (wan/yi tagging to <<NUM_xxx>> placeholders, restored post-call)
- edgarpack/china/translate/router.py:401 (_translate_table_cell deterministic ladder), 368 (split-date repair)
- edgarpack/cli.py:1903-1908, 2196-2249 (resume-by-default; full English only on zero failures)

Looks weird because:
- A long deterministic regex ladder (reporting period, date, numeric amount, percent) runs before any LLM call per table cell; numbers are tagged out before the model sees them; and a partial/failed section deletes its .en.md and blocks filing.full.en.md, with resume-by-default when failed_sections is non-empty.

Possible real-world reason:
- A wan/yi error is a 10,000x mistake, so magnitude is never trusted to the LLM. Table cells are where number and date corruption are most likely, so they are converted deterministically. A partial English filing would be silently incomplete, violating the no-silent-degrade principle; the cache absorbs the rework so resume is cheap. pymupdf4llm splits "12月" across cells, needing date-cell repair.

Evidence:
- code: cli.py:1903-1908, 2196-2249; router.py:368, 401; numbers.py
- tests: tests/test_table_translation.py, tests/test_translation_validators.py, tests/test_translate_sse_artifacts.py
- docs: README.md:410 (fail-closed), china-lens tracker

Risk if removed:
- A 10,000x magnitude error or a partial English filing ships under the same provenance as a correct one. The split-date repair is needed or the literal-token validator rejects valid date rows and fails the section closed.

Current coverage:
- Strong for validators/cache/table cells; the split-date repair path lacks a dedicated test.

Needed corpus/parity case:
- The Unitree 301536 partial-translation resume case (noted in memory), plus a wan/yi magnitude case asserting deterministic conversion, plus a split-date-cell row.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a named "deterministic-first, LLM-for-prose-only" translation contract with explicit magnitude-protection guarantees).

Confidence:
- high

---

## ST-026: S-1 deterministic table parser hardcodes currency=USD and is_audited=True

Location:
- edgarpack/query/s1_financials.py:613-614 (deterministic emitter stamps currency="USD", is_audited=True)
- edgarpack/query/s1_financials.py:295-301 (scale assumes raw dollars when no "in thousands/millions" preamble)

Looks weird because:
- The deterministic summary-table path always emits USD and is_audited=True regardless of the filing's actual reporting currency or whether the row is interim/unaudited, while the LLM path faithfully preserves the model-reported currency and audit status. The module docstring promises ISO4217 awareness the deterministic path does not deliver.

Possible real-world reason:
- The deterministic parser was hardened for US-domestic S-1s (Cerebras, Fervo, Neutron) whose summary tables are USD. F-1 foreign filers (Klarna SEK) report in non-USD, for which this path would mislabel currency. A v1 simplification that has not caught up to F-1.

Evidence:
- code: s1_financials.py:613-614 (confirmed on disk), 295-301
- tests: all deterministic-parse fixtures are USD; no non-USD deterministic-table test
- backlog: this is the active F-1 branch's most likely gap (SCHEMA_VERSION jumped 1->8)

Risk if removed (or "fixed" naively):
- Foreign-filer F-1 values carry wrong currency provenance, violating the provenance promise; interim rows get is_audited=True. A table omitting the scale preamble but reporting in thousands is under-scaled 1000x silently.

Current coverage:
- USD calendar-year US filers only; the non-USD and missing-scale cases are gaps.

Needed corpus/parity case:
- A foreign-filer F-1 (SEK/EUR) deterministic-table extraction asserting the correct currency and audit status, plus a table with no scale preamble.

vNext implication:
- Preserve behavior for the US case, but maybe model it more explicitly later (thread the reported currency/scale/audit status through the deterministic emitter for F-1 parity). This is a defect that is currently load-bearing for the US path; pin the US behavior before fixing the foreign path.

Confidence:
- medium

---

## ST-027: Any Anthropic exception in S-1 extraction is reported as extraction_status='no_api_key'

Location:
- edgarpack/query/s1_financials.py:969-980 (bare except Exception -> status='no_api_key')

Looks weird because:
- extract_or_load_snapshot wraps the Haiku call in a bare except and unconditionally sets status='no_api_key', so an API outage, rate-limit, or 500 is indistinguishable from a genuinely missing key.

Possible real-world reason:
- The dominant failure in practice is a missing key (the offline lane has no ANTHROPIC_API_KEY), and the user-facing hint is the same actionable next step, so conflating saved a status taxonomy.

Evidence:
- code: s1_financials.py:969-980
- tests: missing-key case covered; no test for a transient API error

Risk if removed (or relied on):
- Hides transient API failures as "set your API key", conflicting with the no-silent-imputation invariant that distinguishes fetch-error from no-data. A retry-on-transient strategy cannot tell them apart.

Current coverage:
- Only the key-missing case.

Needed corpus/parity case:
- An offline test mocking a transient Anthropic failure asserting a distinct status from a truly-missing key.

vNext implication:
- Preserve the user-facing hint, but maybe model it more explicitly later (separate no_api_key from extraction_error so the retry/diagnostic story can branch).

Confidence:
- medium

---

## ST-028: S-1 source_sha256 cache key covers only the first 50KB of filing.full.md

Location:
- edgarpack/query/s1_financials.py:856-864 (_SOURCE_SCAN_CHARS = 50_000), 143 (_SECTION_CAP_CHARS = 50_000)

Looks weird because:
- Snapshot cache invalidation hashes only the first 50KB, but the financial-data section (and the deterministic table) can live deep in a multi-hundred-KB S-1. A re-parse that changes only the body past 50KB does not invalidate the cache.

Possible real-world reason:
- Performance plus the heuristic that the prospectus summary / selected financial data heading appears early; it matches the 50KB section cap used during extraction. Cheap, mostly-correct invalidation.

Evidence:
- code: s1_financials.py:856-864, 143
- tests: source_sha256 stability tests cover early-content changes only

Risk if removed (or relied on):
- A genuinely changed amendment whose diff is past 50KB serves a stale snapshot under a fresh-looking cache.

Current coverage:
- Early-content changes only; the past-50KB case is a gap.

Needed corpus/parity case:
- An amendment whose only change is a financial figure beyond the 50KB window, asserting the snapshot is recomputed (or documenting that it is not).

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (hash the located financial section, not a fixed byte prefix).

Confidence:
- medium

---

## ST-029: Diff overlap-rescue can marry topically unrelated paragraphs; numeric-boilerplate suppression can hide real dollar changes

Location:
- edgarpack/diff/text_diff.py:245 (match_score = max(sim, overlap*0.8))
- edgarpack/diff/text_diff.py:101-114 (_BOILERPLATE_TOKEN_PATTERN matches any 1-4 digit number)
- edgarpack/diff/text_diff.py:63-82 (distinctive-token floor, _DISTINCTIVE_MIN_PARAS=8)

Looks weird because:
- The match score admits paragraph pairs whose true Jaccard is below 0.5 (observed 0.38-0.48), so an expanded-but-same risk-factor paragraph stays MODIFIED rather than re-fragmenting into added+removed. Separately, a "$26.0B to $35.1B" sentence can be flagged boilerplate and disappear because the changed tokens are mostly digits. The distinctive-Jaccard ambient-legalese filter is skipped below 8 combined paragraphs.

Possible real-world reason:
- Risk-factor paragraphs expand with large insertions; pure Jaccard would mislabel an expanded-but-same paragraph as add+remove, inflating change counts. Date/quarter rollovers (2024->2025, Q4->Q1) are the dominant mechanical noise, and the broad numeric class was the cheap way to suppress them. Document frequency over a handful of paragraphs is noise, so the distinctive filter needs a floor.

Evidence:
- code: text_diff.py:245, 101-114, 63-82
- tests: test_diff_paragraphs_high_overlap_expansion_is_modified; test_ratio_based_boilerplate; test_distinctive_jaccard_falls_back_on_small_sections
- backlog: docs/BACKLOG.md items 3 (overlap forced marriages) and 12 (numeric over-suppression)

Risk if removed:
- Removing the overlap rescue re-fragments genuine expansions into false add/remove pairs; removing the numeric suppression resurfaces date-rollover noise; tightening the numeric class wrongly hides real $/%-adjacent deltas. The HTML report mitigates sub-0.5 pairs with a "rewritten N% similar" badge rather than an inline redline.

Current coverage:
- The wanted directions are tested; the documented misfires (unrelated marriages, hidden revenue change) are not.

Needed corpus/parity case:
- The CRWV/RDDT/FIG diff-audit pairs (docs/BACKLOG.md item flags CRWV Risk Factors over-claim) asserting that a real dollar change surfaces and an expanded paragraph stays MODIFIED, not add+remove.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a distinct "replaced/rewritten" change type, and a date-like-only boilerplate class that never suppresses $/%-adjacent numbers). Requires a _DIFF_CACHE_VERSION bump.

Confidence:
- medium

---

## ST-030: Timeline annual path counts raw deltas, diverging from pair-diff boilerplate filtering

Location:
- edgarpack/diff/timeline.py:85-108 (builds SectionDelta inline from raw diff_paragraphs)
- edgarpack/diff/section_diff.py:262 + timeline.py:12 (shared _compute_section_intensity, but the boilerplate-strip post-pass at section_diff.py:488-501 runs only in diff_filings)

Looks weird because:
- build_timeline computes added/removed/modified directly from diff_paragraphs without the boilerplate-stripping post-pass that diff_filings applies, so a pure date-rollover section shows MODIFIED in a timeline but clean in a pair diff. The two callers share only _compute_section_intensity, not the full pipeline, yet the CLAUDE.md invariant says they must stay in sync.

Possible real-world reason:
- timeline predates the boilerplate-visibility post-processing; the shared function was the intensity math, not the full noise-suppression pipeline.

Evidence:
- code: timeline.py:85-108; section_diff.py:488-501
- backlog: docs/BACKLOG.md item 13
- invariant: CLAUDE.md ("section_diff.py and timeline.py share _compute_section_intensity()")

Risk if removed (or relied on):
- Timeline and pair diff disagree on the same section pair, violating the spirit of the shared-intensity invariant; a date-rollover looks like a real change in the timeline view.

Current coverage:
- No test asserts timeline-vs-pair-diff parity.

Needed corpus/parity case:
- A two-filing section with only a date rollover, asserting the timeline and the pair diff agree (both clean).

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (route timeline through the same boilerplate-stripping pipeline as diff_filings so the shared invariant is real, not partial).

Confidence:
- high

---

## ST-031: Emerging-topic detection reaches into SearchIndex._get_conn and counts unique accessions, not chunks

Location:
- edgarpack/insights/emerging.py:40, 45-54 (raw SQL against chunks.filing_date/topics_json/accession via index._get_conn())
- edgarpack/index/topic_extract.py:38-59 (context-requiring patterns: competition/regulatory/china_risk need risk/threat context)

Looks weird because:
- detect_emerging_topics bypasses the SearchIndex public API and runs raw SQL, counting distinct accessions per topic (not chunks). Topic patterns deliberately refuse to match neutral prose ("China revenue grew") unless risk/restriction context is present.

Possible real-world reason:
- Counting distinct accessions per topic across a date window is not expressible through SearchIndex.search, so direct SQL is pragmatic. Counting chunks would let a verbose filing inflate a topic; counting accessions normalizes that. For a China-Lens product, China-as-risk vs China-as-market is the whole point, so neutral mentions would flood the topic and make growth ratios meaningless.

Evidence:
- code: emerging.py:40, 45-54; topic_extract.py:38-59 (china_risk comment "avoid matching China revenue grew")
- memory: MEMORY.md ("Emerging topics count by unique filings (accessions), not chunks")
- tests: test_china_risk positive case; detect_emerging_topics has NO test

Risk if removed:
- Counting by chunk lets one verbose filing fake an emerging topic; loosening the patterns floods risk topics with neutral mentions and corrupts growth deltas. The private _get_conn coupling means any chunks-schema change silently breaks emerging detection.

Current coverage:
- GAP: detect_emerging_topics is entirely untested; the context-requiring negative cases (China revenue, EAR-of) are not asserted.

Needed corpus/parity case:
- An emerging-topic case with a verbose single filing (asserting it does not inflate the count) plus negative topic cases (neutral China mention, "ear of") asserting no false tag.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (a public accession+date+topic aggregation API so emerging.py stops reaching into private internals).

Confidence:
- medium

---

## ST-032: Distill caller pack_dir path leaks into output bytes, undermining byte-determinism

Location:
- edgarpack/distill/builder.py:72 (pack_dir stored as-passed) -> models.py:103 (bundle.json), writers.py:67 (index.md Pack cell), writers.py:150-153 (run-log.md)
- edgarpack/distill/checks.py:131-133 (empty gaps.csv is a WARNING, not an error)

Looks weird because:
- A carefully deterministic bundle (sort_keys JSON, sequential ids) embeds the caller's filesystem path verbatim into bundle.json/index.md/run-log.md, so two runs of the same pack from different cwd produce different bytes. Separately, a bundle with zero gaps fails soft (warning) rather than passing cleanly, inverting "no problems = good".

Possible real-world reason:
- Provenance: a human reading run-log.md wants to know which pack on disk produced the bundle. And a perfectly complete extraction over a real SEC filing is unusual; zero gaps more likely means the extractor under-reported than that the filing was fully covered, so the empty-gaps warning is a deliberate skepticism tripwire.

Evidence:
- code: builder.py:72, models.py:103, writers.py:67/150-153, checks.py:131-133
- docs: docs/learn/trail-9-distill-bundle.md:86 (empty-gaps warning rationale)
- tests: run under monkeypatch.chdir(tmp_path), so the leaked path is a tmp dir and bytes are never snapshot-compared; the empty-gaps warning is not directly asserted

Risk if removed:
- Normalizing the path loses "which pack made this"; removing the empty-gaps warning loses the under-reporting tripwire. Keeping the path as-is blocks cross-machine byte-snapshot parity.

Current coverage:
- No test asserts bundle byte-identity; the empty-gaps warning is untested.

Needed corpus/parity case:
- A distill bundle compared semantically (counts, evidence resolvability, row values) with pack_dir normalized, plus a fully-covered fixture asserting the empty-gaps warning fires.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (store a normalized/relative pack identity for snapshotting while keeping a human-readable path in run-log; keep the empty-gaps skepticism explicit).

Confidence:
- medium

---

## ST-033: Static site copies the entire pack dir (rmtree-first) and rewrites repeated TOC-breadcrumb titles

Location:
- edgarpack/site/build.py:175-183 (shutil.rmtree(dst) before copytree)
- edgarpack/site/build.py:516-534 (_normalize_rendered_markdown_line collapses repeated "Form 10-K Summary / 83 / 83" breadcrumbs)

Looks weird because:
- The site generator rmtree's each target before copying raw artifacts (a partial run wipes prior output for that filing), and a narrow regex rewrites repeated TOC breadcrumb lines into a canonical "Item 16. Form 10-K Summary".

Possible real-world reason:
- rmtree ensures the published raw artifacts (manifest.json, filing.full.md) are exactly current and downloads work offline, avoiding stale files from a prior PARSER_VERSION. The breadcrumb regex handles real SEC 10-K TOC artifacts (dotted-leader lines repeating the title and page number) so reader pages are scannable; this mirrors the sectionizer TOC gotchas.

Evidence:
- code: build.py:175-183, 516-534
- tests: tests/test_site_build.py:79-88, :108-161 (pins the NVIDIA 0001045810 legacy case)

Risk if removed:
- Stale/mixed-version artifacts served and broken download links; or reader pages show garbled "Form 10-K Summary / 83 / 83 / 83" breadcrumbs.

Current coverage:
- The breadcrumb rewrite is tested exactly; the rmtree-of-existing-output path is only exercised on a fresh dir.

Needed corpus/parity case:
- A re-run of site build over an existing output dir asserting clean replacement, plus the NVIDIA legacy-breadcrumb case.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (fix the breadcrumb artifacts upstream in md_polish so the site does not need a display-time rewrite; this overlaps the page-break artifact item ST-004 and docs/BACKLOG.md item 3).

Confidence:
- high

---

## ST-034: Legacy accession_nodash pack directory layout is read for backward compatibility

Location:
- edgarpack/pack/build.py:183, 201-213 (checks accession_nodash dir before building; "legacy layout, use --force" warning)

Looks weird because:
- Build checks for a second directory spelling (accession without dashes) and short-circuits rather than rebuilding.

Possible real-world reason:
- An earlier SCHEMA_VERSION named pack dirs with the dashless accession; existing on-disk packs from that era must remain readable without a forced rebuild.

Evidence:
- code: build.py:201 (comment "Backward-compatible read: older versions used accession_nodash as directory name")

Risk if removed:
- Pre-existing packs in the dashless layout become invisible and get rebuilt (wasted fetches) or orphaned. The live corpus (631 packs per memory) may still contain such packs.

Current coverage:
- Not directly tested.

Needed corpus/parity case:
- A pack in the dashless legacy layout asserting it is read (not rebuilt) without --force. Requires a corpus scan to confirm any nodash packs remain before this can be retired.

vNext implication:
- Preserve behavior, but maybe model it more explicitly later (an explicit one-time migration, after confirming the live corpus is clean).

Confidence:
- medium
