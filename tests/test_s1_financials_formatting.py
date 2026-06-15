"""Output shaping: inline S-1 citation marker in the table renderer and
source/accession/is_pro_forma passthrough in the JSON renderer."""

from datetime import date
from types import SimpleNamespace

from edgarpack.query.formatting import format_citation_marker
from edgarpack.query.models import CitedValue, QueryResult


def _snapshot_cv(is_pro_forma: bool = False) -> CitedValue:
    return CitedValue(
        value=78287000,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="S-1",
        filed=date(2024, 9, 30),
        accession="0001628280-24-041596",
        cik="0002021728",
        company="Cerebras Systems Inc.",
        source="s1_pro_forma" if is_pro_forma else "s1_snapshot",
        is_pro_forma=is_pro_forma,
        pro_forma_note=("assumes IPO price $32.50" if is_pro_forma else None),
    )


def test_format_citation_marker_snapshot():
    marker = format_citation_marker(_snapshot_cv(is_pro_forma=False))
    assert "[S-1" in marker
    assert "24-041596" in marker


def test_format_citation_marker_pro_forma():
    marker = format_citation_marker(_snapshot_cv(is_pro_forma=True))
    assert "*" in marker or "pro-forma" in marker.lower()


def test_format_citation_marker_uses_registration_form_type():
    cv = _snapshot_cv(is_pro_forma=False)
    cv.form_type = "F-1"
    marker = format_citation_marker(cv)
    assert marker == "[F-1, 24-041596]"


def test_format_citation_marker_10k_returns_empty():
    cv = CitedValue(
        value=100,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2025, 2, 1),
        accession="0000320193-25-000006",
        cik="0000320193",
        company="Apple Inc.",
        source="hardcoded",
    )
    assert "[S-1" not in format_citation_marker(cv)


def test_cited_value_json_includes_s1_fields():
    cv = _snapshot_cv(is_pro_forma=True)
    dumped = cv.model_dump()
    assert dumped["source"] == "s1_pro_forma"
    assert dumped["is_pro_forma"] is True
    assert dumped["pro_forma_note"] == "assumes IPO price $32.50"
    assert dumped["accession"] == "0001628280-24-041596"


def test_source_badge_surfaces_snapshot_marker():
    """_source_badge_for must route s1_snapshot / s1_pro_forma sources through
    format_citation_marker so the rendered table text carries the inline
    [S-1, ...] citation. Without this wiring the marker function is dead code."""
    from edgarpack.cli import _source_badge_for

    snapshot_cv = _snapshot_cv(is_pro_forma=False)
    badge = _source_badge_for(snapshot_cv)
    assert "[S-1" in badge
    assert "24-041596" in badge


def test_source_badge_marks_pro_forma_with_star():
    from edgarpack.cli import _source_badge_for

    pf_cv = _snapshot_cv(is_pro_forma=True)
    badge = _source_badge_for(pf_cv)
    assert "pro-forma" in badge.lower()
    assert "*" in badge


def test_source_badge_returns_empty_for_no_api_key_placeholder():
    """no_api_key placeholder rows stay quiet: the stderr hint from
    _cmd_query tells the user what to do; the table cell itself just
    shows N/A without a confusing badge."""
    from edgarpack.cli import _source_badge_for

    placeholder = CitedValue(
        value=None,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=0,
        fiscal_period="FY",
        form_type="S-1",
        filed=date(2024, 9, 30),
        accession="",
        cik="0002021728",
        company="Cerebras Systems Inc.",
        source="no_api_key",
    )
    assert _source_badge_for(placeholder) == ""


def test_no_api_key_placeholder_filing_url_is_empty():
    """CitedValue.filing_url must not emit a broken URL for placeholder
    rows with empty accession/cik."""
    placeholder = CitedValue(
        value=None,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2024, 12, 31),
        fiscal_year=0,
        fiscal_period="FY",
        form_type="S-1",
        filed=date(2024, 9, 30),
        accession="",
        cik="",
        company="",
        source="no_api_key",
    )
    assert placeholder.filing_url == ""


def test_render_query_table_no_api_key_placeholder_has_no_citation_marker():
    from edgarpack.cli import _render_query_table

    placeholder = CitedValue(
        value=None,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2026, 6, 8),
        fiscal_year=0,
        fiscal_period="FY",
        form_type="F-1",
        filed=date(2026, 6, 8),
        accession="",
        cik="0002004711",
        company="Bending Spoons S.p.A.",
        source="no_api_key",
    )
    result = QueryResult(
        company="Bending Spoons S.p.A.",
        cik="0002004711",
        period="lfy",
        metrics={"revenue": placeholder},
    )
    args = SimpleNamespace(
        currency="native",
        strict=False,
        citations="inline",
        audit=False,
        show_links="none",
        packs="/tmp/bending-f1-test",
    )

    out = _render_query_table(result, args)

    assert "Revenue: N/A" in out
    assert "[C1]" not in out
    assert "--packs /tmp/bending-f1-test" in out
