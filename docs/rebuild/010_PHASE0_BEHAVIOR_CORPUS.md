# Phase 0 behavior corpus

Status: Phase 0 of a clean-room rewrite. This document PINS and UNDERSTANDS current behavior with evidence. It does NOT design vNext, clean code, refactor, or implement tests. Current code is treated as the behavioral oracle but not automatically correct: it carries bugs, parked experiments, and historical compromises, all surfaced here.

Evidence base: the merged discovery corpus from 15 read-only subsystem archaeologists, sharpened against the live tree where a `file:line` was load-bearing. Out of scope as a source: `docs/archive/internal/superpowers/` (a parked prior vNext plan); it is inventoried in section 10 only, never adopted.

---

## 1. Executive summary

### What EdgarPack appears to do

EdgarPack turns SEC (and HKEX / China A-share) filings into clean, section-addressable markdown packs, then runs cited financial queries, KPI discovery, and evidence-linked filing diffs on top of them. Two load-bearing pipelines join at a shared identity resolver and citation model:

- A **build pipeline** (`build` -> a pack on disk): fetch over a hand-rolled rate-limited SEC client, run six parse steps in strict order (`ixbrl_strip -> html_clean -> semantic_html -> md_render -> md_polish -> sectionize`), write `filing.full.md`, `sections/*.md`, `manifest.json`, `llms.txt`, and optional `chunks.ndjson` / `xbrl.json`.
- A **query pipeline** (`query`, `comps`, `compare`, `which` -> cited values, no build needed for SEC filers): read companyfacts directly, resolve metric names through a hardcoded map plus a self-heal fallback, and compute period math (`ltm`, `lfy`, `mrq`, `mrp`, `annual:N`, `quarterly:N`) with full provenance.

Three parallel sub-products sit alongside: **China Lens** (HKEX `facts.json` extraction at pack time; SSE/CNINFO PDF packs with optional zh->en translation), the **Observatory** (paragraph-level filing diff, registration timelines, bulk harvest, FTS5 search, insights), and **Distill** (compress one pack into a small cited surface).

### Highest-level product contract

The non-negotiable promise, stated identically across `README.md:66`, `docs/ARCHITECTURE.md:19`, `AGENTS.md:9`, and `CLAUDE.md`: **every returned value or changed paragraph carries its filing provenance, and missing facts return `None`, never a guess.** Citations live in the data model (`CitedValue` / `DerivedValue`), not in formatting. The single most load-bearing concrete instance is the LTM contract: a non-null `ltm` value must carry `{mrp, lfy, mrp_prior}` component citations or it flips to `None` plus an `ltm_incomputable` diagnostic, enforced by `_assert_ltm_invariant` (`edgarpack/query/periods.py:483`) and re-asserted suite-wide by an autouse harness (`tests/conftest.py:56-98`).

### What current behavior must be pinned

- **Deterministic pack bytes**: rebuilds produce identical bytes except `manifest.built_at`; keyed off `PARSER_VERSION` (`0.2.1`) / `SCHEMA_VERSION` (`1`) in `edgarpack/config.py:50-51`.
- **The three-way read-path failure distinction**: real network/HTTP failure -> `XBRLFetchError` -> `layer_a_fetch_error` diagnostic; real SEC 404 (no XBRL) -> `{}`, diagnostic-free; these must never collapse to one indistinguishable N/A (`edgarpack/sec/xbrl.py:68-76`).
- **The LTM component-citation contract** and the per-period vocabulary in `periods.py`.
- **The exact JSON / citation-registry shapes** (`to_lean_dict`, `to_cited_dict`, `C#/D#/L#/G#` ids) documented in `docs/QUERY.md`.
- **Diff noise suppression** (mechanical-change suppression, word-weighted intensity shared by `diff/section_diff.py` and `diff/timeline.py`).
- **Translation fail-closed** semantics and the China golden numeric answers in `tests/eval/china_golden.yaml`.

### What is most dangerous to lose

1. **The provenance promise itself.** Any value path that returns a bare number, or any failure that becomes an uncited N/A, breaks the product's reason to exist.
2. **`periods.py` period math.** The subtlest module in the codebase; most financial-reasoning bugs live here. Three formerly-broken behaviors (per-share LTM additive math, annual-only LTM-1 stub selection, Q4 early-return accepting stubs) were FIXED on 2026-06-09 and are now pinned by regression tests; a rewrite must not regress them.
3. **Determinism.** An offline determinism test exists (`test_pack_build.py:217`) but runs `with_chunks=False` in-process, so it cannot catch the determinism risks that matter; full determinism is otherwise verified only live+slow against one filing (NVDA 10-K). The fast suite cannot catch the regressions that bite: the tokenizer fallback (`tokenize.py:48-55`) silently changes chunk bytes in a cold-tiktoken environment, and the SSE+translate path mutates the manifest after hashing it. (Refined by Phase 1 verification 2026-06-16; see `docs/rebuild/032_PHASE1_DIFF_AND_ADJUDICATION.md` §3.)
4. **The HKEX column-shift guard.** The structural column-count gate (`hk/extract.py:278-279`) chooses silence over misattributing a value to the wrong fiscal year.

### Active vs parked

| State | Surfaces |
|---|---|
| Active (CLI, tested) | build, list, company-llms, site, query, comps, compare, which, diff, timeline, harvest, index, search, identify, build-sse, translate-sse, learned, cache, doctor, distill, `f1`/`s1` registration shortcuts |
| Active (data-backed, untested at HTTP layer) | `/api/v1/observatory/*` routes |
| Parked (declared) | FastAPI Evidence Explorer workspace (`edgarpack api`, `edgarpack/api/`, `edgarpack/china/service.py`); the Next.js `web/` frontend. `docs/china-lens/IMPLEMENTATION_TRACKER.md:5-7`: "CLI path active; workspace parked"; beads closed wontfix 2026-04-20. |
| Parked (inventory only) | `docs/archive/internal/superpowers/` prior vNext clean-rewrite plan (self-marked "not the current roadmap"). |
| Experimental / inert | HKEX LLM extraction fallback (`hk/llm_extract.py`, always called with `client=None`); `--describe-images` VLM (`pack/assets.py`, opt-in, output never wired into query/citation path). |

### What needs human judgment before vNext

The biggest open calls (full list in section 13): whether the user-facing `__version__` (`0.1.0`) and `PARSER_VERSION` (`0.2.1`) should be reconciled; which of `query`/`comps`/`compare` (three overlapping comparison surfaces with three metric-arg contracts) is the parity oracle; whether the ~16 known-bad items in `docs/BACKLOG.md` are pinned as-current or fixed during the rewrite (several touch the cited-value promise: HKEX LLM 1000x unit-scaling, fabricated China `filed` dates, FX period-average error); and whether the parked FastAPI/web product is revived or retired. None of these are designed here.

---

## 2. Product contract as observed

Each surface below is the externally observable contract, focused on user outcomes. Entry points are `file:line` where load-bearing.

### 2.1 SEC build / pack / corpus surfaces

| Surface | Entry point | Input forms | Outputs | Files created | Side effects | Cache | Network | Determinism | Citation/provenance | Test coverage | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `build` | `cli.py:1426` `_cmd_build` | company (ticker/name/CIK), `--cik`[deprecated], `--accession`, `--form`, `--out`, `--with-chunks`, `--with-xbrl`, `--force`, `--last N`, `--after`/`--before` | text build summary | pack dir: `filing.full.md`, `sections/*.md`, `manifest.json`, `llms.txt`, optional `chunks.ndjson`/`xbrl.json`; registers in PackRegistry | writes packs + registry; rmtree on `--force`; removes empty dir on fetch failure | `--force` bypasses SEC cache | fetches SEC; `SECRateLimitError` -> 10-min cooldown msg | byte-identical rebuild owned by `pack.build` | manifest carries hashes/offsets; provenance enforced downstream | `test_cli_build_range.py`, `test_build_pack_registration.py` | active |
| `list` | `cli.py:2313` | company, `--cik`, `--form`, `--limit` | aligned form/date/accession rows | none | none | reads SEC cache | `sec.submissions.list_filings` hits SEC | deterministic newest-first | accession/form/date shown | none direct | active |
| `company-llms` | `cli.py:2293` | company, `--cik`, `--out` | path written | company-level `llms.txt` | scans cik dir | reads SEC | fetches submissions for name | sorted newest-first | links each filing's `llms.txt` | none | active |
| `site` | `cli.py:2373` | `--packs`, `--out`, `--base-url`(reserved/unused) | companies/filings/size | static HTML tree (index + reader pages) + copied raw pack artifacts | rmtree each target before copytree | none | none (offline) | intended deterministic (no determinism test) | renders manifest provenance | `test_site_build.py` | active |
| `cache` | `cli.py:2339` | `--clear` | dir + file count + size, or "Cleared cache" | none | `--clear` does `shutil.rmtree(CACHE_DIR)` (destructive, refetchable) | reads `CACHE_DIR` | none | n/a | n/a | none | active |
| `doctor` | `cli.py:1283` | pack dir OR ticker, `--format text\|json` | manifest state, artifact inventory, coverage X/Y, KPI count, health | none | reads PackRegistry; disk fallback `_local_pack_records` | reads registry + `s1_financials.json` | ticker target may hit SEC | deterministic given pack | validates `schema_version==SCHEMA_VERSION` | `test_cli_doctor.py`, `test_pack_doctor.py` | active |

