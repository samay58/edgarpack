# Phase 1 Rebuild Assessment: Codex

Date: 2026-06-16  
Repository: `/Users/samaydhawan/Projects/active/edgarpack`  
Scope: written assessment only. No product code was changed.  
Confidence scale: high = verified in current code and tests/docs; medium = current code supports it but coverage or docs are partial; low = inferred from references, history, or parked code.

# 1. Executive summary

EdgarPack turns primary filing sources into compact, deterministic, inspectable research artifacts. Its active center is the CLI. The repo is not just a filing parser: `README.md`, `docs/GETTING_STARTED.md`, `docs/WORKFLOWS.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`, and the current CLI all converge on the same contract: build clean filing packs; answer financial questions with citations; preserve evidence through diffs, timelines, search, distill bundles, and China/HKEX/SSE workflows. Confidence: high.

The highest-level product contract is: given a company or filing, EdgarPack should produce primary-document-backed artifacts where every number, disclosure change, or extracted finding is traceable to a filing, section, chunk, fact, source URL, or citation registry entry. Missing evidence must produce gaps, warnings, or `None`, not a guessed claim. Confidence: high.

A clean-room rebuild should proceed only if it is narrower than the current repo and begins from behavior-pinning. A blank-slate rewrite is too risky. The current code contains a lot of scar tissue around SEC HTML, XBRL periods, S-1/F-1 registration filings, HKEX/SSE annual reports, translation validation, and diff noise filtering. Much of that code is awkward, but history and tests show that awkwardness often came from real filing failures. Confidence: high.

The biggest regression risk is losing edge-case behavior that currently lives in control flow rather than clean contracts: LTM math and citation formulas, section detection around TOCs/cross-references/registration filings, S-1 selected financial table extraction, malformed tables, HKEX table row attribution, SSE translation resume/validation, and diff paragraph matching. Confidence: high.

The biggest simplification opportunity is to split active product contracts from parked surfaces and commodity infrastructure. The FastAPI/Next China Lens workspace, observatory API wrapper, `insights/`, VLM image descriptions, and some learned/self-heal pathways should not shape vNext unless Samay explicitly revives those surfaces. Commodity SEC listing, filing retrieval, company resolution, and XBRL statement extraction should be investigated as wrappers over EdgarTools rather than rewritten again. Confidence: medium.

What should not be rebuilt by default: the parked Evidence Explorer web app, the FastAPI workspace service, demo fixture seeding, generic insight layers, full custom SEC commodity stack if EdgarTools can be wrapped without breaking EdgarPack's provenance contract, and the image-description/VLM asset path unless registration visual analysis becomes active. Confidence: medium.

Samay judgment is required on exact backward compatibility. The architectural answer changes materially depending on whether old pack layouts, CLI flags, JSON shapes, `learned_concepts`, static site output, and China Lens APIs must remain stable or may migrate behind shims. Confidence: high.

# 2. Capability contract

The repo exposes four classes of public entry points:

- CLI: `edgarpack = edgarpack.cli:app` from `pyproject.toml`. This is the active product surface. Confidence: high.
- Python modules: `build_pack`, `financials`, diff builders, `ChinaLensService`, storage adapters, search/index helpers, distill builders. These are used internally by CLI/tests and some API routes. Confidence: high.
- FastAPI routes: `edgarpack/api/main.py` under `/api/v1`. Existing rebuild docs classify this as parked. Current tests cover some service/API behavior, but not the full HTTP surface. Confidence: medium.
- Web workspace: `web/` Next app for China Lens and Observatory. CI builds it when `SYMPHONY_WEB=1`, but current rebuild docs classify it as parked. Confidence: high.

Common environment and cache behavior:

| Area | Current contract | Confidence |
| --- | --- | --- |
| SEC identity | Live SEC access requires `EDGARPACK_USER_AGENT`; `SECClient` fails early if missing. | high |
| SEC cache | `EDGARPACK_CACHE_DIR`, default `~/.edgarpack/cache`; URL SHA256 files; atomic writes; corrupt entries refetch; companyfacts cached 24h; ticker map cached 24h with stale fallback; older submissions pages treated as immutable. | high |
| SEC pacing | `EDGARPACK_SEC_RATE_LIMIT`, default 5 rps; `EDGARPACK_SEC_MAX_RETRIES`, default 3; rate-limit handling raises typed errors in important paths. | high |
| Terminal links | `NO_COLOR`, `TERM_PROGRAM`, `TERM` affect OSC link rendering only. | high |
| S-1/F-1 VLM fallback | `ANTHROPIC_API_KEY` is optional; missing key creates actionable placeholder behavior for unsupported extraction shapes. | high |
| SSE translation | `EDGARPACK_DEEPINFRA_KEY`, fallback `DEEPINFRA_API_KEY`; translation cache in SQLite by provider/model namespace. | high |
| China workspace storage | `EDGARPACK_CHINA_STORAGE_BACKEND`, `EDGARPACK_CHINA_STORAGE_DIR`, `EDGARPACK_CHINA_OBJECT_STORE_DIR`, `EDGARPACK_CHINA_POSTGRES_DSN`, `EDGARPACK_CHINA_SEED_FIXTURES`. | medium |
| Web env | `NEXT_PUBLIC_CHINA_LENS_API_BASE`, `NEXT_PUBLIC_CHINA_LENS_DEMO`, `NEXT_PUBLIC_OBSERVATORY_API_BASE`. | high |

## 2.1 CLI commands

