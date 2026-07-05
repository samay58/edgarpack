"""Async batch executor with bounded concurrency and progress reporting."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from ..china.acquire import find_latest_annual_report
from ..pack.build import PackResult, build_pack, build_sse_pack
from ..pack.manifest import compute_sha256
from .planner import HarvestItem, HarvestPlan
from .registry import PackRegistry


class HarvestProgress:
    """Track and report harvest progress."""

    def __init__(self, total: int):
        self.total = total
        self.completed = 0
        self.failed = 0
        self.skipped = 0

    def report(self, item: HarvestItem, result: PackResult | None, error: str | None) -> None:
        self.completed += 1
        idx = self.completed
        if error:
            self.failed += 1
            status = f"FAIL ({error})"
        elif result:
            status = f"OK ({result.sections_count} sections, {result.tokens_total:,} tokens)"
        else:
            self.skipped += 1
            status = "SKIP (already built)"

        print(
            f"[{idx}/{self.total}] {item.ticker} {item.form_type} {item.filing_date} ... {status}",
            file=sys.stderr,
        )


async def _build_one(
    item: HarvestItem,
    out_dir: Path,
    registry: PackRegistry,
    progress: HarvestProgress,
    semaphore: asyncio.Semaphore,
    with_chunks: bool = False,
    force: bool = False,
    describe_images: bool = False,
) -> PackResult | None:
    """Build a single filing pack and register it."""
    assert item.cik is not None and item.accession is not None, (
        "SEC harvest items must carry cik/accession (SSE items route through _build_one_sse)"
    )

    async with semaphore:
        error: str | None = None
        result: PackResult | None = None

        if item.already_built and not force:
            progress.report(item, None, None)
            return None

        try:
            result = await build_pack(
                cik=item.cik,
                accession=item.accession,
                form_type=None,
                out_dir=out_dir,
                with_chunks=with_chunks,
                force=force,
                describe_images=describe_images,
            )

            # Compute manifest hash for registry
            manifest_path = result.output_dir / "manifest.json"
            manifest_hash = None
            if manifest_path.exists():
                manifest_hash = compute_sha256(manifest_path.read_bytes())

            registry.register(
                accession=item.accession,
                cik=item.cik,
                ticker=item.ticker,
                company_name=item.company_name,
                form_type=item.form_type,
                filing_date=item.filing_date,
                sections_count=result.sections_count,
                tokens_total=result.tokens_total,
                pack_dir=str(result.output_dir),
                manifest_hash=manifest_hash,
                warnings=result.warnings if result.warnings else None,
            )

        except Exception as e:
            error = str(e)[:200]
            registry.log_error(
                ticker=item.ticker,
                error=error,
                accession=item.accession,
                form_type=item.form_type,
                error_stage="build",
            )

        progress.report(item, result, error)
        return result


async def _build_one_sse(
    item: HarvestItem,
    out_dir: Path,
    registry: PackRegistry,
    progress: HarvestProgress,
    force: bool = False,
    with_chunks: bool = False,
) -> PackResult | None:
    """Resolve, build, and register one SSE (A-share) annual report.

    CNINFO lookup and the SSE PDF download are paced to 1 rps inside their
    own client modules; SSE items are awaited sequentially (no semaphore) so
    a harvest run never has more than one CNINFO request in flight.
    """
    stock_code = item.stock_code or ""
    error: str | None = None

    try:
        selected = find_latest_annual_report(stock_code)
    except Exception as e:
        error = str(e)[:200]
        registry.log_error(
            ticker=item.ticker,
            error=error,
            accession=None,
            form_type=item.form_type,
            error_stage="build",
        )
        progress.report(item, None, error)
        return None

    item.filing_date = selected.filing_date.isoformat()
    company_name = selected.company_name or item.company_name

    if not force and registry.has_sse_filing(stock_code, item.filing_date):
        progress.report(item, None, None)
        return None

    result: PackResult | None = None
    try:
        result = await build_sse_pack(
            url=selected.source_url,
            stock_code=stock_code,
            company_name=company_name,
            filing_date=selected.filing_date,
            out_dir=out_dir,
            with_chunks=with_chunks,
            force=force,
            form_type="annual-report",
        )

        manifest_path = result.output_dir / "manifest.json"
        manifest_hash = None
        if manifest_path.exists():
            manifest_hash = compute_sha256(manifest_path.read_bytes())

        registry.register(
            accession=f"SSE:{stock_code}:{item.filing_date}",
            cik=f"SSE:{stock_code}",
            ticker=item.ticker,
            company_name=company_name,
            form_type=item.form_type,
            filing_date=item.filing_date,
            sections_count=result.sections_count,
            tokens_total=result.tokens_total,
            pack_dir=str(result.output_dir),
            manifest_hash=manifest_hash,
            warnings=result.warnings if result.warnings else None,
            market="SSE",
            stock_code=stock_code,
        )

    except Exception as e:
        error = str(e)[:200]
        registry.log_error(
            ticker=item.ticker,
            error=error,
            accession=None,
            form_type=item.form_type,
            error_stage="build",
        )

    progress.report(item, result, error)
    return result


async def run_harvest(
    plan: HarvestPlan,
    out_dir: Path,
    registry: PackRegistry,
    concurrency: int = 3,
    with_chunks: bool = False,
    force: bool = False,
    describe_images: bool = False,
) -> dict[str, Any]:
    """Execute a harvest plan with bounded concurrency.

    Args:
        plan: HarvestPlan from the planner
        out_dir: Output directory for packs
        registry: Pack registry for tracking
        concurrency: Maximum concurrent SEC requests
        with_chunks: Generate chunks.ndjson for each pack
        force: Rebuild even if already exists
        describe_images: Generate VLM descriptions for images in registration filings

    Returns:
        Summary dict with counts
    """
    items = plan.pending if not force else plan.items
    if not items:
        print("Nothing to harvest. All filings already built.", file=sys.stderr)
        return {"total": 0, "built": 0, "failed": 0, "skipped": len(plan.skipped)}

    sec_items = [i for i in items if i.market != "SSE"]
    sse_items = [i for i in items if i.market == "SSE"]

    progress = HarvestProgress(len(items))
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _build_one(
            item, out_dir, registry, progress, semaphore, with_chunks, force, describe_images
        )
        for item in sec_items
    ]

    sec_results = list(await asyncio.gather(*tasks, return_exceptions=True))

    # SSE (CNINFO) items run one at a time, never inside the SEC semaphore:
    # the CNINFO client paces itself to 1 rps and must never see two
    # in-flight requests from concurrent tasks.
    sse_failed_before = progress.failed
    sse_skipped_before = progress.skipped
    sse_results: list[PackResult | None] = []
    for item in sse_items:
        sse_results.append(
            await _build_one_sse(item, out_dir, registry, progress, force, with_chunks)
        )
    sse_built = sum(1 for r in sse_results if isinstance(r, PackResult))
    sse_failed = progress.failed - sse_failed_before
    sse_skipped = progress.skipped - sse_skipped_before

    results = sec_results + sse_results

    built = sum(1 for r in results if isinstance(r, PackResult))
    failed = progress.failed
    skipped = progress.skipped

    print(f"\nHarvest complete: {built} built, {failed} failed, {skipped} skipped", file=sys.stderr)
    if sse_items:
        print(
            f"  SSE: {sse_built} built, {sse_failed} failed, {sse_skipped} skipped",
            file=sys.stderr,
        )

    if failed > 0:
        errors = registry.get_errors(limit=failed)
        error_by_type: dict[str, int] = {}
        for err in errors:
            short = err["error"][:60]
            error_by_type[short] = error_by_type.get(short, 0) + 1
        print("\nError summary:", file=sys.stderr)
        for msg, count in sorted(error_by_type.items(), key=lambda x: -x[1]):
            print(f"  [{count}x] {msg}", file=sys.stderr)

    return {
        "total": len(items),
        "built": built,
        "failed": failed,
        "skipped": skipped,
    }
