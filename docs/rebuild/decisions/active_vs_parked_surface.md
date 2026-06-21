# Active vs Parked Surface (Phase 0 decision-prep)

Status: decision-PREP, not a final decision. This file inventories every user- or agent-facing surface in EdgarPack and classifies it as active / parked / experimental / deprecated-candidate / uncertain, with repo evidence (git recency, test coverage, docs references, quality-gate wiring, `universe.toml` presence). Phase 0 pins current behavior; it does not decide what vNext keeps. Where the discovery corpus and a live read disagreed, the live read wins and is cited.

Method note on evidence types used below:
- Git recency: `git log --oneline -3 -- <path>` (run 2026-06-16 on branch `codex/f1-registration-upgrade`).
- Quality-gate wiring: `scripts/symphony_quality_gate.sh` (the CI gate). Default lane runs ruff + mypy + offline pytest (lines 11-14); web build is opt-in behind `SYMPHONY_WEB=1`/`SYMPHONY_RELEASE=1` (lines 16-22); China-golden subset behind `SYMPHONY_CHINA_GOLDEN=1` (lines 24-29).
- Parked declarations: `docs/china-lens/IMPLEMENTATION_TRACKER.md:5` ("CLI path active; workspace parked").

The three China surfaces (HKEX facts, SSE/CNINFO build, zh->en translation) and the three frontends (static site, FastAPI api, Next.js web) differ in activity and are split out deliberately.

---

## 1. Active surfaces

Definition used here: shipped, exercised by offline tests in the default quality-gate lane, documented, and (for filer-facing paths) backed by `universe.toml` entries.

### 1a. Core CLI commands

| Surface | Entry | Recent git evidence | Offline test coverage | In default gate | Verdict |
|---|---|---|---|---|---|
| `query` | `cli.py:590` parser, `_cmd_query cli.py:2407` | period/financials work is the densest area; `f73972e` (silent-degrade fixes) | `test_cli_json_contract.py`, `test_cli_query_currency.py`, `test_cli_self_heal.py`, `test_periods.py` (~85KB), `test_financials.py` (~101KB) | yes | active |
| `comps` | `cli.py:896`, `_cmd_comps cli.py:2659` | shares query machinery | `test_cli_json_contract.py` (comps json) | yes | active |
| `compare` | `cli.py:1041` parser, separate module `edgarpack/compare.py:441` | dispatched FIRST in if-chain `cli.py:1155-1158` | `test_cli_json_contract.py` (compare json) | yes | active |
| `which` | `cli.py:996`, `_cmd_which cli.py:3809` | KPI discovery active | `test_cli_which_ux.py`, `test_kpi_extract.py` (~79KB) | yes | active |
| `build` | `cli.py:374`, `_cmd_build cli.py:1426` | `test_cli_build_range.py`, `test_build_pack_registration.py` | yes (mocked fetch) | active |
| `doctor` | `cli.py:452`, `_cmd_doctor cli.py:1283` | `test_cli_doctor.py`, `test_pack_doctor.py` | yes | active |
| `diff` | `cli.py:799`, `_cmd_diff cli.py:2912` | `fde4f93`/`cbd402e`/`c030d9c` (moved-detection, diff cache v7) June 2026 | `test_diff.py` (~32KB), `test_diff_report.py` (~28KB) | yes | active |
| `timeline` (registration) | `cli.py:825`, `_render_registration_timeline cli.py:3038` | F-1/S-1 churn | `test_registration_timeline.py`, `test_cli_registration_timeline_render.py` | yes | active |
| `distill run`/`check` | `cli.py:473`, `_cmd_distill cli.py:1375` | `test_distill.py` | yes | active |
| `f1` / `s1` (registration shortcuts) | dynamic, `_add_registration_shortcut cli.py:672`, registered `cli.py:745-746` | TOP 3 commits all F-1/S-1: `aa1d544`, `f015b9f`, `6273398` | `test_cli_registration_shortcut.py` | yes | active (newest, most-churned) |
| `identify` | `cli.py:584`, `_cmd_identify cli.py:1657` | `test_cli_identify.py`, `test_cli_identity_fallthrough.py` | yes | active |
| `harvest` | `cli.py:748`, `_cmd_harvest cli.py:2832` | `test_planner_registration.py`, `test_harvest_universe.py`, `test_harvest_registry.py` | yes (planner/registry only; runner is network-bound, untested) | active |
| `index` | `cli.py:880`, `_cmd_index cli.py:3306` | `20dd8d7` (FTS purge fix) | `test_search_index.py` (index_pack path untested) | yes | active |
| `search` | `cli.py:870`, `_cmd_search cli.py:3269` | underlying `SearchIndex.search` tested; `search_corpus` not | partial | active |
| `learned` (list/show/verify/clear) | `cli.py:956`, `_cmd_learned cli.py:3359` | `test_cli_self_heal.py` (indirect) | partial | active |
| `cache` / `site` / `api` / `list` / `company-llms` | `cli.py:552/555/571/538/519` | none of these five have a dedicated CLI test | no (CLI-level) | active (under-tested; see notes) |