| Entry point | Inputs | Outputs and files | Side effects, services, cache, determinism, provenance | Coverage | Status |
| --- | --- | --- | --- | --- | --- |
| `edgarpack home` | none | welcome text and starter commands | No files, network, or cache. Deterministic. No citations. | startup/lazy import tests indirectly | active, lightweight |
| `edgarpack build` | company/ticker/CIK/name or deprecated `--cik`; `--accession`; `--form`; `--out`; `--with-chunks`; `--with-xbrl`; `--force`; `--last`; `--after`; `--before` | Pack under `packs/<cik>/<accession>/`: `filing.full.md`, `sections/*.md`, `manifest.json`, `llms.txt`, optional `optional/chunks.ndjson`, optional XBRL JSON, registration assets | Touches SEC submissions/archive/companyfacts endpoints unless exact cached; writes registry; deterministic output expected except fetch timestamp; citations/provenance through manifest, section hashes, chunk IDs, SEC URLs. | build/range/manifest/parse/chunk/doctor/S-1 tests; live smoke gated | active core |
| `edgarpack list` | company/ticker/CIK/name or deprecated `--cik`; `--form`; `--limit` | terminal list of filings | SEC submissions network/cache; no artifact writes except cache. Deterministic for same SEC response. Provenance is accession/form/date. | CLI/list coverage is lighter than build/query | active |
| `edgarpack company-llms` | company or deprecated `--cik`; `--out` | company-level `llms.txt` under pack root | Reads built packs, no SEC network required if packs exist. Deterministic over existing packs. Provenance is pack manifest links. | llms/build tests | active but narrow |
| `edgarpack site` | `--packs`; `--out`; `--base-url` reserved | static HTML site under `site/` or chosen dir; copies/links pack files | Reads local packs; writes site files. No network. `--base-url` appears reserved/unused. Provenance through local pack and SEC links in rendered pages. | site tests and Pages workflow | active static renderer |
| `edgarpack query` | company; optional metrics CSV; `--period`; `--preset`; `--format table/json/json-full`; `--audit`; `--show-links`; `--citations`; `--force`; `--packs`; `--strict`; `--currency` | table, lean JSON, or full cited JSON; audit blocks; reproduce command | SEC companyfacts/submissions cache; reads local packs for S-1/HKEX/SSE/KPI paths; may write learned registry unless strict; deterministic if cache and date-sensitive staleness are controlled. Citation contract via `CitedValue`, `DerivedValue`, registry, formulas, source URLs. | heavy: financials, periods, JSON, strict, no-key, S-1, HK/SSE golden | active core |
| `edgarpack comps` | companies list; `--metrics`; `--period`; `--format`; `--audit`; `--show-links`; `--citations`; `--force`; `--strict` | side-by-side SEC table or JSON | Fan-out over `financials()`; SEC network/cache; no durable artifacts except learned cache. Citation output should carry per-cell provenance and formula audit. | comps/integrity/query tests | active for SEC comps |
| `edgarpack compare` | companies list; optional `--metrics`; `--period`; `--currency`; `--format table/json/markdown`; `--strict` | cross-market comparison table/JSON/markdown | Routes SEC/HKEX/SSE via identity; uses FX rates and local China packs; may read facts.json. Currency warnings and source provenance matter. | compare, FX, HK/SSE tests | active but riskier |
| `edgarpack which` | company; `--format`; `--no-cache`; `--only`; `--max-periods`; `--currency` | KPI catalog/discovered matrix; S-1 disclosure inventory | Reads built packs; may call LLM for KPI discovery; writes `company_kpis` and `learned_concepts`; deterministic when cached, not deterministic with live LLM. Citation/provenance expected through evidence snippets and source pack sections. | CLI which, KPI discovery, S-1 which tests | active, LLM edge optional |
| `edgarpack diff` | `--ticker`; `--form`; `--before`; `--after`; `--format summary/full/json/html`; `--out` | summary/full terminal, JSON, or static HTML pair report | Reads local packs and registry; writes HTML report when requested; diff cache under `~/.edgarpack/diff_cache`. No network except ticker resolution if not local. Evidence anchors include accessions, section IDs, paragraph positions, source links, optional chunk IDs. | substantial diff/report tests and recent history | active core |
| `edgarpack timeline` | annual: `--ticker`, `--section`, `--form`; registration: `--cik`, `--packs`; `--series annual/registration`; `--format text/html`; `--out` | annual text timeline or registration HTML index plus pair reports | Reads packs; registration HTML writes report directory. Uses diff engine but not all pair-diff filtering in annual path. Evidence from pack manifests and pair report anchors. | timeline and registration report tests | active, registration path newer |
| `edgarpack harvest` | `--universe`; `--out`; `--plan`; `--refresh`; `--with-chunks`; `--concurrency`; `--force`; `--describe-images` | plan output or built pack corpus | SEC network/cache; writes packs and harvest registry; optional VLM asset descriptions and image cache. Determinism depends on SEC inputs and VLM flag. Provenance through pack artifacts. | planner/registry/runner tests; daily-refresh script | active batch tool; VLM option experimental |
| `edgarpack index` | `--packs`; `--incremental` | SQLite FTS index, normally `search_index.db` | Reads packs/chunks; writes FTS tables; marks registry indexed. No network. Deterministic over packs. Provenance via chunk metadata. | index/search tests including stale FTS purge | active local search |
| `edgarpack search` | query; `--topic`; `--ticker`; `--form`; `--limit` | ranked terminal results | Reads FTS index and topic catalog. No network. Provenance is pack/chunk/section coordinates. | search/index tests | active |
| `edgarpack identify` | company/name/ticker/code/alias | classification as SEC, HKEX, SSE/A-share, private, unknown | Reads universe/static identity; may use adapters for non-US. No durable writes. Provenance is weak in output. | identity tests | active routing helper |
| `edgarpack build-sse` | target; `--latest-annual`; `--url`; `--stock-code`; `--company`; `--filing-date`; `--out`; `--pdf`; `--with-chunks`; `--translate`; translation flags; `--form-type`; `--force` | SSE/CNINFO pack, `optional/source.pdf`, sections, manifest, chunks, facts for annual reports, optional translated files | CNINFO/SSE/PDF network unless `--pdf`; DeepInfra optional; PDF cache is weaker than SEC cache; deterministic except translation/provider. Provenance through manifest and source PDF, but current China filed-date fallback can fabricate year-end date. | SSE/build/china golden/translation tests | active China lane |
| `edgarpack translate-sse` | `--pack`; `--model`; `--concurrency`; `--batch-size`; `--force` | English translated sections/artifacts and progress summary | DeepInfra network; SQLite translation cache; fail-closed validators; interrupted runs resume from cached batches. Provenance should point back to original section/source. | translation artifact/provider/validator tests; no live provider lane | active but live-untested |
| `edgarpack learned list/show/verify/clear` | filters or exact CIK/metric; `--source`; `--unverified`; `--all` for clear | learned mapping listings or mutations | Mutates learned registry on verify/clear. No network. Provenance is source mechanism and verification metadata. `source=user` is in schema but no active producer found. | self-heal tests | active support surface with uncertain parts |
| `edgarpack cache --clear` | `--clear` optional | cache path/info or cleared cache | Reads/deletes SEC cache dir. No citations. Destructive to local cache only. | light | active support |
| `edgarpack api` | `--host`; `--port` | runs uvicorn FastAPI app | Starts service, imports optional FastAPI/uvicorn. Storage may seed demo evidence by default. Network server side effect. Citation behavior depends on service. | API/service tests partial | parked per rebuild docs |
| `edgarpack doctor` | target pack path or ticker; `--format text/json` | diagnosis report | Reads pack(s), no network except ticker/path resolution. Checks artifact inventory, manifest state, registration coverage. | pack doctor tests | active diagnostic |
| `edgarpack distill run/check` | run: slug, `--pack` or `--company`+`--accession`, `--packs`, `--out`, `--force`; check: bundle path | `reports/<slug>/index.md`, `findings.csv`, `metrics.csv`, `evidence.jsonl`, `gaps.csv`, `filing-map.md`, `run-log.md`, `bundle.json`; validation report | Reads existing packs only; writes distill bundle; no network; rows need evidence or go to gaps. Current bundle embeds paths. | distill builder/writer/check tests | active newer surface |
| `edgarpack f1` / `edgarpack s1` | company; optional metrics; `--accession`; query-like flags; `--packs`; `--force` | query output after building latest registration pack if needed | SEC network/cache and pack writes if missing or forced; routes through registration form defaults. Citation contract is S-1/F-1 snapshot evidence. | current branch tests registration shortcuts | active newer surface |

## 2.2 Python API surfaces

| Surface | Inputs/outputs | Side effects and provenance | Coverage | Status |
| --- | --- | --- | --- | --- |
| `edgarpack.pack.build.build_pack`, `build_pack_range`, `build_sse_pack`, `build_company_llms` | source identifiers/options to `PackResult` and durable packs | SEC/SSE/CNINFO network; pack writes; manifest/chunks/facts provenance. | high for SEC build; medium for SSE | active core |
| `edgarpack.query.financials.financials` | company, metrics, period, packs root, currency, strict-ish flags to `QueryResult` | SEC companyfacts, local pack reads, learned registry writes; citation-rich model. | high | active core |
| `edgarpack.query.periods.select_period` and formula helpers | `MetricSeries`, selector to cited/derived values | No files; period and formula provenance. Autouse test harness asserts LTM invariant. | high | active core |
| `edgarpack.diff.section_diff.diff_filings`, `edgarpack.diff.timeline.build_timeline` | pack dirs or section series to diff models | Reads packs; writes/reads diff cache; evidence anchors. | high for pair diff, medium for timeline | active core |
| `edgarpack.distill.builder.build_distill_bundle`, `writers`, `checks` | pack dir/output to bundle and validation | Reads pack, writes report directory; evidence rows. | medium-high | active new |
| `edgarpack.harvest.runner`, `planner`, `registry` | universe TOML to build plan, SQLite registry | SEC build side effects; registry mutation. | medium | active batch |
| `edgarpack.index.inverted`, `search`, topic catalog | packs/chunks to FTS index and query results | SQLite writes and registry marking. | high | active local search |
| `edgarpack.hk.*`, `edgarpack.sse.*`, `edgarpack.china.translate.*` | PDF/source docs to packs/facts/translations | Network/PDF/DeepInfra/cache; primary-source provenance varies by adapter. | medium | active China/HK lane |
| `edgarpack.china.service.ChinaLensService`, storage adapters | service requests to workspace models | JSON/Postgres/memory state; seeded fixtures by default unless disabled. | medium | parked service core |
| `edgarpack.insights.*` | indexed corpus to insight models | Reads index/registry; no clear public active caller found. | low-medium | experimental/parked |

