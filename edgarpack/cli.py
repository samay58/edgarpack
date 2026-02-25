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
    """Parse CLI arguments and dispatch to the selected subcommand."""
    parser = argparse.ArgumentParser(
        prog="edgarpack",
        description="llms.txt for SEC filings - build deterministic markdown packs.",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"EdgarPack {__version__}",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Build a filing pack")
    p_build.add_argument(
        "--cik",
        "-c",
        required=True,
        help="CIK number (with or without leading zeros)",
    )
    p_build.add_argument(
        "--accession",
        "-a",
        help="Accession number (e.g., 0000320193-24-000123)",
    )
    p_build.add_argument(
        "--form",
        "-f",
        help="Form type: 10-K, 10-Q, 8-K (fetches latest)",
    )
    p_build.add_argument(
        "--out",
        "-o",
        type=Path,
        default=Path("./packs"),
        help="Output directory",
    )
    p_build.add_argument(
        "--with-chunks",
        action="store_true",
        help="Generate chunks.ndjson for RAG",
    )
    p_build.add_argument(
        "--with-xbrl",
        action="store_true",
        help="Generate xbrl.json with financial data",
    )
    p_build.add_argument(
        "--force",
        action="store_true",
        help="Bypass cache and rebuild",
    )

    p_company = sub.add_parser("company-llms", help="Generate company-level llms.txt")
    p_company.add_argument("--cik", "-c", required=True, help="CIK number")
    p_company.add_argument(
        "--out",
        "-o",
        type=Path,
        default=Path("./packs"),
        help="Packs output directory",
    )

    p_list = sub.add_parser("list", help="List recent filings for a company")
    p_list.add_argument("--cik", "-c", required=True, help="CIK number")
    p_list.add_argument("--form", "-f", help="Filter by form type")
    p_list.add_argument("--limit", "-n", type=int, default=10, help="Number of filings to show")

    p_cache = sub.add_parser("cache", help="Show cache info or clear cache")
    p_cache.add_argument("--clear", action="store_true", help="Clear the cache")

    p_site = sub.add_parser("site", help="Generate a minimal static site from packs")
    p_site.add_argument(
        "--packs",
        type=Path,
        default=Path("./packs"),
        help="Directory containing packs",
    )
    p_site.add_argument(
        "--out",
        "-o",
        type=Path,
        default=Path("./site"),
        help="Site output directory",
    )
    p_site.add_argument("--base-url", default=None, help="Optional base URL (reserved)")

    p_api = sub.add_parser("api", help="Run China Lens FastAPI server (requires extra deps)")
    p_api.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1)",
    )
    p_api.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind (default: 8000)",
    )

    # --- query subcommand ---
    p_query = sub.add_parser(
        "query",
        help="Query financial metrics for a company (cited from SEC filings)",
    )
    p_query.add_argument("company", help="Ticker symbol (NVDA) or CIK number")
    p_query.add_argument(
        "metrics",
        nargs="?",
        default=None,
        help="Comma-separated metric names (e.g. revenue,net_income). Omit for all.",
    )
    p_query.add_argument(
        "--period",
        "-p",
        default="lfy",
        help="Period: lfy, mrq, ltm, ltm-1, mrp, annual:N, quarterly:N (default: lfy)",
    )
    p_query.add_argument(
        "--format",
        dest="output_format",
        choices=["table", "json", "json-full"],
        default="table",
        help="Output format: table, json (lean), json-full (verbose). Default: table",
    )
    p_query.add_argument("--force", action="store_true", help="Bypass cache")

    # --- harvest subcommand ---
    p_harvest = sub.add_parser(
        "harvest",
        help="Bulk-download and build filing packs from a universe definition",
    )
    p_harvest.add_argument(
        "--universe",
        "-u",
        type=Path,
        default=Path("universe.toml"),
        help="Path to universe.toml (default: ./universe.toml)",
    )
    p_harvest.add_argument(
        "--out",
        "-o",
        type=Path,
        default=Path("./packs"),
        help="Output directory for packs",
    )
    p_harvest.add_argument(
        "--plan",
        action="store_true",
        help="Dry run: show what would be fetched without downloading",
    )
    p_harvest.add_argument(
        "--refresh",
        action="store_true",
        help="Only build filings not yet in registry",
    )
    p_harvest.add_argument(
        "--with-chunks",
        action="store_true",
        help="Generate chunks.ndjson for each pack (needed for search index)",
    )
    p_harvest.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Maximum concurrent SEC requests (default: 3)",
    )
    p_harvest.add_argument("--force", action="store_true", help="Rebuild all packs")

    # --- diff subcommand ---
    p_diff = sub.add_parser(
        "diff",
        help="Diff two filings of the same company (latest vs. prior by default)",
    )
    p_diff.add_argument(
        "--ticker",
        "-t",
        help="Company ticker (uses registry to find packs)",
    )
    p_diff.add_argument("--form", "-f", default="10-K", help="Form type (default: 10-K)")
    p_diff.add_argument("--before", help="Accession number or pack dir of earlier filing")
    p_diff.add_argument("--after", help="Accession number or pack dir of later filing")
    p_diff.add_argument(
        "--format",
        dest="output_format",
        choices=["summary", "full", "json"],
        default="summary",
        help="Output format (default: summary)",
    )

    # --- timeline subcommand ---
    p_timeline = sub.add_parser(
        "timeline",
        help="Show how a section evolved across filings",
    )
    p_timeline.add_argument("--ticker", "-t", required=True, help="Company ticker")
    p_timeline.add_argument(
        "--section",
        "-s",
        required=True,
        help="Section ID (e.g. 10k_parti_item1a_risk_factors)",
    )
    p_timeline.add_argument("--form", "-f", default="10-K", help="Form type (default: 10-K)")

    # --- search subcommand ---
    p_search = sub.add_parser(
        "search",
        help="Full-text search across the filing corpus",
    )
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--topic", help="Filter by topic tag (e.g. risk:export_controls)")
    p_search.add_argument("--ticker", help="Filter by company ticker")
    p_search.add_argument("--form", help="Filter by form type")
    p_search.add_argument("--limit", "-n", type=int, default=20, help="Max results (default: 20)")

    # --- index subcommand ---
    p_index = sub.add_parser(
        "index",
        help="Build the search index from harvested packs",
    )
    p_index.add_argument(
        "--packs",
        type=Path,
        default=Path("./packs"),
        help="Packs directory to index (default: ./packs)",
    )

    # --- comps subcommand ---
    p_comps = sub.add_parser(
        "comps",
        help="Compare financial metrics across companies",
    )
    p_comps.add_argument("companies", nargs="+", help="Ticker symbols or CIK numbers")
    p_comps.add_argument(
        "--metrics",
        "-m",
        required=True,
        help="Comma-separated metric names",
    )
    p_comps.add_argument(
        "--period",
        "-p",
        default="lfy",
        help="Period: lfy, mrq, ltm, ltm-1, mrp (default: lfy)",
    )
    p_comps.add_argument(
        "--format",
        dest="output_format",
        choices=["table", "json", "json-full"],
        default="table",
        help="Output format: table, json (lean), json-full (verbose). Default: table",
    )
    p_comps.add_argument("--force", action="store_true", help="Bypass cache")

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
    if args.cmd == "api":
        return _cmd_api(args)
    if args.cmd == "query":
        return _cmd_query(args)
    if args.cmd == "comps":
        return _cmd_comps(args)
    if args.cmd == "harvest":
        return _cmd_harvest(args)
    if args.cmd == "diff":
        return _cmd_diff(args)
    if args.cmd == "timeline":
        return _cmd_timeline(args)
    if args.cmd == "search":
        return _cmd_search(args)
    if args.cmd == "index":
        return _cmd_index(args)

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
    total_bytes = int(report.get("total_bytes") or 0)
    print(f"  Size: {total_bytes / 1024:.1f} KB")
    return 0