Note: `cache`, `list`, `company-llms` have no dedicated CLI test (discovery slice "cli" tests row, `coverage_level:none`). They are active product commands but a parity harness must add coverage. `site` and `api` are treated separately under Frontends (Section 3) because their downstream surfaces differ in activity.

### 1b. SEC fetch / parse / pack core (the load-bearing engine)

| Surface | Evidence of active | In gate |
|---|---|---|
| SEC client + cache (`edgarpack/sec/client.py:80`, `cache.py:12`) | `test_sec_client.py`, `test_cache.py`, `test_submissions_pagination.py` | yes |
| Identity resolution (`identity.py:104`, `sec/tickers.py:138`) | `test_china_identity.py`, `test_tickers.py`, `test_tickers_name_resolution.py` | yes |
| 6-step parse pipeline (`parse/ixbrl_strip..sectionize`) | `test_ixbrl_strip.py`, `test_html_clean.py`, `test_md_render.py`, `test_md_polish.py`, `test_sectionize.py` | yes |
| Pack build orchestrator (`pack/build.py:145`) + manifest | `test_pack_build.py`; live determinism `test_determinism.py` (gated) | yes (offline), gated (live determinism) |
| Query core periods/LTM/citations (`query/periods.py`, `models.py`, `citations.py`) | `test_periods.py`, `test_citation_registry.py`, `test_query_models_source.py` + suite-wide LTM autouse harness `conftest.py:55` | yes |
| Metric resolution (`layer_zero`, `concepts`, `self_heal`, `strict`) | `test_layer_zero.py`, `test_concepts.py`, `test_self_heal.py`, `test_cli_self_heal.py` | yes |
| S-1/F-1 snapshot extraction (`query/s1_financials.py`) | `test_s1_financials_extract.py` (~42KB), `_citation`, `_query_integration` | yes (LLM mocked) |
| Diff engine (`diff/section_diff.py`, `text_diff.py`, `html_report.py`) | `test_diff.py`, `test_diff_report.py` | yes |

### 1c. China surface 1 of 3: HKEX facts extraction (`edgarpack/hk/`)

Active but fixture-only on the producer side, live on the read side.

| Aspect | Evidence | Verdict |
|---|---|---|
| Read path (`query`/`comps`/`compare` route HKEX -> `facts.json`) | `_query_china_pack financials.py:2128`; declared active `IMPLEMENTATION_TRACKER.md:5`; `test_china_query_hk.py` | active |
| Extraction (`hk/extract.py:566`, `extract_facts_from_pack`) | most recent commit `8a3bb61 fix(hk): stop column-shift misattribution` (2026-06-09, the column-shift P0) | active, recently hardened |
| `universe.toml` backing | 8 `hk_stock_code` entries (grep count); Tencent `00700`, MiniMax `00100`, Zhipu `02513`, Meituan `03690`, Alibaba `09988`, JD `09618` | active filer set |
| Golden parity | `tests/eval/china_golden.yaml` (MiniMax, Zhipu) + committed fixture packs `tests/fixtures/china_packs/{minimax,zhipu}_2024/` | active offline oracle |
| Producer wiring | NOT wired into CLI `build`; only producible via tests and `scripts/build_hk_fixture_packs.py` (discovery slice "hk" open_questions) | active-but-fixture-only |

