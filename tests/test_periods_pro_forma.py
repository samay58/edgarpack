"""Pro-forma period selector: a new token `pro-forma` parseable by
parse_period_spec. Needed so users can explicitly request S-1 snapshot
rows where is_pro_forma=True (default period selectors exclude them)."""

import pytest

from edgarpack.query.periods import is_snapshot_pseudo_period, parse_period_spec


def test_parse_period_spec_accepts_pro_forma():
    assert parse_period_spec("pro-forma") == ["pro-forma"]


def test_parse_period_spec_rejects_pro_forma_with_offset():
    with pytest.raises(ValueError):
        parse_period_spec("pro-forma-1")


def test_parse_period_spec_accepts_mixed_scalars_with_pro_forma():
    assert parse_period_spec("lfy,pro-forma") == ["lfy", "pro-forma"]


def test_is_snapshot_pseudo_period_true_for_pro_forma():
    assert is_snapshot_pseudo_period("pro-forma")


def test_is_snapshot_pseudo_period_false_for_lfy():
    assert not is_snapshot_pseudo_period("lfy")
    assert not is_snapshot_pseudo_period("ltm")
    assert not is_snapshot_pseudo_period("mrq")
