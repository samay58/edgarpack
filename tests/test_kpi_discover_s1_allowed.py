"""Verify kpi_discover includes registration-class packs in its eligible set."""

from edgarpack.query.kpi_discover import _filter_eligible_packs_for_test


def test_s1_packs_are_eligible():
    fake_packs = [
        type("P", (), {"accession": "a", "form_type": "10-K"})(),
        type("P", (), {"accession": "b", "form_type": "S-1"})(),
        type("P", (), {"accession": "c", "form_type": "S-1/A"})(),
        type("P", (), {"accession": "d", "form_type": "424B4"})(),
        type("P", (), {"accession": "e", "form_type": "FWP"})(),
        type("P", (), {"accession": "f", "form_type": "8-K"})(),
    ]
    eligible = _filter_eligible_packs_for_test(fake_packs)
    accessions = {p.accession for p in eligible}
    assert {"a", "b", "c", "d", "e"}.issubset(accessions)
    assert "f" not in accessions