### 1d. China surface 2 of 3: SSE / CNINFO PDF build (`edgarpack/sse/`, `edgarpack/china/acquire/`)

| Aspect | Evidence | Verdict |
|---|---|---|
| `build-sse` CLI | `cli.py:1069`, `_cmd_build_sse cli.py:1748`; declared active `IMPLEMENTATION_TRACKER.md:5` | active |
| SSE query path | `54e0214 Add XGIMI SSE annual report query path` (most recent sse/ commit) | active |
| `universe.toml` backing | XGIMI `688696` (STAR/Shanghai), Unitree `301536` (ChiNext) per discovery; ~6 stock_code entries | active filer set |
| Test coverage | `test_sse_pack.py` (mocked `pdf_to_markdown`), `test_china_query_sse.py` (synthetic XGIMI pack) | active, offline-mocked |
| facts.json producer wiring | NOT in CLI build for HKEX-style; `build-sse` is the only SSE producer; only 4 metrics extracted (`sse/annual_facts.py:22-43`) | active, narrow scope |

### 1e. China surface 3 of 3: zh->en translation (`edgarpack/china/translate/`)

| Aspect | Evidence | Verdict |
|---|---|---|
| `translate-sse` CLI | `cli.py:1124`, `_cmd_translate_sse cli.py:1888` (~400-line inline orchestrator) | active |
| Recent git | `449ca16 fix: harden SSE table cell fallback (#16)`, `a75d7c7 fix: harden SSE translation recovery (#15)` | active, hardened |
| Test coverage | `test_deepinfra_translator.py`, `test_translation_validators.py`, `test_translation_cache.py`, `test_table_translation.py`, `test_translate_sse_artifacts.py` (DeepInfra mocked) | active, offline-mocked |
| Network dependency | DeepInfra (`EDGARPACK_DEEPINFRA_KEY`); no live translation test in repo | active but never live-tested |

### 1f. Generated docs and parity anchors

| Artifact | Evidence | Verdict |
|---|---|---|
| `docs/METRIC_DIRECTORY.json` / `.md` | `test_metric_directory_docs.py` asserts byte-equality with `scripts/generate_metric_directory.py` | active (strongest doc-vs-code drift guard) |
| `tests/eval/china_golden.yaml` | `test_china_query_eval.py` runs it in the DEFAULT offline lane (see uncertainty below re: `eval` marker) | active |
| `data/fx_rates.csv` | consumed by `test_china_query_eval.py` USD path + `fx/rates.py` | active offline FX oracle |
| Repo layout allowlist | `test_repo_layout.py:31-37` allowlists `tests`, `web`, `cerebras.toml` | active guard |

---

## 2. Parked surfaces

Definition: present, importable/buildable, sometimes tested, but explicitly declared not-the-current-product, or with no caller/wiring into the active path.

### 2a. China Lens FastAPI Evidence Explorer workspace

The single clearest parked declaration in the repo.

| Evidence | Citation |
|---|---|
| Explicit parked statement | `docs/china-lens/IMPLEMENTATION_TRACKER.md:5`. "What is parked: the Evidence Explorer / FastAPI workspace (`edgarpack api`) and every item in the Open list below" |
| Beads closed wontfix | same line: "workspace beads were closed wontfix on 2026-04-20 (`edgarpack-lb1` epic plus `lb1.4`, `lb1.7`, `lb1.11`, `lb1.12`, `lb1.14`, `4o4`, `kax`)" |
| Git recency | `edgarpack/api/` last functional change `737c602` (cleanup) + mechanical mypy/index fixes (`20dd8d7`, `89f1760`); no `/ask` or `/documents` test |
| Still tested (so not dead) | `test_china_api.py` (skipped unless fastapi installed), `test_api_exports.py` | 
| Observatory sub-router | `api/observatory/routes.py`. NO HTTP-level test in repo (discovery slice "observatory-index" tests row) |

