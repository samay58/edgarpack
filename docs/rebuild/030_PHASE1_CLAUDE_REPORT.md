# Phase 1 assessment (Claude): EdgarPack ahead of a possible clean-room rebuild

Status: written assessment only. No product code written, no rewrite started, no implementation proposed, current implementation unmodified. Read-only.

Method: this assessment is independent of, but cross-checked against, the Phase 0 behavior corpus (`docs/rebuild/010_PHASE0_BEHAVIOR_CORPUS.md`, `tests/parity/corpus.yaml`, and the four `decisions/` + `memos/` files). To avoid circularly re-stating Phase 0, four read-only verification passes re-derived behavior directly from source for the four highest-stakes subsystems (query/period engine; SEC acquisition; parse/pack/determinism; China/diff/observatory/distill/frontends). Where this pass disagrees with or sharpens Phase 0, it is marked AGREE / DISAGREE / EXTEND. Confidence is marked high/medium/low. The prior archived vNext plan in `docs/archive/internal/superpowers/` was deliberately not used as input.

Branch assessed: `codex/f1-registration-upgrade`. PARSER_VERSION 0.2.1, SCHEMA_VERSION 1.

---

## 1. Executive summary

**What EdgarPack actually does.** It turns filings (SEC, HKEX, SSE/CNINFO) into deterministic, section-addressable markdown packs, then answers cited financial queries, discovers KPIs, and produces evidence-linked filing diffs on top of those packs. Verified from the code, not assumed: the citation model is a data-model contract (`CitedValue`/`DerivedValue` in `query/models.py`), not a formatting convention, and the LTM case is enforced by a runtime assertion (`query/periods.py:483`, `_assert_ltm_invariant`) plus a suite-wide autouse harness (`tests/conftest.py:55-98`). Confidence: high.

**Highest-level product contract.** Every returned value or changed paragraph carries its filing provenance, and a missing fact returns `None` plus a typed diagnostic, never a guess. The contract is real and load-bearing in three concrete mechanisms: the LTM component-citation rule (a non-null `ltm` must carry `{mrp, lfy, mrp_prior}` or it flips to `None` + `ltm_incomputable`); the 404-vs-error split on the XBRL read path (`sec/xbrl.py:72-76`: a real SEC 404 returns `{}` diagnostic-free, any other failure raises `XBRLFetchError`); and the HKEX column-count guard (`hk/extract.py:278-279`: a misaligned grid emits no fact rather than misattributing a value to the wrong year). Confidence: high.

**Should a clean-room rebuild proceed?** My position, medium-high confidence: **not as a from-scratch clean room. Proceed instead with harness-first, in-place re-architecture.** Reasoning, and I will defend it: the codebase's value is concentrated in hard-won, under-tested edge handling (the period engine, malformed-HTML survival in the parse pipeline, the China PDF extraction, diff noise suppression). The single hardest invariant, byte-determinism, has no offline regression test that exercises the surfaces that actually break it (verified below). A clean-room rewrite's dominant failure mode is exactly losing this scar tissue, and you would be reproducing it blind. The honest sequencing is: (1) build the offline parity + determinism harness first (the Phase 0 corpus is the seed, but it is not yet executable), (2) re-architect module by module behind that harness, (3) settle the edgartools delegation question with a spike. If a clean-room rebuild is mandated regardless, gate its start on step 1. A rewrite without the harness is the highest-risk option on the table.

**Biggest regression risk.** Byte-determinism. It is the load-bearing invariant under the pack cache (PARSER_VERSION/SCHEMA_VERSION keying) and under the diff engine (which compares packs paragraph by paragraph), and it has at least four verified ways to break with no offline test catching them: the tiktoken-cold `len//4` tokenizer fallback that silently changes chunk boundaries and hashes (`parse/tokenize.py:48-55`, `pack/chunks.py:167`), the SSE+translate manifest mutated after its own hash (`pack/build.py:564-571`), the all-or-nothing latin-1 decode fallback (`pack/build.py:83-88`), and the silent image-drop on a transient asset fetch failure (`pack/assets.py:78-82`). Confidence: high.

**Biggest simplification opportunity.** Two, roughly equal. First, the SEC acquisition plumbing that is genuinely commodity (the `company_tickers.json` map in `sec/tickers.py`, and the archive document download in `sec/archives.py`) is a clean delegation candidate to EdgarTools, gated on preserving four invariants (below). Second, the structural debt: `cli.py` is 4094 lines and contains a ~400-line inline `translate-sse` orchestrator (`cli.py:1888-2290`) with real business logic that is unreachable from the service/API path and untested at unit level. Extracting that, deleting the orphaned `insights/` package and the inert HKEX LLM path, and replacing the positional formula evaluator with a precedence-correct one are all low-risk wins. Confidence: high.

**What should not be rebuilt (preserve behavior, refactor structure only).** `query/periods.py` period math and the LTM contract; the parse-pipeline malformed-HTML guards (font-size:0 pairing rule, colspan clamp, S-1 heading injection, TOC-disarm state machine); the China extraction (HKEX regex grid + SSE Chinese-numeral sectionizer + translation number-safety); the diff noise-suppression taxonomy; and the deterministic SHA256 cache. None of these have an off-the-shelf equivalent that preserves the citation contract. Confidence: high.

**What requires Samay judgment (the four that gate architecture).** (a) edgartools delegation: acceptable given the deliberate pydantic+tiktoken-only dependency constraint, or not? (b) Known-bad disposition: for each provenance-touching bug, pin the current wrong output for parity then fix, or fix during the rewrite? (c) Is the FastAPI/`web` Evidence Explorer definitively retired, or revived? (d) Is exact pack-artifact and CLI compatibility required for existing consumers, or may outputs change? Everything downstream forks on these. Full list in section 11.

---

## 2. Capability contract

All ~24 surfaces, verified against `cli.py` dispatch and the owning modules. "Status" is active / parked / experimental-inert. Network "yes*" means only when the input is a ticker/name that must be resolved or a pack must be built; the core operation is offline.

### SEC build / corpus

| Surface | Entry | Inputs | Outputs / files | Side effects | Cache | Net | Determinism | Citation | Tests | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `build` | `cli.py:1426` | company/CIK, `--accession`, `--form`, `--out`, `--with-chunks`, `--with-xbrl`, `--force`, `--last/--after/--before` | pack dir: `filing.full.md`, `sections/*.md`, `manifest.json`, `llms.txt`, opt `chunks.ndjson`/`xbrl.json`; registry row | writes pack+registry; `--force` rmtree; removes empty dir on fetch fail | `--force` bypasses | yes | byte-identical except `manifest.built_at` | manifest hashes/offsets | `test_cli_build_range.py`, `test_build_pack_registration.py`, `test_pack_build.py` | active |
| `list` | `cli.py:2313` | company, `--form`, `--limit` | form/date/accession rows | none | reads | yes | newest-first | shows accession/form/date | none direct | active |
| `company-llms` | `cli.py:2293` | company, `--out` | company-level `llms.txt` | scans cik dir | reads | yes | sorted | links per-filing llms.txt | none | active |
| `site` | `cli.py:2373` | `--packs`, `--out`, `--base-url`(unused) | static HTML tree + copied artifacts | rmtree targets before copytree | none | no | intended (no det test) | renders manifest provenance | `test_site_build.py` | active |
| `cache` | `cli.py:2339` | `--clear` | dir/file/size or "Cleared" | `--clear` rmtree CACHE_DIR (refetchable) | reads | no | n/a | n/a | none | active |
| `doctor` | `cli.py:1283` | pack dir OR ticker, `--format` | manifest state, inventory, coverage, KPI count | none | reads registry | yes* | deterministic given pack | validates schema_version | `test_cli_doctor.py`, `test_pack_doctor.py` | active |