## 2.3 FastAPI and web surfaces

| Surface | Inputs/outputs | Side effects and services | Coverage | Status |
| --- | --- | --- | --- | --- |
| `/healthz` | GET to health JSON | none | minimal | parked |
| `/api/v1/companies`, `/packs`, `/documents`, `/evidence`, `/ask`, `/citations`, `/connectors` | China Lens workspace JSON | `ChinaLensService`; storage adapters; can seed demo evidence; pack status GET advances job state by one tick. | service and some API tests | parked |
| `/api/v1/observatory/...` | companies, diff, timeline, search, stats, topics | wraps local registry/index/diff models | no full HTTP lane found | parked wrapper over active diff/search |
| `web/app/workspace/*` | Next routes for China Lens workspace | calls `web/lib/api-client.ts`; can fall back to demo sample data | web build in CI, component tests not obvious | parked |
| `web/app/observatory/*` | Next routes for Observatory UI | calls `NEXT_PUBLIC_OBSERVATORY_API_BASE`; errors loudly if API missing | web build in CI | parked |

# 3. Product truth versus implementation accident

User jobs:

| User job | Evidence | Status | Confidence |
| --- | --- | --- | --- |
| Get cited financial values from filings. | `query`, `comps`, `compare`, `docs/QUERY.md`, metric directory. | active investor-critical | high |
| Build deterministic filing packs for reading, search, diffs, and LLM handoff. | `build`, `llms.txt`, `optional/chunks.ndjson`, workflows. | active handoff-critical | high |
| Inspect disclosure changes without mechanical filing noise. | `diff`, `timeline`, `docs/OBSERVATORY.md`, recent diff commits. | active investor-critical | high |
| Work with pre-IPO registration filings where companyfacts is empty. | S-1 guide, `f1`/`s1`, `s1_financials.py`, branch history. | active investor-critical | high |
| Compare SEC/HKEX/SSE companies with period/currency warnings. | `compare`, HK/SSE code, China golden fixtures. | active but fragile | medium |
| Translate and inspect Chinese primary filings. | `build-sse`, `translate-sse`, China Lens docs. | active CLI lane, service parked | medium |
| Produce small evidence bundles from one filing. | `distill`, docs, tests. | active new | medium-high |
| Run a browser workspace for China Lens/Evidence Explorer. | FastAPI/web code, implementation tracker, rebuild docs. | parked unless revived | high |
| Generate insights from indexed corpus. | `insights/` modules, no clear active caller. | experimental/parked | medium |

Product promises:

- Citation-backed values and findings. This is explicit in `AGENTS.md`, README, query models, distill, and docs. Confidence: high.
- Deterministic, inspectable artifacts. Build pipeline, manifest hashes, docs, and tests support this. Confidence: high.
- Missing evidence stays missing. `CitedValue` nullable outputs, S-1 no-key placeholder, distill gaps, and docs all encode this. Confidence: high.
- Period/currency context is not hidden. Query/compare outputs, FX handling, warnings, and tests support this. Confidence: high.
- Local-first agent handoff. `llms.txt`, chunks, JSON outputs, static site, and distill exist for downstream tooling. Confidence: high.

Implementation mechanisms:

- Custom SEC client/cache/submissions/ticker/companyfacts/archive stack.
- Custom HTML/iXBRL cleaning, markdown rendering, sectionizing, polishing, and chunking.
- Custom concept map, period selector, calculation registry, citation registry.
- SQLite registries for harvest/search/learned mappings/translation cache.
- Custom deterministic diff and static HTML renderer.
- PDF-to-markdown adapters for HKEX/SSE plus regex facts extraction.
- Optional LLM/VLM fallbacks for S-1 tables, KPI discovery, HK facts, and registration assets.

Historical accidents and likely bloat:

- `api` and `web` appear to have been added for China Lens workspace exploration, then parked. They still run/build, but they should not define vNext unless revived. Confidence: high.
- `insights/` is an analytical layer over the filing index with no obvious CLI/API route. It may be useful, but it is not part of the active contract. Confidence: medium.
- Two concept maps exist: `query/concepts.py` as the real CLI registry and `query/metric_map.py` as a smaller cross-standard helper. Docs explicitly call out the distinction. The smaller map may be load-bearing for HK/China but should not be mistaken for the source of truth. Confidence: high.
- `site --base-url` is reserved but not meaningfully used. Confidence: high.
- `--cik` flags remain deprecated compatibility shims. Confidence: high.
- Seeded China API fixtures and demo web fixtures are useful for UI demos but dangerous as default evidence. Confidence: high.

Investor-critical workflows:

- `query`, `comps`, `compare`, `diff`, `timeline`, `f1`/`s1`, S-1 financial extraction, HKEX/SSE facts, currency conversion, and distill. Confidence: high.

Agent/LLM handoff-critical workflows:

- `build` packs, `manifest.json`, `llms.txt`, `optional/chunks.ndjson`, JSON query outputs, static HTML diff reports, `distill` evidence bundles. Confidence: high.

Parked workflows:

- FastAPI Evidence Explorer workspace, Next China Lens workspace, Observatory API UI, demo data seeding, broad `insights/`. Confidence: medium-high.

Parts that exist because they were easy to add, not clearly because they belong:

- Generic workspace CRUD around China Lens; `web/lib/sample-data.ts`; route wrappers that duplicate CLI-visible behavior; VLM asset descriptions; broad topic/insight extraction; `home` marketing copy. Marking these as removable would require Samay scope confirmation. Confidence: medium.

# 4. Architecture map

High-level data flow:

```text
Identity input
  -> identity.py / sec.tickers / CNINFO/HK aliases
  -> source adapters
       SEC submissions + archive + companyfacts
       HKEX PDF/index
       SSE/CNINFO PDF/index
  -> pack builders
       iXBRL strip -> HTML clean -> semantic reduce -> markdown render -> polish -> sectionize
       PDF -> markdown -> sectionize_cn / HK heading maps
  -> artifacts
       filing.full.md, sections, manifest, llms.txt, chunks, facts, assets
  -> analysis layers
       query/periods/citations, diff/timeline, search/index, distill, compare/fx
  -> renderers
       CLI tables/JSON, static site, static diff HTML, distill CSV/JSONL/MD
  -> parked service/UI
       FastAPI routes, Next workspace
```

Core dependency graph:

```text
cli.py
  -> identity, config
  -> sec/* -> pack/build -> parse/* -> pack/* -> harvest/registry
  -> query/financials -> query/periods/models/citations/concepts/self_heal
  -> compare -> fx + query + identity
  -> diff/* -> pack manifests + chunks
  -> harvest/* -> pack/build + registry
  -> index/* -> registry + chunks/sections
  -> distill/* -> pack reader + S-1 snapshot
  -> hk/sse/china adapters
  -> api/main only for `api`

web/
  -> HTTP clients -> api routes -> china/service or observatory wrappers
```

## 4.1 Module map

