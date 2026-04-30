"""Benchmark harness: measure how much EdgarPack compresses a raw SEC filing.

Produces reproducible numbers for the "By the numbers" claim in README.md
and the full methodology doc at docs/BENCHMARKS.md. Every figure in the
README must trace back to an entry in the JSON this script emits.

Outputs:
  - benchmarks/efficiency-YYYY-MM-DD.json        (headline + per-filing rollup)
  - benchmarks/efficiency-YYYY-MM-DD-run.log     (full run log)
  - benchmarks/artifacts/<TICKER>_10K_<accession>/
        raw.htm, stripped.htm, filing.full.md,
        section_item1a_risk_factors.md, metrics.json, manifest.json

Run:
  export EDGARPACK_USER_AGENT="Your Name your.email@example.com"
  uv run python scripts/benchmark_efficiency.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import shutil
import statistics
import sys
import time
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from edgarpack import __version__ as edgarpack_version  # noqa: N812
from edgarpack.config import PARSER_VERSION, SCHEMA_VERSION
from edgarpack.pack.build import build_pack
from edgarpack.parse.ixbrl_strip import strip_ixbrl
from edgarpack.parse.tokenize import count_tokens, has_tiktoken
from edgarpack.sec.archives import fetch_filing_html
from edgarpack.sec.submissions import get_latest_filing
from edgarpack.sec.tickers import resolve_company

# Keep the sample pinned here. Any change to this list is a change to the
# published benchmark and should be a real decision, not a drive-by edit.
DEFAULT_TICKERS: tuple[str, ...] = ("NVDA", "AAPL", "TSLA")
FORM_TYPE = "10-K"

# Item 1A section IDs vary slightly across filers; this regex catches the
# common shapes produced by edgarpack/parse/sectionize.py.
ITEM_1A_PATTERNS: tuple[str, ...] = (
    "10k_parti_item1a_risk_factors.md",
    "10k_part1_item1a_risk_factors.md",
    "10k_parti_item_1a_risk_factors.md",
)

logger = logging.getLogger("benchmark_efficiency")


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    sh = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(sh)


def _bytes_and_tokens(blob: str | bytes) -> dict[str, int]:
    """Return {bytes, tokens_cl100k} for a text blob."""
    if isinstance(blob, bytes):
        raw = blob
        text = blob.decode("utf-8", errors="replace")
    else:
        text = blob
        raw = blob.encode("utf-8")
    return {"bytes": len(raw), "tokens_cl100k": count_tokens(text)}


def _reduction_pct(before: int, after: int) -> float | None:
    if before <= 0:
        return None
    return round((1.0 - (after / before)) * 100.0, 2)


def _find_section_item1a(sections_dir: Path) -> Path | None:
    for name in ITEM_1A_PATTERNS:
        candidate = sections_dir / name
        if candidate.exists():
            return candidate
    # Fallback: any file with item1a + risk_factors in the stem.
    for candidate in sorted(sections_dir.glob("*item*1a*risk_factors*.md")):
        return candidate
    return None


async def _measure_filing(
    ticker: str,
    artifacts_root: Path,
) -> dict[str, Any]:
    """Measure one filing end-to-end and write its artifacts + metrics.json."""
    logger.info("==== %s %s ====", ticker, FORM_TYPE)

    resolve_start = time.monotonic()
    cik, canonical_ticker, title = await resolve_company(ticker)
    logger.info(
        "resolved %s -> cik=%s ticker=%s title=%s (%.2fs)",
        ticker,
        cik,
        canonical_ticker,
        title,
        time.monotonic() - resolve_start,
    )

    meta_start = time.monotonic()
    meta = await get_latest_filing(cik, FORM_TYPE)
    logger.info(
        "latest %s meta: accession=%s filed=%s primary=%s (%.2fs)",
        FORM_TYPE,
        meta.accession,
        meta.filing_date,
        meta.primary_document,
        time.monotonic() - meta_start,
    )

    artifact_dir = artifacts_root / f"{canonical_ticker}_10K_{meta.accession}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Stage A: fetch raw HTML. The normal pack builder is primary-document-only;
    # this benchmark still fetches related HTML so historical "combined raw"
    # figures remain reproducible as an upper-bound payload comparison.
    fetch_start = time.monotonic()
    html_files = await fetch_filing_html(meta)
    fetch_seconds = time.monotonic() - fetch_start

    if not html_files:
        raise RuntimeError(f"No HTML fetched for {ticker} {meta.accession}")

    primary_filename, primary_bytes = html_files[0]
    primary_text = primary_bytes.decode("utf-8", errors="replace")

    # "Combined" is retained for continuity with older benchmark artifacts.
    # The operational build denominator is now the primary filing document.
    combined_text = "\n".join(blob.decode("utf-8", errors="replace") for _, blob in html_files)

    primary_metrics = _bytes_and_tokens(primary_text)
    combined_raw_metrics = _bytes_and_tokens(combined_text)

    logger.info(
        "raw: primary=%s (%d bytes, %d tokens)",
        primary_filename,
        primary_metrics["bytes"],
        primary_metrics["tokens_cl100k"],
    )
    logger.info(
        "raw: combined %d bytes, %d tokens across %d files (fetch %.2fs)",
        combined_raw_metrics["bytes"],
        combined_raw_metrics["tokens_cl100k"],
        len(html_files),
        fetch_seconds,
    )

    # Persist raw (primary) for offline review. Combined HTML is redundant to
    # commit since we also commit the stripped + clean forms.
    (artifact_dir / "raw.htm").write_bytes(primary_bytes)

    # Stage B: iXBRL tag strip on the combined text for historical comparison.
    strip_start = time.monotonic()
    stripped_combined = strip_ixbrl(combined_text)
    strip_seconds = time.monotonic() - strip_start
    stripped_metrics = _bytes_and_tokens(stripped_combined)

    # Persist the stripped primary as well so the artifact triple (raw/stripped/clean)
    # stays coherent for any single file.
    stripped_primary = strip_ixbrl(primary_text)
    (artifact_dir / "stripped.htm").write_text(stripped_primary, encoding="utf-8")

    logger.info(
        "stripped: %d bytes, %d tokens (strip %.2fs)",
        stripped_metrics["bytes"],
        stripped_metrics["tokens_cl100k"],
        strip_seconds,
    )

    # Stage C: build the full pack. Cold rebuild (force=True); then warm
    # (no force) to confirm the manifest-cache fast path.
    with TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        cold_start = time.monotonic()
        cold_result = await build_pack(
            cik=cik,
            accession=meta.accession,
            out_dir=scratch,
            with_chunks=False,
            with_xbrl=False,
            force=True,
        )
        cold_seconds = time.monotonic() - cold_start
        pack_dir = cold_result.output_dir

        warm_start = time.monotonic()
        await build_pack(
            cik=cik,
            accession=meta.accession,
            out_dir=scratch,
            with_chunks=False,
            with_xbrl=False,
            force=False,
        )
        warm_seconds = time.monotonic() - warm_start

        filing_full = pack_dir / "filing.full.md"
        filing_full_text = filing_full.read_text(encoding="utf-8")
        clean_metrics = _bytes_and_tokens(filing_full_text)

        sections_dir = pack_dir / "sections"
        section_path = _find_section_item1a(sections_dir)
        if section_path is not None:
            section_text = section_path.read_text(encoding="utf-8")
            section_metrics = _bytes_and_tokens(section_text)
            (artifact_dir / "section_item1a_risk_factors.md").write_text(
                section_text, encoding="utf-8"
            )
        else:
            logger.warning("Item 1A section file not found for %s", ticker)
            section_metrics = None

        shutil.copy(filing_full, artifact_dir / "filing.full.md")
        shutil.copy(pack_dir / "manifest.json", artifact_dir / "manifest.json")

    logger.info(
        "clean: %d bytes, %d tokens (cold build %.2fs, warm %.2fs)",
        clean_metrics["bytes"],
        clean_metrics["tokens_cl100k"],
        cold_seconds,
        warm_seconds,
    )

    reductions = {
        "primary_raw_to_stripped_pct": _reduction_pct(
            primary_metrics["tokens_cl100k"],
            _bytes_and_tokens(stripped_primary)["tokens_cl100k"],
        ),
        "combined_raw_to_stripped_pct": _reduction_pct(
            combined_raw_metrics["tokens_cl100k"],
            stripped_metrics["tokens_cl100k"],
        ),
        "stripped_to_clean_pct": _reduction_pct(
            stripped_metrics["tokens_cl100k"],
            clean_metrics["tokens_cl100k"],
        ),
        "combined_raw_to_clean_pct": _reduction_pct(
            combined_raw_metrics["tokens_cl100k"],
            clean_metrics["tokens_cl100k"],
        ),
        "primary_raw_to_clean_pct": _reduction_pct(
            primary_metrics["tokens_cl100k"],
            clean_metrics["tokens_cl100k"],
        ),
    }

    per_filing: dict[str, Any] = {
        "ticker": canonical_ticker,
        "cik": cik,
        "company_name": meta.company_name,
        "form_type": meta.form_type,
        "accession": meta.accession,
        "filing_date": meta.filing_date.isoformat(),
        "primary_document": meta.primary_document,
        "html_files_fetched": [name for name, _ in html_files],
        "raw_primary": primary_metrics,
        "raw_combined": combined_raw_metrics,
        "stripped_combined": stripped_metrics,
        "clean_full_md": clean_metrics,
        "section_item1a_risk_factors": section_metrics,
        "reductions": reductions,
        "wall_clock_seconds": {
            "resolve_company": round(time.monotonic() - resolve_start, 3),
            "fetch_filing_html": round(fetch_seconds, 3),
            "ixbrl_strip_combined": round(strip_seconds, 3),
            "build_pack_cold": round(cold_seconds, 3),
            "build_pack_warm": round(warm_seconds, 3),
        },
    }

    (artifact_dir / "metrics.json").write_text(
        json.dumps(per_filing, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return per_filing


def _median_numeric(values: Iterable[float | int | None]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 2)


def _roll_up(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the median headline numbers a reviewer can cite in the README."""

    def field(path: tuple[str, ...]) -> list[float | int | None]:
        out: list[float | int | None] = []
        for row in results:
            cursor: Any = row
            for key in path:
                if cursor is None:
                    break
                cursor = cursor.get(key) if isinstance(cursor, dict) else None
            out.append(cursor)
        return out

    return {
        "raw_combined_tokens_median": _median_numeric(field(("raw_combined", "tokens_cl100k"))),
        "raw_primary_tokens_median": _median_numeric(field(("raw_primary", "tokens_cl100k"))),
        "stripped_combined_tokens_median": _median_numeric(
            field(("stripped_combined", "tokens_cl100k"))
        ),
        "clean_full_md_tokens_median": _median_numeric(field(("clean_full_md", "tokens_cl100k"))),
        "section_item1a_tokens_median": _median_numeric(
            field(("section_item1a_risk_factors", "tokens_cl100k"))
        ),
        "combined_raw_to_clean_reduction_pct_median": _median_numeric(
            field(("reductions", "combined_raw_to_clean_pct"))
        ),
        "primary_raw_to_clean_reduction_pct_median": _median_numeric(
            field(("reductions", "primary_raw_to_clean_pct"))
        ),
        "build_pack_cold_seconds_median": _median_numeric(
            field(("wall_clock_seconds", "build_pack_cold"))
        ),
        "build_pack_warm_seconds_median": _median_numeric(
            field(("wall_clock_seconds", "build_pack_warm"))
        ),
    }


