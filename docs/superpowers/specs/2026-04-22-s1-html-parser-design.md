# S-1 HTML Parser: Resolve Empty-Filing Regression

**Date:** 2026-04-22
**Status:** Draft spec, pending review
**Blocks:** Cerebras demo, merge of `feat/new-filer-s1-support`
**Related:** `docs/superpowers/specs/2026-04-22-new-filer-s1-support-design.md` (pre-IPO pipeline), `docs/superpowers/specs/2026-04-22-new-filer-s1-support-design.md`

## Problem

Running the full demo flow against Cerebras Systems (CIK 0002021728, S-1 filed 2026-04-17) produces a near-empty pack:

```
packs/0002021728/0001628280-26-025762/
  filing.full.md    # 2 lines, 50 chars: just the title header
  sections/unknown_01.md    # same 50 chars
  manifest.json     # tokens_total: 21, warnings: ["No section headings detected in document"]
```

The primary document (`cerebras-sx1april2026.htm`, 8.56 MB, ~400 pages of S-1 content) is downloaded correctly. The parse pipeline collapses it:

| Stage | Size | Verdict |
|---|---|---|
| Downloaded HTML | 8,560,693 chars | OK |
| After `strip_ixbrl` | 8,560,692 chars | OK (nothing to strip) |
| After `clean_html` | **205 chars** | **BROKEN** |
| After `reduce_to_semantic` | 205 chars | Downstream of break |
| After `render_markdown` | 0 chars | Downstream of break |

The extracted `_S1MetricsBundle` runs against 21 tokens of text, finds nothing, and the timeline / which CLI surfaces have no material to render. The Cerebras demo does not work.

## Root cause (narrow)

Cerebras's S-1 wraps each printed page in a div with this style string:

```html
<div style="--justify:justify;--position:absolute;background-color:#FFFFFF;border:1px solid #CCCC;
content-visibility:auto;float:none;font-size:0;height:792pt;margin:10px auto 10px auto;
overflow:hidden;padding:0;position:relative;width:612pt">
```

The `font-size:0` declaration on the page wrapper is a CSS reset: children (`<font style="font-size:10pt">...`) explicitly set their own size, and the wrapper's zero value is a guard against inherited sizes bleeding in.

Our `is_hidden_style` in `edgarpack/parse/html_clean.py:56` treats `font-size:0` as a signal that text is visually hidden (screen-reader / SEO trick):

```python
HIDDEN_STYLE_PATTERNS = [
    ...
    re.compile(r"font-size\s*:\s*0(?:px|pt|em|rem)?(?:\s|;|$)", re.IGNORECASE),
    ...
]
```

Any single pattern firing sets `_skip_depth = 1`, discarding the entire subtree. The Cerebras page wrapper fires the font-size check, and every page of the S-1 is dropped.

This is a false positive specific to SEC's S-1 rendering idiom. Our 10-K / 10-Q fixtures never exercised it, which is why the test suite did not catch it.

## Root cause (broad)

Even with the narrow bug patched, S-1 parsing remains weak. The Cerebras filing format differs structurally from 10-Ks in ways `semantic_html.reduce_to_semantic` and `md_render.render_markdown` were not designed for:

| Characteristic | 10-K / 10-Q | S-1 (Cerebras style) |
|---|---|---|
| Paragraph tags | `<p>` | None. Text in `<font>` tags |
| Heading tags | `<h1>` – `<h6>` | None. Heading is `<font size:24 weight:bold>` |
| Layout | Document flow | Absolute positioning (`top:XXpt;left:YYpt`) |
| Reading order | DOM order | Must be reconstructed from `top,left` |
| Character count | ~500K – 2M | 5M – 20M (print layout) |
| Sections | `<hr/>`, `<h1>`, ITEM headings | Implicit from font size bumps |

Inspection of a 50KB slice of Cerebras's S-1:

```
position:absolute count: 284
<p> tag count: 0
<h1>..<h6> count: 0
font-size histogram: 8pt:83, 9pt:28, 12pt:24, 0pt:14, 10pt:5, 16pt:5, 18pt:4, 24pt:1
```

Zero semantic tags. All structure encoded in positioning + font metrics.

## Scope decision