Verdict: parked. `edgarpack api` (the CLI command at `cli.py:571`) is the live entrypoint to a parked workspace. It imports cleanly and serves seeded Tencent (`cmp_tencent_0700`) fixtures offline, but is not the product surface.

### 2b. Next.js `web/` frontend (rogo-china-lens-web)

| Evidence | Citation |
|---|---|
| Parked plumbing | `IMPLEMENTATION_TRACKER.md` (per discovery slice "site-api-web"): "Evidence Explorer interactions still need plumbing past the first screen" |
| Git recency | `web/` last commit `2026-04-30` (`d11c114`), untouched while the active branch does F-1 CLI work |
| Gate wiring | only built when `SYMPHONY_WEB=1` (`symphony_quality_gate.sh:16`); default gate skips web entirely |
| Tracked allowlist entry | `test_repo_layout.py:32` (`web`); tracked on purpose, not sprawl |
| Test coverage | no JS unit/integration tests; only `web/scripts/smoke-assets.sh` (needs running dev server) |

Verdict: parked frontend shell. Tracked and gated-on-demand, but not in the default pipeline and not iterated since April.

### 2c. Observatory HTTP routes (the data-backed half of the FastAPI app)

| Evidence | Citation |
|---|---|
| Built at import in `api/observatory/routes.py:218`, mounted `api/main.py:67` | data-backed (reads real `registry.db`/`search_index.db`) |
| No HTTP-level test | discovery slice "observatory-index" / "site-api-web": zero tests reference observatory routes |
| Consumed only by parked `web/` Observatory views | `web/lib/observatory-api.ts` |

Verdict: parked-adjacent. Lives inside the parked FastAPI workspace; the underlying diff/index/timeline engines are active (Section 1), but this route layer is untested and only consumed by the parked frontend.

### 2d. Prior vNext clean-rewrite plan (INVENTORY ONLY)

| Evidence | Citation |
|---|---|
| Self-marked archived | `docs/archive/internal/superpowers/plans/2026-04-24-edgarpack-vnext-clean-rewrite.md` (2925 lines) marked "Archived 2026-04-25 ... not the current EdgarPack roadmap" |
| Repo policy | `docs/archive/internal/README.md`: archived rewrite plans "should not be treated as roadmap unless explicitly revived in a new bead" |
| No `edgarpack_next/` package exists | proposed Typer/Rich/evidence-verb design never built |

Verdict: parked artifact, OUT OF SCOPE as a design source per Phase 0 rules. Inventoried here only to record that it exists; its architectural conclusions (Typer, Rich, `edgarpack_next`, FastAPI evidence-verbs) are not adopted.

---

## 3. Experimental surfaces

Definition: shipped and reachable but opt-in, scaffolded-but-inert, or not wired into the citation/product path.

| Surface | Evidence | Why experimental |
|---|---|---|
| VLM image description (`build --describe-images`, `pack/assets.py:144`) | flag is off by default; `.desc.txt` outputs NOT consumed by query/citation/search path (discovery slice "query-s1" deprecation_signals) | opt-in, dead-end output, the only true vision-model usage |
| HK LLM fallback (`hk/llm_extract.py:69`) | called with `client=None` in production (`llm_extract.py:84-85`); `facts.json` fixtures contain only `extraction_method='regex'`, never `'learned:llm'` | scaffolded-but-inert |
| Self-heal LLM proposal (`self_heal.py:416`) | shells out to `codex`/`claude` on PATH detected at import (`self_heal.py:351`); fuzzy-only when no backend; host-dependent | reachable but non-deterministic/optional |
| `static site` generator (`edgarpack site`, `edgarpack/site/build.py:45`) | ACTIVE + tested (`test_site_build.py`), but `--base-url` flag accepted and never used (`cli.py:569`, unreferenced in `build.py` body) | mostly active; one experimental/reserved param |

