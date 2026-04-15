from datetime import UTC, datetime

from edgarpack.pack.manifest import (
    FilingInfo,
    Manifest,
    SectionInfo,
    SourceInfo,
)


def _minimal_manifest(**overrides) -> Manifest:
    base = dict(
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=SourceInfo(url="https://example", fetched_at=datetime(2024, 1, 1, tzinfo=UTC)),
        filing=FilingInfo(
            cik="0001234567",
            accession="0001234567-24-000001",
            form_type="10-K",
            filing_date="2024-01-01",
            company_name="Acme",
        ),
        sections=[],
        artifacts={},
        warnings=[],
        tokens_total=0,
    )
    base.update(overrides)
    return Manifest(**base)


def test_manifest_defaults_to_us_gaap_usd():
    m = _minimal_manifest()
    assert m.accounting_standard == "US-GAAP"
    assert m.reporting_currency == "USD"


def test_manifest_accepts_ifrs_and_cny():
    m = _minimal_manifest(accounting_standard="IFRS", reporting_currency="CNY")
    assert m.accounting_standard == "IFRS"
    assert m.reporting_currency == "CNY"


def test_manifest_roundtrips_new_fields_through_json():
    import json

    m = _minimal_manifest(accounting_standard="IFRS", reporting_currency="CNY")
    payload = m.model_dump(mode="json")
    rehydrated = Manifest(**json.loads(json.dumps(payload)))
    assert rehydrated.accounting_standard == "IFRS"
    assert rehydrated.reporting_currency == "CNY"


_ = SectionInfo
