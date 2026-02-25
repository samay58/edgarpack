# Codex Handoff: Observatory Quality + Performance Overhaul

## Context

EdgarPack converts SEC EDGAR filings into deterministic markdown packs with stable section IDs, SHA256 hashes, and token counts. The Filing Observatory extends this with diff, timeline, search, and insight layers to surface what *actually changed* between filings.

The Observatory pipeline is functionally complete (harvest, diff, timeline, search, insights, API, web frontend all work end-to-end), but the diff engine produces useless results. Every modified section shows 99-100% change intensity because the intensity calculation treats any non-identical paragraph at full weight regardless of similarity. A paragraph that changed "2024" to "2025" (95% Jaccard similarity) scores identically to a complete rewrite. The system surfaces no meaningful insight ranking, no boilerplate filtering, and no distinction between mechanical date rollovers and genuinely new disclosure language.

This task is a quality + performance overhaul of the diff engine and its consumers. No new features. Fix what's broken, make it fast, make the output useful.

## Problem 1: Change Intensity Ignores Similarity

**File**: `edgarpack/diff/section_diff.py`, function `_compute_section_intensity()` (line 28-57)

**Current behavior**: Any paragraph with `change_type != UNCHANGED` contributes its full word count to `changed_words`. A 500-word paragraph that changed one date (similarity=0.98) counts the same as a 500-word paragraph that was completely rewritten (similarity=0.15).

**Fix**: Weight changed paragraphs by `(1 - similarity)`. A paragraph at 0.95 similarity should contribute only 5% of its word weight to the intensity score.

```python
# Current (broken):
if pd.change_type != ChangeType.UNCHANGED:
    changed_words += words

# Fixed:
if pd.change_type == ChangeType.ADDED or pd.change_type == ChangeType.REMOVED:
    changed_words += words  # fully new/gone content = full weight
elif pd.change_type == ChangeType.MODIFIED:
    changed_words += words * (1.0 - pd.similarity)
# UNCHANGED contributes 0
```

**Verification**: After this fix, NVDA's 10-K diff should show most sections well below 50% intensity. Sections with only date rollovers should be in the 1-5% range. Risk factors with genuine new paragraphs should be noticeably higher.

**Tests to update**: `tests/test_diff.py` - add a test that diffs paragraphs with high similarity and verifies intensity is proportionally low.

## Problem 2: No Boilerplate / Date-Rollover Detection

**File**: `edgarpack/diff/text_diff.py` and `edgarpack/diff/models.py`

SEC filings change dates every year. "fiscal year ended January 28, 2024" becomes "fiscal year ended January 26, 2025". These are not insights. Similarly, cross-reference changes ("see Item 7 of our 2024 Annual Report" to "2025 Annual Report") and page number shifts are noise.

**Approach**: Add a `is_boilerplate` boolean field to `ParagraphDelta`. After computing similarity, check if the delta is mechanical:

1. In `models.py`, add to `ParagraphDelta`:
   ```python
   is_boilerplate: bool = False
   ```

2. In `text_diff.py`, after creating a MODIFIED `ParagraphDelta` (around line 116-125), classify it:
   ```python
   def _is_boilerplate_change(old_text: str, new_text: str, similarity: float) -> bool:
       """Detect mechanical changes that aren't substantive (dates, years, page refs)."""
       if similarity < 0.80:
           return False  # significant rewrite, not boilerplate

       old_norm = _normalize(old_text)
       new_norm = _normalize(new_text)
       old_words = set(old_norm.split())
       new_words = set(new_norm.split())

       diff_words = (old_words - new_words) | (new_words - old_words)

       # Check if all differing words are dates, years, or numbers
       date_pattern = re.compile(r"^\d{1,4}$|^(january|february|march|april|may|june|july|august|september|october|november|december)$|^(fiscal|ended|beginning|ending)$|^\d{1,2}(st|nd|rd|th)?$", re.I)

       if all(date_pattern.match(w) for w in diff_words):
           return True

       return False
   ```

3. In `_compute_section_intensity()`, skip boilerplate paragraphs entirely (they should not inflate the score).

**Verification**: Sections that currently show 99% intensity due to "2024"→"2025" throughout should drop to near 0%. The NVDA diff analysis script at `/tmp/analyze_diff.py` can be used to validate.

## Problem 3: Section Titles Are Garbage

**File**: `edgarpack/parse/sectionize.py`, function `_clean_title()` (line 310-314) and `_truncate_title()` (line 316-320)

Many sections get titles like "of this Annual Report on Form 10-K for additional infor" because the sectionizer captures trailing cross-reference text from concatenated headings instead of the actual section name.

**Root cause**: When a heading like `ITEM 1A. RISK FACTORSFor a discussion of this Annual Report...` is parsed, the regex captures everything after the item number as the title. The `_clean_title` function doesn't strip these trailing cross-reference clauses.

