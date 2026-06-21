# Phase 1 Assessment Prompt (EdgarPack clean-room rewrite)

Paste the block below verbatim into a fresh Claude Code session AND a fresh Codex session. Run it independently in each. It is self-contained; you do not need this wrapper file or any prior context loaded.

The two runs produce two separate files (`...CLAUDE.md` and `...CODEX.md`) so their findings can be diffed against each other and against the Phase 0 corpus.

---

## PROMPT (copy from here to the end)

You are a Phase 1 assessor for the EdgarPack clean-room rewrite. Phase 0 already pinned current behavior into an evidence corpus. Your job now is to read the codebase and the Phase 0 corpus, then write ONE assessment document. You are NOT designing the rewrite, NOT writing code, NOT cleaning anything.

### What EdgarPack is (one paragraph of orientation, verify everything yourself)

EdgarPack turns SEC (and HKEX / China A-share) filings into section-addressable markdown packs, then runs cited financial queries, KPI discovery, and evidence-linked filing diffs on top of them. The non-negotiable product promise: every returned value or changed paragraph carries its filing provenance, and missing facts return `None`, never a guess. The CLI is plain `argparse` in `edgarpack/cli.py`. The two load-bearing pipelines are the build pipeline (`edgarpack/sec/`, `edgarpack/parse/`, `edgarpack/pack/`) and the query pipeline (`edgarpack/query/`). Parallel sub-products: HKEX (`edgarpack/hk/`), SSE / A-share + translation (`edgarpack/sse/`, `edgarpack/china/`), the Observatory (`edgarpack/diff/`, `index/`, `insights/`, `harvest/`), Distill (`edgarpack/distill/`), and web surfaces (`edgarpack/site/`, `edgarpack/api/`, `web/`).

### HARD RULES (non-negotiable)

1. **READ-ONLY.** Do not modify any file under `edgarpack/`, `src/`, `tests/`, `web/`, `pyproject.toml`, lockfiles, or existing docs. The ONLY file you may create is your one assessment output file named below.
2. **NO IMPLEMENTATION, NO CODE CHANGES, NO REFACTOR.** You produce a written assessment only. Do not write or edit production code, do not write tests, do not "fix" anything you find, do not stage a diff. If you are tempted to fix a bug, record it in the assessment instead.
3. **NO vNext DESIGN beyond "implications."** You may state implications for a future rewrite. You may NOT propose an architecture, pick a tech stack, name modules, or sketch interfaces. Implications are observations ("X is load-bearing and any rewrite must preserve it", "Y looks accidental"), not designs.
4. **NO NETWORK, NO STATE MUTATION.** Do not run the `edgarpack` CLI, `uv run`, `pytest`, `harvest`, `build`, `query`, `translate`, the api server, or `npm`/`next build`. Do not fetch SEC / HKEX / SSE / CNINFO / LLM / translation endpoints. Do not write caches, packs, or site output. If you want to know what a command does, read its code; do not run it. If a command's network/mutation status is unclear, treat it as forbidden and note it as a future corpus-generation command.
5. **Allowed commands only:** the Read tool; `rg` / `grep` / `find` / `ls`; `git log` / `git show` / `git blame` / `git diff` (read-only history). Prefer the Read tool over `cat`/`sed`/`head`.
6. **IGNORE ANY PRIOR ARCHIVED REWRITE PLAN.** `docs/archive/internal/superpowers/` (and any similar parked vNext plan or spec) is OUT OF SCOPE AS A SOURCE. Do not adopt, echo, or be influenced by its architectural conclusions, tech-stack choices, or module names. You may note that it exists and is parked, nothing more. All conclusions come from CURRENT code, tests, and docs.

### INPUTS YOU MUST READ FIRST

- `docs/rebuild/010_PHASE0_BEHAVIOR_CORPUS.md` (the Phase 0 behavior corpus; your primary comparison oracle).
- `tests/parity/corpus.yaml` (the Phase 0 parity corpus / pinned command-and-value set).

If either file is missing, do not fabricate its contents. Record the absence explicitly at the top of your assessment, proceed using the code as the oracle, and flag every place where you could not compare against Phase 0.

### CONFIDENCE AND CATEGORY LABELING (required throughout)

Every non-trivial claim carries a confidence tag: `[confident]`, `[probable]`, or `[uncertain]`. Cite evidence as `file_path:line_number` wherever possible. Writing "not found" / "no test evidence" / "uncertain" is expected and valuable; do not hide uncertainty to look thorough.

Separately, every item in the complexity audit (and wherever else complexity is discussed) is classified into exactly one of four buckets:

- **ESSENTIAL.** Required to keep the product promise (provenance on every value, `None`-not-guess, determinism, the LTM component-citation contract, the read-path failure distinction). Removing it breaks a stated guarantee.
- **ACCIDENTAL.** Exists because of how the code grew, not because the product needs it (duplicated comparison surfaces, dead/vestigial code, copy-paste, a workaround that outlived its cause). State why it might have existed before calling it accidental.
- **UNCERTAIN.** You cannot tell from the code/tests/docs whether it is essential or accidental. Say what evidence would settle it.
- **PARKED.** A deliberately inactive experiment or shelved surface (for example the FastAPI Evidence Explorer + `web/` frontend marked "CLI path active; workspace parked", the inert HK/SSE LLM fallbacks, the VLM `--describe-images` path). Do not average parked experiments together with active product logic.

