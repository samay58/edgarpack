# Reference: diff report models and HTML renderer

`edgarpack/diff/report_models.py` (123 lines)
`edgarpack/diff/report_builder.py` (487 lines)
`edgarpack/diff/html_report.py` (643 lines)

The static report layer turns an existing filing diff into a deterministic reading surface. It does not generate claims. It does not call an LLM. It builds a typed `DiffReport` with paragraph anchors, token spans, optional chunk ids, and source links, then renders script-free HTML for pair reports and registration timeline indexes.

See [Trail 8](../trail-8-static-diff-report.md) for the end-to-end story.

---

## Data types

### `FilingSourceRef`

`edgarpack/diff/report_models.py:18`. Filing-level provenance for a report side: accession, CIK, company name, form, filing date, SEC source URL, and local pack directory.

### `SectionSourceRef`

`edgarpack/diff/report_models.py:28`. Section-level provenance from `manifest.json`: section id, title, relative path, character bounds, and section SHA256.

### `EvidenceAnchor`

`edgarpack/diff/report_models.py:37`. Paragraph-level provenance. Carries accession, section id, section path, paragraph index, character start/end, and optional chunk id. This is the unit the HTML evidence line renders.

### `TextSpan`

`edgarpack/diff/report_models.py:47`. Inline token span for modified paragraphs. `side` is `old` or `new`; `op` is `equal`, `insert`, `delete`, or `replace`. Joining all spans for one side reconstructs that side's original text.

### `ReportParagraphDelta`

`edgarpack/diff/report_models.py:53`. Report-ready paragraph row. Holds old/new anchors, old/new raw text, old/new token spans, similarity, and word counts.

### `ParagraphGroup`

`edgarpack/diff/report_models.py:66`. Rendering group for paragraph rows. `kind="changed"` and `kind="context"` carry paragraphs. `kind="collapsed"` carries counts only.

### `ReportSectionDelta`

`edgarpack/diff/report_models.py:73`. One changed section in a pair report. Includes old/new section refs, paragraph counts, intensity, interest score, and paragraph groups.

### `DiffReport`

`edgarpack/diff/report_models.py:88`. Top-level pair report. Includes old/new filing refs, chunk coverage status, section counts, overall intensity, and section list.

### Timeline models

`TimelineReportEntry`, `TimelineTransition`, and `TimelineReport` live at `edgarpack/diff/report_models.py:101-123`. The CLI builds these from registration timeline entries so `render_timeline_index_html` can link the pair pages.

---

## Builder functions

### `build_text_spans(old_text: str, new_text: str) -> tuple[list[TextSpan], list[TextSpan]]`

`edgarpack/diff/report_builder.py:34`.

Splits old and new text into word, whitespace, and punctuation tokens. Runs `difflib.SequenceMatcher(..., autojunk=False)`. Emits deterministic old and new span lists.

The invariant is reconstruction: `"".join(span.text for span in old_spans) == old_text` and the same for new. The test suite asserts this directly at `tests/test_diff_report.py:32-47`.

### `_load_chunks(pack_dir: Path) -> _ChunkLookup`

`edgarpack/diff/report_builder.py:108`.

Reads `optional/chunks.ndjson` if present. Malformed lines, non-object rows, missing ids, and invalid offsets are skipped. Missing file returns an empty lookup.

### `_ChunkLookup.chunk_id_for(section_id, char_start, char_end) -> str | None`

`edgarpack/diff/report_builder.py:101`.

Returns a chunk id only when a paragraph range is fully contained inside a chunk range. This prevents the report from claiming chunk evidence for a paragraph that only overlaps a chunk boundary.

### `_chunk_status(before_chunks, after_chunks, sections) -> ChunkStatus`

`edgarpack/diff/report_builder.py:155`.

Returns `missing` when neither side has chunks. Returns `available` when both sides have chunk files and every changed anchor has a chunk id. Returns `partial` for all mixed cases.

### `_paragraph_locations(text: str) -> dict[str, deque[_ParagraphLocation]]`

`edgarpack/diff/report_builder.py:261`.

