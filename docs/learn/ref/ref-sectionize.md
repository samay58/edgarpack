# Reference: parse/sectionize.py

`edgarpack/parse/sectionize.py` (824 lines)

Form-aware section detection and splitting for SEC filings. Input: the markdown that came out of `render_markdown`. Output: a list of `Section` objects, each with a stable ID, a title, and a character range. Every pack's `sections/*.md` layout and every `manifest.json` entry depends on this module's slug rules and TOC filtering.

---

## Data types

### Section

```python
class Section(BaseModel):
    id: str
    title: str
    content: str
    char_start: int
    char_end: int
    warnings: list[str] = Field(default_factory=list)
```

The unit of output. `id` is the slug (see `section_id` below). `title` is human-readable (e.g. "Risk Factors"). `content` is the exact markdown substring for this section. `char_start` / `char_end` index into the full filing markdown so readers can reconstitute a section's position without re-running the sectionizer. `warnings` collect any per-section concerns (duplicate IDs, preamble detection, etc.).

### SectionMatch

```python
class SectionMatch(NamedTuple):
    line_num: int
    char_pos: int
    part: str | None
    item: str
    title: str
    form_type: str
```

Intermediate result from `find_sections`. Position plus the parsed `(part, item, title)` triple. A `SectionMatch` becomes a `Section` after `sectionize` carves out the content between this match and the next.

---

## Public functions

### sectionize(markdown, form_type)

`edgarpack/parse/sectionize.py:864`. The top-level entry point called from `pack/build.py`.

**Flow:**

1. Call `find_sections(markdown, form_type)` to get a list of `SectionMatch` objects.
2. If empty, return a single `unknown_01` section covering the full document with a warning.
3. If there's substantial content before the first match (>100 chars), prepend an `unknown_00` "Preamble" section.
4. For each match, compute `content` as `markdown[match.char_pos : next_match.char_pos]`, generate a stable ID via `section_id()`, wrap in a `Section`.
5. Run `_filter_toc_stubs` to drop TOC table rows that look like sections.
6. Resolve duplicate IDs by appending `_1`, `_2`, etc. and attaching a "Duplicate section ID detected" warning.

Returns the final list of `Section` objects in document order.

### find_sections(markdown, form_type)

`edgarpack/parse/sectionize.py:235`. The regex-based section detector. Walks the markdown line by line (and also scans inline flattened text and markdown table cells), matches against form-specific patterns, maintains a "current Part" state so items inside Part I don't bleed into Part II, and returns a deduped list of `SectionMatch` objects.

Three patterns drive it:

- `ITEM_PATTERN_10K` (line 34) matches `ITEM <n>[A-Z]?` optionally prefixed with `PART <roman>`. Handles markdown headings, TOC table cells, and page-number prefixes.
- `ITEM_PATTERN_8K` (line 44) matches `ITEM <major>.<minor>` numbering used by 8-K filings.
- `PART_HEADING_PATTERN` (line 52) matches a `PART <roman>` heading with no item, used to update the current-Part state for subsequent matches.
- `TITLED_SECTION_PATTERN` (line 59) matches common non-item titles (SIGNATURES, INDEX TO EXHIBITS, FINANCIAL STATEMENTS, NOTES TO CONSOLIDATED FINANCIAL STATEMENTS).

A TOC state machine within `find_sections` detects when the scanner enters a table of contents (typically identified by a run of short table rows with page numbers) and skips matches within it. TOC stubs that leak through get filtered out later by `_filter_toc_stubs`.

### section_id(form, part, item, title)

`edgarpack/parse/sectionize.py:160`. Generates the stable slug used as the section's ID and filename. Format depends on form type:

- **10-K**: `10k_part<roman>_item<num>[_<slug>]` (e.g. `10k_parti_item1a_risk_factors`)
- **10-Q**: `10q_part<roman>_item<num>[_<slug>]`
- **8-K**: `8k_item_<major>_<minor>[_<slug>]` (dots in item numbers become underscores)
- **Other**: `<form>[_part<roman>][_item<num>][_<slug>]`

The title slug comes from `slugify(title)` (line 120). If the title is empty, the slug is an 8-char SHA1 digest prefixed with `s`, a stable fallback so every section still gets a unique ID.

**Load-bearing invariant**: for a given `(form, part, item, title)` tuple, `section_id` always returns the same string. Rebuilds produce identical filenames, which is what makes the pack hashes stable.

### slugify(text, max_len=30)

`edgarpack/parse/sectionize.py:120`. Lowercase, replace `" and "` and `"&"` with underscores, strip non-alphanumerics, collapse whitespace to underscores, trim to `max_len` on an underscore boundary if possible. Returns the final slug string.

The canonical item titles map at line 73 (`_CANONICAL_ITEM_TITLES`) defines the title to use when a filing just has "Item 1A." and no accompanying text. Useful when the regex catches the item but the title is missing.

### normalize_form_type_for_sections(form_type)

`edgarpack/parse/sectionize.py:97`. Normalizes `"10-K/A"`, `"10K"`, `" 10-k "`, etc. to a canonical base form (`"10-K"`). Amendments (`/A`) are folded into their base form so an amended 10-K and an original 10-K produce the same section IDs.

---

## TOC stub filtering

### `_is_toc_stub(content)`

`edgarpack/parse/sectionize.py:802`. Classifies a section as a TOC stub if its content is entirely markdown table rows plus the item heading itself, with no real prose.

**Rule**: walk the lines. Table rows (`|` prefix, at least two `|`) count as table lines. Lines that look like an item heading (`ITEM 1A.`, `PART I.`, etc. after heading-hash stripping) are ignored. Anything else counts as non-table content. If there's any non-table non-heading text, return `False` (real content). If it's all table lines, return `True` (stub).

### `_filter_toc_stubs(sections)`

`edgarpack/parse/sectionize.py:718`. Runs `_is_toc_stub` on every section. Drops stubs outright (by definition they carry no useful content). The `unknown_00` preamble is exempt.

**Why this matters**: SEC filings almost always contain a table of contents near the top with entries like `| Item 1A. | Risk Factors | 17 |`. The sectionizer's regex matches "Item 1A" inside the TOC and tries to create a section from it, with "content" being just the next few characters of the TOC table. `_filter_toc_stubs` catches those and drops them, so the real "Risk Factors" section (several hundred lines later) keeps its clean ID.

---

## Invariants

- For a given `(form, part, item, title)` tuple, `section_id` returns the same string. Enforced by the deterministic transforms in `slugify` and `section_id`.
- Every section's `char_start` / `char_end` are valid slices of the input markdown: `content == markdown[char_start:char_end].strip()`. Enforced in `sectionize` at line 794.
- After `_filter_toc_stubs`, no section's content consists solely of TOC table rows. Enforced by the stub filter run at line 812.
- Duplicate IDs get a numeric suffix and a warning, never silent overwrites. Enforced at line 815.
- Form type is normalized before ID generation. Amendments and original filings with the same content produce identical IDs.

---

## What this module does not do

- **It does not do semantic sectioning.** The module matches against literal patterns. Filings with unusual formatting may produce a single `unknown_01` section.
- **It does not fix up the TOC state machine if the filter fails.** If a TOC match slips through as a stub, `_filter_toc_stubs` catches it; if the filter also fails, the stub appears in the final output. In practice this is rare.
- **It does not read from disk or network.** Pure function: `(markdown, form_type) -> list[Section]`. Testable with string fixtures, no SEC calls needed.
- **It does not chunk for RAG.** That's `pack/chunks.py`, which operates on sections after they've been produced by this module.