### SEC query

| Surface | Entry | Inputs | Outputs | Side effects | Net | Citation | Tests | Status |
|---|---|---|---|---|---|---|---|---|
| `query` | `cli.py:2407` | company, metrics CSV, `--period` (lfy/lfy-N/mrq/mrq-N/mrp/ltm/ltm-N/annual:N/quarterly:N/grid), `--preset perf`, `--format table\|json\|json-full`, `--audit`, `--citations`, `--strict`, `--currency native\|usd\|both`, `--force` | table / lean JSON (`to_lean_dict`) / full JSON (`to_cited_dict`) | self-heal writes learned registry unless `--strict` | yes (S-1 reads pack; pro-forma needs ANTHROPIC_API_KEY) | full `CitedValue`/`DerivedValue`; missing => None | `test_cli_json_contract.py`, `test_periods.py`, `test_financials.py`, `test_cli_query_currency.py`, `test_cli_self_heal.py` | active |
| `comps` | `cli.py:2659` | companies, `--metrics` REQUIRED, `--period`, fmt, `--strict` | single/multi-period comps; per-company `strict_rejected` | self-heal write unless strict | yes (parallel) | per-cell citations | `test_cli_json_contract.py`, `test_comps.py` | active |
| `compare` | `cli.py:1041`/`compare.py:441` | companies (2+), `--metrics` optional, `--period`, `--currency`, `--format table\|json\|markdown`, `--strict` | side-by-side + sources; FY-mismatch flags; **one bad ticker sinks the command** | self-heal write unless strict | yes | citation markers + sources | `test_compare.py`, `test_cli_json_contract.py` | active |
| `which` | `cli.py:3809` (+`_cmd_which_china:3719`) | company, fmt, `--only`, `--max-periods`, `--currency` | KPI table (discovered + catalog); S-1 profile; China branch deterministic | KPI cache write; LLM shell-out for SEC discovery | yes* | metric names + values | `test_cli_which_ux.py`, `test_kpi_*` | active |
| `f1`/`s1` | `_add_registration_shortcut cli.py:672`, dispatch `1598` | company, metrics, `--accession`, query flags | builds latest F-1/S-1 pack if needed, delegates to query | writes pack+registry | yes | `s1_snapshot`/`s1_pro_forma` | `test_cli_registration_shortcut.py` | active (only `f1`/`s1` wired; other forms hard-rejected `cli.py:1601-1603`) |
| `learned` | `cli.py:3359` | list/show/verify/clear, `--cik`/`--metric`/`--source`/`--all` | tabular list; promote; removed count | verify/clear MUTATE registry | no | inspects self-heal registry | `test_cli_self_heal.py` | active |

### Observatory

| Surface | Entry | Inputs | Outputs | Net | Status |
|---|---|---|---|---|---|
| `diff` | `cli.py:2912` | `--ticker`(+form) OR `--before/--after` (accession or pack dir), `--format summary\|full\|json\|html`, `--out` | stats / paragraph deltas / `DiffResult.model_dump` / cited HTML | `--ticker` may fetch; diff offline | active |
| `timeline` | `cli.py:3204` (+`_render_registration_timeline:3038`) | `--ticker`+`--section` OR `--cik`, `--series annual\|registration`, `--format text\|html`, `--out` | annual section evolution / registration redline | `--ticker` may fetch | active (annual html is a hard error `cli.py:3210-3215`) |
| `harvest` | `cli.py:2832` | `--universe`, `--out`, `--plan`, `--refresh`, `--with-chunks`, `--concurrency`, `--describe-images` | plan/progress; exit 1 if any failed | heavy SEC; VLM if `--describe-images` | active |
| `index` | `cli.py:3306` | `--packs`, `--incremental` | per-pack chunk counts | none | writes FTS5 index | active |
| `search` | `cli.py:3269` | query, `--topic`, `--ticker`, `--form`, `--limit` | hits + snippets | `--ticker` may fetch; FTS5 offline | active |
| `identify` | `cli.py:1657` | company/name/stock-code/alias | display name + routed status + next step | may fetch; A-share tries CNINFO | active |

### China Lens

| Surface | Entry | Inputs | Outputs | Net / Env | Status |
|---|---|---|---|---|---|
| `build-sse` | `cli.py:1748` | target/stock-code, `--latest-annual`, `--url`, `--pdf`, `--translate`, `--form-type`, `--force` | selected-annual block + pack | CNINFO download unless `--pdf`; DeepInfra if `--translate` (`EDGARPACK_DEEPINFRA_KEY`) | active |
| `translate-sse` | `cli.py:1888` (~400-line inline orchestrator) | `--pack` REQUIRED, `--model`, `--concurrency`, `--batch-size`, `--force` | per-section progress; exit 1 if any section failed | DeepInfra (`EDGARPACK_DEEPINFRA_KEY`) | active |
| `api` | `cli.py:2386` | `--host`, `--port` | uvicorn (blocking); 8 routers under `/api/v1` | binds socket; needs china extra | parked |

### Distill

| Surface | Entry | Inputs | Outputs | Net | Status |
|---|---|---|---|---|---|
| `distill run` | `cli.py:1375`, `distill/builder.py:64` | slug, `--pack` OR `--accession`, `--out` | 8-file bundle (`index.md`, `findings.csv`, `metrics.csv`, `evidence.jsonl`, `gaps.csv`, `filing-map.md`, `run-log.md`, `bundle.json`) | reads local pack only | active |
| `distill check` | `distill/checks.py:24` | bundle dir | ok / exit 1 + errors | none | active |

### Python / HTTP / web surfaces

- Python API: `query.financials.financials()`, `pack.build.build_pack()`, `diff.section_diff`, `distill.builder`, and the `__init__` re-exports are importable but informally contracted; tested via the CLI and module tests. Status: active-internal.
- China FastAPI routes (`api/routes/*` over `china/service.py`): in-memory SQLite seeded with Tencent fixtures; `/ask` is evidence-only-or-not_found; `/packs/{id}/status` is a GET that mutates state one tick per call (`api/routes/packs.py:45-47`). Status: parked. `test_china_api.py` smoke-covers it.
- Observatory HTTP routes (`api/observatory/routes.py`, mounted `api/main.py:67`): read the real on-disk registry/index, but have no route test. Status: parked, untested.
- Next.js `web/` (`rogo-china-lens-web`): Evidence Explorer + Observatory UI; china client swallows errors to a fixture fallback, observatory client throws. Last feature-touched Apr 30. Status: parked; built only behind `SYMPHONY_WEB=1`.

AGREE with Phase 0 section 2 on all surface statuses. EXTEND: `compare` is the only comparison surface that fails the whole command on a single bad ticker (`compare.py`), a real UX divergence from `comps` (parallel `asyncio.gather`); and `which` SEC-discovery shells out to an LLM CLI, which is a hidden network/non-determinism boundary inside an otherwise-offline-looking command.

