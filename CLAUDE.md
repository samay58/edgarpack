# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

EdgarPack turns SEC (and HKEX / China A-share) filings into clean, section-addressable markdown packs, then runs cited financial queries, KPI discovery, and evidence-linked filing diffs on top of them. The non-negotiable product promise: **every returned value or changed paragraph carries its filing provenance.** Missing facts return `None`, never a guess.

## Commands

Run from the repo with `uv run` (the docs show bare `edgarpack` for readability, but repo-local work uses `uv run edgarpack ...`). For ad-hoc Python, use the project venv (`.venv/bin/python`), not system python.

```bash
# Lint + format (ruff: select E,F,I,N,W,UP; line-length 100) and types (mypy strict)
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy edgarpack

# Tests: offline lane (the default; no network)
uv run --extra dev --extra china --extra sse pytest -q
uv run --extra dev pytest tests/test_periods.py -q          # single file
uv run --extra dev pytest tests/test_periods.py::test_ltm -q # single test

# Gated lanes (opt-in)
uv run --extra dev pytest --run-slow          # @pytest.mark.slow (e.g. determinism rebuild)
EDGARPACK_USER_AGENT="Name email@example.com" \
  uv run --extra dev pytest --run-live-sec     # @pytest.mark.live_sec (hits real SEC)

# The repo quality gate (ruff + pytest; web build with SYMPHONY_WEB=1)
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache scripts/symphony_quality_gate.sh

# Wipe regenerable clutter (caches, dist, stray test dirs); --corpus also clears packs/ + site/
scripts/clean.sh

# Web (Next.js app under web/, package name rogo-china-lens-web)
npm --prefix web run lint
npm --prefix web run build
```

`EDGARPACK_USER_AGENT` (format `Name email@example.com`) is required for any live SEC call; the first network call fails with an actionable error if it is unset. SEC requests are paced (default 5 req/s) and cached on disk under `EDGARPACK_CACHE_DIR` (default `~/.edgarpack/cache`). For China A-share / HKEX work, add `--extra china --extra sse`.

## Architecture

The CLI (`edgarpack/cli.py`, plain `argparse`, no Click/Typer) dispatches every subcommand. There are two load-bearing pipelines, joined by a shared identity resolver and citation model.

**Identity routing** (`edgarpack/identity.py` + `universe.toml`): the user's positional arg (ticker / CIK / company name) resolves to a `ResolvedCompany` tagged `sec | hkex | private`. This tag decides which data path runs. Ticker/name resolution itself lives in `edgarpack/sec/tickers.py`: forgiving input, ambiguity raises a typed error listing candidates, unknown input returns a fuzzy "did you mean".

**Build pipeline** (`build` → a pack on disk). `edgarpack/sec/` fetches over a stdlib HTTP client with token-bucket rate limiting + retry (`client.py`) and a SHA256-keyed atomic disk cache (`cache.py`). `edgarpack/parse/` then runs **six steps in strict order**: `ixbrl_strip → html_clean → semantic_html → md_render → md_polish → sectionize`. `edgarpack/pack/build.py` is the 13-step orchestrator that writes `filing.full.md`, `sections/*.md`, `manifest.json` (hashes + offsets), `llms.txt`, and optional `chunks.ndjson` / `xbrl.json`. S-1 filers with no native headings get synthetic headings injected before sectionize (`parse/s1_headings.py`).

**Query pipeline** (`query`, `comps`, `compare`, `which` → cited values, no build needed for SEC). `edgarpack/query/financials.py` is the orchestrator. `periods.py` is the subtlest module in the codebase; period vocabulary (`ltm`, `lfy`, `mrq`, `mrp`, `annual:N`, `quarterly:N`), LTM math, anchor selection, fiscal-year matching, staleness rejection. Most financial-reasoning bugs live here. The single-period table renderer lives in `query/render.py`; the shared arithmetic-formula evaluator in `query/formula.py`. Metric names resolve through `layer_zero.py` / `metric_map.py`; unknown metrics hit the **self-heal** path (`self_heal.py`) which fuzzy/LLM-resolves a concept and persists it in the `learned_concepts` registry (`learned_registry.py`, inspect via `edgarpack learned list`). `--strict` rejects any non-`hardcoded` concept source (`strict.py`).