| Package/module | Responsibility | Upstream dependencies | Downstream consumers | Type/status | Overburdened? |
| --- | --- | --- | --- | --- | --- |
| `edgarpack/cli.py` | Single argparse surface, rendering glue, command orchestration | nearly every package | all CLI users | CLI, active | yes. It is too large and contains orchestration that belongs in services. |
| `edgarpack/config.py` | Env parsing, constants, defaults | stdlib | SEC/cache/query/build | config, active | no |
| `edgarpack/identity.py` | Company resolution and market routing | universe/static data, SEC ticker helpers | query/build/compare/identify | adapter/core boundary | medium, because SEC/HK/SSE/private concerns mix |
| `edgarpack/sec/*` | SEC HTTP, cache, submissions, archives, ticker resolution, XBRL companyfacts | `config`, urllib/json | build/query/list/harvest | source adapter, active | moderate |
| `edgarpack/parse/*` | HTML/iXBRL/table/markdown/section pipeline | stdlib parsers, optional tokenizer | pack build, diff/search/query S-1 | core parsing, active | yes, because real filing scar tissue accumulates here |
| `edgarpack/pack/*` | Durable pack artifacts, manifest, chunks, llms, doctor, assets | SEC/HK/SSE adapters, parse | CLI, query fallback, diff, index, site, distill | core artifact layer | moderate |
| `edgarpack/query/*` | Metric concepts, financial selection, periods, citations, render, S-1 snapshots, KPI discovery, self-heal | SEC companyfacts, packs, learned registry, optional LLM | query/comps/compare/which/distill | core query engine | yes. `financials.py` is doing too many source-specific jobs. |
| `edgarpack/diff/*` | Paragraph and section diffs, report model/builder, static HTML, timelines | packs, chunks, manifests | diff/timeline/API/docs | core analysis + renderer | moderate |
| `edgarpack/harvest/*` | Universe planning, batch build runner, SQLite registry | build/sec/config | harvest/index/diff/search | adapter/orchestration | no |
| `edgarpack/index/*` | FTS index, search, topic extraction/catalog | packs/chunks/registry/sqlite | search/API/insights | active local search | moderate |
| `edgarpack/insights/*` | Higher-level disclosure analytics | index/registry/diff | tests only found | experimental/parked | uncertain |
| `edgarpack/fx/*` | Currency conversion and rate lookup | `data/fx_rates.csv` | compare/query China paths | adapter/support | no |
| `edgarpack/hk/*` | HKEX PDF acquisition, pack build, facts extraction, optional LLM fill | PDF/markdown, hardcoded company meta | compare/query/build fixtures | source adapter, active | yes, because metadata defaults and extraction are entangled |
| `edgarpack/sse/*` | SSE/CNINFO PDF fetch, PDF-to-MD, Chinese section/facts extraction | httpx/pymupdf4llm optional | build-sse/query/translate | source adapter, active | moderate |
| `edgarpack/china/*` | CNINFO acquisition, translation, China Lens service/storage | httpx/sqlite/FastAPI optional | build-sse/translate-sse/API/web | mixed active and parked | yes, service/UI storage concerns mix with source adapters |
| `edgarpack/distill/*` | One-pack compact evidence bundle | packs/S-1 snapshot | CLI distill | renderer/artifact layer, active | no |
| `edgarpack/site/*` | Static pack browser | packs | CLI site, Pages workflow | renderer, active | no |
| `edgarpack/api/*` | FastAPI routers | service/diff/search | `edgarpack api`, web | parked API | medium |
| `web/*` | Next UI for China Lens and Observatory | API env URLs | browser users | parked web | no for UI, yes as product scope |
| `scripts/*` | quality gate, daily refresh, FX refresh, metric docs, benchmarks, cleanup | CLI, external services | dev/release ops | support | no |

Boundaries that look necessary:

- Source acquisition must stay separate from artifact generation. SEC, HKEX, SSE, CNINFO, and translation all have different failure/cache semantics.
- Pack artifacts must remain a stable contract between build, query fallback, diff, search, distill, site, and LLM handoff.
- Query values need a first-class citation/calculation model, not renderer-specific strings.
- Diff/timeline should consume packs, not raw SEC HTML.
- China/HK/SSE should be adapters with explicit fact extraction and currency/accounting standard metadata.

Boundaries that look accidental:

- CLI contains service orchestration, rendering, and some domain logic.
- `financials.py` crosses SEC companyfacts, S-1 packs, China pack discovery, metric selection, stale checks, and serialization.
- API/web workspace code lives beside active CLI code and can pull scope into vNext accidentally.
- Learned/self-heal and KPI discovery are intermixed with deterministic query paths.

# 5. Data and artifact contracts

| Artifact/contract | Shape | Documented | Tested | Consumed by code | User-visible | vNext disposition | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Pack layout | `packs/<cik>/<accession>/...`; China/SSE variants under `packs/sse/...` | yes | high | many modules | yes | preserve semantically, maybe shim paths | high |
| `filing.full.md` | full cleaned markdown | yes | high | diff/search/distill/manual | yes | preserve semantically | high |
| `sections/*.md` | section files by stable IDs | yes | high for SEC/S-1; medium China | query fallback, diff, search, distill, llms | yes | preserve IDs where parity needs them | high |
| `manifest.json` | source, filing, sections, hashes, parser/schema, optional translation metadata | yes | high | nearly all pack consumers | yes | preserve or migrate with compatibility loader | high |
| `llms.txt` | compact pack/company index | yes | medium | user/agent handoff | yes | preserve semantically | high |
| `optional/chunks.ndjson` | chunk IDs, section, text, offsets/hash | yes | high | search, diff report chunk anchors, RAG handoff | yes | preserve semantically, keep stable IDs if possible | high |
| XBRL artifacts | optional companyfacts/XBRL JSON | partly | medium | query/build diagnostics | mostly machine | wrap/delegate possible | medium |
| `facts.json` | HK/SSE extracted facts | partly | medium via golden | query China/HK compare | machine/user via query | preserve semantically, fix known bad provenance | high |
| Query JSON lean | `QueryResult.to_lean_dict` compact metrics/citations | yes | high | agents/users | yes | preserve or version | high |
| Query `json-full` | full `CitedValue`/`DerivedValue`/filing/citation data | yes | high | agents/tests | yes | preserve fields semantically; version if changed | high |
| Citation registry | `C#`, calculation IDs, source records | partly | high | render/audit/json | yes | preserve concept exactly | high |
| Calculation registry | formulas and components | partly | high for LTM/derived | audit/json/render | yes | preserve semantically | high |
| `CitedValue` | value, unit, metric, concept, period, filing, source tags, URLs, warnings, excerpt, accounting/currency metadata | partly | high | query/comps/compare/render/distill | yes | preserve semantically | high |
| `DerivedValue` | formula, components, warnings, citation/calculation links | partly | high | derived metrics/audit | yes | preserve semantically | high |
| Diff output | `DiffResult`, `SectionDelta`, `ParagraphDelta`; summary/full/json/html | yes | high | CLI/API/report | yes | preserve semantic labels including `moved` | high |
| Timeline output | annual text, registration HTML index/pairs | yes | medium | CLI/report | yes | preserve registration behavior, reconsider annual API | medium |
| Site output | static HTML pages and copied pack links | basic | medium-high | Pages workflow/users | yes | preserve if public showcase remains | medium |
| Translation artifacts | translated sections/metadata/cache | docs | medium | CLI/query/manual | yes | preserve semantically, harden live contract | medium |
| Failure artifacts | distill gaps, warnings, no-key placeholders, harvest errors | partial | medium | CLI/tests | yes | preserve fail-empty/fail-loud behavior | high |
| SEC cache files | SHA256 URL cache | docs/ref | high | SEC client | no | can intentionally break if wrapper supplies equivalent behavior | medium |
| Translation cache | SQLite by provider/model namespace | docs | high unit | translate-sse | no | preserve resume semantics, not exact file | high |
| Learned/self-heal artifacts | SQLite learned concepts and KPI rows | docs/tests | high self-heal, medium KPI | query/which/learned | yes via CLI | preserve only if self-heal remains active; version needed | medium |
| Generated metric directory | `docs/METRIC_DIRECTORY.md/json` from script | yes | script has check mode | docs/users | yes | preserve generation or replace with registry export | medium |
| Distill bundle | MD/CSV/JSONL/gaps/map/log/bundle | yes | medium-high | check/users/agents | yes | preserve semantically | high |

# 6. Complexity audit

## 6.1 Essential complexity