---

## 3. Product truth versus implementation accident

**User jobs (what people actually come for).**
1. "Give me this filer's number, with a citation I can audit." (`query`, `comps`, `compare`)
2. "Turn this filing into something an agent/LLM can read and cite." (`build`, `llms.txt`, `chunks.ndjson`, `site`)
3. "What changed between these two filings, and is it real?" (`diff`, `timeline`)
4. "Do the same for HK and China A-share filers that have no XBRL." (China Lens)
5. "Compress one filing into a small, fully-cited evidence surface." (`distill`)

**Product promises (verified, not aspirational).** Provenance on every value; `None`-not-guess on every miss; deterministic packs; offline-by-default for the query/diff core. These are enforced in the data model and the test harness, not just documented.

**Implementation mechanisms that are product, not accident.** The `CitedValue`/`DerivedValue` split; the LTM three-component contract; the 404-vs-error distinction; the diff mechanical-suppression taxonomy; the China column-count guard; translation number tag/restore. These are the moat.

**Historical accidents (easy-to-add, do-not-belong-as-is).** Production query code reading `tests/fixtures/china_packs/` with a hardcoded `fy=2024` and CWD-relative paths (`query/financials.py:1977-1987`); the in-place mutation of the cached companyfacts dict to inject a synthetic headcount fact under `us-gaap` (`financials.py:1036-1054`); the `~400-line translate-sse` orchestrator living in `cli.py`; the two divergent universe.toml load paths with inconsistent failure handling (`cli.py:107-113` silent-None vs `cli.py:2417-2424` exit-2). Each had a plausible reason (offline HK demo, derived `revenue_per_employee`, expediency), but none belongs in the steady-state architecture.

**Abandoned / parked experiments still in the repo.** The HKEX LLM extraction fallback (`hk/llm_extract.py`, always invoked with `client=None`, so inert); the `insights/` package (zero callers outside `__init__` and tests; `emerging.py` has no test at all); the FastAPI Evidence Explorer + `web/` (declared parked, beads-closed wontfix 2026-04-20); the `--describe-images` VLM `.desc.txt` output (written, never read by query/search/citation).

**Investor-critical workflows.** `query`/`comps`/`compare` with citations, and `diff`/`timeline` for tracking disclosure change. These are where a wrong-but-confident number is most damaging.

**Agent/LLM-handoff-critical workflows.** `build` -> `llms.txt`/`sections/*.md`/`chunks.ndjson`, and `distill`. The determinism guarantee matters most here, because agents cache and cross-reference by hash and offset.

**Parked but still shipped.** FastAPI/`web`, `insights/`, HKEX LLM path. Section 6.4 isolates these.

AGREE with Phase 0's active/parked split. EXTEND with the "implementation accident" framing: the four accidents above are the ones that most distort the architecture and are the cleanest to correct without touching the contract.

---

## 4. Architecture map

```
                          identity.py (universe.toml)               errors.py
                          resolve ticker/CIK/name -> SEC|HKEX|SSE + private flag
                                       |
        +------------------------------+-------------------------------+
        |                              |                               |
   BUILD pipeline                 QUERY pipeline                  OBSERVATORY
   (pack on disk)                 (cited values)                  (diff/index/search)
        |                              |                               |
  sec/ (client,cache,xbrl,        query/ (financials,            diff/ (section_diff,
   tickers,submissions,            periods,formula,models,        text_diff,timeline,
   archives)                       render,layer_zero,             html_report)
        |                          concepts,metric_map,           index/ (FTS5)
  parse/ (ixbrl_strip ->           self_heal,learned_registry,    insights/ (orphaned)
   html_clean -> semantic_html     strict,s1_financials,comps)    harvest/ (registry,
   -> md_render -> md_polish            |                          planner,runner)
   -> sectionize, s1_headings)     reads companyfacts directly
        |                          (SEC) OR facts.json (HK/SSE)   distill/ (builder,
  pack/ (build,manifest,                                          checks,writers)
   chunks,assets)                  CHINA LENS adapters:
        |                          hk/ (extract,adapter,          site/ (static HTML)
   writes filing.full.md,           sections,llm_extract[inert])  api/ (FastAPI,parked)
   sections/, manifest.json,       sse/ (annual_facts,            web/ (Next.js,parked)
   llms.txt, chunks.ndjson         sectionize_cn)
                                   china/ (service,translate/*)
                                   fx/ (convert,loader)
```

Source acquisition boundary: `sec/`, `hk/acquire`, CNINFO download in the SSE path. Parsing/extraction boundary: `parse/` (SEC HTML), `hk/extract` (HK PDF tables), `sse/` (Chinese PDF). Pack writer/reader boundary: `pack/` writes, `query/` and `diff/` read. Query engine boundary: `query/`. Citation/audit boundary: `query/models.py` + `periods.py` invariant + `conftest.py` harness. Diff/timeline boundary: `diff/`. China boundary: `hk/` + `sse/` + `china/` + `fx/`, joined to query via `facts.json`. Web/API boundary: `api/` + `web/` (parked). Cache/state/config boundary: `sec/cache.py`, `harvest/registry.py` (SQLite), `learned_registry.py` (SQLite), `config.py`, root tomls.

Per major module:

| Module | Responsibility | Upstream | Downstream | Role | Overburdened? |
|---|---|---|---|---|---|
| `cli.py` | argparse dispatch for all subcommands | everything | user | CLI | **Yes** (4094 lines; inline translate orchestrator; two universe-load paths) |
| `query/periods.py` | period vocabulary, LTM/MRQ math, anchor selection, staleness, the LTM invariant | `financials.py` | render, comps | core | Yes (the subtlest module; the disarm of complexity into helpers is partial) |
| `query/financials.py` | orchestrate fetch -> resolve -> compute -> cite; China routing | sec/xbrl, concepts, periods | CLI, comps, which, distill | core | **Yes** (mutates input facts; reads tests/fixtures; China + SEC + S-1 paths in one module) |
| `query/self_heal.py` | fuzzy/LLM concept resolution + learned registry persistence | concepts, LLM CLI | financials | adapter | Yes (read-path DB write; import-time PATH scan) |
| `sec/client.py`,`cache.py` | rate-limited fetch + deterministic disk cache | config | all sec/ | core | No |
| `sec/tickers.py` | ticker/CIK/name resolution incl pre-IPO | client, cache | identity, cli | adapter | Yes (pre-IPO efts path uncached; stale-map silent fallback) |
| `parse/sectionize.py` | section/Item detection, TOC handling | md_polish | pack | core | Yes (TOC-disarm state machine is the highest-churn weirdness) |
| `pack/build.py` | 13-step orchestrator | parse, sec | query, diff | core | Yes (SSE form-type guess; latin-1 fallback; translate manifest mutation) |
| `hk/extract.py` | HK PDF table -> facts.json | hk/acquire | financials (China) | core | Yes (Jan-Dec synthesis; column guard; inert LLM seam) |
| `diff/text_diff.py` | paragraph alignment + noise suppression | packs | section_diff, timeline | core | No |
| `insights/*` | disclosure/topic/language-shift detection | index | nothing | experimental/orphaned | n/a (dead-weight) |
| `api/*`, `china/service.py` | FastAPI workspace | china storage | web/ | parked | n/a |
| `distill/builder.py` | pack -> cited bundle | pack | user | renderer | No (path leak aside) |