Clarification on the static site (frontend 1 of 3): it is the ONLY frontend with real offline unit tests (`test_site_build.py`) and is the most active of the three frontends (`edgarpack/site/` touched in `11e6e17`, `d11c114`, `89f1760`). It is classified active overall; only its `--base-url` param is experimental/reserved. Contrast with the FastAPI api (parked, 2a) and Next.js web (parked, 2b).

---

## 4. Deprecated candidates

Definition: evidence of being superseded, inert, or leftover, with at least one independent signal. Each needs a grep for live callers before removal; do not delete on this evidence alone.

| Candidate | Evidence inactive | Why it existed | Risk |
|---|---|---|---|
| `edgarpack/insights/` (disclosures, emerging, language_shift) | grep `from edgarpack.insights` returns ONLY `tests/test_insights.py` (verified live); no CLI subcommand, no API route, no doc command surface | the analytical payoff layer (new disclosures, language shifts, emerging topics) intended for an API/web surface never wired | medium; `emerging.py` encodes the documented "count by unique accession" invariant; confirm no planned surface before treating dead |
| `eval` pytest marker | declared in `pyproject.toml` markers but grep `pytest.mark.eval` returns ZERO usages (verified live); `test_china_query_eval.py` runs in the default lane | intended to gate the China golden harness as opt-in | low functional; but its absence means the golden tests run on every fast pytest, which a rewrite must know |
| `strip_ixbrl_selectolax` (`parse/ixbrl_strip.py:70`) | explicit compat alias for a removed DOM impl; no production caller in build path; untested | breadcrumb from a removed selectolax DOM stripper | low; grep whole repo + docs/learn before removal |
| `--cik`/`-c` flags on build/company-llms/list (`cli.py:392/528/546`) | help text literally `[deprecated]`; warning printed when used (`cli.py:1250-1253`); positional resolver is the documented path | original CIK-keyed interface before the positional resolver | medium; scripts may pass `--cik`; enumerate callers (esp. numeric-CIK/pre-IPO) first |
| `site --base-url` (`cli.py:569`) | help says `(reserved)`; never referenced in `build.py` body | anticipated configurable deploy base URL | low; confirm `build_site` doesn't branch on it |
| `metric_map.py` (standards-keyed `METRIC_MAP`/`resolve_concepts`) | `financials.py` imports `resolve_concept` from `.concepts`, NOT `resolve_concepts` from `.metric_map` | earlier accounting-standard-keyed map superseded by `concepts.py` MetricMeta | medium; trace china/hk/comps importers before removal |
| `learned` source value `'user'` | documented in `learned_registry.py` docstring but `upsert` never writes it; verify uses `verif_method='manual'` | parked hook for manual concept authoring | low; contract surface only, strict already rejects non-hardcoded |
| `_STALENESS_YEARS` dict (`financials.py:64`) | declared empty, never populated; default always used | unused per-period staleness override hook | medium; pin test usage first |
| Dead skip-patterns / hk `_parse` helpers / comps compat wrappers | `docs/BACKLOG.md` items 6,11,14,15; commit `5914d11` already dropped one xlsx skip-pattern | refactor residue | medium; BACKLOG already did much of this grep |
| `daily-refresh.sh` + `com.edgarpack.refresh.plist` | hardcodes an absolute checkout path; uses `.venv/bin/edgarpack` not `uv run`; no test | operator cron for Observatory corpus | low; confirm corpus still refreshed |

---

## 5. Uncertain surfaces requiring Samay judgment

These cannot be resolved from current code/docs alone and are decision inputs, not conclusions.

