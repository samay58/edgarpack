# China Lens + S-1/F-1 Streamlining Plan

Decided 2026-07-05 after a three-agent audit (China Lens code reality, S-1/F-1 registration path, rebuild-corpus digest) plus firsthand reads of `docs/rebuild/decisions/*` and `docs/BACKLOG.md`. This file is the execution contract; delete it when all phases ship.

## Decisions (Samay, 2026-07-05)

1. **Web stack**: cut the China demo workspace (FastAPI china routers + `china/` service half + `web/` workspace UI). Keep the observatory API routes and observatory web UI; their product fate is a separate later call. Static `edgarpack site` remains the canonical deterministic web surface.
2. **Provenance bugs**: fix now, don't pin-then-fix. Parity corpus pins corrected behavior.
3. **China coverage**: any-ticker acquisition. Real `build-hk`, real CNINFO/HKEX acquisition, China lanes in harvest.
4. **S-1/F-1**: robustness + flexibility (amendments, non-USD/IFRS, module split, schema-validated LLM rows, real-filing golden fixtures). Full adapter promotion deferred to vNext.

## Status

- Phase 0 routing spike: DONE 2026-07-05. Bare A-share codes route correctly to the SSE path for configured and unconfigured codes; the 2026-04-27 research note recorded pre-fix behavior fixed the same day by 54e0214. No routing fix needed. Vestigial `resolved = _synthetic_sse_company(...)` at `cli.py:2447-2448` (never read); remove during Phase 2.
- Phase 0 pymupdf4llm spike: DONE 2026-07-05. Five real CNINFO filings (Moutai, XGIMI, BYD, SigmaStar, Wuliangye) built end to end. Verdict: pymupdf4llm is a sound foundation for the text/section layer on modern filings across all three boards (no OCR needed post-2007, sections clean); the regex facts layer on top of it is not (2 correct / 1 empty / 1 confidently-wrong). Worst case reproduced: BYD FY2025 revenue returned as a fully cited ¥80.00 (an ESG ratio row). New Phase 2 items added below from this spike. Phase 3 sign-off requires a 20-30 filer sweep. Artifacts under the session scratchpad `sse-spike/`.
- Phase 1 cut: DONE 2026-07-05 on branch `streamline/phase1-cut` (5 commits, gate green incl. SYMPHONY_WEB=1). ~4,600 LOC deleted.
- Phase 2 trust: DONE 2026-07-05 on branch `streamline/phase2-trust`. All 25 spec'd fixes landed via 8 packet branches (sonnet x6, opus x2, per the Fable orchestration doctrine; specs in docs/phase2-specs/), then an adversarial review layer (opus, effort high) surfaced 8 more confirmed defects, all fixed in 4 follow-up branches or deferred to BACKLOG with evidence. Highlights: the FX period-average fix was initially dead code on the production path (caught by review, now wired and golden-tested through the production function); truncated/empty LLM snapshots no longer cache permanently; no fabricated dates survive on the China or registration paths (period_end and filed are now honestly optional). Final gate green: 1,686 offline tests, ruff, mypy strict, web build. Token ledger in docs/phase2-specs/LEDGER.md.
- Phase 3: not started. Entry gate: the 20-30 filer extraction sweep (per the Phase 0 spike caveat).

## Phase 0: steering spikes (parallel, read-only)

- **pymupdf4llm stress test**: run real CNINFO annual-report PDFs through `sse/pdf_to_md.py` + `sectionize_cn` + `annual_facts`; measure section detection rate, table fidelity, 万元 prevalence. Both Phase 1 rebuild reports missed this dependency; it is load-bearing for the entire A-share path and steers Phase 3 scope.
- **A-share routing arbitration**: run `identify`/`query` on bare `688696` to settle the docs contradiction (2026-04-27 research note says it 404s via SEC CIK; IMPLEMENTATION_TRACKER says it routes). Code is the arbiter.

## Phase 1: cut (branch `streamline/phase1-cut`)

Protocol per item: caller grep before deletion; offline suite + full gate (incl. `SYMPHONY_WEB=1` web build) green after.

