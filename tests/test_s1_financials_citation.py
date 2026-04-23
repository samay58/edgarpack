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