---

## 5. Data and artifact contracts

| Artifact | Producer | Documented | Tested | Consumed by | User-visible | vNext treatment |
|---|---|---|---|---|---|---|
| pack dir layout | `pack/build.py` | yes (CLAUDE/ARCH) | yes | query, diff, distill, site | yes | preserve exactly (cache + diff key off it) |
| `filing.full.md` | `pack/build` + parse | yes | yes (offline det test, narrow) | diff, S-1 query | yes | preserve semantically; determinism must hold |
| `sections/*.md` | `sectionize` | yes | yes | diff, site | yes | preserve exactly (section ids are cache/diff keys) |
| `manifest.json` (hashes, offsets, versions, `source.fetched_at`=filing date) | `pack/manifest.py:151-177` | yes | yes (`test_pack_build.py:31`) | doctor, query, diff | yes | preserve exactly; normalize `built_at` only |
| `llms.txt` | `pack/build` | yes | yes (byte-equality offline) | agents | yes | preserve semantically |
| `chunks.ndjson` | `pack/chunks.py` | yes | partial (not in offline det test) | search/index, agents | yes | preserve semantically; **fix the tiktoken-fallback nondeterminism first** |
| `xbrl.json` | `pack` (opt) | partial | partial | external | yes | preserve semantically |
| `facts.json` (HK/SSE) | `hk/extract`, `sse/annual_facts` | partial | yes (golden) | query (China) | indirectly | preserve semantically; fix Jan-Dec dates + matched_label drop |
| query lean JSON (`to_lean_dict`) | `query/models.py` | yes (QUERY.md) | yes (`test_cli_json_contract`) | external/agents | yes | preserve semantically (it is a public contract) |
| query full JSON (`to_cited_dict`, `C#/D#/L#/G#` ids) | `query/models.py` | yes | yes | external/agents | yes | preserve semantically |
| citation/calculation registry | `query/models.py` | yes | yes | audit | yes | preserve semantically |
| `CitedValue`/`DerivedValue` shapes | `query/models.py` | yes | yes | everything cited | yes | **preserve exactly (the core contract)** |
| diff JSON/HTML/markdown | `diff/*` | yes (OBSERVATORY) | yes | external | yes | preserve semantically; `_DIFF_CACHE_VERSION` gates changes |
| timeline outputs | `diff/timeline` | yes | yes | external | yes | preserve semantically |
| site output | `site/build` | partial | yes | browser | yes | migrate (least contract-bound) |
| translation artifacts (`.en.md`, manifest block) | SSE path | partial | yes (validators) | external | yes | migrate to a hashed `translation.json`; current manifest mutation breaks determinism |
| failure artifacts (diagnostics, `gaps.csv`) | query, distill | yes | yes | audit | yes | preserve semantically |
| cache files (SHA256 sharded) | `sec/cache.py` | yes | partial (TTL tests misplaced) | all fetch | no | preserve exactly (determinism device) |
| learned/self-heal registry (`~/.edgarpack/registry.db`) | `learned_registry.py` | yes | yes | query, learned cmd | no | preserve semantically; reconsider read-path write |
| metric directory (`METRIC_DIRECTORY.md/json`) | `scripts/generate_metric_directory.py` | yes | yes (byte-equality drift guard) | docs | yes | preserve exactly (drift-guarded) |
| distill bundle (8 files) | `distill/builder` | yes (DISTILL.md) | yes | external | yes | preserve semantically; **normalize `pack_dir`/`total_bytes` (path leak)** |

AGREE with Phase 0 section 4. EXTEND: the lean/full query JSON is a genuine external contract (documented field-by-field in `docs/QUERY.md` with stable `C#/D#/L#/G#` ids), so it should be treated as "preserve semantically" with a schema test, not casually migrated. The single artifact most in tension with the determinism guarantee is `chunks.ndjson`, because its producer branches on `has_tiktoken()`.

---

## 6. Complexity audit

### 6.1 Essential complexity (required by filing reality; preserve behavior)

| Item | Files | Real-world condition | Breaks if removed | Cleaner vNext preservation |
|---|---|---|---|---|
| LTM three-component math + invariant | `periods.py:483,541-817` | SEC files cumulative YTD + standalone quarters under the same context | Silent wrong LTM; the citation contract collapses | Keep the math; lift the invariant from a runtime assert into a typed constructor that cannot build an invalid LTM |
| Cumulative-vs-standalone quarter detection (<=100 day) | `periods.py:379-406` | 4-4-5 and 52/53-week fiscal calendars; dual-tagged YTD/standalone | MRQ returns 9-month YTD; LTM subtracts wrong spans | Keep; document the day windows as named domain constants |
| Segment/dimensional fact filtering | `financials.py:138-173` | companyfacts mixes consolidated + segment values at one context | Segment breakouts leak in as totals | Keep |
| font-size:0 pairing rule | `html_clean.py:95-99` | Cerebras/print-layout S-1 wrappers use `font-size:0` on the page container | Multi-MB S-1 collapses to ~200 chars | Keep; it is the single highest-value 5-line guard in parse |
| colspan/rowspan grid + lower-clamp | `md_render.py:313-376` | merged multi-period table headers; TSM-2006 `colspan="0"` | Financial table columns misalign, breaking citations | Keep; **add an upper clamp** (currently unbounded allocation on adversarial colspan) |
| S-1 synthetic heading injection | `s1_headings.py` | absolute-positioned-div renderers with no `<h>` tags | S-1 becomes one unsectioned blob | Keep; it is genuinely novel IP |
| HK column-count silence guard | `hk/extract.py:278-279` | misaligned PDF grids would misattribute a value to the wrong year | Silent wrong-year citation (worst-case provenance failure) | Keep |
| Translation number tag/restore | `china/translate/numbers.py:109-154` | wan/yi 10,000x magnitude units; an MT error is a 10,000x mistake | Catastrophic magnitude errors in translated financials | Keep exactly; never delegate numbers to the LLM |
| Diff mechanical-suppression taxonomy | `diff/text_diff.py` | TOC, date rollovers, cross-refs, re-split paragraphs inflate naive diff | Diff drowns in noise; the OBSERVATORY promise fails | Keep; see 9 for the over-suppression edge |
| Deterministic SHA256 atomic cache, no eviction | `sec/cache.py` | byte-identical rebuilds; refetchable-by-design | Determinism + cache contract break | Keep |

### 6.2 Accidental complexity (appears removable; pin before removing)

