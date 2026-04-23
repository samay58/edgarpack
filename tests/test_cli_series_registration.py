"""Smoke test that --series=registration is accepted by the CLI parser."""

import subprocess
import sys


def test_cli_accepts_series_registration_flag():
    result = subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "timeline", "--help"],
        capture_output=True,
        text=True,
    )
    # Help output should include --series.
    combined = result.stdout + result.stderr
    assert "--series" in combined or "series" in combined.lower()

    probe = subprocess.run(
        [
            sys.executable,
            "-m",
            "edgarpack.cli",
            "timeline",
            "--series",
            "registration",
            "--cik",
            "0002021728",
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    # Flag should be accepted (not "unrecognized arguments").
    assert "unrecognized arguments" not in probe.stderr.lower()
