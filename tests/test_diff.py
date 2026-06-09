"""Tests for the diff engine."""

import json
import tempfile
from pathlib import Path

import pytest

from edgarpack.diff import section_diff as section_diff_module
from edgarpack.diff.models import ChangeType, ParagraphDelta, SectionDelta
from edgarpack.diff.section_diff import diff_filings
from edgarpack.diff.text_diff import (
    _distinctive_jaccard,
    _doc_frequencies,
    _is_cross_reference,
    _is_toc_link,
    _jaccard,
    _split_paragraphs,
    diff_paragraphs,
)
from edgarpack.parse.sectionize import find_sections

# --- text_diff tests ---


def test_jaccard_identical():
    assert _jaccard("hello world", "hello world") == 1.0


def test_jaccard_disjoint():
    assert _jaccard("hello world", "foo bar") == 0.0


def test_jaccard_partial():
    sim = _jaccard("hello world foo", "hello world bar")
    assert 0.3 < sim < 0.8


def test_jaccard_empty():
    assert _jaccard("", "") == 1.0
    assert _jaccard("hello", "") == 0.0


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
    assert _distinctive_jaccard(a, b, df, 2) == _jaccard(a, b)


def test_split_paragraphs():
    text = "First paragraph.\n\nSecond paragraph.\n\n\nThird paragraph."
    paras = _split_paragraphs(text)
    assert len(paras) == 3
    assert paras[0] == "First paragraph."
    assert paras[1] == "Second paragraph."
    assert paras[2] == "Third paragraph."


def test_diff_paragraphs_identical():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    deltas = diff_paragraphs(text, text)
    assert all(d.change_type == ChangeType.UNCHANGED for d in deltas)
    assert len(deltas) == 3


def test_diff_paragraphs_added():
    old = "Paragraph one.\n\nParagraph two."
    new = "Paragraph one.\n\nParagraph two.\n\nBrand new paragraph."
    deltas = diff_paragraphs(old, new)
    added = [d for d in deltas if d.change_type == ChangeType.ADDED]
    assert len(added) == 1
    assert "Brand new" in added[0].new_text


def test_diff_paragraphs_removed():
    old = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    new = "Paragraph one.\n\nParagraph three."
    deltas = diff_paragraphs(old, new)
    removed = [d for d in deltas if d.change_type == ChangeType.REMOVED]
    assert len(removed) == 1
    assert "two" in removed[0].old_text


def test_diff_paragraphs_modified():
    old = "The company faces significant risk from export controls.\n\nOther risk factors apply."
    new = (
        "The company faces major risk from new export control regulations."
        "\n\nOther risk factors apply."
    )
    deltas = diff_paragraphs(old, new)
    modified = [d for d in deltas if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert modified[0].similarity > 0.4


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
        if d.change_type == ChangeType.MODIFIED and d.old_text and "disaster recovery" in d.old_text
    ]
    assert married == []
    assert any(
        d.change_type == ChangeType.REMOVED and "disaster" in (d.old_text or "") for d in deltas
    )
    assert any(
        d.change_type == ChangeType.ADDED and "sustainability" in (d.new_text or "") for d in deltas
    )


def test_diff_paragraphs_high_overlap_expansion_is_modified():
    old = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    new = (
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
        "nu xi omicron pi rho sigma tau upsilon phi chi psi omega"
    )
    deltas = diff_paragraphs(old, new)

    modified = [d for d in deltas if d.change_type == ChangeType.MODIFIED]
    added = [d for d in deltas if d.change_type == ChangeType.ADDED]
    removed = [d for d in deltas if d.change_type == ChangeType.REMOVED]

    assert len(modified) == 1
    assert len(added) == 0
    assert len(removed) == 0
    assert modified[0].similarity <= 0.5


def test_moved_change_type_exists():
    assert ChangeType.MOVED.value == "moved"
    delta = SectionDelta(section_id="s", title="S", change_type=ChangeType.MODIFIED)
    assert delta.paragraphs_moved == 0


# --- section_diff tests ---