| Item | Files | Why it might have existed | Evidence now unnecessary | Pin before removal | Path |
|---|---|---|---|---|---|
| `insights/` package | `insights/*` | built for the parked observatory web surface | zero callers outside `__init__`/tests; `emerging.py` has no test | the accession-level emerging-topic counting invariant | delete or move behind the (parked) web surface |
| HKEX LLM extraction path | `hk/llm_extract.py`, `extract.py:606-609` | planned self-heal seam mirroring SEC | always `client=None`; fixtures show only `extraction_method='regex'` | the `learned:llm` tag, cache-key format, and the latent USD/1000x bug | delete, or wire a client and port the regex multiplier |
| `~400-line translate-sse` in `cli.py` | `cli.py:1888-2290` | expedient placement during China Lens build-out | unreachable from service/API; untested at unit level | the fail-closed + manifest-write logic | extract to `china/translate/pipeline.py` |
| Production read of `tests/fixtures/china_packs/` | `financials.py:1977-1987` | offline HK demo needed a committed corpus | a config-driven pack root would replace it | the offline HK query that `test_cli_json_contract` depends on, plus the CWD==repo-root assumption | introduce a pack-root config |
| In-place facts dict mutation (synthetic headcount under us-gaap) | `financials.py:1036-1054` | lets `revenue_per_employee` resolve via the normal path | a side channel avoids mutating cached SEC data | the placement decision (us-gaap not dei) | thread the value rather than mutate |
| Two divergent universe-load paths | `cli.py:107-113` vs `2417-2424` | `query` re-loads the universe for a private-company pre-pass | one loader can serve both | both behaviors (silent-None vs exit-2); decide canonical | unify the loader |
| `warnings.warn` for dropped archive files | `archives.py:188-192` | likely copy from older code | `logger.warning` everywhere else | the partial-doc-set behavior | switch to logger; thread into manifest warnings |
| positional 5-token formula evaluator (no precedence) | `formula.py` | dependency-free, avoids `eval` | a tiny AST-restricted evaluator is safer | existing formula shapes (they coincide with left-assoc) | replace with a precedence-correct evaluator; the `formula.py:58` "respect precedence" comment is already wrong |
| `_STALENESS_YEARS` empty dict | `financials.py:64` | unfinished per-metric override hook | never populated | any test patching it | delete |
| `site --base-url` (accepted, unused) | `cli.py:569`, `site/build.py:45` | anticipated deploy base URL | param never read in body | confirm `build_site` does not branch on it | remove flag |

### 6.3 Uncertain complexity (might be load-bearing; needs a corpus case to adjudicate)

| Item | Files | Possible reason | Missing evidence | Case needed |
|---|---|---|---|---|
| `_simplify_complex_tables` dot-leader reshape of wide financial tables | `md_polish.py:293-371` | human/LLM readability + token budget | whether the S-1 extractor or diff ever needs the original grid | feed a wide financial table through pack -> S-1 query and check value fidelity |
| self-heal on the read path (fuzzy + LLM + DB write before verified gate) | `self_heal.py:351-355,662` | coverage for non-canonical XBRL tags | value of the marginal coverage vs the non-determinism + global write | a corpus of filers that only resolve via self-heal, with and without `--strict` |
| `verify_order_of_magnitude` sign tolerance ([0.25,4.0], accepts sign flips) | `self_heal.py:321-344` | restatement sign flips are common | whether a sign-aware check loses real matches | a sign-flip restatement fixture |
| latin-1 whole-blob decode fallback | `pack/build.py:83-88` | legacy windows-1252 filings (pre-2001) | whether `errors="replace"` would suffice | a mixed-encoding filing fixture |
| derived provenance from first component | `financials.py:1831-1862` | components are window-aligned first (`:1581-1587`) | whether any offset formula reaches this without alignment | a YoY/trend derived metric with misaligned components |
| `_detect_sse_form_type` default-to-prospectus | `pack/build.py:59-80,464` | prospectus-first was the original pipeline | how often a real annual report misses markers in the first 20k chars | an annual report with late markers |

### 6.4 Parked complexity (do not let it shape vNext unless revived)

| Item | Files | Status | Reviving condition | Isolation |
|---|---|---|---|---|
| FastAPI Evidence Explorer | `api/*`, `china/service.py`, `china/storage.py` | parked (tracker `:5-7`, beads wontfix) | China Lens becomes a web product | keep behind the china extra; pin the seed corpus + pack-status tick + citation-resolve contract |
| Observatory HTTP routes | `api/observatory/*` | parked, untested | the above | seed a fixture + add a route test before any reliance |
| Next.js `web/` | `web/*` | parked (Apr 30) | the above | keep behind `SYMPHONY_WEB=1`; it is git-tracked and allowlisted in `test_repo_layout.py` |
| `--describe-images` VLM output | `pack/assets.py:132` | inert (nothing reads `.desc.txt`) | a figure-query roadmap | keep the image-fetch+src-rewrite half (load-bearing for registration markdown); park the descriptions |

---

## 7. Test and behavior-pinning reality

**Covered by tests (offline, value-level):** LTM/LTM-1 math, per-share degrade, Q4 short-circuit, annual-only fallbacks, segment filtering, mrq standalone-vs-cumulative, self-heal fuzzy + shape guards + verify boundaries, strict recursion (indirect), the China golden harness (two HK filers, native + USD), lean/full JSON contract, metric-directory byte-equality, the parse fixtures (font-size:0 wrapper, malformed spans), HK column-shift (9 regressions), diff suppression.

**Only covered by fixtures (not asserted as behavior):** the cerebras S-1 sample and selected-financial-data fixtures exercise the S-1 extractor path but pin extraction shape more than exact values.

**Only encoded in implementation (no test):** the in-place facts mutation (`financials.py:1036-1054`); the production `tests/fixtures/` read + CWD assumption; the AXP/issuer revenue gotcha; the `no_api_key`-conflates-all-exceptions behavior in S-1 extraction; the formula evaluator mis-precedence case; the universe-load divergence.

**Documented but untested:** byte-determinism for the surfaces that actually break it (chunks tiktoken-state, SSE+translate manifest mutation); the 404-vs-XBRLFetchError split has no dedicated offline test (only gated live integration).

**Tested but undocumented:** the autouse LTM harness in `conftest.py:55-98` is a silent global guard most contributors will not know exists; the strict-xfail discipline in `test_china_query_eval.py:130-131` (a good guard that fails if a golden goes null without a tagged bug id).

**Neither documented nor tested but important:** the determinism preconditions (tiktoken present, asset fetch successful, no translation); the China FX fiscal-year-average correctness.

**Edge cases a naive rewrite would lose:** every item in section 9, plus the font-size:0 rule and the colspan clamp.

**Tests too coupled to implementation:** the China golden harness pins USD values derived from the same single-month FX rate the code uses, so it pins behavior, not correctness, and cannot catch the FX averaging bug. The metric-directory byte-equality test couples docs to a generator. Both are fine as parity pins but must not be mistaken for correctness oracles.

**Tests that should become parity tests:** `test_pack_build` determinism (broaden to `with_chunks=True`, cross-process), the lean/full JSON contract, the diff suppression cases, the China golden.

**Tests that should become semantic invariants:** the LTM contract (already an invariant via the harness; make it a constructor invariant), the 404-vs-error split, the no-imputation pagination, the translation magnitude round-trip.

### Coverage table

