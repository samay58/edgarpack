"""Map SnapshotFact → CitedValue for insertion into QueryResult."""

from datetime import date

from edgarpack.query.models import CitedValue
from edgarpack.query.s1_financials import (
    SnapshotFact,
    pick_snapshot_fact,
    snapshot_fact_to_cited_value,
    snapshots_for_cik,
)


def test_snapshot_fact_to_cited_value_preserves_core_fields():
    fact = SnapshotFact(
        accession="0001628280-24-041596",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="revenue",
        value_cents=7828700000,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
        source_text="Revenue ... $78,287",
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="0002021728",
        company="Cerebras Systems Inc.",
        form_type="S-1",
        filed=date(2024, 9, 30),
        concept="Revenues",
    )
    assert isinstance(cv, CitedValue)
    assert cv.metric == "revenue"
    assert cv.value == 78287000.0
    assert cv.unit == "USD"
    assert cv.fiscal_year == 2024
    assert cv.fiscal_period == "FY"
    assert cv.form_type == "S-1"
    assert cv.accession == "0001628280-24-041596"
    assert cv.cik == "0002021728"
    assert cv.source == "s1_snapshot"
    assert cv.is_pro_forma is False
    assert cv.excerpt_text == "Revenue ... $78,287"
    assert cv.to_lean_metric()["excerpt_text"] == "Revenue ... $78,287"
    citation = cv.to_citation_record("C1")
    assert citation["excerpt_text"] == "Revenue ... $78,287"


def test_snapshot_fact_to_cited_value_marks_pro_forma_source():
    fact = SnapshotFact(
        accession="0001628280-26-025762",
        fiscal_year=2025,
        period_end="2025-12-31",
        metric="cash_and_equivalents",
        value_cents=124310000000,
        currency="USD",
        is_audited=False,
        is_pro_forma=True,
        pro_forma_note="assumes IPO price $32.50, midpoint",
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="0002021728",
        company="Cerebras Systems Inc.",
        form_type="S-1",
        filed=date(2026, 4, 17),
        concept="CashAndCashEquivalentsAtCarryingValue",
    )
    assert cv.source == "s1_pro_forma"
    assert cv.is_pro_forma is True
    assert cv.pro_forma_note == "assumes IPO price $32.50, midpoint"


def test_snapshot_fact_to_cited_value_per_share_unit():
    fact = SnapshotFact(
        accession="x",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="eps_basic",
        value_cents=-108,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="x",
        company="Test",
        form_type="S-1",
        filed=date(2024, 9, 30),
        concept="EarningsPerShareBasic",
    )
    assert cv.value == -1.08
    assert cv.unit == "USD/shares"


def test_snapshot_fact_to_cited_value_shares_unit():
    fact = SnapshotFact(
        accession="x",
        fiscal_year=2024,
        period_end="2024-12-31",
        metric="shares_outstanding_basic",
        value_cents=24012345600,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="x",
        company="Test",
        form_type="S-1",
        filed=date(2024, 9, 30),
        concept="WeightedAverageNumberOfSharesOutstandingBasic",
    )
    assert cv.value == 240123456.0
    assert cv.unit == "shares"


