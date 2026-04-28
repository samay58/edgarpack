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


def test_root_help_shows_branded_welcome() -> None:
    result = _run_cmd("--help")

    assert result.returncode == 0
    assert "Primary filings. Clean packs. Cited answers." in result.stdout
    assert "[C1]" in result.stdout
    assert "[  E P  ]" in result.stdout
    assert "edgarpack home" in result.stdout


def test_home_command_shows_starter_commands() -> None:
    result = _run_cmd("home")

    assert result.returncode == 0
    assert "EdgarPack" in result.stdout
    assert "edgarpack query NVDA revenue --period ltm" in result.stdout
    assert "edgarpack build-sse 688696 --latest-annual --with-chunks" in result.stdout


def test_bare_command_shows_first_run_home() -> None:
    result = _run_cmd()

    assert result.returncode == 0
    assert "Primary filings. Clean packs. Cited answers." in result.stdout
    assert "Start:" in result.stdout


def test_subcommand_help_does_not_show_brand_banner() -> None:
    result = _run_cmd("query", "--help")

    assert result.returncode == 0
    assert "[  E P  ]" not in result.stdout
    assert "Primary filings. Clean packs. Cited answers." not in result.stdout
