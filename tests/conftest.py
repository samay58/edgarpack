"""Shared pytest configuration for slow/live SEC test lanes."""

from __future__ import annotations

import os

import pytest


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