### 2.2 SEC query surfaces

| Surface | Entry point | Input forms | Outputs | Side effects | Cache | Network | Citation/provenance | Test coverage | Status |
|---|---|---|---|---|---|---|---|---|---|
| `query` | `cli.py:2407` | company, metrics CSV (optional => all), `--period`/`-p` (lfy, lfy-N, mrq, mrq-N, mrp, ltm, ltm-N, pro-forma, annual:N, quarterly:N, CSV grid), `--preset perf`, `--format table\|json\|json-full`, `--audit`, `--show-links`, `--citations`, `--force`, `--packs`, `--strict`, `--currency native\|usd\|both` | table / lean JSON (`to_lean_dict`) / full JSON (`to_cited_dict`); Reproduce permalink | self-heal may write learned registry unless `--strict`; `--strict` applies `apply_strict` and reports `strict_rejected` | `--force` bypasses cache | SEC companyfacts; S-1 reads pack; pro-forma may need `ANTHROPIC_API_KEY` | `CitedValue`/`DerivedValue` full provenance; missing => `None` not guess | `test_cli_json_contract.py`, `test_cli_query_currency.py`, `test_cli_query_no_api_key_hint.py`, `test_cli_self_heal.py`, `test_periods.py`, `test_financials.py` | active |
| `comps` | `cli.py:2659` | companies (1+), `--metrics`/`-m` (REQUIRED), `--period`, `--format`, `--audit`, `--show-links`, `--citations`, `--force`, `--strict` | single/multi-period comps table; lean/full JSON; per-company `strict_rejected` | self-heal write unless `--strict` | `--force` bypasses | parallel SEC fetches via `asyncio.gather` | per-cell citations | `test_cli_json_contract.py` (comps) | active |
| `compare` | `cli.py:1041` parser, `compare.py:441` `cmd_compare` | companies (doc says 2+), `--metrics` (optional, hardcoded default list), `--period`, `--currency`, `--format table\|json\|markdown`, `--strict` | side-by-side table/markdown/json + sources block; FY-mismatch flags | self-heal write unless `--strict` | n/a | parallel SEC/HKEX fetches; one bad ticker sinks the command | citation markers + sources | `test_cli_json_contract.py` (compare) | active |
| `which` | `cli.py:3809` (+ `_cmd_which_china:3719`) | company, `--format table\|json`, `--no-cache`, `--only all\|discovered\|catalog`, `--max-periods`, `--currency` | KPI table (discovered + catalog), newest-first; JSON with diagnostics; S-1 profile block; China branch is deterministic pack metrics | `discover_kpis` may write KPI cache | n/a | resolves company (may hit SEC); discovery shells out to LLM CLI | metric NAMES + values for catalog | `test_cli_which_ux.py` | active |
| `f1` / `s1` | `_add_registration_shortcut` `cli.py:672`, dispatch `cli.py:1598` | company, metrics (optional), `--accession`, `--period`, query flags, `--preset perf`, `--strict` | builds latest F-1/S-1 pack if needed, then delegates to `_cmd_query` | writes registration pack + registers; existence check `has_registration_pack_for_cik` | reuses pack unless `--force` | may fetch SEC to build | same as query (`s1_snapshot`/`s1_pro_forma`) | `test_cli_registration_shortcut.py` | active |
| `learned` | `cli.py:3359` | list/show/verify/clear with `--cik`/`--metric`/`--source`/`--unverified`/`--all` | tabular list (✓/⚠), promote, removed count | verify/clear MUTATE LearnedRegistry; clear without filter requires `--all` | n/a | none | inspects self-heal registry | `test_cli_self_heal.py` (touches) | active |

### 2.3 Observatory surfaces

| Surface | Entry point | Input forms | Outputs | Files | Network | Status |
|---|---|---|---|---|---|---|
| `diff` | `cli.py:2912` | `--ticker`(+`--form`) OR `--before`/`--after` (accession or pack dir), `--format summary\|full\|json\|html`, `--out` (html) | summary stats / paragraph deltas / `DiffResult.model_dump` / static cited HTML | html mode writes `--out` | `--ticker` may hit SEC; diff offline | active |
| `timeline` | `cli.py:3204` (+ `_render_registration_timeline:3038`) | `--ticker`+`--section` (annual) OR `--cik` (registration), `--form`, `--packs`, `--series annual\|registration`, `--format text\|html`, `--out` | annual section evolution / registration redline chain | html (registration only) writes a dir of reports | `--ticker` may hit SEC; registration offline | active |
| `harvest` | `cli.py:2832` | `--universe`, `--out`, `--plan`, `--refresh`, `--with-chunks`, `--concurrency`, `--force`, `--describe-images` | stderr plan/progress; exit 1 if any failed | many packs + registry rows; `--describe-images` writes `assets/.descriptions.json` | heavy SEC fetch; VLM calls when `--describe-images` | active |
| `index` | `cli.py:3306` | `--packs`, `--incremental` | per-pack chunk counts + total | writes FTS5 search index; marks packs indexed | none | active |
| `search` | `cli.py:3269` | query, `--topic`, `--ticker`, `--form`, `--limit` | "Found N results", topics line, per-hit snippet with markers | none | `--ticker` may hit SEC; search offline FTS5 | active |
| `identify` | `cli.py:1657` | company (name/ticker/stock code/alias) | display name + status (SEC filer / public HKEX / public A-share/SSE / private / ambiguous / unknown) + next-step | none | may hit SEC; A-share code tries CNINFO | active |

### 2.4 China Lens surfaces

| Surface | Entry point | Input forms | Outputs | Network | Env vars | Status |
|---|---|---|---|---|---|---|
| `build-sse` | `cli.py:1748` | target (name/alias/stock code), `--latest-annual`, `--url`, `--stock-code`, `--company`, `--filing-date`, `--pdf`, `--with-chunks`, `--translate`(+model/concurrency/batch), `--form-type auto\|annual-report\|ipo-prospectus`, `--force` | selected-annual block + build summary | CNINFO download unless `--pdf`; optional DeepInfra translation | `EDGARPACK_DEEPINFRA_KEY` | active |
| `translate-sse` | `cli.py:1888` (~400-line inline orchestrator) | `--pack` (REQUIRED), `--model`, `--concurrency`, `--batch-size`, `--force` | per-section progress; "Translated: N, M from cache"; exit 1 if any section failed | DeepInfra translation endpoint | `EDGARPACK_DEEPINFRA_KEY` | active |
| `api` | `cli.py:2386` | `--host`, `--port` | runs uvicorn (blocking); mounts 8 routers under `/api/v1` | binds socket; needs `china` extra | China routes offline (seeded fixtures); observatory routes read on-disk SQLite | parked |

### 2.5 Distill surfaces

| Surface | Entry point | Input forms | Outputs | Network | Status |
|---|---|---|---|---|---|
| `distill run` | `cli.py:1375`, `distill/builder.py:64` | slug, `--pack` OR `--accession`(+`--packs`), `--company`, `--out`, `--force` | 8-file bundle: `index.md`, `findings.csv`, `metrics.csv`, `evidence.jsonl`, `gaps.csv`, `filing-map.md`, `run-log.md`, `bundle.json` | none (reads local pack only) | active |
| `distill check` | `distill/checks.py:24` | bundle dir | "distill check ok" or exit 1 + errors | none | active |

### 2.6 API / web (parked)

| Surface | Entry point | Input forms | Outputs | Status |
|---|---|---|---|---|
| China Lens HTTP routes | `edgarpack/api/main.py`, `routes/*` | REST: companies/packs/documents/evidence/ask/citations/connectors | in-memory SQLite seeded with Tencent (`cmp_tencent_0700`) fixtures; `/ask` returns evidence-only or not_found | parked |
| Observatory HTTP routes | `api/observatory/routes.py:71` | GET companies/diff/timeline/search/stats/topics | reads real on-disk registry/search-index | parked (data-backed half; no HTTP test) |
| Next.js `web/` | `web/app/*` | browser routes | Evidence Explorer + Filing Observatory UI; china client swallows errors -> fixture fallback, observatory client throws actionable error | parked |

