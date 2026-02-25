"""Async batch executor with bounded concurrency and progress reporting."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ..pack.build import PackResult, build_pack
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
) -> PackResult | None:
    """Build a single filing pack and register it."""
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
            error = str(e)[:100]

        progress.report(item, result, error)
        return result


async def run_harvest(
    plan: HarvestPlan,
    out_dir: Path,
    registry: PackRegistry,
    concurrency: int = 3,
    with_chunks: bool = False,
    force: bool = False,
) -> dict:
    """Execute a harvest plan with bounded concurrency.

    Args:
        plan: HarvestPlan from the planner
        out_dir: Output directory for packs
        registry: Pack registry for tracking
        concurrency: Maximum concurrent SEC requests
        with_chunks: Generate chunks.ndjson for each pack
        force: Rebuild even if already exists

    Returns:
        Summary dict with counts
    """
    items = plan.pending if not force else plan.items
    if not items:
        print("Nothing to harvest. All filings already built.", file=sys.stderr)
        return {"total": 0, "built": 0, "failed": 0, "skipped": len(plan.skipped)}

    progress = HarvestProgress(len(items))
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _build_one(item, out_dir, registry, progress, semaphore, with_chunks, force)
        for item in items
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    built = sum(1 for r in results if isinstance(r, PackResult))
    failed = progress.failed
    skipped = progress.skipped

    print(f"\nHarvest complete: {built} built, {failed} failed, {skipped} skipped", file=sys.stderr)

    return {
        "total": len(items),
        "built": built,
        "failed": failed,
        "skipped": skipped,
    }