| Item | Files/modules | Real condition handled | Evidence | Breakage if removed | vNext preservation | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Six-step SEC parse pipeline | `pack/build.py`, `parse/ixbrl_strip.py`, `html_clean.py`, `semantic_html.py`, `md_render.py`, `md_polish.py`, `sectionize.py` | SEC filings mix iXBRL, weird HTML, hidden text, tables, TOCs, anchors. | build docs, parse tests, commit history, scar tissue memo. | Garbled packs, unstable sections, broken diffs/search/S-1 queries. | Keep explicit staged parser, but isolate each stage with fixtures and golden outputs. | high |
| Font-size-zero S-1 wrapper guard | `parse/html_clean.py`, `tests/test_html_clean_s1_wrapper.py` | Registration filings can wrap real content in `font-size:0` style containers. | recent F-1 upgrade commit and tests. | Entire S-1/F-1 filings can disappear. | Preserve as named rule with corpus fixture. | high |
| Malformed table span handling | `parse/md_render.py`, TSM fixture/tests | Real tables have bad colspan/rowspan values. | commit `fix(parse): handle malformed table spans`; fixtures. | Table cells shift or crash; facts extraction misreads values. | Use robust table model with explicit span normalization. | high |
| TOC, index, cross-reference section guards | `parse/sectionize.py`, `md_polish.py` | Filing TOCs and references look like headings. | docs, tests, commit history `reject cross-ref...`. | Duplicate or false section IDs; diff/report quality collapses. | Keep heading detector with negative corpus cases. | high |
| S-1/F-1 heading injection and snapshot extraction | `parse/s1_headings.py`, `query/s1_financials.py`, `cli.py` shortcuts | Pre-IPO filers lack companyfacts; selected financial tables vary. | S-1 docs/tests/current branch commits. | Registration query returns N/A or wrong older values. | Make registration adapter first-class, not fallback hidden in SEC query. | high |
| LTM three-citation invariant | `query/periods.py`, `query/formula.py`, `tests/conftest.py` | LTM needs YTD + FY - prior YTD, with alignment. | docs, autouse test harness, many period tests. | Silent wrong LTM and bad investor outputs. | Keep period algebra and citation formula model as non-negotiable core. | high |
| Per-share and instant metric period exceptions | `query/periods.py` | EPS/per-share cannot always LTM-sum; balance sheet metrics are instants. | period docs/tests and scar memo. | Nonsense derived numbers. | Encode metric shape policy in typed registry. | high |
| Strict mode learned-value rejection | `query/strict.py`, `models.py`, `financials.py` | Users need deterministic hardcoded-only values. | tests after `f73972e`; docs metric directory. | Learned or text-scan values leak into strict output. | Preserve a deterministic mode at query boundary. | high |
| Citation/calculation registry | `query/models.py`, `citations.py`, render/json | Product promise requires auditable values. | AGENTS, README, tests. | Outputs become claims without evidence. | Keep as core domain concept independent of renderer. | high |
| Diff moved/distinctive-token/containment logic | `diff/text_diff.py`, `section_diff.py`, report modules | SEC paragraphs move, re-split, and share legal boilerplate. | recent commits and OBSERVATORY docs. | False added/removed risk factors dominate reports. | Preserve behavior with pairwise parity fixtures. | high |
| HKEX wrapped-label and column-shift guards | `hk/extract.py`, China golden tests | PDF text extraction wraps labels and table columns. | HK commits and golden xfails. | Misattributed financial facts. | Keep PDF table extraction as adapter with golden expected facts. | high |
| SSE translation validators and resume cache | `china/translate/*`, translate tests | LLM translation can drop numbers, tokens, tables, or stop mid-run. | implementation tracker and tests. | English artifacts become untrustworthy or expensive to resume. | Keep fail-closed validators and resumable cache. | high |
| SEC rate-limit/user-agent/cache semantics | `sec/client.py`, `sec/cache.py`, `config.py` | SEC fair access and flaky network. | docs/tests/deploy workflow. | Live commands fail or get blocked. | Delegate only if wrapper preserves identity, pacing, retries, cache failure semantics. | high |

## 6.2 Accidental complexity

| Item | Files/modules | Why it might have existed | Evidence unnecessary or lower priority | Behavior to pin first | Simplification path | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Parked FastAPI workspace | `edgarpack/api/*`, `china/service.py` | China Lens product exploration and Evidence Explorer. | Rebuild docs classify as parked; CLI is active surface. | API route list and seed behavior if Samay revives. | Move behind optional package or archive until product surface is active. | medium-high |
| Next workspace demo mode | `web/*`, `web/lib/sample-data.ts` | UI iteration without backend. | No active deployment docs found beyond web build; API fallback can present demo data. | Demo visual state if needed. | Keep as separate demo app, not vNext core. | medium |
| `site --base-url` reserved flag | `cli.py`, `site/build.py` | Future hosted site URL handling. | Deprecation docs note it is reserved/unused. | Current output with and without flag. | Remove or implement only if public URLs require it. | high |
| Deprecated `--cik` options | `build`, `list`, `company-llms` | Backward compatibility. | Positional company now accepts CIK. | Old command compatibility if required. | Compatibility shim or documented breaking change. | high |
| Seeded China API fixtures default-on | `china/service.py` | Offline demo convenience. | Known-bad rebuild doc flags fabricated evidence risk. | API demo behavior. | Flip default off if API revived; keep explicit demo flag. | high |
| Broad `insights/` layer | `edgarpack/insights/*` | Observatory expansion after indexing. | No obvious current CLI/API route found. | Any tests that assert outputs. | Park in separate experimental namespace. | medium |
| VLM asset image descriptions | `pack/assets.py`, harvest `--describe-images` | Registration filings with important images. | Optional flag, no active docs beyond help; cost-bearing. | Asset download and description cache behavior. | Keep asset download; park description generation. | medium |
| Dual metric maps | `query/concepts.py`, `query/metric_map.py` | Cross-standard helper grew beside main registry. | Metric directory says `concepts.py` owns CLI registry. | HK/SSE consumers of `metric_map.py`. | Collapse into one typed registry with accounting-standard overrides, after parity. | medium |

## 6.3 Uncertain complexity

| Item | Files/modules | Possible reason | Missing evidence | Needed case | Confidence |
| --- | --- | --- | --- | --- | --- |
| `query/financials.py` China pack discovery reads `tests/fixtures/china_packs` | `query/financials.py` | Makes offline China query tests work without installing packs. | Whether production intentionally supports fixture fallback. | Production-like China pack query outside tests. | medium |
| `_STALENESS_YEARS = {}` with default fallback | `query/financials.py` | Placeholder for metric-specific freshness rules. | No populated config found. | Query stale/non-stale fixtures by metric. | medium |
| `learned_concepts.source='user'` | `models.py`, `self_heal.py`, CLI learned | Planned manual overrides. | No active producer found. | User override workflow or deletion decision. | medium |
| HKEX LLM fallback with `client=None` in active extraction | `hk/extract.py`, `hk/llm_extract.py` | Future fallback or disabled-cost guard. | Whether any production run passes a real client. | HK filing where regex misses value and LLM should fill. | medium |
| `translate-sse` inline orchestrator in CLI | `cli.py`, `china/translate/*` | Progress and resume UX needed before abstraction. | Whether users rely on exact progress text. | Interrupted full annual report resume corpus. | high for behavior, medium for structure |
| `distill` path embedding in `bundle.json` | `distill/models.py`, `writers.py` | Traceability to source pack/output. | Whether absolute/local paths are acceptable durable contract. | Moving bundle between machines. | medium |
| `api` status GET mutates job progress | `china/service.py` | Simulated async jobs for demo. | Whether intended API contract. | Real UI polling against service. | medium |

## 6.4 Parked complexity