Maps split paragraph text to ordered source positions in the original section. Repeated paragraph text gets a queue of positions so anchors advance one occurrence at a time.

### `_anchor(...) -> EvidenceAnchor | None`

`edgarpack/diff/report_builder.py:277`.

Converts one paragraph text into an `EvidenceAnchor` by popping the next matching source location, stamping the filing accession, section id, section path, char range, and optional chunk id.

### `_context_groups(paragraphs, context_window) -> list[ParagraphGroup]`

`edgarpack/diff/report_builder.py:392`.

Groups report paragraphs into changed runs, short context runs, and collapsed runs. Long unchanged spans keep the first and last `context_window` paragraphs and replace the middle with counts.

### `build_pair_report(before_dir, after_dir, *, context_window=2) -> DiffReport`

`edgarpack/diff/report_builder.py:417`.

The main adapter. Loads both manifests, reads optional chunks, calls `diff_filings`, infers moved old sections when section ids changed, builds paragraph anchors and token spans, groups context, and returns a `DiffReport`.

The function never writes files. It is safe to call from `diff --format html`, `timeline --series registration --format html`, and tests.

---

## HTML renderer functions

### `_safe_http_href(url: str | None) -> str | None`

`edgarpack/diff/html_report.py:288`.

Allows only `http` and `https` URLs with a network location. Used for SEC source links.

### `_safe_relative_href(path: str) -> str | None`

`edgarpack/diff/html_report.py:298`.

Allows only safe relative paths. Rejects URL schemes, network locations, absolute paths, fragment links, empty paths, and `..` traversal. Used for timeline index links to pair pages.

### `_safe_pack_file_href(pack_dir: str, section_path: str) -> str | None`

`edgarpack/diff/html_report.py:312`.

Resolves a manifest section path against the pack directory and returns an escaped `file://` URI only if the resolved path remains inside the pack root. This is the guard that makes `old pack` and `new pack` links work from arbitrary report output directories without allowing path traversal.

### `_anchor_bits(anchor, label, source_url, pack_dir) -> list[str]`

`edgarpack/diff/html_report.py:344`.

Builds the evidence-line fragments for one side: accession, section id, paragraph number, char offsets, chunk id, source link or missing marker, and pack file link or omitted marker.

### `_paragraph_html(...) -> str`

`edgarpack/diff/html_report.py:390`.

Renders one paragraph row: gutter, marker, old/new prose block, and evidence line. Modified rows render both old and new prose blocks. Added and removed rows render one side.

### `_section_nav_html(report: DiffReport) -> str`

`edgarpack/diff/html_report.py:459`.

Builds the left rail. Omits unchanged sections. Each changed row links to the section hunk id and prints added/removed paragraph counts.

### `render_pair_report_html(report: DiffReport, reproduce_command: str = "") -> str`

`edgarpack/diff/html_report.py:517`.

Returns a complete HTML document with embedded CSS. The structure is topbar, hero, two-column layout, changed-section rail, diff pane, and provenance footer. The document is static and script-free.

### `render_timeline_index_html(report: TimelineReport) -> str`

`edgarpack/diff/html_report.py:581`.

Returns a complete HTML index for registration timelines. Each transition links to a pair report through `_safe_relative_href` and shows add/remove/modify/unchanged counts plus intensity.

---

## Invariants

- Report generation is deterministic for the same pair of pack directories. `build_pair_report` reads manifests, section markdown, optional chunks, and `diff_filings`; it does not read external state beyond the diff cache used by the existing engine.
- A visible paragraph evidence line never invents a source. Missing anchors render as missing markers. Unsafe source URLs and unsafe pack paths render as missing or omitted markers.
- Local pack links are absolute `file://` links to resolved pack files. They are not relative to the output report directory.
- Joining token spans reconstructs the source paragraph text. The spans are for rendering only; they are not a separate source of truth.
- Collapsed context changes only the report shape, not the underlying diff. Long unchanged runs become counts so reviewers can read the changed parts without losing position.
- Timeline HTML is a directory of pair reports plus an index. The index does not duplicate paragraph detail; it links to the same pair report renderer used by `diff --format html`.
