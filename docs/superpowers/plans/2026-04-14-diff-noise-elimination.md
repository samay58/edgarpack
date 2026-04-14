# Diff Noise Elimination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate six sources of noise from the filing diff engine so output surfaces only purposeful disclosure changes.

**Architecture:** Four focused edits across two existing files (`text_diff.py`, `section_diff.py`) plus CLI output cleanup in `cli.py`. No new modules. Each change targets a specific noise source where it naturally belongs in the pipeline.

**Tech Stack:** Python, Pydantic models, regex, existing diff infrastructure

**Spec:** `docs/superpowers/specs/2026-04-14-diff-noise-elimination-design.md`

---

### Task 1: TOC Link Paragraph Filtering

Filter out paragraphs that are solely Table of Contents links before paragraph matching begins. These inflate modified-paragraph counts (13 of 37 "modified" paragraphs in NVDA Risk Factors were TOC links).

**Files:**
- Modify: `edgarpack/diff/text_diff.py:45-48` (add filter function near `_split_paragraphs`)
- Modify: `edgarpack/diff/text_diff.py:107-108` (apply filter after splitting)
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_diff.py`:

```python
from edgarpack.diff.text_diff import _is_toc_link


def test_toc_link_detected():
    assert _is_toc_link("[Table of Contents](#if3830601512b46079053ec0daaf407ac_7)")
    assert _is_toc_link("[Table of Contents](#i82ea215a7c1f4862b6518f1348ddc832_7)")
    assert _is_toc_link("  [Table of Contents](#abc123)  ")


def test_standalone_anchor_link_detected():
    assert _is_toc_link("[Back to top](#anchor_hash_99)")


def test_prose_mentioning_toc_not_detected():
    assert not _is_toc_link("See the Table of Contents for navigation to each section.")
    assert not _is_toc_link("Risk factors are discussed below.")
    assert not _is_toc_link("[Table of Contents](#abc) and other text follows here.")


def test_toc_links_filtered_from_diff():
    old = (
        "Risk factors summary.\n\n"
        "[Table of Contents](#old_hash_abc)\n\n"
        "We face competition in AI chips."
    )
    new = (
        "Risk factors summary.\n\n"
        "[Table of Contents](#new_hash_xyz)\n\n"
        "We face competition in AI chips."
    )
    deltas = diff_paragraphs(old, new)
    # TOC link should be invisible: 2 unchanged paragraphs, no modified
    assert len(deltas) == 2
    assert all(d.change_type == ChangeType.UNCHANGED for d in deltas)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diff.py::test_toc_link_detected tests/test_diff.py::test_standalone_anchor_link_detected tests/test_diff.py::test_prose_mentioning_toc_not_detected tests/test_diff.py::test_toc_links_filtered_from_diff -v`

Expected: ImportError for `_is_toc_link`, then assertion failures.

- [ ] **Step 3: Implement TOC link detection and filtering**

In `edgarpack/diff/text_diff.py`, add after the `_split_paragraphs` function (after line 48):

```python
_TOC_LINK_PATTERN = re.compile(
    r"^\[.*?\]\(#[a-f0-9_]+\)$",
    re.IGNORECASE,
)


def _is_toc_link(text: str) -> bool:
    """Return True if the paragraph is solely a TOC or anchor link."""
    return bool(_TOC_LINK_PATTERN.match(text.strip()))
```

Then in the `diff_paragraphs` function, change lines 107-108 from:

```python
    old_paras = _split_paragraphs(old_text)
    new_paras = _split_paragraphs(new_text)