| Item | Files/modules | Current status | Revival trigger | Isolation if kept | Confidence |
| --- | --- | --- | --- | --- | --- |
| China Lens FastAPI workspace | `edgarpack/api/*`, `china/service.py` | parked by rebuild decision docs | Samay says Evidence Explorer/API is active product | optional extra package, explicit storage config, seed fixtures off | high |
| Next workspace | `web/*` | parked UI, still built in CI | Samay wants browser workflow | separate app consuming versioned API | high |
| Observatory API wrapper | `api/observatory/routes.py` | parked wrapper over active diff/search | hosted observatory revived | keep API thin over core models | medium |
| `insights/` | `edgarpack/insights/*` | experimental | user asks for corpus-level language/topic analytics | separate command/API with own artifacts | medium |
| Asset VLM descriptions | `pack/assets.py` | optional experimental | registration visuals are investor-critical | explicit asset analysis module, not build default | medium |

# 7. Test and behavior-pinning reality

What is covered by tests:

- Query period selection, LTM formulas, derived metrics, strict mode, self-heal, CLI JSON, formatting, links, no-key hints. Confidence: high.
- Build artifacts, parse edge cases, sectionization, chunks, manifest, doctor, site. Confidence: high.
- Diff text/section/report behavior, including moved paragraphs and distinctive-token gating. Confidence: high.
- HK/SSE/China golden fixture lanes, translation validators, DeepInfra client config, storage. Confidence: medium-high.
- Distill bundle writer/checker. Confidence: medium-high.
- Search index/registry stale FTS behavior. Confidence: high.
- Web build via CI when `SYMPHONY_WEB=1`; behavior tests are limited. Confidence: medium.

What is only covered by fixtures:

- MiniMax/Zhipu China facts and golden values, including known xfails.
- S-1/F-1 registration table shapes from Cerebras and test HTML fixtures.
- Some malformed table and font-size-zero parser cases.
- Distill sample pack behavior.

What is only encoded in implementation:

- Many CLI exact rendering details, progress messages, cache file names, learned registry semantics, and API workspace polling behavior.
- Some China provenance fallbacks, HK unknown-filer defaults, and fixture fallback paths.
- Exact static site HTML structure beyond smoke tests.

Documented but untested or under-tested:

- Full live SSE/CNINFO/DeepInfra behavior.
- Public Pages showcase build from live SEC.
- Complete FastAPI HTTP contract.
- Exact `llms.txt` consumer expectations.
- `site --base-url`.
- API demo fixture safety.

Tested but under-documented:

- Autouse LTM invariant harness.
- Strict rejection of learned/text-scan values.
- Diff moved paragraph counts/scoring.
- S-1 no-key placeholder rows.
- Search FTS stale posting purge.

Neither fully documented nor fully tested but important:

- China pack discovery fallback into test fixtures.
- HKEX `matched_label` loss in serialized facts.
- Query staleness policy by metric.
- Annual timeline not sharing all pair-diff boilerplate filtering.
- Translation progress text and partial artifact behavior.

Naive rewrite edge cases likely to lose:

- S-1 wrapper hidden-content guard.
- TOC and cross-reference false heading rejection.
- LTM exactly three citations with formula audit.
- Per-share LTM degradation and instant metric latest-value policy.
- SEC 404 companyfacts returns empty, but non-404 raises.
- Older submissions page immutable cache handling.
- Diff `moved` versus `added/removed` classification.
- HKEX wrapped-label/table-column repairs.
- SSE translation literal/number/table validators.

Coverage table:

| Behavior | Current coverage | Risk | Suggested parity case | Priority |
| --- | --- | --- | --- | --- |
| SEC pack deterministic layout | build/manifest/chunk tests, live determinism gated | high | one offline fixture pack byte contract plus one live smoke | P0 |
| S-1/F-1 selected financial extraction | strong targeted tests, current branch | high | Cerebras 2024/2026 and one F-1 fixture with no-key fallback | P0 |
| LTM formula and citations | autouse harness plus period tests | high | parity JSON for revenue LTM and derived margin LTM | P0 |
| Strict mode | strict/self-heal tests | medium | learned value rejected with warning in query JSON | P0 |
| SEC 404 vs fetch error | xbrl/client tests | high | companyfacts 404 empty, 500 raises, cache not poisoned | P0 |
| Sectionizer TOC/cross-ref guards | unit fixtures | high | filing fixture with TOC, cross-ref sentence, inline heading | P0 |
| Diff moved/re-split/legalese | strong recent tests | high | old/new pair with reordered and re-split risk paragraphs | P0 |
| HKEX table extraction | golden fixtures plus known xfails | high | MiniMax/Zhipu facts and query parity, include xfails explicitly | P0 |
| SSE annual facts | China tests | high | CNINFO annual report fixture with units, fiscal date, facts | P0 |
| Translation validators/resume | unit tests, no live DeepInfra | high | fake provider interrupted run, numeric/literal/table failure cases | P0 |
| Distill evidence rows | tests | medium | one pack to full distill bundle, all rows evidence-backed | P1 |
| Search index | tests | medium | reindex removes stale postings, invalid FTS syntax fallback | P1 |
| Static site | smoke tests and Pages workflow | medium | generated HTML link/provenance parity | P1 |
| Learned registry | tests | medium | list/show/verify/clear and source taxonomy | P1 |
| FastAPI workspace | partial service/API tests | medium if revived, low if parked | OpenAPI/route contract only if active | P2 |
| Web workspace | build only | low if parked | browser flow only if active | P3 |

Tests too coupled to implementation:

- Tests that assume repo CWD or production fallback into `tests/fixtures`.
- Tests around exact CLI text when JSON contract would be more stable.
- API service tests that rely on seeded fixture progression rather than real state transitions.

Tests that should become parity tests:

- Existing `tests/parity/corpus.yaml` should become the rebuild oracle for CLI commands and artifacts.
- Query JSON-full for core SEC, S-1, HKEX, SSE values.
- Diff JSON and HTML report evidence anchors.
- Pack artifact manifest and section IDs for selected fixtures.

Tests that should become semantic invariants:

- Every non-null value has citation/provenance.
- Derived values cite every component and formula.
- Missing data is `None`/gap/warning, never older fallback without explicit warning.
- Pack section hashes change when source text changes.
- Translation cannot drop numbers, literal tokens, markdown table shape, or end incomplete.

# 8. Reinvention check

External source reviewed on 2026-06-16: EdgarTools official docs and GitHub. The docs state that EdgarTools supports company lookup by ticker/CIK/name, offline bundled reference data, filing access back to 1994, attachment download, clean text/markdown, sections, filing search, form-specific objects, XBRL statements, raw facts querying, multi-period XBRL stitching, standardized statement views, local storage, SEC identity, rate limiting, and retries. Sources:

- https://edgartools.readthedocs.io/en/latest/
- https://edgartools.readthedocs.io/en/latest/guides/finding-companies/
- https://edgartools.readthedocs.io/en/latest/guides/working-with-filing/
- https://edgartools.readthedocs.io/en/latest/guides/financial-data/
- https://edgartools.readthedocs.io/en/latest/xbrl/
- https://edgartools.readthedocs.io/en/latest/resources/sec-compliance/
- https://edgartools.readthedocs.io/en/latest/guides/local-storage/
- https://github.com/dgunning/edgartools

