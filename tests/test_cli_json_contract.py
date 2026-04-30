"""CLI stdout contracts for machine-readable modes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )


def _assert_parse_clean_json(*args: str) -> dict:
    result = _run(*args)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("{")
    return json.loads(result.stdout)


def test_query_json_stdout_parse_clean() -> None:
    payload = _assert_parse_clean_json("query", "zhipu", "revenue", "--format", "json")

    assert payload["company"].startswith("Zhipu")
    assert "revenue" in payload["metrics"]


def test_comps_json_stdout_parse_clean() -> None:
    payload = _assert_parse_clean_json(
        "comps",
        "minimax",
        "zhipu",
        "--metrics",
        "revenue",
        "--format",
        "json",
    )

    assert set(payload["companies"]) == {"minimax", "zhipu"}


def test_which_json_stdout_parse_clean() -> None:
    payload = _assert_parse_clean_json("which", "zhipu", "--format", "json")

    assert payload["company"].startswith("Zhipu")
    assert payload["citations"]


def test_compare_json_stdout_parse_clean() -> None:
    payload = _assert_parse_clean_json(
        "compare",
        "minimax",
        "zhipu",
        "--metrics",
        "revenue",
        "--format",
        "json",
    )

    assert len(payload["companies"]) == 2
    assert payload["citations"]