Spec ships in two passes, landed as one branch:

**Pass 1, unblock the demo (narrow fix, ~1 hour)**: loosen `is_hidden_element` so `font-size:0` alone no longer discards subtrees. Demo renders full S-1 as flat prose; sections may still be weak.

**Pass 2, S-1-aware structure inference (~4 hours)**: a new `parse/s1_layout.py` module that detects the absolute-positioning idiom and reconstructs reading order plus heading hierarchy from font metrics. Existing 10-K / 10-Q parsing is untouched.

Both passes are required before merging `feat/new-filer-s1-support` to main. Pass 1 alone produces a demo that shows all Cerebras S-1 text but without the ranked section diffs that are the headline feature; Pass 2 makes the demo honest.

## Pass 1: narrow hidden-style fix

### Change

In `edgarpack/parse/html_clean.py`:

1. Remove the standalone `font-size:0` entry from `HIDDEN_STYLE_PATTERNS`. The remaining patterns (`display:none`, `visibility:hidden`, `width:0`, `height:0`, `opacity:0`, negative-offset absolute) continue to catch genuine hiding.
2. Replace it with a conjunction: only treat `font-size:0` as hiding when combined with at least one other hiding signal (e.g., `width:0` AND `height:0` AND `font-size:0`). Cerebras's page wrapper has `height:792pt;width:612pt`, so the conjunction correctly does not fire.
3. Add a regression fixture (`tests/fixtures/s1_font_size_zero_wrapper.html`) containing the Cerebras page-wrapper div with real child text, and a test asserting the child text survives.

### Files

| File | Change | ~LOC |
|---|---|---|
| `edgarpack/parse/html_clean.py` | Replace pattern, add conjunction helper | +15 / -3 |
| `tests/fixtures/s1_font_size_zero_wrapper.html` | New fixture | +40 |
| `tests/test_html_clean_s1_wrapper.py` | New test file | +25 |

### Acceptance

- `clean_html` on the Cerebras primary document produces **≥ 1MB** of output (currently 205 chars).
- The new regression test passes.
- All existing tests continue to pass, including `tests/test_html_clean.py` if it exists, and the `preserve_images` behavior from Task 12.

## Pass 2: S-1 layout-aware structure inference

### New module: `edgarpack/parse/s1_layout.py` (~200 LOC)

Public entry point: `reconstruct_s1_structure(html: str) -> str`.

Returns **semantic HTML** that downstream `semantic_html.reduce_to_semantic` and `md_render.render_markdown` can process unchanged. The module is invoked conditionally from `pack/build.py` when the form is registration-class AND the input HTML has the absolute-positioning signature; otherwise the existing pipeline runs.

### Detection heuristic

`_is_absolute_positioned_layout(html: str) -> bool`:

- True when `position:absolute` appears on ≥ 20 elements AND `<p>` tag count is zero AND `<font` tag count is ≥ 50.
- Cheap linear scan, no full parse.
- 10-Ks never match this predicate.

### Reading-order reconstruction

1. Parse all visible elements (post-`clean_html`) with their inline style attributes retained.
2. For each text-carrying element, extract `top` (absolute) and `left` (absolute) in pt. Elements without positioning inherit from their nearest ancestor div that has `position:absolute`.
3. Group elements by their containing page wrapper (detected via `height:792pt` or similar page-sized div). SEC renders one page per wrapper; within a page, sort by `(top, left)`.
4. Across pages, order is DOM order of wrappers.

### Heading inference

Within each page, text elements are classified by their `font-size` and `font-weight`:

| Font cue | Semantic tag |
|---|---|
| `font-size ≥ 20pt` | `<h1>` |
| `font-size 14-19pt` AND `font-weight:bold` | `<h2>` |
| `font-size 12-13pt` AND `font-weight:bold` | `<h3>` |
| `font-size 12-13pt` | `<p>` |
| `font-size < 12pt` | `<p>` (body or footnote) |

Consecutive inline `<font>` children on the same `top` coordinate concatenate into a single text run.

### Paragraph boundary detection

Two elements with Δtop > 1.8 × median-line-height start a new paragraph. Pages always break to a new paragraph.

### Table detection

