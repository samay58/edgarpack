# Static Filing Diff Reports

## Status

Design approved on April 25, 2026.

This spec upgrades the current EdgarPack Filing Observatory first, while keeping the
internal model compatible with a later vNext `trace` command. It is associated with bead
`edgarpack-nqy`, but the first implementation lands in the current `edgarpack diff` and
`edgarpack timeline` surfaces rather than waiting for the clean rewrite.

The visual baseline is the approved Paper mockup direction: a light, dense,
code-review-for-filings report. The two exported Paper screenshots showed one duplicated
direction, not three distinct directions; that direction is strong enough to use as the
visual target.

## Goal

Ship deterministic static HTML reports for filing diffs and registration timelines that feel
like a review-grade analyst instrument, not a generic dashboard.

The reports should make document changes easy to inspect, cite, archive, print, and share
without adding a claim-generation layer.

## Non-Goals

- No LLM-generated summaries.
- No generated findings in v1.
- No custom JavaScript.
- No dependency on Diffs.com or `@pierre/diffs`.
- No replacement of the existing section and paragraph alignment algorithm.
- No Next.js Observatory rewrite.
- No true multi-version paragraph lineage.
- No silent mutation of existing packs during report generation.

## Product Contract

Pair diff:

```bash
edgarpack diff --before OLD --after NEW --format html --out report.html
edgarpack diff --ticker NVDA --form 10-K --format html --out report.html
```

Registration timeline:

```bash
edgarpack timeline \
  --series registration \
  --cik 0002021728 \
  --packs ./packs \
  --format html \
  --out reports/cerebras-s1/
```

`diff --format html` writes one self-contained static HTML file. Existing `summary`,
`full`, and `json` output must stay compatible.

`timeline --series registration --format html` writes:

```text
index.html
pair-001.html
pair-002.html
...
```

The timeline index shows filing order, transition stats, changed-section rankings, and
links to pair pages. Pair pages show the full redline for one consecutive filing
transition. Annual section timeline HTML is deferred.

## Ethos

The report is a primary-document review artifact. It may show deterministic facts about the
diff: changed sections, added and removed words, paragraph indices, offsets, chunk status,
and source links.

It must not infer business meaning. Examples of forbidden v1 output:

- "The company is now more concerned about China."
- "Customer concentration risk worsened."
- "Management softened its guidance."

Those are findings, not redlines. A later findings layer may exist only if every generated
finding points to old and new evidence chunk IDs.

## Visual System

Use the Paper mockup as the baseline: light, dense, code-review-for-filings.

Preserve these traits:

- Thin top command bar with product, version, command context, and pair navigation.
- Large accession-to-accession title with compact filing labels beside it.
- Left changed-section rail with additions/deletions and active-section state.
- Full-width diff reading pane with paragraph gutters, change markers, and section headers.
- Cream/off-white canvas, black ink typography, and restrained red/green diff fields.
- Metadata strips below changed paragraphs.
- Footer provenance block with SEC EDGAR links, local pack files, and reproduce command.
- No dashboard cards, decorative CTA buttons, dark chrome, glow, or gradients.

Typography:

- Use serif typography for filing prose only.
- Use tight sans or monospace treatment for command chrome, metadata, gutters, anchors, and
  section rail text.
- Keep body prose readable at screenshot scale.
- Keep metadata compact but not low-contrast.

Static CSS components should map to semantic report structure:

```text
report-shell
topbar
pair-hero
section-rail
diff-pane
section-hunk
paragraph-row
evidence-line
provenance-footer
```

Accessibility:

- Semantic headings and navigation.
- Visible focus states.
- Color is never the only signal; rows also label added, removed, modified, and unchanged.
- Native `<details>` for collapsed unchanged context.
- No required hover-only interactions.
- Print stylesheet for review packets.

## Data Model

Add report-specific models beside the existing diff models in
`edgarpack/diff/report_models.py`. Do not break existing `DiffResult`, `SectionDelta`, or
`ParagraphDelta` consumers.

