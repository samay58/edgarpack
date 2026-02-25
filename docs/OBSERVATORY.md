# Filing Observatory

The Observatory provides change intelligence over immutable filing packs.
It focuses on one question: what changed in language, not just what changed in bytes.

## Core Behavior

### Section diff semantics

- `ADDED` and `REMOVED` paragraphs contribute full weight.
- `MODIFIED` paragraphs contribute `word_count * (1 - similarity)`.
- Boilerplate-only edits (`is_boilerplate=true`) contribute zero weight.
- Section intensity is the ratio of weighted changed words to total section words.

### Ranking semantics

Each section carries:

- `change_intensity`: normalized rewrite intensity
- `interest_score`: relevance-to-human-review score
- `section_type`: `prose`, `financial_statement`, `signature`, `exhibit_index`

UIs should sort by `interest_score` first, then `change_intensity`.

### Boilerplate handling

`text_diff` marks high-similarity mechanical edits (date/year/page/reference-style token changes) as `is_boilerplate`.
These edits remain visible in full payloads but are discounted from intensity and interest scoring.

## API Contract

Route:

```text
GET /api/v1/observatory/companies/{ticker}/diff
```

Query parameters:

- `form_type`: filing type to compare (default `10-K`)
- `detail`: `full` or `sections`
  - `full`: includes paragraph deltas
  - `sections`: strips `paragraph_deltas` for summary views
- `section_types`: comma-separated section filters
  - `prose,financial_statement,signature,exhibit_index`
  - use `all` (default) to disable filtering

## Performance Model

- Diff results are cached on disk under `~/.edgarpack/diff_cache` (derived from `EDGARPACK_CACHE_DIR` parent).
- Cache key = SHA256 of `(cache_version, before_manifest_fingerprint, after_manifest_fingerprint)`.
- Warm cache skips paragraph diff recomputation and returns precomputed `DiffResult`.

## Module Responsibilities

- `edgarpack/diff/text_diff.py`: paragraph-level matching + similarity + boilerplate tagging
- `edgarpack/diff/section_diff.py`: section assembly, intensity/interest scoring, caching
- `edgarpack/diff/timeline.py`: multi-filing section evolution using the same scoring semantics
- `edgarpack/api/observatory/routes.py`: filtered/trimmed API payload shaping
- `web/components/observatory/*`: ranking, filtering, and presentation controls
