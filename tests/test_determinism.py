"""Determinism verification: build the same filing twice, compare byte-for-byte.

This test hits the SEC API so it is skipped by default. Run with:
    pytest tests/test_determinism.py -v --run-slow
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from edgarpack.pack.build import build_pack


def _pack_files(pack_dir: Path) -> dict[str, bytes]:
    """Read all files in a pack directory into a dict keyed by relative path."""
    result: dict[str, bytes] = {}
    for f in sorted(pack_dir.rglob("*")):
        if f.is_file():
            result[str(f.relative_to(pack_dir))] = f.read_bytes()
    return result


@pytest.fixture
def _require_slow(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--run-slow", default=False):
        pytest.skip("slow test: pass --run-slow to run")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow", action="store_true", default=False, help="Run slow network tests"
    )


@pytest.mark.usefixtures("_require_slow")
class TestDeterminism:
    """Build the same filing twice to separate directories, verify identical output."""

    CIK = "0001045810"  # NVDA

    def test_same_filing_produces_identical_packs(self) -> None:
        async def _run() -> None:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_a = Path(tmpdir) / "run_a"
                out_b = Path(tmpdir) / "run_b"

                result_a = await build_pack(
                    cik=self.CIK,
                    form_type="10-K",
                    out_dir=out_a,
                    with_chunks=True,
                    force=True,
                )
                result_b = await build_pack(
                    cik=self.CIK,
                    form_type="10-K",
                    out_dir=out_b,
                    with_chunks=True,
                    force=True,
                )

                files_a = _pack_files(result_a.output_dir)
                files_b = _pack_files(result_b.output_dir)

                assert set(files_a.keys()) == set(files_b.keys()), (
                    f"File sets differ:\n"
                    f"  Only in A: {set(files_a) - set(files_b)}\n"
                    f"  Only in B: {set(files_b) - set(files_a)}"
                )

                for path in sorted(files_a):
                    if path == "manifest.json":
                        # Compare manifest ignoring built_at timestamp
                        ma = json.loads(files_a[path])
                        mb = json.loads(files_b[path])
                        ma.pop("built_at", None)
                        mb.pop("built_at", None)
                        assert ma == mb, "manifest.json content differs"
                    else:
                        assert files_a[path] == files_b[path], f"File differs: {path}"

        asyncio.run(_run())
