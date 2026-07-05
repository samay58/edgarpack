"""Shared pytest configuration for slow/live SEC test lanes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

_CHINA_FIXTURE_PACK_ROOT = Path(__file__).parent / "fixtures" / "china_packs"


@pytest.fixture(autouse=True)
def _china_pack_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point China pack discovery at the committed fixtures.

    Production reads flat ``{name}_{fy}`` China packs only when
    EDGARPACK_CHINA_PACK_ROOT is set (opt-in, never a hardcoded test path).
    The test suite opts in here so fixture-based HKEX queries resolve; setting
    it via os.environ means subprocess-based CLI contract tests inherit it too.
    """
    monkeypatch.setenv("EDGARPACK_CHINA_PACK_ROOT", str(_CHINA_FIXTURE_PACK_ROOT))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests",
    )
    parser.addoption(
        "--run-live-sec",
        action="store_true",
        default=False,
        help="Run live SEC integration tests",
    )
    parser.addoption(
        "--live-sec-full",
        action="store_true",
        default=False,
        help="Run expanded live SEC coverage, including the 30+ filing matrix",
    )


@pytest.fixture
def _require_slow(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--run-slow", default=False):
        pytest.skip("slow test: pass --run-slow to run")


@pytest.fixture
def _require_live_sec(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--run-live-sec", default=False):
        pytest.skip("live SEC test: pass --run-live-sec to run")
    if not os.environ.get("EDGARPACK_USER_AGENT", "").strip():
        pytest.skip("live SEC tests require EDGARPACK_USER_AGENT")


@pytest.fixture
def _require_live_sec_full(
    request: pytest.FixtureRequest,
    _require_live_sec: None,
) -> None:
    if not request.config.getoption("--live-sec-full", default=False):
        pytest.skip("expanded live SEC coverage: pass --live-sec-full to run")


@pytest.fixture(autouse=True)
def _ltm_citation_contract_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Double-check the LTM citation contract on every test.

    `_select_ltm_like` already asserts the invariant at each return point via
    `_finalize`. This harness wraps `select_period` as a belt-and-suspenders
    check: any test that calls `select_period(..., period="ltm" | "ltm-1")`
    gets its result passed through `_assert_ltm_invariant` again, so a future
    bypass of `_finalize` (e.g. a new return path) cannot escape the contract
    in the test suite.
    """
    import importlib

    from edgarpack.query import periods as _periods_mod

    _financials_mod = importlib.import_module("edgarpack.query.financials")

    original = _periods_mod.select_period

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        period_val: str | None = None
        if len(args) >= 7:
            candidate = args[6]
            if isinstance(candidate, str):
                period_val = candidate
        if period_val is None:
            candidate_kw = kwargs.get("period")
            if isinstance(candidate_kw, str):
                period_val = candidate_kw
        if period_val is None:
            return result
        period_norm = period_val.strip().lower()
        if period_norm in ("ltm", "ltm-1"):
            label = "LTM" if period_norm == "ltm" else "LTM-1"
            if isinstance(result, list):
                for item in result:
                    _periods_mod._assert_ltm_invariant(item, label)
            else:
                _periods_mod._assert_ltm_invariant(result, label)
        return result

    monkeypatch.setattr(_periods_mod, "select_period", _wrapped)
    monkeypatch.setattr(_financials_mod, "select_period", _wrapped)
