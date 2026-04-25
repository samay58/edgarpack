# Trail 8: How `edgarpack diff --format html` turns two packs into a static report

**Time**: ~12 minutes
**Prereq**: [Trail 1](trail-1-build-a-pack.md) and [Trail 7](trail-7-s1-pre-ipo.md). You should know what a pack contains and why registration timelines matter.
**Covers**: `edgarpack/cli.py:_cmd_diff`, `edgarpack/diff/report_builder.py`, `edgarpack/diff/report_models.py`, `edgarpack/diff/html_report.py`

You run `edgarpack diff --before packs/NVDA/2024 --after packs/NVDA/2025 --format html --out report.html`. The command does not ask a model to summarize what changed. It reads two local packs, reuses the existing section diff engine, builds paragraph-level evidence anchors, and writes a script-free HTML file you can open locally.

The important contract is provenance. Every visible changed paragraph points back to the old accession, new accession, section id, paragraph number, character offsets, optional chunk id, SEC source URL, and local pack file.

---

## 1. The CLI chooses the report path only after it has real packs

The `diff` parser accepts the same pack selectors as the text diff path, plus `--format html` and `--out` for the static artifact.

```python
p_diff.add_argument("--before", help="Accession number or pack dir of earlier filing")
p_diff.add_argument("--after", help="Accession number or pack dir of later filing")
p_diff.add_argument(
    "--format",
    dest="output_format",
    choices=["summary", "full", "json", "html"],
    default="summary",
)
p_diff.add_argument("--out", "-o", type=Path, help="Output path for --format html")
```

The handler first resolves `--ticker` or explicit `--before` / `--after` into two pack directories. It refuses to continue if either directory is missing. Only then does the HTML branch run.

```python
if args.output_format == "html":
    if args.out is None:
        print("Error: --out is required when --format html", file=sys.stderr)
        return 2

    report = build_pair_report(before_dir, after_dir)
    html = render_pair_report_html(report, reproduce_command=reproduce_command)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
```

That order keeps the command honest. `--format html` is only a renderer swap. It does not bypass pack resolution, pack existence checks, or the same `diff_filings` calculation that powers the older text and JSON outputs.

**Code**: `edgarpack/cli.py:500-523` (`p_diff`), `edgarpack/cli.py:2298-2319` (HTML branch in `_cmd_diff`).

---

## 2. The report builder wraps the existing diff engine with evidence

`build_pair_report` is the adapter between the old diff result and the new report contract. It loads both manifests, builds source refs, reads optional chunk maps, then calls `diff_filings`.

```python
before_manifest = load_manifest_dict(before_dir, on_missing="raise")
after_manifest = load_manifest_dict(after_dir, on_missing="raise")
before_source = _filing_ref(before_dir, before_manifest)
after_source = _filing_ref(after_dir, after_manifest)
before_chunks = _load_chunks(before_dir)
after_chunks = _load_chunks(after_dir)
diff = diff_filings(before_dir, after_dir)
```

The manifest matters because the diff engine knows which paragraphs changed, but the report needs more than that. A reader needs filing identity, source URL, section path, section hash, and local pack directory. `_filing_ref` and `_section_ref` pull that out of `manifest.json`.

For each changed section, the builder finds the old and new section text, maps split paragraphs back to character offsets, and creates `ReportParagraphDelta` rows. Modified paragraphs also get token spans through `build_text_spans`, so the renderer can highlight replacements without changing the underlying old or new text.

**Code**: `edgarpack/diff/report_builder.py:182-193` (`_filing_ref`), `edgarpack/diff/report_builder.py:204-214` (`_section_ref`), `edgarpack/diff/report_builder.py:34-62` (`build_text_spans`), `edgarpack/diff/report_builder.py:417-487` (`build_pair_report`).

---

## 3. Paragraph anchors are source positions, not guesses

The builder reconstructs paragraph positions from the source section text.

```python
for index, paragraph in enumerate(_split_paragraphs(text), start=1):
    char_start = text.find(paragraph, search_start)
    ...
    locations[paragraph].append(_ParagraphLocation(index, paragraph, char_start, char_end))
```

Repeated paragraphs are stored in a queue. When a delta refers to the same paragraph text twice, `_anchor` pops the next location instead of always pointing to the first copy. That is why the report can say "paragraph 31, offset 24936-25082" instead of just "somewhere in Risk Factors."

Optional chunks are stricter. `_ChunkLookup.chunk_id_for` only returns a chunk id when the paragraph's character range is fully inside that chunk. Partial overlap is not good enough because a chunk id in the report is an evidence claim.

```python
if chunk.char_start <= char_start and char_end <= chunk.char_end:
    return chunk.chunk_id
```

