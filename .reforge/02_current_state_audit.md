# Current State Audit

## P0

No P0 found in the validated CLI/core path. The approved full pytest lane passed (`1301 passed, 50 skipped, 12 xfailed`) and ruff passed.

## P1 Findings

### P1: Product boundary is split between the actual CLI product and parked app surfaces

Evidence:

- README exposes both mature CLI commands and a China Lens API command (`README.md:153-186`).
- The implementation tracker says the CLI is primary and Evidence Explorer / FastAPI is parked (`docs/china-lens/IMPLEMENTATION_TRACKER.md:5-7`).
- The Bead trim spec says China Lens and observatory web are parked experiments, not live surfaces (`docs/superpowers/specs/2026-04-20-bead-backlog-trim-design.md:3-5`, `docs/superpowers/specs/2026-04-20-bead-backlog-trim-design.md:20-32`).
- `web/` and `edgarpack/api/` remain in tree with runnable clients/routes.

Impact:

Future work can accidentally optimize the parked web/API instead of the validated CLI. That conflicts with the current product truth and increases review surface.

Validation idea:

Run `edgarpack --help`, `pytest -q`, and a docs scan for "parked" before accepting new API/web work. New web/API work should require an explicit "China Lens is active again" decision.

### P1: Demo evidence paths contain invented-looking facts outside fixture governance

Evidence:

- `AGENTS.md:14-15` says use fixtures and every generated finding must point to evidence chunk IDs.
- `web/lib/sample-data.ts:36-146` embeds demo claims, citation labels, and evidence text directly in the web client.
- `edgarpack/china/service.py:86-189` seeds mock CNINFO URLs and hardcoded chunks by default.
- Golden-fixture docs require hand verification and forbid auto-regeneration from CLI output (`tests/eval/README.md:26-52`).

Impact:

If the web/API surface is revived, seeded/demo findings can be mistaken for source-backed behavior. The architecture must route examples through committed fixtures or clearly mark them as non-production.

Validation idea:

Add a test or lint rule in build mode that production/demo-off code paths cannot return `demoPack` or mock CNINFO URLs, and that all supported findings cite chunks present in the selected pack doc set.

### P1: Strict typing is configured but not a usable gate

Evidence:

- `pyproject.toml:64-66` sets mypy strict.
- `./.venv/bin/mypy .` currently fails with `1293 errors in 136 files`.
- The implementation tracker lists strict mypy baseline restoration as parked (`docs/china-lens/IMPLEMENTATION_TRACKER.md:121-123`).

Impact:

Future agents may treat mypy as a quality gate and burn time on a non-current baseline, or ignore it entirely despite the strict config.

Validation idea:

Choose either a scoped mypy gate for core modules or explicitly document mypy as non-gating until a dedicated typing pass lands. Re-run `./.venv/bin/mypy <chosen scope>`.

## P2 Findings

### P2: CLI commands are mostly literal, but the command grammar is not fully ergonomic for humans or agents

Evidence:

- Top-level help exposes 19 commands in one flat list: `build`, `doctor`, `company-llms`, `list`, `cache`, `site`, `api`, `query`, `harvest`, `diff`, `timeline`, `search`, `index`, `comps`, `learned`, `which`, `compare`, `build-sse`, `translate-sse`.
- Core commands such as `build`, `query`, `diff`, `timeline`, `search`, `index`, `cache`, and `doctor` are more literal than the insider commands, but they are evidence for vNext rather than names to preserve by default.
- `which` is well-described in help, but the name is not discoverable unless a user already knows the intended question: "which qualitative / MD&A KPIs does this company disclose?"
- `comps` and `compare` overlap semantically. `comps` is finance shorthand for peer comparable metrics; `compare` is a broader side-by-side comparison. Humans and agents can reasonably choose the wrong one.
- `learned` exposes an implementation concept ("self-heal learned_concepts registry") rather than a user task like managing metric mappings.
- `company-llms`, `build-sse`, and `translate-sse` are literal, but they create a mixed taxonomy: some commands are task-first (`build`, `query`), some artifact-first (`company-llms`), and some source-specific (`build-sse`).
- `api` is generic even though it starts the parked China Lens FastAPI surface.