```

to:

```python
    old_paras = [p for p in _split_paragraphs(old_text) if not _is_toc_link(p)]
    new_paras = [p for p in _split_paragraphs(new_text) if not _is_toc_link(p)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diff.py -v`

Expected: All tests pass, including existing tests.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/text_diff.py tests/test_diff.py
git commit -m "fix(diff): filter TOC link paragraphs before matching"
```

---

### Task 2: Expanded Boilerplate Detection

Two additions: (a) cross-reference pattern detection, (b) ratio-based boilerplate pass that catches date-only changes below the 80% similarity threshold.

**Files:**
- Modify: `edgarpack/diff/text_diff.py:51-83` (expand boilerplate detection)
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_diff.py`:

```python
from edgarpack.diff.text_diff import _is_cross_reference


def test_cross_reference_detected():
    assert _is_cross_reference("See Item 7 for a discussion of our results of operations.")
    assert _is_cross_reference("Refer to Note 12 in our consolidated financial statements.")
    assert _is_cross_reference(
        "For additional information, see Part II, Item 8 of this Annual Report."
    )
    assert _is_cross_reference("For further discussion, refer to Item 1A Risk Factors.")


def test_cross_reference_not_detected_for_prose():
    assert not _is_cross_reference(
        "We face heightened competition in AI and accelerated computing chips. "
        "Our products compete with those from AMD, Intel, and custom silicon "
        "from major cloud service providers."
    )
    assert not _is_cross_reference(
        "The company reported revenue of $35.1 billion for the quarter. "
        "See the full financial statements for details on segment breakdown."
    )


def test_cross_reference_not_detected_for_long_paragraphs():
    # Over 100 words should not be flagged even with cross-ref opener
    long_text = "See Item 7 for discussion. " + "word " * 100
    assert not _is_cross_reference(long_text)


def test_cross_reference_pair_marked_boilerplate():
    old = "See Item 7 of our Annual Report on Form 10-K for the fiscal year ended January 28, 2024."
    new = "See Item 7 of our Annual Report on Form 10-K for the fiscal year ended January 26, 2025."
    deltas = diff_paragraphs(old, new)
    modified = [d for d in deltas if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert modified[0].is_boilerplate is True


def test_ratio_based_boilerplate():
    # 65% similarity but the only changed words are dates/fiscal refs
    old = (
        "We invested heavily in research and development during fiscal year 2024 "
        "ended January 28, 2024, focusing on next-generation architectures and "
        "advanced manufacturing processes for our Q4 product lineup."
    )
    new = (
        "We invested heavily in research and development during fiscal year 2025 "
        "ended January 26, 2025, focusing on next-generation architectures and "
        "advanced manufacturing processes for our Q1 product lineup."
    )
    deltas = diff_paragraphs(old, new)
    modified = [d for d in deltas if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert modified[0].is_boilerplate is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diff.py::test_cross_reference_detected tests/test_diff.py::test_ratio_based_boilerplate -v`

Expected: ImportError for `_is_cross_reference`, assertion failures.

- [ ] **Step 3: Implement cross-reference detection**

In `edgarpack/diff/text_diff.py`, add after the `_is_boilerplate_change` function (after line 83):

```python
_CROSS_REF_OPENER = re.compile(
    r"^(?:see\s|refer\s+to\s|for\s+(?:additional|further)\s+"
    r"(?:information|discussion|details?))",
    re.IGNORECASE,
)
_CROSS_REF_TARGET = re.compile(r"(?:item\s+\d+|note\s+\d+|part\s+[IVXivx]+)", re.IGNORECASE)


def _is_cross_reference(text: str) -> bool:
    """Return True if text is a short cross-reference sentence."""
    stripped = text.strip()
    if len(stripped.split()) > 100:
        return False
    return bool(_CROSS_REF_OPENER.match(stripped) and _CROSS_REF_TARGET.search(stripped))
```

- [ ] **Step 4: Implement ratio-based boilerplate pass**

Replace the existing `_is_boilerplate_change` function (lines 72-83) with:

```python
def _is_boilerplate_change(old_text: str, new_text: str, similarity: float) -> bool:
    """Detect mechanical changes unlikely to be substantive (dates/refs/page numbers).

    Two checks:
    1. Strict: 80%+ similarity AND 100% of changed words match boilerplate tokens
    2. Ratio: >60% of changed words match boilerplate tokens (any similarity)
    Also flags cross-reference paragraph pairs regardless of content changes.
    """
    # Cross-reference pairs are always boilerplate
    if _is_cross_reference(old_text) and _is_cross_reference(new_text):
        return True

    old_words = _tokenize_for_change_detection(old_text)
    new_words = _tokenize_for_change_detection(new_text)
    diff_words = (old_words - new_words) | (new_words - old_words)
    if not diff_words:
        return False

    boilerplate_count = sum(1 for w in diff_words if _BOILERPLATE_TOKEN_PATTERN.match(w))

    # Strict check: high similarity + all changed words are boilerplate
    if similarity >= 0.80 and boilerplate_count == len(diff_words):
        return True

    # Ratio check: >60% of changed words are boilerplate tokens
    if boilerplate_count / len(diff_words) > 0.60:
        return True

    return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diff.py -v`

Expected: All tests pass, including existing `test_boilerplate_date_change`.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/diff/text_diff.py tests/test_diff.py
git commit -m "fix(diff): expand boilerplate detection with cross-refs and ratio pass"
```

---

### Task 3: Section Fallback Matching

Add a second matching pass that strips form+part prefixes from section IDs to match sections that moved between parts (e.g., `10k_partii_item7_mda` -> `10k_partiv_item7_mda`).

**Files:**
- Modify: `edgarpack/diff/section_diff.py:273-424` (refactor section pairing in `diff_filings`)
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_diff.py`:

```python
def test_fallback_matching_across_parts():
    """Sections that move between parts should match, not show as added+removed."""
    with tempfile.TemporaryDirectory() as tmp:
        content = (
            "Management discusses results of operations.\n\n"
            "Revenue increased 20% year over year."
        )
        before_sections = {
            "10k_partii_item7_managements_discussion": content,
            "10k_parti_item1_business": "Business description.",
        }
        after_sections = {
            "10k_partiv_item7_managements_discussion": content,
            "10k_parti_item1_business": "Business description.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        # MDA should match across parts (unchanged content), not be added+removed
        assert result.sections_added == 0
        assert result.sections_removed == 0
        assert result.sections_unchanged == 2


def test_fallback_matching_ambiguous_skipped():
    """When multiple sections share the same reduced key, skip fallback matching."""
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item15_exhibits_financial_statement": "Exhibit list A.",
            "10k_partii_item15_exhibits_financial_statement": "Exhibit list B.",
        }
        after_sections = {
            "10k_partiii_item15_exhibits_financial_statement": "Exhibit list C.",
            "10k_partiv_item15_exhibits_financial_statement": "Exhibit list D.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        # Ambiguous: 2 before and 2 after share reduced key, so all become added/removed
        assert result.sections_added == 2
        assert result.sections_removed == 2


def test_fallback_matching_modified_content():
    """Sections that moved parts AND changed content should show as modified."""
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_partii_item7_managements_discussion": (
                "Old management discussion with prior year analysis.\n\n"
                "Revenue was flat year over year."
            ),
        }
        after_sections = {
            "10k_partiv_item7_managements_discussion": (
                "New management discussion with current year analysis.\n\n"
                "Revenue increased 20% year over year."
            ),
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_added == 0
        assert result.sections_removed == 0
        assert result.sections_modified == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diff.py::test_fallback_matching_across_parts tests/test_diff.py::test_fallback_matching_ambiguous_skipped tests/test_diff.py::test_fallback_matching_modified_content -v`

Expected: `test_fallback_matching_across_parts` fails (sections_added == 1, sections_removed == 1).

- [ ] **Step 3: Implement fallback section matching**

In `edgarpack/diff/section_diff.py`, add a helper function before `diff_filings` (before line 273):

```python
_FORM_PART_PREFIX = re.compile(r"^10[kq]_part[a-z]+_")


def _reduced_section_key(section_id: str) -> str:
    """Strip form+part prefix to get item+slug for fallback matching.

    '10k_partii_item7_managements_discussion' -> 'item7_managements_discussion'
    """
    return _FORM_PART_PREFIX.sub("", section_id)
```

Then refactor the section pairing logic inside `diff_filings`. Replace the block from line 308 (`all_section_ids = ...`) through line 395 (end of the `for sid` loop) with three-pass matching:

```python
    # --- Pass 1: exact ID matching ---
    exact_matched_before: set[str] = set()
    exact_matched_after: set[str] = set()
    section_pairs: list[tuple[str, dict | None, dict | None]] = []

    for sid in sorted(set(before_sections.keys()) & set(after_sections.keys())):
        section_pairs.append((sid, before_sections[sid], after_sections[sid]))
        exact_matched_before.add(sid)
        exact_matched_after.add(sid)

    # --- Pass 2: fallback matching by item+slug (strip part prefix) ---
    remaining_before = {
        sid: sec for sid, sec in before_sections.items() if sid not in exact_matched_before
    }
    remaining_after = {
        sid: sec for sid, sec in after_sections.items() if sid not in exact_matched_after
    }

    # Build reduced-key -> [section_ids] maps
    before_by_reduced: dict[str, list[str]] = {}
    for sid in remaining_before:
        key = _reduced_section_key(sid)
        before_by_reduced.setdefault(key, []).append(sid)

    after_by_reduced: dict[str, list[str]] = {}
    for sid in remaining_after:
        key = _reduced_section_key(sid)
        after_by_reduced.setdefault(key, []).append(sid)

    fallback_matched_before: set[str] = set()
    fallback_matched_after: set[str] = set()

    for key in set(before_by_reduced.keys()) & set(after_by_reduced.keys()):
        before_ids = before_by_reduced[key]
        after_ids = after_by_reduced[key]
        # Only pair unique 1:1 matches
        if len(before_ids) == 1 and len(after_ids) == 1:
            b_sid = before_ids[0]
            a_sid = after_ids[0]
            # Use the after section ID as the canonical ID
            section_pairs.append((a_sid, before_sections[b_sid], after_sections[a_sid]))
            fallback_matched_before.add(b_sid)
            fallback_matched_after.add(a_sid)

    # --- Pass 3: remaining unmatched are genuinely added/removed ---
    for sid in sorted(remaining_before):
        if sid not in fallback_matched_before:
            section_pairs.append((sid, before_sections[sid], None))

    for sid in sorted(remaining_after):
        if sid not in fallback_matched_after:
            section_pairs.append((sid, None, after_sections[sid]))

    # --- Process all pairs ---
    section_deltas: list[SectionDelta] = []
    n_unchanged = 0
    n_modified = 0
    n_added = 0
    n_removed = 0

    for sid, before_sec, after_sec in section_pairs:
        section_type = _classify_section(sid)

        if before_sec and not after_sec:
            n_removed += 1
            old_text = _read_section(before_dir, before_sec["path"])
            para_count = len([p for p in old_text.split("\n\n") if p.strip()])
            words_removed = len(old_text.split())
            delta = SectionDelta(
                section_id=sid,
                title=_display_title(sid, before_sec.get("title", sid)),
                change_type=ChangeType.REMOVED,
                section_type=section_type,
                paragraphs_removed=para_count,
                change_intensity=0.4 if section_type == "financial_statement" else 1.0,
            )
            delta.interest_score = words_removed * 0.8 * _section_interest_weight(section_type)
            section_deltas.append(delta)
            continue

        if not before_sec and after_sec:
            n_added += 1
            new_text = _read_section(after_dir, after_sec["path"])
            para_count = len([p for p in new_text.split("\n\n") if p.strip()])
            words_added = len(new_text.split())
            delta = SectionDelta(
                section_id=sid,
                title=_display_title(sid, after_sec.get("title", sid)),
                change_type=ChangeType.ADDED,
                section_type=section_type,
                paragraphs_added=para_count,
                change_intensity=0.4 if section_type == "financial_statement" else 1.0,
            )
            delta.interest_score = words_added * 1.5 * _section_interest_weight(section_type)
            section_deltas.append(delta)
            continue

        # Both exist: check SHA256 for instant unchanged detection
        if before_sec["sha256"] == after_sec["sha256"]:
            n_unchanged += 1
            section_deltas.append(
                SectionDelta(
                    section_id=sid,
                    title=_display_title(sid, after_sec.get("title", sid)),
                    change_type=ChangeType.UNCHANGED,
                    section_type=section_type,
                    change_intensity=0.0,
                )
            )
            continue

        # Sections differ: do paragraph-level diff
        n_modified += 1
        old_text = _read_section(before_dir, before_sec["path"])
        new_text = _read_section(after_dir, after_sec["path"])

        para_deltas = diff_paragraphs(old_text, new_text)

        added = sum(1 for d in para_deltas if d.change_type == ChangeType.ADDED)
        removed = sum(1 for d in para_deltas if d.change_type == ChangeType.REMOVED)
        modified = sum(1 for d in para_deltas if d.change_type == ChangeType.MODIFIED)
        unchanged = sum(1 for d in para_deltas if d.change_type == ChangeType.UNCHANGED)

        delta = SectionDelta(
            section_id=sid,
            title=_display_title(sid, after_sec.get("title", sid)),
            change_type=ChangeType.MODIFIED,
            section_type=section_type,
            paragraphs_added=added,
            paragraphs_removed=removed,
            paragraphs_modified=modified,
            paragraphs_unchanged=unchanged,
            paragraph_deltas=para_deltas,
        )
        delta.change_intensity = _compute_section_intensity(delta)
        delta.interest_score = compute_interest_score(delta)
        section_deltas.append(delta)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diff.py -v`

Expected: All tests pass, including existing tests and new fallback tests.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/section_diff.py tests/test_diff.py
git commit -m "fix(diff): add fallback section matching across part prefixes"
```

---

### Task 4: Section Type Suppression and Boilerplate-Aware Output

Suppress financial_statement and signature sections from all diff output. Make boilerplate paragraphs invisible in counts and deltas. Recompute overall intensity from non-suppressed sections only.

**Files:**
- Modify: `edgarpack/diff/section_diff.py:397-423` (post-processing and intensity)
- Modify: `edgarpack/cli.py:1053-1064` (output formatting)
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_diff.py`:

```python
def test_financial_sections_suppressed():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Old business description.",
            "10k_partii_item8_financial_statements": "Old revenue: $10B.\n\nOld net income: $2B.",
        }
        after_sections = {
            "10k_parti_item1_business": "New business description with changes.",
            "10k_partii_item8_financial_statements": "New revenue: $15B.\n\nNew net income: $3B.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        # Financial statements should be suppressed
        section_ids = [d.section_id for d in result.section_deltas]
        assert "10k_partii_item8_financial_statements" not in section_ids
        # Business should still be present
        assert "10k_parti_item1_business" in section_ids
        # Counts should exclude suppressed sections
        assert result.sections_modified == 1


def test_signature_sections_suppressed():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Business description.",
            "10k_partiv_itemother_signatures": "Signed January 28, 2024.",
        }
        after_sections = {
            "10k_parti_item1_business": "Business description.",
            "10k_partiv_itemother_signatures": "Signed January 26, 2025.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        section_ids = [d.section_id for d in result.section_deltas]
        assert "10k_partiv_itemother_signatures" not in section_ids


def test_exhibit_index_not_suppressed():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_partiv_itemother_exhibit_index": "Exhibit 31.1\n\nExhibit 31.2",
        }
        after_sections = {
            "10k_partiv_itemother_exhibit_index": "Exhibit 31.1\n\nExhibit 31.2\n\nExhibit 32.1",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        section_ids = [d.section_id for d in result.section_deltas]
        assert "10k_partiv_itemother_exhibit_index" in section_ids


def test_boilerplate_invisible_in_paragraph_counts():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": (
                "For the fiscal year ended January 28, 2024, we grew revenue.\n\n"
                "We expanded into new markets with bold product launches."
            ),
        }
        after_sections = {
            "10k_parti_item1_business": (
                "For the fiscal year ended January 26, 2025, we grew revenue.\n\n"
                "We expanded into enterprise markets with aggressive product launches."
            ),
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        delta = result.section_deltas[0]
        # Only the substantive change should be visible, not the date boilerplate
        visible_deltas = [d for d in delta.paragraph_deltas if not d.is_boilerplate]
        boilerplate_deltas = [d for d in delta.paragraph_deltas if d.is_boilerplate]
        assert len(visible_deltas) >= 1
        # Paragraph counts should exclude boilerplate
        assert delta.paragraphs_modified == len(
            [d for d in visible_deltas if d.change_type == ChangeType.MODIFIED]
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diff.py::test_financial_sections_suppressed tests/test_diff.py::test_signature_sections_suppressed tests/test_diff.py::test_boilerplate_invisible_in_paragraph_counts -v`

Expected: Assertion failures (financial sections still present, paragraph counts include boilerplate).

- [ ] **Step 3: Implement section suppression and boilerplate-aware counts**

In `edgarpack/diff/section_diff.py`, add a constant after `_INTEREST_SECTION_WEIGHTS` (after line 23):

```python
_SUPPRESSED_SECTION_TYPES = {"financial_statement", "signature"}
```

Then in `diff_filings`, after the section pairing loop (where `section_deltas` is fully built), replace the sorting and intensity block (the code starting at the `# Highest-signal deltas first` comment through the `DiffResult` construction) with:

```python
    # --- Filter: suppress noise section types ---
    section_deltas = [
        d for d in section_deltas if d.section_type not in _SUPPRESSED_SECTION_TYPES
    ]

    # --- Filter: make boilerplate paragraphs invisible ---
    for delta in section_deltas:
        if delta.paragraph_deltas:
            visible = [pd for pd in delta.paragraph_deltas if not pd.is_boilerplate]
            delta.paragraph_deltas = visible
            # Recount from visible paragraphs only
            delta.paragraphs_added = sum(
                1 for d in visible if d.change_type == ChangeType.ADDED
            )
            delta.paragraphs_removed = sum(
                1 for d in visible if d.change_type == ChangeType.REMOVED
            )
            delta.paragraphs_modified = sum(
                1 for d in visible if d.change_type == ChangeType.MODIFIED
            )
            delta.paragraphs_unchanged = sum(
                1 for d in visible if d.change_type == ChangeType.UNCHANGED
            )

    # Recount section-level stats from non-suppressed deltas
    n_unchanged = sum(1 for d in section_deltas if d.change_type == ChangeType.UNCHANGED)
    n_modified = sum(1 for d in section_deltas if d.change_type == ChangeType.MODIFIED)
    n_added = sum(1 for d in section_deltas if d.change_type == ChangeType.ADDED)
    n_removed = sum(1 for d in section_deltas if d.change_type == ChangeType.REMOVED)

    # Highest-signal deltas first
    section_deltas.sort(key=lambda d: (-d.interest_score, -d.change_intensity, d.section_id))

    # Compute overall change intensity from non-suppressed sections
    total_sections = len(section_deltas)
    if total_sections > 0:
        weighted = sum(d.change_intensity for d in section_deltas)
        overall_intensity = weighted / total_sections
    else:
        overall_intensity = 0.0
```

**Important:** The `_compute_section_intensity` and `compute_interest_score` functions are called before this filtering step (inside the per-pair loop). They already skip boilerplate paragraphs in their calculations, so intensity/interest scores remain correct even after we remove boilerplate deltas from the list. No changes needed to those functions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diff.py -v`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/section_diff.py tests/test_diff.py
git commit -m "fix(diff): suppress financial/signature sections, hide boilerplate from output"
```

---

### Task 5: CLI Output Formatting

Add paragraph text display with length cap to `--format full`, and bump the diff cache version to invalidate stale cached results.

**Files:**
- Modify: `edgarpack/cli.py:1053-1064` (full format output)
- Modify: `edgarpack/diff/section_diff.py:14` (cache version bump)

- [ ] **Step 1: Bump the diff cache version**

In `edgarpack/diff/section_diff.py`, change line 15 from:

```python
_DIFF_CACHE_VERSION = "v4"
```

to:

```python
_DIFF_CACHE_VERSION = "v5"
```

This invalidates all cached diff results so the new filtering takes effect.

- [ ] **Step 2: Update CLI `--format full` output**

In `edgarpack/cli.py`, replace the `if args.output_format == "full":` block (lines 1053-1064) with:

```python
        if args.output_format == "full":
            print()
            for delta in result.section_deltas:
                if delta.change_type.value == "unchanged":
                    continue
                print(f"  [{delta.change_type.value.upper()}] {delta.title} ({delta.section_id})")
                if delta.change_type.value == "modified":
                    print(
                        f"    +{delta.paragraphs_added} -{delta.paragraphs_removed} "
                        f"~{delta.paragraphs_modified} ={delta.paragraphs_unchanged}"
                    )
                    print(f"    Change intensity: {delta.change_intensity:.1%}")
                    for pd in delta.paragraph_deltas:
                        if pd.change_type.value == "unchanged":
                            continue
                        _print_paragraph_delta(pd)
```

And add the helper function before `_cmd_diff` (before line 996):

```python
def _truncate(text: str, max_words: int = 200) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def _print_paragraph_delta(pd: Any) -> None:
    if pd.change_type.value == "added":
        print(f"      [NEW] {_truncate(pd.new_text or '')}")
    elif pd.change_type.value == "removed":
        print(f"      [DEL] {_truncate(pd.old_text or '')}")
    elif pd.change_type.value == "modified":
        print(f"      [CHG sim={pd.similarity:.0%}]")
        print(f"        - {_truncate(pd.old_text or '')}")
        print(f"        + {_truncate(pd.new_text or '')}")
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -v`

Expected: All 301+ tests pass.

- [ ] **Step 4: Commit**

```bash
git add edgarpack/diff/section_diff.py edgarpack/cli.py
git commit -m "feat(diff): add paragraph text to --format full, bump cache version"
```

---

### Task 6: Acceptance Test (NVDA FY2024 vs FY2025)

Run the real NVDA diff and verify the noise elimination is working.

**Files:**
- No code changes. This is a validation step.

- [ ] **Step 1: Clear the diff cache**

Old cached results use `v4` and won't be found automatically, but clear to be safe:

```bash
rm -rf ~/.edgarpack/diff_cache/
```

- [ ] **Step 2: Run the NVDA diff**

```bash
export EDGARPACK_USER_AGENT="Samay Dhawan samay@example.com"
.venv/bin/edgarpack diff \
  --before ./packs/0001045810/0001045810-25-000023 \
  --after ./packs/0001045810/0001045810-26-000021 \
  --format full
```

**Verify these criteria:**
- Section deltas: ~15-18 (was 64)
- Overall intensity: ~30-45% (was 72.4%)
- No financial statement or signature sections in output
- No TOC link paragraphs showing as modified
- Risk Factors modified paragraphs: ~20-24 (was 37, 13 were TOC links)
- MDA and other cross-part sections show as matched (modified or unchanged), not added+removed

- [ ] **Step 3: Run the JSON output and verify programmatically**

```bash
.venv/bin/edgarpack diff \
  --before ./packs/0001045810/0001045810-25-000023 \
  --after ./packs/0001045810/0001045810-26-000021 \
  --format json > /tmp/nvda_diff.json

python3 -c "
import json
data = json.load(open('/tmp/nvda_diff.json'))
deltas = data['section_deltas']
print(f'Section deltas: {len(deltas)}')
print(f'Overall intensity: {data[\"overall_change_intensity\"]:.1%}')
print(f'Added: {data[\"sections_added\"]}')
print(f'Removed: {data[\"sections_removed\"]}')
print(f'Modified: {data[\"sections_modified\"]}')
# Check no suppressed types leaked through
types = set(d['section_type'] for d in deltas)
assert 'financial_statement' not in types, 'Financial sections leaked!'
assert 'signature' not in types, 'Signature sections leaked!'
# Check no TOC links in paragraph deltas
for d in deltas:
    for pd in d.get('paragraph_deltas', []):
        text = (pd.get('old_text') or '') + (pd.get('new_text') or '')
        assert '[Table of Contents]' not in text, f'TOC link leaked in {d[\"section_id\"]}'
print('All acceptance criteria passed.')
"
```

- [ ] **Step 4: Run full test suite one final time**

Run: `.venv/bin/python -m pytest tests/ -x -v`

Expected: All tests pass.

- [ ] **Step 5: Final commit with any adjustments**

If any thresholds or patterns needed tweaking during acceptance testing, commit those adjustments:

```bash
git add -A
git commit -m "chore(diff): acceptance test adjustments for noise elimination"
```
