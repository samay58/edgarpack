"""Verify periods helpers do not treat registration-class forms as annual/quarterly."""

from edgarpack.query.periods import _is_annual, _is_quarter_form_type
from edgarpack.sec.submissions import is_registration_form


def test_registration_form_is_not_annual():
    for form in ("S-1", "S-1/A", "F-1", "F-1/A", "424B4", "FWP"):
        assert not _is_annual({"form": form, "fp": ""}), form


def test_registration_form_is_not_quarterly():
    for form in ("S-1", "S-1/A", "F-1", "F-1/A", "424B4", "FWP"):
        assert not _is_quarter_form_type(form), form


def test_is_registration_form_is_accessible_from_periods_callers():
    assert is_registration_form("S-1")
    assert not is_registration_form("10-K")