| Behavior | Current coverage | Risk | Suggested parity case | Priority |
|---|---|---|---|---|
| Pack byte determinism (chunks + cross-machine tiktoken) | offline test exists but `with_chunks=False`, same-process; full test gated live+slow, NVDA only | HIGH | offline fixture-fed determinism with chunks, simulate tiktoken-absent | P0 |
| LTM component-citation contract | exact, offline (`test_periods` + autouse harness) | HIGH | required-for-parity | P0 |
| Period vocabulary (lfy/mrq/ltm/annual:N) | exact, offline | HIGH | required-for-parity | P0 |
| 404-vs-XBRLFetchError split | none offline (live only) | HIGH | mocked 404 vs network-error | P0 |
| Tokenizer-fallback determinism | `test_tokenize` (not cross-env) | HIGH | cold-tiktoken chunk-equality | P0 |
| HK column-shift guard | exact, offline (9 regressions) | HIGH | high-risk edge | P0 |
| China FX fiscal-year average | golden pins the buggy value | MEDIUM | independent FY-average oracle (not code-derived) | P1 |
| SSE+translate manifest determinism | none | HIGH | translate-block normalization parity | P1 |
| Lean/full JSON shape | semantic, offline | MEDIUM | required-for-parity | P1 |
| Diff suppression + intensity | semantic, offline | HIGH | high-risk edge; include numeric-only-change case | P1 |
| Sectionizer TOC/INDEX disarm | semantic, partial | HIGH | high-risk edge | P1 |
| S-1 snapshot extraction (USD/is_audited hardcode) | semantic, offline (mock LLM) | MEDIUM | non-USD F-1 fixture | P1 |
| Self-heal read-path write + verify | exact, offline (mock LLM) | MEDIUM | strict vs non-strict parity | P1 |
| HKEX LLM 1000x (inert) | none (path inert) | HIGH (if activated) | known-bad pin | P1 |
| China fabricated `filed=Dec-31` | test enshrines it | MEDIUM | known-bad pin | P1 |
| AXP/issuer revenue resolution | none | MEDIUM | known-bad/uncertain pin | P1 |
| Cache TTL "missing meta = expired" | tests misplaced below `unittest.main()` | MEDIUM | re-home the TTL tests | P1 |
| Universe-load divergence | none | MEDIUM | both-paths parity | P2 |

---

## 8. Reinvention check (and: should EdgarPack exist at all?)

EdgarTools (`edgartools`/`edgar` on PyPI) provides company resolution, `get_filings()`, filing download, `get_facts()`/`Financials`, and its own throttle + cache. EdgarPack deliberately caps core deps at pydantic+tiktoken and explicitly rejects cache eviction (`config.py`, CLAUDE.md).

| Area | Verdict | Reasoning (confidence) |
|---|---|---|
| Company resolution (ticker/CIK/name map) | **DELEGATE the map; KEEP the pre-IPO + universe glue** | The `company_tickers.json` fetch/build in `sec/tickers.py` is pure commodity. But the pre-IPO `efts.sec.gov/LATEST/search-index` resolution with the content-only-match substring guard (`tickers.py:282-300`, the WhiteFiber-not-Cerebras fix) and the universe.toml HKEX/SSE routing are not in EdgarTools and must stay owned. high |
| Filing listing / submissions pagination | **INVESTIGATE -> likely WRAP** | The no-imputation contract (exhausted-iterator = not-found, warn-and-continue, 30-day-immutable TTL) is the value. Delegatable only if EdgarTools surfaces per-page fetch failures rather than silently returning short lists. high |
| Filing download / archives | **DELEGATE (mostly)** | `fetch_filing_index` + `fetch_file` + R*.htm/exhibit skip is exactly EdgarTools' attachment handling. Keep only a thin primary-only selector. high |
| SEC cache + rate limit | **KEEP OWNED** | EdgarTools brings its own cache lifecycle and dependency tree, both of which violate EdgarPack's determinism guarantee and the pydantic+tiktoken-only constraint. high |
| XBRL facts | **INVESTIGATE (high stakes)** | The 404-vs-`XBRLFetchError` split is the single most load-bearing invariant; delegation is possible only if EdgarTools exposes the raw HTTP status rather than a pre-digested empty result. Verify first. high |
| Concept normalization | **INVESTIGATE / partial DELEGATE** | The hand-maintained 60-metric `METRIC_MAP` with priority-ordered tag lists rots; EdgarTools' standardized concepts could back it. Keep EdgarPack's metric names and `CONCEPT_SCOPE_WARNINGS` (domain knowledge a library will not carry). medium |
| Financial statements / period logic | **KEEP OWNED** | The cited-LTM model with component citations and `None`+typed-diagnostic is the product IP; no library enforces it. high |
| Form-specific parsing (S-1 heading injection) | **KEEP OWNED** | Genuinely novel; reconstructs headings from TOC anchors for absolute-div renderers. high |
| Filing text / markdown conversion | **WRAP for inline only; KEEP the table grid** | A wholesale swap to markdownify/html2text simultaneously breaks the colspan/rowspan grid, the table-polish stack, and byte-determinism (and therefore the PARSER_VERSION cache and the diff engine). Treat those three as one coupled swap, which is why a wholesale swap is not worth it. high |
| iXBRL stripping | **INVESTIGATE (lean KEEP)** | The regex approach is deterministic and fast; a prior DOM (selectolax) impl was already removed (`ixbrl_strip.py:70` alias is the residue). Low priority. medium |
| Search / index | **KEEP OWNED** | FTS5 + pattern topic extraction is light and offline; no reason to delegate. high |
| China (HKEX/SSE) extraction, translation, diff suppression | **KEEP OWNED** | No off-the-shelf library does HK-prospectus PDF table extraction, CSRC section detection, wan/yi-safe translation, or SEC-noise diff suppression. This is the moat. high |
| Insider/fund/proxy parsing | **n/a / DELETE if added** | Not in scope today; do not build it, delegate to EdgarTools if ever needed. high |

**Should EdgarPack exist at all? My honest answer: yes, but narrower, as a citation/evidence layer that wraps EdgarTools for commodity SEC acquisition while keeping the differentiated IP owned.** Confidence: medium-high. The differentiated value is the provenance data model, the period engine, the China Lens, the diff/timeline noise suppression, and distill. The commodity is the ticker map and archive download (clean delegations) and possibly submissions/XBRL (gated on whether EdgarTools preserves the no-imputation and 404-vs-error semantics). The cache+client stay owned for determinism and dependency reasons. The thing that makes a "thin wrap over EdgarTools" optimistic is that four invariants (404-vs-error, no-imputation pagination, deterministic cache, pre-IPO content-only-match) each require either keeping owned code or verifying a library behavior, so the wrapper is not thin. The dependency cost alone (EdgarTools pulls pandas/lxml/httpx/rich) likely fails the stated pydantic+tiktoken-only constraint, which is itself a Samay decision. Do not adopt EdgarTools wholesale.

---

## 9. Load-bearing weirdness and risk register