def _cmd_api(args: Any) -> int:
    try:
        import uvicorn
    except Exception:
        print(
            "Error: uvicorn is not installed. Install with: uv pip install -e '.[china]'",
            file=sys.stderr,
        )
        return 1

    try:
        from .api.main import create_app
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    app = create_app()
    uvicorn.run(app, host=str(args.host), port=int(args.port))
    return 0


def _cmd_query(args: Any) -> int:
    async def _run() -> int:
        from .query.comps import _format_value
        from .query.financials import financials

        try:
            result = await financials(
                company=args.company,
                metrics=args.metrics,
                period=args.period,
                force=bool(args.force),
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        if args.output_format == "json":
            import json

            print(json.dumps(result.to_lean_dict(), indent=2, default=str))
            return 0

        if args.output_format == "json-full":
            import json

            print(json.dumps(result.to_cited_dict(), indent=2, default=str))
            return 0

        # Table format
        print(f"{result.company} (CIK: {result.cik})\n")
        citations: list[tuple[str, str | None]] = []
        seen_citations: set[str] = set()
        for metric_name, cited in result.metrics.items():
            label = metric_name.replace("_", " ").title()
            if cited is None:
                print(f"  {label}: N/A")
            elif isinstance(cited, list):
                print(f"  {label}:")
                for item in cited:
                    if item.value is None:
                        continue
                    formatted = _format_value(item)
                    period_label = f"{item.fiscal_period}{item.fiscal_year}"
                    print(f"    {period_label}: {formatted}")
                    cite = item.citation
                    if cite not in seen_citations:
                        seen_citations.add(cite)
                        citations.append((cite, item.viewer_url))
            elif cited.value is None:
                print(f"  {label}: N/A")
            else:
                formatted = _format_value(cited)
                print(f"  {label}: {formatted}")
                cite = cited.citation
                if cite not in seen_citations:
                    seen_citations.add(cite)
                    citations.append((cite, cited.viewer_url))

        if citations:
            print("\nSources:")
            for cite_text, viewer in citations:
                print(f"  - {cite_text}")
                if viewer:
                    print(f"    {viewer}")

        return 0

    return asyncio.run(_run())


def _cmd_comps(args: Any) -> int:
    async def _run() -> int:
        from .query.comps import comps, comps_to_json, comps_to_lean_json, format_comps_table

        metric_list = [m.strip() for m in args.metrics.split(",")]

        try:
            results = await comps(
                companies=args.companies,
                metrics=metric_list,
                period=args.period,
                force=bool(args.force),
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        if args.output_format == "json":
            print(comps_to_lean_json(results, metric_list, args.period))
        elif args.output_format == "json-full":
            print(comps_to_json(results))
        else:
            print(format_comps_table(results, metric_list))

        return 0

    return asyncio.run(_run())


def _cmd_harvest(args: Any) -> int:
    if not args.universe.exists():
        print(f"Error: universe file not found: {args.universe}", file=sys.stderr)
        return 2

    async def _run() -> int:
        from .harvest.planner import plan_harvest
        from .harvest.registry import PackRegistry
        from .harvest.runner import run_harvest
        from .harvest.universe import load_universe

        universe = load_universe(args.universe)
        registry = PackRegistry()

        print(
            f"Universe: {len(universe.companies)} companies from {args.universe}",
            file=sys.stderr,
        )

        plan = await plan_harvest(universe, registry, refresh=bool(args.refresh))

        print(
            f"Plan: {plan.total_filings} total, {plan.new_filings} new, "
            f"{plan.already_built} already built",
            file=sys.stderr,
        )

        if args.plan:
            # Dry run: print plan and exit
            for item in plan.items:
                status = "SKIP" if item.already_built else "NEW"
                print(f"  [{status}] {item.ticker} {item.form_type} {item.filing_date}")
            return 0

        summary = await run_harvest(
            plan,
            out_dir=args.out,
            registry=registry,
            concurrency=int(args.concurrency),
            with_chunks=bool(args.with_chunks),
            force=bool(args.force),
        )

        registry.close()
        return 1 if summary.get("failed", 0) > 0 else 0

    return asyncio.run(_run())


def _cmd_diff(args: Any) -> int:
    from pathlib import Path

    async def _run() -> int:
        from .diff.section_diff import diff_filings

        before_dir: Path | None = None
        after_dir: Path | None = None

        if args.before and args.after:
            before_dir = Path(args.before)
            after_dir = Path(args.after)
        elif args.ticker:
            from .harvest.registry import PackRegistry

            registry = PackRegistry()
            packs = registry.list_packs(ticker=args.ticker, form_type=args.form)
            registry.close()

            if len(packs) < 2:
                print(
                    f"Error: need at least 2 {args.form} filings for {args.ticker}, "
                    f"found {len(packs)}",
                    file=sys.stderr,
                )
                return 1

            after_dir = Path(packs[0].pack_dir)
            before_dir = Path(packs[1].pack_dir)
        else:
            print("Error: provide --ticker or both --before and --after", file=sys.stderr)
            return 2

        if not before_dir.exists() or not after_dir.exists():
            print("Error: pack directory not found on disk", file=sys.stderr)
            return 1

        result = diff_filings(before_dir, after_dir)

        if args.output_format == "json":
            import json

            print(json.dumps(result.model_dump(), indent=2, default=str))
            return 0

        # Summary format
        print(f"{result.company} {result.form_type}")
        print(f"  Before: {result.before_date} ({result.before_accession})")
        print(f"  After:  {result.after_date} ({result.after_accession})")
        print(
            f"  Sections: {result.sections_unchanged} unchanged, "
            f"{result.sections_modified} modified, "
            f"{result.sections_added} added, "
            f"{result.sections_removed} removed"
        )
        print(f"  Overall change intensity: {result.overall_change_intensity:.1%}")

        if args.output_format == "full":
            print()
            for delta in result.section_deltas:
                if delta.change_type.value == "unchanged":
                    continue
                print(f"  [{delta.change_type.value.upper()}] {delta.title} ({delta.section_id})")
                if delta.change_type.value == "modified":
                    print(
                        f"    +{delta.paragraphs_added} -{delta.paragraphs_removed} "
                        f"~{delta.paragraphs_modified} ={delta.paragraphs_unchanged}"
                    )
                    print(f"    Change intensity: {delta.change_intensity:.1%}")

        return 0

    return asyncio.run(_run())


def _cmd_timeline(args: Any) -> int:
    async def _run() -> int:
        from .diff.timeline import build_timeline
        from .harvest.registry import PackRegistry

        registry = PackRegistry()
        packs = registry.list_packs(ticker=args.ticker, form_type=args.form)
        registry.close()

        if not packs:
            print(f"No {args.form} filings found for {args.ticker}", file=sys.stderr)
            return 1

        # Sort ascending by filing date
        packs.sort(key=lambda p: p.filing_date)
        pack_dirs = [Path(p.pack_dir) for p in packs if Path(p.pack_dir).exists()]

        entries = build_timeline(pack_dirs, args.section)

        print(f"Timeline: {args.ticker} / {args.section} / {args.form}\n")
        for entry in entries:
            if not entry.section_found:
                print(f"  {entry.filing_date} ({entry.accession}): section not found")
                continue

            if entry.delta is None:
                print(f"  {entry.filing_date} ({entry.accession}): initial ({entry.tokens} tokens)")
            elif entry.delta.change_type.value == "unchanged":
                print(f"  {entry.filing_date} ({entry.accession}): unchanged")
            else:
                d = entry.delta
                print(
                    f"  {entry.filing_date} ({entry.accession}): "
                    f"+{d.paragraphs_added} -{d.paragraphs_removed} ~{d.paragraphs_modified} "
                    f"({d.change_intensity:.0%} changed)"
                )

        return 0

    return asyncio.run(_run())


def _cmd_search(args: Any) -> int:
    from .index.search import search_corpus

    result = search_corpus(
        query=args.query,
        topic=args.topic,
        ticker=args.ticker,
        form_type=args.form,
        limit=int(args.limit),
    )

    if result.total_hits == 0:
        print("No results found.")
        return 0

    print(f"Found {result.total_hits} results across {len(result.companies)} companies\n")
    if result.topics_found:
        print(f"Topics: {', '.join(result.topics_found)}\n")

    for hit in result.hits:
        company = hit.ticker or hit.cik
        print(f"  [{company}] {hit.form_type} {hit.filing_date} - {hit.section_id}")
        snippet = hit.snippet.replace("\n", " ").strip()
        if len(snippet) > 200:
            snippet = snippet[:200] + "..."
        print(f"    {snippet}")
        print()

    return 0


def _cmd_index(args: Any) -> int:
    """Build the search index from all packs in a directory."""
    from .harvest.registry import PackRegistry
    from .index.inverted import SearchIndex

    packs_dir = Path(args.packs)
    if not packs_dir.exists():
        print(f"Error: packs directory not found: {packs_dir}", file=sys.stderr)
        return 2

    registry = PackRegistry()
    index = SearchIndex()

    packs = registry.list_packs()
    if not packs:
        print("No packs in registry. Run harvest first.", file=sys.stderr)
        return 1

    total_chunks = 0
    for i, pack in enumerate(packs, 1):
        pack_dir = Path(pack.pack_dir)
        if not pack_dir.exists():
            label = f"{pack.ticker} {pack.form_type} {pack.filing_date}"
            print(f"  [{i}/{len(packs)}] {label} ... SKIP (dir missing)")
            continue
        count = index.index_pack(pack_dir, ticker=pack.ticker)
        total_chunks += count
        label = f"{pack.ticker} {pack.form_type} {pack.filing_date}"
        print(f"  [{i}/{len(packs)}] {label} ... {count} chunks")

    print(f"\nIndexed {total_chunks} chunks from {len(packs)} packs", file=sys.stderr)

    registry.close()
    index.close()
    return 0


if __name__ == "__main__":
    app()
