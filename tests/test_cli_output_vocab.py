"""CLI output vocabulary: filing (not accn), [discovered] (not raw taxonomy tag)."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestCitationRendererVocab:
    def test_citation_uses_filing_not_accn(self) -> None:
        from edgarpack.cli import _render_citation_lines

        record = {
            "form_type": "10-K",
            "fiscal_label": "FY2025",
            "period": "2025-12-31",
            "accession": "0001564408-26-000013",
            "filed": "2026-02-05",
        }
        lines = _render_citation_lines(
            "C1",
            record,
            show_links="off",
            width=120,
        )
        joined = "\n".join(lines)
        assert "filing 0001564408-26-000013" in joined
        assert "accn" not in joined


class TestSourceBadgeVocab:
    def test_discovered_kpi_collapses_to_discovered_badge(self) -> None:
        from edgarpack.cli import _source_badge_for

        cited = MagicMock()
        cited.source = "learned:kpi-discovered"
        cited.warnings = []
        assert _source_badge_for(cited) == " [discovered]"

    def test_discovered_kpi_cached_also_collapses(self) -> None:
        from edgarpack.cli import _source_badge_for

        cited = MagicMock()
        cited.source = "learned:kpi-cached"
        cited.warnings = []
        assert _source_badge_for(cited) == " [discovered]"

    def test_learned_llm_keeps_compact_form(self) -> None:
        from edgarpack.cli import _source_badge_for

        cited = MagicMock()
        cited.source = "learned:llm"
        cited.warnings = []
        assert _source_badge_for(cited) == " [learned:llm ✓]"

    def test_hardcoded_returns_empty(self) -> None:
        from edgarpack.cli import _source_badge_for

        cited = MagicMock()
        cited.source = "hardcoded"
        cited.warnings = []
        assert _source_badge_for(cited) == ""

    def test_unverified_warning_swaps_check_for_warn(self) -> None:
        from edgarpack.cli import _source_badge_for

        cited = MagicMock()
        cited.source = "learned:llm"
        cited.warnings = ["unverified: value not cross-checked"]
        assert _source_badge_for(cited) == " [learned:llm ⚠]"
