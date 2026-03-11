# Codex Prompt: Citation Deep Linking + CLI Audit UX Spec

You are working in the `edgarpack` repo. I do not want a generic brainstorm. I want a thoughtful, implementation-ready spec for improving citation provenance and CLI audit UX in the existing query interface.

## Context

EdgarPack already has a working citation system:

- `CitedValue` carries filing provenance and multiple deep-link types.
- `DerivedValue` carries component citations for derived metrics and LTM-style periods.
- The CLI query/comps flows already print values and a sources footer.
- Lean and full JSON outputs already exist.

The problem is that the current linking/citation experience is only "technically present." It is not yet elegant, obvious, or trivially auditable for humans using the CLI.

I want to spec out three things:

1. Higher-quality, deeper-linking citations
2. Elegant ways to display citations in the current CLI query interface so the underlying data is trivial to parse and audit
3. Quality-of-life UX improvements around auditability, especially for LTM / LTM-1 calculations

For example: when we show an LTM value, the citation/explanation should make it extremely obvious how the number was computed. An auditor should not need to mentally reconstruct `LTM = MRP + LFY - MRP_prior` from a vague prose citation.

## Important Product Intent

- Stay grounded in the current CLI and query architecture. Do not drift into generic "AI research assistant" ideas.
- Prefer incremental, reviewable improvements over a complete reinvention.
- Do not default to a full-screen TUI. If you think a richer interface is eventually warranted, keep that as a later option, not the primary recommendation.
- Optimize for trust, auditability, and speed of verification.
- The user should be able to answer: "Where did this number come from?" in seconds.
- The user should be able to answer: "How was this LTM number constructed?" in seconds.
- The output should remain useful in plain terminals and copy/paste cleanly.
- Machine-readable output still matters. Human UX improvements cannot come at the expense of provenance quality in JSON.

## Inspect These Files First

- `edgarpack/cli.py`
- `edgarpack/query/models.py`
- `edgarpack/query/comps.py`
- `edgarpack/query/periods.py`
- `docs/QUERY.md`

Optional inspiration only:

- `web/components/china-lens/evidence-explorer.tsx`
- `web/components/china-lens/pack-workspace.tsx`

## Current Weak Spots To Evaluate

You should verify these in the code, then expand on them with your own findings:

- Single-company CLI output prints the value first and then a detached `Sources:` footer. This makes auditing slow because the evidence is separated from the number.
- `DerivedValue.citation` collapses LTM provenance into a single prose string instead of a structured calculation trace.
- Lean JSON exposes `ltm_components`, but today it is too thin for serious auditability.
- Multiple deep-link types exist (`filing_url`, `concept_url`, `viewer_url`, `document_url`, `anchor_url`), but the CLI does not have a clear preferred-link strategy.
- Warnings and provenance are not surfaced close enough to the value they qualify.
- The current UX is technically correct but not "auditor-friendly."

## Task

Produce an implementation-ready spec in `docs/CITATION-CLI-UX-SPEC.md`.

Do not start by changing behavior. First write the spec.

Your spec should cover both:

1. Data/provenance model improvements
2. CLI presentation/interaction improvements

## Questions The Spec Must Answer

### 1. Citation Model / Deep Linking

- What fields should a "best-in-class" citation expose for direct metrics?
- What fields should a "best-in-class" citation expose for derived metrics?
- What fields should a "best-in-class" citation expose for LTM / LTM-1 specifically?
- Which URL should be considered the primary deep link in the CLI, and why?
- When should we show `anchor_url` vs `viewer_url` vs `filing_url` vs `concept_url`?
- Should citations get stable short IDs in CLI output (for example `[C1]`, `[L1]`, `[S2]`)?
- Should the JSON shapes change, and if so, how do we preserve backward compatibility?

### 2. LTM Auditability

- How should the CLI explain `LTM = MRP + LFY - MRP_prior` in a way that is instantly legible?
- What exact component metadata should be visible for `mrp`, `lfy`, and `mrp_prior`?
- How should the CLI display period windows so the user can confirm the trailing window without doing date arithmetic in their head?
- How should warnings for per-share metrics, split contamination, or scope ambiguity appear?
- Should LTM have a compact mode and a full audit mode? If yes, define both clearly.

### 3. CLI UX

- What should the default `edgarpack query` experience look like?
- What should an explicit audit-oriented mode look like?
- How should `edgarpack comps` handle citations without turning the table into a mess?
- How should wrapping, indentation, numbering, and spacing work in narrow terminals?
- Should there be new flags such as `--audit`, `--show-links`, `--citations inline`, or similar? If yes, recommend the exact flags and defaults.
- Which improvements are must-have vs nice-to-have?

### 4. Quality-of-Life Improvements

I want you to push beyond the obvious ask and identify adjacent CLI UX improvements that materially improve trust and speed of audit. Examples of the kind of thinking I want:

- better placement of warnings
- clearer reproduction commands / permalinks
- compact inline evidence summaries
- structured calculation blocks
- better default formatting for date ranges and fiscal labels
- deduping repeated citations without hiding important distinctions
- making derived metrics easier to inspect, not just LTM

Do not pad this section with generic ideas. Keep it grounded in the current codebase.

## Required Deliverables In The Spec

Your spec must include all of the following:

1. A current-state critique with concrete file references
2. A proposed citation model revision
3. A proposed CLI rendering model revision
4. At least 3 concrete CLI mockups:
   - one direct metric
   - one LTM metric
   - one multi-company comps example
5. A JSON strategy:
   - what changes in lean JSON
   - what changes in full JSON
   - whether a new audit-focused format is warranted
6. A prioritized implementation plan with phases
7. Acceptance criteria that are specific enough to test
8. Risks / tradeoffs / backward-compat notes

## Concrete Scenarios To Use In Your Mockups

Use realistic examples based on this repo's query model, but do not fabricate live facts from the internet. Use schematic or fixture-style examples if needed.

- `edgarpack query NVDA revenue --period ltm`
- `edgarpack query NVDA gross_margin --period ltm`
- `edgarpack query AAPL revenue`
- `edgarpack comps NVDA AMD --metrics revenue,gross_margin --period ltm`

## Output Quality Bar

- Be opinionated.
- Make tradeoffs explicit.
- Prefer concrete recommendations over option overload.
- If you present multiple options, choose one as the recommendation.
- Avoid vague statements like "improve visibility" unless you specify exactly how.
- Keep the spec focused on trust, auditability, and elegant CLI ergonomics.

## Strong Hint

One of the most important outcomes here is making LTM numbers trivially easy to audit. A good answer will likely recommend a structured audit block that shows:

- formula
- component roles
- component values
- fiscal labels / date ranges
- accession / filing metadata
- preferred deep link per component
- nearby warnings

But do not stop there. I also want the direct-metric citation story and the comps-table citation story improved, not just LTM.

## Final Response

When you are done:

1. Point me to `docs/CITATION-CLI-UX-SPEC.md`
2. Summarize the recommended direction in 5-10 bullets
3. Call out the top 3 implementation decisions that should be made before coding
