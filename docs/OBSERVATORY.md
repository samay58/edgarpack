# Filing Observatory

The observatory diffs filings at the paragraph level and surfaces what actually changed in the prose. Financial tables, signature blocks, TOC links, and date rollovers are filtered out. What remains are the disclosure changes that matter: rewrites to risk factors, new regulatory language, deleted sections, shifts in how a company describes itself.

## What the diff engine does

Given two packs for the same company (e.g., NVDA's FY2024 and FY2025 10-Ks), the engine:

1. Matches sections across filings by stable ID, with a fallback pass that handles sections moving between Parts (e.g., MDA moving from Part II to Part IV between filings).
2. For each matched section, aligns paragraphs using fingerprinting (exact matches) then Jaccard similarity (fuzzy matches via dynamic programming).
3. Scores each section by change intensity (word-weighted, so a 3-word date change counts less than a 200-word risk factor rewrite).
4. Strips noise before output: TOC links, boilerplate, suppressed section types.

## What gets filtered

**Suppressed entirely** (never appear in diff output):
- Financial statement sections (Item 8, Item 15 schedules). The numbers change every year. Not insight.
- Signature blocks. Date rollovers, officer list changes.

**Filtered at the paragraph level** (removed before matching):
- Table of Contents links. These are standalone `[Table of Contents](#hash)` paragraphs whose anchor hashes change between filings.

**Marked as boilerplate and hidden** (matched but invisible in output):
- Cross-reference sentences ("See Item 7 for discussion...", "Refer to Note 12...").
- Date/fiscal-year rollovers where the only changed words are dates, quarter references, or page numbers. Two detection passes: a strict check (80%+ similarity, all changed words are mechanical tokens) and a ratio check (>60% of changed words are mechanical tokens at any similarity level).

**Kept but damped:**
- Exhibit index changes (0.15x weight in interest scoring). Exhibit shuffles can occasionally signal something real.

## Section matching

Three-pass strategy:

1. **Exact ID match.** `10k_parti_item1a_risk_factors` matches `10k_parti_item1a_risk_factors`.
2. **Fallback match.** For unmatched sections, strip the form+part prefix (`10k_partii_` -> `item7_managements_discussion`) and match by the remainder. Only unique 1:1 matches are paired. This catches sections that move between Parts across filings without treating them as added+removed.
3. **Genuinely new/removed.** Anything still unmatched after both passes.

## Intensity and ranking

Each section delta carries:

- `change_intensity`: ratio of weighted changed words to total non-boilerplate words (0.0 = identical, 1.0 = fully rewritten).
- `interest_score`: absolute relevance score for ranking. Prose sections get full weight. Exhibit indices get 0.15x.
- `section_type`: `prose` or `exhibit_index` (financial statements and signatures are suppressed before output).

Output is sorted by `interest_score` descending, then `change_intensity`, then section ID for stable tie-breaking.

For modified paragraphs:
- Added/removed paragraphs contribute full word count.
- Modified paragraphs contribute `word_count * (1 - similarity)`.
- Boilerplate paragraphs contribute nothing and are invisible in output.

## CLI usage

`--ticker` accepts a ticker, a CIK, or a company name. All three route through the same resolver as `query` / `build`.

```bash
# Summary: section counts and overall intensity
edgarpack diff --ticker NVDA --form 10-K

# Full: paragraph-level old/new text for each change
edgarpack diff --ticker "NVIDIA" --form 10-K --format full

# JSON: machine-readable for downstream analysis
edgarpack diff --ticker NVDA --form 10-K --format json

# By pack path (no registry needed)
edgarpack diff --before ./packs/CIK/accession-old --after ./packs/CIK/accession-new

# Evolution of one section across every registered filing
edgarpack timeline --ticker NVDA --section 10k_parti_item1a_risk_factors
```

## API

```
GET /api/v1/observatory/companies/{ticker}/diff?form_type=10-K&detail=full
```

- `detail=full`: includes paragraph deltas with old/new text.
- `detail=sections`: section-level stats only (lighter payload).

## Caching

Diff results are cached on disk under `~/.edgarpack/diff_cache/`. Cache key is derived from the manifest fingerprints of both filings plus a cache version string. If the diff engine changes behavior (new filtering, new scoring), the cache version bumps and old entries are ignored. Corrupted cache files are detected and recomputed automatically.

## Module map

- `edgarpack/diff/text_diff.py`: paragraph splitting, TOC filtering, fingerprinting, Jaccard alignment, boilerplate detection.
- `edgarpack/diff/section_diff.py`: section matching (3-pass), intensity/interest scoring, suppression, output assembly, caching.
- `edgarpack/diff/timeline.py`: tracks one section across multiple filings using the same scoring. Does not apply section-type suppression (timeline is for drilling into a specific section, including financials).
- `edgarpack/diff/models.py`: `ParagraphDelta`, `SectionDelta`, `DiffResult` (Pydantic models).
- `edgarpack/api/observatory/routes.py`: API endpoints with filtering and payload shaping.

## Known limitations

- **MDA (Item 7)** is rewritten every year because it describes the specific fiscal year's results. The diff engine correctly reports high intensity, but this is expected behavior, not a signal. A future improvement could flag MDA as a section where high change intensity is normal.
- **Sectionizer fragmentation** occasionally splits cross-reference sentences into their own sections (e.g., a section titled "(b)(32)(ii) of Regulation S-K..."). These are parse artifacts from the sectionizer, not real disclosures.
- **No semantic ranking within sections.** All paragraph changes in a section are presented equally. The "AI" insertion into a regulatory laundry list is more interesting than the 15th bullet point reordering, but the engine has no way to distinguish them without an LLM pass.