**Pre-IPO / S-1 path**: S-1 filers usually have no SEC companyfacts. Query reads the built registration pack instead and lazily extracts a snapshot (`query/s1_financials.py`), tagging values `s1_snapshot` / `s1_pro_forma`.

**China Lens** is a parallel sub-product, not a bolt-on. HKEX (`edgarpack/hk/`) extraction runs at pack time and populates `facts.json`, which the query layer reads instead of SEC companyfacts when identity routes a filer to HKEX. SSE / A-share (`edgarpack/sse/`, `edgarpack/china/`) build from CNINFO PDFs via `build-sse`, detect CSRC sections by Chinese numerals, and optionally run a zh→en translation pipeline (`--translate`, needs `EDGARPACK_DEEPINFRA_KEY`). FX normalization uses `data/fx_rates.csv`.

**Observatory** (`edgarpack/diff/`, `index/`, `insights/`, `harvest/`): paragraph-level language diffs between two local packs with mechanical-change suppression (TOC, date rollovers, cross-references, financial tables), static HTML reports (`diff/html_report.py`), S-1 registration timelines (`diff/timeline.py`), bulk harvest from `universe.toml` into a SQLite registry (`harvest/`), and an FTS5 search index (`index/`).

**Distill** (`edgarpack/distill/`, `edgarpack distill run|check`): compresses one existing pack into a small cited surface (`index.md`, `findings.csv`, `metrics.csv`, `evidence.jsonl`, `gaps.csv`, ...). Rule: rows need evidence; unsupported claims go to `gaps.csv`, not into confident prose. v1 uses existing packs only; it does not fetch.

### Citation model (`edgarpack/query/models.py`)

`CitedValue` = a direct SEC fact with full provenance (company, CIK, accession, form, filing date, concept tag, period). `DerivedValue` = a computed metric carrying the full map of its component `CitedValue`s. **Hard contract**: a non-null `ltm` value must carry `{mrp, lfy, mrp_prior}` component citations; a missing component flips the result to `None` + an `ltm_incomputable` diagnostic, never an uncited scalar.

## Invariants to respect when changing code

- **Determinism is a guarantee.** Rebuilds must produce identical bytes (there is a `--run-slow` determinism test). Any change to HTML cleaning, section detection, or chunking will usually require regenerating fixtures and bumping `PARSER_VERSION` in `edgarpack/config.py` (`SCHEMA_VERSION` for pack-layout changes). Downstream caches key off these versions.
- **No silent imputation.** Network/HTTP failures on the read path raise (`XBRLFetchError`) and surface as a per-metric diagnostic (`layer_a_fetch_error`); a real SEC 404 ("no XBRL") maps to `{}` and stays diagnostic-free. Don't collapse those two cases into an indistinguishable N/A.
- **Citations live in the data model**, not in formatting. Don't add a value path that returns a bare number.
- `diff/section_diff.py` and `diff/timeline.py` share `_compute_section_intensity()` (word-weighted, not paragraph-count). Keep them in sync.
- **Output paths** use `DEFAULT_PACKS_DIR` / `DEFAULT_SITE_DIR` / `DEFAULT_REPORTS_DIR` in `edgarpack/config.py`. `universe.toml` and `data/` are root-pinned (read CWD- and package-relative); do not move them.

## Workflow

Branch off `main`, keep diffs small, run the gate, commit, push. No mandatory tracker; task tracking is `docs/BACKLOG.md` or commit messages. The repo root is allowlisted by `tests/test_repo_layout.py`, so a new tracked top-level entry must be added there on purpose. Full conventions in `AGENTS.md`.

## Where to read more

- `docs/ARCHITECTURE.md`: the stage-by-stage "how it works" with the parse-pipeline and query examples.
- `docs/learn/README.md` + trails 0-8: code walk-throughs that trace a concrete command through the actual modules; `docs/learn/ref/` is the per-module dictionary.
- `docs/QUERY.md`: full metric/period/citation/JSON reference. `docs/OBSERVATORY.md`: diff + timeline. Also `docs/DISTILL.md`, `docs/TESTING.md` (offline vs live lanes), `docs/BENCHMARKS.md`.
