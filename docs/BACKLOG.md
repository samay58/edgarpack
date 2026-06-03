# EdgarPack Backlog

Project-local backlog. Items moved here from phoenix `tasks.md` on 2026-04-21 during the bloat reduction pass, per the rule: project sub-tasks live in the project, not in the global task pile.

This file is the task tracker (beads was retired 2026-06-02). Keep it lightweight: add genuine outstanding work, delete items when shipped.

---

## SSE Prospectus Pipeline (Parked)

**Parked**: 2026-04-10 during code scrub to keep main clean.

In-progress China/foreign filings feature on branch `feat/sse-prospectus`. Adds `build-sse` + `translate-sse` CLI subcommands, `edgarpack/sse/` module, and `edgarpack/china/translate/` pipeline (deepinfra, glossary, preprocess, validators, router, cache, numbers) for Chinese IPO prospectus ingestion with zh->en translation. 1195+ insertions across 11 files.

Resume with: `cd ~/Projects/active/edgarpack && git checkout feat/sse-prospectus`.

Includes pilot work on Unitree Robotics IPO deep-dive at `data/unitree-ipo-deep-dive.md`.

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

## Known query bugs (P1)

Carried over from project notes / the retired beads backlog. Symptoms are confirmed; fix directions are a starting point, not verified.

1. **Per-share LTM sums ratios incorrectly.** For per-share metrics the LTM path adds the three components (mrp + lfy - mrp_prior) as if they were flows. Ratios are not additive over a trailing window, so the per-share LTM value is wrong. Likely fix: compute LTM on the underlying numerator and denominator, then divide.
2. **Annual-only filer LTM-1 picks TOC stubs.** For filers with no 10-Q, the `ltm-1` anchor selection can land on a table-only/stub fact instead of a real value. Likely fix: reject stub/zero-content facts during `ltm-1` anchor search.
3. **December fiscal-year Q4 early-return.** For Dec-FY filers the standalone-Q4 path returns early before computing the value. Likely fix: remove the early return so Q4 derives as annual minus Q1-Q3.

---

## Deferred cli.py decomposition (from the 2026-06-02 tech-debt pass)

The single-period query renderer was already extracted to `query/render.py`. The remaining "cli.py is wiring, not logic" moves, each a self-contained, test-covered commit when wanted:

- `_cmd_translate_sse` (~400 lines) into `china/translate/pipeline.py` (covered by `tests/test_translate_sse_artifacts.py`).
- `_render_registration_timeline` into `diff/timeline.py` (covered by `tests/test_cli_registration_timeline_render.py`).
- The `which` render cluster (~640 lines) into `query/kpi_render.py`.
- Period-selector regex centralization in `query/periods.py` (medium risk, lower payoff).
