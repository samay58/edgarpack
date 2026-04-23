"""Tests for registration-form normalization and the family constant."""

from edgarpack.sec.submissions import (
    REGISTRATION_FORMS,
    is_registration_form,
    normalize_form_type,
)


def test_registration_forms_family_is_exported():
    assert "S-1" in REGISTRATION_FORMS
    assert "S-1/A" in REGISTRATION_FORMS
    assert "F-1" in REGISTRATION_FORMS
    assert "F-1/A" in REGISTRATION_FORMS
    assert "424B1" in REGISTRATION_FORMS
    assert "424B4" in REGISTRATION_FORMS
    assert "FWP" in REGISTRATION_FORMS
    assert "10-K" not in REGISTRATION_FORMS


def test_normalize_form_type_preserves_s1():
    assert normalize_form_type("S-1") == "S-1"
    assert normalize_form_type("s-1") == "S-1"
    assert normalize_form_type("S1") == "S-1"


def test_normalize_form_type_preserves_s1_amendment():
    assert normalize_form_type("S-1/A") == "S-1/A"
    assert normalize_form_type("s1/a") == "S-1/A"


def test_normalize_form_type_preserves_f1():
    assert normalize_form_type("F-1") == "F-1"
    assert normalize_form_type("F1/A") == "F-1/A"


def test_normalize_form_type_preserves_424b():
    assert normalize_form_type("424B1") == "424B1"
    assert normalize_form_type("424b4") == "424B4"


def test_normalize_form_type_preserves_fwp():
    assert normalize_form_type("FWP") == "FWP"
    assert normalize_form_type("fwp") == "FWP"


def test_is_registration_form_true_for_family():
    for form in ("S-1", "S-1/A", "F-1", "F-1/A", "424B1", "424B3", "FWP"):
        assert is_registration_form(form), form


def test_is_registration_form_false_for_periodic():
    for form in ("10-K", "10-Q", "8-K", "20-F", "40-F", "", "DEF 14A"):
        assert not is_registration_form(form), form


def test_is_registration_form_handles_casing_and_whitespace():
    assert is_registration_form(" s-1 ")
    assert is_registration_form("s1/a")
    assert is_registration_form("fwp")
