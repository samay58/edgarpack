"""CLI entry point for EdgarPack. Uses argparse directly (no third-party CLI
framework) so the project runs in constrained environments without extra deps.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from . import __version__
from .config import DEFAULT_PACKS_DIR, DEFAULT_REPORTS_DIR, DEFAULT_SITE_DIR
from .errors import AmbiguousCompany, UnknownCompany

# The single-period query renderers live in query/render.py. They are re-exported
# lazily (via __getattr__) so `from edgarpack.cli import _render_query_table` keeps
# working for tests WITHOUT importing the heavy query package at CLI startup.
# mypy sees only the TYPE_CHECKING imports, never __getattr__, so it still
# resolves these names statically instead of typing every attribute as Any.
_LAZY_QUERY_RENDER_EXPORTS = frozenset(
    {"_render_query_table", "_render_citation_lines", "_source_badge_for"}
)

if TYPE_CHECKING:
    from .query.render import (  # noqa: F401
        _render_citation_lines,
        _render_query_table,
        _source_badge_for,
    )
else:

    def __getattr__(name: str) -> Any:
        if name in _LAZY_QUERY_RENDER_EXPORTS:
            from .query import render

            return getattr(render, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_EDGARPACK_HOME = r"""
              .------------------------------------------.
             /  SOURCE FILINGS                         /|
            /  SEC 10-K   HKEX PDF   CNINFO ANNUAL    / |
           /------------------------------------------/  |
          /__/__/__/__/__/__/__/__/__/__/__/__/__/__/   |
          |   .------------------------------------. |   |
          |   |  ITEM 1A / MD&A              [S4] | |   |
          |   |  -------------------------------  | |   |
          |   |  exact text from the filing       | |   |
          |   |        [C1] o-------.             | |   |
          |   '----------------------\------------' |  /
          |    .---------------------\----------.   | /
          |   /  PACK: notes.md       \         /|  |/
          |  /   evidence.ndjson       '-> [C1]/ |  /
          | /    tables/  sources.yml    p.12  /  | /
          |/-----------------------------------/   |/
          |             [  E D G A R P A C K  ]   |
          '----------------------------------------'

EdgarPack
Primary filings. Clean packs. Cited answers.
"""


_EDGARPACK_STARTER_COMMANDS = """\
Begin with primary evidence:
  edgarpack query NVDA revenue --period ltm
  edgarpack build AAPL --form 10-K --with-chunks
  edgarpack build-sse 688696 --latest-annual --with-chunks