Delete:
- `edgarpack/china/` workspace half: `service.py`, `storage.py`, `models.py`, `jobs/`, `synthesis/`, `qa/`, `index/`. Keep `translate/`, `acquire/`, `extract/`.
- `edgarpack/api/` china routers + their dependencies; slim `api/main.py` to observatory routes + healthz. `edgarpack api` CLI command survives, observatory-only.
- `web/` workspace surfaces: `app/(workspace)/`, `components/china-lens/`, china half of `lib/api-client.ts`, `lib/sample-data.ts`. Observatory UI stays; root already redirects to `/observatory`.
- `hk/llm_extract.py` + the inert `llm_fallback` plumbing in `hk/extract.py` (production always passes `client=None`; dormant path carries a 1000x scaling bug). Its tests go with it.
- Demo translators (`PrefixTranslator`/`IdentityTranslator`) in `china/translate/provider.py`, keep the Protocol (grep tests first).
- Unreachable `_COMPANY_META` rows (Alibaba/JD) in `hk/adapter.py`.
- Fixture PDFs from git (`tests/fixtures/china_packs/*/[0-9]*.pdf`, `source.pdf`): tests need sections + `facts.json`, not binaries. The uncommitted minimax PDF deletions in the working tree fold into this. Note: fixture REGENERATION then requires re-downloading PDFs via `scripts/download_hk_prospectus.sh`; acceptable.
- Env-var surface that dies with the service (`EDGARPACK_CHINA_SEED_FIXTURES`, `EDGARPACK_CHINA_STORAGE_*`, `NEXT_PUBLIC_CHINA_LENS_DEMO`).

Explicitly NOT cut in this phase:
- `hk/acquire.py` (unused scraper): seed material for Phase 3 `build-hk`.
- `insights/` (zero callers): tied to the observatory product call, which stays open.
- `edgarpack/site/` and observatory diff/index/timeline engines: active.
- General-bloat items from `docs/rebuild/decisions/deprecation_candidates.md` outside China Lens scope (metric_map unification, --cik flags, etc.): follow the rebuild effort's own protocol, separate pass.

Tests to adjust: `test_china_api.py`, `test_api_exports.py` become observatory-only smoke tests; delete `test_hk_llm_extract.py`, `test_china_service/storage` etc.

## Phase 2: trust (the correctness cluster, TDD, workflow fan-out with adversarial verify)

