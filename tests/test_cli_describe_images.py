"""CLI flag plumbing test for --describe-images."""

import subprocess
import sys


def test_cli_accepts_describe_images_flag():
    result = subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "harvest", "--help"],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "describe-images" in combined or "describe_images" in combined