| Area | Classification | Reasoning | Confidence |
| --- | --- | --- | --- |
| Company resolution | WRAP/INVESTIGATE | EdgarTools has mature ticker/CIK/name lookup and bundled reference data. EdgarPack still needs cross-market SEC/HKEX/SSE/private routing and pre-IPO name behavior. | high |
| Filing listing | DELEGATE/WRAP | EdgarTools exposes company filings and filters. EdgarPack needs exact CLI output, cache semantics, and `--last/--after/--before` behavior. | high |
| Filing download | WRAP | EdgarTools can access HTML/text/markdown/attachments. EdgarPack needs deterministic pack artifacts, source hashes, llms, chunks, and section IDs. | high |
| SEC cache/rate limit behavior | INVESTIGATE | EdgarTools has local storage, identity, rate limiting, and retries. Need spike to compare failure semantics, 404 handling, atomic cache, and deterministic offline behavior. | high |
| Section extraction | KEEP OWNED or WRAP carefully | EdgarTools offers `filing.sections()` and markdown, but EdgarPack's section IDs and TOC/cross-ref/S-1 scars are product contracts. | high |
| XBRL facts | WRAP/DELEGATE | EdgarTools raw facts and company facts could replace commodity fetch/parse. EdgarPack's CitedValue and period/citation semantics remain owned. | high |
| Financial statements | WRAP | EdgarTools has standardized statements and multi-period XBRL stitching. EdgarPack needs investor query DSL, LTM formulas, missing-data semantics, and citations. | high |
| Concept normalization | INVESTIGATE/WRAP | EdgarTools standardization may be stronger than EdgarPack maps. Must compare against EdgarPack metric directory and warnings. | medium |
| Form-specific parsing | WRAP for SEC commodity forms, KEEP OWNED for registration pack contract | EdgarTools supports TenK/TenQ/TwentyF/Form4/13F/proxy objects and prospectus data, but EdgarPack's S-1 selected financial and timeline behavior is custom. | medium-high |
| Filing text/markdown | INVESTIGATE | EdgarTools markdown could simplify parse stack, but current pack/diff quality depends on custom cleanup. Requires golden comparison. | high |
| Search | KEEP OWNED for local pack search | EdgarTools has filing search/advanced search, but EdgarPack search anchors into chunks, topics, and local packs. | medium |
| Insider/fund/proxy parsing | DELETE from EdgarPack unless product expands | EdgarTools covers Form 4, 13F, DEF 14A. EdgarPack has no active differentiated surface here. | high |
| HKEX/SSE/CNINFO | KEEP OWNED | EdgarTools is SEC-focused. China/HK adapters are differentiated if product scope includes them. | high |
| Citation/evidence layer | KEEP OWNED | This is EdgarPack's core product, not a commodity library feature. | high |

Should EdgarPack exist at all? Yes, but narrower. EdgarTools appears capable of replacing or wrapping commodity SEC access and XBRL statement plumbing. EdgarPack's reason to exist is the evidence layer: deterministic pack artifacts, citation/calculation contracts, filing-diff reading surfaces, registration filing extraction, local agent handoff, and non-US primary-document adapters. The honest target is "EdgarPack as a wrapper/evidence layer over mature SEC plumbing where parity holds," not "EdgarPack as a full custom EDGAR stack forever." Confidence: medium-high.

# 9. Load-bearing weirdness and risk register

| Location | Why it looks weird | Why it may be load-bearing | Edge case | Coverage | Parity test needed | Severity | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `parse/html_clean.py` font-size-zero logic | Hidden style is not always removed | S-1 real content can sit inside zero-size wrapper | registration wrapper content | direct test | S-1 wrapper fixture full pack | critical | high |
| `parse/sectionize.py` heading rejection | Lots of negative heuristics | TOCs/cross-refs mimic item headings | "See Item 7" and paren citations | tests/docs | false heading corpus | critical | high |
| `parse/s1_headings.py` TOC anchor injection | Adds headings before cleaning | Registration filings may have anchor-only headings | S-1/F-1 sections otherwise missing | tests/current branch | F-1/S-1 fixture with anchor headings | critical | high |
| `query/periods.py` LTM logic | Dense control flow and warnings | Date windows and period alignment are hard | annual-only, YTD, prior YTD, stale facts | high | JSON formula parity | critical | high |
| `tests/conftest.py` autouse LTM harness | Test monkeypatches selection globally | Prevents silent invariant regressions across unrelated tests | LTM value without formula components | high | keep as semantic invariant | high | high |
| `query/s1_financials.py` no-key placeholder source | Emits placeholder rows instead of failing hard | User needs actionable no-key message and no stale fallback | missing `ANTHROPIC_API_KEY` | tests | query JSON no-key parity | high | high |
| `query/financials.py` SEC 404 empty behavior | Treats 404 unlike other errors | New/pre-IPO filers have no companyfacts | companyfacts missing | tests | 404 vs 500 parity | high | high |
| `query/financials.py` China fixture fallback | Production reads `tests/fixtures` path | Enables offline China queries; maybe accidental | local dev without built China packs | docs flag known bad | decide and pin | medium | medium |
| `hk/extract.py` wrapped label merge | PDF text cleanup is ad hoc | HK rows wrap labels before values | MiniMax R&D/OCF | golden xfail/commits | fact extraction parity | high | high |
| `hk/extract.py` drops `matched_label` on serialization | Loses useful provenance | Could be accidental but affects auditability | HK facts debugging | known bad doc | facts.json shape decision | medium | high |
| `sse/client.py` non-atomic PDF cache | Simpler than SEC cache | Might not matter for local usage, but corrupt partial PDFs are possible | interrupted download | backlog only | corrupt PDF cache case | medium | medium |
| `china/translate/validators.py` fail-closed stack | Looks overbuilt | LLM can drop numbers/tables/literals | annual report translation | unit tests | fake provider failure matrix | high | high |
| `diff/text_diff.py` moved and containment passes | Diff algorithm is complex | Avoids false added/removed from reorders and re-splits | risk factor reordering | strong tests/docs | old/new pack pair parity | critical | high |
| `diff/timeline.py` annual path differs from pair diff | Similar feature uses different filtering | Might be historical layering, but annual timeline users may rely on current output | section timeline text | partial | annual timeline golden | medium | medium |
| `china/service.py` seed fixtures default | Demo convenience can masquerade as evidence | Useful for UI demos, dangerous if productized | fabricated Tencent evidence | known bad doc | API revived default-off test | high if revived | high |

# 10. First-principles vNext implications

Non-negotiable domain concepts:

- Primary source identity: CIK/accession/form/date/source URL or China/HK equivalent.
- Durable filing pack with manifest, full text, sections, hashes, and optional chunks.
- Evidence chunk/section/fact IDs.
- `CitedValue` and `DerivedValue` equivalents with source, period, unit, warnings, and formula components.
- Missing/unsafe extraction represented as gap/warning/`None`, not invented values.
- Period selector algebra for `lfy`, `mrq`, `ltm`, offsets, annual/quarterly series, and registration special cases.
- Source adapter boundaries for SEC, HKEX, SSE/CNINFO, translation, FX.
- Deterministic renderers and machine-readable JSON.

Boundaries that seem necessary:

- Acquisition adapters separate from pack writers.
- Pack reader/writer separate from query/diff/search/distill.
- Query domain model separate from CLI renderer.
- Registration filing path separate from ordinary companyfacts path.
- Translation provider separate from validators and cache.
- Parked web/API separate from active CLI package.

Boundaries that seem accidental:

- CLI as all-purpose application service.
- `financials.py` as cross-market orchestration plus source extraction plus output shaping.
- Test fixture paths inside production China lookup.
- API demo state inside service core.
- Multiple registries and concept maps without one typed public schema.

Source adapters that seem needed:

- SEC adapter, possibly wrapping EdgarTools.
- Registration/S-1/F-1 adapter over built packs.
- HKEX annual/prospectus PDF adapter.
- SSE/CNINFO annual/prospectus PDF adapter.
- Translation adapter for Chinese sections.
- FX adapter with explicit source and rate type.

External dependencies to consider:

- EdgarTools for SEC resolution, listing, filing download, XBRL facts/statements, rate limiting, storage.
- Existing optional PDF stack for SSE/HKEX if quality holds.
- SQLite remains reasonable for local search, learned mappings, registry, and translation cache.
- Avoid adding web/API dependencies to core CLI.

Artifact contracts to preserve:

- Pack semantic layout, manifest fields, sections, llms, chunks.
- Query JSON semantics, especially citations/calculations/warnings.
- Diff JSON/HTML evidence anchors and `moved` semantics.
- Distill evidence/gaps contract.
- China facts/translation semantics, but fix known bad provenance with versioning.