**Fix**: In `_clean_title()` or as a post-processing step, strip common trailing noise patterns:

```python
def _clean_title(raw: str) -> str:
    t = _normalize_heading_text(raw)
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)

    # Strip trailing cross-reference clauses
    # "Risk Factors For a discussion of..." -> "Risk Factors"
    # "Business See Item 7 for..." -> "Business"
    for pattern in [
        r"\s*(?:For|See|Refer to|Please see|As discussed)\s+.*$",
        r"\s*(?:The following|This section|Information)(?:\s+(?:discussion|table|report)).*$",
        r"\s*of this Annual Report.*$",
        r"\s*of (?:our|the) (?:\d{4}\s+)?(?:Annual|Quarterly) Report.*$",
    ]:
        t = re.sub(pattern, "", t, flags=re.IGNORECASE)

    return t.strip()
```

**Also**: Add a known-title mapping for standard 10-K/10-Q items so even badly parsed titles fall back to canonical names:

```python
_CANONICAL_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
}
```

When a title is empty, too short (< 3 words of actual content), or starts with a cross-reference word, fall back to the canonical title for that item number.

**Verification**: Run `edgarpack diff --ticker NVDA --form 10-K --format full` and verify all section titles are readable item names, not truncated cross-reference fragments.

## Problem 4: Financial Statements Are Noise

**File**: `edgarpack/diff/section_diff.py` and potentially `edgarpack/api/observatory/routes.py`

Consolidated financial statements (balance sheet, income statement, cash flow) are tables of numbers that change every year. They will always show high change intensity because every number is different. This is not an insight; the numbers are the data, not the prose.

**Approach**: Add a section classification system. Tag sections by type:

1. Add to `SectionDelta` in `models.py`:
   ```python
   section_type: str = "prose"  # "prose", "financial_statement", "signature", "exhibit_index"
   ```

2. In `section_diff.py`, classify sections by their ID pattern:
   ```python
   def _classify_section(section_id: str) -> str:
       sid_lower = section_id.lower()
       if any(kw in sid_lower for kw in ["financial_statements", "item8", "item_8"]):
           return "financial_statement"
       if "signature" in sid_lower:
           return "signature"
       if "exhibit" in sid_lower and "index" in sid_lower:
           return "exhibit_index"
       return "prose"
   ```

3. In the API route for diff and in the frontend, allow filtering by section type. Default to showing only prose sections (or at least de-prioritize financial statements and signatures in the sort order).

4. In `_compute_section_intensity()`, for financial_statement sections, weight table-heavy paragraphs lower since number changes are expected.

**Verification**: NVDA's diff should no longer show "Consolidated Balance Sheets" at 100% intensity at the top of the list. Financial statement sections should be de-prioritized or filterable.

## Problem 5: Performance

**Files**: `edgarpack/api/observatory/routes.py`, `edgarpack/diff/section_diff.py`

The diff endpoint takes 719ms for just 2 filings. Every request re-reads all section files from disk and recomputes paragraph-level diffs. This will not scale to 80 companies.

**Fixes**:

### 5a. Cache diff results
Add a simple disk cache for computed diffs. The cache key is `sha256(before_manifest_hash + after_manifest_hash)`. Since packs are immutable after build, this cache never goes stale.

```python
# In section_diff.py or a new edgarpack/diff/cache.py:
import hashlib
import json
from pathlib import Path
from ..config import CACHE_DIR

_DIFF_CACHE_DIR = CACHE_DIR.parent / "diff_cache"

def _cache_key(before_dir: Path, after_dir: Path) -> str:
    before_hash = json.loads((before_dir / "manifest.json").read_text())
    after_hash = json.loads((after_dir / "manifest.json").read_text())
    combined = f"{before_hash.get('manifest_hash', '')}:{after_hash.get('manifest_hash', '')}"
    return hashlib.sha256(combined.encode()).hexdigest()

def get_cached_diff(key: str) -> DiffResult | None:
    path = _DIFF_CACHE_DIR / f"{key}.json"
    if path.exists():
        return DiffResult.model_validate_json(path.read_text())
    return None

def cache_diff(key: str, result: DiffResult) -> None:
    _DIFF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (_DIFF_CACHE_DIR / f"{key}.json").write_text(result.model_dump_json())
```

Wrap `diff_filings()` to check cache first.

### 5b. Avoid re-creating Registry/Index per request
In `routes.py`, `_get_registry()` and `_get_search_index()` create a new SQLite connection on every request. Use module-level singletons instead:

```python
_registry: PackRegistry | None = None
_search_index: SearchIndex | None = None

def _get_registry() -> PackRegistry:
    global _registry
    if _registry is None:
        _registry = PackRegistry()
    return _registry

def _get_search_index() -> SearchIndex:
    global _search_index
    if _search_index is None:
        _search_index = SearchIndex()
    return _search_index
```

Remove the `try/finally/close()` pattern from every route handler. The connection stays open for the server lifetime (WAL mode handles concurrent reads fine).