Elements arranged in a grid pattern (multiple elements sharing the same `top`, with distinct `left` columns) are emitted as `<table>` with `<tr>` rows and `<td>` cells. Threshold: at least 2 rows where each row has ≥ 2 columns, and column `left` values align to within ±2pt across rows.

Tables detected this way are relevant for the Principal Stockholders extractor (Task 11 output), which currently matches whitespace-aligned plaintext rows. Converting to proper `<table>` markup improves `_PRINCIPAL_HOLDER_ROW` match rates.

### Integration into `pack/build.py`

Inside `_process_html_files_for_form` (Task 15), after `clean_html` and before `reduce_to_semantic`:

```python
from .parse.s1_layout import _is_absolute_positioned_layout, reconstruct_s1_structure
if preserve and _is_absolute_positioned_layout(html_cleaned):
    html_cleaned = reconstruct_s1_structure(html_cleaned)
```

Periodic filings never meet the predicate, so behavior there is unchanged. S-1s that do not use the absolute-positioning idiom (older filings, smaller issuers) skip the reconstruction and flow through the existing pipeline.

### Files

| File | Change | ~LOC |
|---|---|---|
| `edgarpack/parse/s1_layout.py` | NEW: detect + reconstruct | +200 |
| `edgarpack/pack/build.py` | Conditional reconstruction call | +6 |
| `tests/fixtures/s1_absolute_positioned_page.html` | Real Cerebras page slice | +500 |
| `tests/test_s1_layout_reconstruction.py` | 8 behavioral tests | +150 |
| `tests/test_s1_sectionize_against_cerebras.py` | End-to-end: real Cerebras slice → sectionizer finds anchors | +80 |

### Acceptance

1. **Text preservation**: `reconstruct_s1_structure` applied to the full Cerebras S-1 produces markdown with ≥ 90% of the raw document's text content (measured by visible-character count after collapsing whitespace).
2. **Heading detection**: every item in `S1_ANCHOR_TITLES` that appears in Cerebras's S-1 shows up in `manifest.json` `sections` with a non-generic ID (not `unknown_01`, `unknown_02`, ...). Measured against the published Cerebras S-1 TOC.
3. **Table integrity**: Cerebras's Principal Stockholders table is emitted as an HTML `<table>`, and `extract_principal_holders` matches at least 5 named rows.
4. **Regression**: all periodic-filing tests (10-K / 10-Q / 8-K) pass without modification. The reconstruction predicate never fires for those forms.
5. **End-to-end**: `edgarpack build --cik 0002021728 --accession 0001628280-26-025762` produces `filing.full.md` ≥ 200KB with `tokens_total ≥ 50,000`. Manifest has no `"No section headings detected"` warning.

## Kill-list (explicitly NOT in v1)

Do not let scope creep eat the patch. These are deliberate omissions:

- No general-purpose absolute-positioning engine. Scope limited to SEC's S-1 / S-1/A / F-1 / F-1/A / 424B* / FWP rendering format.
- No full CSS parser. Read only `top`, `left`, `width`, `height`, `font-size`, `font-weight` from inline `style` attributes. Ignore `@media`, external stylesheets, style elements.
- No PDF fallback. If an S-1 is distributed only as PDF, it remains unsupported (matches existing 10-K / 10-Q behavior).
- No OCR on embedded images. Task 14 VLM pipeline already covers that.
- No page-break markers in output markdown. Paragraph breaks suffice; page numbers would be noise.
- No per-company calibration. Heuristic thresholds are global; if Cerebras's font-size cutoffs differ from WhiteFiber's or Klarna's, we adjust the thresholds, not branch per issuer.
- No retroactive re-parsing. The Cerebras pack in the registry will be rebuilt manually via `edgarpack build --force`; no migration script.

## Test plan

Unit tests run on fixtures derived from Cerebras's real S-1 (snippets, not the whole 8.56 MB file; we check in a 500-line representative slice).

**Fixture-derived tests** (fast, deterministic, committed):

