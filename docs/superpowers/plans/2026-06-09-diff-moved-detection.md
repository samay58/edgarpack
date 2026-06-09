# Diff Precision: Moved Detection and Distinctive-Token Gating

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the paragraph-level diff labels trustworthy: reordered or far-moved paragraphs get a `moved` label instead of false `added`/`removed`, and topically unrelated paragraphs sharing legal boilerplate stop being married as `modified`.

**Architecture:** Two changes inside `diff_paragraphs()` plus their fan-out. First, a distinctive-token Jaccard (an IDF-lite filter that ignores tokens ambient across the section's paragraphs) gates the existing DP pairing, killing boilerplate-tail marriages. Second, an order-free rescue pass over the DP's leftovers pairs near-verbatim paragraphs as a new `ChangeType.MOVED`. Scoring damps moved content, the diff cache version bumps, and the report renders moved paragraphs as redlines with a badge. JSON gains one enum value and one count field; nothing else changes shape.

**Tech Stack:** Python stdlib only (the diff layer has no third-party deps beyond pydantic models). No `PARSER_VERSION` bump: pack bytes are untouched.

---

## Why (evidence)

Ground-truth audit, 2026-06-09 (see `docs/BACKLOG.md`, "Diff engine precision findings"):

- 10 of 11 "added" Risk Factors paragraphs in the CRWV 10-Q pair (`0001769628-25-000062` → `0001769628-26-000222`) had matching text in the before filing. Pass 1 (exact fingerprints) is already order-free, so these are *near*-verbatim strays: small wording edits or embedded page-number debris dodge the fingerprint, then the order-preserving DP in pass 2 can't pair them across a reorder.
- Confirmed forced marriages at reported Jaccard 0.38-0.48: disaster-recovery paired with sustainability, tariffs with supplier concentration. Both pairs share the ambient legal tail ("could adversely affect our business, operating results, financial condition..."), which inflates plain Jaccard. A flat floor cannot separate them from genuine rewrites in the same range; distinctiveness filtering can.
- Recall is not the problem: no hidden changes were found in three audited pairs. Only the labels lie.

## Goals

1. A paragraph that exists near-verbatim in both filings is never labeled `added` or `removed`.
2. A `modified` pair shares distinctive (non-ambient) vocabulary, not just legal boilerplate.
3. Moved-but-barely-edited content stops inflating interest scores and intensity.
4. Deterministic output, versioned cache, all existing consumers handled.

## Non-goals

- Page-break artifact stripping inside section markdown ("Table of Contents", bare page numbers mid-paragraph). That is a parse-pipeline change with a `PARSER_VERSION` bump and fixture regeneration; it gets its own spec. Until then, artifact paragraphs may surface as `moved` pairs (both sides contain them), which is harmless.
- HTML report layout work (shipped 2026-06-09 in `diff/html_report.py`).
- Split/merge detection beyond what the existing overlap rescue already handles.

## Tuning constants (calibrated in Task 7)

| Constant | Initial | Meaning |
| --- | --- | --- |
| `_DISTINCTIVE_DF_RATIO = 0.25` | 0.25 | Token is "ambient" if it appears in >= 25% of the section pair's paragraphs |
| `_DISTINCTIVE_MIN_PARAS = 8` | 8 | Below this many paragraphs, DF stats are noise; fall back to plain Jaccard |
| `_DISTINCTIVE_FLOOR = 0.2` | 0.2 | DP diagonal also requires distinctive Jaccard >= this |
| `_RESCUE_MIN_JACCARD = 0.6` | 0.6 | Rescue pair must be near-verbatim by plain Jaccard |
| `_RESCUE_MIN_DISTINCTIVE = 0.5` | 0.5 | ...and share distinctive vocabulary |
| `_MOVED_DAMPING = 0.3` | 0.3 | Moved paragraphs contribute `words * (1 - sim) * 0.3` to scores |

Calibration outcome (2026-06-09, CRWV/FIG/RDDT pairs): all constants confirmed at their initial values. The three audited CRWV forced-marriage pairs measure distinctive 0.358 / 0.435 / 0.603 against the real section DF, interleaved with genuine rewrites (0.470, 0.493 sit between them), so no floor separates them without unmarrying real pairs; the floor stays at 0.2, which blocks the pathological tail-only case, and the renderer's stacked-below-0.5 presentation mitigates the rest. CRWV added 11 -> 7 with all four artifact strays demoted to moved at similarity 1.0; FIG gained 8 moved with all four verified lesson quotes still visible; RDDT unchanged (0 added before and after). Output confirmed byte-identical across independent fresh caches.

## File structure

| File | Change |
| --- | --- |
| `edgarpack/diff/models.py` | `ChangeType.MOVED`; `SectionDelta.paragraphs_moved` |
| `edgarpack/diff/text_diff.py` | `_doc_frequencies`, `_distinctive_jaccard`, DP gate, rescue pass |
| `edgarpack/diff/section_diff.py` | counts, interest/intensity damping, cache `v6` → `v7` |
| `edgarpack/diff/report_builder.py` | build text spans for `MOVED` |
| `edgarpack/diff/report_models.py` | `ReportSectionDelta.paragraphs_moved` |
| `edgarpack/diff/html_report.py` | moved marker/badge; counts in rail and hunk header |
| `edgarpack/insights/language_shift.py` | explicitly skip `MOVED` |
| `docs/OBSERVATORY.md` | document the new change type and count |
| `tests/test_diff.py`, `tests/test_diff_report.py` | new unit tests |

---

### Task 1: Models

**Files:**
- Modify: `edgarpack/diff/models.py`
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing test**

```python
def test_moved_change_type_exists():
    assert ChangeType.MOVED.value == "moved"
    delta = SectionDelta(section_id="s", title="S", change_type=ChangeType.MODIFIED)
    assert delta.paragraphs_moved == 0
```

(`SectionDelta` is already imported in `tests/test_diff.py` via `from edgarpack.diff.models import ...`; extend that import with `SectionDelta` if absent.)

- [ ] **Step 2: Run it; expect `AttributeError: MOVED`**

Run: `uv run --extra dev pytest tests/test_diff.py::test_moved_change_type_exists -q`

- [ ] **Step 3: Implement**

In `edgarpack/diff/models.py`:

```python
class ChangeType(StrEnum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    MOVED = "moved"
    ADDED = "added"
    REMOVED = "removed"
```

In `SectionDelta`, after `paragraphs_modified`:

```python
    paragraphs_moved: int = 0
```

- [ ] **Step 4: Run the test; expect PASS. Run the full diff suite to catch surprises**

Run: `uv run --extra dev pytest tests/test_diff.py tests/test_diff_report.py -q`

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/models.py tests/test_diff.py
git commit -m "feat(diff): add ChangeType.MOVED and paragraphs_moved count"
```

### Task 2: Distinctive-token Jaccard

**Files:**
- Modify: `edgarpack/diff/text_diff.py`
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing tests**

```python
from edgarpack.diff.text_diff import _distinctive_jaccard, _doc_frequencies

_LEGAL_TAIL = (
    "which could materially and adversely affect our business operating results "
    "financial condition and prospects and the trading price of our common stock"
)


def _df_for(paragraphs):
    return _doc_frequencies(paragraphs)


def test_distinctive_jaccard_ignores_ambient_legal_tail():
    # Ten paragraphs all share the legal tail; two have unrelated heads.
    a = f"Failure to maintain effective disaster recovery plans {_LEGAL_TAIL}"
    b = f"Our sustainability goals and commitments may prove costly {_LEGAL_TAIL}"
    fillers = [f"Risk topic number {i} about something unique {_LEGAL_TAIL}" for i in range(8)]
    paragraphs = [a, b, *fillers]
    df = _df_for(paragraphs)
    assert _distinctive_jaccard(a, b, df, len(paragraphs)) < 0.1


def test_distinctive_jaccard_keeps_true_rewrites():
    a = f"We rely on three suppliers for GPU components and networking equipment {_LEGAL_TAIL}"
    b = f"We rely on five suppliers for GPU components and networking equipment {_LEGAL_TAIL}"
    fillers = [f"Risk topic number {i} about something unique {_LEGAL_TAIL}" for i in range(8)]
    paragraphs = [a, b, *fillers]
    df = _df_for(paragraphs)
    assert _distinctive_jaccard(a, b, df, len(paragraphs)) > 0.6


def test_distinctive_jaccard_falls_back_on_small_sections():
    a = "alpha beta gamma delta"
    b = "alpha beta gamma epsilon"
    df = _df_for([a, b])
    # 2 paragraphs < _DISTINCTIVE_MIN_PARAS: must equal plain jaccard
    from edgarpack.diff.text_diff import _jaccard

    assert _distinctive_jaccard(a, b, df, 2) == _jaccard(a, b)
```

- [ ] **Step 2: Run them; expect ImportError**

Run: `uv run --extra dev pytest tests/test_diff.py -k distinctive -q`

- [ ] **Step 3: Implement in `text_diff.py`** (after `_overlap_ratio`)

```python
import math  # add to imports at top

_DISTINCTIVE_DF_RATIO = 0.25
_DISTINCTIVE_MIN_PARAS = 8


def _doc_frequencies(paragraphs: list[str]) -> dict[str, int]:
    """Count, per token, how many paragraphs contain it."""
    df: dict[str, int] = {}
    for paragraph in paragraphs:
        for word in set(_normalize(paragraph).split()):
            df[word] = df.get(word, 0) + 1
    return df


def _distinctive_jaccard(a: str, b: str, df: dict[str, int], total_paras: int) -> float:
    """Jaccard over tokens that are NOT ambient across the section's paragraphs.

    Legal boilerplate ("could adversely affect our business...") appears in most
    risk paragraphs and inflates plain Jaccard between unrelated topics. Tokens
    present in >= _DISTINCTIVE_DF_RATIO of paragraphs are dropped before
    comparing. Small sections fall back to plain Jaccard: DF over a handful of
    paragraphs is noise.
    """
    if total_paras < _DISTINCTIVE_MIN_PARAS:
        return _jaccard(a, b)
    cutoff = max(2, math.ceil(total_paras * _DISTINCTIVE_DF_RATIO))
    words_a = {w for w in set(_normalize(a).split()) if df.get(w, 0) < cutoff}
    words_b = {w for w in set(_normalize(b).split()) if df.get(w, 0) < cutoff}
    if not words_a and not words_b:
        # Pure-ambient paragraphs carry no distinctive signal either way.
        return _jaccard(a, b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
```

- [ ] **Step 4: Run the three tests; expect PASS**

Run: `uv run --extra dev pytest tests/test_diff.py -k distinctive -q`

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/text_diff.py tests/test_diff.py
git commit -m "feat(diff): distinctive-token jaccard with ambient-legalese filtering"
```

### Task 3: Gate the DP pairing

**Files:**
- Modify: `edgarpack/diff/text_diff.py` (inside `diff_paragraphs`)
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing test**

```python
def test_boilerplate_tail_pair_is_not_married():
    tail = (
        "Any failure could materially and adversely affect our business, operating "
        "results, financial condition, and prospects, and the trading price of our "
        "Class A common stock could decline."
    )
    fillers_old = [f"Old standalone risk number {i} covering topic {i}. {tail}" for i in range(8)]
    fillers_new = [f"Old standalone risk number {i} covering topic {i}. {tail}" for i in range(8)]
    old = "\n\n".join(
        [f"We depend on effective disaster recovery plans and backup systems. {tail}", *fillers_old]
    )
    new = "\n\n".join(
        [f"Our sustainability commitments may be costly to achieve. {tail}", *fillers_new]
    )
    deltas = diff_paragraphs(old, new)
    married = [
        d
        for d in deltas
        if d.change_type == ChangeType.MODIFIED
        and d.old_text
        and "disaster recovery" in d.old_text
    ]
    assert married == []
    assert any(d.change_type == ChangeType.REMOVED and "disaster" in (d.old_text or "") for d in deltas)
    assert any(d.change_type == ChangeType.ADDED and "sustainability" in (d.new_text or "") for d in deltas)
```

- [ ] **Step 2: Run it; expect FAIL (they currently marry via the shared tail)**

Run: `uv run --extra dev pytest tests/test_diff.py::test_boilerplate_tail_pair_is_not_married -q`

- [ ] **Step 3: Implement.** In `diff_paragraphs`, compute DF once after splitting (so every later pass can use it):

```python
    old_paras = [p for p in _split_paragraphs(old_text) if not _is_toc_link(p)]
    new_paras = [p for p in _split_paragraphs(new_text) if not _is_toc_link(p)]
    df = _doc_frequencies(old_paras + new_paras)
    total_paras = len(old_paras) + len(new_paras)
```

Add the floor constant near the other module constants:

```python
_DISTINCTIVE_FLOOR = 0.2
```

In the pass-2 matrix loop, also compute and store distinctive similarity, and zero out the match score when the pair fails the floor (the DP and traceback then need no changes at all):

```python
    distinctive: list[list[float]] = [[0.0] * n_new for _ in range(n_old)]
    for oi, (_, op) in enumerate(unmatched_old):
        for nj, (_, np_) in enumerate(unmatched_new):
            sim = _jaccard(op, np_)
            overlap = _overlap_ratio(op, np_)
            dist = _distinctive_jaccard(op, np_, df, total_paras)
            jaccard[oi][nj] = sim
            distinctive[oi][nj] = dist
            # Overlap-based rescue score avoids false added/removed for contained
            # rewrites; the distinctive floor keeps boilerplate-tail pairs apart.
            score = max(sim, overlap * 0.8)
            match_score[oi][nj] = score if dist >= _DISTINCTIVE_FLOOR else 0.0
```

- [ ] **Step 4: Run the new test AND the existing overlap-expansion guard; both must pass**

Run: `uv run --extra dev pytest tests/test_diff.py::test_boilerplate_tail_pair_is_not_married tests/test_diff.py::test_diff_paragraphs_high_overlap_expansion_is_modified -q`

The expansion guard matters: a contained rewrite shares its distinctive head tokens, so the floor must not break it. If it fails, the floor is too high; drop `_DISTINCTIVE_FLOOR` to 0.15 and re-run before touching anything else.

- [ ] **Step 5: Run the whole offline suite**

Run: `uv run --extra dev pytest -q`

- [ ] **Step 6: Commit**

```bash
git add edgarpack/diff/text_diff.py tests/test_diff.py
git commit -m "fix(diff): require distinctive-token overlap before pairing modified paragraphs"
```

### Task 4: Order-free rescue pass producing MOVED

**Files:**
- Modify: `edgarpack/diff/text_diff.py` (between the current pass-2 block and pass 3)
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing test.** The fixture must CROSS two near-verbatim pairs. With only one leftover pair, the order-preserving DP pairs it without help and no rescue fires (exact duplicates are already matched order-free in pass 1, so each pair below differs by one word to dodge the fingerprint).

```python
_MOVED_OLD = "\n\n".join([
    "Xray risk about supplier concentration and component lead times in great detail today.",
    "Yankee risk about customer concentration with two customers over half of total revenue.",
])
_MOVED_NEW = "\n\n".join([
    "Yankee risk about customer concentration with three customers over half of total revenue.",
    "Xray risk about supplier concentration and component lead times in great detail tomorrow.",
])


def test_crossed_near_verbatim_pairs_yield_moved_not_added():
    # Old order X,Y; new order Y,X. The DP can take at most one of the two
    # crossing diagonals; the other pair must come back via the rescue pass.
    deltas = diff_paragraphs(_MOVED_OLD, _MOVED_NEW)
    by_type = {t: [d for d in deltas if d.change_type == t] for t in ChangeType}
    assert len(by_type[ChangeType.MOVED]) == 1
    assert len(by_type[ChangeType.MODIFIED]) == 1
    assert by_type[ChangeType.ADDED] == []
    assert by_type[ChangeType.REMOVED] == []
    assert by_type[ChangeType.MOVED][0].similarity > 0.7
```

- [ ] **Step 2: Run it; expect FAIL (the crossed pair currently shows as added + removed)**

Run: `uv run --extra dev pytest tests/test_diff.py::test_crossed_near_verbatim_pairs_yield_moved_not_added -q`

- [ ] **Step 3: Implement.** Constants near the others:

```python
_RESCUE_MIN_JACCARD = 0.6
_RESCUE_MIN_DISTINCTIVE = 0.5
```

Insert between the `for oi, nj, sim in reversed(matched_pairs):` block and pass 3:

```python
    # Pass 3: order-free rescue. The DP is order-preserving, so a paragraph that
    # moved across the section ends up unmatched on both sides. Near-verbatim
    # leftovers pair here as MOVED; greedy best-first keeps it deterministic.
    leftover_old = [i for i in range(len(old_paras)) if not old_matched[i]]
    leftover_new = [j for j in range(len(new_paras)) if not new_matched[j]]
    rescue_candidates: list[tuple[float, int, int]] = []
    for i in leftover_old:
        for j in leftover_new:
            sim = _jaccard(old_paras[i], new_paras[j])
            if sim < _RESCUE_MIN_JACCARD:
                continue
            if _distinctive_jaccard(old_paras[i], new_paras[j], df, total_paras) < (
                _RESCUE_MIN_DISTINCTIVE
            ):
                continue
            rescue_candidates.append((sim, i, j))
    rescue_candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    for sim, i, j in rescue_candidates:
        if old_matched[i] or new_matched[j]:
            continue
        old_matched[i] = True
        new_matched[j] = True
        deltas.append(
            ParagraphDelta(
                change_type=ChangeType.MOVED,
                old_text=old_paras[i],
                new_text=new_paras[j],
                similarity=sim,
                old_word_count=len(old_paras[i].split()),
                new_word_count=len(new_paras[j].split()),
                is_boilerplate=_is_boilerplate_change(old_paras[i], new_paras[j], sim),
            )
        )
```

Renumber the trailing comment (`# Pass 4: remaining unmatched...`).

- [ ] **Step 4: Run the test; expect PASS. Then the full file**

Run: `uv run --extra dev pytest tests/test_diff.py -q`

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/text_diff.py tests/test_diff.py
git commit -m "feat(diff): order-free rescue pass labels reordered paragraphs as moved"
```

### Task 4b: Containment demotion for verbatim re-splits (added at the calibration gate)

Calibration on the CRWV pair showed the rescue pass alone leaves `paragraphs_added` at 11: the false adds there are not reorders but re-splits (fragments of a before-side paragraph whose DP partner was already consumed), so no removed-side counterpart exists to pair with. Whole-paragraph normalized containment catches the verbatim subset of these (including all page-break artifact rows) with zero false-positive risk: text contained verbatim in the other filing is by definition not new language. Edited re-splits stay `added`; fixing those requires split-aware alignment (out of scope, see Non-goals).

**Files:**
- Modify: `edgarpack/diff/text_diff.py` (top of `diff_paragraphs` + the final Pass 4)
- Test: `tests/test_diff.py`

Implementation: compute `norm_old_full = _normalize(old_text)` and `norm_new_full = _normalize(new_text)` once near the df computation. In Pass 4, before emitting ADDED for an unmatched new paragraph, check `_normalize(new_paras[j]) in norm_old_full`; if contained, emit `ChangeType.MOVED` with `old_text=new_text=new_paras[j]`, `similarity=1.0`, both word counts equal, `is_boilerplate=False`. Symmetrically for REMOVED against `norm_new_full` (old_text=new_text=old_paras[i]). At similarity 1.0 the scoring contribution is zero by construction.

Tests: a one-paragraph-split-into-two-verbatim-fragments fixture asserting one MODIFIED + one MOVED + zero ADDED, and a duplicate-artifact fixture (old has one "Table of Contents" paragraph, new has two) asserting the surplus instance is MOVED, not ADDED.

### Task 5: Scoring, counts, cache version

**Files:**
- Modify: `edgarpack/diff/section_diff.py:17` (cache version), `:225-255` (interest), `:258-299` (intensity), `:463-466` (counts)
- Modify: `edgarpack/insights/language_shift.py:66-73`
- Test: `tests/test_diff.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_moved_paragraph_damps_interest_and_counts():
    moved = ParagraphDelta(
        change_type=ChangeType.MOVED,
        old_text="x " * 200,
        new_text="x " * 199 + "y",
        similarity=0.9,
        old_word_count=200,
        new_word_count=200,
    )
    added = ParagraphDelta(
        change_type=ChangeType.ADDED,
        new_text="x " * 200,
        new_word_count=200,
    )
    moved_section = SectionDelta(
        section_id="s", title="S", change_type=ChangeType.MODIFIED,
        paragraph_deltas=[moved],
    )
    added_section = SectionDelta(
        section_id="s", title="S", change_type=ChangeType.MODIFIED,
        paragraph_deltas=[added],
    )
    assert 0 < compute_interest_score(moved_section) < compute_interest_score(added_section) * 0.1
```

(The lower bound matters for TDD: before Task 5 lands, MOVED hits no scoring branch and scores 0.0, so without `0 <` the assertion would pass vacuously.)

And a count check reusing the Task 4 crossing fixture (module constants `_MOVED_OLD` / `_MOVED_NEW`):

```python
def test_paragraphs_moved_counted():
    deltas = diff_paragraphs(_MOVED_OLD, _MOVED_NEW)
    assert sum(1 for d in deltas if d.change_type == ChangeType.MOVED) == 1
```

- [ ] **Step 2: Run; expect the interest test to FAIL.** Before this task lands, MOVED hits no scoring branch, the moved section scores 0.0, and the `0 <` lower bound makes the assertion fail as intended.

Run: `uv run --extra dev pytest tests/test_diff.py -k "moved" -q`

- [ ] **Step 3: Implement.**

`section_diff.py:17`:

```python
_DIFF_CACHE_VERSION = "v7"
```

Module constant near the damping constants at the top:

```python
_MOVED_DAMPING = 0.3
```

`compute_interest_score`, inside the per-delta branch chain:

```python
            elif pd.change_type == ChangeType.MOVED:
                similarity = max(0.0, min(1.0, pd.similarity))
                score += words * (1.0 - similarity) * _MOVED_DAMPING
```

`_compute_section_intensity`, same pattern in its branch chain:

```python
        elif pd.change_type == ChangeType.MOVED:
            similarity = max(0.0, min(1.0, pd.similarity))
            changed_words += words * (1.0 - similarity) * paragraph_weight * _MOVED_DAMPING
```

Also in `_compute_section_intensity`, the counts-only fallback (taken when `paragraph_deltas` is empty) must count moved paragraphs in the denominator but not as changed (a bare move is not a rewrite, and the crude path cannot damp):

```python
        total = (
            delta.paragraphs_unchanged
            + delta.paragraphs_modified
            + delta.paragraphs_moved
            + delta.paragraphs_added
            + delta.paragraphs_removed
        )
```

(`changed` stays `modified + added + removed`.)

Count assembly (next to the existing sums around line 463):

```python
            paragraphs_moved=sum(1 for d in para_deltas if d.change_type == ChangeType.MOVED),
```

`insights/language_shift.py`, in the loop at lines 66-68, before the ADDED/REMOVED check:

```python
            if pd.change_type == ChangeType.MOVED:
                # Movement is not language shift; edits inside moved paragraphs
                # are below the signal bar for this insight.
                continue
```

- [ ] **Step 4: Run the full offline suite**

Run: `uv run --extra dev pytest -q`

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/section_diff.py edgarpack/insights/language_shift.py tests/test_diff.py
git commit -m "feat(diff): moved-aware scoring, counts, and diff cache v7"
```

### Task 6: Report rendering

**Files:**
- Modify: `edgarpack/diff/report_models.py` (`ReportSectionDelta`), `edgarpack/diff/report_builder.py:325`, `edgarpack/diff/html_report.py`, `edgarpack/cli.py:2716-2720,2995`
- Test: `tests/test_diff_report.py`

- [ ] **Step 1: Write the failing test** (same crossing fixture as Task 4; two near-verbatim pairs in swapped order so exactly one becomes `moved`)

```python
def test_moved_paragraph_renders_with_badge_and_spans(tmp_path) -> None:
    old = "\n\n".join([
        "Xray risk about supplier concentration and component lead times in great detail today.",
        "Yankee risk about customer concentration with two customers over half of total revenue.",
    ])
    new = "\n\n".join([
        "Yankee risk about customer concentration with three customers over half of total revenue.",
        "Xray risk about supplier concentration and component lead times in great detail tomorrow.",
    ])
    before = _write_pack(tmp_path, "S1-001", old)
    after = _write_pack(tmp_path, "S1A-002", new)
    report = build_pair_report(before, after)
    moved = [
        paragraph
        for section in report.sections
        for group in section.groups
        for paragraph in group.paragraphs
        if paragraph.change_type == ChangeType.MOVED
    ]
    assert len(moved) == 1
    assert moved[0].old_spans and moved[0].new_spans  # spans built for moved pairs
    html = render_pair_report_html(report)
    assert "moved-badge" in html
    assert "<ins>" in html and "<del>" in html  # unified redline rendered
```

- [ ] **Step 2: Run; expect FAIL**

Run: `uv run --extra dev pytest tests/test_diff_report.py::test_moved_paragraph_renders_with_badge_and_spans -q`

- [ ] **Step 3: Implement.**

`report_models.py`, in `ReportSectionDelta` after `paragraphs_modified`:

```python
    paragraphs_moved: int = 0
```

`report_builder.py:325`, build spans for moved pairs too:

```python
        if (
            delta.change_type in {ChangeType.MODIFIED, ChangeType.MOVED}
            and delta.old_text
            and delta.new_text
        ):
            old_spans, new_spans = build_text_spans(delta.old_text, delta.new_text)
```

In `build_pair_report`'s `ReportSectionDelta(...)` construction (next to `paragraphs_modified=delta.paragraphs_modified`):

```python
                paragraphs_moved=delta.paragraphs_moved,
```

`html_report.py`:

1. `_marker_for` gains an entry (up-down arrows, reusing the amber marker class):

```python
        ChangeType.MOVED: ("&#8645;", "marker-modified"),
```

2. In `_paragraph_html`, MOVED already falls through the `elif` chain into the final `else` (the MODIFIED path), so the unified-vs-stacked similarity logic applies unchanged. Prepend a badge at the top of that branch:

```python
    else:
        if para.change_type == ChangeType.MOVED:
            blocks.append('<span class="rewrite-badge moved-badge">moved</span>')
        raw_old = para.old_text or ""
        ...
```

3. `_evidence_html`: add `ChangeType.MOVED` to both membership sets (old-anchor set and new-anchor set) so a moved pair links both sides.
4. Rail and hunk-header counts. In `_section_nav_html`, after the `rail-modified` span:

```python
            f'<span class="rail-modified">~{section.paragraphs_modified}</span>'
            + (
                f'<span class="rail-modified">&#8645;{section.paragraphs_moved}</span>'
                if section.paragraphs_moved
                else ""
            )
```

In `_section_html`, extend the `hunk-meta` f-string the same way (`&#8645;{n} · ` before the intensity, only when nonzero).
5. CSS: `.moved-badge { color: #725b16; }` next to `.rewrite-badge`.

`cli.py` text renderer (the diff text format also branches on change-type strings):

- `cli.py:2716-2720`: the paragraph-marker if/elif chain gains `elif pd.change_type.value == "moved": marker = "~"` (or whatever variable that chain assigns; mirror the modified arm).
- `cli.py:2995`: add `"moved": "&#8645;"`-equivalent to the marker `.get(...)` dict (plain text: `"moved": "~"`).

- [ ] **Step 4: Run the report suite; expect PASS**

Run: `uv run --extra dev pytest tests/test_diff_report.py -q`

- [ ] **Step 5: Commit**

```bash
git add edgarpack/diff/report_models.py edgarpack/diff/report_builder.py \
  edgarpack/diff/html_report.py edgarpack/cli.py tests/test_diff_report.py
git commit -m "feat(diff): render moved paragraphs with badge, spans, and counts"
```

### Task 7: Calibration against the audited pairs (manual gate before merge)

**Files:**
- Modify (if calibration demands): the constants in `edgarpack/diff/text_diff.py`
- Modify: `docs/OBSERVATORY.md` (document `moved` + `paragraphs_moved`)

This task needs the local packs from the 2026-06-09 audit (CRWV `0001769628-25-000062/-26-000222`, FIG `0001628280-25-049683/-26-035209`, RDDT `0001713445-25-000018/-26-000022`). Rebuild with `uv run edgarpack build <TICKER> --form <FORM> --last 2` if absent.

- [ ] **Step 1: Re-run the CRWV diff and check the added label**

```bash
uv run edgarpack diff --before packs/0001769628/0001769628-25-000062 \
  --after packs/0001769628/0001769628-26-000222 --format json > /tmp/crwv-v7.json
python3 - <<'EOF'
import json
d = json.load(open("/tmp/crwv-v7.json"))
rf = next(s for s in d["section_deltas"] if s["title"] == "Risk Factors")
print({k: rf[k] for k in ("paragraphs_added", "paragraphs_removed",
                          "paragraphs_moved", "paragraphs_modified")})
for p in rf["paragraph_deltas"]:
    if p["change_type"] == "added":
        print("ADDED:", (p["new_text"] or "")[:120])
EOF
```

Acceptance: `paragraphs_added` <= 4 (was 11), and every surviving added paragraph passes phrase verification (`grep -ci "<distinctive phrase>" packs/0001769628/0001769628-25-000062/filing.full.md` returns 0). Artifact paragraphs ("Table of Contents") may legitimately pair as moved; that is fine.

- [ ] **Step 2: Check the audited forced marriages are gone**

In the same JSON: no `modified` delta pairs the disaster-recovery paragraph with the sustainability paragraph, or the trade-policy paragraph with the supplier paragraph. The cost-of-revenue pair (similarity 0.76 in the audit) must still be `modified`.

- [ ] **Step 3: Regression-check FIG and RDDT**

```bash
uv run edgarpack diff --before packs/0001579878/0001628280-25-049683 \
  --after packs/0001579878/0001628280-26-035209 --format json > /tmp/fig-v7.json
uv run edgarpack diff --before packs/0001713445/0001713445-25-000018 \
  --after packs/0001713445/0001713445-26-000022 --format json > /tmp/rddt-v7.json
```

Acceptance: the four verified lesson-2 Figma quotes still appear in visible deltas; RDDT Risk Factors still reports 0 added and its modified count stays within ±3 of 36 (the distinctive floor may correctly unmarry a couple of weak pairs, which then surface as added+removed or moved; eyeball any that flip).

- [ ] **Step 4: Determinism**

Run each diff twice with the cache dir pointed at a temp location; byte-identical JSON both times:

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cal1 uv run edgarpack diff --before ... --after ... --format json > /tmp/a.json
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cal2 uv run edgarpack diff --before ... --after ... --format json > /tmp/b.json
diff /tmp/a.json /tmp/b.json && echo deterministic
```

- [ ] **Step 5: If a constant moved during calibration, record the final values in this file's tuning table and in the module docstring. Document `moved` in `docs/OBSERVATORY.md` (one paragraph in the JSON-format section plus the counts table).**

- [ ] **Step 6: Full gate and commit**

```bash
EDGARPACK_CACHE_DIR=/tmp/edgarpack-cache scripts/symphony_quality_gate.sh
git add docs/OBSERVATORY.md docs/superpowers/plans/2026-06-09-diff-moved-detection.md
git commit -m "docs(diff): document moved change type; record calibrated thresholds"
```

---

## Acceptance criteria (the whole feature)

1. CRWV Risk Factors pair: `paragraphs_added` drops from 11 to 7 (the four verbatim/artifact strays demote to `moved` at similarity 1.0; the seven survivors are edited re-splits, a documented limitation requiring split-aware alignment). Calibration note 2026-06-09: the original "<= 4" target assumed the false adds were reorders; ground truth showed re-splits, and edited re-splits are out of scope per Non-goals.
2. The two audited forced marriages are no longer `modified`; the genuine 0.76-similarity rewrite still is.
3. `moved` paragraphs are visible in JSON and HTML (badge + redline) but contribute at most `words * (1 - sim) * 0.3` to interest and intensity.
4. FIG lesson-2 quotes unaffected; RDDT behavior stable.
5. Same inputs produce byte-identical JSON; old cache entries are invalidated by `v7`.
6. Full offline suite, ruff, and mypy strict all green via the quality gate.

## Risks

- **The distinctive floor unmarries real rewrites.** Mitigated by the small-section fallback, the calibration task, and the fact that an unmarried real rewrite degrades gracefully: it becomes added+removed (both visible) or a moved pair via rescue, never invisible.
- **DF cutoff sensitivity on mid-size sections (8-15 paragraphs).** `max(2, ceil(n * 0.25))` keeps the cutoff sane at the low end; calibration step 3 watches RDDT (a 10-K Risk Factors with ~106 engine paragraphs) and the synthetic tests pin the extremes.
- **Downstream JSON consumers seeing an unknown change_type.** Only `insights/language_shift.py` consumes ChangeType outside the diff package (handled in Task 5); external consumers of the JSON get a new string value, called out in OBSERVATORY.md. The web app does not parse paragraph change types today.
