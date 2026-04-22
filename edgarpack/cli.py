"""CLI entry point for EdgarPack. Uses argparse directly (no third-party CLI
framework) so the project runs in constrained environments without extra deps.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import textwrap
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .errors import AmbiguousCompany, UnknownCompany


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc


async def _resolve_cli_company(query: str) -> Any:
    """Resolve a CLI company-like argument to a canonical ResolvedCompany.

    Tries ``universe.toml`` first (for HKEX routing, private-company detection,
    and alias fast-path), then falls back to the SEC ticker/name universe.

    Raises:
        UnknownCompany: nothing matched, with "Did you mean: ..." suggestions.
        AmbiguousCompany: the name matches multiple SEC titles; user must
            disambiguate with a ticker.
    """
    from .identity import ResolvedCompany, load_identity, resolve
    from .sec.tickers import resolve_company as resolve_sec_company

    universe_path = Path("universe.toml")
    index = None
    if universe_path.exists():
        try:
            index = load_identity(universe_path)
        except AmbiguousCompany:
            raise
        except Exception:
            index = None

    if index is not None:
        for kwargs in (
            {"ticker": query, "company": None},
            {"ticker": None, "company": query},
        ):
            try:
                res = resolve(index, **kwargs)
            except UnknownCompany:
                continue
            # universe.toml entries often omit CIK for US issuers. Fall
            # through to SEC in that case so callers always get a CIK.
            if res.cik or res.private or res.source == "HKEX":
                return res

    cik, ticker, title = await resolve_sec_company(query)
    return ResolvedCompany(
        ticker=ticker or query.strip().upper(),
        listing=None,
        source="SEC",
        cik=cik,
        hk_stock_code=None,
        aliases=(title,) if title else (),
        private=False,
    )


def _canonical_company_label(resolved: Any, fallback: str) -> str:
    """Best-effort display label for a resolved company argument."""
    aliases = getattr(resolved, "aliases", ()) or ()
    if aliases:
        first = aliases[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    ticker = getattr(resolved, "ticker", None)
    if isinstance(ticker, str) and ticker.strip():
        return ticker.strip().upper()
    return fallback


def _preferred_company_arg(resolved: Any, fallback: str) -> str:
    """Best command-line company token for examples and remediation text."""
    ticker = getattr(resolved, "ticker", None)
    if isinstance(ticker, str) and ticker.strip():
        return ticker.strip().upper()
    return fallback


def _group_build_warnings(warnings: list[str]) -> list[str]:
    """Collapse repeated low-signal build warnings into grouped summaries."""
    counts = Counter(warnings)
    lines: list[str] = []

    duplicate_count = counts.pop("Duplicate section ID detected, suffix added", 0)
    if duplicate_count:
        noun = "section" if duplicate_count == 1 else "sections"
        verb = "was" if duplicate_count == 1 else "were"
        lines.append(f"Duplicate section IDs: {duplicate_count} {noun} {verb} de-duped")

    preamble_count = counts.pop("Content before first detected section", 0)
    if preamble_count:
        noun = "boundary issue" if preamble_count == 1 else "boundary issues"
        lines.append(f"Content before first detected section: {preamble_count} {noun}")

    token_count = counts.pop("Token counts are approximate (tiktoken not installed)", 0)
    if token_count:
        lines.append("Token counts are approximate (tiktoken not installed)")

    for message, count in sorted(counts.items()):
        if count == 1:
            lines.append(message)
        else:
            lines.append(f"{message} ({count}x)")
    return lines


def _register_pack_result(result: Any, *, ticker: str | None = None) -> None:
    """Register a successful standalone build in PackRegistry."""
    from .harvest.registry import PackRegistry
    from .pack.manifest import compute_sha256

    filing = result.filing_meta or {}
    accession = filing.get("accession")
    cik = filing.get("cik")
    form_type = filing.get("form_type")
    filing_date = filing.get("filing_date")
    company_name = filing.get("company_name")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (accession, cik, form_type, filing_date, company_name)
    ):
        return

    manifest_path = Path(result.output_dir) / "manifest.json"
    manifest_hash = compute_sha256(manifest_path.read_bytes()) if manifest_path.exists() else None

    registry = PackRegistry()
    try:
        registry.register(
            accession=accession,
            cik=cik,
            ticker=ticker,
            company_name=company_name,
            form_type=form_type,
            filing_date=filing_date,
            sections_count=int(result.sections_count),
            tokens_total=int(result.tokens_total),
            pack_dir=str(result.output_dir),
            manifest_hash=manifest_hash,
            warnings=result.warnings if result.warnings else None,
        )
    finally:
        registry.close()


def app(argv: list[str] | None = None) -> None:
    """Console script entrypoint (kept as `app` for packaging compatibility)."""
    try:
        raise SystemExit(main(argv))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130) from None


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

    p_build = sub.add_parser(
        "build",
        help="Build a single filing pack, or a range via --last/--after/--before",
        description=(
            "Build and register a filing pack. "
            "Examples: `edgarpack build AAPL --form 10-K` (latest), "
            "`edgarpack build AAPL --form 10-K --last 5` (five most recent), "
            "`edgarpack build AAPL --form 10-K --after 2020-01-01 --before 2022-12-31`."
        ),
    )
    p_build.add_argument(
        "company",
        nargs="?",
        help="Ticker or company name first (e.g. FIG, Figma, NVDA). CIK also accepted.",
    )
    p_build.add_argument(
        "--cik",
        "-c",
        help="[deprecated] CIK number. Prefer the positional company argument.",
    )
    p_build.add_argument(
        "--accession",
        "-a",
        help="Accession number (e.g., 0000320193-24-000123)",
    )
    p_build.add_argument(
        "--form",
        "-f",
        help=(
            "Form type: 10-K, 10-Q, 8-K. "
            "Defaults to 10-K when combined with --last/--after/--before; "
            "fetches latest when used alone."
        ),
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
    p_build.add_argument(
        "--last",
        type=int,
        default=None,
        help="Build the N most recent filings of --form. Mutually exclusive with --accession.",
    )
    p_build.add_argument(
        "--after",
        type=_parse_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Lower bound on filing date for range builds.",
    )
    p_build.add_argument(
        "--before",
        type=_parse_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Upper bound on filing date for range builds.",
    )

    p_doctor = sub.add_parser(
        "doctor",
        help="Diagnose a pack directory or sweep every pack for a ticker",
        description=(
            "Inspect pack manifest state, artifact inventory, and KPI coverage. "
            "Pass a pack path for a single-pack report, or a ticker for a sweep."
        ),
    )
    p_doctor.add_argument(
        "target",
        help=(
            "Pack directory (e.g. ./packs/0000320193/0000320193-24-000001) or ticker (e.g. AAPL)"
        ),
    )
    p_doctor.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    p_company = sub.add_parser("company-llms", help="Generate company-level llms.txt")
    p_company.add_argument(
        "company",
        nargs="?",
        help="Ticker, CIK, or company name",
    )
    p_company.add_argument(
        "--cik",
        "-c",
        help="[deprecated] CIK number. Prefer the positional company argument.",
    )
    p_company.add_argument(
        "--out",
        "-o",
        type=Path,
        default=Path("./packs"),
        help="Packs output directory",
    )

    p_list = sub.add_parser("list", help="List recent filings for a company")
    p_list.add_argument(
        "company",
        nargs="?",
        help="Ticker, CIK, or company name",
    )
    p_list.add_argument(
        "--cik",
        "-c",
        help="[deprecated] CIK number. Prefer the positional company argument.",
    )
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

    p_query = sub.add_parser(
        "query",
        help="Query financial metrics for a company (cited from SEC filings)",
    )
    p_query.add_argument(
        "company",
        help="Ticker symbol (NVDA), CIK number, or company name (e.g. NVIDIA)",
    )
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
        help=(
            "Period selector(s). Scalars: lfy, mrq, ltm, lfy-N, ltm-N, mrq-N, mrp. "
            "Series: annual:N, quarterly:N. "
            "CSV list for a multi-period grid: lfy,lfy-1,lfy-2 "
            "(scalar selectors only; series cannot be combined). Default: lfy."
        ),
    )
    p_query.add_argument(
        "--preset",
        choices=["perf"],
        help="Expand to a curated metric list. Combines with --metrics (union, preset first).",
    )
    p_query.add_argument(
        "--format",
        dest="output_format",
        choices=["table", "json", "json-full"],
        default="table",
        help="Output format: table, json (lean), json-full (verbose). Default: table",
    )
    p_query.add_argument(
        "--audit",
        action="store_true",
        help="Show structured audit blocks for derived/LTM metrics",
    )
    p_query.add_argument(
        "--show-links",
        choices=["primary", "all", "none"],
        default="primary",
        help="Link verbosity in table output (default: primary)",
    )
    p_query.add_argument(
        "--citations",
        choices=["inline", "footer", "off"],
        default=None,
        help=(
            "Citation placement in table output. Default: 'inline' for single-period, "
            "'footer' for multi-period grids."
        ),
    )
    p_query.add_argument("--force", action="store_true", help="Bypass cache")
    p_query.add_argument(
        "--strict",
        action="store_true",
        help="Reject values resolved via the self-heal path (learned mappings). "
        "Only hardcoded METRIC_MAP resolutions are returned.",
    )
    p_query.add_argument(
        "--currency",
        choices=["native", "usd", "both"],
        default="both",
        help="Currency output: native (reporting currency only), usd (USD only), both.",
    )

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

    p_search = sub.add_parser(
        "search",
        help="Full-text search across the filing corpus",
    )
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--topic", help="Filter by topic tag (e.g. risk:export_controls)")
    p_search.add_argument("--ticker", help="Filter by company ticker")
    p_search.add_argument("--form", help="Filter by form type")
    p_search.add_argument("--limit", "-n", type=int, default=20, help="Max results (default: 20)")

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
    p_index.add_argument(
        "--incremental",
        action="store_true",
        help="Only index packs not yet marked as indexed in the registry",
    )

    p_comps = sub.add_parser(
        "comps",
        help="Compare financial metrics across companies",
    )
    p_comps.add_argument(
        "companies",
        nargs="+",
        help="Tickers, CIKs, or company names",
    )
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
    p_comps.add_argument(
        "--audit",
        action="store_true",
        help="Show expanded calculation details under the table",
    )
    p_comps.add_argument(
        "--show-links",
        choices=["primary", "all", "none"],
        default="primary",
        help="Link verbosity in table output (default: primary)",
    )
    p_comps.add_argument(
        "--citations",
        choices=["inline", "footer", "off"],
        default="inline",
        help="Citation placement in table output (default: inline)",
    )
    p_comps.add_argument("--force", action="store_true", help="Bypass cache")
    p_comps.add_argument(
        "--strict",
        action="store_true",
        help="Reject values resolved via self-heal (learned mappings, text scans). "
        "Only deterministic hardcoded METRIC_MAP resolutions survive.",
    )

    p_learned = sub.add_parser(
        "learned",
        help="Inspect or manage the self-heal learned_concepts registry",
    )
    learned_sub = p_learned.add_subparsers(dest="learned_cmd", required=True)

    p_learned_list = learned_sub.add_parser("list", help="List learned mappings")
    p_learned_list.add_argument("--cik", help="Filter by CIK")
    p_learned_list.add_argument("--metric", help="Filter by metric name")
    p_learned_list.add_argument(
        "--source",
        choices=["fuzzy", "llm", "user", "kpi-llm"],
        help="Filter by source mechanism",
    )
    p_learned_list.add_argument(
        "--unverified",
        action="store_true",
        help="Show only unverified mappings",
    )

    p_learned_show = learned_sub.add_parser("show", help="Show one mapping")
    p_learned_show.add_argument("cik")
    p_learned_show.add_argument("metric")

    p_learned_verify = learned_sub.add_parser(
        "verify",
        help="Promote an unverified mapping to verified",
    )
    p_learned_verify.add_argument("cik")
    p_learned_verify.add_argument("metric")

    p_learned_clear = learned_sub.add_parser("clear", help="Delete mappings")
    p_learned_clear.add_argument("--cik")
    p_learned_clear.add_argument("--metric")
    p_learned_clear.add_argument(
        "--all",
        action="store_true",
        help="Clear everything (required if no filter is provided)",
    )

    p_which = sub.add_parser(
        "which",
        help=(
            "List the qualitative / MD&A KPIs a company discloses across its "
            "filings (e.g. Figma's key business metrics)."
        ),
    )
    p_which.add_argument(
        "company",
        help="Ticker or company name (e.g. FIG, Figma). CIK also accepted.",
    )
    p_which.add_argument(
        "--format",
        dest="which_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    p_which.add_argument(
        "--no-cache",
        action="store_true",
        help="Re-run discovery on every filing (expensive; one LLM call per pack)",
    )
    p_which.add_argument(
        "--only",
        choices=["all", "discovered", "catalog"],
        default="all",
        help="Restrict output to discovered-only or catalog-only rows",
    )
    p_which.add_argument(
        "--max-periods",
        type=int,
        default=6,
        help="Max period columns to render in the table view (default: 6)",
    )

    p_compare = sub.add_parser("compare", help="Side-by-side comparison of two or more companies")
    p_compare.add_argument(
        "companies",
        nargs="+",
        help="Two or more tickers, CIKs, or company names",
    )
    p_compare.add_argument("--metrics", help="Comma-separated metric names")
    p_compare.add_argument("--period", default="lfy", help="Fiscal period (default: lfy)")
    p_compare.add_argument(
        "--currency",
        choices=["native", "usd", "both"],
        default="both",
        help="Currency output mode",
    )
    p_compare.add_argument(
        "--format",
        dest="compare_format",
        choices=["table", "json", "markdown"],
        default="table",
        help="Output format",
    )
    p_compare.add_argument(
        "--strict",
        action="store_true",
        help="Reject values resolved via self-heal (learned mappings, text scans). "
        "Only deterministic hardcoded METRIC_MAP resolutions survive.",
    )

    p_build_sse = sub.add_parser(
        "build-sse",
        help="Build a pack from an SSE (Shanghai Stock Exchange) prospectus PDF",
    )
    p_build_sse.add_argument(
        "--url", required=True, help="URL of the PDF on the SSE disclosure platform"
    )
    p_build_sse.add_argument("--stock-code", required=True, help="SSE stock code (e.g. 301536)")
    p_build_sse.add_argument("--company", required=True, help="Company name")
    p_build_sse.add_argument("--filing-date", required=True, help="Filing date (YYYY-MM-DD)")
    p_build_sse.add_argument(
        "--out", "-o", type=Path, default=Path("./packs"), help="Output directory"
    )
    p_build_sse.add_argument("--pdf", type=Path, help="Local PDF file (skip download)")
    p_build_sse.add_argument(
        "--with-chunks", action="store_true", help="Generate chunks.ndjson for RAG"
    )
    p_build_sse.add_argument(
        "--translate",
        action="store_true",
        help="Run the zh->en translation pipeline (requires EDGARPACK_DEEPINFRA_KEY)",
    )
    p_build_sse.add_argument(
        "--translate-model",
        default="deepseek-ai/DeepSeek-V3",
        help="DeepInfra model ID for translation",
    )
    p_build_sse.add_argument("--force", action="store_true", help="Rebuild even if exists")

    p_translate = sub.add_parser(
        "translate-sse",
        help="Translate an existing SSE pack to English (requires EDGARPACK_DEEPINFRA_KEY)",
    )
    p_translate.add_argument("--pack", type=Path, required=True, help="Path to SSE pack directory")
    p_translate.add_argument(
        "--model",
        default="deepseek-ai/DeepSeek-V3",
        help="DeepInfra model ID",
    )
    p_translate.add_argument("--force", action="store_true", help="Re-translate even if exists")

    args = parser.parse_args(argv)

    if args.cmd == "compare":
        from .compare import cmd_compare

        return cmd_compare(args)

    if args.cmd == "build-sse":
        return _cmd_build_sse(args)
    if args.cmd == "translate-sse":
        return _cmd_translate_sse(args)
    if args.cmd == "build":
        return _cmd_build(args)
    if args.cmd == "doctor":
        return _cmd_doctor(args)
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
    if args.cmd == "learned":
        return _cmd_learned(args)
    if args.cmd == "which":
        return _cmd_which(args)

    parser.print_help()
    return 2


async def _resolve_ticker_arg(value: str | None) -> tuple[int, str | None]:
    """Resolve a --ticker flag (which now accepts names) to a canonical ticker."""
    if not value:
        return 0, None
    try:
        resolved = await _resolve_cli_company(value)
    except (UnknownCompany, AmbiguousCompany) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, None
    return 0, resolved.ticker


async def _cik_from_company_args(args: Any) -> tuple[int, str | None]:
    """Resolve CIK from a build/list/company-llms-style args namespace.

    Returns ``(exit_code, cik)``. ``exit_code == 0`` means success; a non-zero
    value means the caller should return that code immediately.

    Accepts either the positional ``args.company`` argument or the deprecated
    ``--cik`` flag. Refuses to proceed if both (or neither) were supplied.
    """
    company = getattr(args, "company", None)
    cik = getattr(args, "cik", None)

    if company and cik:
        print(
            "Error: pass either the positional company argument OR --cik, not both.",
            file=sys.stderr,
        )
        return 2, None

    if not company and not cik:
        print(
            "Error: a company argument is required (ticker, CIK, or company name).",
            file=sys.stderr,
        )
        return 2, None

    if cik and not company:
        print(
            "Warning: --cik is deprecated; pass the ticker, CIK, or company "
            "name as a positional argument instead.",
            file=sys.stderr,
        )
        return 0, cik

    try:
        resolved = await _resolve_cli_company(company)
    except (UnknownCompany, AmbiguousCompany) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, None

    if resolved.private:
        print(
            f"Error: {resolved.ticker} is a private company with no public filings.",
            file=sys.stderr,
        )
        return 2, None

    if not resolved.cik:
        print(
            f"Error: no CIK available for {resolved.ticker}. "
            "Pass --cik explicitly or use a different identifier.",
            file=sys.stderr,
        )
        return 2, None

    return 0, resolved.cik


def _cmd_doctor(args: Any) -> int:
    from .harvest.registry import PackRegistry
    from .pack.doctor import diagnose_pack

    target = args.target
    target_path = Path(target)
    is_path = target_path.exists() and target_path.is_dir()

    registry = PackRegistry()
    results: list = []

    if is_path:
        diag = diagnose_pack(target_path, registry=registry)
        results.append(diag)
    else:

        async def _resolve() -> str | None:
            try:
                resolved = await _resolve_cli_company(target)
            except (UnknownCompany, AmbiguousCompany) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return None
            return resolved.cik

        cik = asyncio.run(_resolve())
        if cik is None:
            return 2
        records = registry.list_packs(cik=cik)
        if not records:
            print(f"No packs registered for {target} (CIK: {cik}). Run `edgarpack build {target}`.")
            return 0
        for rec in records:
            diag = diagnose_pack(Path(rec.pack_dir), registry=registry)
            results.append(diag)

    if args.format == "json":
        payload = (
            results[0].model_dump()
            if len(results) == 1
            else {"packs": [r.model_dump() for r in results]}
        )
        print(json.dumps(payload, indent=2, default=str))
        return 0

    for idx, diag in enumerate(results):
        if idx > 0:
            print("")
        header = diag.accession or Path(diag.pack_dir).name
        print(f"Pack: {header}")
        print(f"  Path: {diag.pack_dir}")
        print(f"  Manifest: {diag.manifest_state}", end="")
        if diag.manifest_error:
            print(f" ({diag.manifest_error})")
        else:
            print("")
        if diag.manifest_state == "ok":
            print(f"  Filing: {diag.form_type} filed {diag.filing_date} ({diag.company_name})")
            print(f"  Sections: {diag.sections_count}  Tokens: {diag.tokens_total:,}")
            if diag.artifacts_present:
                art_line = ", ".join(
                    f"{name} ({diag.artifact_sizes.get(name, 0):,}B)"
                    for name in diag.artifacts_present
                )
                print(f"  Artifacts: {art_line}")
            print(
                f"  Coverage: {diag.catalog_concepts_resolved}/"
                f"{diag.catalog_concepts_total} catalog concepts resolved"
            )
            print(f"  Discovered KPIs: {diag.discovered_kpi_count}")
            health = "healthy" if diag.healthy else "low coverage"
            print(f"  Health: {health}")
        if diag.remediation:
            print(f"  Remediation: {diag.remediation}")

    if len(results) > 1:
        healthy = sum(1 for r in results if r.healthy)
        print("")
        print(
            f"Summary: {healthy}/{len(results)} packs healthy, "
            f"{len(results) - healthy} need attention"
        )

    return 0


def _cmd_build(args: Any) -> int:
    last = getattr(args, "last", None)
    after = getattr(args, "after", None)
    before = getattr(args, "before", None)
    range_flags = (last is not None, after is not None, before is not None)
    is_range = any(range_flags)

    if args.accession and is_range:
        print(
            "Error: use either --accession (one filing) or "
            "--last/--after/--before (a range), not both.",
            file=sys.stderr,
        )
        return 2

    if not args.accession and not args.form and not is_range:
        print(
            "Error: provide --accession, --form, or --last/--after/--before",
            file=sys.stderr,
        )
        return 2

    if is_range and not args.form:
        args.form = "10-K"

    async def _run() -> int:
        from .pack.build import build_pack

        resolved_label = args.company or args.cik or "company"
        resolved_ticker: str | None = None
        if args.company:
            try:
                resolved = await _resolve_cli_company(args.company)
            except (UnknownCompany, AmbiguousCompany):
                resolved = None
            if resolved is not None:
                resolved_label = _preferred_company_arg(resolved, args.company)
                ticker = getattr(resolved, "ticker", None)
                if isinstance(ticker, str) and ticker.strip():
                    resolved_ticker = ticker.strip().upper()

        rc, cik = await _cik_from_company_args(args)
        if rc != 0 or cik is None:
            return rc

        try:
            if is_range:
                from .pack.build import build_pack_range

                results = await build_pack_range(
                    cik=cik,
                    form_type=args.form,
                    last=args.last,
                    after=args.after,
                    before=args.before,
                    out_dir=args.out,
                    with_chunks=bool(args.with_chunks),
                    with_xbrl=bool(args.with_xbrl),
                    force=bool(args.force),
                )
            else:
                result = await build_pack(
                    cik=cik,
                    accession=args.accession,
                    form_type=args.form,
                    out_dir=args.out,
                    with_chunks=bool(args.with_chunks),
                    with_xbrl=bool(args.with_xbrl),
                    force=bool(args.force),
                )
                results = [result]
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        built = 0
        skipped = 0
        for result in results:
            _register_pack_result(result, ticker=resolved_ticker)
            already_built = any("Pack already exists" in w for w in result.warnings)
            if already_built:
                skipped += 1
            else:
                built += 1

        if is_range:
            print(
                f"{built} pack(s) built, {skipped} skipped (already registered)",
                file=sys.stderr,
            )
            for result in results[:5]:
                accn = result.filing_meta.get("accession", "?")
                print(f"  ✓ {accn}  {result.output_dir}")
            if len(results) > 5:
                print(f"  ... and {len(results) - 5} more")
            return 0

        result = results[0]
        print("✓ Pack built")
        print(f"  Output: {result.output_dir}")
        print(f"  Company: {result.filing_meta.get('company_name', 'Unknown')}")
        print(f"  Form: {result.filing_meta.get('form_type', 'Unknown')}")
        print(f"  Filing Date: {result.filing_meta.get('filing_date', 'Unknown')}")
        print(f"  Sections: {result.sections_count}")
        print(f"  Tokens: {result.tokens_total:,}")
        print(f"  Registry: ready for `edgarpack which {resolved_label}`")

        if any("Pack already exists" in w for w in result.warnings):
            print(
                "  Already built. To list other filings: "
                f"`edgarpack list {resolved_label} --form {args.form or '10-K'}`"
            )
            print(
                "  To pull older filings: "
                f"`edgarpack build {resolved_label} --form {args.form or '10-K'} --last 5`"
            )

        if result.warnings:
            grouped = _group_build_warnings(result.warnings)
            print(
                f"\nNon-fatal warnings ({len(grouped)} groups from {len(result.warnings)} events):"
            )
            for w in grouped[:10]:
                print(f"  - {w}")
            if len(grouped) > 10:
                print(f"  ... and {len(grouped) - 10} more groups")

        return 0

    return asyncio.run(_run())


def _cmd_build_sse(args: Any) -> int:
    from datetime import date

    try:
        filing_date = date.fromisoformat(args.filing_date)
    except ValueError:
        print(f"Error: invalid date format: {args.filing_date} (use YYYY-MM-DD)", file=sys.stderr)
        return 2

    async def _run() -> int:
        from .pack.build import build_sse_pack

        try:
            result = await build_sse_pack(
                url=args.url,
                stock_code=args.stock_code,
                company_name=args.company,
                filing_date=filing_date,
                out_dir=args.out,
                pdf_path=args.pdf,
                with_chunks=bool(args.with_chunks),
                force=bool(args.force),
                translate=bool(args.translate),
                translate_model=args.translate_model,
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        print("Pack built")
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


def _cmd_translate_sse(args: Any) -> int:
    pack_dir = Path(args.pack)
    if not pack_dir.exists():
        print(f"Error: pack directory not found: {pack_dir}", file=sys.stderr)
        return 2

    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: no manifest.json in {pack_dir}", file=sys.stderr)
        return 2

    import json

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Check if already translated
    if not args.force and manifest_data.get("translation"):
        print("Pack already translated. Use --force to re-translate.", file=sys.stderr)
        return 0

    async def _run() -> int:
        from .china.translate.cache import DEFAULT_NAMESPACE, TranslationCache
        from .china.translate.deepinfra import DeepInfraTranslator
        from .china.translate.glossary import FinancialGlossary
        from .china.translate.numbers import tag_numbers
        from .china.translate.preprocess import preprocess_paragraphs
        from .china.translate.router import SectionRouter
        from .china.translate.validators import (
            GlossaryConsistencyValidator,
            validate_translation,
        )

        sections_dir = pack_dir / "sections"
        if not sections_dir.exists():
            print(f"Error: no sections/ directory in {pack_dir}", file=sys.stderr)
            return 1

        # Find Chinese section files (exclude .en.md)
        zh_files = sorted(f for f in sections_dir.glob("*.md") if not f.name.endswith(".en.md"))
        if not zh_files:
            print("No Chinese section files found", file=sys.stderr)
            return 1

        # Derive stock_code from pack path (packs/sse/{stock_code}/...)
        stock_code = manifest_data.get("filing", {}).get("stock_code", "")
        packs_dir = pack_dir.parent.parent.parent  # sse/{code}/{filing_id} -> packs

        glossary = FinancialGlossary.with_company_overlay(stock_code, packs_dir)
        translator = DeepInfraTranslator(glossary=glossary, model=args.model)
        router = SectionRouter(translator)
        cache = TranslationCache(namespace=DEFAULT_NAMESPACE)
        glossary_validator = GlossaryConsistencyValidator()

        cached_count = 0
        translated_count = 0
        en_sections: list[str] = []
        failed_sections: list[str] = []
        translated_sections: list[str] = []

        for zh_file in zh_files:
            section_id = zh_file.stem
            content = zh_file.read_text(encoding="utf-8")
            paragraphs = [p for p in content.split("\n\n") if p.strip()]
            decisions = preprocess_paragraphs(paragraphs)

            uncached_indices: list[int] = []
            uncached_texts: list[str] = []
            translation_sources: list[str | None] = [None] * len(decisions)
            para_results: list[str | None] = [None] * len(decisions)

            for i, decision in enumerate(decisions):
                if decision.action == "drop":
                    continue
                if decision.action == "passthrough":
                    para_results[i] = decision.cleaned
                    translation_sources[i] = "passthrough"
                    continue

                cached = cache.get(decision.cleaned)
                if cached is not None:
                    para_results[i] = cached.text_en
                    cached_count += 1
                    translation_sources[i] = "cache"
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(decision.cleaned)

            def _validate(index: int, text_zh: str, text_en: str) -> Any:
                _, number_tags = tag_numbers(text_zh)
                return validate_translation(
                    text_zh=text_zh,
                    text_en=text_en,
                    number_tags=number_tags,
                    glossary_terms=glossary.terms,
                    glossary_validator=glossary_validator,
                    allow_han=False,
                    paragraph_index=index,
                )

            for i, decision in enumerate(decisions):
                if translation_sources[i] != "cache" or para_results[i] is None:
                    continue
                report = _validate(i, decision.cleaned, para_results[i])
                if report.has_errors:
                    uncached_indices.append(i)
                    uncached_texts.append(decision.cleaned)
                    para_results[i] = None
                    translation_sources[i] = None
                    cached_count -= 1

            section_failed = False
            section_error_messages: list[str] = []
            if uncached_texts:
                results = await router.translate_section(section_id, uncached_texts)
                retry_indices: list[int] = []
                retry_texts: list[str] = []
                for idx, result in zip(uncached_indices, results, strict=False):
                    report = _validate(idx, result.text_zh, result.text_en)
                    if report.has_errors:
                        retry_indices.append(idx)
                        retry_texts.append(result.text_zh)
                        continue
                    para_results[idx] = result.text_en
                    translation_sources[idx] = "translated"
                    cache.put(result)
                    translated_count += 1

                if retry_texts:
                    retry_results = await router.translate_section(
                        section_id,
                        retry_texts,
                        strict=True,
                    )
                    for idx, result in zip(retry_indices, retry_results, strict=False):
                        report = _validate(idx, result.text_zh, result.text_en)
                        if report.has_errors:
                            section_failed = True
                            section_error_messages.extend(
                                f"p{idx}: {issue.message}"
                                for issue in report.issues
                                if issue.severity == "error"
                            )
                            break
                        para_results[idx] = result.text_en
                        translation_sources[idx] = "translated"
                        cache.put(result)
                        translated_count += 1

            if section_failed or any(
                translation_sources[i] is None and decisions[i].action == "translate"
                for i in range(len(decisions))
            ):
                failed_sections.append(section_id)
                en_path = sections_dir / f"{section_id}.en.md"
                if en_path.exists():
                    en_path.unlink()
                print(f"  {section_id}: failed closed")
                for msg in section_error_messages[:3]:
                    print(f"    - {msg}")
                continue

            en_content = "\n\n".join(p for p in para_results if p)
            en_sections.append(en_content)
            en_path = sections_dir / f"{section_id}.en.md"
            en_path.write_text(en_content, encoding="utf-8")
            translated_sections.append(section_id)
            print(f"  {section_id}: {len(paragraphs)} paragraphs")

        # Write full English filing
        wrote_full_en = False
        if en_sections and not failed_sections:
            full_en = "\n\n---\n\n".join(en_sections)
            full_en_path = pack_dir / "filing.full.en.md"
            full_en_path.write_text(full_en, encoding="utf-8")
            wrote_full_en = True
        else:
            full_en_path = pack_dir / "filing.full.en.md"
            if full_en_path.exists():
                full_en_path.unlink()

        # Update manifest
        manifest_data["translation"] = {
            "provider": translator.provider,
            "model": args.model,
            "glossary_version": glossary.version,
            "cached_paragraphs": cached_count,
            "translated_paragraphs": translated_count,
            "failed_sections": failed_sections,
            "translated_sections": translated_sections,
            "full_filing_written": wrote_full_en,
        }
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        await translator.close()
        cache.close()
        print(f"\nTranslated: {translated_count} paragraphs, {cached_count} from cache")
        return 1 if failed_sections else 0

    return asyncio.run(_run())


def _cmd_company_llms(args: Any) -> int:
    async def _run() -> int:
        from .pack.build import build_company_llms

        rc, cik = await _cik_from_company_args(args)
        if rc != 0 or cik is None:
            return rc

        try:
            path = await build_company_llms(cik, args.out)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        print(f"✓ Company llms.txt written: {path}")
        return 0

    return asyncio.run(_run())


def _cmd_list(args: Any) -> int:
    async def _run() -> int:
        from .sec.submissions import list_filings

        rc, cik = await _cik_from_company_args(args)
        if rc != 0 or cik is None:
            return rc

        try:
            filings = await list_filings(cik, form_type=args.form, limit=int(args.limit))
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


def _wrap_cli_text(text: str, width: int, indent: str = "      ") -> list[str]:
    """Wrap CLI text while preserving readable hanging indentation."""
    wrapped = textwrap.fill(
        text,
        width=max(40, width),
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped.splitlines()


def _render_citation_lines(
    citation_id: str,
    record: dict[str, object],
    *,
    show_links: str,
    width: int,
) -> list[str]:
    """Render one citation record for table/audit output."""
    from .query.links import compact_url, osc8, supports_osc8

    lines: list[str] = []
    form_type = record.get("form_type")
    fiscal_label = record.get("fiscal_label")
    period = record.get("period")
    accession = record.get("accession")
    filed = record.get("filed")

    primary = record.get("primary_link")
    primary = primary if isinstance(primary, str) else ""
    osc8_on = supports_osc8()

    marker_label = f"[{citation_id}]"
    if show_links != "none" and osc8_on and primary:
        marker_label = osc8(primary, marker_label)

    summary = (
        f"{marker_label} {form_type} {fiscal_label} | period {period} | "
        f"filing {accession} | filed {filed}"
    )
    if show_links != "none" and not osc8_on and primary:
        summary = f"{summary}  {compact_url(primary)}"
    lines.extend(_wrap_cli_text(summary, width, indent="         "))

    if show_links == "all":
        links = record.get("links", {})
        if isinstance(links, dict):
            for link_key, link_value in links.items():
                if not isinstance(link_value, str) or not link_value:
                    continue
                rendered = compact_url(link_value)
                if osc8_on:
                    rendered = osc8(link_value, rendered)
                lines.extend(
                    _wrap_cli_text(f"     {link_key}: {rendered}", width, indent="         ")
                )

    return lines


def _marker_with_link(
    marker: str,
    payload: dict[str, object] | None,
    citations_lookup: dict[str, dict[str, object]],
    calculations_lookup: dict[str, dict[str, object]],
    *,
    show_links: str,
) -> str:
    from .query.links import osc8, supports_osc8

    if show_links == "none" or not marker or not supports_osc8():
        return marker

    tag = marker.strip().lstrip("[").rstrip("]").split(",")[0].strip()
    record: dict[str, object] | None = None
    if tag.startswith(("C",)):
        record = citations_lookup.get(tag)
    elif tag.startswith(("L", "D", "G")):
        calc = calculations_lookup.get(tag)
        if isinstance(calc, dict):
            result_cid = calc.get("result_citation_id")
            if isinstance(result_cid, str):
                record = citations_lookup.get(result_cid)
    if not isinstance(record, dict):
        return marker
    link = record.get("primary_link")
    if not isinstance(link, str) or not link:
        return marker
    return osc8(link, marker)


def _source_badge_for(v: Any) -> str:
    """Render the source indicator that follows a metric's formatted value.

    - 'hardcoded' -> empty (no badge).
    - 'learned:kpi-*' -> ' [discovered]' (all discovered-KPI sources collapse
      to one human label; the specific taxonomy stays on CitedValue.source).
    - other 'learned:*' -> ' [<source> ✓]' (self-heal learned badge).
    - warning contains 'unverified' -> ✓ becomes ⚠.
    """
    src = getattr(v, "source", "hardcoded")
    if src == "hardcoded":
        return ""
    if src.startswith("learned:kpi-"):
        return " [discovered]"
    mark = "✓"
    for w in getattr(v, "warnings", []):
        if "unverified" in w.lower():
            mark = "⚠"
            break
    return f" [{src} {mark}]"


def _render_query_table(result: Any, args: Any) -> str:
    """Render single-company query output with inline citation/audit ergonomics."""
    from .query.comps import _format_value

    lean = result.to_lean_dict()
    metrics_lean = lean.get("metrics", {})
    citations = lean.get("citations", {})
    calculations = lean.get("calculations", {})
    permalink = lean.get("permalink")

    width = shutil.get_terminal_size((120, 20)).columns
    lines: list[str] = [f"{result.company} (CIK: {result.cik})", ""]

    strict = bool(getattr(args, "strict", False))
    # Strict filtering is canonical in query.strict.apply_strict. When
    # invoked from _cmd_query the result has already been filtered and
    # the rejected-name list rides on args. When invoked directly (tests,
    # library use) we filter here so the render path stays self-contained.
    strict_rejected_incoming: list[str] = list(getattr(args, "_strict_rejected_names", ()))
    if strict and not strict_rejected_incoming:
        from .query.strict import apply_strict as _apply_strict_local

        strict_rejected_incoming = _apply_strict_local(result)
    strict_rejected: list[str] = []

    for metric_name, raw_value in result.metrics.items():
        label = metric_name.replace("_", " ").title()
        lean_value = metrics_lean.get(metric_name)

        if raw_value is None:
            if strict and metric_name in strict_rejected_incoming:
                lines.append(f"{label}: N/A [strict]")
                strict_rejected.append(metric_name)
            else:
                lines.append(f"{label}: N/A")
            continue

        if isinstance(raw_value, list):
            lines.append(f"{label}:")
            lean_items = lean_value if isinstance(lean_value, list) else []
            for idx, item in enumerate(raw_value):
                if item.value is None:
                    continue
                payload = lean_items[idx] if idx < len(lean_items) else {}
                marker = ""
                if args.citations != "off":
                    calc_id = payload.get("calculation_id") if isinstance(payload, dict) else None
                    citation_ids = (
                        payload.get("citation_ids") if isinstance(payload, dict) else None
                    )
                    if isinstance(calc_id, str):
                        marker = f" [{calc_id}]"
                    elif isinstance(citation_ids, list) and citation_ids:
                        marker = f" [{','.join(str(cid) for cid in citation_ids)}]"
                    marker = _marker_with_link(
                        marker,
                        payload if isinstance(payload, dict) else None,
                        citations,
                        calculations,
                        show_links=getattr(args, "show_links", "primary"),
                    )

                lines.append(f"  {item.fiscal_label}: {_format_value(item)}{marker}")
                if isinstance(payload, dict):
                    warnings = payload.get("warnings", [])
                    if isinstance(warnings, list):
                        for warning in warnings:
                            lines.extend(
                                _wrap_cli_text(
                                    f"  ! warning: {warning}",
                                    width,
                                    indent="             ",
                                )
                            )
            continue

        payload = lean_value if isinstance(lean_value, dict) else {}
        marker = ""
        calc_id = payload.get("calculation_id")
        citation_ids = payload.get("citation_ids", [])
        if args.citations != "off":
            if isinstance(calc_id, str):
                marker = f" [{calc_id}]"
            elif isinstance(citation_ids, list) and citation_ids:
                marker = f" [{','.join(str(cid) for cid in citation_ids)}]"
            marker = _marker_with_link(
                marker,
                payload if isinstance(payload, dict) else None,
                citations,
                calculations,
                show_links=getattr(args, "show_links", "primary"),
            )

        source_badge = _source_badge_for(raw_value)
        lines.append(f"{label}: {_format_value(raw_value)}{marker}{source_badge}")

        warnings = payload.get("warnings", []) if isinstance(payload, dict) else []
        if isinstance(warnings, list):
            for warning in warnings:
                lines.extend(
                    _wrap_cli_text(
                        f"  ! warning: {warning}",
                        width,
                        indent="             ",
                    )
                )

        if args.citations == "inline":
            if isinstance(calc_id, str):
                calc = calculations.get(calc_id, {})
                formula = calc.get("formula", "")
                kind = calc.get("kind", "")
                if kind == "ltm":
                    components = calc.get("components", [])
                    if isinstance(components, list) and components:
                        comp_map = {
                            str(comp.get("role")): str(comp.get("citation_id"))
                            for comp in components
                            if isinstance(comp, dict)
                        }
                        expr = (
                            f"mrp[{comp_map.get('mrp', '?')}] + "
                            f"lfy[{comp_map.get('lfy', '?')}] - "
                            f"mrp_prior[{comp_map.get('mrp_prior', '?')}]"
                        )
                        lines.extend(
                            _wrap_cli_text(f"  [{calc_id}] LTM = {expr}", width, indent="         ")
                        )
                    else:
                        lines.extend(
                            _wrap_cli_text(
                                f"  [{calc_id}] formula: {formula}",
                                width,
                                indent="         ",
                            )
                        )
                else:
                    lines.extend(
                        _wrap_cli_text(
                            f"  [{calc_id}] formula: {formula}",
                            width,
                            indent="         ",
                        )
                    )

                if args.audit:
                    window = calc.get("window")
                    if isinstance(window, dict):
                        w_start = window.get("start")
                        w_end = window.get("end")
                        lines.extend(
                            _wrap_cli_text(
                                f"     window: {w_start}..{w_end}",
                                width,
                                indent="             ",
                            )
                        )

                    components = calc.get("components", [])
                    if isinstance(components, list):
                        for component in components:
                            if not isinstance(component, dict):
                                continue
                            role = component.get("role")
                            cid = component.get("citation_id")
                            value = component.get("value")
                            unit = component.get("unit")
                            fiscal = component.get("fiscal_label")
                            comp_line = f"     {role}[{cid}] value={value} {unit} | {fiscal}"
                            lines.extend(_wrap_cli_text(comp_line, width, indent="             "))
                            if isinstance(cid, str):
                                record = citations.get(cid)
                                if isinstance(record, dict):
                                    lines.extend(
                                        _render_citation_lines(
                                            cid,
                                            record,
                                            show_links=args.show_links,
                                            width=width,
                                        )
                                    )
            elif isinstance(citation_ids, list):
                for cid in citation_ids:
                    record = citations.get(cid)
                    if isinstance(record, dict):
                        lines.extend(
                            _render_citation_lines(
                                str(cid), record, show_links=args.show_links, width=width
                            )
                        )

    if args.citations == "footer":
        if citations:
            lines.append("")
            lines.append("Sources:")
            for cid in sorted(
                citations.keys(),
                key=lambda x: int(x[1:]) if x[1:].isdigit() else 9999,
            ):
                record = citations.get(cid)
                if isinstance(record, dict):
                    lines.extend(
                        _render_citation_lines(cid, record, show_links=args.show_links, width=width)
                    )
        if calculations:
            lines.append("")
            lines.append("Calculations:")
            for calc_id in sorted(
                calculations.keys(),
                key=lambda x: (x[:1], int(x[1:]) if x[1:].isdigit() else 9999),
            ):
                calc = calculations.get(calc_id)
                if not isinstance(calc, dict):
                    continue
                formula = calc.get("formula", "")
                metric_name = calc.get("metric", "")
                lines.extend(
                    _wrap_cli_text(
                        f"[{calc_id}] {metric_name} = {formula}",
                        width,
                        indent="         ",
                    )
                )

    diagnostics = result.diagnostics
    if diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for diag in diagnostics:
            # Diagnostic is a pydantic model; getattr guards against stub dicts
            # slipping in via monkey-patched tests.
            metric_name = getattr(diag, "metric", "?")
            message = getattr(diag, "message", "")
            lines.extend(
                _wrap_cli_text(
                    f"  {metric_name}: {message}",
                    width,
                    indent="    ",
                )
            )

    if strict_rejected:
        lines.append("")
        lines.append(f"Strict mode: rejected learned values for: {', '.join(strict_rejected)}")
        lines.append("Use `edgarpack learned list` to inspect, or re-run without --strict.")

    if isinstance(permalink, str) and permalink:
        lines.append("")
        lines.extend(_wrap_cli_text(f"Reproduce: {permalink}", width, indent="           "))

    return "\n".join(lines)


def _cmd_query(args: Any) -> int:
    from .identity import load_identity, resolve

    # Universe-local pre-pass: catch private companies and ambiguous aliases
    # before hitting the SEC resolver. Unknown-to-universe inputs fall through
    # to financials(), which uses sec.tickers.resolve_company and now handles
    # ticker / CIK / company-name input transparently.
    resolved = None
    universe_path = Path("universe.toml")
    if universe_path.exists():
        try:
            index = load_identity(universe_path)
        except AmbiguousCompany as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"Error: failed to load universe: {e}", file=sys.stderr)
            return 2

        for kwargs in (
            {"ticker": args.company, "company": None},
            {"ticker": None, "company": args.company},
        ):
            try:
                resolved = resolve(index, **kwargs)
                break
            except UnknownCompany:
                continue
            except AmbiguousCompany as e:
                print(f"Error: {e}", file=sys.stderr)
                return 2

    if resolved is not None and resolved.private:
        print(
            f"Error: {resolved.ticker} is a private company with no public filings. "
            "Query is unsupported for private companies.",
            file=sys.stderr,
        )
        return 2

    async def _run() -> int:
        from .query.financials import financials
        from .query.layer_zero import MetricNotFound
        from .query.periods import parse_period_spec
        from .query.presets import expand_metrics

        try:
            periods = parse_period_spec(args.period)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

        try:
            expanded = expand_metrics(args.metrics, getattr(args, "preset", None))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        metric_input: str | list[str] | None
        metric_list_for_render: list[str] | None = None
        if expanded is None:
            metric_input = None
        else:
            metric_input = expanded
            metric_list_for_render = expanded

        async def _fetch(period: str):
            return await financials(
                company=args.company,
                metrics=metric_input,
                period=period,
                force=bool(args.force),
            )

        try:
            if len(periods) == 1:
                result = await _fetch(periods[0])
            else:
                gathered = await asyncio.gather(*[_fetch(p) for p in periods])
                results_by_period = dict(zip(periods, gathered))
                result = gathered[0]
        except MetricNotFound as e:
            print(f"Error: {e}", file=sys.stderr)
            metric_names = metric_list_for_render or []
            if len(metric_names) == 1:
                missing = metric_names[0]
                if missing == "subscription_customers":
                    print(
                        "Tip: `subscription_customers` maps to the catalog metric "
                        "`customer_count`.",
                        file=sys.stderr,
                    )
                print(
                    f"Company-specific KPI slugs come from `edgarpack which {args.company}`.",
                    file=sys.stderr,
                )
                print(
                    f"Run `edgarpack which {args.company}` first to see available slugs, "
                    "or retry with a catalog metric like `customer_count` if you want "
                    "the generic Layer B path.",
                    file=sys.stderr,
                )
            return 2
        except AmbiguousCompany as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        except ValueError as e:
            msg = str(e)
            print(f"Error: {msg}", file=sys.stderr)
            lower = msg.lower()
            if lower.startswith(("unknown ticker", "unknown company", "ambiguous company")):
                return 2
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        strict_flag = bool(getattr(args, "strict", False))
        strict_rejected: list[str] = []
        if strict_flag:
            from .query.strict import apply_strict

            if len(periods) == 1:
                strict_rejected = apply_strict(result)
            else:
                seen: set[str] = set()
                for _p, _r in results_by_period.items():
                    for name in apply_strict(_r):
                        if name not in seen:
                            seen.add(name)
                            strict_rejected.append(name)

        # Single-period path: keep existing behavior byte-for-byte.
        if len(periods) == 1:
            if args.output_format == "json":
                import json

                payload = result.to_lean_dict()
                if strict_flag:
                    payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
                return 0

            if args.output_format == "json-full":
                import json

                payload = result.to_cited_dict()
                if strict_flag:
                    payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
                return 0

            citations_mode = args.citations if args.citations is not None else "inline"
            args_for_render = _ArgProxy(
                args,
                citations=citations_mode,
                _strict_rejected_names=strict_rejected,
            )
            print(_render_query_table(result, args_for_render))
            return 0

        # Multi-period path: render the metrics x periods grid.
        from .query.comps import (
            format_financial_perf_table,
            multi_period_to_full_json,
            multi_period_to_lean_json,
        )

        if metric_list_for_render is None:
            # Caller requested all metrics; use the first result's keys.
            metric_list_for_render = list(result.metrics.keys())

        if args.output_format == "json":
            print(multi_period_to_lean_json(results_by_period, metric_list_for_render, periods))
            return 0

        if args.output_format == "json-full":
            print(multi_period_to_full_json(results_by_period, metric_list_for_render, periods))
            return 0

        citations_mode = args.citations if args.citations is not None else "footer"
        width = shutil.get_terminal_size((120, 20)).columns
        print(
            format_financial_perf_table(
                results_by_period,
                metric_list_for_render,
                periods,
                citations_mode=citations_mode,
                show_links=args.show_links,
                audit=bool(args.audit),
                terminal_width=width,
            )
        )
        return 0

    return asyncio.run(_run())


class _ArgProxy:
    """Shallow proxy that forwards attribute access but overrides a few fields.

    Used so ``_render_query_table`` sees a resolved ``citations`` value even
    though the argparse default is ``None`` (for multi-period default
    inference). Keeps the existing single-period rendering path untouched.
    """

    def __init__(self, inner: Any, **overrides: Any) -> None:
        self._inner = inner
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._inner, name)


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

        strict_flag = bool(getattr(args, "strict", False))
        strict_rejected: dict[str, list[str]] = {}
        if strict_flag:
            from .query.strict import apply_strict

            for _company, _result in results.items():
                rejected = apply_strict(_result)
                if rejected:
                    strict_rejected[_company] = rejected

        if args.output_format == "json":
            import json

            # comps_to_lean_json returns a JSON string; we want to re-parse
            # only when we need to attach strict_rejected. For the common
            # non-strict path the output stays byte-identical.
            if strict_flag and strict_rejected:
                payload = json.loads(comps_to_lean_json(results, metric_list, args.period))
                payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
            else:
                print(comps_to_lean_json(results, metric_list, args.period))
        elif args.output_format == "json-full":
            import json

            if strict_flag and strict_rejected:
                payload = json.loads(comps_to_json(results))
                payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
            else:
                print(comps_to_json(results))
        else:
            width = shutil.get_terminal_size((120, 20)).columns
            print(
                format_comps_table(
                    results,
                    metric_list,
                    citations_mode=args.citations,
                    show_links=args.show_links,
                    audit=bool(args.audit),
                    terminal_width=width,
                )
            )
            if strict_flag and strict_rejected:
                print("")
                flat = sorted({m for v in strict_rejected.values() for m in v})
                print(f"Strict mode: rejected learned values for: {', '.join(flat)}")
                print("Use `edgarpack learned list` to inspect, or re-run without --strict.")

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
        if plan.errors:
            print(
                f"Errors: {len(plan.errors)} companies/forms skipped during planning",
                file=sys.stderr,
            )
            for err in plan.errors:
                label = f"{err.ticker} {err.form_type}" if err.form_type else err.ticker
                print(f"  SKIP {label}: {err.error}", file=sys.stderr)

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


def _truncate(text: str, max_words: int = 200) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def _print_paragraph_delta(pd: Any) -> None:
    if pd.change_type.value == "added":
        print(f"      [NEW] {_truncate(pd.new_text or '')}")
    elif pd.change_type.value == "removed":
        print(f"      [DEL] {_truncate(pd.old_text or '')}")
    elif pd.change_type.value == "modified":
        print(f"      [CHG sim={pd.similarity:.0%}]")
        print(f"        - {_truncate(pd.old_text or '')}")
        print(f"        + {_truncate(pd.new_text or '')}")


def _cmd_diff(args: Any) -> int:
    async def _run() -> int:
        from .diff.section_diff import diff_filings

        before_dir: Path | None = None
        after_dir: Path | None = None

        if args.before and args.after:
            before_dir = Path(args.before)
            after_dir = Path(args.after)
        elif args.ticker:
            rc, ticker = await _resolve_ticker_arg(args.ticker)
            if rc != 0 or ticker is None:
                return rc

            from .harvest.registry import PackRegistry

            registry = PackRegistry()
            packs = registry.list_packs(ticker=ticker, form_type=args.form)
            registry.close()

            if len(packs) < 2:
                print(
                    f"Error: need at least 2 {args.form} filings for {ticker}, found {len(packs)}",
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
                    for pd in delta.paragraph_deltas:
                        if pd.change_type.value == "unchanged":
                            continue
                        _print_paragraph_delta(pd)

        return 0

    return asyncio.run(_run())


def _cmd_timeline(args: Any) -> int:
    async def _run() -> int:
        from .diff.timeline import build_timeline
        from .harvest.registry import PackRegistry

        rc, ticker = await _resolve_ticker_arg(args.ticker)
        if rc != 0 or ticker is None:
            return rc

        registry = PackRegistry()
        packs = registry.list_packs(ticker=ticker, form_type=args.form)
        registry.close()

        if not packs:
            print(f"No {args.form} filings found for {ticker}", file=sys.stderr)
            return 1

        packs.sort(key=lambda p: p.filing_date)
        pack_dirs = [Path(p.pack_dir) for p in packs if Path(p.pack_dir).exists()]

        entries = build_timeline(pack_dirs, args.section)

        print(f"Timeline: {ticker} / {args.section} / {args.form}\n")
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

    ticker: str | None = None
    if args.ticker:
        rc, ticker = asyncio.run(_resolve_ticker_arg(args.ticker))
        if rc != 0 or ticker is None:
            return rc

    result = search_corpus(
        query=args.query,
        topic=args.topic,
        ticker=ticker,
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

    if args.incremental:
        packs = registry.unindexed_packs()
        if not packs:
            print("All packs already indexed. Nothing to do.", file=sys.stderr)
            registry.close()
            index.close()
            return 0
        print(f"Incremental: {len(packs)} unindexed packs", file=sys.stderr)
    else:
        packs = registry.list_packs()
        if not packs:
            print("No packs in registry. Run harvest first.", file=sys.stderr)
            registry.close()
            index.close()
            return 1

    total_chunks = 0
    indexed_accessions: list[str] = []
    for i, pack in enumerate(packs, 1):
        pack_dir = Path(pack.pack_dir)
        if not pack_dir.exists():
            label = f"{pack.ticker} {pack.form_type} {pack.filing_date}"
            print(f"  [{i}/{len(packs)}] {label} ... SKIP (dir missing)")
            continue
        count = index.index_pack(pack_dir, ticker=pack.ticker)
        total_chunks += count
        indexed_accessions.append(pack.accession)
        label = f"{pack.ticker} {pack.form_type} {pack.filing_date}"
        print(f"  [{i}/{len(packs)}] {label} ... {count} chunks")

    if indexed_accessions:
        registry.mark_indexed_batch(indexed_accessions)

    print(f"\nIndexed {total_chunks} chunks from {len(packs)} packs", file=sys.stderr)

    registry.close()
    index.close()
    return 0


def _cmd_learned(args: Any) -> int:
    """Inspect or manage the self-heal learned_concepts registry."""
    from .query.learned_registry import LearnedRegistry

    reg = LearnedRegistry()
    try:
        sub_cmd = args.learned_cmd
        if sub_cmd == "list":
            rows = reg.list_rows(
                cik=args.cik,
                metric=args.metric,
                source=args.source,
                only_unverified=bool(args.unverified),
            )
            if not rows:
                print("no learned mappings")
                return 0
            print(f"{'CIK':<12} {'METRIC':<24} {'CONCEPT':<40} {'SRC':<8} {'V':<2} HITS LEARNED_AT")
            for r in rows:
                mark = "✓" if r.verified else "⚠"
                print(
                    f"{r.cik:<12} {r.metric:<24} {r.concept:<40} "
                    f"{r.source:<8} {mark:<2} {r.hit_count:<4} {r.learned_at}"
                )
            return 0

        if sub_cmd == "show":
            row = reg.lookup(args.cik, args.metric)
            if row is None:
                print(f"no mapping for ({args.cik}, {args.metric})", file=sys.stderr)
                return 1
            print(f"CIK:          {row.cik}")
            print(f"Metric:       {row.metric}")
            print(f"Concept:      {row.concept}")
            print(f"Taxonomy:     {row.taxonomy}")
            print(f"Source:       {row.source}")
            print(f"Verified:     {row.verified}")
            print(f"Verif method: {row.verif_method or '-'}")
            print(f"Value sample: {row.value_sample}")
            print(f"Learned at:   {row.learned_at}")
            print(f"Hit count:    {row.hit_count}")
            return 0

        if sub_cmd == "verify":
            if reg.lookup(args.cik, args.metric) is None:
                print(f"no mapping for ({args.cik}, {args.metric})", file=sys.stderr)
                return 1
            reg.verify_row(args.cik, args.metric)
            print(f"verified: ({args.cik}, {args.metric})")
            return 0

        if sub_cmd == "clear":
            try:
                removed = reg.clear(
                    cik=args.cik,
                    metric=args.metric,
                    all=bool(args.all),
                )
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 2
            print(f"removed {removed} row(s)")
            return 0

        print(f"Unknown learned subcommand: {sub_cmd}", file=sys.stderr)
        return 2
    finally:
        reg.close()


def _format_kpi_value(value: float | None, unit: str | None, magnitude: str | None) -> str:
    """Render a discovered KPI value for the `which` table view.

    Compact, human-readable: scales by magnitude, trims trailing zeros,
    returns a dash for missing values so the column stays aligned.
    """
    if value is None:
        return "-"
    if unit == "percent":
        return f"{value:g}%"

    base = value
    suffix = ""
    if magnitude == "thousands":
        suffix = "K"
    elif magnitude == "millions":
        suffix = "M"
    elif magnitude == "billions":
        suffix = "B"

    if abs(base) >= 1 and base == int(base):
        rendered = f"{int(base)}"
    else:
        rendered = f"{base:g}"

    prefix = "$" if unit == "USD" else ""
    return f"{prefix}{rendered}{suffix}" if suffix or prefix else rendered


def _render_which_empty_state(
    *,
    display_name: str,
    command_label: str,
    cik: str,
    diagnostics: Any,
) -> str:
    """Return an actionable empty-state message for `edgarpack which`."""
    if diagnostics.total_registered_packs == 0:
        return (
            f"No registered packs found for {display_name} (CIK: {cik}).\n"
            f"Build one first with `edgarpack build {command_label} --form 10-K`."
        )
    if diagnostics.unreadable_manifest_packs >= diagnostics.eligible_packs > 0:
        return (
            f"No KPIs shown for {display_name} because all {diagnostics.eligible_packs} "
            "candidate filing packs were unreadable on disk.\n"
            f"Rebuild a fresh pack with `edgarpack build {command_label} --form 10-K --force`."
        )
    if diagnostics.llm_failed_packs > 0 and diagnostics.discovered_packs == 0:
        return (
            f"No KPIs shown for {display_name} because discovery failed on "
            f"{diagnostics.llm_failed_packs} filing(s).\n"
            "Check that `codex` or `claude` is available, then retry with "
            f"`edgarpack which {command_label} --no-cache`."
        )
    if diagnostics.empty_packs > 0:
        return (
            f"Discovery completed for {display_name}, but none of the scanned filings "
            "contained qualifying qualitative KPIs.\n"
            f"Try `edgarpack which {command_label} --no-cache` after building a more relevant "
            "10-K or 10-Q if you expect KPIs to be present."
        )
    return (
        f"No disclosed KPIs found for {display_name} (CIK: {cik}).\n"
        f"Try `edgarpack which {command_label} --no-cache` after building a 10-K or 10-Q."
    )


def _render_which_diagnostics(diagnostics: Any) -> str | None:
    """Render one concise stderr summary for non-fatal discovery issues."""
    fragments: list[str] = []
    if diagnostics.cached_packs:
        fragments.append(f"{diagnostics.cached_packs} cached")
    if diagnostics.discovered_packs:
        fragments.append(f"{diagnostics.discovered_packs} analyzed")
    if diagnostics.manifest_missing_packs:
        fragments.append(
            f"{diagnostics.manifest_missing_packs} skipped "
            "(manifest missing; run `edgarpack build <ticker>`)"
        )
    if diagnostics.manifest_invalid_json_packs:
        fragments.append(
            f"{diagnostics.manifest_invalid_json_packs} skipped "
            "(manifest invalid JSON; run `edgarpack doctor <pack-dir>` for details)"
        )
    if diagnostics.manifest_schema_mismatch_packs:
        fragments.append(
            f"{diagnostics.manifest_schema_mismatch_packs} skipped "
            "(manifest schema mismatch; rebuild with `edgarpack build <ticker> --force`)"
        )
    if diagnostics.manifest_io_error_packs:
        fragments.append(
            f"{diagnostics.manifest_io_error_packs} skipped "
            "(manifest I/O error; check filesystem permissions)"
        )
    if diagnostics.llm_failed_packs:
        fragments.append(f"{diagnostics.llm_failed_packs} discovery failure(s)")
    if diagnostics.empty_packs:
        fragments.append(f"{diagnostics.empty_packs} with no qualifying KPIs")
    if not fragments:
        return None
    return "Discovery summary: " + ", ".join(fragments)


def _render_which_table(aggregates: list, max_periods: int) -> str:
    """Render a compact table view of discovered + catalog KPIs.

    Layout:
      slug         source    unit       latest   P1   P2   P3 ...
      paid_seats   discovered count      1.2M    900K 950K ...

    Period columns are the newest-first union across all aggregates. Gaps
    render as '-' so the drop-off pattern is visually obvious (e.g. a
    metric that was disclosed in FY2023 but dropped in FY2024).
    """
    if not aggregates:
        return ""

    all_labels: list[str] = []
    seen: set[str] = set()
    for agg in aggregates:
        for point in agg.periods:
            if point.label not in seen:
                seen.add(point.label)
                all_labels.append(point.label)

    all_labels.sort(
        key=lambda lbl: next(
            (p.sort_key for agg in aggregates for p in agg.periods if p.label == lbl),
            "",
        ),
        reverse=True,
    )
    labels = all_labels[:max_periods]

    slug_w = max(5, min(30, max(len(a.slug) for a in aggregates)))
    name_w = max(12, min(30, max(len(a.display_name or "") for a in aggregates)))
    src_w = max(len("source"), max(len(a.source) for a in aggregates))
    unit_w = max(5, max(len(a.unit or "-") for a in aggregates))

    header = (
        f"{'slug':<{slug_w}}  {'display':<{name_w}}  {'src':<{src_w}}  "
        f"{'unit':<{unit_w}}  {'latest':>10}"
    )
    for lbl in labels:
        header += f"  {lbl:>8}"

    separator = f"{'─' * slug_w}  {'─' * name_w}  {'─' * src_w}  {'─' * unit_w}  {'─' * 10}"
    for _ in labels:
        separator += f"  {'─' * 8}"

    lines: list[str] = [header, separator]

    alias_lines: list[str] = []
    for agg in aggregates:
        latest = agg.latest
        latest_str = (
            _format_kpi_value(latest.value, latest.unit or agg.unit, latest.magnitude)
            if latest
            else "-"
        )

        by_label = {p.label: p for p in agg.periods}
        row = (
            f"{agg.slug[:slug_w]:<{slug_w}}  "
            f"{(agg.display_name or '')[:name_w]:<{name_w}}  "
            f"{agg.source:<{src_w}}  "
            f"{(agg.unit or '-'):<{unit_w}}  "
            f"{latest_str:>10}"
        )
        for lbl in labels:
            p = by_label.get(lbl)
            cell = (
                _format_kpi_value(p.value, p.unit or agg.unit, p.magnitude)
                if p is not None
                else "-"
            )
            row += f"  {cell:>8}"
        lines.append(row)

        if agg.aliases:
            alias_lines.append(
                f"  (aliases) {agg.slug}: " + ", ".join(f"'{a}'" for a in agg.aliases)
            )

    if alias_lines:
        lines.append("")
        lines.extend(alias_lines)

    return "\n".join(lines)


def _cmd_which(args: Any) -> int:
    """List the qualitative / MD&A KPIs a company discloses across filings."""
    import json as _json

    from .harvest.registry import PackRegistry
    from .query.kpi_discover import DiscoveryDiagnostics, DiscoveryProgressEvent, discover_kpis

    async def _resolve() -> tuple[int, Any | None]:
        try:
            resolved = await _resolve_cli_company(args.company)
            return 0, resolved
        except (UnknownCompany, AmbiguousCompany, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2, None
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1, None

    rc, resolved = asyncio.run(_resolve())
    if rc != 0 or resolved is None:
        return rc
    cik = getattr(resolved, "cik", None)
    if not isinstance(cik, str) or not cik.strip():
        print(
            f"Error: {args.company} does not resolve to a public SEC filer with a CIK.",
            file=sys.stderr,
        )
        return 2
    company_label = _preferred_company_arg(resolved, args.company)
    display_name = _canonical_company_label(resolved, args.company)

    print(
        f"Resolving company {args.company} -> {display_name} (CIK {cik})",
        file=sys.stderr,
    )

    registry = PackRegistry()
    try:
        packs = registry.list_packs(cik=cik, limit=200)
        if not packs:
            print(
                f"No registered packs found for {display_name} (CIK: {cik}). Run "
                f"`edgarpack build {company_label} --form 10-K` first.",
                file=sys.stderr,
            )
            return 1

        diagnostics = DiscoveryDiagnostics()

        def _progress(event: DiscoveryProgressEvent) -> None:
            if event.phase == "pack" and event.pack is not None:
                pack = event.pack
                filing_date = pack.filing_date or "unknown"
                print(
                    f"Running KPI discovery on filing {event.index}/{event.total} "
                    f"({pack.form_type} {filing_date})",
                    file=sys.stderr,
                )

        print(f"Loading up to {len(packs)} registered pack(s)", file=sys.stderr)
        try:
            aggregates = discover_kpis(
                cik=cik,
                pack_registry=registry,
                force=bool(args.no_cache),
                include_catalog=(args.only != "discovered"),
                diagnostics=diagnostics,
                progress_callback=_progress,
            )
        except Exception as e:
            print(f"Error running discovery: {e}", file=sys.stderr)
            return 1
    finally:
        registry.close()

    if args.only == "discovered":
        aggregates = [a for a in aggregates if a.source == "discovered"]
    elif args.only == "catalog":
        aggregates = [a for a in aggregates if a.source == "catalog"]

    summary = _render_which_diagnostics(diagnostics)
    if summary:
        print(summary, file=sys.stderr)

    if args.which_format == "json":
        payload = {
            "cik": cik,
            "company": packs[0].company_name,
            "ticker": packs[0].ticker,
            "count": len(aggregates),
            "kpis": [a.to_json() for a in aggregates],
        }
        print(_json.dumps(payload, indent=2, default=str))
        return 0

    print(f"Disclosed KPIs for {packs[0].company_name} (CIK: {cik}):\n")
    if aggregates:
        print("Rendering KPI table", file=sys.stderr)
        print(_render_which_table(aggregates, int(args.max_periods)))
    else:
        print(
            _render_which_empty_state(
                display_name=display_name,
                command_label=company_label,
                cik=cik,
                diagnostics=diagnostics,
            )
        )
    return 0


if __name__ == "__main__":
    app()
