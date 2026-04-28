import subprocess
import sys
from pathlib import Path


def _run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )


def test_root_help_stays_compact_and_points_to_home() -> None:
    result = _run_cmd("--help")

    assert result.returncode == 0
    assert "Primary filings turned into clean packs and cited answers." in result.stdout
    assert "edgarpack home" in result.stdout
    assert "[  E D G A R P A C K  ]" not in result.stdout
    assert "SOURCE FILINGS" not in result.stdout


def test_home_command_shows_starter_commands() -> None:
    result = _run_cmd("home")

    assert result.returncode == 0
    assert "EdgarPack" in result.stdout
    assert "SOURCE FILINGS" in result.stdout
    assert "[  E D G A R P A C K  ]" in result.stdout
    assert "Begin with primary evidence:" in result.stdout
    assert "edgarpack query NVDA revenue --period ltm" in result.stdout
    assert "edgarpack build-sse 688696 --latest-annual --with-chunks" in result.stdout
    assert "edgarpack home" not in result.stdout


def test_bare_command_shows_first_run_home() -> None:
    result = _run_cmd()

    assert result.returncode == 0
    assert "Primary filings. Clean packs. Cited answers." in result.stdout
    assert "Begin with primary evidence:" in result.stdout


def test_subcommand_help_does_not_show_brand_banner() -> None:
    result = _run_cmd("query", "--help")

    assert result.returncode == 0
    assert "[  E D G A R P A C K  ]" not in result.stdout
    assert "Primary filings. Clean packs. Cited answers." not in result.stdout