def _host_info() -> dict[str, str]:
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "processor": platform.processor() or "unknown",
    }


async def _run(
    tickers: tuple[str, ...],
    out_json: Path,
    artifacts_root: Path,
) -> int:
    ua = os.environ.get("EDGARPACK_USER_AGENT", "").strip()
    if not ua:
        logger.error(
            "EDGARPACK_USER_AGENT is not set. SEC requires a user agent of the form "
            "'Your Name your.email@example.com'. Export it and retry."
        )
        return 2

    if not has_tiktoken():
        logger.error(
            "tiktoken is not available. Install it so token counts are real cl100k "
            "numbers instead of a 4-chars-per-token estimate. `uv pip install tiktoken`."
        )
        return 2

    artifacts_root.mkdir(parents=True, exist_ok=True)

    per_filing_results: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            per_filing_results.append(await _measure_filing(ticker, artifacts_root))
        except Exception as exc:
            logger.exception("Measurement failed for %s: %s", ticker, exc)
            return 1

    rollup = _roll_up(per_filing_results)

    # Sanity: raw token count should be well above a floor; unusually high
    # or low values usually mean a fetch glitch, not a real filing.
    for row in per_filing_results:
        raw_combined_tokens = row["raw_combined"]["tokens_cl100k"]
        if raw_combined_tokens < 200_000 or raw_combined_tokens > 20_000_000:
            logger.warning(
                "Sanity: %s raw combined tokens = %d (outside 200k..20M band); "
                "investigate before trusting this row",
                row["ticker"],
                raw_combined_tokens,
            )

    doc = {
        "generated_at": datetime.now(UTC).isoformat(),
        "edgarpack_version": edgarpack_version,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "tokenizer": "cl100k_base",
        "form_type": FORM_TYPE,
        "sample_tickers": list(tickers),
        "host": _host_info(),
        "filings": per_filing_results,
        "rollup_median": rollup,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Wrote rollup: %s", out_json)

    # Echo the headline so the log has the single source of truth too.
    logger.info(
        "MEDIAN raw_combined=%s tokens, clean=%s tokens, reduction=%s%%",
        rollup["raw_combined_tokens_median"],
        rollup["clean_full_md_tokens_median"],
        rollup["combined_raw_to_clean_reduction_pct_median"],
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    today = date.today().isoformat()
    default_out = Path("benchmarks") / f"efficiency-{today}.json"
    default_log = Path("benchmarks") / f"efficiency-{today}-run.log"
    default_artifacts = Path("benchmarks") / "artifacts"

    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--tickers",
        nargs="+",
        default=list(DEFAULT_TICKERS),
        help=f"Tickers to benchmark (default: {' '.join(DEFAULT_TICKERS)})",
    )
    ap.add_argument("--out-json", type=Path, default=default_out)
    ap.add_argument("--log", type=Path, default=default_log)
    ap.add_argument("--artifacts", type=Path, default=default_artifacts)
    args = ap.parse_args(argv)

    _setup_logging(args.log)
    logger.info(
        "edgarpack %s | parser %s | schema %s",
        edgarpack_version,
        PARSER_VERSION,
        SCHEMA_VERSION,
    )
    logger.info("tickers: %s", args.tickers)

    return asyncio.run(_run(tuple(args.tickers), args.out_json, args.artifacts))


if __name__ == "__main__":
    raise SystemExit(main())
