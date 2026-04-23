"""Tests for S-1-only disclosure extractors."""

from edgarpack.query.kpi_discover import (
    extract_dilution,
    extract_lockup,
    extract_principal_holders,
    extract_use_of_proceeds,
)


def test_use_of_proceeds_simple():
    text = (
        "We intend to use the net proceeds from this offering as follows: "
        "approximately $150.0 million for research and development, "
        "$80.0 million for manufacturing capacity expansion, "
        "and the remainder for working capital."
    )
    hits = extract_use_of_proceeds(text)
    assert len(hits) >= 2
    assert any("research" in h.claim.lower() for h in hits)
    assert any("manufacturing" in h.claim.lower() for h in hits)
    assert all(h.metric_kind == "s1_disclosure" for h in hits)
    assert all(h.disclosure_type == "use_of_proceeds" for h in hits)


def test_dilution_per_share():
    text = "You will experience immediate dilution of $12.50 per share."
    hits = extract_dilution(text)
    assert hits
    assert "$12.50" in hits[0].claim
    assert hits[0].disclosure_type == "dilution"


def test_lockup_days():
    text = "The lock-up period will be 180 days from the date of this prospectus."
    hits = extract_lockup(text)
    assert hits
    assert "180" in hits[0].claim
    assert hits[0].disclosure_type == "lockup"


def test_principal_holders_with_percentages():
    text = (
        "Name                        Shares           Percent\n"
        "Acme Capital LP             12,500,000       18.4%\n"
        "Founder Jane Doe             9,000,000       13.2%\n"
        "Strategic Ventures Fund      5,250,000        7.7%"
    )
    hits = extract_principal_holders(text)
    assert len(hits) >= 3
    assert any("Acme Capital" in h.claim for h in hits)
    assert all(h.metric_kind == "s1_disclosure" for h in hits)
    assert all(h.disclosure_type == "principal_holder" for h in hits)


def test_nothing_extracted_on_irrelevant_text():
    text = "The Company was founded in 2016 in Los Altos, California."
    assert extract_use_of_proceeds(text) == []
    assert extract_dilution(text) == []
    assert extract_lockup(text) == []
    assert extract_principal_holders(text) == []