### Notable contract facts

- **`--version` is `0.1.0`** (`__init__.py:5`) while `PARSER_VERSION` is `0.2.1`. User-facing version and parser-determinism version are decoupled.
- **`compare` is dispatched FIRST** in the if-chain (`cli.py:1155`), ahead of `home`; it is the only command in a separate module (`compare.py`).
- **`f1` and `s1` are the only dynamically-registered subcommands**; only those two form types are wired (`cli.py:745-746`), and any other `registration_form` is hard-rejected (`cli.py:1601-1603`).
- **`--format html` is only valid** for `diff` (with `--out`) and `timeline --series registration`; annual timeline html is a hard error (`cli.py:3210-3215`).

---

## 3. Workflow map

Grouped by user job, not module.

### 3.1 SEC pack generation
- **User job**: turn a filing into a clean, addressable markdown pack.
- **Surfaces**: `build`, `f1`/`s1` shortcuts, `harvest` (bulk).
- **Artifacts**: `filing.full.md`, `sections/*.md`, `manifest.json`, `llms.txt`, optional `chunks.ndjson`/`xbrl.json`, registration `assets/*`.
- **Trust/citation**: manifest carries section hashes + char offsets; deterministic bytes.
- **Edge cases**: legacy `accession_nodash` dir read-compat (`build.py:201-213`); latin-1 decode fallback for pre-2001 filings (`build.py:83-88`); S-1 heading injection before `clean_html` strips ids.
- **Regression risk**: HIGH (parse-order, determinism, sectionizer TOC bugs are documented known-bad).
- **In corpus**: yes.

### 3.2 SEC listing / accession resolution
- **User job**: resolve a ticker/CIK/name (or pre-IPO issuer name) to a filing.
- **Surfaces**: `identify`, `list`, plus internal `_resolve_cli_company` shared everywhere.
- **Artifacts**: none durable; cached `company_tickers.json`, submissions pages.
- **Trust**: produces the CIK all citations key off; ambiguity raises typed error, unknown gives fuzzy "did you mean".
- **Edge cases**: pre-IPO EDGAR full-text search via undocumented `efts.sec.gov/LATEST/search-index` (`tickers.py:224`); content-only-match rejection (the WhiteFiber-not-Cerebras guard); China A-share numeric-code short-circuit before SEC.
- **Regression risk**: MEDIUM-HIGH (undocumented endpoint, multi-market routing precedence).
- **In corpus**: yes.

### 3.3 SEC financial query
- **User job**: get a cited financial value for a company/period.
- **Surfaces**: `query`, `f1`/`s1`.
- **Artifacts**: lean/full JSON, citation/calculation registries.
- **Trust**: `CitedValue` full provenance; None-not-guess; three-way fetch-failure distinction.
- **Edge cases**: AXP/issuer revenue resolves to ASC-606 `us-gaap:Revenues` not the headline figure; synthetic `EntityNumberOfEmployees` injected into facts dict (`financials.py:1036`).
- **Regression risk**: HIGH.
- **In corpus**: yes.

### 3.4 Derived metrics & period semantics
- **User job**: LTM/LFY/MRQ/annual:N math, margins, ratios, CAGR.
- **Surfaces**: internal `periods.py`, `formula.py`, surfaced via `query`/`comps`.
- **Trust**: LTM component-citation contract; FY exact-matching; staleness rejection.
- **Edge cases**: standalone-quarter threshold 100 days; full-year window 350-380 days; per-share LTM degrades to annual (`ltm_degraded`); balance-sheet LTM bypasses the invariant; `eval_formula` has NO operator precedence.
- **Regression risk**: HIGHEST (subtlest module; three fixed bugs to not regress).
- **In corpus**: yes.

### 3.5 Comps & compare
- **User job**: cross-company comparison.
- **Surfaces**: `comps` (metrics required), `compare` (separate module, hardcoded default metrics, FX handling).
- **Edge cases**: three overlapping comparison surfaces with three metric-arg contracts and three formatter stacks; one bad ticker sinks `compare`.
- **Regression risk**: MEDIUM.
- **In corpus**: yes.

### 3.6 KPI discovery / which
- **User job**: discover the qualitative/MD&A KPIs a filer discloses.
- **Surfaces**: `which`, China branch `_cmd_which_china`.
- **Artifacts**: KPI cache, `company_kpis` registry tables.
- **Trust**: KPI values tagged `learned:kpi-*` (rejected by `--strict`).
- **Edge cases**: one LLM call per pack (cached); China branch is a different deterministic code path.
- **Regression risk**: MEDIUM.
- **In corpus**: yes (LLM path mocked in tests).

### 3.7 Filing diff
- **User job**: see what language changed between two filings.
- **Surfaces**: `diff` (summary/full/json/html).
- **Artifacts**: `DiffResult` JSON, static HTML report, diff cache (`_DIFF_CACHE_VERSION` v7).
- **Trust**: mechanical-change suppression; every changed paragraph carries old/new evidence anchors.
- **Edge cases**: overlap-rescue forced marriages; numeric-boilerplate over-suppression (can hide real dollar changes); page-break artifacts in JSON.
- **Regression risk**: HIGH (uncalibrated magic-number weights; documented precision items).
- **In corpus**: yes.

### 3.8 Registration timeline / S-1 chains
- **User job**: redline the S-1 -> S-1/A -> 424B amendment chain.
- **Surfaces**: `timeline --series registration`.
- **Trust**: CIK-scoped (rejects empty/mismatched CIK); html pairs carry full evidence anchors.
- **Regression risk**: MEDIUM.
- **In corpus**: yes.

### 3.9 Search / index / harvest
- **User job**: bulk-ingest a universe and search the corpus.
- **Surfaces**: `harvest`, `index`, `search`.
- **Artifacts**: `registry.db`, `search_index.db`, `harvest_errors` table.
- **Edge cases**: FTS5 reindex purge contract (plain DELETE so triggers fire); emerging-topic counting by unique accession; `--refresh` relabels counts but does not change the build set.
- **Regression risk**: MEDIUM.
- **In corpus**: yes (harvest runner network path untested offline).

### 3.10 Local site / agent handoff
- **User job**: publish a readable corpus / hand off to LLM agents.
- **Surfaces**: `site`, `llms.txt`, `company-llms`.
- **Trust**: deterministic, dependency-free, href-sanitized HTML.
- **Regression risk**: LOW-MEDIUM.
- **In corpus**: yes.

### 3.11 HKEX facts
- **User job**: query Hong Kong listed filers with the same cited model.
- **Surfaces**: `query`/`comps`/`which`/`identify` routing source=HKEX -> reads `facts.json`.
- **Artifacts**: HKEX `facts.json` (taxonomy `hkfrs`).
- **Edge cases**: column-shift P0 guard; `matched_label` dropped on serialization; metadata hardcoded in a 6-entry dict; `build_hk_pack`/`extract_facts_from_pack` NOT wired into the CLI build command (fixture-only).
- **Regression risk**: HIGH (correctness-sensitive extraction; open xfail edgarpack-483).
- **In corpus**: yes.

### 3.12 SSE / CNINFO PDF packs
- **User job**: build A-share annual-report/prospectus packs from CNINFO PDFs.
- **Surfaces**: `build-sse`, query routing source=SSE -> `facts.json` (taxonomy `cas`).
- **Artifacts**: SSE `facts.json` (4 metrics only), `source.pdf`.
- **Edge cases**: only 4 metrics extracted; ambiguous form-type defaults to IPO-PROSPECTUS; CNINFO market routing by stock-code first digit.
- **Regression risk**: MEDIUM (narrow scope, fragile PDF table parsing).
- **In corpus**: yes (no SSE/CAS golden rows yet).

### 3.13 Chinese translation
- **User job**: produce English-readable SSE pack sections.
- **Surfaces**: `translate-sse`, `build-sse --translate`.
- **Artifacts**: `*.en.md`, `filing.full.en.md` (only on zero failures), `translation.failures.json`, manifest translation block.
- **Trust**: number magnitude (wan/yi 10,000x) NEVER delegated to the LLM; fail-closed validators.
- **Edge cases**: resume-by-default when `failed_sections` present; SQLite cache keyed by strategy fingerprint.
- **Regression risk**: HIGH (heavily scar-tissued; magnitude invariant is load-bearing).
- **In corpus**: yes (DeepInfra mocked in tests).