| Question | Conflicting / missing evidence | Why it needs Samay |
|---|---|---|
| Are the three China surfaces (HKEX read, SSE build, translation) all in scope for vNext, or is one being narrowed? | All three are active (Section 1c-1e) but producer paths are fixture-only (HK) or narrow (SSE 4 metrics, `sse/annual_facts.py:22-43); translation never live-tested | Product scope call |
| Is the FastAPI Evidence Explorer + `web/` definitively dead, or revived if China Lens becomes a web product? | `IMPLEMENTATION_TRACKER.md:5` says "Revisit only if China Lens becomes a web product surface again" | Decides whether `static site` is the only web surface carried forward |
| Bare 6-digit A-share routing (e.g. `688696`): does code route via SSE, or fall into SEC CIK `0000688696` -> 404 -> N/A? | `docs/research/2026-04-27-xgimi-china-filer-smoke.md:74,80` records the 404 behavior; `IMPLEMENTATION_TRACKER.md` claims raw codes route correctly. Docs contradict; Phase 0 may not run code to arbitrate | Resolve before pinning China A-share parity |
| Should `__version__` (0.1.0, `__init__.py:5`) be reconciled with `PARSER_VERSION` (0.2.1) / `SCHEMA_VERSION` (1) (`config.py:50-51`)? Verified divergence live | They intentionally track different things (release vs parser-determinism); unifying would invalidate all pack caches | Canonical version semantics for vNext |
| Is `edgarpack/insights/` a parked experiment to ship, or library-only utility, or removable? | zero callers outside its test (verified); no doc/command surface | Whether the rewrite preserves it as a feature |
| Should the `static site` be promoted to the canonical "publish a readable corpus" surface, replacing the parked Next.js Observatory UI? | site is the only tested+deterministic+offline frontend (`test_site_build.py`) | Frontend strategy |
| Is `tests/parity/` reserved for this rewrite's parity harness? | Directory does not currently exist on disk (verified: `git ls-files tests/parity` empty, no dir); Phase-0 prompt permits new files under `tests/parity/` for synthesis agents | Confirms harness home + structure conventions |
| Of the ~16 `docs/BACKLOG.md` known-bad items, which are "preserve for parity then fix" vs "fix in rewrite"? | Notably the test-enshrined China Dec-31 fabricated `filed` date (`financials.py:2092-2098`) and the HK 1000x LLM unit-scaling bug (`hk/llm_extract.py:102-115`) both touch the cited-value promise | Whether parity corpus pins current (wrong) or intended output |
| Is the investor-workbench-p0 direction (`docs/superpowers/specs/2026-05-11`) shelved, partially shipped, or the shape of vNext? | May had ~10 commits; June pivoted to diff/F-1 work | Materially affects what the rewrite optimizes for |

---

## Appendix: frontend and China-surface activity matrix (the explicitly-requested split)

Three frontends:

| Frontend | Git recency | Default-gate tested | Parked? | Verdict |
|---|---|---|---|---|
| Static site (`edgarpack/site/`, `edgarpack site`) | `89f1760`, `d11c114`, `11e6e17` | yes (`test_site_build.py`) | no | ACTIVE |
| FastAPI api (`edgarpack/api/`, `edgarpack api`) | `737c602` + mechanical fixes | partial (`test_china_api.py` skip-gated, no `/ask`/`/documents`/observatory) | yes (`IMPLEMENTATION_TRACKER.md:5`) | PARKED |
| Next.js web (`web/`) | `2026-04-30` (`d11c114`) | no (only `SYMPHONY_WEB=1`) | yes | PARKED |

Three China surfaces:

| China surface | Module | Most recent commit | Producer wiring | Verdict |
|---|---|---|---|---|
| HKEX facts | `edgarpack/hk/` | `8a3bb61` (2026-06-09, column-shift P0) | fixture-only producer; live read path | ACTIVE (fixture-only producer) |
| SSE/CNINFO build | `edgarpack/sse/`, `china/acquire/` | `54e0214` (XGIMI query path) | `build-sse` only; 4 metrics | ACTIVE (narrow) |
| zh->en translation | `edgarpack/china/translate/` | `449ca16` (#16, harden table cell) | `translate-sse`; never live-tested | ACTIVE (offline-mocked only) |
