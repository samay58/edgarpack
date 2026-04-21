# EdgarPack Backlog

Project-local backlog. Items moved here from phoenix `tasks.md` on 2026-04-21 during the bloat reduction pass, per the rule: project sub-tasks live in the project, not in the global task pile.

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