### 3.14 Learned / self-heal / maintenance
- **User job**: resolve a metric not in the hardcoded map; manage the learned registry.
- **Surfaces**: self-heal path (query), `learned` subcommand, `cache --clear`, `doctor`.
- **Artifacts**: `learned_concepts` registry, KPI cache.
- **Trust**: only `source=='hardcoded'` survives `--strict`; learned values verified against prior-year order of magnitude before persist.
- **Edge cases**: LLM backend chosen by import-time PATH scan (codex preferred over claude); a read-path query mutates the shared registry; verify tolerates sign flips.
- **Regression risk**: MEDIUM-HIGH (non-reproducible across machines).
- **In corpus**: yes (LLM path mocked).

### 3.15 API / web
- **User job**: graphical Evidence Explorer / Observatory.
- **Surfaces**: `api`, `web/`.
- **Status**: PARKED. China routes run on seeded fixtures; observatory routes read on-disk state; `/ask`, `/documents`, all `/observatory` routes untested.
- **In corpus**: inventory only; the China seed corpus and citation-resolve contract should be pinned before any removal.

### 3.16 Test & quality gate
- **User job**: keep the gate green.
- **Surfaces**: `scripts/symphony_quality_gate.sh`, offline pytest lane, three gated lanes (`--run-slow`, `--run-live-sec`, `--live-sec-full`), China golden harness.
- **In corpus**: yes (the parity harness should mirror these lanes).

---

## 4. Artifact inventory

| Artifact | Producer | Consumer | Visibility | Documented | Tested | Capture policy | Important fields | Unstable fields to normalize |
|---|---|---|---|---|---|---|---|---|
| `manifest.json` | `pack/manifest.py:187` | doctor, query, diff, timeline, site, translate-sse | public (pack) | yes | yes | normalized | `schema_version`, `parser_version`, `filing{cik,accession,form_type,filing_date,period_of_report}`, `sections[]` (id,path,char offsets,sha256), `artifacts{}`, `tokens_total` | `generated_at`, `source.fetched_at` (forced to filing_date midnight), `built_at`, `warnings`, translation block (SSE) |
| `filing.full.md` | `pack/build.py:260` | diff, distill, query S-1/SSE, site | public | yes | yes | exact | full markdown w/ prepended `# {company} \| {form} \| Filed {date}` title | none |
| `sections/{id}.md` | `pack/build.py:265` | chunks, llms.txt, query, diff | public | yes | yes | exact | per-section markdown; filename is section_id | none |
| `llms.txt` (filing + company) | `pack/llms_txt.py:7`, `build.py:879` | LLM agents, company index | public | yes | yes | exact | deterministic index of pack + sections + optional | none |
| `chunks.ndjson` | `pack/chunks.py:265` | FTS5 search builder | public | yes | yes | normalized | `chunk_id` (content hash), `section_id`, char offsets, tokens | chunk boundaries + ids (tiktoken-vs-heuristic branch) |
| `xbrl.json` | `pack/build.py:286` | manual (not primary query path) | public | yes | NO | semantic | reshaped companyfacts | SEC-side facts drift |
| `facts.json` (HKEX `hkfrs`) | `hk/extract.py:634` | `_query_china_pack` `financials.py:2154` | pack-internal, queried | yes | yes | semantic | `{hkfrs:{Concept:{label,units:{CCY:[points]}}}}`; point carries `accn`, `section_id`, `extraction_method`, `fy` | `accn`, `source_path` (absolute/machine-specific); `matched_label` dropped on serialization |
| `facts.json` (SSE `cas`) | `sse/annual_facts.py:162` | `_query_china_pack` | pack-internal, queried | partial | yes | semantic | 4 metrics only; `cas` taxonomy | `source_document` hardcoded `optional/source.pdf` |
| query lean JSON (`to_lean_dict`) | `query/models.py:617` | render, comps, CLI `--format json`, web | public | yes | yes | normalized | dedups filings; citations/calculations registries (`C#/D#/L#`) | `filings.*.url`, `permalink`, `primary_link` (network-enriched `fact_id`) |
| query full JSON (`to_cited_dict`) | `query/models.py:558` | CLI `--format json-full` | public | yes | yes | normalized | full provenance per metric | derived URLs, `fact_id` |
| CitationRegistry maps | `query/citations.py:48` | render markers, JSON | public | yes | yes | exact | stable `C#/D#/L#/G#` ids deduped by `citation_key` | none |
| diff JSON (`DiffResult`) | `diff/section_diff.py:520` | CLI json, API, report_builder, insights | public | yes | yes | normalized | section_deltas, change types | `interest_score`, `change_intensity`, `overall_change_intensity` (floats); ordering (score-driven) |
| diff HTML report | `diff/html_report.py:1003` | browser | public | yes | yes | semantic | evidence anchors, source links | absolute pack file URIs, reproduce-command paths, timestamps |
| timeline (annual/registration) | `timeline.py:110`/`164` | CLI, API | public/internal | yes | partial | normalized/exact | per-entry accession+date+intensity; registration CIK-scoped | `content_preview`, `pack_dir` (absolute) |
| translation manifest block + `translation.failures.json` + `*.en.md` | `cli.py:2232` | bilingual llms.txt, China query | public (pack) | partial | partial | semantic / known_bad | `strategy_fingerprint`, `failed_sections`, `full_filing_written` | `cached_paragraphs`, `translated_paragraphs`, LLM output (non-deterministic) |
| `s1_financials.json` snapshot cache | `query/s1_financials.py:934` | augment, `which`, distill | public (pack) | yes | yes | semantic | `schema_version`(==8), `source_sha256`, `facts[SnapshotFact]` | `extracted_at`, `model`, `source_sha256` |
| `assets/.descriptions.json` + `*.desc.txt` (VLM) | `pack/assets.py:160` | none in query path (loose files) | pack-internal | yes | partial | manual | per-image description | all (non-deterministic VLM) |
| `registry.db` (PackRegistry) | `harvest/registry.py:136` | doctor, diff, timeline, index, API | internal SQLite | yes | yes | normalized | accession(PK), cik, form, filing_date, manifest_hash, `indexed_at` | `built_at`, `indexed_at`, `pack_dir` (absolute) |
| `harvest_errors` table | `harvest/registry.py:279` | runner histogram | internal | yes | NO | normalized | `error_stage`(always 'build'), error(200-char) | `id`, `created_at` |
| `search_index.db` (FTS5) | `index/inverted.py:116` | search, topic stats, emerging | internal SQLite | partial | yes | semantic | external-content FTS5 over chunks | `rowid`, BM25 `rank` |
| `learned_concepts` registry | `query/learned_registry.py:333` | learned subcommand, self-heal, strict | internal SQLite | yes | yes | semantic | cik, metric, concept, source, verified, accession | `learned_at`, `hit_count`, `source` (machine-dependent) |
| `data/fx_rates.csv` | `scripts/refresh_fx.py` | China USD path, `fx.rates.load_rates` | repo-pinned, public | yes | yes | normalized/exact | `ccy_pair`, `month_end_date`, `spot_end`, `period_average` | refresh drift (golden USD 2% tol absorbs) |
| `docs/METRIC_DIRECTORY.json/.md` | `scripts/generate_metric_directory.py` | humans, drift test | committed | yes | yes | exact | full metric/alias/formula/KPI registry | none (byte-equality guarded) |
| distill bundle (8 files) | `distill/writers.py:13` | distill check, humans/tools | public | yes | yes | exact (evidence/csv) / normalized (index/run-log) | evidence_ids must resolve; bundle.json counts==rows | `pack_dir` path leak (bundle.json/index.md/run-log.md) |
| `benchmarks/efficiency-*.json` | `scripts/benchmark_efficiency.py` | README, BENCHMARKS.md | committed | yes | NO | manual | compression numbers | accession (latest changes), token counts, timestamps |
| static site HTML tree | `site/build.py:45` | static server, browser | public | yes | yes | normalized | reader pages + copied raw pack | `total_bytes`, absolute `out_dir` |
| `tests/eval/china_golden.yaml` | hand-curated | `test_china_query_eval.py` | internal | yes | yes | semantic | native exact + USD (rel_tol 0.02) | `fx_rate` (informational) |

---

## 5. Behavior-pinning strategy

Snapshot levels and when each applies:

- **EXACT**: byte-for-byte equality. Use for outputs the determinism guarantee already covers and that carry no env-dependent fields: `filing.full.md`, `sections/*.md`, `llms.txt`, the `CitationRegistry` id assignment, `docs/METRIC_DIRECTORY.json/.md`, distill `evidence.jsonl` and the CSV row files. A diff here is a real behavioral change.
- **NORMALIZED**: equality after stripping/normalizing a known set of unstable fields. Use for `manifest.json` (pop `generated_at`/`built_at`/`source.fetched_at`/`warnings`/version fields), query lean/full JSON (normalize derived/network-enriched URLs, `permalink`, `fact_id`), `chunks.ndjson` (pin a known tiktoken-present state), diff JSON (tolerance on float scores), `registry.db`/`search_index.db` rows (drop timestamps + absolute paths), static-site report dicts (drop `total_bytes`/`out_dir`).
- **SEMANTIC**: assert facts and relationships, not bytes. Use for HKEX/SSE `facts.json` (assert the cited value + period + currency, not serialization order), `s1_financials.json`, the China golden (native exact, USD within 2%), and diff HTML reports (assert structural tokens + anchor presence, not full HTML).
- **MANUAL**: human-reviewed, never auto-regenerated. Use for `tests/eval/china_golden.yaml`, `benchmarks/efficiency-*.json`, VLM descriptions, `source.pdf`, and any output that embeds an absolute machine path until that leak is normalized.
- **DEPRECATED**: capture for inventory but not asserted forward. Use for `web/.next` build output, the inert HKEX LLM cache, and `error_stage`-style scaffolding columns.
- **KNOWN-BAD**: pin the CURRENT (wrong) output explicitly labeled as defective, so the rewrite can choose to preserve-for-parity-then-fix. Use for the HKEX LLM 1000x unit-scaling output, the fabricated China `filed=Dec-31` date (a test enshrines it), the FX one-month-average-for-annual-flow value, `*.en.md` translation output, and the diff numeric-boilerplate-suppressed sentences.

Selection rule: prefer the strictest level the artifact's unstable fields allow. Promote KNOWN-BAD items to a fix decision in section 13 rather than silently locking them as EXACT.

---

## 6. Proposed corpus cases

This summarizes the intended grouping of `tests/parity/corpus.yaml` (produced by the sibling D2 author). `tests/parity/` currently exists as an empty, untracked directory, evidently reserved for this harness. Five groups, each existing for a distinct reason:

1. **required-for-parity**: the behaviors the rewrite must reproduce or it is not EdgarPack. Pack determinism (NVDA 10-K bytes); the full period vocabulary against synthetic and real companyfacts; the LTM component-citation contract; lean/full JSON shapes; citation-registry id assignment; the China golden native values; metric-directory byte-equality; CLI `--format json` cleanliness; lazy-startup invariant. Exists because these are the load-bearing contract.
2. **high-risk edge case**: the scar-tissue behaviors most likely to drift: sectionizer TOC/INDEX state machine; malformed colspan/span tables (TSM 2006); font-size:0 S-1 wrapper; HKEX column-shift guard; per-share LTM degrade; standalone-vs-cumulative quarter; pre-IPO content-only-match rejection; diff overlap-rescue and boilerplate suppression; translation number tagging. Exists because each encodes a real filing-world condition that a naive rewrite re-breaks.
3. **manual review**: outputs that cannot be auto-asserted and need a human eye: China golden additions, benchmark figures, diff/timeline HTML reports, VLM descriptions, anything embedding an absolute path. Exists to keep non-deterministic or path-leaking artifacts out of the byte-equality lane.
4. **parked-deprecated**: the FastAPI/web Evidence Explorer contract (seed corpus, citation-resolve, pack-status tick) and the inert HKEX LLM path. Pinned only to document the contract before any removal decision. Exists so a removal does not silently sever a tested-but-parked surface.
5. **uncertain**: behaviors where docs/tests/code disagree or no test exists: bare 6-digit A-share routing (research note vs tracker disagree), the `--refresh` accounting semantics, `xbrl.json` production, `site --base-url`, the inert `_STALENESS_YEARS` hook. Exists to flag what must be characterized by running code (which Phase 0 cannot) before trusting either source.

---

## 7. Semantic invariants to implement later

These are the relationships a later validator should assert (not designed here, only enumerated with evidence):

- **Pack integrity**: every `sections/{id}.md` referenced in `manifest.sections` exists on disk and its sha256 matches; every `manifest.artifacts` entry exists; `manifest.json` is excluded from its own artifact hashes (`build.py:316`).
- **Manifest references resolve**: `char_start`/`char_end` index into the same `filing.full.md` bytes written to disk (after title prepend); `char_end > char_start`.
- **Deterministic rebuilds**: same filing + same `PARSER_VERSION`/`SCHEMA_VERSION` -> identical bytes for `filing.full.md`, `sections/*.md`, `llms.txt`, `manifest.json` (modulo `built_at`). Currently only checked live+slow against NVDA; the validator needs an OFFLINE fixture-fed determinism case.
- **Citation resolvability**: every `CitedValue`/diff-evidence/distill-evidence id resolves; deep-link URLs degrade to a lower tier or `None`, never a broken link.
- **Cited financial values**: every rendered value traces to a `CitedValue`/`DerivedValue`; no bare-number path.
- **Derived metric formulas**: `DerivedValue` carries its component map; cross-period alignment (single fiscal_year/period_end) or `None`; `eval_formula` is positional (no precedence) and returns `None` (not 0) on missing operands/div-by-zero.
- **LTM/LFY/MRQ period semantics**: LTM = `mrp + lfy - mrp_prior` with the three component citations; FY-anchored selectors reject nearest-period substitutes; standalone quarter <=100 days, full year 350-380 days; per-share LTM degrades to annual.
- **Stale-data guards**: bare selectors reject values >2 fiscal years behind current year (`ltm-1` allows 3); series/offset selectors skip the check.
- **Currency provenance**: HKEX/SSE values carry `reporting_currency` from the pack (CNY/USD/HKD); `unit=='headcount'` maps currency to empty; FX conversion (ASC-830) uses spot for balance sheet, average for flows.
- **Diff noise suppression**: financial_statement/signature sections suppressed; boilerplate paragraphs invisible and excluded from the intensity denominator; intensity word-weighted and shared by `section_diff.py` + `timeline.py`.
- **Translation validation**: number/literal/han/table-structure preservation; fail-closed (no partial `filing.full.en.md`); strategy-fingerprint-scoped cache.
- **Source-family provenance**: `CitedValue.source` in the closed set (`hardcoded`, `learned:*`, `text-scan`, `s1_snapshot`, `s1_pro_forma`, `no_api_key`); `--strict` keeps only `hardcoded` and recurses into derived components.
- **Offline vs live lanes**: the offline lane must never hit SEC/HKEX/SSE/CNINFO/LLM; live behavior reached only through `--run-live-sec`/`--run-slow`/eval gates.

---

## 8. Current coverage reality

### What tests cover (offline, strong)
Period math + LTM (`test_periods.py`), query orchestration (`test_financials.py`), citation/JSON contract (`test_cli_json_contract.py`, `test_citation_registry.py`), markdown render/polish idempotency, sectionize, China golden (`test_china_query_eval.py`), metric-directory byte-equality (`test_metric_directory_docs.py`), lazy startup (`test_cli_lazy_startup.py`), repo layout (`test_repo_layout.py`), diff + report, S-1 extraction (mocked LLM), self-heal + learned registry, translation validators (mocked DeepInfra), harvest planner + registry + universe, FTS5 search.

### What docs promise but tests do not (gated/mock-only)
- **Determinism on real filings**: an offline test exists but is too narrow (`test_pack_build.py:217`, `with_chunks=False`, in-process); no offline test exercises the surfaces that actually break (chunks/tiktoken state, SSE+translate manifest mutation). Full determinism is verified only live+slow (NVDA). (Corrected by Phase 1 verification 2026-06-16.)
- **Real-SEC format drift**: only `test_live_sec_integration.py` (gated, not CI).
- **Deep-link viewer_url/document_url**: depend on live submissions, mocked in offline tests.
- **Live LLM self-heal / KPI discovery**: always mocked; fuzzy-only is the de-facto offline behavior.
- **fetch_company_facts 404-vs-error split**: the single most load-bearing no-imputation boundary has no dedicated offline unit test.