| # | Location | Why it looks wrong | Why it is load-bearing | Real-world edge | Test coverage | Parity case needed | Severity |
|---|---|---|---|---|---|---|---|
| 1 | tiktoken `len//4` fallback (`tokenize.py:48-55`, `chunks.py:167`) | a token counter that silently changes counting mode | determinism of `chunks.ndjson`, `tokens_total`, and artifact hashes | cold/absent tiktoken cache offline | not cross-env tested | cold-tiktoken chunk-equality | HIGH |
| 2 | SSE+translate manifest mutated after hashing (`build.py:564-571`) | manifest content changes after its own hash is computed | that pack class is otherwise non-reproducible | any translate run with cache warmth variance | none | translate-block normalization | HIGH |
| 3 | no negative cache for 404 companyfacts (`xbrl.py:72-75`) | re-hits SEC on every metric query for a no-XBRL filer | preserves the 404-vs-error split (the `{}` is diagnostic-free) | S-1/pre-IPO sessions | live only | mocked-404 negative-cache | HIGH |
| 4 | pre-IPO resolution via undocumented `efts.sec.gov/LATEST/search-index`, uncached, content-only-match guard | internal endpoint + no cache | the only pre-IPO name->CIK path; the guard fixes a real wrong-CIK bug | Cerebras/Klarna-class filers | mocked + live-gated | pre-IPO resolution + content-only-match | HIGH |
| 5 | FX "average" = one FYE-month average, not fiscal-year average (`fx/convert.py:71-73`, `query/currency.py:130-133`) | mislabels income-statement conversion | every cross-market `--currency usd` annual flow | any non-USD annual filer | golden pins the buggy value | independent FY-average oracle | HIGH |
| 6 | HKEX LLM fallback hardcodes `unit="USD"`, raw value, no multiplier (`llm_extract.py:104-114`) | a 1000x-wrong value beside correctly-scaled regex facts | inert today (`client=None`); a trap if activated | CNY filer if the seam is wired | none (inert) | known-bad pin | HIGH (if activated) |
| 7 | font-size:0 only hides when paired (`html_clean.py:95-99`) | refuses the textbook cloaking signal | without it, S-1 wrappers collapse the whole filing | absolute-div S-1 renderers | `test_html_clean_s1_wrapper` | already pinned | HIGH (kept) |
| 8 | HK column-count silence guard (`hk/extract.py:278-279`) | a parsed grid yields nothing | silence over wrong-year misattribution | comma-less/decimal/negative columns | 9 regressions | already pinned | HIGH (kept) |
| 9 | colspan lower-clamp only, no upper clamp (`md_render.py:313-376`) | tolerates `colspan="0"` but also `colspan="99999"` | the low clamp is essential (TSM-2006); the missing high clamp is a robustness gap | adversarial/corrupt span | malformed-span fixture | add an upper-bound case | MEDIUM |
| 10 | sectionize TOC-disarm state machine (`sectionize.py:615-658`) | intricate branching on separator/header/blockquote TOC rows | prevents phantom sections from TOC rows | split TOC tables, INDEX heading, blockquote TOC | `test_sectionize` (gaps) | TOC-disarm regression set | MEDIUM |
| 11 | HKEX synthesizes Jan-Dec for every fact (`extract.py:623-624`) | wrong period dates for non-Dec FYE (Alibaba 09988 is Mar-31) | low blast radius today (active goldens are Dec-FYE) | universe expansion to non-Dec FYE HK filers | none | non-Dec-FYE HK fixture | MEDIUM |
| 12 | diff boilerplate class includes any 1-4 digit number (`text_diff.py:104`) | a `$26.0B -> $35.1B` change can be suppressed | the number class is needed to suppress date/section noise; the `_DISTINCTIVE_FLOOR` (0.2) partly mitigates | a financial sentence whose only change is the figure | `test_diff` | numeric-only-change case | MEDIUM |
| 13 | `financials()` mutates the cached companyfacts dict (`:1036-1054`) | a read op side-effects fetched data | enables `revenue_per_employee` via the normal path | shared/cached facts object reused across calls | none | mutation-isolation case | MEDIUM |
| 14 | self-heal upserts to `registry.db` on the read path before the verified gate (`self_heal.py:662`) | a read query writes a global DB | persistence + later rediscovery fall-through | parallel processes; cross-machine backend differences | persistence pinned | strict vs non-strict parity | MEDIUM |
| 15 | two-clock cooldown: 60s-clamped Retry-After vs 600s default (`client.py:141,151,232`) | user-facing cooldown can be wrong in both directions | the 60s clamp guards against a huge Retry-After; 600 is the fair-access window | a SEC 429 with a real Retry-After: 600 | only the no-header path | cooldown-reporting case | MEDIUM |
| 16 | silent stale ticker-map fallback (`tickers.py:89-92`) | serves an expired map with no diagnostic | offline resolution beats hard failure | a renamed/new ticker (SQ->XYZ) | none | stale-map case | MEDIUM |
| 17 | distill bundle embeds the `--pack` path verbatim (`writers.py:67,150`) | absolute local path in output bytes | intentional provenance ("which pack made this") | same pack distilled from a different cwd | none | normalize `pack_dir` in the harness | LOW-MEDIUM |
| 18 | latin-1 whole-blob decode fallback (`build.py:83-88`) | all-or-nothing reinterpretation | legacy non-UTF-8 filings | a mostly-utf-8 filing with one bad byte | none | mixed-encoding fixture | LOW-MEDIUM |
| 19 | pack-status GET mutates state one tick per request (`api/routes/packs.py:45-47`) | a GET with a side effect | deterministic MVP simulation of an async pipeline | parked surface | `test_china_api.py:46-48` | parked | LOW |

AGREE with Phase 0's weirdness list. DISAGREE / sharpen on three points: Phase 0 said the asset-drop emits "a warning at most"; verification shows there is no warning at all at the asset layer (`assets.py:78-82` just `continue`s), so it is quieter than reported. Phase 0 implied the diff timeline diverges broadly; the divergence is on counts only, the shared intensity still applies boilerplate filtering. Phase 0's "no offline determinism test" is literally false (`test_pack_build.py:217` exists) but spiritually correct, because that test runs `with_chunks=False` same-process and cannot catch any of the HIGH-severity determinism risks.

---

## 10. First-principles vNext implications

Not a vNext design. Constraints any vNext must respect.

**Non-negotiable domain concepts.** Provenance as a data-model property (not formatting); `None`+typed-diagnostic for every miss; the LTM component-citation contract; the 404-vs-fetch-error distinction; byte-determinism of the pack core; translation magnitude safety; the HK column-count guard.

**Boundaries that seem necessary.** Identity routing (SEC | HKEX | SSE + private) as the front door; a source-acquisition boundary per family; a single parse-pipeline contract producing the pack; a query engine that reads either companyfacts or `facts.json` behind one interface; a citation/audit boundary owning `CitedValue`/`DerivedValue`; a diff boundary over local packs only.

**Boundaries that seem accidental.** `cli.py` owning business logic (the translate orchestrator); `financials.py` owning SEC + China + S-1 routing in one module; the two universe-load paths; production code reaching into `tests/fixtures/`.

**Source adapters that seem needed.** SEC (XBRL + HTML), HKEX (PDF tables), SSE/CNINFO (Chinese PDF). Each must map onto the same `facts`/pack contract so the query engine stays source-agnostic.

**External dependencies to consider.** EdgarTools for company resolution map + archive download (gated on the four invariants and the dependency-budget decision); a maintained FX rate source over the bundled `data/fx_rates.csv`; tiktoken as a hard precondition (vendor the `cl100k_base` asset or fail loud) rather than the silent `len//4` fallback.

**Artifact contracts to preserve.** Pack layout, `manifest.json`, `sections/*.md` ids, lean/full query JSON with `C#/D#/L#/G#` ids, `CitedValue`/`DerivedValue`, diff/timeline outputs. Preserve exactly where they are cache/diff keys; preserve semantically where they are external read contracts.