China (all pinned at file:line in `docs/BACKLOG.md` and `docs/rebuild/decisions/known_bad_current_behavior.md`):
- Rebuild the SSE facts extraction contract (`sse/annual_facts.py`), per the Phase 0 spike: extract from the 第二节 key-financials table only (substring matching over all sections pulled ESG ratios and parent-company rows into Revenue); handle the empty SZSE header corner cell (`_split_row` at `:57` strips it, shifting BYD's whole year map one column left); reset `current_years` at table boundaries (`:105`, quarterly tables inherit the annual year map); emit at most one point per (concept, fiscal_year); cross-validate against the table's own YoY% column; strip backtick code spans in `_clean_cell` (mono-font digits zeroed out SigmaStar extraction, silently).
- SSE 万元/scale detection (`sse/annual_facts.py`): currently unit hardcoded CNY, values raw. Modern key tables are 单位:元, but each filing carries 6-13 万元-denominated MD&A tables the current matcher can ingest at 1/10,000 scale. Fail closed when the 单位 marker is unrecognized.
- Fix CNINFO `--latest-annual` selection (`china/acquire/cninfo.py:269`): use the orgId-based `stock=` parameter instead of `searchkey=` full-text (which served Wuliangye's FY2005 scanned report as "latest"); exclude 英文版 filings from `_is_full_annual_report`; add a staleness floor on the selected filing.
- Query-side China fact selection (`query/periods.py:164-166,324`): frame-tagged duplicates share an identical (fy, filed) sort key, so document order decides which point wins. Make selection deterministic and prefer the key-table point; a contaminated point must lose or the result must go to None + diagnostic.
- OCR is an undeclared system dependency: pymupdf4llm silently shells to Tesseract on image-heavy pages, and a missing chi_sim model injected junk into a pack. Detect and fail loudly (or skip with a build warning naming the dependency).
- FX fiscal-year average (`fx/convert.py:71-73`): average monthly rows across the period; needs an independent FY-average oracle for the golden USD numbers.
- Real HK fiscal periods (`hk/extract.py:577-578, 622-623`): carry actual period end; instants for balance-sheet facts.
- China `filed` date (`financials.py:2076, 2111-2113`): stop fabricating Dec-31; un-enshrine the test.
- Replace the `tests/fixtures` + `fy=2024` production fallback (`financials.py:1976-1987`) with a configurable China pack root; migrate `test_cli_json_contract.py`.
- `sectionize_cn` TOC guard + `第X章`/`第X部分` support (changes SSE pack bytes: PARSER_VERSION bump; batch with the BACKLOG parse-pipeline items if convenient, else standalone bump).
- Unknown HKEX filer: fail closed instead of silent CNY/HKFRS default (`hk/adapter.py:133-140`).
- Serialize `matched_label` into `facts.json` (`hk/extract.py:621-631`).
- Translation: spend budget flag (token/dollar cap), DeepInfra `finish_reason=length` handling; extract the 400-line `_cmd_translate_sse` into `china/translate/pipeline.py` (BACKLOG already scopes this).

S-1/F-1 (audit P0/P1s; all in `edgarpack/query/s1_financials.py` unless noted):
- Merge deterministic + LLM extraction: LLM fills slugs the deterministic pass didn't produce, deterministic wins on conflict (`:956` short-circuit is the biggest coverage hole; label map has no cash/assets/equity/shares branches).
- Failure statuses (`llm_parse_failed`, `no_financial_data_found`) become retryable with cooldown; attempt partial-JSON salvage.
- Split `except Exception` → honest taxonomy: `no_api_key` only for ImportError/missing key; `llm_call_failed` carries exception text (`:971`). Fix the misleading CLI hint.
- Currency from section context in the deterministic parser; refuse deterministic emission on non-USD presentation markers (`:613`). Stop hardcoding `is_audited=True` (`:614`).
- Real period ends: no fabricated `-12-31` (`:338`); reject FY classification for interim contexts with unrecognized dates; fix Jan-31-style fiscal calendars.
- Hash full `filing.full.md` for snapshot invalidation (drop the 50KB window, `:856-864`).
- Emit `Diagnostic`s throughout the registration path (unsupported period, empty latest snapshot, status != ok).
- Magnitude gates on LLM rows (revenue ≥ gross_profit, cross-year 1000x jump detector).
- `MODEL_ID` / max-tokens env-overridable; one retry with backoff on transient errors.
- Amendment awareness: `has_registration_pack_for_cik` accepts F-1/A for F-1; filing selection prefers newest of {F-1, F-1/A} (`submissions.py:257` never matches amendments today).
- Negative caching for 404 companyfacts (`sec/xbrl.py:72-73`), preserving the 404-vs-error split.

## Design north star: the zero-knowledge American investor (added 2026-07-05)

Persona: a US investor with no China background and one strong prior ("Chinese numbers can't be trusted"). For them, provenance is the product: the bilingual citation path (English value, click through to the exact Chinese line + translation) is the wedge, not polish. Two principles govern Phase 3 scope:

1. **English is the default surface; Chinese is the provenance layer.** Query output, metric/KPI/section labels, and errors are always English (glossary-backed); full-document translation stays opt-in. Cited values render both: "Revenue (营业收入), CNY 170.9B, FY2024 annual report, filed 2025-04-02."
2. **Teach at the point of confusion; never editorialize.** Static one-liners for filing types ("年度报告: the A-share equivalent of a 10-K"). Filing-disclosed facts (auditor, listing venues, VIE/share-class structure) become citable KPIs. No risk scores, no dashboards, no screening, no macro commentary.

Acceptance scenario for Phase 3: on a cold machine, `edgarpack query BYD revenue,net_income --period lfy` resolves the ADR/US name, builds the pack if needed (with a time expectation printed), and returns cited USD+CNY values with the Chinese source text one flag away; `edgarpack comps BYD TSLA --metrics revenue,gross_margin` returns one USD-basis table with the FX convention stated and every cell cited.

## Phase 3: build (coverage + flexibility)

- `build-hk` CLI: real HKEX acquisition (rework `hk/acquire.py`), metadata from filing/universe.toml instead of the hardcoded 6-company dict.
- Any-ticker query for built packs: `query` currently refuses A-share codes absent from `universe.toml` even after `build-sse` succeeded ad hoc; discover built China packs from the pack root/registry instead.
- Consider coordinate-based `find_tables` (pymupdf) for the SSE facts layer instead of re-parsing rendered markdown; the durable fix for font-dependent artifacts. Gate Phase 3 sign-off on a 20-30 filer sweep (per-filer variance was high in the 5-filer spike).
- Harvest China lanes (CNINFO + HKEX) so coverage refreshes; today `harvest/` is SEC-only.
- SSE extraction widened past 4 metrics; interim-report support so `ltm`/`mrq` mean something for China filers.
- Dual-listing linkage in `universe.toml` schema (BABA 20-F vs 9988.HK cross-market query), including US names and ADR tickers (BYDDY, BABA) resolving to the right filer with plain-language disambiguation.
- One-command flow for China filers: `query` builds the pack if needed (the `f1`/`s1` build-if-needed pattern), so a novice never runs `build-sse` + edits universe.toml by hand.
- English-default surface: metric/KPI/section labels and errors in English via the translation glossary; bilingual provenance rendering (English label + Chinese matched_label + source text flag). Filing-type one-liner explainers in output headers (static strings).
- Filing-disclosed context KPIs for foreign-wary investors: auditor name, listing venues, VIE/share-class structure where the filing states them. Cited facts only, no editorial.
- Curated starter universe (~50 recognizable China names: BYD, Moutai, CATL, Tencent, Xiaomi, ...) as the coverage seed; doubles as the 20-30+ filer Phase 3 sweep corpus.
- S-1/F-1: split the 1,628-line module (deterministic parser / LLM extraction+cache / query integration); pydantic-validate LLM rows; unify `pick_snapshot_fact` + `_pick_snapshot_candidate`; rename `vlm` extra or wire vision; golden fixtures from 3-4 real filings (Cerebras S-1, one IFRS F-1, one non-calendar-FY filer); registration metric expansion (diluted shares, dilution, use of proceeds, offering terms).

## Phase 4: close-out (registered directive, Samay 2026-07-05; run when Phase 3 completes)

Trigger: Wave A merged, re-sweep gate passed, and the build-hk-construct decision made (shipped or explicitly deferred). Then, in order:

1. **Tight and polished, no AI slop shipped.** Full quality gate (ruff, mypy strict, offline suite, SYMPHONY_WEB build). Adversarial review pass over the accumulated Phase 3 diff (opus refuters, findings verified before acting). A dedicated slop sweep against the kill list in ~/.claude/CLAUDE.md over every shipped prose surface: docs touched this effort (STREAMLINE-PLAN, specs, QUERY/S1/OBSERVATORY updates), README, CLI user-facing strings and error messages, and code comments/docstrings (delete formulaic ones rather than rewrite). Run slopcheck.py on self-authored docs. Fable takes the final taste pass on diffs only.
2. **Consolidate.** Prune all worktrees; worktrees themselves are disposable checkouts, the BRANCHES are what merge: fold any unmerged packet branches or drop them deliberately, then delete merged phase2/phase3 branches. Update CLAUDE.md and docs to match the shipped reality (removed China workspace/api surfaces, new commands, new package layout). Refresh project memory (MEMORY.md) to the post-streamline state. Final ledger entry: totals by tier, Fable share, all-Fable counterfactual, per the doctrine's promotion checklist.
3. **Push to main properly.** Merge the stack (phase1-cut -> phase2-trust -> phase3-build) into main, run the full gate ON main before pushing, push. No force-push; the branch history is the audit trail.
4. **Production surfaces updated.** The PARSER_VERSION bumps (0.2.1 -> 0.2.3) stale-key the existing pack corpus and diff caches: decide refresh scope, then re-run harvest (now with China lanes) and incremental index, regenerate the static site, and confirm the daily-refresh launchd job still points at a valid checkout and binary. Verify with a readback: one SEC query, one A-share query, one HK query (if shipped), one diff report, all from the refreshed corpus.

## Acceptance gates

- Every phase: `scripts/symphony_quality_gate.sh` green (Phase 1 also with `SYMPHONY_WEB=1`).
- Phase 2: each fix lands with a regression test; china golden yaml updated where USD numbers change (FX fix); parity corpus rows updated to pin corrected behavior per Decision 2.
- Phase 3: end-to-end proof per feature (a real HKEX ticker built + queried; a real F-1/A picked up by `f1`).