### What code handles but tests do not
- `index_pack` manifest+chunks reading; `search_corpus` aggregation; HKEX `extract_facts_from_pack` LLM path scaling; the `--refresh` items-vs-skipped branch; observatory HTTP routes (zero tests); the two dead `DiskCache` TTL tests (`test_cache.py:64,78`, defined inside the `if __name__ == "__main__"` block after `unittest.main()`, so never collected; confirmed 2026-06-16 via `pytest --collect-only` = 3 tests collected, neither TTL test among them, so `missing meta = expired` and `corrupt meta = refetch` have zero coverage); annual `build_timeline` (shares `_compute_section_intensity` with pair-diff so intensity matches, but reports raw paragraph counts that include boilerplate because it skips the pair-diff boilerplate-invisible recount, `032 §2 D5`); `xbrl.json` production; build runner `_build_one` (network-bound).

### What fixtures exist
Committed HKEX packs (MiniMax `minimax_2024`, Zhipu `zhipu_2024`); `cerebras_s1_sample.md`, `cerebras_selected_financial_data.md`, `tsm_2006_malformed_span_table.html`, `s1_font_size_zero_wrapper.html`; synthetic packs built in `tmp_path`; `tests/eval/china_golden.yaml`; `data/fx_rates.csv`.

### What is likely only in implementation
The exact diff weighting constants; the translation router's deterministic table-cell conversion ladder; the self-heal shape-guard forbidden-token lists; the sectionizer inline-flatten recovery heuristics; the HKEX/SSE metadata defaults.

### What is unsafe to rewrite without characterization
`periods.py` (subtlest module, three fixed bugs); the HKEX extraction column-shift guard; the parse pipeline order + sectionizer; the translation magnitude invariant; the three-way fetch-failure distinction.

### Required coverage table

| Behavior | Current evidence | Coverage level | Risk | Suggested corpus case | Priority |
|---|---|---|---|---|---|
| Pack byte determinism | `test_determinism.py` (live+slow, NVDA only) | exact but gated | HIGH | offline fixture-fed determinism | P0 |
| LTM component-citation contract | `test_periods.py` + autouse harness `conftest.py:56` | exact, offline | HIGH | required-for-parity | P0 |
| Period vocabulary (lfy/mrq/ltm/annual:N) | `test_periods.py` (~85KB) | exact, offline | HIGH | required-for-parity | P0 |
| 404-vs-XBRLFetchError split | none dedicated; live only | none offline | HIGH | high-risk edge | P0 |
| Tokenizer-fallback determinism | `test_tokenize.py` (not cross-env) | partial | HIGH | high-risk edge (cold-tiktoken) | P0 |
| HKEX column-shift guard | `test_hk_extract.py` (9 regressions) | exact, offline | HIGH | high-risk edge | P0 |
| Lean/full JSON shape | `test_cli_json_contract.py` | semantic, offline | MEDIUM | required-for-parity | P1 |
| Metric directory byte-equality | `test_metric_directory_docs.py` | exact, offline | MEDIUM | required-for-parity | P1 |
| China golden native + USD | `test_china_query_eval.py` | semantic, offline | MEDIUM | required-for-parity | P1 |
| Diff suppression + intensity | `test_diff.py` | semantic, offline | HIGH | high-risk edge | P1 |
| Sectionizer TOC/INDEX | `test_sectionize.py` (gaps) | semantic, partial | HIGH | high-risk edge | P1 |
| S-1 snapshot extraction | `test_s1_financials_extract.py` | semantic, offline (mock LLM) | MEDIUM | high-risk edge | P1 |
| Translation fail-closed + tagging | `test_translation_validators.py` | semantic, offline (mock) | HIGH | high-risk edge | P1 |
| Self-heal fuzzy + shape guards | `test_self_heal.py` | exact, offline (mock LLM) | MEDIUM | high-risk edge | P1 |
| HKEX LLM unit-scaling (1000x) | none (path inert) | none | HIGH | known-bad | P1 |
| China fabricated `filed=Dec-31` | test enshrines it | exact (wrong) | MEDIUM | known-bad | P1 |
| FX period-average for annual flow | `test_china_fx.py` (gap) | partial | MEDIUM | known-bad | P1 |
| Observatory HTTP routes | none | none | LOW (parked) | parked-deprecated | P2 |
| Bare 6-digit A-share routing | docs disagree | uncertain | MEDIUM | uncertain | P1 |
| `build_timeline` annual divergence | none | none | MEDIUM | high-risk edge | P2 |
| Pre-IPO content-only-match rejection | `test_tickers_name_resolution.py` | semantic, offline | MEDIUM | high-risk edge | P1 |

---

## 9. Load-bearing weirdness seed list

Not removable. Each entry: location, why it looks weird, why it may exist, real-world condition, current test evidence, needed parity case, confidence.

1. **font-size:0 alone must NOT hide an element** (`parse/html_clean.py:95-100`). Weird: font-size:0 is the textbook cloaking signal yet is refused as a hide cue unless paired with another zero-size cue. Reason: modern S-1 renderers (Cerebras-era) use font-size:0 on the page-wrapper div while the body lives inside; treating it as hidden collapsed multi-MB filings. Real condition: absolute-positioned-div S-1 renderers. Evidence: `test_html_clean_s1_wrapper.py`. Parity case: S-1 wrapper preservation. Confidence: high.

2. **Zero/out-of-range colspan tolerated** (`parse/md_render.py:313-317`). Weird: `colspan='0'` and oversized colspans are clamped, not rejected. Reason: real TSM 2006 20-F has malformed spans; browsers render colspan=0 as 1; columns must not shift under currency headers. Evidence: `test_md_render.py:119` + `tsm_2006_malformed_span_table.html`. Parity case: malformed-span table render. Confidence: high.

3. **manifest `source.fetched_at` is the filing date, not real fetch time** (`pack/manifest.py:151-157`). Weird: a field named `fetched_at` does not record when bytes were fetched. Reason: determinism; real fetch time breaks byte-identity and cache keys. Evidence: `test_pack_build.py:30-59`. Parity case: stable-timestamp manifest. Confidence: high.

4. **HKEX column-count structural guard emits NO fact on mismatch** (`hk/extract.py:278-279`). Weird: a parsed numeric grid whose column count != year-header count yields silence, not a value. Reason: the column-shift P0 (2026-06-09) showed comma-less/decimal/negative columns mis-attributing every later year; silence over misattribution. Evidence: `test_hk_extract.py` (9 regressions). Parity case: column-shift regression set. Confidence: high.

5. **Per-share LTM degrades to annual** (`query/periods.py:577-619`). Weird: EPS LTM does not compute the three-component formula. Reason: per-share figures are non-additive across split boundaries. Evidence: `test_periods.py:361,2297,2316`. Parity case: per-share LTM degrade + `ltm_degraded`. Confidence: high.

6. **Balance-sheet LTM bypasses the LTM invariant** (`query/periods.py:621-642`). Weird: an instant metric returns the latest period-end balance, deliberately not satisfying `_assert_ltm_invariant`. Reason: balances are point-in-time; the latest balance IS the LTM-end balance. Evidence: `test_ltm_instant_returns_latest`. Parity case: instant-LTM latest balance. Confidence: high.

7. **Pre-IPO EDGAR name search hits an undocumented endpoint** (`sec/tickers.py:224`, `efts.sec.gov/LATEST/search-index`). Weird: an internal XHR backend, not a documented API. Reason: pre-IPO filers have no companyfacts/ticker; this is the only name->CIK path. Evidence: `test_tickers_name_resolution.py` + gated `test_resolve_live_identity.py`. Parity case: pre-IPO resolution (mocked). Confidence: high.

8. **Content-only-match rejection** (`sec/tickers.py:282-300`). Weird: a hit is discarded unless the query is a substring of the hit's own `display_names`. Reason: EDGAR FTS matches filing CONTENT; WhiteFiber's S-1 mentioning Cerebras would otherwise resolve `Cerebras` to WhiteFiber's CIK. Evidence: `test_resolve_company_by_name_rejects_content_only_matches`. Parity case: content-only-match rejection. Confidence: high.

9. **`_extract_values` breaks on first non-empty unit in a fixed order** (`query/periods.py:195-208`). Weird: iterates `(USD, shares, USD/shares, pure)` and breaks on the first present. Reason: companyfacts can report a concept under multiple units; deterministic USD-first avoids mixing scales. Evidence: implicit. Parity case: multi-unit-conflict. Confidence: high.

10. **Standalone-quarter threshold is 100 days, full-year 350-380 days** (`query/periods.py:379-406,35-36`). Weird: magic day windows. Reason: 4-4-5 retail and 52/53-week fiscal calendars; SEC files both 9-month-cumulative and 3-month-standalone for the same Q3 end. Evidence: `test_mrq_picks_standalone_not_cumulative`. Parity case: standalone-vs-cumulative quarter. Confidence: high.