```text
DiffReport
  report_kind: "pair" | "timeline_pair"
  before_source: FilingSourceRef
  after_source: FilingSourceRef
  chunk_status: "available" | "missing" | "partial"
  sections: list[ReportSectionDelta]

TimelineReport
  cik: str
  entries: list[TimelineReportEntry]
  transitions: list[TimelineTransition]

FilingSourceRef
  accession: str
  cik: str
  company_name: str
  form_type: str
  filing_date: str
  source_url: str | None
  pack_dir: str

SectionSourceRef
  section_id: str
  title: str
  path: str
  char_start: int
  char_end: int
  sha256: str

ReportSectionDelta
  section_id: str
  title: str
  change_type: ChangeType
  old_ref: SectionSourceRef | None
  new_ref: SectionSourceRef | None
  paragraphs_added: int
  paragraphs_removed: int
  paragraphs_modified: int
  paragraphs_unchanged: int
  change_intensity: float
  interest_score: float
  groups: list[ParagraphGroup]

ParagraphGroup
  kind: "changed" | "context" | "collapsed"
  paragraphs: list[ReportParagraphDelta]
  collapsed_count: int
  collapsed_word_count: int

ReportParagraphDelta
  change_type: ChangeType
  old_anchor: EvidenceAnchor | None
  new_anchor: EvidenceAnchor | None
  old_text: str | None
  new_text: str | None
  spans: list[TextSpan]
  similarity: float
  old_word_count: int
  new_word_count: int

EvidenceAnchor
  accession: str
  section_id: str
  section_path: str
  paragraph_index: int
  char_start: int
  char_end: int
  chunk_id: str | None

TextSpan
  side: "old" | "new"
  op: "equal" | "insert" | "delete" | "replace"
  text: str
```

The model is display and evidence structure. It does not contain `summary`, `finding`,
`claim`, or `insight` fields in v1.

## Conversion Pipeline

The existing engine remains the source of truth for section and paragraph matching:

```text
diff_filings()
  -> DiffResult
  -> report adapter
  -> DiffReport
  -> HTML renderer
```

The adapter is responsible for:

1. Loading both manifests and section markdown files.
2. Building paragraph indices for each section with paragraph ordinals and character ranges.
3. Converting `SectionDelta` and `ParagraphDelta` into report deltas.
4. Computing deterministic inline spans for modified paragraphs.
5. Mapping anchors to optional chunk IDs when chunk artifacts exist.
6. Grouping unchanged context around changed paragraphs.
7. Computing report-level chunk status.

Inline spans:

- Use Python stdlib `difflib.SequenceMatcher`.
- Tokenize into word, punctuation, and whitespace runs so output preserves original prose.
- Emit old and new side spans separately.
- Use operation values `equal`, `insert`, `delete`, and `replace`.
- No LLM or semantic rewrite.

Paragraph offsets:

- Offsets are relative to the section markdown file.
- Report metadata should make this clear.
- Source URLs link to the filing document, not exact SEC paragraph anchors.

Chunk mapping:

- SEC packs usually have chunks only when built with `--with-chunks`; local `packs/` may not
  contain `optional/chunks.ndjson`.
- If both sides have chunk files and the changed paragraph range falls within a chunk, include
  the relevant `chunk_id`.
- If one side is missing chunks or coverage is incomplete, use `chunk_status: partial`.
- If both sides are missing chunks, use `chunk_status: missing`.
- Do not generate chunks from the report command.

Context grouping:

- Changed paragraphs are always visible.
- Nearby unchanged context is visible in bounded form.
- Long unchanged runs collapse into native `<details>` with count and word-count labels.
- Full sections are not shown by default.

## HTML Renderer

Add `edgarpack/diff/html_report.py` as a pure-Python renderer. It should emit static,
self-contained HTML and CSS. No `<script>` tag should appear.

Pair page requirements:

- Top command bar.
- Pair hero with before/after accession, form labels, and stats.
- Left changed-section rail.
- Main diff pane grouped by section.
- Hunk headers with section title, counts, and permalink.
- Paragraph gutters with paragraph indices and change markers.
- Modified paragraphs render old/new text with inline spans.
- Added and removed paragraphs render single-side rows.
- Evidence line under changed paragraphs:
  - accession
  - section ID
  - paragraph index
  - offset range
  - chunk ID or chunk status
  - SEC/source link
  - local pack section link