def _create_pack(
    pack_dir: Path,
    accession: str,
    filing_date: str,
    company_name: str,
    form_type: str,
    sections: dict[str, str],
) -> None:
    """Create a minimal pack directory for testing."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    sections_dir = pack_dir / "sections"
    sections_dir.mkdir(exist_ok=True)

    from edgarpack.pack.manifest import compute_sha256

    section_list = []
    for sid, content in sections.items():
        section_path = sections_dir / f"{sid}.md"
        section_path.write_text(content, encoding="utf-8")
        section_list.append(
            {
                "id": sid,
                "title": sid.replace("_", " ").title(),
                "path": f"sections/{sid}.md",
                "char_start": 0,
                "char_end": len(content),
                "tokens_approx": len(content.split()),
                "sha256": compute_sha256(content),
            }
        )

    manifest = {
        "schema_version": 1,
        "filing": {
            "cik": "0001045810",
            "accession": accession,
            "form_type": form_type,
            "filing_date": filing_date,
            "company_name": company_name,
        },
        "sections": section_list,
        "artifacts": {},
        "warnings": [],
        "tokens_total": sum(s["tokens_approx"] for s in section_list),
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_diff_filings_identical():
    with tempfile.TemporaryDirectory() as tmp:
        sections = {
            "10k_parti_item1_business": "This is the business section.\n\nIt has two paragraphs.",
            "10k_parti_item1a_risk_factors": "Risk factors are discussed here.",
        }
        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_unchanged == 2
        assert result.sections_modified == 0
        assert result.overall_change_intensity == 0.0


def test_diff_filings_modified():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Old business description.\n\nOld second paragraph.",
            "10k_parti_item1a_risk_factors": "Original risk factors.",
        }
        after_sections = {
            "10k_parti_item1_business": (
                "New business description with changes.\n\nOld second paragraph."
            ),
            "10k_parti_item1a_risk_factors": "Original risk factors.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_unchanged == 1  # risk factors unchanged
        assert result.sections_modified == 1  # business modified
        assert result.overall_change_intensity > 0


def test_diff_filings_added_section():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Business section.",
        }
        after_sections = {
            "10k_parti_item1_business": "Business section.",
            "10k_parti_item1a_risk_factors": "New risk section.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_added == 1
        assert result.sections_unchanged == 1


def test_diff_filings_removed_section():
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Business section.",
            "10k_parti_item1a_risk_factors": "Old risk section.",
        }
        after_sections = {
            "10k_parti_item1_business": "Business section.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        assert result.sections_removed == 1


def test_intensity_reflects_similarity():
    with tempfile.TemporaryDirectory() as tmp:
        before_text = (
            "For the fiscal year ended January 28, 2024, we maintained supply chain "
            "resilience through multi-sourcing and inventory discipline."
        )
        after_text = (
            "For the fiscal year ended January 26, 2025, we maintained supply chain "
            "resilience through multi-sourcing and inventory discipline."
        )

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(
            before_dir,
            "acc-001",
            "2024-01-01",
            "Test Corp",
            "10-K",
            {"10k_parti_item1_business": before_text},
        )
        _create_pack(
            after_dir,
            "acc-002",
            "2025-01-01",
            "Test Corp",
            "10-K",
            {"10k_parti_item1_business": after_text},
        )

        result = diff_filings(before_dir, after_dir)
        modified = next(d for d in result.section_deltas if d.change_type == ChangeType.MODIFIED)
        assert modified.change_intensity < 0.10


def test_boilerplate_date_change():
    old = (
        "For the fiscal year ended January 28, 2024, we continued to invest in product "
        "engineering, customer support, and operational resilience, and we refer to Item 7 "
        "of our Annual Report for a broader discussion."
    )
    new = (
        "For the fiscal year ended January 26, 2025, we continued to invest in product "
        "engineering, customer support, and operational resilience, and we refer to Item 7 "
        "of our Annual Report for a broader discussion."
    )

    deltas = diff_paragraphs(old, new)
    modified = [d for d in deltas if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert modified[0].is_boilerplate is True


def test_interest_score_ranks_substance():
    with tempfile.TemporaryDirectory() as tmp:
        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"

        before_sections = {
            "10k_parti_item1_business": (
                "For the fiscal year ended January 28, 2024, see Item 7 of our Annual Report."
            ),
            "10k_parti_item1a_risk_factors": (
                "We face competition in AI chips.\n\nSupply constraints could impact deliveries."
            ),
        }
        after_sections = {
            "10k_parti_item1_business": (
                "For the fiscal year ended January 26, 2025, see Item 7 of our Annual Report."
            ),
            "10k_parti_item1a_risk_factors": (
                "We face heightened competition in AI and accelerated computing chips.\n\n"
                "New export controls and licensing requirements may materially constrain sales."
            ),
        }

        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
        deltas = {d.section_id: d for d in result.section_deltas}
        assert (
            deltas["10k_parti_item1a_risk_factors"].interest_score
            > deltas["10k_parti_item1_business"].interest_score
        )
        assert result.section_deltas[0].section_id == "10k_parti_item1a_risk_factors"


def test_boilerplate_is_excluded_from_intensity_denominator():
    delta = SectionDelta(
        section_id="10k_parti_item1_business",
        title="Business",
        change_type=ChangeType.MODIFIED,
        paragraph_deltas=[
            ParagraphDelta(
                change_type=ChangeType.MODIFIED,
                old_text="For the fiscal year ended January 28, 2024.",
                new_text="For the fiscal year ended January 26, 2025.",
                old_word_count=9,
                new_word_count=9,
                similarity=0.95,
                is_boilerplate=True,
            ),
            ParagraphDelta(
                change_type=ChangeType.MODIFIED,
                old_text="We expanded into new verticals and signed channel partners.",
                new_text=(
                    "We expanded into enterprise verticals and signed global channel partners."
                ),
                old_word_count=9,
                new_word_count=10,
                similarity=0.5,
            ),
        ],
    )

    intensity = section_diff_module._compute_section_intensity(delta)
    assert intensity == pytest.approx(0.5)


def test_corrupted_diff_cache_recovers(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        monkeypatch.setattr(section_diff_module, "_DIFF_CACHE_DIR", tmp_path / "diff_cache")

        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        _create_pack(
            before_dir,
            "acc-001",
            "2024-01-01",
            "Test Corp",
            "10-K",
            {"10k_parti_item1_business": "Old business text."},
        )
        _create_pack(
            after_dir,
            "acc-002",
            "2025-01-01",
            "Test Corp",
            "10-K",
            {"10k_parti_item1_business": "New business text with meaningful changes."},
        )

        first = diff_filings(before_dir, after_dir)
        key = section_diff_module._cache_key(
            section_diff_module._load_manifest(before_dir),
            section_diff_module._load_manifest(after_dir),
        )
        cache_file = section_diff_module._DIFF_CACHE_DIR / f"{key}.json"
        cache_file.write_text("{not-valid-json", encoding="utf-8")

        second = diff_filings(before_dir, after_dir)
        assert second.sections_modified == 1
        assert second.section_deltas[0].section_id == first.section_deltas[0].section_id
        assert second.section_deltas[0].change_type == first.section_deltas[0].change_type


def test_canonical_title_fallback():
    md = (
        "ITEM 1A. RISK FACTORSFor a discussion of this Annual Report on Form 10-K for "
        "additional information.\n\nBody text."
    )
    matches = find_sections(md, "10-K")
    assert matches
    assert matches[0].item == "1A"
    assert matches[0].title == "Risk Factors"


def test_repeated_toc_title_falls_back_to_canonical_title():
    md = "Item 1. Item 1. / Item 1. / Business / Business / Business / 4 / 4 / 4\n\nBody text."
    matches = find_sections(md, "10-K")
    assert matches
    assert matches[0].item == "1"
    assert matches[0].title == "Business"


def test_diff_display_title_normalizes_legacy_repeated_toc_title():
    title = "/ Form 10-K Summary / Form 10-K Summary / Form 10-K Summary / 83 / 83 / 83"

    assert section_diff_module._display_title("10k_partiv_item16_form_10k_summary", title) == (
        "Form 10-K Summary"
    )


# --- TOC link filtering tests ---


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
    assert len(deltas) == 2
    assert all(d.change_type == ChangeType.UNCHANGED for d in deltas)


# --- Cross-reference and boilerplate tests ---


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


# --- Section fallback matching tests ---


def test_fallback_matching_across_parts():
    """Sections that move between parts should match, not show as added+removed."""
    with tempfile.TemporaryDirectory() as tmp:
        content = (
            "Management discusses results of operations.\n\nRevenue increased 20% year over year."
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
        assert result.sections_added == 0
        assert result.sections_removed == 0
        assert result.sections_unchanged == 2


def test_fallback_matching_ambiguous_skipped():
    """When multiple sections share the same reduced key, skip fallback matching."""
    with tempfile.TemporaryDirectory() as tmp:
        before_sections = {
            "10k_parti_item1_business": "Business A.",
            "10k_partii_item1_business": "Business B.",
        }
        after_sections = {
            "10k_partiii_item1_business": "Business C.",
            "10k_partiv_item1_business": "Business D.",
        }

        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        _create_pack(before_dir, "acc-001", "2024-01-01", "Test Corp", "10-K", before_sections)
        _create_pack(after_dir, "acc-002", "2025-01-01", "Test Corp", "10-K", after_sections)

        result = diff_filings(before_dir, after_dir)
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


# --- Section suppression tests ---


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
        section_ids = [d.section_id for d in result.section_deltas]
        assert "10k_partii_item8_financial_statements" not in section_ids
        assert "10k_parti_item1_business" in section_ids
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
        delta = next(d for d in result.section_deltas if d.change_type == ChangeType.MODIFIED)
        # No boilerplate paragraphs should be in the deltas at all
        assert all(not pd.is_boilerplate for pd in delta.paragraph_deltas)
        # Should have at least one visible modified paragraph
        assert delta.paragraphs_modified >= 1