Compatibility shims likely needed:

- Read old `manifest.json` and old accession path shapes.
- Preserve deprecated `--cik` or provide clear migration.
- Version query JSON if field names change.
- Read old learned registry or provide migration/export.
- Allow old packs to feed diff/search/distill during transition.

Areas to delete or park:

- FastAPI/Next workspace unless revived.
- Demo seed fixtures as default runtime behavior.
- `insights/` from core vNext.
- VLM asset descriptions from default build.
- Reserved or no-op CLI flags.
- Internal archived plans as sources of truth.

Open questions for Samay appear in section 11.

# 11. Questions for Samay

1. Is the CLI the only active user surface for vNext, with FastAPI/Next explicitly parked?
2. Must old pack artifacts remain readable by vNext, or is a migration command acceptable?
3. Must exact CLI compatibility be preserved, including deprecated `--cik`, output text, and progress messages, or only semantic behavior?
4. Is `json-full` a stable external contract for agents, or can it be versioned and changed?
5. Is EdgarTools acceptable as a core dependency if a spike proves parity for SEC resolution, listing, filings, and XBRL?
6. Are HKEX and SSE/CNINFO active product scope, or should they be isolated as optional adapters?
7. Is the China Lens API/workspace still parked, or should it shape service boundaries now?
8. Does `distill` matter as a first-class product surface or as an experiment over packs?
9. Should learned/self-heal mappings remain in product, or should vNext prefer strict deterministic extraction with explicit user review?
10. Which old outputs are allowed to break: static site HTML, diff HTML, `llms.txt`, learned registry, translation artifacts, or metric directory?

# 12. Appendix

## Files and areas inspected

Current repo inventory was inspected with `rg --files`, `find`, and targeted reads across source, docs, tests, scripts, config, web/API, rebuild docs, parity corpus, and git history. Binary fixtures such as PDFs were inventoried as fixtures; I did not decode every binary byte manually.

Key source areas inspected:

- `edgarpack/cli.py`
- `edgarpack/config.py`, `edgarpack/identity.py`, `edgarpack/__init__.py`
- `edgarpack/sec/client.py`, `cache.py`, `submissions.py`, `tickers.py`, `xbrl.py`, `archives.py`
- `edgarpack/parse/ixbrl_strip.py`, `html_clean.py`, `semantic_html.py`, `md_render.py`, `md_polish.py`, `sectionize.py`, `tokenize.py`, `s1_headings.py`
- `edgarpack/pack/build.py`, `manifest.py`, `chunks.py`, `llms_txt.py`, `doctor.py`, `assets.py`
- `edgarpack/query/models.py`, `financials.py`, `periods.py`, `strict.py`, `citations.py`, `s1_financials.py`, `concepts.py`, `metric_map.py`, `self_heal.py`, `kpi_discover.py`, `kpi_extract.py`, `render.py`, `links.py`
- `edgarpack/diff/text_diff.py`, `section_diff.py`, `timeline.py`, `report_models.py`, `report_builder.py`, `html_report.py`
- `edgarpack/harvest/*`, `edgarpack/index/*`, `edgarpack/insights/*`
- `edgarpack/hk/*`, `edgarpack/sse/*`, `edgarpack/china/*`
- `edgarpack/api/*`, `web/*`
- `edgarpack/distill/*`, `edgarpack/site/*`, `edgarpack/fx/*`

Key docs/config/scripts inspected:

- `AGENTS.md`, `README.md`, `pyproject.toml`, `universe.toml`, `cerebras.toml`
- `docs/ARCHITECTURE.md`, `docs/GETTING_STARTED.md`, `docs/WORKFLOWS.md`, `docs/QUERY.md`, `docs/TESTING.md`, `docs/S1.md`, `docs/DISTILL.md`, `docs/OBSERVATORY.md`, `docs/METRIC_DIRECTORY.md`, `docs/learn/manifest.yml`
- `docs/rebuild/010_PHASE0_BEHAVIOR_CORPUS.md`
- `docs/rebuild/decisions/active_vs_parked_surface.md`
- `docs/rebuild/decisions/deprecation_candidates.md`
- `docs/rebuild/decisions/known_bad_current_behavior.md`
- `docs/rebuild/memos/scar_tissue_seed.md`
- `docs/rebuild/prompts/phase1_assessment_prompt.md`
- `tests/parity/corpus.yaml`
- `.github/workflows/ci.yml`, `.github/workflows/deploy-site.yml`
- `scripts/symphony_quality_gate.sh`, `daily-refresh.sh`, `clean.sh`, `refresh_fx.py`, `generate_metric_directory.py`, `benchmark_efficiency.py`

Tests inspected by inventory and targeted reads:

- 132 `test_*.py` files under `tests/`
- `tests/conftest.py`
- China golden harness at `tests/eval/china_golden.yaml`
- Fixture directories including `tests/fixtures/china_packs`, S-1/Cerebras fixtures, malformed table fixtures, parser fixtures

## Commands discovered

CLI commands discovered in `edgarpack/cli.py`:

`home`, `build`, `doctor`, `distill run`, `distill check`, `company-llms`, `list`, `cache`, `site`, `api`, `identify`, `query`, `f1`, `s1`, `harvest`, `diff`, `timeline`, `search`, `index`, `comps`, `learned list`, `learned show`, `learned verify`, `learned clear`, `which`, `compare`, `build-sse`, `translate-sse`.

Quality and operational commands discovered:

- `scripts/symphony_quality_gate.sh`
- `scripts/daily-refresh.sh`
- `scripts/clean.sh`
- `scripts/refresh_fx.py`
- `scripts/generate_metric_directory.py`
- GitHub Actions CI gate and Pages showcase deploy.

## Git history inspected

Recent history shows active work concentrated in registration/F-1 parsing, S-1 financial extraction, diff moved semantics, strict/LTM/self-heal hardening, HKEX table misattribution fixes, SSE translation recovery, SEC build fetching, and repository hygiene. This strongly supports treating the complex paths as recent scar tissue rather than dead code. Confidence: high.

Representative commits observed:

- `aa1d544 Tighten registration review findings`
- `f015b9f Add registration query shortcuts`
- `f63fde4 Upgrade F-1 registration parsing`
- `f73972e fix(query): close the silent-degrade holes in LTM, strict, and self-heal`
- `8a3bb61 fix(hk): stop column-shift misattribution in plain table rows`
- `28c12e5 feat(diff): demote verbatim re-split paragraphs to moved via containment`
- `a75d7c7 fix: harden SSE translation recovery`
- `4bf95c7 fix: harden SEC build fetching`

## Assumptions

- The current branch reflects intentional work and should be assessed as current behavior, not ignored in favor of `main`.
- Existing rebuild docs are useful evidence, but current code wins when they differ.
- Public artifacts and CLI outputs matter more than internal module boundaries.
- Binary PDFs are primary fixtures, but their semantic expected values are represented through facts/golden tests.

## Uncertainties

- Whether FastAPI/Next should remain parked.
- Whether exact artifact backward compatibility is mandatory.
- Whether EdgarTools can preserve EdgarPack's failure semantics and citation needs without expensive wrappers.
- Whether HKEX/SSE lanes are core vNext scope or optional product modules.
- Whether learned/self-heal should stay active or be replaced by explicit review.
- Whether web/demo seed fixtures have any current user.

## Suggested next investigation steps

These are investigation steps, not implementation tasks:

1. Run the existing quality gate and China golden lanes on the current branch to confirm the baseline before any rebuild discussion.
2. Execute the parity corpus commands in `tests/parity/corpus.yaml` and capture current outputs as immutable rebuild fixtures.
3. Spike EdgarTools only against read-only parity questions: same company resolution, filing selection, markdown/section output, XBRL facts, and SEC error/cache semantics.
4. Decide active versus parked surfaces with Samay before designing vNext boundaries.
5. Freeze the artifact compatibility policy before deleting or migrating any pack/query/diff/distill shapes.
