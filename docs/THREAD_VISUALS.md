# Thread Visuals

This guide is the reference for EdgarPack social-thread visuals. Use it when a
future Codex, Claude Code, or human session plans a public X/Twitter or LinkedIn
thread from filing analysis.

The current quality bar is the Cerebras portrait series:

- Reference kit: `assets/thread-visual-reference/cerebras-filing-series-2026/`
- Design notes: `assets/thread-visual-reference/cerebras-filing-series-2026/00_design_system.md`
- Format: 4:5 portrait social cards, approximately `1122 x 1402px`

The older `assets/cerebras-visuals/` landscape set is useful context, but the
portrait filing series is the bar to meet or beat for future public threads.

## When To Use This

Use this reference when the work product is:

- A public thread derived from EdgarPack outputs.
- A visual explanation of a filing diff, S-1, 10-K, 10-Q, or named-company
  research bundle.
- A thread where the visuals need to carry the analysis, not merely decorate
  the prose.

Do not use it for internal implementation docs, CLI screenshots, raw research
ledgers, or local debugging artifacts.

## Visual Standard

Future thread visuals should feel like a premium editorial research series:
warm paper background, high-contrast serif headlines, precise gray rules,
restrained line icons, and one live orange accent. The mood is filing analysis
for smart public-market readers: sharp, sparse, legible, and source-grounded.

Keep these constants:

- Light background in the warm ivory family.
- Large serif headline with generous whitespace.
- Small circular slide index and series label near the top-left.
- Thin dividers, dotted gridlines, and source footer.
- Orange used for the main analytical signal, not sprayed everywhere.
- One visual idea per card.

Vary the composition per slide. A thread should not become eight versions of
the same card with different text.

## Evidence Rules

Every meaningful claim in a visual must be traceable to filing evidence,
EdgarPack output, or a clearly named external source. Do not create visuals that
look more certain than the source material.

Required:

- Footer source language on every exported card.
- Numbers copied from the evidence ledger, thread notes, or filing sections.
- Caution around inferred labels such as "customer", "creditor", "anchor", or
  "pivot". If the filing does not support the word, use a softer description.
- No invented market context just because it makes a cleaner graphic.

Preferred source footer:

```text
Source: <Company> filings, via edgarpack diff.
```

For amendment comparisons:

```text
Source: <Date> and <Date> <form> filings, via edgarpack diff.
```

## Accessibility Checks

Before a card is treated as publishable:

- The headline should remain readable on a phone preview.
- Body copy should avoid dense paragraphs. Use short captions and labels.
- Orange should never be the only way to distinguish a data state.
- Data charts need labeled axes or direct labels. Do not rely on shape alone.
- Footer source text can be small, but it must remain legible at social preview
  size.
- Alt text should be written for each final image before posting.

## Thread Workflow

Start with the thread spine, not the image style. The best sequence is:

1. Build the evidence surface with EdgarPack.
2. Draft the thread with one analytical beat per tweet.
3. Pick the 5 to 8 beats that deserve visuals.
4. Assign each selected beat a different visual form: chart, before/after,
   table, relationship map, metric rail, or comparison card.
5. Render visuals against the Cerebras portrait reference.
6. Re-check every number, label, and source footer against the evidence.

If the visual cannot be supported by evidence, cut the visual or change the
claim. EdgarPack's advantage is trust. The graphics should make that trust
visible.