**Compatibility shims likely needed.** The legacy `accession_nodash` pack-directory read path (`pack/build.py:183,201-213`) if existing on-disk packs must remain readable; the `--cik` deprecated flag if scripts still pass it; the lean/full JSON shape for any external consumer.

**Areas to delete or park.** `insights/` (orphaned); the inert HKEX LLM path; `_STALENESS_YEARS`; `site --base-url`; the `--describe-images` descriptions output (keep the image fetch). Park (do not delete, do not let it shape vNext): FastAPI/`web`.

**Open questions for Samay.** Section 11.

---

## 11. Questions for Samay

Only the ones that change the architecture or scope.

1. **edgartools delegation and the dependency budget.** Is delegating company-resolution map + archive download (and possibly submissions/XBRL) to EdgarTools acceptable, given it would breach the deliberate pydantic+tiktoken-only core-dependency constraint? This single answer decides how much of `sec/` is even in scope for a rewrite. Confidence this matters: high.
2. **Known-bad disposition (pin vs fix).** For each provenance-touching bug, pin the current wrong output for parity then fix later, or fix during the rewrite? The pointed ones: HKEX LLM 1000x (`llm_extract.py:104-114`), the test-enshrined China `filed=Dec-31` (`financials.py:2076` fabricates, `:2111-2113` assigns), the FX one-month-average-for-annual-flow (`fx/convert.py:71-73`). The parity corpus cannot be finalized until you rule on these. high.
3. **FastAPI/`web` Evidence Explorer: retired or revived?** This decides whether `site` is the only web surface carried forward, whether the observatory HTTP routes need a seeded fixture, and whether `insights/` is dead or dormant. high.
4. **Pack-artifact and CLI compatibility.** Are existing on-disk packs consumed outside the repo (forcing exact-byte artifact compatibility and the `accession_nodash` read shim), and is exact CLI-flag compatibility required, or may outputs and flags change in vNext? high.
5. **The three comparison surfaces.** Keep `query`/`comps`/`compare` as three, or consolidate? If consolidating, which output is the parity oracle? medium.
6. **Determinism scope across machines.** Must byte-determinism hold where tiktoken's `cl100k_base` asset is present on one run and absent on another? If yes, vNext should make tiktoken a hard precondition and drop the `len//4` fallback, and add an offline determinism test with chunks. high.
7. **HKEX wiring + metadata source.** Should `facts.json` generation be a first-class CLI command (a `build-hk` like `build-sse`), or stay fixture-only? And should HK/SSE currency/accounting-standard (and FYE) come from the filing or `universe.toml` rather than the hardcoded 6-entry `_COMPANY_META`? medium-high.
8. **Which users/workflows matter most.** Investor-facing cited query/diff, or agent/LLM pack handoff? The determinism and JSON-contract investments weight differently depending on the answer. high.

---

## 12. Appendix

**Files inspected (primary).** `edgarpack/cli.py`, `__init__.py`, `errors.py`, `config.py`, `identity.py`; `query/{periods,financials,formula,models,render,layer_zero,concepts,metric_map,self_heal,learned_registry,strict,s1_financials,comps,currency}.py`; `sec/{client,cache,xbrl,tickers,submissions,archives}.py`; `parse/{ixbrl_strip,html_clean,semantic_html,md_render,md_polish,sectionize,s1_headings,tokenize}.py`; `pack/{build,manifest,chunks,assets}.py`; `hk/{extract,adapter,llm_extract}.py`; `sse/{annual_facts,sectionize_cn}.py`; `china/{service,translate/numbers,translate/validators}.py`; `fx/convert.py`; `diff/{text_diff,section_diff,timeline}.py`; `insights/*`; `harvest/{registry,planner,runner}.py`; `distill/{builder,checks,writers}.py`; `site/build.py`; `api/{main,routes/*,observatory/routes}.py`; `web/` (package.json, app, lib).

**Tests inspected.** `conftest.py`, `test_periods.py`, `test_financials.py`, `test_self_heal.py`, `test_query_derivations.py`, `test_query_models_source.py`, `test_sec_client.py`, `test_cache.py`, `test_tickers*.py`, `test_submissions_pagination.py`, `test_archives.py`, `test_html_clean*.py`, `test_md_render*.py`, `test_md_polish.py`, `test_sectionize*.py`, `test_s1_headings.py`, `test_tokenize.py`, `test_chunks.py`, `test_pack_build.py`, `test_determinism.py`, `test_assets_pipeline.py`, `test_diff*.py`, `test_china_query_eval.py`, `test_china_fx.py`, `test_hk_*.py`, `test_translation_validators.py`, `test_distill.py`, `test_insights.py`, `test_china_api.py`, `tests/eval/china_golden.yaml`. Fixtures: `s1_font_size_zero_wrapper.html`, `tsm_2006_malformed_span_table.html`, `cerebras_s1_sample.md`, `china_packs/`.

**Commands discovered.** See Phase 0 section 12 (33 commands with offline-safety). The parity-harness-relevant offline ones: `query` against HK fixtures, `diff --before/--after` on pack dirs, `timeline --series registration`, `distill run/check`, `site`, `index`, `learned`, plus the gated `pytest --run-slow --run-live-sec` as the live determinism oracle.

**Assumptions.** EdgarTools' capabilities are taken from its public API surface (company resolution, get_filings, download, get_facts, Financials, throttle, cache); its missing-data and partial-page semantics are unverified and gate the XBRL/submissions delegation. Behavior was read, not executed (no network, no CLI, no pytest), per the read-only constraint.

**Uncertainties (explicitly held, not averaged away).** Whether the cache TTL tests (`test_cache.py:64-85`) are collected by pytest (likely yes, contra Phase 0; a `pytest --collect-only` settles it). Whether EdgarTools preserves the 404-vs-error split. Whether `_simplify_complex_tables` reshape loses fidelity the S-1 extractor needs. Whether bare 6-digit A-share codes route to SSE or fall through to a SEC 404 (docs disagree; only running code settles it). The exact blast radius of the FX averaging bug beyond the single golden filer.

**Suggested next investigation steps (not implementation).** (1) Run `pytest --collect-only tests/test_cache.py` to settle the TTL-test collection question. (2) Spike EdgarTools against three filers (a clean 10-K, a no-XBRL S-1, a renamed ticker) to test the four invariants before any delegation decision. (3) Build an independent FX fiscal-year-average oracle and check it against the China golden to size the averaging bug. (4) Make the Phase 0 `corpus.yaml` executable as the first harness, starting with the P0 rows in section 7. (5) Run a Codex Phase 1 pass against this same prompt and diff the two assessments; the disagreements are where the highest uncertainty lives.

---

*Confidence summary: high on all verified behavioral claims (each traced to exact file:line by four independent read-only passes). Medium on the EdgarTools delegation verdicts (gated on unverified library semantics) and on the recommendation against a full clean-room rebuild (a judgment call, defended above). The four corrections to the Phase 0 corpus (cache-test collection, offline determinism test exists-but-narrow, asset-drop has no warning, diff timeline diverges on counts only) are folded in above and should be back-ported to the Phase 0 documents.*
