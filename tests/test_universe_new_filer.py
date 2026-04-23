"""Tests for universe config extensions supporting new (pre-IPO) filers."""

import pytest
from pydantic import ValidationError

from edgarpack.harvest.universe import CompanySpec, UniverseConfig


def test_company_spec_accepts_name_only():
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    assert spec.name == "Cerebras Systems"
    assert spec.ticker is None
    assert spec.cik is None
    assert spec.forms_s1 == 8


def test_company_spec_accepts_ticker_only():
    spec = CompanySpec(ticker="NVDA")
    assert spec.ticker == "NVDA"


def test_company_spec_accepts_cik_only():
    spec = CompanySpec(cik="0002021728", forms_s1=8)
    assert spec.cik == "0002021728"


def test_company_spec_rejects_all_identifiers_missing():
    with pytest.raises(ValidationError) as exc:
        CompanySpec(forms_s1=8)
    msg = str(exc.value).lower()
    assert "identifier" in msg or "ticker" in msg or "name" in msg or "cik" in msg


def test_form_counts_emits_registration_sentinel_when_forms_s1_set():
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert counts.get("__REGISTRATION__") == 8


def test_form_counts_applies_pre_ipo_inference_when_only_forms_s1_set():
    """If forms_s1 is set and periodic forms are not explicitly provided,
    10-K / 10-Q / 8-K are inferred to 0 to avoid spurious harvest errors."""
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert "10-K" not in counts
    assert "10-Q" not in counts
    assert "8-K" not in counts


def test_form_counts_respects_explicit_override_post_ipo():
    """Post-IPO the user adds explicit periodic counts; those override the
    pre-IPO inference and registration amendments keep flowing."""
    spec = CompanySpec(ticker="CRBS", forms_s1=2, forms_10k=2, forms_10q=4, forms_8k=5)
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert counts["__REGISTRATION__"] == 2
    assert counts["10-K"] == 2
    assert counts["10-Q"] == 4
    assert counts["8-K"] == 5


def test_form_counts_unchanged_for_public_only_filer():
    """A public-only filer should still get the default 10-K/10-Q/8-K counts."""
    spec = CompanySpec(ticker="NVDA")
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert counts["10-K"] == 2
    assert counts["10-Q"] == 4
    assert counts["8-K"] == 5
    assert "__REGISTRATION__" not in counts