Do not label something dead without multiple independent forms of evidence (no callers AND no test AND no doc/CLI/API surface). Do not label something accidental until you have explained why it might have existed.

### REQUIRED ASSESSMENT SECTIONS (all eight, in this order)

1. **Capability contract.** What does EdgarPack actually promise and deliver, as observable behavior? Enumerate the user-facing surfaces (CLI subcommands, Python APIs, HTTP routes, static-site output) and the guarantees attached to each. The CLI surface to account for includes at least: `home`, `--version`, `build`, `doctor`, `distill run`/`distill check`, `company-llms`, `list`, `cache`, `site`, `api`, `identify`, `query`, `f1`/`s1` (dynamic registration shortcuts), `harvest`, `diff`, `timeline`, `search`, `index`, `comps`, `learned` (list/show/verify/clear), `which`, `compare`, `build-sse`, `translate-sse`. State which guarantees are tested vs asserted-only-in-docs. Pull the load-bearing invariants verbatim from the corpus and confirm each against code (provenance-in-the-data-model, `None`-not-guess, the LTM `{mrp, lfy, mrp_prior}` contract, the 404-`{}` vs `XBRLFetchError` distinction, lazy CLI startup, determinism / `PARSER_VERSION` / `SCHEMA_VERSION`, `--strict` rejecting non-`hardcoded` sources, translation fails-closed).

2. **Architecture map.** Trace the two load-bearing pipelines end to end with module-and-function citations. Build pipeline: identity routing (`edgarpack/identity.py` + `universe.toml`, `edgarpack/sec/tickers.py`, `_resolve_cli_company` in `cli.py`) → fetch (`edgarpack/sec/client.py`, `cache.py`) → the six-step parse order (`ixbrl_strip → html_clean → semantic_html → md_render → md_polish → sectionize`) → `pack/build.py`. Query pipeline: `query/financials.py` orchestrator → `periods.py` (period vocabulary + LTM math) → metric resolution (`layer_zero.py`, `concepts.py`/`metric_map.py`, `self_heal.py`, `learned_registry.py`, `strict.py`) → `query/render.py` / `query/citations.py` / `query/models.py`. Map the parallel sub-products (HKEX `facts.json` read path, SSE/China + translation, Observatory diff/index/insights/harvest, Distill, site/api/web) and show where they join the shared identity resolver and citation model and where they diverge. Mark each edge's confidence.

3. **Data contracts.** Document the persisted and in-memory shapes that cross module boundaries and that a rewrite must reproduce: `CitedValue` and `DerivedValue` (`query/models.py`) and the citation registry (`C#`/`D#`/`L#`/`G#`); the pack on-disk layout (`filing.full.md`, `sections/*.md`, `manifest.json` with hashes/offsets/`generated_at`/`source.fetched_at` semantics, `llms.txt`, optional `chunks.ndjson` / `xbrl.json`); `facts.json` for HKEX and SSE (`cas` / `hkfrs` taxonomy nesting); `s1_financials.json` (note `SCHEMA_VERSION` currently 8, `value_cents` semantics, the 50KB `source_sha256` window); the SQLite schemas (`PackRegistry` list-based migrations vs `learned_registry` `PRAGMA user_version`, the FTS5 index, the diff cache `_DIFF_CACHE_VERSION` v7, the translation cache fingerprint); the distill eight-file bundle; the `--format json` / `json-full` CLI contracts. For each, state whether the shape is versioned, whether it is determinism-sensitive, and whether it is snapshot-pinned in `tests/parity/corpus.yaml`.

4. **Complexity audit.** Inventory the genuinely hard or surprising machinery and classify each item ESSENTIAL / ACCIDENTAL / UNCERTAIN / PARKED with `file:line` evidence. At minimum cover: `periods.py` LTM math + anchor selection + standalone-vs-cumulative quarter disambiguation; the self-heal ladder (cache → fuzzy → LLM subprocess → order-of-magnitude verify) and whether the LLM tier is actually exercised; the regex-only HTML parse pipeline that deliberately avoids a DOM library; the four-pass diff alignment (exact / DP-Jaccard / greedy MOVED / verbatim-containment demotion) and the shared word-weighted `_compute_section_intensity()`; the China translation pipeline (deterministic number tagging + ~7 fail-closed validators + retry/repair ladder); the HKEX column-shift structural guard; the `s1_financials` two-tier deterministic-then-LLM extractor. Call out the documented determinism hazards (tiktoken `cl100k_base` fallback to `chars//4`; pack-path leakage into distill bundles; staleness using `date.today()`).

