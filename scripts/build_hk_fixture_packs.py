"""Build HK pack fixtures from committed prospectus PDFs.

Patches the adapter's downloader to a no-op so it consumes the locally-
committed source.pdf instead of refetching from hkexnews.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

from edgarpack.hk.acquire import HKFilingRef
from edgarpack.hk.adapter import build_hk_pack

FIXTURES = Path("tests/fixtures/china_packs")

TARGETS = [
    ("minimax_2024", "00100", 2024, "MiniMax IPO Prospectus"),
    ("zhipu_2024", "02513", 2024, "Zhipu IPO Prospectus"),
]


def _make_noop_downloader(source_pdf: Path):
    def _noop(ref: HKFilingRef, out: Path) -> Path:
        if not out.exists():
            shutil.copy2(source_pdf, out)
        return out

    return _noop


def main() -> int:
    for dir_name, stock_code, fy, label in TARGETS:
        pack_dir = FIXTURES / dir_name
        pdf = pack_dir / "source.pdf"
        if not pdf.exists():
            print(f"missing: {pdf}", file=sys.stderr)
            return 1

        ref = HKFilingRef(
            stock_code=stock_code,
            fiscal_year=fy,
            pdf_url=f"file://{pdf.resolve()}",
            announcement_date="N/A",
        )

        with patch("edgarpack.hk.adapter._download_pdf", side_effect=_make_noop_downloader(pdf)):
            pack = build_hk_pack(ref, pack_dir)
        print(f"built {label} -> {pack.path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