11. **Production query reads `tests/fixtures/china_packs/`** (`query/financials.py:1981,1985`). Weird: shipping code resolves against the tests directory. Reason: HK fixture packs were the only committed HKEX corpus; the demo/CLI had to query minimax/zhipu offline. Real condition: offline HK demo. Evidence: `test_cli_json_contract.py` passing offline. Parity case: HK fixture query (and a flag for the CWD-must-be-repo-root assumption). Confidence: high.

12. **Translation number magnitude never delegated to the LLM** (`china/translate/numbers.py`). Weird: numbers are tagged to placeholders before the LLM call and restored after. Reason: a wan/yi error is a 10,000x mistake. Evidence: `test_table_translation.py`, validators. Parity case: number-tag round-trip. Confidence: high.

13. **Empty `gaps.csv` is a WARNING, not an error, in distill check** (`distill/checks.py:131-133`). Weird: a perfectly complete bundle fails soft. Reason: a fully complete extraction over a real filing is more likely under-reporting than truth. Evidence: documented, no direct test. Parity case: empty-gaps warning. Confidence: high.

14. **`--refresh` relabels counts but does not change the build set** (`harvest/planner.py:127-130`). Weird: a flag that changes accounting, not behavior. Reason: clean "already built" skip report over an already-idempotent delta planner. Evidence: planner tests (branch untested). Parity case: refresh items-vs-skipped. Confidence: high.

15. **Pack-status GET mutates state one tick per request** (`api/routes/packs.py:40-49`). Weird: a GET with a side effect. Reason: MVP simulates an async pipeline deterministically. Evidence: `test_china_api.py:38-48`. Parity case: pack-status tick (parked). Confidence: high.

16. **S-1 distill metric window anchors on the snapshot's max fiscal year, not the filing year** (`distill/builder.py:296-305,462-491`). Weird: anchors on the snapshot year then caps by filing year. Reason: an S-1 filed early in a year carries audited years + interim that trail the filing year by one; filing-year anchoring drops the newest legitimate data. Evidence: `test_distill_window_anchors_on_snapshot_years_not_filing_year`. Parity case: window anchoring. Confidence: high.

---

## 10. Bloat / deprecation seed list

Not recommendations to delete. Each: location/command, why it may have existed, evidence it may be inactive/parked, risk if removed, behavior to pin before removal, confidence.

1. **`--cik`/`-c` flag on build/company-llms/list** (`cli.py:392-394,528,546`). Existed: original CIK-keyed interface before the positional resolver. Inactive evidence: help text "[deprecated]", warning printed on use. Risk: scripts passing `--cik` break; some flows use it to bypass resolution. Pin: enumerate callers; confirm the positional path resolves the same CIKs (esp. pre-IPO/numeric). Confidence: medium.

2. **`site --base-url`** (`cli.py:569`). Existed: anticipated configurable deploy base URL. Inactive: "(reserved)", passed to `build_site` but never referenced in the body. Risk: low. Pin: confirm `build_site` does not branch on it. Confidence: medium.

3. **HKEX LLM extraction path** (`hk/llm_extract.py`, `hk/extract.py:606-609`). Existed: self-heal fallback mirroring the SEC path. Inactive: always called with `client=None`; facts.json fixtures only show `extraction_method='regex'`. Risk: removes a planned activation seam; the `unit='USD'` hardcode contract would mis-tag CNY filers if ever turned on. Pin: cache-key format and the `learned:llm` tag before removal. Confidence: low.

4. **`_COMPANY_META` hardcoded 6-entry HKEX metadata** (`hk/adapter.py:12`). Existed: manual pin of demo filers' currency/standard (PDF has no machine-readable field). Inactive: only 2 codes have built fixtures. Risk: removal without a replacement silently mislabels currency/standard (IFRS Alibaba/JD vs HKFRS; USD MiniMax). Pin: a filing-derived or universe.toml-derived metadata source first. Confidence: low.

5. **FastAPI Evidence Explorer workspace + `web/`** (`edgarpack/api/`, `web/`). Existed: China Lens MVP web product. Inactive: declared parked (`IMPLEMENTATION_TRACKER.md:5-7`); beads wontfix 2026-04-20; only built behind `SYMPHONY_WEB=1`; no JS tests; observatory/ask/documents routes untested. Risk: `web/` is git-tracked with a release gate; `test_china_api.py`/`test_api_exports.py` cover it. Pin: the in-memory seed corpus, the deterministic pack-status tick, and the citation-resolve contract. Confidence: medium (parked, not dead).

6. **Dead code from the 2026-06-09 review** (`BACKLOG.md` items 6,11,14): `strip_ixbrl_selectolax` alias (`ixbrl_strip.py:70`), `simplify_html` (`semantic_html.py:89`), `has_ixbrl`, hk `_parse` helpers, `comps.py` compat wrappers (`comps.py:58-85`, used by one test), dead skip-patterns in `sec/archives.py`. Existed: leftover scaffolding (a selectolax DOM path was tried and abandoned). Inactive: named in the adversarial review; commit `5914d11` already pruned one. Risk: low individually; grep for live callers first. Pin: exact symbols. Confidence: medium.

7. **`learned` source value `'user'`** (`learned_registry.py:9`). Existed: anticipated user-authored mappings. Inactive: no code path sets `source='user'`; verify uses `verif_method='manual'` and leaves source unchanged. Risk: documentation/contract drift only. Pin: confirm no external tool inserts `source='user'`. Confidence: low.

8. **`_STALENESS_YEARS` dict (always empty)** (`financials.py:64`). Existed: per-period staleness override hook. Inactive: never populated; falls back to default 2. Risk: a test may patch it. Pin: test usage. Confidence: medium.

9. **`PackRegistry.mark_indexed` (single) and `register_pack`** (`harvest/registry.py:252,158`). Existed: single-item companions. Inactive: only the batch variants are called. Risk: a migration/notebook may use them. Pin: external callers. Confidence: low.

10. **VLM `.desc.txt` output** (`pack/assets.py:132`). Existed: figure-search ambition. Inactive: nothing reads `.desc.txt`; not in chunks/search/citation path. Risk: the `download_assets` half (image fetch + src rewrite) IS load-bearing for registration markdown and must stay. Pin: confirm no external consumer + no figure-query roadmap. Confidence: low.

---

## 11. Reinvention questions for later

No final dependency decision. Classification only.

| Area | Current impl | Mature equivalent | Classification | Note |
|---|---|---|---|---|
| SEC company resolution | `cli.py:90`, `sec/tickers.py` | edgartools / sec-cik-mapper | likely delegatable | Strongest candidate; the share-class dot->dash, AmbiguousCompany UX, and pre-IPO issuer-name fallback are the differentiated parts. |
| Filing listing / submissions pagination | `sec/submissions.py:175` | edgartools `get_filings()` | likely delegatable | Columnar-page + 30d-immutable TTL + warn-and-continue are what edgartools abstracts; the "exhausted iterator = not found" no-imputation contract must survive. |
| Filing download / archives | `sec/archives.py` | edgartools | needs spike | Rate-limit-after-siblings behavior is deliberate; primary-only path avoids exhibits. |
| Section extraction (Item/Part) | `parse/sectionize.py:283` | edgartools TenK/TenQ items | needs spike | Highest-value spike; TOC-skip, inline-flatten recovery, cross-ref rejection, S-1 anchor whitelist are differentiated; basic Item split is delegatable. |
| XBRL facts retrieval | `sec/xbrl.py:29` | edgartools `get_facts()` | needs spike | The 404=>`{}` vs `XBRLFetchError` split is the load-bearing invariant; check the library's error model first. |
| Financial statements / period logic | `query/periods.py`, `financials.py` | edgartools Financials | likely differentiated | The cited-LTM model with component citations and None+typed-Diagnostic is the product IP. |
| Concept normalization | `query/layer_zero.py`, `concepts.py` | edgartools / us-gaap taxonomy | likely differentiated | Priority lists, duration/instant flags, forbidden-token shape guards encode economic judgment. |
| Rate limiting / cache | `sec/client.py`, `cache.py` | edgartools throttle / requests-cache / hishel | needs spike | Stdlib-only is a deliberate constraint; the unbounded-by-design, corrupt-refetch, missing-meta=expired cache semantics are intentional (eviction explicitly NOT wanted). |
| Filing markdown conversion | `parse/md_render.py`, `md_polish.py` | markdownify / html2text / pandoc | needs spike | The colspan/rowspan grid, malformed-table tolerance, and byte-determinism break under a library swap. |
| iXBRL stripping | `parse/ixbrl_strip.py` | Arelle / selectolax | likely differentiated | Deliberately regex-based for portability + determinism; a prior DOM impl was removed. |
| Form-specific parsing (S-1 heading injection) | `parse/s1_headings.py` | none directly | likely differentiated | Genuinely novel: reconstructs headings from TOC anchors for absolute-div renderers. |
| Token counting | `parse/tokenize.py` | tiktoken (already used) | likely delegatable | Already delegated; the `//4` heuristic fallback is the determinism liability. |
| Paragraph diff alignment | `diff/text_diff.py` | difflib / datasketch MinHash-LSH | likely differentiated | The SEC-noise suppression taxonomy is the value; generic diff resurfaces the noise. |

