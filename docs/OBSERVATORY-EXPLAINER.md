# Observatory System Map

A module-by-module view of how a filing becomes a diff, a timeline, and a search result. Use this when onboarding to the Observatory pipeline or when tracing an unexpected output back to its source.

## Design goals

- Flow first, details second.
- Each module is traceable back to a file path and a test.
- Layered: 90-second overview, 10-minute mental model, deep-debug mode.

## Module map

```mermaid
flowchart LR
    A[SEC Filing HTML] --> B[parse/sectionize.py\nStable IDs + Canonical Titles]
    B --> C[Pack Artifacts\nmanifest + sections/*.md]

    C --> D[diff/text_diff.py\nParagraph match + similarity + boilerplate]
    D --> E[diff/section_diff.py\nIntensity + interest score + section type + cache]
    E --> F[diff/timeline.py\nCross-filing evolution]
    E --> G[insights/language_shift.py\nHigh-intensity rewrite detector]

    E --> H[api/observatory/routes.py\nFiltering + detail=sections + section_types]
    F --> H
    G --> H

    H --> I[web/lib/observatory-api.ts\nTyped client]
    I --> J[UI: company-grid]
    I --> K[UI: company-detail]
    I --> L[UI: diff-viewer]
    I --> M[UI: timeline-view]
    I --> N[UI: search-page]
```

## Layered drill-down plan

### Layer 1: 90-second orientation

- Data enters at `sectionize`.
- Diff intelligence happens in `text_diff` + `section_diff`.
- API shapes payloads for summary vs deep views.
- UI consumes typed models and surfaces ranking/filters.

### Layer 2: 10-minute implementation mental model

- `text_diff`: match paragraphs, compute similarity, tag boilerplate.
- `section_diff`: compute intensity and `interest_score`, classify section type, cache by manifest-pair hash.
- `routes`: serve lightweight (`detail=sections`) or full payloads; filter by section type.

### Layer 3: deep-debug mode

- Why a section ranked high: inspect paragraph deltas and score factors.
- Why intensity dropped: inspect similarity weighting + boilerplate exclusion.
- Why response is fast: verify cache-hit path and stripped payload mode.

## Interaction pattern for an interactive version

- Hover module: one-sentence purpose + key outputs.
- Click module: code pointers, invariants, and tests.
- Toggle overlays:
  - `Signal vs Noise` (boilerplate, financial statements, signatures)
  - `Performance` (cache hit/miss, payload sizes)
  - `Traceability` (input -> output fields)

## Avoiding “garbled complexity”

- Keep every card to: `Purpose`, `Inputs`, `Outputs`, `Invariants`.
- Never show more than one abstraction level in a single frame.
- Use one canonical example (NVDA 10-K year-over-year) across all layers.
- Color semantics:
  - blue = core pipeline
  - amber = scoring/ranking
  - green = performance paths
  - gray = expected-noise pathways