"""


def _format_home() -> str:
    return f"{_EDGARPACK_HOME}\n{_EDGARPACK_STARTER_COMMANDS}"


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
    from .identity import ResolvedCompany, load_identity, looks_like_china_a_share_code, resolve
    from .sec.tickers import resolve_company as resolve_sec_company
    from .sec.tickers import resolve_company_by_name

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
            if res.cik or res.private or res.source in {"HKEX", "SSE"}:
                return res

    if looks_like_china_a_share_code(query):
        raise UnknownCompany(
            f"Unknown ticker {query!r} looks like a China A-share code. "
            "Add it to universe.toml and build an SSE pack before querying."
        )

    # Try the public ticker/name map first. Falls back to EDGAR issuer-name
    # search for pre-IPO filers (no ticker yet, not in company_tickers.json).
    # If the fallback also fails or the network is unreachable, surface the
    # original public-map UnknownCompany rather than crashing.
    try:
        cik, ticker, title = await resolve_sec_company(query)
    except UnknownCompany as public_err:
        try:
            pre_ipo_cik, pre_ipo_title = await resolve_company_by_name(query)
        except (UnknownCompany, AmbiguousCompany):
            raise
        except Exception:
            raise public_err from None
        return ResolvedCompany(
            ticker=query.strip().upper(),
            listing=None,
            source="SEC",
            cik=pre_ipo_cik,
            hk_stock_code=None,
            stock_code=None,
            aliases=(pre_ipo_title,) if pre_ipo_title else (),
            private=False,
        )

    return ResolvedCompany(
        ticker=ticker or query.strip().upper(),
        listing=None,
        source="SEC",
        cik=cik,
        hk_stock_code=None,
        stock_code=None,
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
    accession = cast(str, accession)
    cik = cast(str, cik)
    form_type = cast(str, form_type)
    filing_date = cast(str, filing_date)
    company_name = cast(str, company_name)

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


def _local_pack_records(
    *,
    cik: str,
    ticker: str | None = None,
    form_type: str | None = None,
    packs_root: Path = DEFAULT_PACKS_DIR,
    limit: int = 200,
) -> list[Any]:
    """Best-effort discovery for packs present on disk but absent from registry."""
    from .harvest.registry import PackRecord

    cik_norm = cik.strip().zfill(10)
    cik_dir = packs_root / cik_norm
    if not cik_dir.is_dir():
        return []

    records: list[PackRecord] = []
    for manifest_path in cik_dir.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        filing = manifest.get("filing") if isinstance(manifest, dict) else None
        if not isinstance(filing, dict):
            continue
        found_form = str(filing.get("form_type") or filing.get("form") or "").strip()
        if form_type and found_form.upper() != form_type.upper():
            continue
        accession = str(filing.get("accession") or manifest_path.parent.name)
        company_name = str(
            filing.get("company_name") or filing.get("company") or ticker or cik_norm
        )
        filing_date = str(filing.get("filing_date") or filing.get("filed") or "")
        sections = manifest.get("sections") if isinstance(manifest.get("sections"), list) else []
        stats = manifest.get("stats") if isinstance(manifest.get("stats"), dict) else {}
        sections_count = int(stats.get("sections_count") or len(sections) or 0)
        tokens_total = int(stats.get("tokens_total") or manifest.get("tokens_total") or 0)
        built_at = str(manifest.get("built_at") or filing_date or "")
        records.append(
            PackRecord(
                accession=accession,
                cik=str(filing.get("cik") or cik_norm).zfill(10),
                ticker=ticker,
                company_name=company_name,
                form_type=found_form,
                filing_date=filing_date,
                sections_count=sections_count,
                tokens_total=tokens_total,
                pack_dir=str(manifest_path.parent),
                built_at=built_at,
                manifest_hash=manifest.get("manifest_hash"),
            )
        )

    records.sort(key=lambda rec: (rec.filing_date, rec.accession), reverse=True)
    return records[:limit]


def _local_pack_hint(records: list[Any], *, command_label: str, form_type: str = "10-K") -> str:
    if not records:
        return (
            f"Run `edgarpack build {command_label} --form {form_type}` for a periodic "
            f"filing, or `edgarpack build {command_label} --form S-1 --with-chunks` "
            "or `--form F-1` for a registration filing."
        )
    first_path = records[0].pack_dir
    count = len(records)
    noun = "directory" if count == 1 else "directories"
    return (
        f"Found {count} pack {noun} on disk but none in the registry. "
        f"Inspect one with `edgarpack doctor {first_path}` or rebuild/register with "
        f"`edgarpack build {command_label} --form {form_type}`. For a registration "
        f"filing, use `edgarpack build {command_label} --form S-1 --with-chunks` "
        "or `--form F-1`."
    )


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
        description="Primary filings turned into clean packs and cited answers.",
        epilog="Run `edgarpack home` for the visual welcome and starter commands.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"EdgarPack {__version__}",
    )

    sub = parser.add_subparsers(dest="cmd", required=True, metavar="command")

    sub.add_parser(
        "home",
        help="Show the EdgarPack welcome and starter commands",
        description=_format_home(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p_build = sub.add_parser(
        "build",
        help="Build a single filing pack, or a range via --last/--after/--before",
        description=(
            "Build and register a filing pack. "
            "Examples: `edgarpack build AAPL --form 10-K` (latest), "
            "`edgarpack build AAPL --form 10-K --last 5` (five most recent), "
            "`edgarpack build Fervo Energy --form S-1 --with-chunks`, "
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
            "Form type: 10-K, 10-Q, 8-K, S-1, S-1/A, F-1, F-1/A. "
            "Defaults to 10-K when combined with --last/--after/--before; "
            "fetches latest when used alone."
        ),
    )
    p_build.add_argument(
        "--out",
        "-o",
        type=Path,
        default=DEFAULT_PACKS_DIR,
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

    p_distill = sub.add_parser(
        "distill",
        help="Compress an existing filing pack into cited human and machine-readable files",
    )
    distill_sub = p_distill.add_subparsers(dest="distill_cmd", required=True)
    p_distill_run = distill_sub.add_parser(
        "run",
        help="Distill one existing pack into reports/<slug>/",
    )
    p_distill_run.add_argument("slug", help="Output slug under --out")
    p_distill_run.add_argument(
        "--pack",
        type=Path,
        help="Existing pack directory to distill",
    )
    p_distill_run.add_argument(
        "--company",
        help="Company name for build-command hints and output metadata",
    )
    p_distill_run.add_argument(
        "--accession",
        help="Accession to resolve under --packs when --pack is omitted",
    )
    p_distill_run.add_argument(
        "--packs",
        type=Path,
        default=DEFAULT_PACKS_DIR,
        help="Pack root used with --accession (default: ./packs)",
    )
    p_distill_run.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Reports output root (default: ./reports)",
    )
    p_distill_run.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing distill output directory",
    )
    p_distill_check = distill_sub.add_parser(
        "check",
        help="Validate a distilled filing bundle",
    )
    p_distill_check.add_argument("bundle", type=Path, help="Distill output directory")

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
        default=DEFAULT_PACKS_DIR,
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
        default=DEFAULT_PACKS_DIR,
        help="Directory containing packs",
    )
    p_site.add_argument(
        "--out",
        "-o",
        type=Path,
        default=DEFAULT_SITE_DIR,
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

    p_identify = sub.add_parser(
        "identify",
        help="Identify whether a company is SEC, HKEX, SSE/A-share, private, or unknown",
    )
    p_identify.add_argument("company", help="Company name, ticker, stock code, or alias")

    p_query = sub.add_parser(
        "query",
        help="Query cited financial metrics for a company",
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
            "Period selector(s). Scalars: lfy, mrq, ltm, lfy-N, ltm-N, mrq-N, mrp, pro-forma. "
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
        "--packs",
        type=Path,
        default=DEFAULT_PACKS_DIR,
        help=(
            "Pack root for registration snapshot fallback and local fact stores (default: ./packs)"
        ),
    )
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
        help=(
            "Currency output: native reporting currency, USD-normalized with native "
            "provenance, or both (default)."
        ),
    )

    def _add_registration_shortcut(name: str, form_type: str, help_text: str) -> None:
        p_reg = sub.add_parser(
            name,
            help=help_text,
            description=(
                f"Build the latest {form_type} pack if needed, then query cited "
                "registration financials. Example: "
                f"`edgarpack {name} 0002004711 revenue,net_income`."
            ),
        )
        p_reg.add_argument("company", help="CIK, ticker, or company name")
        p_reg.add_argument(
            "metrics",
            nargs="?",
            default=None,
            help="Comma-separated metric names. Omit for the default registration set.",
        )
        p_reg.add_argument(
            "--accession",
            "-a",
            help="Pin an exact accession instead of the latest matching filing.",
        )
        p_reg.add_argument(
            "--period",
            "-p",
            default="lfy",
            help="Period selector. Default: lfy.",
        )
        p_reg.add_argument(
            "--format",
            dest="output_format",
            choices=["table", "json", "json-full"],
            default="table",
            help="Output format. Default: table.",
        )
        p_reg.add_argument(
            "--packs",
            type=Path,
            default=DEFAULT_PACKS_DIR,
            help="Pack root for advanced or isolated testing.",
        )
        p_reg.add_argument("--force", action="store_true", help="Rebuild the pack first.")
        p_reg.add_argument("--audit", action="store_true", help="Show audit blocks.")
        p_reg.add_argument(
            "--show-links",
            choices=["primary", "all", "none"],
            default="primary",
            help="Link verbosity in table output.",
        )
        p_reg.add_argument(
            "--citations",
            choices=["inline", "footer", "off"],
            default=None,
            help="Citation placement in table output.",
        )
        p_reg.add_argument(
            "--currency",
            choices=["native", "usd", "both"],
            default="both",
            help="Currency output. Default: both.",
        )
        p_reg.add_argument(
            "--preset",
            choices=["perf"],
            help="Expand to a curated metric list. Combines with --metrics.",
        )
        p_reg.add_argument(
            "--strict",
            action="store_true",
            help="Reject values resolved via the self-heal path.",
        )
        p_reg.set_defaults(registration_form=form_type)

    _add_registration_shortcut("f1", "F-1", "Build/query an F-1 registration filing")
    _add_registration_shortcut("s1", "S-1", "Build/query an S-1 registration filing")

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
        default=DEFAULT_PACKS_DIR,
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
    p_harvest.add_argument(
        "--describe-images",
        action="store_true",
        help=(
            "Generate VLM descriptions for images in registration-class filings. "
            "Requires the optional `anthropic` extra (pip install edgarpack[vlm]). "
            "Descriptions are hash-cached per image in <pack>/assets/.descriptions.json "
            "so re-harvests do not re-bill."
        ),
    )

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
        choices=["summary", "full", "json", "html"],
        default="summary",
        help="Output format (default: summary)",
    )
    p_diff.add_argument(
        "--out",
        "-o",
        type=Path,
        help="Output path for --format html",
    )

    p_timeline = sub.add_parser(
        "timeline",
        help="Show how a section evolved across filings",
    )
    p_timeline.add_argument("--ticker", "-t", help="Company ticker (required for --series=annual)")
    p_timeline.add_argument(
        "--section",
        "-s",
        help="Section ID (e.g. 10k_parti_item1a_risk_factors, required for --series=annual)",
    )
    p_timeline.add_argument("--form", "-f", default="10-K", help="Form type (default: 10-K)")
    p_timeline.add_argument(
        "--cik",
        help="CIK for the company (required for --series=registration)",
    )
    p_timeline.add_argument(
        "--packs",
        type=Path,
        default=DEFAULT_PACKS_DIR,
        help="Packs directory (default: ./packs)",
    )
    p_timeline.add_argument(
        "--series",
        choices=["annual", "registration"],
        default="annual",
        help=(
            "Which filing series to build the timeline over. "
            "'annual' (default) is the existing 10-K / 10-Q run. "
            "'registration' is the S-1 / F-1 / amendment / 424B / FWP redline chain."
        ),
    )
    p_timeline.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "html"],
        default="text",
        help="Output format (default: text)",
    )
    p_timeline.add_argument(
        "--out",
        "-o",
        type=Path,
        help="Output directory for --format html",
    )

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
        default=DEFAULT_PACKS_DIR,
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
        help=(
            "Period selector(s). Scalars: lfy, mrq, ltm, lfy-N, ltm-N, mrq-N, mrp. "
            "Series: annual:N. CSV list for a multi-period grid: lfy,lfy-1,lfy-2. "
            "Default: lfy."
        ),
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
        default=None,
        help=(
            "Citation placement in table output. Default: 'inline' for single-period, "
            "'footer' for multi-period grids."
        ),
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
    p_which.add_argument(
        "--currency",
        choices=["native", "usd", "both"],
        default="both",
        help=(
            "Currency output: native reporting currency, USD-normalized with native "
            "provenance, or both (default)."
        ),
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
        help="Currency output mode: native, USD-normalized with native provenance, or both",
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
        help="Build a pack from an SSE / China A-share primary filing PDF",
    )
    p_build_sse.add_argument(
        "target",
        nargs="?",
        help="Company name, alias, or stock code for --latest-annual lookup",
    )
    p_build_sse.add_argument(
        "--latest-annual",
        action="store_true",
        help="Find the latest CNINFO annual report for the A-share before building",
    )
    p_build_sse.add_argument("--url", help="URL of the PDF on the SSE/CNINFO disclosure platform")
    p_build_sse.add_argument("--stock-code", help="SSE stock code (e.g. 688696)")
    p_build_sse.add_argument("--company", help="Company name")
    p_build_sse.add_argument("--filing-date", help="Filing date (YYYY-MM-DD)")
    p_build_sse.add_argument(
        "--out", "-o", type=Path, default=DEFAULT_PACKS_DIR, help="Output directory"
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
    p_build_sse.add_argument(
        "--translate-concurrency",
        type=int,
        default=5,
        help="Max concurrent DeepInfra translation requests when --translate is used (default: 5)",
    )
    p_build_sse.add_argument(
        "--translate-batch-size",
        type=int,
        default=25,
        help="Translation units to validate/cache per progress batch (default: 25)",
    )
    p_build_sse.add_argument(
        "--form-type",
        choices=["auto", "annual-report", "ipo-prospectus"],
        default="auto",
        help="SSE document type override (default: auto)",
    )
    p_build_sse.add_argument("--force", action="store_true", help="Rebuild even if exists")

    p_build_hk = sub.add_parser(
        "build-hk",
        help="Build a pack from a HKEX-listed issuer's latest English annual report",
        description=(
            "Resolve a HKEX issuer (company name/ticker via universe, or a bare stock "
            "code like 0700), acquire its latest English annual report, section it via "
            "the report's own table of contents, extract facts, and write the pack. "
            "The acquire step always selects the latest annual report; pinning a "
            "specific filing is out of scope for this command."
        ),
    )
    p_build_hk.add_argument(
        "company",
        help="Company name/ticker (resolved via universe) or a bare HKEX stock code (e.g. 0700)",
    )
    p_build_hk.add_argument(
        "--out",
        "-o",
        type=Path,
        default=DEFAULT_PACKS_DIR,
        help="Output directory",
    )

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
    p_translate.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent DeepInfra translation requests (default: 5; lower if rate limited)",
    )
    p_translate.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Translation units to validate/cache per progress batch (default: 25)",
    )
    p_translate.add_argument("--force", action="store_true", help="Re-translate even if exists")
    p_translate.add_argument(
        "--budget-tokens",
        type=int,
        default=0,
        help="Stop after this many DeepInfra tokens (prompt+completion) are spent; "
        "0 (default) means unlimited. Sections not yet reached are left pending "
        "for the same command to resume.",
    )

    raw_argv = sys.argv[1:] if argv is None else argv
    if not raw_argv:
        print(_format_home())
        return 0

    args = parser.parse_args(raw_argv)

    if args.cmd == "compare":
        from .compare import cmd_compare

        return cmd_compare(args)

    if args.cmd == "home":
        print(_format_home())
        return 0
    if args.cmd == "identify":
        return _cmd_identify(args)
    if args.cmd == "build-sse":
        return _cmd_build_sse(args)
    if args.cmd == "build-hk":
        return _cmd_build_hk(args)
    if args.cmd == "translate-sse":
        return _cmd_translate_sse(args)
    if args.cmd == "build":
        return _cmd_build(args)
    if args.cmd == "doctor":
        return _cmd_doctor(args)
    if args.cmd == "distill":
        return _cmd_distill(args)
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
    if args.cmd in {"f1", "s1"}:
        return _cmd_registration_shortcut(args)
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
        return 0, str(cik)

    if not isinstance(company, str):
        print("Error: company must be a string.", file=sys.stderr)
        return 2, None
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
    results: list[Any] = []

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
            return resolved.cik if isinstance(resolved.cik, str) else None

        cik = asyncio.run(_resolve())
        if cik is None:
            return 2
        records = registry.list_packs(cik=cik)
        if not records:
            records = _local_pack_records(cik=cik, ticker=target)
            if records:
                print(_local_pack_hint(records, command_label=target))
            else:
                print(
                    f"No packs registered for {target} (CIK: {cik}). "
                    f"Run `edgarpack build {target}`."
                )
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


def _cmd_distill(args: Any) -> int:
    from .distill import (
        DistillError,
        build_distill_bundle,
        check_distill_bundle,
        resolve_pack_path,
        write_distill_bundle,
    )

    if args.distill_cmd == "check":
        result = check_distill_bundle(args.bundle)
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if not result.ok:
            for error in result.errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"distill check ok: {result.path}")
        return 0

    try:
        pack_dir = resolve_pack_path(
            pack=args.pack,
            accession=args.accession,
            packs_root=args.packs,
        )
        bundle = build_distill_bundle(
            slug=args.slug,
            pack_dir=pack_dir,
            output_root=args.out,
            company_hint=args.company,
        )
        output_dir = write_distill_bundle(bundle, force=args.force)
    except DistillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.accession and args.company:
            print(
                "hint: build the pack first with "
                f'`edgarpack build "{args.company}" --accession {args.accession} --with-chunks`',
                file=sys.stderr,
            )
        return 2
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote distilled filing bundle to {output_dir}")
    print(f"Run `edgarpack distill check {output_dir}` to validate it.")
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
            from .sec.client import SECRateLimitError

            if isinstance(e, SECRateLimitError):
                print(f"Error: {e}", file=sys.stderr)
                print(
                    "SEC rate limit cooldown: wait 10 minutes before retrying. "
                    "Already fetched filings are cached; retrying immediately can extend "
                    "the timeout.",
                    file=sys.stderr,
                )
                return 1
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


def _registration_shortcut_pack_exists(
    *,
    cik: str,
    pack_root: Path,
    form_type: str,
    accession: str | None,
) -> bool:
    from .query.s1_financials import has_registration_pack_for_cik

    return has_registration_pack_for_cik(
        cik,
        pack_root,
        form_type=form_type,
        accession=accession,
    )


async def _registration_shortcut_ticker(args: Any) -> str | None:
    company = getattr(args, "company", None)
    if not isinstance(company, str) or not company.strip():
        return None
    try:
        resolved = await _resolve_cli_company(company)
    except (UnknownCompany, AmbiguousCompany):
        return None
    ticker = getattr(resolved, "ticker", None)
    return ticker.strip().upper() if isinstance(ticker, str) and ticker.strip() else None


def _cmd_registration_shortcut(args: Any) -> int:
    """Build a registration pack when needed, then reuse the normal query command."""
    form_type = str(getattr(args, "registration_form", "") or "").upper()
    if form_type not in {"F-1", "S-1"}:
        print(f"Error: unsupported registration shortcut form {form_type!r}", file=sys.stderr)
        return 2

    async def _ensure_pack() -> int:
        from .pack.build import build_pack
        from .sec.client import SECRateLimitError

        resolved_ticker = await _registration_shortcut_ticker(args)
        rc, cik = await _cik_from_company_args(args)
        if rc != 0 or cik is None:
            return rc

        pack_root = Path(getattr(args, "packs", DEFAULT_PACKS_DIR))
        accession = getattr(args, "accession", None)
        force = bool(getattr(args, "force", False))
        if not force and _registration_shortcut_pack_exists(
            cik=cik,
            pack_root=pack_root,
            form_type=form_type,
            accession=accession,
        ):
            return 0

        target = accession or f"latest {form_type}"
        print(f"Building {target} pack for {args.company}...", file=sys.stderr)
        try:
            result = await build_pack(
                cik=cik,
                accession=accession,
                form_type=form_type,
                out_dir=pack_root,
                with_chunks=True,
                with_xbrl=False,
                force=force,
            )
        except SECRateLimitError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print("SEC rate limit cooldown: wait 10 minutes before retrying.", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        _register_pack_result(result, ticker=resolved_ticker)
        built_accession = result.filing_meta.get("accession", "?")
        built_form = result.filing_meta.get("form_type", form_type)
        print(f"Ready: {built_form} {built_accession}", file=sys.stderr)
        return 0

    rc = asyncio.run(_ensure_pack())
    if rc != 0:
        return rc
    return _cmd_query(args)


def _cmd_identify(args: Any) -> int:
    async def _run() -> int:
        from .identity import looks_like_china_a_share_code

        try:
            resolved = await _resolve_cli_company(args.company)
        except UnknownCompany as e:
            if looks_like_china_a_share_code(args.company):
                try:
                    selected = _find_latest_sse_annual_report(args.company)
                except Exception:
                    print(f"{args.company}")
                    print("Status: unknown China A-share code")
                    print("No SEC fallback attempted.")
                    print(
                        "Next: add the company to universe.toml, then run "
                        "build-sse --latest-annual."
                    )
                    return 0
                print(selected.company_name or args.company)
                print("Status: public A-share / SSE")
                print(f"Stock Code: {args.company.strip()}")
                print(f"Next: edgarpack build-sse {args.company} --latest-annual --with-chunks")
                return 0
            print(args.company)
            print("Status: unknown")
            print(str(e))
            print("No SEC/HKEX/SSE/private workflow could be verified from local indexes.")
            return 0
        except AmbiguousCompany as e:
            print(args.company)
            print("Status: ambiguous")
            print(str(e))
            return 0

        display_name = _canonical_company_label(resolved, args.company)
        source = str(getattr(resolved, "source", "") or "")
        if getattr(resolved, "private", False):
            print(display_name)
            print("Status: private company")
            print("No public filing workflow is available.")
            return 0

        if source == "SSE":
            stock_code = getattr(resolved, "stock_code", None) or getattr(resolved, "ticker", "")
            print(display_name)
            print("Status: public A-share / SSE")
            print(f"Stock Code: {stock_code}")
            print(f"Next: edgarpack build-sse {args.company} --latest-annual --with-chunks")
            return 0

        if source == "HKEX":
            stock_code = getattr(resolved, "hk_stock_code", None) or getattr(resolved, "ticker", "")
            print(display_name)
            print("Status: public HKEX listing")
            print(f"Stock Code: {stock_code}")
            print("Next: build or import the HKEX pack, then run edgarpack which/query.")
            return 0

        print(display_name)
        print("Status: public SEC filer")
        print(f"Ticker: {getattr(resolved, 'ticker', args.company)}")
        print(f"CIK: {getattr(resolved, 'cik', '')}")
        print(f"Next: edgarpack query {args.company} revenue --period lfy")
        return 0

    return asyncio.run(_run())


def _find_latest_sse_annual_report(stock_code: str) -> Any:
    from .china.acquire import find_latest_annual_report

    return find_latest_annual_report(stock_code)


def _synthetic_sse_company(stock_code: str) -> Any:
    from .identity import ResolvedCompany

    code = stock_code.strip()
    return ResolvedCompany(
        ticker=code,
        listing="SSE",
        source="SSE",
        cik=None,
        hk_stock_code=None,
        stock_code=code,
        aliases=(),
        private=False,
    )


def _cmd_build_sse(args: Any) -> int:
    from datetime import date

    async def _run() -> int:
        from .identity import looks_like_china_a_share_code
        from .pack.build import build_sse_pack

        url = getattr(args, "url", None)
        stock_code = getattr(args, "stock_code", None)
        company_name = getattr(args, "company", None)
        form_type = getattr(args, "form_type", "auto")

        if bool(getattr(args, "latest_annual", False)):
            if not stock_code:
                target = getattr(args, "target", None)
                if not target:
                    print(
                        "Error: provide a company/stock-code target or --stock-code with "
                        "--latest-annual",
                        file=sys.stderr,
                    )
                    return 2
                if looks_like_china_a_share_code(target):
                    stock_code = target.strip()
                else:
                    try:
                        resolved = await _resolve_cli_company(target)
                    except (UnknownCompany, AmbiguousCompany) as e:
                        print(f"Error: {e}", file=sys.stderr)
                        return 2
                    if getattr(resolved, "private", False):
                        print(
                            f"Error: {target} is private; no SSE annual report is available.",
                            file=sys.stderr,
                        )
                        return 2
                    if getattr(resolved, "source", None) != "SSE":
                        print(
                            f"Error: {target} is not registered as an SSE/A-share company.",
                            file=sys.stderr,
                        )
                        return 2
                    stock_code = getattr(resolved, "stock_code", None) or getattr(
                        resolved,
                        "ticker",
                        None,
                    )
                    company_name = company_name or _canonical_company_label(resolved, target)

            try:
                selected = _find_latest_sse_annual_report(str(stock_code))
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
            url = selected.source_url
            company_name = (
                getattr(args, "company", None)
                or company_name
                or selected.company_name
                or str(stock_code)
            )
            filing_date = selected.filing_date
            if form_type == "auto":
                form_type = "annual-report"
            print("Selected annual report")
            print(f"  Stock Code: {stock_code}")
            print(f"  Company: {company_name}")
            print(f"  Filing Date: {filing_date.isoformat()}")
            print(f"  Source: {url}")
        else:
            missing = [
                name
                for name, value in (
                    ("--url", url),
                    ("--stock-code", stock_code),
                    ("--company", company_name),
                    ("--filing-date", getattr(args, "filing_date", None)),
                )
                if not value
            ]
            if missing:
                print(
                    "Error: missing required manual build arguments: " + ", ".join(missing),
                    file=sys.stderr,
                )
                print(
                    "Tip: use `edgarpack build-sse <company-or-code> --latest-annual` "
                    "to look up the primary annual report automatically.",
                    file=sys.stderr,
                )
                return 2
            try:
                filing_date = date.fromisoformat(args.filing_date)
            except ValueError:
                print(
                    f"Error: invalid date format: {args.filing_date} (use YYYY-MM-DD)",
                    file=sys.stderr,
                )
                return 2

        try:
            result = await build_sse_pack(
                url=str(url),
                stock_code=str(stock_code),
                company_name=str(company_name),
                filing_date=filing_date,
                out_dir=args.out,
                pdf_path=args.pdf,
                with_chunks=bool(args.with_chunks),
                force=bool(args.force),
                translate=bool(args.translate),
                translate_model=args.translate_model,
                translate_concurrency=int(getattr(args, "translate_concurrency", 5)),
                translate_batch_size=int(getattr(args, "translate_batch_size", 25)),
                form_type=form_type,
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


def _resolve_hk_stock_code(company: str) -> str:
    """Resolve a build-hk positional arg to a HKEX stock code.

    A bare numeric code goes straight to the acquire layer, which zero-pads and
    substring-resolves it. A name/ticker is resolved through the identity index
    and must route to a HKEX listing.
    """
    query = company.strip()
    if query.replace(" ", "").isdigit():
        return query.replace(" ", "")
    resolved = asyncio.run(_resolve_cli_company(query))
    if getattr(resolved, "source", None) != "HKEX":
        raise UnknownCompany(
            f"{company!r} does not resolve to a HKEX listing; pass a bare HKEX stock "
            "code (e.g. 0700) instead."
        )
    code = getattr(resolved, "hk_stock_code", None)
    if not code:
        raise UnknownCompany(f"{company!r} resolves to HKEX but has no stock code in the universe.")
    return str(code)


def _acquire_hk_filing(client: Any, code: str) -> tuple[Any, str, list[str]]:
    from .hk import acquire as hk

    hk.warm_up(client)
    match = hk.resolve_stock_id(client, code)
    rows = hk.list_annual_reports(client, match.stock_id)
    row = hk.select_latest_annual_report(rows, stock_code=match.code)
    ref = hk.to_filing_ref(row, stock_code=match.code)
    return ref, match.name, list(row.stock_codes)


def _print_hk_facts_summary(pack_path: Path, facts_path: Path) -> None:
    data = json.loads(facts_path.read_text())
    facts = data.get("facts", {})
    concept_count = sum(len(concepts) for concepts in facts.values())
    print(f"Pack: {pack_path}")
    print(f"Company: {data.get('company')}  Stock code: {data.get('stock_code')}")
    print(f"Facts: {concept_count} concept(s) across {len(facts)} standard block(s)")


def _cmd_build_hk(args: Any) -> int:
    import httpx

    from .hk import acquire as hk
    from .hk import extract as hk_extract
    from .hk.adapter import build_hk_pack
    from .hk.toc import HKSectioningError

    class _BlockedFallbackError(Exception):
        pass

    try:
        code = _resolve_hk_stock_code(args.company)
    except (UnknownCompany, AmbiguousCompany) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    client = httpx.Client(
        headers={"User-Agent": "edgarpack/0.1 (+https://github.com)"},
        follow_redirects=True,
        timeout=120.0,
    )
    try:
        ref, company_name, dual_codes = _acquire_hk_filing(client, code)
        out_dir = args.out / ref.stock_code / f"{ref.stock_code}_{ref.fiscal_year}"
        pack = build_hk_pack(
            ref,
            out_dir,
            company_name=company_name,
            dual_counter_codes=dual_codes,
            client=client,
        )
    except HKSectioningError as e:
        print(f"Error: could not section the HKEX filing for {code}: {e}", file=sys.stderr)
        return 1
    except (hk.HKEXSearchBlocked, hk.HKFilingMetadataError, LookupError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    finally:
        client.close()

    # hk-extract-fixes owns extract.py; consume its typed error when it lands,
    # falling back to a local stand-in in trees where it has not.
    blocked_error: type[BaseException] = getattr(
        hk_extract, "HKExtractionBlockedError", _BlockedFallbackError
    )
    try:
        facts_path = hk_extract.extract_facts_from_pack(pack.path)
    except blocked_error as e:
        print(f"Error: HKEX facts extraction blocked for {code}: {e}", file=sys.stderr)
        print(f"Sectioned pack written to {pack.path} (facts not extracted).")
        return 1

    _print_hk_facts_summary(pack.path, facts_path)
    return 0


def _cmd_translate_sse(args: Any) -> int:
    from .china.translate.pipeline import run_translate_sse

    return run_translate_sse(args)


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
        from .query.layer_zero import MetricNotFound, resolve_alias
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
        metric_list_for_error: list[str] | None = None
        if expanded is None:
            metric_input = None
        else:
            metric_input = expanded
            metric_list_for_error = expanded
            metric_list_for_render = [resolve_alias(metric) for metric in expanded]

        async def _fetch(period: str) -> Any:
            return await financials(
                company=args.company,
                metrics=metric_input,
                period=period,
                force=bool(args.force),
                pack_root=getattr(args, "packs", DEFAULT_PACKS_DIR),
                display_token=args.company,
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
            metric_names = metric_list_for_error or []
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

        # Emit a one-line hint when registration extraction couldn't run. A
        # missing API key gets install/export instructions; a runtime call
        # failure gets its detail and a retry nudge. Scan every period's result
        # (not just the first) so --period lfy,pro-forma surfaces the hint even
        # when only the pro-forma call hit the failure.
        scan_sources = [result] if len(periods) == 1 else list(results_by_period.values())
        missing_key = any(
            getattr(v, "source", "") == "no_api_key"
            for r in scan_sources
            for v in (r.metrics or {}).values()
            if v is not None
        )
        if missing_key:
            print(_render_query_no_api_key_hint(), file=sys.stderr)
        else:
            extraction_failed = _registration_extraction_failure_message(scan_sources)
            if extraction_failed:
                print(_render_query_extraction_failed_hint(extraction_failed), file=sys.stderr)

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
            from .query.render import _render_query_table

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
            print(
                multi_period_to_lean_json(
                    results_by_period,
                    metric_list_for_render,
                    periods,
                    display_token=args.company,
                )
            )
            return 0

        if args.output_format == "json-full":
            print(
                multi_period_to_full_json(
                    results_by_period,
                    metric_list_for_render,
                    periods,
                    display_token=args.company,
                )
            )
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
        from .query.comps import (
            comps,
            comps_multi_period_to_json,
            comps_multi_period_to_lean_json,
            comps_series_to_period_grid,
            comps_to_json,
            comps_to_lean_json,
            expand_comps_periods,
            format_comps_multi_period_table,
            format_comps_table,
        )

        metric_list = [m.strip() for m in args.metrics.split(",")]

        try:
            periods = expand_comps_periods(args.period)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

        quarterly_series = len(periods) == 1 and periods[0].startswith("quarterly:")
        render_periods = periods

        try:
            if quarterly_series:
                quarterly_count = int(periods[0].split(":", 1)[1])
                results = await comps(
                    companies=args.companies,
                    metrics=metric_list,
                    period=periods[0],
                    force=bool(args.force),
                )
                results_by_period, render_periods = comps_series_to_period_grid(
                    results,
                    metric_list,
                    max_periods=quarterly_count,
                )
            elif len(periods) == 1:
                results = await comps(
                    companies=args.companies,
                    metrics=metric_list,
                    period=periods[0],
                    force=bool(args.force),
                )
            else:
                gathered = await asyncio.gather(
                    *[
                        comps(
                            companies=args.companies,
                            metrics=metric_list,
                            period=period,
                            force=bool(args.force),
                        )
                        for period in periods
                    ]
                )
                results_by_period = dict(zip(periods, gathered))
                render_periods = periods
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        strict_flag = bool(getattr(args, "strict", False))
        strict_rejected: dict[str, list[str]] = {}
        if strict_flag:
            from .query.strict import apply_strict

            if len(periods) > 1 or quarterly_series:
                scan_results = [
                    result
                    for period_results in results_by_period.values()
                    for result in period_results.values()
                ]
            else:
                scan_results = list(results.values())
            for _result in scan_results:
                rejected = apply_strict(_result)
                if rejected:
                    key = _result.display_token or _result.company or _result.cik
                    existing = strict_rejected.setdefault(key, [])
                    for metric in rejected:
                        if metric not in existing:
                            existing.append(metric)

        if args.output_format == "json":
            import json

            if len(periods) > 1 or quarterly_series:
                payload = json.loads(
                    comps_multi_period_to_lean_json(
                        results_by_period,
                        metric_list,
                        render_periods,
                        companies=args.companies,
                    )
                )
                if strict_flag and strict_rejected:
                    payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
                return 0

            # comps_to_lean_json returns a JSON string; we want to re-parse
            # only when we need to attach strict_rejected. For the common
            # non-strict path the output stays byte-identical.
            if strict_flag and strict_rejected:
                payload = json.loads(comps_to_lean_json(results, metric_list, periods[0]))
                payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
            else:
                print(comps_to_lean_json(results, metric_list, periods[0]))
        elif args.output_format == "json-full":
            import json

            if len(periods) > 1 or quarterly_series:
                payload = json.loads(
                    comps_multi_period_to_json(
                        results_by_period,
                        render_periods,
                        companies=args.companies,
                    )
                )
                if strict_flag and strict_rejected:
                    payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
                return 0

            if strict_flag and strict_rejected:
                payload = json.loads(comps_to_json(results))
                payload["strict_rejected"] = strict_rejected
                print(json.dumps(payload, indent=2, default=str))
            else:
                print(comps_to_json(results))
        else:
            width = shutil.get_terminal_size((120, 20)).columns
            if len(periods) > 1 or quarterly_series:
                citations_mode = args.citations if args.citations is not None else "footer"
                print(
                    format_comps_multi_period_table(
                        results_by_period,
                        metric_list,
                        render_periods,
                        companies=args.companies,
                        citations_mode=citations_mode,
                        show_links=args.show_links,
                        audit=bool(args.audit),
                        terminal_width=width,
                    )
                )
            else:
                citations_mode = args.citations if args.citations is not None else "inline"
                print(
                    format_comps_table(
                        results,
                        metric_list,
                        citations_mode=citations_mode,
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
            describe_images=bool(args.describe_images),
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
    elif pd.change_type.value == "moved":
        print(f"      [MOV sim={pd.similarity:.0%}]")
        print(f"        - {_truncate(pd.old_text or '')}")
        print(f"        + {_truncate(pd.new_text or '')}")


def _cmd_diff(args: Any) -> int:
    async def _run() -> int:
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
                disk_packs = []
                try:
                    resolved = await _resolve_cli_company(args.ticker)
                    cik = getattr(resolved, "cik", None)
                    if isinstance(cik, str) and cik.strip():
                        disk_packs = _local_pack_records(
                            cik=cik,
                            ticker=ticker,
                            form_type=args.form,
                            limit=20,
                        )
                except (UnknownCompany, AmbiguousCompany, ValueError):
                    disk_packs = []
                if len(disk_packs) >= 2:
                    print(
                        _local_pack_hint(disk_packs, command_label=args.ticker, form_type=args.form)
                        + " Using disk packs for this diff run.",
                        file=sys.stderr,
                    )
                    packs = disk_packs
                else:
                    print(
                        f"Error: need at least 2 {args.form} filings for {ticker}, "
                        f"found {len(packs)}",
                        file=sys.stderr,
                    )
                    if disk_packs:
                        print(
                            f"Found only {len(disk_packs)} matching pack(s) on disk under ./packs.",
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

        if args.output_format == "html":
            if args.out is None:
                print("Error: --out is required when --format html", file=sys.stderr)
                return 2

            from .diff.html_report import render_pair_report_html
            from .diff.report_builder import build_pair_report

            report = build_pair_report(before_dir, after_dir)
            reproduce_command = (
                f"edgarpack diff --before {before_dir} --after {after_dir} "
                f"--format html --out {args.out}"
            )
            html = render_pair_report_html(report, reproduce_command=reproduce_command)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(html, encoding="utf-8")
            print(f"Wrote HTML diff report to {args.out}")
            return 0

        from .diff.section_diff import diff_filings

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


def _render_registration_timeline(args: Any) -> int:
    """Print a redline timeline for a pre-IPO filer's S-1 chain.

    For each consecutive pair (S-1 -> S-1/A -> ... -> 424B), runs diff_filings
    and summarizes section-level adds / removes / modifications with
    word-weighted change intensity. Top-N most interesting sections surface
    first; fully-unchanged sections are omitted.
    """
    from .diff.section_diff import diff_filings
    from .diff.timeline import build_registration_timeline
    from .query.kpi_discover import extract_s1_metrics_from_pack

    if not getattr(args, "cik", None):
        print("error: --cik is required when --series=registration", file=sys.stderr)
        return 2

    pack_root = Path(getattr(args, "packs", DEFAULT_PACKS_DIR))
    entries = build_registration_timeline(pack_root=pack_root, cik=args.cik)

    if not entries:
        print(
            f"No registration-class filings found for CIK {args.cik} under {pack_root}",
            file=sys.stderr,
        )
        return 1

    if getattr(args, "output_format", "text") == "html":
        out_dir = getattr(args, "out", None)
        if out_dir is None:
            print("error: --out is required when --format html", file=sys.stderr)
            return 2

        from .diff.html_report import render_pair_report_html, render_timeline_index_html
        from .diff.report_builder import build_pair_report
        from .diff.report_models import TimelineReport, TimelineReportEntry, TimelineTransition

        out_dir.mkdir(parents=True, exist_ok=True)
        timeline_entries = [
            TimelineReportEntry(
                accession=entry.accession,
                form_type=entry.form_type,
                filing_date=entry.filing_date,
                pack_dir=str(entry.pack_dir),
            )
            for entry in entries
        ]
        transitions: list[TimelineTransition] = []

        for idx, (before, after) in enumerate(zip(entries, entries[1:], strict=False), start=1):
            pair_report = build_pair_report(before.pack_dir, after.pack_dir)
            output_file = f"pair-{idx:03d}.html"
            reproduce_command = (
                "edgarpack timeline "
                f"--series registration --cik {args.cik} --packs {pack_root} "
                f"--format html --out {out_dir}"
            )
            (out_dir / output_file).write_text(
                render_pair_report_html(pair_report, reproduce_command=reproduce_command),
                encoding="utf-8",
            )
            transitions.append(
                TimelineTransition(
                    index=idx,
                    before=timeline_entries[idx - 1],
                    after=timeline_entries[idx],
                    output_file=output_file,
                    sections_added=pair_report.sections_added,
                    sections_removed=pair_report.sections_removed,
                    sections_modified=pair_report.sections_modified,
                    sections_unchanged=pair_report.sections_unchanged,
                    overall_change_intensity=pair_report.overall_change_intensity,
                )
            )

        timeline = TimelineReport(
            cik=args.cik,
            entries=timeline_entries,
            transitions=transitions,
        )
        (out_dir / "index.html").write_text(
            render_timeline_index_html(timeline),
            encoding="utf-8",
        )
        print(f"Wrote HTML registration timeline report to {out_dir}")
        return 0

    print(f"Registration timeline for CIK {args.cik} ({len(entries)} filings)\n")

    # Registration metrics snapshot for the most recent filing: framing +
    # disclosures the filer states in their latest draft. Cheap, reads only that pack.
    latest = entries[-1]
    bundle = extract_s1_metrics_from_pack(latest.pack_dir)
    if bundle and bundle.total_hits:
        print(
            f"Registration disclosures in latest filing ({latest.accession}, {latest.form_type}):"
        )
        if bundle.framing:
            print(f"  framing claims: {len(bundle.framing)}")
            for hit in bundle.framing[:3]:
                print(f"    - {hit.claim}")
        if bundle.use_of_proceeds:
            print(f"  use of proceeds items: {len(bundle.use_of_proceeds)}")
        if bundle.dilution:
            print(f"  dilution claims: {len(bundle.dilution)}")
        if bundle.lockup:
            print(f"  lockup terms: {len(bundle.lockup)}")
        if bundle.principal_holders:
            print(f"  principal holders: {len(bundle.principal_holders)}")
        print()

    if len(entries) < 2:
        print("Only one registration filing present. No redline to compute.")
        return 0

    for before, after in zip(entries, entries[1:], strict=False):
        header = (
            f"=== {before.accession} ({before.form_type}, {before.filing_date}) "
            f"-> {after.accession} ({after.form_type}, {after.filing_date}) ==="
        )
        print(header)

        try:
            result = diff_filings(before.pack_dir, after.pack_dir, detail="sections")
        except Exception as exc:
            print(f"  diff failed: {exc}\n")
            continue

        print(
            f"  overall intensity: {result.overall_change_intensity:.1%}  "
            f"(+{result.sections_added} -{result.sections_removed} "
            f"~{result.sections_modified} ={result.sections_unchanged})"
        )

        changed = [d for d in result.section_deltas if d.change_type.value != "unchanged"]
        changed.sort(key=lambda d: d.interest_score, reverse=True)
        if not changed:
            print("  no section changes detected.\n")
            continue

        top_n = 5
        for delta in changed[:top_n]:
            marker = {
                "added": "+",
                "removed": "-",
                "modified": "~",
                "moved": "~",
            }.get(delta.change_type.value, "?")
            print(
                f"  {marker} {delta.title}  "
                f"[{delta.change_intensity:.1%} intensity, score {delta.interest_score:.2f}]"
            )
            if delta.change_type.value == "modified":
                print(
                    f"      +{delta.paragraphs_added} added, "
                    f"-{delta.paragraphs_removed} removed, "
                    f"~{delta.paragraphs_modified} modified"
                )

        remainder = len(changed) - top_n
        if remainder > 0:
            print(f"  ... {remainder} more changed sections omitted.")
        print()

    return 0


def _cmd_timeline(args: Any) -> int:
    series = getattr(args, "series", "annual")

    if series == "registration":
        return _render_registration_timeline(args)

    if getattr(args, "output_format", "text") == "html":
        print(
            "error: --format html is currently supported only with --series registration",
            file=sys.stderr,
        )
        return 2

    # Annual path (existing behavior, unchanged).
    async def _run() -> int:
        from .diff.timeline import build_timeline
        from .harvest.registry import PackRegistry

        if not getattr(args, "ticker", None):
            print("error: --ticker is required when --series=annual", file=sys.stderr)
            return 2
        if not getattr(args, "section", None):
            print("error: --section is required when --series=annual", file=sys.stderr)
            return 2

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
        packs = registry.list_packs(limit=None)
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


def _render_query_no_api_key_hint() -> str:
    return (
        "Note: registration financial extraction requires the `vlm` extra and "
        "ANTHROPIC_API_KEY. From the repo use `uv run --extra dev --extra vlm ...`; "
        "for an install use `pip install edgarpack[vlm]`. Disclosures available via "
        "`edgarpack which`."
    )


def _registration_extraction_failure_message(results: list[Any]) -> str | None:
    """Return a registration extraction-failure diagnostic message, if any.

    Skips the missing-key case (handled by the no_api_key hint) so this only
    fires for a runtime call / parse failure the user can retry.
    """
    for result in results:
        for diag in getattr(result, "diagnostics", []) or []:
            if getattr(diag, "metric", "") != "extraction":
                continue
            message = str(getattr(diag, "message", ""))
            if "no_api_key" in message:
                continue
            return message
    return None


def _render_query_extraction_failed_hint(message: str) -> str:
    return f"Note: {message}. Retry shortly."


def _render_which_empty_state(
    *,
    display_name: str,
    command_label: str,
    cik: str,
    diagnostics: Any,
    has_s1_context: bool = False,
) -> str:
    """Return an actionable empty-state message for `edgarpack which`."""
    if diagnostics.total_registered_packs == 0:
        return (
            f"No registered packs found for {display_name} (CIK: {cik}).\n"
            f"Build a periodic pack with `edgarpack build {command_label} --form 10-K`, "
            f"or build a registration pack with `edgarpack build {command_label} "
            "--form S-1 --with-chunks` or `--form F-1`."
        )
    if diagnostics.unreadable_manifest_packs >= diagnostics.eligible_packs > 0:
        return (
            f"No KPIs shown for {display_name} because all {diagnostics.eligible_packs} "
            "candidate filing packs were unreadable on disk.\n"
            f"Rebuild a fresh periodic pack with `edgarpack build {command_label} "
            f"--form 10-K --force`, or a fresh registration pack with `edgarpack build "
            f"{command_label} --form S-1 --with-chunks --force` or `--form F-1`."
        )
    if diagnostics.llm_failed_packs > 0 and diagnostics.discovered_packs == 0:
        return (
            f"No KPIs shown for {display_name} because discovery failed on "
            f"{diagnostics.llm_failed_packs} filing(s).\n"
            "Check that `codex` or `claude` is available, then retry with "
            f"`edgarpack which {command_label} --no-cache`."
        )
    if diagnostics.empty_packs > 0:
        if has_s1_context:
            name = display_name.rstrip(".")
            candidate_filings = [f for f in diagnostics.filings if f.candidate_count > 0]
            if candidate_filings:
                candidate_count = sum(f.candidate_count for f in candidate_filings)
                accepted = sum(f.accepted_rows for f in candidate_filings)
                rejected = sum(f.rejected_rows for f in candidate_filings)
                return (
                    f"No recurring operating KPI rows were accepted for {name}, but "
                    f"registration discovery scanned {candidate_count} candidate window(s) "
                    f"({accepted} accepted, {rejected} rejected).\n"
                    "Cached registration disclosures and financial metrics are shown below.\n"
                    f"Retry with `edgarpack which {command_label} --no-cache` after changing "
                    "the discovery backend or prompt."
                )
            return (
                f"No recurring operating KPI table was found for {name}.\n"
                "Cached registration disclosures and financial metrics are shown below.\n"
                f"Try `edgarpack query {command_label} revenue,net_income,operating_cash_flow,"
                "capex,free_cash_flow --period lfy,lfy-1` for the financial view."
            )
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
            "(manifest missing; run `edgarpack build <ticker> --form 10-K` "
            "or build a registration pack with `--form S-1 --with-chunks` or `--form F-1`)"
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


def _count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _render_which_coverage_note(diagnostics: Any) -> str | None:
    """Render a stdout warning when the KPI table is based on partial coverage."""
    eligible = int(getattr(diagnostics, "eligible_packs", 0) or 0)
    contributing = int(getattr(diagnostics, "contributing_packs", 0) or 0)
    if eligible <= 0 or contributing >= eligible:
        return None

    reasons: list[str] = []
    unreadable = int(getattr(diagnostics, "unreadable_manifest_packs", 0) or 0)
    if unreadable:
        reasons.append(_count_phrase(unreadable, "unreadable/missing pack"))
    llm_failed = int(getattr(diagnostics, "llm_failed_packs", 0) or 0)
    if llm_failed:
        reasons.append(_count_phrase(llm_failed, "discovery failure", "discovery failures"))
    empty = int(getattr(diagnostics, "empty_packs", 0) or 0)
    if empty:
        reasons.append(f"{empty} no qualifying KPIs")

    reason_text = f" ({', '.join(reasons)})" if reasons else ""
    return (
        "Coverage note: "
        f"{contributing} of {eligible} eligible filings contributed KPI rows"
        f"{reason_text}. Table is partial."
    )


def _which_diagnostics_payload(diagnostics: Any) -> dict[str, Any]:
    eligible = int(getattr(diagnostics, "eligible_packs", 0) or 0)
    contributing = int(getattr(diagnostics, "contributing_packs", 0) or 0)
    filings: list[dict[str, Any]] = []
    for item in getattr(diagnostics, "filings", []) or []:
        if hasattr(item, "to_json"):
            filings.append(item.to_json())
        elif isinstance(item, dict):
            filings.append(dict(item))
    return {
        "total_registered_packs": int(getattr(diagnostics, "total_registered_packs", 0) or 0),
        "eligible_packs": eligible,
        "contributing_packs": contributing,
        "cached_packs": int(getattr(diagnostics, "cached_packs", 0) or 0),
        "discovered_packs": int(getattr(diagnostics, "discovered_packs", 0) or 0),
        "manifest_missing_packs": int(getattr(diagnostics, "manifest_missing_packs", 0) or 0),
        "manifest_invalid_json_packs": int(
            getattr(diagnostics, "manifest_invalid_json_packs", 0) or 0
        ),
        "manifest_schema_mismatch_packs": int(
            getattr(diagnostics, "manifest_schema_mismatch_packs", 0) or 0
        ),
        "manifest_io_error_packs": int(getattr(diagnostics, "manifest_io_error_packs", 0) or 0),
        "llm_failed_packs": int(getattr(diagnostics, "llm_failed_packs", 0) or 0),
        "empty_packs": int(getattr(diagnostics, "empty_packs", 0) or 0),
        "partial": eligible > 0 and contributing < eligible,
        "coverage_note": _render_which_coverage_note(diagnostics),
        "filings": filings,
    }


def _render_which_table(aggregates: list[Any], max_periods: int) -> str:
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


def _cmd_which_china(args: Any, resolved: Any) -> int:
    """List deterministic metrics available from a local China pack."""

    async def _run() -> tuple[int, Any | None, str | None]:
        from .query.financials import financials

        try:
            result = await financials(
                company=args.company,
                metrics=None,
                period="lfy",
                display_token=args.company,
            )
        except FileNotFoundError as e:
            return 1, None, str(e)
        except Exception as e:
            return 1, None, str(e)
        return 0, result, None

    rc, result, error = asyncio.run(_run())
    source = str(getattr(resolved, "source", "China") or "China")
    stock_code = (
        getattr(resolved, "stock_code", None)
        or getattr(resolved, "hk_stock_code", None)
        or getattr(resolved, "ticker", "")
    )
    display_name = _canonical_company_label(resolved, args.company)
    if rc != 0 or result is None:
        if source == "SSE":
            print(
                f"No local China pack found for {display_name} ({source} {stock_code}).",
                file=sys.stderr,
            )
            print(
                "Build the annual-report pack first, for example:",
                file=sys.stderr,
            )
            print(
                "  edgarpack build-sse --stock-code 688696 "
                '--company "Chengdu XGIMI Technology Co., Ltd." '
                "--filing-date 2025-04-22 "
                "--url https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF "
                "--out packs --with-chunks",
                file=sys.stderr,
            )
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    if args.which_format == "json":
        print(json.dumps(result.to_lean_dict(), indent=2, sort_keys=True))
        return 0

    from .query.currency import CurrencyMode, format_cited_currency

    rows: list[tuple[str, str, str, str, str]] = []
    currency_mode = cast(CurrencyMode, getattr(args, "currency", "both"))
    for metric, value in result.metrics.items():
        if value is None:
            continue
        cited = value[0] if isinstance(value, list) and value else value
        if cited is None or isinstance(cited, list):
            continue
        rows.append(
            (
                metric,
                cited.concept,
                format_cited_currency(cited, mode=currency_mode, metric=metric),
                cited.fiscal_label,
                cited.source or "pack",
            )
        )

    print(f"Disclosed metrics for {display_name} ({source} {stock_code}):")
    if not rows:
        print("No deterministic metrics found in the local China pack.")
        return 1

    widths = [
        max(len(row[i]) for row in rows + [("metric", "concept", "latest", "period", "src")])
        for i in range(5)
    ]
    header = ("metric", "concept", "latest", "period", "src")
    print("  ".join(header[i].ljust(widths[i]) for i in range(5)))
    print("  ".join("─" * widths[i] for i in range(5)))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(5)))
    return 0


def _cmd_which(args: Any) -> int:
    """List the qualitative / MD&A KPIs a company discloses across filings."""
    import json as _json

    from .harvest.registry import PackRegistry
    from .query.kpi_discover import DiscoveryDiagnostics, DiscoveryProgressEvent, discover_kpis

    async def _resolve() -> tuple[int, Any | None]:
        try:
            resolved = await _resolve_cli_company(args.company)
            return 0, resolved
        except UnknownCompany as e:
            from .identity import looks_like_china_a_share_code

            if looks_like_china_a_share_code(args.company):
                return 0, _synthetic_sse_company(args.company)
            print(f"Error: {e}", file=sys.stderr)
            return 2, None
        except (AmbiguousCompany, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2, None
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1, None

    rc, resolved = asyncio.run(_resolve())
    if rc != 0 or resolved is None:
        return rc
    if getattr(resolved, "source", None) in {"SSE", "HKEX"}:
        return _cmd_which_china(args, resolved)
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
            packs = _local_pack_records(cik=cik, ticker=company_label, limit=200)
            if packs:
                print(
                    _local_pack_hint(packs, command_label=company_label),
                    file=sys.stderr,
                )
                return 1
            else:
                print(
                    f"No registered packs found for {display_name} (CIK: {cik}). "
                    f"{_local_pack_hint([], command_label=company_label)}",
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

    s1_block = _render_which_s1_metrics(packs, diagnostics=diagnostics)

    if args.which_format == "json":
        payload = {
            "cik": cik,
            "company": packs[0].company_name,
            "ticker": packs[0].ticker,
            "count": len(aggregates),
            "diagnostics": _which_diagnostics_payload(diagnostics),
            "kpis": [a.to_json() for a in aggregates],
        }
        print(_json.dumps(payload, indent=2, default=str))
        return 0

    print(f"Disclosed KPIs for {packs[0].company_name} (CIK: {cik}):\n")
    if aggregates:
        print("Rendering KPI table", file=sys.stderr)
        coverage_note = _render_which_coverage_note(diagnostics)
        if coverage_note:
            print(coverage_note)
            print()
        print(_render_which_table(aggregates, int(args.max_periods)))
    else:
        print(
            _render_which_empty_state(
                display_name=display_name,
                command_label=company_label,
                cik=cik,
                diagnostics=diagnostics,
                has_s1_context=bool(s1_block),
            )
        )

    if s1_block:
        print()
        print(s1_block)
    return 0


def _cached_s1_queryable_metrics(pack_dir: Path) -> list[str]:
    """Return user-facing financial metrics available in a current registration cache."""
    from .query.s1_financials import SCHEMA_VERSION, SnapshotResult, source_sha256_for_pack

    cache = pack_dir / "s1_financials.json"
    if not cache.exists():
        return []
    try:
        snapshot = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return []
    if snapshot.schema_version != SCHEMA_VERSION:
        return []
    if snapshot.source_sha256 != source_sha256_for_pack(pack_dir):
        return []

    raw_metrics = {
        fact.metric
        for fact in snapshot.facts
        if fact.is_audited
        and not fact.is_pro_forma
        and (fact.fiscal_period or "FY").upper() == "FY"
    }
    display_metrics: set[str] = set()
    for metric in raw_metrics:
        if metric == "operating_income_loss":
            display_metrics.add("operating_income")
        elif metric == "net_income_loss":
            display_metrics.add("net_income")
        else:
            display_metrics.add(metric)

    if {"operating_cash_flow", "capex"}.issubset(raw_metrics):
        display_metrics.add("free_cash_flow")
    if {"gross_profit", "revenue"}.issubset(raw_metrics):
        display_metrics.add("gross_margin")
    if {"operating_income_loss", "revenue"}.issubset(raw_metrics):
        display_metrics.add("operating_margin")
    if {"net_income_loss", "revenue"}.issubset(raw_metrics):
        display_metrics.add("net_margin")
    if {"operating_cash_flow", "capex", "revenue"}.issubset(raw_metrics):
        display_metrics.add("fcf_margin")
    if {"capex", "revenue"}.issubset(raw_metrics):
        display_metrics.add("capex_intensity")

    preferred_order = [
        "revenue",
        "gross_profit",
        "gross_margin",
        "adjusted_gross_profit",
        "operating_income",
        "operating_margin",
        "net_income",
        "net_margin",
        "adjusted_ebitda",
        "operating_cash_flow",
        "capex",
        "free_cash_flow",
        "fcf_margin",
        "capex_intensity",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    ]
    ordered = [metric for metric in preferred_order if metric in display_metrics]
    ordered.extend(sorted(display_metrics - set(ordered)))
    return ordered


def _render_which_s1_metrics(
    packs: list[Any],
    *,
    diagnostics: Any | None = None,
) -> str:
    """Render a registration profile block for any registration-class packs.

    Shown only when the CIK has at least one pack with non-empty extractor
    output. Kept compact so periodic-filer queries don't get visually heavier.
    """
    from .query.registration_profile import build_registration_profile
    from .sec.submissions import is_registration_form

    lines: list[str] = []
    reg_packs = [p for p in packs if is_registration_form(getattr(p, "form_type", ""))]
    reg_packs.sort(key=lambda p: getattr(p, "filing_date", "") or "")
    filing_status = {
        status.accession: status for status in getattr(diagnostics, "filings", []) or []
    }

    for pack in reg_packs:
        profile = build_registration_profile(Path(pack.pack_dir))
        status = filing_status.get(getattr(pack, "accession", ""))
        status_has_content = bool(
            status is not None
            and (
                status.candidate_count
                or status.accepted_rows
                or status.rejected_rows
                or status.retryable
            )
        )
        if (profile is None or not profile.has_content) and not status_has_content:
            continue

        if profile:
            header = (
                f"Registration profile ({profile.form_type}, {profile.filing_date}, "
                f"{profile.accession}):"
            )
        else:
            header = (
                f"Registration profile ({pack.form_type}, {pack.filing_date}, {pack.accession}):"
            )
        lines.append(header)

        if profile and profile.financial_metrics:
            lines.append("  Queryable registration financial metrics:")
            lines.append(f"    {', '.join(profile.financial_metrics)}")
        elif profile and profile.financial_status not in {"not_extracted", "ok"}:
            lines.append(f"  Registration financial extraction: {profile.financial_status}")

        if status is not None and status.candidate_count:
            retryable = " retryable" if status.retryable else ""
            lines.append(
                "  KPI discovery:"
                f" {status.candidate_count} candidate window(s),"
                f" {status.accepted_rows} accepted,"
                f" {status.rejected_rows} rejected{retryable}"
            )

        if profile:
            for group in profile.disclosures:
                lines.append(f"  {group.label} ({len(group.claims)}):")
                for claim in group.claims[:3]:
                    lines.append(f"    - {claim}")
                if len(group.claims) > 3:
                    lines.append(f"    ... {len(group.claims) - 3} more")
        lines.append("")

    return "\n".join(lines).rstrip()


if __name__ == "__main__":
    app()