- Footer provenance block:
  - SEC EDGAR/source URLs
  - local pack files
  - reproduce command

Timeline index requirements:

- Filing sequence in chronological order.
- Transition list in pair order.
- For each transition: before/after accession, forms, dates, section counts, word counts,
  and link to pair page.
- Changed-section summary per transition.
- No full redline embedded in index.

HTML safety:

- Escape all filing prose and metadata.
- Treat section titles, paths, and URLs as untrusted for rendering.
- Use safe relative links for generated pair pages.

## CLI Integration

`diff`:

- Add `"html"` to `--format` choices.
- Add `--out` / `-o` for HTML output path.
- Require `--out` when `--format html` is used.
- Do not print full HTML to stdout by default.

`timeline`:

- Add `"html"` to registration timeline output.
- Add `--out` / `-o` for the output directory.
- `--format html` is supported for `--series registration` in v1.
- If `--series annual --format html` is requested before support exists, return a clear
  unsupported error.

## Testing

Unit tests should use tiny synthetic packs so failures stay precise. A small fixture should
exercise:

- one modified paragraph
- one added section
- one removed paragraph
- unchanged context
- collapsed unchanged run
- HTML escaping
- missing chunks
- available chunks
- source URL and local pack section links

Required focused tests:

- report model conversion preserves section and paragraph metadata
- inline span generation is deterministic
- paragraph offsets are correct
- chunk status is `missing`, `partial`, and `available` under the right fixture conditions
- renderer emits no `<script>`
- renderer escapes hostile source text
- pair report includes anchors, evidence lines, source links, and reproduce command
- registration timeline report writes `index.html` and pair pages
- existing `summary`, `full`, and `json` diff behavior remains stable

Manual smoke:

```bash
edgarpack timeline \
  --series registration \
  --cik 0002021728 \
  --packs ./packs \
  --format html \
  --out /tmp/cerebras-s1-report
```

Inspect `/tmp/cerebras-s1-report/index.html` and at least one pair page.

Quality gates after code changes:

```bash
uv run ruff check .
uv run pytest tests/test_diff.py tests/test_cli_registration_timeline_render.py -q
```

If implementation touches shared CLI parsing, manifest loading, or shared diff models, run:

```bash
uv run pytest -q
```

## Acceptance Criteria

- `diff --format html --out report.html` writes a self-contained static report.
- `timeline --series registration --format html --out DIR` writes `index.html` and pair pages.
- Modified paragraphs show old/new prose with deterministic inline word spans.
- Every visible changed paragraph exposes accession, section ID, paragraph index, char offset,
  source URL, and local section path.
- Chunk status is explicit.
- No generated prose findings or LLM summaries appear.
- Long unchanged runs collapse with native `<details>`.
- Source text is HTML-escaped.
- No `<script>` tag is emitted.
- The visual system follows the approved Paper mockup baseline.
- Manual Cerebras local S-1 report smoke completes.

## Risks And Guardrails

The main risks are model drift, visual mediocrity, and false authority.

Guardrails:

- Keep the report model additive.
- Keep old diff output stable.
- Keep the renderer static.
- Keep source prose escaped.
- Keep chunks optional for raw redlines and mandatory for any future finding layer.
- Keep timeline pairwise.
- Keep visual styling scoped to the static report files.

Known edge cases:

- S-1 section IDs can be ugly. Display clean titles while preserving raw IDs in metadata.
- Source URLs do not deep-link to exact paragraphs.
- Chunk mapping may be partial or unavailable.
- Very large sections need bounded default rendering.
- Financial statement sections remain subject to the existing diff engine's suppression and
  ranking behavior unless a future spec changes that contract.

## Deferred Work

- Generated findings with old and new chunk IDs.
- Next.js Observatory consumption of `DiffReport`.
- True multi-version paragraph lineage.
- HTML annual section timelines.
- Optional local search or filters with JavaScript.
- Visual variants beyond the approved Paper baseline.