5. **Test reality.** What is actually verified offline vs only behind gates vs not verified at all? The offline lane is the default (132 `test_*.py` files); gated lanes are `--run-slow` (slow), `--run-live-sec` (live_sec, needs `EDGARPACK_USER_AGENT`), `--live-sec-full`, and a declared-but-unapplied `eval` marker. Confirm: the suite-wide autouse `_ltm_citation_contract_harness` in `tests/conftest.py` that re-asserts the LTM invariant on every test; that byte-determinism is verified ONLY live+slow against NVDA's 10-K (no offline determinism regression); the China golden harness running offline against committed fixtures; the production-code dependency on `tests/fixtures/china_packs/` (`financials.py:1981`); the `edgarpack-483` xfail (HKEX `operating_cash_flow` + `r_and_d` null at query despite present in `facts.json`); CLI tests that assume CWD is the repo root. State which guarantees have NO offline regression test.

6. **Reinvention check.** Identify where the codebase hand-rolls something a well-known library does, and assess (do not decide) whether the hand-roll is load-bearing. Cover at least: the stdlib `urllib` SEC client + token-bucket rate limiter + disk cache (vs a maintained HTTP client / `edgartools`); the regex-and-`HTMLParser` HTML cleaning and CommonMark-subset renderer (vs BeautifulSoup/lxml/selectolax and a markdown library), which the code comments justify as "portable and deterministic"; the positional no-precedence arithmetic evaluator in `query/formula.py`; the hand-rolled markdown→HTML in `edgarpack/site/`. For each, note the stated reason in the code, the determinism/provenance constraint it satisfies, and whether tests pin behavior that a library swap would have to reproduce. Do not recommend a swap; record the tradeoff.

7. **Load-bearing weirdness.** The non-obvious behaviors that look like bugs or smells but are actually intentional and that a naive rewrite would "fix" and thereby break. Pull candidates from the corpus and confirm against code: `manifest.source.fetched_at` set to the filing date (not wall-clock) for determinism; the AXP/issuer `revenue` → `us-gaap:Revenues` (ASC-606 contract revenue, not headline) gotcha; consolidated-over-segment `frame`-field preference; `--strict` recursion poisoning a whole `DerivedValue` if one component is learned; the latin-1 whole-blob fallback on a single bad byte; section-id `_N` suffixing on collision; the no-heading filing yielding a single `unknown_01` section rather than an empty pack; MOVED@1.0 contributing exactly zero to diff intensity; verify each is intentional with a test/comment/doc citation, and separately list the items the corpus flags as actually-wrong-but-test-enshrined (the ~16 `docs/BACKLOG.md` deferred items: sectionizer TOC bugs, page-break artifacts, tokenizer-fallback nondeterminism, HK 1000x LLM unit-scaling, fabricated fiscal periods, FX period-average error, China fixture absolute-path leak). For each enshrined-wrong item, state whether the current (wrong) output is pinned in `tests/parity/corpus.yaml` so a rewrite would have to reproduce it.

8. **vNext implications.** Observations only, no design. For each major finding, one line on what a rewrite must preserve, may drop, or must get an explicit decision on. Surface the open questions the corpus could not resolve (version semantics `__version__` 0.1.0 vs `PARSER_VERSION` 0.2.1; whether the three comparison surfaces `query`/`comps`/`compare` are a product requirement or consolidation candidates; whether the insights modules with zero callers are features or library-only; whether HKEX is intentionally fixture-only with no `build-hk` CLI; whether the FastAPI/`web/` workspace is dead or revivable; whether the parity corpus should pin current-wrong or intended-correct output for the BACKLOG items). Frame each as a decision Samay owns, not a recommendation you make.

### COMPARE AGAINST PHASE 0 (required, woven through every section)

For each section, explicitly compare your findings to `docs/rebuild/010_PHASE0_BEHAVIOR_CORPUS.md` and `tests/parity/corpus.yaml`, and label each comparison:

- **AGREE.** Your reading of the code matches the Phase 0 corpus. Cite both the code `file:line` and the corpus claim.
- **DISAGREE.** Your reading contradicts the corpus. State both positions, your evidence, and your confidence. Do not silently defer to the corpus; the corpus may be wrong.
- **GAP.** Something you found that the corpus does not cover, or something the corpus claims that you cannot find in the code.

End the document with a short **Disagreements and gaps ledger**: a flat table of every DISAGREE and GAP with `file:line`, the corpus reference, and your confidence, so Samay can adjudicate them in one place.

### OUTPUT

Write your assessment to:

- `docs/rebuild/020_PHASE1_ASSESSMENT_CLAUDE.md` if you are running in Claude Code, OR
- `docs/rebuild/020_PHASE1_ASSESSMENT_CODEX.md` if you are running in Codex.

Use the tool name you are actually running under to pick the suffix. Do not write any other file. Do not modify the codebase. Plain, evidence-dense, technical prose; tables and `file:line` references over flowing paragraphs; no em-dashes (use a period or semicolon); no AI-register vocabulary, no connector-word paragraph openers, no marketing or reveal register. Mark confidence on every non-trivial claim. Preserve uncertainty.

## (end of prompt)