If chunks are missing or do not cover a changed paragraph, the report still renders the accession, section, paragraph, and offsets. The `chunk_status` field tells you whether chunk coverage is available, partial, or missing.

**Code**: `edgarpack/diff/report_builder.py:81-105` (`_ChunkLookup`), `edgarpack/diff/report_builder.py:145-179` (`_chunk_status`), `edgarpack/diff/report_builder.py:261-302` (`_paragraph_locations` and `_anchor`), `edgarpack/diff/report_models.py:37-45` (`EvidenceAnchor`).

---

## 4. Long unchanged runs collapse before rendering

The report is not a raw full-filing dump. `_context_groups` walks the paragraph deltas and keeps short context around changed runs. Long unchanged runs become a `ParagraphGroup(kind="collapsed")` with paragraph and word counts.

```python
if len(run) <= collapse_threshold:
    groups.append(ParagraphGroup(kind="context", paragraphs=list(run)))
    return

leading = run[:context_window]
trailing = run[-context_window:] if context_window else []
collapsed = run[context_window : len(run) - context_window]
```

This is a reading-surface decision, not a diff-engine decision. The report model keeps enough structure for the renderer to show context without forcing a reader to scroll through every unchanged paragraph in the filing.

**Code**: `edgarpack/diff/report_builder.py:352-414` (`_context_groups` helpers), `edgarpack/diff/report_models.py:66-70` (`ParagraphGroup`).

---

## 5. The HTML renderer is intentionally static

`render_pair_report_html` writes one HTML string with embedded CSS and no JavaScript. The main layout has a top bar, hero, changed-section rail, paragraph rows, and provenance footer.

```python
<aside class="section-rail" aria-label="Changed sections">
  <p class="rail-title">{changed_count} changed sections</p>
  {sections_nav}
</aside>
<div class="diff-pane">{section_html}</div>
```

The renderer does not compute the diff. It only serializes a `DiffReport`. That separation is the reason the same report model can also power `timeline --series registration --format html`.

Changed paragraphs render in three layers:

1. Gutter and marker: paragraph number plus `+`, `-`, `~`, or `.`.
2. Prose: old text, new text, or both for modified rows.
3. Evidence line: source ids and source links.

The CSS sets the paper palette, monospace metadata, serif prose body, focus outline, mobile single-column fallback, print behavior, and reduced-motion guard in one place.

**Code**: `edgarpack/diff/html_report.py:20-273` (static CSS), `edgarpack/diff/html_report.py:390-430` (`_paragraph_html`), `edgarpack/diff/html_report.py:517-578` (`render_pair_report_html`).

---

## 6. Hrefs are deliberately narrow

The renderer accepts only two href families.

SEC source links must be `http` or `https`.

```python
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    return None
```

Timeline page links must be relative paths that do not start with `/`, `#`, a URL scheme, or `..`.

Local pack links are different. They are resolved against the actual pack directory and emitted as `file://` URIs only if the target stays inside that pack root.

```python
pack_root = Path(pack_dir).expanduser().resolve(strict=False)
target = (pack_root / normalized).resolve(strict=False)
target.relative_to(pack_root)
return escape(target.as_uri(), quote=True)
```

This is why the `old pack` and `new pack` links work when the report lives in `/tmp/report.html`: they point to the original pack files, not to a fake `sections/` directory beside the report.

The regression tests cover both sides of this contract. Valid pack links must appear as absolute file URIs, and unsafe `javascript:`, `data:`, and `../` paths must not become hrefs.

**Code**: `edgarpack/diff/html_report.py:288-330` (href guards), `edgarpack/diff/html_report.py:344-370` (`_anchor_bits`), `tests/test_diff_report.py:466-529` (static report and pack-link assertions), `tests/test_diff_report.py:556-588` (unsafe href rejection).

---

## 7. Registration timelines reuse the same pair report

`timeline --series registration --format html` creates a directory, writes one pair report per transition, and writes `index.html` as the trail map.

```python
for idx, (before, after) in enumerate(zip(entries, entries[1:], strict=False), start=1):
    pair_report = build_pair_report(before.pack_dir, after.pack_dir)
    output_file = f"pair-{idx:03d}.html"
    (out_dir / output_file).write_text(
        render_pair_report_html(pair_report, reproduce_command=reproduce_command),
        encoding="utf-8",
    )
```

The index is intentionally small. It lists each transition, links to the pair file through the safe relative-href guard, and prints section counts plus overall intensity.

This matters for S-1 review. The timeline gives you the filing chain. The pair report gives you the paragraph-level evidence for each transition. Both surfaces share the same provenance model.

**Code**: `edgarpack/cli.py:2391-2435` (registration timeline HTML output), `edgarpack/diff/html_report.py:581-643` (`render_timeline_index_html`), `edgarpack/diff/report_models.py:101-123` (timeline report models).