Impact:

The live CLI is usable, but the command surface makes the intended workflow harder to infer from `edgarpack --help`. This matters for both humans and agents because the fastest path is not just "know a command exists"; it is knowing the right sequence: inspect filings, build packs, query cited metrics, discover qualitative KPIs, compare, diff/timeline, then index/search.

Validation idea:

For the approved clean rewrite, start with a new evidence-verb grammar instead of aliasing the old surface first: `filings`, `pack`, `cite`, and `audit`, followed later by `compare` and `trace`. Old-command aliases should wait until the new grammar is stable and explicitly approved.

### P2: Core behavior is healthy, but several modules are too broad for repeated change

Evidence:

- `edgarpack/cli.py` is 3005 lines.
- `edgarpack/query/financials.py`, `query/periods.py`, `query/kpi_extract.py`, and `query/kpi_discover.py` are large, load-bearing modules.
- `docs/learn/manifest.yml:141-147` calls `periods.py` and `financials.py` subtle load-bearing modules.

Impact:

Broad files slow review and increase the chance that a small CLI change touches unrelated behavior. The original assessment treated this as a refactor smell rather than a rewrite trigger; the user's later clean-rewrite decision supersedes that conservative call.

Validation idea:

For vNext, require failing `tests/vnext` coverage first, preserve the old implementation as parity evidence, and do not port old broad orchestrators unless a test proves the behavior is needed.

### P2: Stale backlog conflicts with current shipped state

Evidence:

- `docs/BACKLOG.md:7-15` says SSE is parked on `feat/sse-prospectus`.
- README and tracker both show SSE build/translate as live (`README.md:178-181`, `docs/china-lens/IMPLEMENTATION_TRACKER.md:27-41`).
- Code contains `build_sse_pack` on main (`edgarpack/pack/build.py:329-460`).

Impact:

Future agents may check out stale branches or misclassify live SSE support as parked.

Validation idea:

In build mode, update `docs/BACKLOG.md` only after verifying `edgarpack build-sse --help`, the SSE tests, and the current branch history.

### P2: HKEX annual-report support is explicitly unresolved

Evidence:

- `bd show edgarpack-sfi` says current HK pack pipeline is built around IPO prospectuses and does not support mature HKEX annual-report shape.
- HKEX fixtures are MiniMax/Zhipu IPO prospectuses (`tests/fixtures/china_packs/README.md:7-9`).
- HK adapter uses section-heading mapping over PDF text (`edgarpack/hk/adapter.py:57-145`).

Impact:

Cross-market comparisons are validated for the committed fixture shape, not for all HKEX filers named in the universe.

Validation idea:

Add Tencent/Meituan annual-report fixtures and golden entries before claiming annual-report support.

### P2: Section-level pack targeting has a known filer-dependent limitation

Evidence:

- Benchmarks show NVDA Item 1A extracts cleanly, but AAPL and TSLA Item 1A land as short stubs (`docs/BENCHMARKS.md:90-102`).
- The limitation section says not to promise reliable section targeting until incorporation-by-reference is handled (`docs/BENCHMARKS.md:118-127`).

Impact:

Full filing compression is validated; per-section research workflows need guardrails.

Validation idea:

Use fixture packs for incorporation-by-reference filers and assert section token/length thresholds for known sections before marketing or relying on section-only LLM prompts.

## P3 Findings

### P3: Open ready beads are narrow UX/coverage follow-ups

Evidence:

- `bd ready` shows `edgarpack-sfi` and `edgarpack-t2h`.
- `edgarpack-t2h` says a known discovered-KPI slug with no matching period rows renders with a label but no N/A marker.

Impact:

These are not rebuild drivers. They are targeted follow-ups.

Validation idea:

Add one CLI regression test per bead and run the specific test plus `pytest -q`.