1. `_is_absolute_positioned_layout` returns True for the Cerebras slice, False for a 10-K slice.
2. `reconstruct_s1_structure` on the Cerebras slice produces HTML with `<h1>`, `<h2>`, `<p>`, and at least one `<table>` tag.
3. Reading order from scrambled DOM: shuffle the input elements, verify output text order matches top-to-bottom reading order.
4. Heading inference: three elements with font-sizes 24pt, 14pt-bold, 12pt produce `<h1>`, `<h2>`, `<p>` respectively.
5. Paragraph split: two elements with large `Δtop` emit two `<p>` tags, not one.
6. Table detection: grid of 3x3 elements with aligned `left` columns becomes a `<table>` with 3 rows x 3 cells.
7. Full pipeline: Cerebras slice → `reconstruct_s1_structure` → `reduce_to_semantic` → `render_markdown` → non-empty markdown containing known S-1 phrases ("Prospectus Summary", "Use of Proceeds").
8. Sectionizer integration: the rendered markdown, fed to `find_sections("S-1")`, returns at least 6 of the 11 `S1_ANCHOR_TITLES`.

**Live-SEC smoke test** (gated on `--run-slow --run-live-sec`):

9. Full Cerebras S-1 roundtrip: fetch, build, assert `tokens_total ≥ 50,000`, assert manifest has ≥ 5 sections with non-generic IDs.

## Open questions resolved during implementation

These are design calls that may shift once we inspect the real fixture:

- Exact font-size cutoffs between `<h1>`, `<h2>`, `<h3>`, `<p>`. Default table in the spec is a starting point; tune against Cerebras until the sectionizer catches all expected anchors.
- Whether `font-weight:bold` alone should promote body text to a heading. Probably not, since S-1s bold-emphasize inline and we'd get false headings. Keep the size threshold as primary signal.
- How aggressively to merge sibling `<font>` runs on the same `top` line. Likely merge unconditionally; worst case we lose subscripts.

## File-change map (pass 1 + pass 2 combined)

| File | Change | ~LOC |
|---|---|---|
| `edgarpack/parse/html_clean.py` | Remove false-positive hidden-style pattern, add conjunction | +15 / -3 |
| `edgarpack/parse/s1_layout.py` | NEW: detect + reconstruct absolute-positioned HTML | +200 |
| `edgarpack/pack/build.py` | Conditional reconstruction call | +6 |
| `tests/fixtures/s1_font_size_zero_wrapper.html` | Regression fixture (pass 1) | +40 |
| `tests/fixtures/s1_absolute_positioned_page.html` | Cerebras slice (pass 2) | +500 |
| `tests/test_html_clean_s1_wrapper.py` | Pass 1 regression test | +25 |
| `tests/test_s1_layout_reconstruction.py` | 8 behavioral tests for pass 2 | +150 |
| `tests/test_s1_sectionize_against_cerebras.py` | End-to-end anchor detection | +80 |
| `tests/test_s1_build_live_smoke.py` | Live-SEC roundtrip (slow-gated) | +40 |
| **Non-test total** | | **~218** |
| **Test total** | | **~835** |

## Success criteria (demo-ready)

After both passes land and the Cerebras pack is rebuilt with `--force`:

```bash
edgarpack build cerebras --form S-1 --force  # rebuilds the single Cerebras pack
wc -l packs/0002021728/0001628280-26-025762/filing.full.md  # ≥ 10,000 lines
jq '.tokens_total' packs/0002021728/0001628280-26-025762/manifest.json  # ≥ 50,000
jq '.sections | length' packs/0002021728/0001628280-26-025762/manifest.json  # ≥ 20
```

Then the demo commands:

```bash
edgarpack which "Cerebras Systems"
edgarpack timeline --series registration --cik 0002021728
```

Produce non-empty output with TAM claims, use-of-proceeds items, dilution, principal holders, and (once amendments are filed) a redline chain.

## Implementation sequence

1. Branch off current `feat/new-filer-s1-support`; do not start a new branch so all S-1 work ships together.
2. Pass 1 first: one commit, one regression fixture, verify Cerebras builds to full length (even without proper structure).
3. Pass 2: TDD the `s1_layout.py` module against the Cerebras fixture slice; unit tests before the behavioral test; behavioral test before live-SEC smoke.
4. Rebuild Cerebras pack with `--force`. Run demo flow. Confirm acceptance criteria.
5. Commit, push, proceed to merge.
