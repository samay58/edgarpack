"""CLI entry point for EdgarPack.

This CLI intentionally avoids third-party CLI frameworks so the project remains
easy to run in constrained environments.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from . import __version__


def app(argv: list[str] | None = None) -> None:
    """Console script entrypoint (kept as `app` for packaging compatibility)."""
    raise SystemExit(main(argv))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="edgarpack",
        description="llms.txt for SEC filings — build deterministic markdown packs.",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"EdgarPack {__version__}",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Build a filing pack")
    p_build.add_argument("--cik", "-c", required=True, help="CIK number (with or without leading zeros)")
    p_build.add_argument("--accession", "-a", help="Accession number (e.g., 0000320193-24-000123)")
    p_build.add_argument("--form", "-f", help="Form type: 10-K, 10-Q, 8-K (fetches latest)")
    p_build.add_argument("--out", "-o", type=Path, default=Path("./packs"), help="Output directory")
    p_build.add_argument("--with-chunks", action="store_true", help="Generate chunks.ndjson for RAG")
    p_build.add_argument("--with-xbrl", action="store_true", help="Generate xbrl.json with financial data")
    p_build.add_argument("--force", action="store_true", help="Bypass cache and rebuild")

    p_company = sub.add_parser("company-llms", help="Generate company-level llms.txt")
    p_company.add_argument("--cik", "-c", required=True, help="CIK number")
    p_company.add_argument("--out", "-o", type=Path, default=Path("./packs"), help="Packs output directory")

    p_list = sub.add_parser("list", help="List recent filings for a company")
    p_list.add_argument("--cik", "-c", required=True, help="CIK number")
    p_list.add_argument("--form", "-f", help="Filter by form type")
    p_list.add_argument("--limit", "-n", type=int, default=10, help="Number of filings to show")

    p_cache = sub.add_parser("cache", help="Show cache info or clear cache")
    p_cache.add_argument("--clear", action="store_true", help="Clear the cache")

    p_site = sub.add_parser("site", help="Generate a minimal static site from packs")
    p_site.add_argument("--packs", type=Path, default=Path("./packs"), help="Directory containing packs")
    p_site.add_argument("--out", "-o", type=Path, default=Path("./site"), help="Site output directory")
    p_site.add_argument("--base-url", default=None, help="Optional base URL (reserved)")

    args = parser.parse_args(argv)

    if args.cmd == "build":
        return _cmd_build(args)
    if args.cmd == "company-llms":
        return _cmd_company_llms(args)
    if args.cmd == "list":
        return _cmd_list(args)
    if args.cmd == "cache":
        return _cmd_cache(args)
    if args.cmd == "site":
        return _cmd_site(args)

    parser.print_help()
    return 2


def _cmd_build(args: Any) -> int:
    if not args.accession and not args.form:
        print("Error: either --accession or --form must be provided", file=sys.stderr)
        return 2

    async def _run() -> int:
        from .pack.build import build_pack

        try:
            result = await build_pack(
                cik=args.cik,
                accession=args.accession,
                form_type=args.form,
                out_dir=args.out,
                with_chunks=bool(args.with_chunks),
                with_xbrl=bool(args.with_xbrl),
                force=bool(args.force),
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        print("✓ Pack built")
        print(f"  Output: {result.output_dir}")
        print(f"  Company: {result.filing_meta.get('company_name', 'Unknown')}")
        print(f"  Form: {result.filing_meta.get('form_type', 'Unknown')}")
        print(f"  Filing Date: {result.filing_meta.get('filing_date', 'Unknown')}")
        print(f"  Sections: {result.sections_count}")
        print(f"  Tokens: {result.tokens_total:,}")

        if result.warnings:
            print(f"\nWarnings ({len(result.warnings)}):")
            for w in result.warnings[:10]:
                print(f"  - {w}")
            if len(result.warnings) > 10:
                print(f"  ... and {len(result.warnings) - 10} more")

        return 0

    return asyncio.run(_run())


def _cmd_company_llms(args: Any) -> int:
    async def _run() -> int:
        from .pack.build import build_company_llms

        try:
            path = await build_company_llms(args.cik, args.out)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        print(f"✓ Company llms.txt written: {path}")
        return 0

    return asyncio.run(_run())


def _cmd_list(args: Any) -> int:
    async def _run() -> int:
        from .sec.submissions import list_filings

        try:
            filings = await list_filings(args.cik, form_type=args.form, limit=int(args.limit))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        if not filings:
            print("No filings found")
            return 0

        print(f"Recent filings for {filings[0].company_name} (CIK: {filings[0].cik}):\n")
        for f in filings:
            print(f"  {f.form_type:8} {f.filing_date}  {f.accession}")
        return 0

    return asyncio.run(_run())


def _cmd_cache(args: Any) -> int:
    from .config import CACHE_DIR
    from .sec.cache import DiskCache

    cache = DiskCache(CACHE_DIR)
    cache_dir = cache.cache_dir

    if not cache_dir.exists():
        print(f"Cache directory: {cache_dir} (empty)")
        return 0

    if args.clear:
        import shutil

        try:
            shutil.rmtree(cache_dir)
        except Exception as e:
            print(f"Error clearing cache: {e}", file=sys.stderr)
            return 1
        print(f"Cleared cache: {cache_dir}")
        return 0

    total_size = 0
    file_count = 0
    for f in cache_dir.rglob("*"):
        if f.is_file():
            total_size += f.stat().st_size
            file_count += 1

    size_mb = total_size / (1024 * 1024)
    print(f"Cache directory: {cache_dir}")
    print(f"Files: {file_count}")
    print(f"Size: {size_mb:.1f} MB")
    return 0


def _cmd_site(args: Any) -> int:
    from .site.build import build_site

    report = build_site(args.packs, args.out, base_url=args.base_url)
    print("✓ Site generated")
    print(f"  Output: {report.get('out_dir')}")
    print(f"  Companies: {report.get('companies')}")
    print(f"  Filings: {report.get('filings')}")
    total_bytes = int(report.get('total_bytes') or 0)
    print(f"  Size: {total_bytes / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    app()