### 5c. Lazy paragraph delta loading
The full diff JSON payload can be large when it includes every paragraph's old_text and new_text for all sections. For the company detail page (which only shows section-level bars), the API should support a `?detail=sections` parameter that omits paragraph_deltas. The full paragraph data should only be loaded when the user clicks into the diff viewer.

**Verification**: After caching, the second request for the same diff should return in < 10ms. The company detail page should load in < 200ms.

## Problem 6: Insight Scoring and Ranking

**File**: New logic in `edgarpack/diff/section_diff.py` or a new `edgarpack/diff/scoring.py`

After fixing intensity and boilerplate, add a simple "interest score" that ranks sections by actual signal:

```python
def compute_interest_score(delta: SectionDelta) -> float:
    """Score a section delta by how interesting the changes are for a human reader.

    Factors:
    - Net new paragraphs (added - removed) indicate disclosure expansion
    - Low-similarity modified paragraphs indicate substantive rewrites
    - High word count in changed content means more material to read
    - Boilerplate changes are discounted to zero
    """
    if delta.change_type == ChangeType.UNCHANGED:
        return 0.0

    score = 0.0
    for pd in delta.paragraph_deltas:
        if pd.is_boilerplate:
            continue
        words = max(pd.old_word_count, pd.new_word_count)
        if pd.change_type == ChangeType.ADDED:
            score += words * 1.5  # new content is most interesting
        elif pd.change_type == ChangeType.REMOVED:
            score += words * 0.8  # removals are notable but less than additions
        elif pd.change_type == ChangeType.MODIFIED:
            score += words * (1.0 - pd.similarity)  # weighted by how different

    return score
```

Add `interest_score: float = 0.0` to `SectionDelta` in `models.py`. Compute it alongside intensity. Sort the diff output by interest_score (descending) instead of raw intensity.

Add `interest_score` to the TypeScript types in `web/types/observatory.ts` and sort by it in the frontend components.

**Verification**: After all fixes, the NVDA diff should rank risk factors, MD&A, and business description sections at the top (where actual prose changes happen), not financial statements or signature pages.

## Files to Modify (Summary)

| File | Changes |
|------|---------|
| `edgarpack/diff/models.py` | Add `is_boilerplate` to ParagraphDelta, `section_type` and `interest_score` to SectionDelta |
| `edgarpack/diff/text_diff.py` | Add `_is_boilerplate_change()`, set `is_boilerplate` on MODIFIED deltas |
| `edgarpack/diff/section_diff.py` | Fix `_compute_section_intensity()` to use similarity weighting, add `_classify_section()`, add `compute_interest_score()`, add diff caching |
| `edgarpack/diff/timeline.py` | Inherits intensity fix via `_compute_section_intensity()` (no changes needed) |
| `edgarpack/parse/sectionize.py` | Fix `_clean_title()` to strip cross-ref clauses, add canonical title fallback |
| `edgarpack/api/observatory/routes.py` | Singleton registry/index, `?detail=sections` parameter, sort by interest_score |
| `edgarpack/insights/language_shift.py` | Inherits intensity fix (verify threshold still makes sense with new scale) |
| `edgarpack/insights/disclosures.py` | No changes needed (already uses Jaccard directly) |
| `web/types/observatory.ts` | Add `is_boilerplate`, `section_type`, `interest_score` fields |
| `web/components/observatory/diff-viewer.tsx` | Sort by interest_score, option to hide boilerplate, dim financial statement sections |
| `web/components/observatory/company-detail.tsx` | Sort bars by interest_score |
| `tests/test_diff.py` | Add tests for similarity-weighted intensity, boilerplate detection, interest scoring |

## Testing Strategy

1. Run existing tests first: `python3 -m pytest tests/ -x -v` (294 should pass)
2. After changes, all existing tests should still pass
3. Add new tests in `tests/test_diff.py`:
   - `test_intensity_reflects_similarity`: Diff two paragraphs at 0.95 similarity, verify intensity < 0.10
   - `test_boilerplate_date_change`: "fiscal year ended January 28, 2024" vs "2025", verify `is_boilerplate=True`
   - `test_interest_score_ranks_substance`: Create sections with boilerplate vs. substantive changes, verify interest_score ordering
   - `test_canonical_title_fallback`: Verify bad titles get replaced by canonical names
4. Run lint: `ruff check . && ruff format --check .`
5. End-to-end: Start API server (`edgarpack api`), hit diff endpoint, verify response has sane intensity values and interest scores

## What NOT to Change

- Do not modify the harvest pipeline, registry, or pack build process
- Do not add new CLI subcommands
- Do not change the search index or topic extraction
- Do not restructure the codebase or add new packages
- Do not add dependencies
- Do not change the sectionizer's section ID generation (IDs must remain stable)
- Do not touch China Lens code
- Keep all changes backward-compatible with existing pack format