def test_snapshot_fact_to_cited_value_absent_period_end_yields_none():
    # fix: bare-year-absent-period. A bare-year FY fact carries no period_end
    # (empty string in the snapshot row); the CitedValue must render that as
    # None rather than fabricating a December year-end.
    fact = SnapshotFact(
        accession="a",
        fiscal_year=2026,
        period_end="",
        metric="revenue",
        value_cents=100,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    cv = snapshot_fact_to_cited_value(
        fact,
        cik="x",
        company="Test",
        form_type="S-1",
        filed=date(2026, 4, 17),
        concept="Revenues",
    )
    assert cv.period_end is None
    assert cv.fiscal_year == 2026


def test_pick_snapshot_fact_lfy_resolves_with_absent_period_end():
    # fiscal_year still drives lfy/lfy-N selection when period_end is absent.
    facts = [
        SnapshotFact("a", 2024, "", "revenue", 90, "USD", True, False, None),
        SnapshotFact("a", 2025, "", "revenue", 100, "USD", True, False, None),
    ]
    picked = pick_snapshot_fact(facts, metric="revenue", period="lfy")
    assert picked is not None
    assert picked.fiscal_year == 2025
    assert picked.value_cents == 100

    prior = pick_snapshot_fact(facts, metric="revenue", period="lfy-1")
    assert prior is not None
    assert prior.fiscal_year == 2024


def test_pick_snapshot_fact_mrp_resolves_with_absent_period_end():
    facts = [SnapshotFact("a", 2025, "", "revenue", 100, "USD", True, False, None)]
    picked = pick_snapshot_fact(facts, metric="revenue", period="mrp")
    assert picked is not None
    assert picked.value_cents == 100


def test_pick_snapshot_fact_lfy_returns_latest_audited():
    facts = [
        SnapshotFact("a", 2023, "2023-12-31", "revenue", 100, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 200, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 999, "USD", False, True, "assume"),
    ]
    picked = pick_snapshot_fact(facts, metric="revenue", period="lfy")
    assert picked is not None
    assert picked.value_cents == 200
    assert picked.is_pro_forma is False


def test_pick_snapshot_fact_lfy_minus_1():
    facts = [
        SnapshotFact("a", 2023, "2023-12-31", "revenue", 100, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 200, "USD", True, False, None),
    ]
    picked = pick_snapshot_fact(facts, metric="revenue", period="lfy-1")
    assert picked is not None
    assert picked.value_cents == 100


def test_pick_snapshot_fact_pro_forma_returns_only_pro_forma_rows():
    facts = [
        SnapshotFact("a", 2024, "2024-12-31", "cash_and_equivalents", 1, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "cash_and_equivalents", 999, "USD", False, True, "x"),
    ]
    picked = pick_snapshot_fact(facts, metric="cash_and_equivalents", period="pro-forma")
    assert picked is not None
    assert picked.is_pro_forma is True
    assert picked.value_cents == 999


def test_pick_snapshot_fact_lfy_excludes_pro_forma_and_unaudited():
    facts = [
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 999, "USD", False, True, "pro"),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 77, "USD", False, False, None),
    ]
    assert pick_snapshot_fact(facts, metric="revenue", period="lfy") is None


def test_pick_snapshot_fact_mrp_returns_latest_interim_even_when_unaudited():
    # Fix 6 (audited-honesty): interim columns now carry is_audited=False, so
    # mrp selection must NOT filter on is_audited or it would skip the most
    # recent (interim) period. Proves mrp still resolves after the honest flag.
    facts = [
        SnapshotFact("a", 2025, "2025-12-31", "revenue", 500, "USD", True, False, None),
        SnapshotFact(
            "a", 2026, "2026-03-31", "revenue", 130, "USD", False, False, None, fiscal_period="Q1"
        ),
    ]
    picked = pick_snapshot_fact(facts, metric="revenue", period="mrp")
    assert picked is not None
    assert picked.period_end == "2026-03-31"
    assert picked.fiscal_period == "Q1"
    assert picked.is_audited is False
    # lfy still skips the unaudited interim and returns the audited FY.
    lfy = pick_snapshot_fact(facts, metric="revenue", period="lfy")
    assert lfy is not None
    assert lfy.period_end == "2025-12-31"


def test_snapshots_for_cik_walks_pack_root_and_filters_by_cik(tmp_path):
    import json as _json

    (tmp_path / "0002021728").mkdir()
    pack_a = tmp_path / "0002021728" / "0001628280-24-041596"
    pack_a.mkdir()
    (pack_a / "manifest.json").write_text(
        _json.dumps(
            {
                "filing": {
                    "accession": "0001628280-24-041596",
                    "form_type": "S-1",
                    "filing_date": "2024-09-30",
                    "cik": "0002021728",
                    "company_name": "Cerebras",
                }
            }
        )
    )
    (pack_a / "filing.full.md").write_text("# x\n\nrevenue 1")
    (pack_a / "s1_financials.json").write_text(
        _json.dumps(
            {
                "schema_version": 1,
                "accession": "0001628280-24-041596",
                "extracted_at": "2026-04-22T00:00:00Z",
                "extraction_status": "ok",
                "source_sha256": "x",
                "model": "claude-haiku-4-5-20251001",
                "facts": [
                    {
                        "accession": "0001628280-24-041596",
                        "fiscal_year": 2024,
                        "period_end": "2024-12-31",
                        "metric": "revenue",
                        "value_cents": 100,
                        "currency": "USD",
                        "is_audited": True,
                        "is_pro_forma": False,
                        "pro_forma_note": None,
                    }
                ],
            }
        )
    )

    (tmp_path / "0000000000").mkdir()
    pack_b = tmp_path / "0000000000" / "ignored"
    pack_b.mkdir()
    (pack_b / "manifest.json").write_text(
        _json.dumps(
            {
                "filing": {
                    "accession": "ignored",
                    "form_type": "S-1",
                    "filing_date": "2020-01-01",
                    "cik": "0000000000",
                    "company_name": "Other",
                }
            }
        )
    )
    (pack_b / "filing.full.md").write_text("x")

    facts = snapshots_for_cik("0002021728", pack_root=tmp_path)
    assert len(facts) == 1
    assert facts[0].accession == "0001628280-24-041596"