---

## 12. Commands discovered

| Command | Purpose | Safe offline | Likely side effects | Future parity harness |
|---|---|---|---|---|
| `edgarpack home` / bare invocation | print banner + starter commands | yes | stdout only | yes |
| `edgarpack --version` | print `EdgarPack 0.1.0` | yes | none | uncertain |
| `edgarpack build <co> [...]` | build a SEC pack | no | writes pack + registry; network | uncertain (corpus-gen) |
| `edgarpack list <co>` | list recent filings | no | none | no |
| `edgarpack company-llms <co>` | company-level llms.txt | no | writes `llms.txt`; network | uncertain |
| `edgarpack site --packs ... --out ...` | static reader site | yes | writes site (rmtree targets) | yes |
| `edgarpack cache [--clear]` | inspect / clear SEC cache | yes | `--clear` rmtree CACHE_DIR (refetchable) | no |
| `edgarpack doctor <pack\|ticker>` | pack health | yes (path) / no (ticker) | reads registry | yes |
| `edgarpack identify <token>` | routing oracle | uncertain | network for unknown tokens | yes |
| `edgarpack query <co> <metrics> -p <sel>` | cited metric query | no | SEC cache + learned registry writes | uncertain |
| `edgarpack query zhipu revenue --format json` | offline HK fixture query | yes | reads fixture packs | yes |
| `edgarpack comps <cos> -m <metrics>` | cross-company comps | no | network + cache | uncertain |
| `edgarpack compare <cos> [-m]` | side-by-side compare | no | network | uncertain |
| `edgarpack which <co>` | KPI discovery | yes (China) / no (SEC LLM) | KPI cache; LLM shell-out | yes (China) |
| `edgarpack f1\|s1 <co> [metrics]` | build-then-query registration | no | writes pack + registry | uncertain |
| `edgarpack diff --before A --after B --format json` | offline pack diff | yes | diff cache | yes |
| `edgarpack diff --ticker NVDA` | registry-driven diff | uncertain | ticker resolution + diff cache | yes |
| `edgarpack timeline --series registration --cik ... --packs ...` | registration redline | yes | reads packs; html writes dir | yes |
| `edgarpack timeline --ticker ... --section ...` | annual section evolution | uncertain | ticker resolution | uncertain |
| `edgarpack search "<q>" [--topic ...]` | FTS5 corpus search | yes | creates empty index if missing | uncertain |
| `edgarpack index --packs ... [--incremental]` | build/update FTS5 index | yes | writes index + registry flags | uncertain |
| `edgarpack harvest --universe ... --plan` | dry-run delta plan | no | planning hits SEC | uncertain |
| `edgarpack harvest --universe ... --refresh --with-chunks` | bulk build | no | packs + registry + errors; heavy SEC | no |
| `edgarpack build-sse <code> --latest-annual` | China A-share pack | no | CNINFO download + pack | no |
| `edgarpack build-sse --pdf <local> ... --translate` | local build + translate | no | DeepInfra translation | no |
| `edgarpack translate-sse --pack <dir>` | translate SSE pack | no | DeepInfra + writes `.en.md`/manifest/cache | no |
| `edgarpack learned list\|show\|verify\|clear` | manage learned registry | yes | verify/clear MUTATE registry.db | yes |
| `edgarpack distill run <slug> --pack <dir>` | compress one pack | yes | writes reports/<slug>/ (8 files) | yes |
| `edgarpack distill check <bundle>` | validate a bundle | yes | none | yes |
| `edgarpack api --host ... --port ...` | run FastAPI (parked) | yes | binds socket; seeds fixtures | uncertain |
| `scripts/symphony_quality_gate.sh` | repo quality gate | uncertain | writes cache; web build with SYMPHONY_WEB=1 | no |
| `scripts/clean.sh [--corpus]` | wipe regenerable clutter | no | destructive (deletes packs/site/caches) | no |
| `scripts/generate_metric_directory.py` | regen metric directory | yes | overwrites the two docs (drift-guarded) | yes (read-only) |
| `scripts/build_hk_fixture_packs.py` | rebuild HK fixture packs | yes | overwrites fixtures (uses committed PDFs) | yes |
| `scripts/benchmark_efficiency.py` | compression benchmark | no | network + writes benchmarks/ | uncertain |
| `scripts/refresh_fx.py` | refresh `data/fx_rates.csv` | no | FRED network; rewrites CSV | no |
| `scripts/download_hk_prospectus.sh` | download HK prospectus PDFs | no | network | no |
| `scripts/daily-refresh.sh` (launchd) | automated daily harvest+index | no | network; writes packs/index/logs | no |
| `uv run --extra dev ... pytest -q` | offline test lane | yes | temp cache/tmp_path | yes |
| `pytest --run-live-sec` / `--run-slow` / `--live-sec-full` | gated lanes | no | live SEC network + cache | yes (live oracle) |

---

## 13. Open questions for Samay

Only questions that materially affect the rewrite.

1. **Version semantics.** Should the user-facing `__version__` (`0.1.0`, `__init__.py:5`) be reconciled with `PARSER_VERSION`/`SCHEMA_VERSION` (`0.2.1`/`1`), or is the divergence intentional (release vs parser-determinism version)? The rewrite needs the canonical version source.

2. **Three comparison surfaces.** `query`/`comps`/`compare` are three overlapping comparison surfaces with three metric-arg contracts and three formatter stacks. Keep all three, or consolidate, and if consolidating, which output is the parity oracle?

3. **Known-bad disposition.** For the ~16 `docs/BACKLOG.md` items, which are "pin current (wrong) output for parity then fix" vs "fix during the rewrite"? Specifically the HKEX LLM 1000x unit-scaling (`hk/llm_extract.py:102-115`), the test-enshrined China `filed=Dec-31` date (fabricated at `financials.py:2076`, assigned at `:2111-2113`), and the FX one-month-average-for-annual-flow (`fx/convert.py:71-73`) all touch the cited-value promise. The parity corpus must pin either the current or the intended number; the call is yours.

4. **Parked FastAPI/web.** Is the Evidence Explorer / `web/` definitively retired for vNext, or revived if China Lens becomes a web product again? This decides whether `site` is the only web surface carried forward and whether the observatory HTTP routes need a seeded fixture before rewrite.

5. **HKEX wiring + metadata source.** Should `facts.json` generation be wired into the CLI (an `edgarpack build-hk` like `build-sse`), or is HKEX intentionally fixture-only? And should HKEX/SSE currency/accounting-standard come from the filing or `universe.toml` rather than the hardcoded 6-entry `_COMPANY_META`?

6. **Determinism guarantee scope.** Should byte-determinism hold across machines where tiktoken's `cl100k_base` asset is absent on one run and present on another (`tokenize.py:48-55`)? If yes, `tokens_total` and chunk boundaries are determinism hazards; should the rewrite declare tiktoken a hard precondition and drop the heuristic fallback, plus add an offline determinism test?

7. **edgartools delegation.** Is delegating SEC company resolution / filing listing / submissions / companyfacts to edgartools on the table, given the project deliberately keeps core deps to pydantic+tiktoken and explicitly does NOT want cache eviction? The 404-vs-error split and the no-imputation pagination contract must survive any delegation.

8. **A-share routing truth.** Does current code route a bare 6-digit A-share code (e.g. `688696`) through the SSE path, or does it still fall into SEC CIK `0000688696` -> 404 -> N/A as the 2026-04-27 XGIMI research note records? The research note and the China tracker disagree; only running code (which Phase 0 cannot) or your call settles which is the oracle.

9. **Production fixture-path dependency.** `query/financials.py:1981` reads `tests/fixtures/china_packs/` from production code (and assumes CWD is the repo root). Is this a permanent demo path or a bridge to a config-driven pack root? The rewrite needs a real pack-root config either way.

10. **Parity exactness.** Is exact-byte snapshot parity a goal for the artifacts that currently leak absolute paths (distill bundles, manifests, registry rows), or is normalized/semantic parity sufficient given those leaks and the non-deterministic upstream `s1_financials.json` LLM output?
