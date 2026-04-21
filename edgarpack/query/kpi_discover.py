"""Per-company KPI discovery aggregator backing `edgarpack which`.

Walks every pack registered for a CIK, runs the discovery LLM pass on
each (cache hits skip the LLM), and returns a per-slug view that merges
all per-filing rows into a period-availability matrix plus alias tracking.

Responsibilities split with kpi_extract.py:
- kpi_extract.py owns single-pack LLM extraction + hallucination firewall.
- kpi_discover.py owns multi-pack aggregation, cache invalidation, and the
  public CompanyKpiAggregate shape consumed by the CLI / API.

Catalog-hit metrics (KPI_CATALOG) are NOT run through the discovery LLM:
their presence is inferred by reading the learned_concepts cache (kpi-llm
rows). That keeps the `which` view unified across both sources without
double-extracting the same metric.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path

from ..harvest.registry import PackRecord, PackRegistry
from .kpi_extract import (
    KPI_CATALOG,
    DiscoveredKpi,
    _load_pack_manifest,
    _resolve_period_end,
    extract_discoveries_detailed,
)
from .learned_registry import CompanyKpiRow, LearnedRegistry

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryDiagnostics:
    """Structured per-run stats for a `which` invocation."""

    total_registered_packs: int = 0
    eligible_packs: int = 0
    cached_packs: int = 0
    discovered_packs: int = 0
    manifest_missing_packs: int = 0
    manifest_invalid_json_packs: int = 0
    manifest_schema_mismatch_packs: int = 0
    manifest_io_error_packs: int = 0
    llm_failed_packs: int = 0
    empty_packs: int = 0

    @property
    def unreadable_manifest_packs(self) -> int:
        return (
            self.manifest_missing_packs
            + self.manifest_invalid_json_packs
            + self.manifest_schema_mismatch_packs
            + self.manifest_io_error_packs
        )


@dataclass(frozen=True)
class DiscoveryProgressEvent:
    """Structured discovery progress event emitted to the CLI layer."""

    phase: str
    index: int = 0
    total: int = 0
    pack: PackRecord | None = None


@dataclass(frozen=True)
class PackDiscoveryResult:
    """Result of attempting discovery for a single filing pack."""

    discovered: list[DiscoveredKpi]
    status: str
    # one of: cached | discovered | manifest_missing | manifest_invalid_json
    #       | manifest_schema_mismatch | manifest_io_error | llm_failed | empty


@dataclass(frozen=True)
class PeriodPoint:
    """One period's value for an aggregated KPI.

    `label` is the human-readable period tag ('FY2024', "Q1'24", or a bare
    ISO date when fiscal labels aren't available). `sort_key` is the
    period_end ISO string; downstream code uses it for stable ordering.
    """

    label: str
    sort_key: str
    period_end: str
    fiscal_year: int
    fiscal_period: str
    form_type: str
    accession: str
    value: float | None
    unit: str | None
    magnitude: str | None
    section_id: str | None
    chunk_id: str | None
    source_substring: str | None


@dataclass
class CompanyKpiAggregate:
    """A KPI rolled up across every filing that disclosed it.

    `source` is 'catalog' when the KPI appears in KPI_CATALOG (i.e. is a
    known named metric that Layer B has already extracted), 'discovered'
    when free-form discovery surfaced it. Mixed sources collapse to
    'catalog' so users see the stable name first.
    """

    slug: str
    display_name: str
    source: str  # 'catalog' | 'discovered'
    unit: str | None
    definition: str | None
    aliases: list[str] = field(default_factory=list)
    periods: list[PeriodPoint] = field(default_factory=list)

    @property
    def latest(self) -> PeriodPoint | None:
        return self.periods[0] if self.periods else None

    def to_json(self) -> dict:
        latest = self.latest
        return {
            "slug": self.slug,
            "display_name": self.display_name,
            "source": self.source,
            "unit": self.unit,
            "definition": self.definition,
            "aliases": list(self.aliases),
            "latest_value": latest.value if latest else None,
            "latest_period": latest.label if latest else None,
            "periods": [
                {
                    "label": p.label,
                    "period_end": p.period_end,
                    "fiscal_year": p.fiscal_year,
                    "fiscal_period": p.fiscal_period,
                    "form_type": p.form_type,
                    "accession": p.accession,
                    "value": p.value,
                    "unit": p.unit,
                    "magnitude": p.magnitude,
                    "section_id": p.section_id,
                    "chunk_id": p.chunk_id,
                    "source_substring": p.source_substring,
                }
                for p in self.periods
            ],
        }


# ---------------------------------------------------------------------------
# Per-pack discovery cache management
# ---------------------------------------------------------------------------


def _period_label(form_type: str, fiscal_year: int, fiscal_period: str, period_end: str) -> str:
    """Render a human-readable period label for the aggregate view."""
    form = (form_type or "").upper()
    if fiscal_year and fiscal_period == "FY":
        return f"FY{fiscal_year}"
    if fiscal_year and fiscal_period.startswith("Q"):
        yy = fiscal_year % 100
        return f"{fiscal_period}'{yy:02d}"
    if period_end:
        return period_end
    return form or "unknown"


def _discover_pack(
    *,
    pack_record: PackRecord,
    learned_reg: LearnedRegistry,
    force: bool = False,
) -> PackDiscoveryResult:
    """Run or replay the discovery LLM pass for one pack.

    On cache hit (any company_kpis row exists for this accession), reads
    the cached rows back as DiscoveredKpi and returns them. On miss, runs
    the LLM, persists every discovered row, and returns the fresh list.
    Pack directory read errors are logged and yield an empty list rather
    than raising, so one bad pack doesn't poison the aggregate view.
    """
    cik = pack_record.cik
    accession = pack_record.accession

    if not force and learned_reg.company_kpi_has_accession(cik, accession):
        cached_rows = learned_reg.company_kpi_list(cik=cik, accession=accession)
        if not cached_rows:
            return PackDiscoveryResult(discovered=[], status="empty")
        return PackDiscoveryResult(
            discovered=[_cached_row_to_discovered(row) for row in cached_rows],
            status="cached",
        )

    pack_dir = Path(pack_record.pack_dir)
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        logger.info("Discovery: manifest.json missing at %s (accn=%s)", pack_dir, accession)
        return PackDiscoveryResult(discovered=[], status="manifest_missing")
    try:
        manifest = _load_pack_manifest(pack_dir)
    except json.JSONDecodeError as e:
        logger.info(
            "Discovery: invalid JSON manifest at %s (accn=%s): %s", pack_dir, accession, e
        )
        return PackDiscoveryResult(discovered=[], status="manifest_invalid_json")
    except (OSError, UnicodeDecodeError) as e:
        logger.info(
            "Discovery: manifest I/O error at %s (accn=%s): %s", pack_dir, accession, e
        )
        return PackDiscoveryResult(discovered=[], status="manifest_io_error")

    # Schema mismatch: manifest parsed but is the wrong shape for this EdgarPack.
    schema_version = manifest.get("schema_version") if isinstance(manifest, dict) else None
    from ..config import SCHEMA_VERSION as _SCHEMA_VERSION

    required_top_level = {"filing", "sections", "parser_version"}
    missing = required_top_level - set(manifest.keys() if isinstance(manifest, dict) else [])
    if not isinstance(schema_version, int) or schema_version != _SCHEMA_VERSION or missing:
        logger.info(
            "Discovery: manifest schema mismatch at %s (accn=%s): schema=%r missing=%s",
            pack_dir,
            accession,
            schema_version,
            sorted(missing),
        )
        return PackDiscoveryResult(discovered=[], status="manifest_schema_mismatch")

    existing_slugs = learned_reg.company_kpi_distinct_slugs(cik)
    extraction = extract_discoveries_detailed(
        pack_dir=pack_dir,
        pack_record=pack_record,
        manifest=manifest,
        existing_slugs=existing_slugs,
    )
    discovered = extraction.kpis

    if force:
        # Drop prior rows for this accession before writing fresh ones so a
        # rerun with a different prompt / model doesn't accumulate stale
        # rows next to the new ones.
        learned_reg.company_kpi_clear(cik=cik, accession=accession)

    if not discovered:
        if extraction.status == "no_kpis":
            # Persist a sentinel so the next `which` call doesn't re-invoke the
            # LLM on a filing that genuinely has no qualifying KPIs.
            period_end_iso = ""
            filing = manifest.get("filing", {}) if isinstance(manifest, dict) else {}
            por = filing.get("period_of_report") if isinstance(filing, dict) else None
            if isinstance(por, str) and por.strip():
                period_end_iso = por.strip()
            learned_reg.company_kpi_mark_empty(
                cik=cik,
                accession=accession,
                form_type=pack_record.form_type,
                period_end=period_end_iso,
            )
            return PackDiscoveryResult(discovered=[], status="empty")
        return PackDiscoveryResult(discovered=[], status="llm_failed")

    for kpi in discovered:
        learned_reg.company_kpi_upsert(
            cik=cik,
            accession=accession,
            slug=kpi.slug,
            display_name=kpi.display_name,
            aliases=[],
            unit=kpi.unit,
            magnitude=kpi.magnitude,
            value=kpi.value,
            period_end=kpi.period_end,
            fiscal_year=kpi.fiscal_year,
            fiscal_period=kpi.fiscal_period,
            form_type=pack_record.form_type,
            definition=kpi.definition,
            section_id=kpi.section_id,
            chunk_id=kpi.chunk_id,
            source_substring=kpi.source_substring,
            confidence=kpi.confidence,
        )
    return PackDiscoveryResult(discovered=discovered, status="discovered")


def _cached_row_to_discovered(row: CompanyKpiRow) -> DiscoveredKpi:
    return DiscoveredKpi(
        slug=row.slug,
        display_name=row.display_name,
        unit=row.unit,
        magnitude=row.magnitude,
        value=row.value,
        period_end=row.period_end,
        fiscal_year=row.fiscal_year,
        fiscal_period=row.fiscal_period,
        definition=row.definition,
        section_id=row.section_id,
        chunk_id=row.chunk_id,
        source_substring=row.source_substring or "",
        confidence=row.confidence or 0.0,
        reused_slug=False,
    )


# ---------------------------------------------------------------------------
# Catalog-hit enumeration (reads learned_concepts; does NOT run LLM)
# ---------------------------------------------------------------------------


def _catalog_points_for_cik(
    cik: str,
    learned_reg: LearnedRegistry,
    pack_records_by_accession: dict[str, PackRecord],
) -> dict[str, list[PeriodPoint]]:
    """Gather already-cached catalog KPI hits across every filing for a CIK.

    Reads the learned_concepts kpi-llm rows the Layer B extractor writes
    on successful catalog extractions. No LLM call; any catalog KPI the
    user has never queried for this company simply doesn't appear. This
    is the intended behavior for the first release: `which` surfaces
    *disclosed* KPIs, not catalog coverage aspirations.
    """
    rows = learned_reg.list_rows(cik=cik, source="kpi-llm")
    by_metric: dict[str, list[PeriodPoint]] = {}
    for row in rows:
        if row.metric not in KPI_CATALOG:
            continue
        pack = pack_records_by_accession.get(row.accession)
        if pack is None:
            continue
        try:
            manifest = _load_pack_manifest(Path(pack.pack_dir))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            manifest = {}
        period_end_date, fiscal_year, fiscal_period = _resolve_period_end(manifest, pack)
        period_end_iso = (
            period_end_date.isoformat() if period_end_date and period_end_date != _date.min else ""
        )
        label = _period_label(pack.form_type, fiscal_year, fiscal_period, period_end_iso)
        unit_hint = KPI_CATALOG[row.metric].unit_hint
        point = PeriodPoint(
            label=label,
            sort_key=period_end_iso or pack.filing_date,
            period_end=period_end_iso,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            form_type=pack.form_type,
            accession=row.accession,
            value=row.value_sample,
            unit=unit_hint,
            magnitude=None,
            section_id=None,
            chunk_id=None,
            source_substring=None,
        )
        by_metric.setdefault(row.metric, []).append(point)
    return by_metric


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def discover_kpis(
    cik: str,
    *,
    registry_path: Path | None = None,
    pack_registry: PackRegistry | None = None,
    force: bool = False,
    include_catalog: bool = True,
    diagnostics: DiscoveryDiagnostics | None = None,
    progress_callback: Callable[[DiscoveryProgressEvent], None] | None = None,
) -> list[CompanyKpiAggregate]:
    """Return the per-slug aggregate of KPIs disclosed by a company.

    Walks every pack registered for ``cik`` (10-K, 10-Q, and any other
    form the registry carries). For packs without a cached discovery pass,
    invokes the LLM (subject to backend availability); cached passes
    replay in memory at near-zero cost.

    Set ``force=True`` to re-run discovery on every pack, dropping cached
    rows. Use sparingly: each pack re-run costs one LLM invocation.

    Set ``include_catalog=False`` to restrict the output to free-form
    discovered KPIs (hides catalog-backed metrics like ARR even when
    they're in the learned_concepts cache).
    """
    own_registry = False
    if pack_registry is None:
        pack_registry = PackRegistry()
        own_registry = True

    learned_reg = LearnedRegistry(db_path=registry_path)

    try:
        packs = pack_registry.list_packs(cik=cik, limit=200)
        if diagnostics is not None:
            diagnostics.total_registered_packs = len(packs)
        if not packs:
            return []

        packs_by_accn: dict[str, PackRecord] = {p.accession: p for p in packs}
        eligible_packs = [
            p for p in packs if (p.form_type or "").upper().startswith(("10-K", "10-Q", "20-F"))
        ]
        if diagnostics is not None:
            diagnostics.eligible_packs = len(eligible_packs)

        # Run / replay discovery per pack. 10-Ks and 10-Qs are the primary
        # targets; other forms (8-K, S-1) rarely carry KPIs but there's no
        # harm letting the LLM decide per-filing.
        per_slug_points: dict[str, list[PeriodPoint]] = {}
        per_slug_display: dict[str, str] = {}
        per_slug_unit: dict[str, str | None] = {}
        per_slug_definition: dict[str, str | None] = {}
        per_slug_aliases: dict[str, list[str]] = {}

        for idx, pack in enumerate(eligible_packs, start=1):
            if progress_callback is not None:
                progress_callback(
                    DiscoveryProgressEvent(
                        phase="pack",
                        index=idx,
                        total=len(eligible_packs),
                        pack=pack,
                    )
                )
            pack_result = _discover_pack(
                pack_record=pack,
                learned_reg=learned_reg,
                force=force,
            )
            if diagnostics is not None:
                status_map = {
                    "cached": "cached_packs",
                    "discovered": "discovered_packs",
                    "manifest_missing": "manifest_missing_packs",
                    "manifest_invalid_json": "manifest_invalid_json_packs",
                    "manifest_schema_mismatch": "manifest_schema_mismatch_packs",
                    "manifest_io_error": "manifest_io_error_packs",
                    "llm_failed": "llm_failed_packs",
                    "empty": "empty_packs",
                }
                attr = status_map.get(pack_result.status)
                if attr is not None:
                    setattr(diagnostics, attr, getattr(diagnostics, attr) + 1)
            for kpi in pack_result.discovered:
                slug = kpi.slug
                if slug.startswith("__"):
                    continue
                label = _period_label(
                    pack.form_type, kpi.fiscal_year, kpi.fiscal_period, kpi.period_end
                )
                sort_key = kpi.period_end or pack.filing_date
                per_slug_points.setdefault(slug, []).append(
                    PeriodPoint(
                        label=label,
                        sort_key=sort_key,
                        period_end=kpi.period_end,
                        fiscal_year=kpi.fiscal_year,
                        fiscal_period=kpi.fiscal_period,
                        form_type=pack.form_type,
                        accession=pack.accession,
                        value=kpi.value,
                        unit=kpi.unit,
                        magnitude=kpi.magnitude,
                        section_id=kpi.section_id,
                        chunk_id=kpi.chunk_id,
                        source_substring=kpi.source_substring,
                    )
                )
                # Latest filing wins for display_name / definition / unit so the
                # most recent wording surfaces. Prior spellings get appended as
                # aliases so naming drift is visible.
                existing_display = per_slug_display.get(slug)
                if existing_display and existing_display != kpi.display_name:
                    aliases = per_slug_aliases.setdefault(slug, [])
                    if existing_display not in aliases and existing_display != kpi.display_name:
                        aliases.append(existing_display)
                per_slug_display[slug] = kpi.display_name or existing_display or slug
                if kpi.definition:
                    per_slug_definition[slug] = kpi.definition
                elif slug not in per_slug_definition:
                    per_slug_definition[slug] = None
                if kpi.unit:
                    per_slug_unit[slug] = kpi.unit
                elif slug not in per_slug_unit:
                    per_slug_unit[slug] = None

        catalog_points: dict[str, list[PeriodPoint]] = {}
        if include_catalog:
            catalog_points = _catalog_points_for_cik(cik, learned_reg, packs_by_accn)

        aggregates: list[CompanyKpiAggregate] = []
        catalog_slugs = set(catalog_points.keys())
        discovered_slugs = set(per_slug_points.keys())

        for slug in sorted(catalog_slugs | discovered_slugs):
            points: list[PeriodPoint] = []
            source: str
            display_name = slug.replace("_", " ").title()
            unit: str | None = None
            definition: str | None = None
            aliases: list[str] = []
            if slug in catalog_slugs:
                points.extend(catalog_points[slug])
                source = "catalog"
                unit = KPI_CATALOG[slug].unit_hint
                definition = KPI_CATALOG[slug].description or None
                display_name = (
                    KPI_CATALOG[slug].phrases[0] if KPI_CATALOG[slug].phrases else display_name
                )
            else:
                source = "discovered"
            if slug in discovered_slugs:
                points.extend(per_slug_points[slug])
                if slug not in catalog_slugs:
                    display_name = per_slug_display.get(slug, display_name)
                    unit = per_slug_unit.get(slug)
                    definition = per_slug_definition.get(slug)
                    aliases = per_slug_aliases.get(slug, [])

            points.sort(key=lambda p: p.sort_key, reverse=True)
            aggregates.append(
                CompanyKpiAggregate(
                    slug=slug,
                    display_name=display_name,
                    source=source,
                    unit=unit,
                    definition=definition,
                    aliases=aliases,
                    periods=points,
                )
            )
        # Sort: discovered first (alphabetical), then catalog (alphabetical).
        # Users care most about what this specific company discloses beyond
        # the well-known canon, so surface discovered rows up top.
        aggregates.sort(key=lambda a: (0 if a.source == "discovered" else 1, a.slug))
        return aggregates
    finally:
        learned_reg.close()
        if own_registry:
            pack_registry.close()


def lookup_company_kpi(
    *,
    cik: str,
    slug: str,
    period: str,
    registry_path: Path | None = None,
    pack_registry: PackRegistry | None = None,
) -> CompanyKpiRow | None:
    """Resolve a single (cik, slug, period) to a persisted CompanyKpiRow.

    Used by the extended `financials()` resolution order so
    `edgarpack query FIG paid_seats --period lfy` works without a second
    LLM pass: the row must already be in the company_kpis cache.

    Period mapping:
      lfy   -> most recent row from a 10-K filing
      mrq   -> most recent row from a 10-Q filing
      mrp / ltm -> most recent row from any form
    Unknown period -> most recent row from any form (best-effort fallback).
    """
    own_registry = False
    if pack_registry is None:
        pack_registry = PackRegistry()
        own_registry = True
    learned_reg = LearnedRegistry(db_path=registry_path)
    try:
        rows = learned_reg.company_kpi_list(cik=cik, slug=slug)
        if not rows:
            return None

        p = period.strip().lower()
        if p == "lfy":
            filtered = [r for r in rows if (r.form_type or "").upper().startswith("10-K")]
        elif p == "mrq":
            filtered = [r for r in rows if (r.form_type or "").upper().startswith("10-Q")]
        else:
            filtered = list(rows)

        if not filtered:
            filtered = list(rows)

        filtered.sort(key=lambda r: (r.period_end or "", r.extracted_at), reverse=True)
        return filtered[0]
    finally:
        learned_reg.close()
        if own_registry:
            pack_registry.close()


__all__ = [
    "CompanyKpiAggregate",
    "DiscoveryDiagnostics",
    "DiscoveryProgressEvent",
    "PeriodPoint",
    "discover_kpis",
    "lookup_company_kpi",
]
