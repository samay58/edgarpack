"""Guard against top-level sprawl: the repo root only grows on purpose.

If you intentionally add a new tracked top-level entry, add it to ALLOWED below.
Otherwise this test tells you to move it into an existing directory.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

ALLOWED: frozenset[str] = frozenset(
    {
        # tooling / config
        ".claude",
        ".github",
        ".gitignore",
        ".learn-pack",
        "pyproject.toml",
        "uv.lock",
        # docs / instructions
        "AGENTS.md",
        "README.md",
        # source
        "edgarpack",
        "tests",
        "web",
        "scripts",
        # root-pinned data / config inputs
        "data",
        "universe.toml",
        "cerebras.toml",
        # content / output
        "docs",
        "assets",
        "benchmarks",
        "reports",
        "demo",
    }
)


def _tracked_top_level() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {line.split("/", 1)[0] for line in out.splitlines() if line.strip()}


def test_no_top_level_sprawl() -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    unexpected = _tracked_top_level() - ALLOWED
    assert not unexpected, (
        f"New tracked top-level entries not in the allowlist: {sorted(unexpected)}. "
        "If intentional, add them to ALLOWED in tests/test_repo_layout.py; "
        "otherwise move them into an existing directory."
    )
