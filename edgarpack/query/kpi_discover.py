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

import hashlib
import json
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any

from ..harvest.registry import PackRecord, PackRegistry
from ..sec.submissions import is_registration_form
from .kpi_extract import (
    _DISCOVERY_VERSION,
    KPI_CATALOG,
    DiscoveredKpi,
    _load_pack_manifest,
    _resolve_period_end,
    extract_discoveries_detailed,
)
from .learned_registry import CompanyKpiRow, LearnedRegistry

logger = logging.getLogger(__name__)


def _filter_eligible_packs(packs: Iterable[PackRecord]) -> list[PackRecord]:
    out: list[PackRecord] = []
    for p in packs:
        ft = (getattr(p, "form_type", "") or "").upper()
        if ft.startswith(("10-K", "10-Q", "20-F")) or is_registration_form(ft):
            out.append(p)
    return out


# Public alias for tests.
_filter_eligible_packs_for_test = _filter_eligible_packs


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
    contributing_packs: int = 0
    filings: list[DiscoveryFilingStatus] = field(default_factory=list)

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
class DiscoveryFilingStatus:
    """Per-filing outcome for a `which` discovery pass."""

    accession: str
    form_type: str
    filing_date: str
    status: str
    contributed: bool
    candidate_count: int = 0
    model_attempts: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    retryable_failures: int = 0
    retryable: bool = False

    def to_json(self) -> dict[str, object]:
        resume_action: str | None = None
        is_retryable = self.retryable or self.status == "llm_failed"
        if is_retryable:
            resume_action = "rerun_which"
        elif self.status.startswith("manifest_"):
            resume_action = "rebuild_pack"
        return {
            "accession": self.accession,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "status": self.status,
            "contributed": self.contributed,
            "candidate_count": self.candidate_count,
            "model_attempts": self.model_attempts,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "retryable_failures": self.retryable_failures,
            "retryable": is_retryable,
            "resume_action": resume_action,
        }


@dataclass(frozen=True)
class PackDiscoveryResult:
    """Result of attempting discovery for a single filing pack."""

    discovered: list[DiscoveredKpi]
    status: str
    # one of: cached | discovered | manifest_missing | manifest_invalid_json
    #       | manifest_schema_mismatch | manifest_io_error | llm_failed | empty
    candidate_count: int = 0
    model_attempts: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    retryable_failures: int = 0
    retryable: bool = False


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


def _period_no_chunk_reason(point: PeriodPoint) -> dict[str, str] | None:
    """Structured fallback locator for discovered KPI rows without chunk IDs."""
    if point.chunk_id:
        return None
    if point.section_id and point.source_substring:
        return {
            "reason": "section_excerpt_fallback",
            "section_id": point.section_id,
            "source_substring": point.source_substring,
        }
    if point.source_substring:
        return {
            "reason": "source_substring_only",
            "source_substring": point.source_substring,
        }
    if point.section_id:
        return {
            "reason": "section_only",
            "section_id": point.section_id,
        }
    return {"reason": "locator_missing"}


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

    def _period_to_json(self, point: PeriodPoint) -> dict[str, object]:
        payload: dict[str, object] = {
            "label": point.label,
            "period_end": point.period_end,
            "fiscal_year": point.fiscal_year,
            "fiscal_period": point.fiscal_period,
            "form_type": point.form_type,
            "accession": point.accession,
            "value": point.value,
            "unit": point.unit,
            "magnitude": point.magnitude,
            "section_id": point.section_id,
            "chunk_id": point.chunk_id,
            "source_substring": point.source_substring,
        }
        if point.source_substring or point.section_id:
            reason = _period_no_chunk_reason(point)
            if reason is not None:
                payload["no_chunk_reason"] = reason
        return payload

    def to_json(self) -> dict[str, Any]:
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
            "periods": [self._period_to_json(point) for point in self.periods],
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


def _pack_fingerprint(pack_record: PackRecord, manifest: dict[str, Any]) -> str:
    """Stable fingerprint for versioned discovery cache invalidation."""
    sections = manifest.get("sections", []) if isinstance(manifest, dict) else []
    section_fingerprints: list[object] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_fingerprints.append(
                {
                    "id": section.get("id"),
                    "path": section.get("path"),
                    "sha256": section.get("sha256"),
                    "char_start": section.get("char_start"),
                    "char_end": section.get("char_end"),
                }
            )
    payload = {
        "accession": pack_record.accession,
        "built_at": pack_record.built_at,
        "schema_version": manifest.get("schema_version") if isinstance(manifest, dict) else None,
        "parser_version": manifest.get("parser_version") if isinstance(manifest, dict) else None,
        "sections": section_fingerprints,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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

    run_exists = learned_reg.company_kpi_discovery_run_exists(
        cik=cik,
        accession=accession,
        discovery_version=_DISCOVERY_VERSION,
    )
    if not force and not run_exists and learned_reg.company_kpi_has_accession(cik, accession):
        # Legacy pre-staged cache rows did not have discovery run metadata, so
        # preserve the old behavior: cache hits do not need the pack directory
        # to still be readable.
        cached_rows = learned_reg.company_kpi_list(cik=cik, accession=accession)
        if not cached_rows:
            return PackDiscoveryResult(discovered=[], status="empty")
        return PackDiscoveryResult(
            discovered=[_cached_row_to_discovered(row) for row in cached_rows],
            status="cached",
            accepted_rows=len(cached_rows),
        )

    pack_dir = Path(pack_record.pack_dir)
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        logger.info("Discovery: manifest.json missing at %s (accn=%s)", pack_dir, accession)
        return PackDiscoveryResult(discovered=[], status="manifest_missing")
    try:
        manifest = _load_pack_manifest(pack_dir)
    except json.JSONDecodeError as e:
        logger.info("Discovery: invalid JSON manifest at %s (accn=%s): %s", pack_dir, accession, e)
        return PackDiscoveryResult(discovered=[], status="manifest_invalid_json")
    except (OSError, UnicodeDecodeError) as e:
        logger.info("Discovery: manifest I/O error at %s (accn=%s): %s", pack_dir, accession, e)
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

    pack_fingerprint = _pack_fingerprint(pack_record, manifest)
    if not force and learned_reg.company_kpi_discovery_run_is_complete(
        cik=cik,
        accession=accession,
        discovery_version=_DISCOVERY_VERSION,
        pack_fingerprint=pack_fingerprint,
    ):
        cached_rows = learned_reg.company_kpi_list(cik=cik, accession=accession)
        if not cached_rows:
            return PackDiscoveryResult(discovered=[], status="empty")
        return PackDiscoveryResult(
            discovered=[_cached_row_to_discovered(row) for row in cached_rows],
            status="cached",
            accepted_rows=len(cached_rows),
        )

    existing_slugs = learned_reg.company_kpi_distinct_slugs(cik)
    extraction = extract_discoveries_detailed(
        pack_dir=pack_dir,
        pack_record=pack_record,
        manifest=manifest,
        existing_slugs=existing_slugs,
    )
    discovered = extraction.kpis
    learned_reg.company_kpi_candidates_replace(
        cik=cik,
        accession=accession,
        discovery_version=_DISCOVERY_VERSION,
        candidates=extraction.candidate_windows,
    )
    learned_reg.company_kpi_rejections_replace(
        cik=cik,
        accession=accession,
        discovery_version=_DISCOVERY_VERSION,
        rejections=extraction.rejections,
    )

    if force or run_exists:
        # Drop prior rows for this accession before writing fresh ones so a
        # rerun with a different prompt / model doesn't accumulate stale
        # rows next to the new ones.
        learned_reg.company_kpi_clear(cik=cik, accession=accession)

    if not discovered:
        if extraction.status == "no_kpis":
            # Persist a sentinel so the next `which` call doesn't re-invoke the
            # LLM on a filing that genuinely has no qualifying KPIs. Retryable
            # failures never reach this branch.
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
            learned_reg.company_kpi_discovery_run_upsert(
                cik=cik,
                accession=accession,
                discovery_version=_DISCOVERY_VERSION,
                pack_fingerprint=pack_fingerprint,
                locator_status=(
                    "no_candidates" if not extraction.candidate_windows else "candidates"
                ),
                extractor_status=extraction.status,
                reconciler_status="not_needed",
                candidate_count=extraction.candidate_count,
                model_attempts=extraction.model_attempts,
                accepted_rows=0,
                rejected_rows=extraction.rejected_rows,
                retryable_failures=extraction.retryable_failures,
                retryable=False,
                completed=True,
            )
            return PackDiscoveryResult(
                discovered=[],
                status="empty",
                candidate_count=extraction.candidate_count,
                model_attempts=extraction.model_attempts,
                accepted_rows=0,
                rejected_rows=extraction.rejected_rows,
                retryable_failures=extraction.retryable_failures,
            )
        learned_reg.company_kpi_discovery_run_upsert(
            cik=cik,
            accession=accession,
            discovery_version=_DISCOVERY_VERSION,
            pack_fingerprint=pack_fingerprint,
            locator_status="candidates" if extraction.candidate_windows else "no_candidates",
            extractor_status=extraction.status,
            reconciler_status="not_run",
            candidate_count=extraction.candidate_count,
            model_attempts=extraction.model_attempts,
            accepted_rows=0,
            rejected_rows=extraction.rejected_rows,
            retryable_failures=extraction.retryable_failures,
            retryable=True,
            completed=False,
        )
        return PackDiscoveryResult(
            discovered=[],
            status="llm_failed",
            candidate_count=extraction.candidate_count,
            model_attempts=extraction.model_attempts,
            accepted_rows=0,
            rejected_rows=extraction.rejected_rows,
            retryable_failures=extraction.retryable_failures,
            retryable=True,
        )

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
    learned_reg.company_kpi_discovery_run_upsert(
        cik=cik,
        accession=accession,
        discovery_version=_DISCOVERY_VERSION,
        pack_fingerprint=pack_fingerprint,
        locator_status="candidates",
        extractor_status=extraction.status,
        reconciler_status="completed",
        candidate_count=extraction.candidate_count,
        model_attempts=extraction.model_attempts,
        accepted_rows=extraction.accepted_rows,
        rejected_rows=extraction.rejected_rows,
        retryable_failures=extraction.retryable_failures,
        retryable=extraction.retryable,
        completed=not extraction.retryable,
    )
    return PackDiscoveryResult(
        discovered=discovered,
        status="discovered",
        candidate_count=extraction.candidate_count,
        model_attempts=extraction.model_attempts,
        accepted_rows=extraction.accepted_rows,
        rejected_rows=extraction.rejected_rows,
        retryable_failures=extraction.retryable_failures,
        retryable=extraction.retryable,
    )


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
        eligible_packs = _filter_eligible_packs(packs)
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
            usable_kpis = [kpi for kpi in pack_result.discovered if not kpi.slug.startswith("__")]
            if diagnostics is not None:
                contributed = bool(usable_kpis)
                if contributed:
                    diagnostics.contributing_packs += 1
                diagnostics.filings.append(
                    DiscoveryFilingStatus(
                        accession=pack.accession,
                        form_type=pack.form_type,
                        filing_date=pack.filing_date,
                        status=pack_result.status,
                        contributed=contributed,
                        candidate_count=pack_result.candidate_count,
                        model_attempts=pack_result.model_attempts,
                        accepted_rows=pack_result.accepted_rows,
                        rejected_rows=pack_result.rejected_rows,
                        retryable_failures=pack_result.retryable_failures,
                        retryable=pack_result.retryable,
                    )
                )
            for kpi in usable_kpis:
                slug = kpi.slug
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
                    display_aliases = per_slug_aliases.setdefault(slug, [])
                    if (
                        existing_display not in display_aliases
                        and existing_display != kpi.display_name
                    ):
                        display_aliases.append(existing_display)
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
) -> CompanyKpiRow | list[CompanyKpiRow] | None:
    """Resolve (cik, slug, period) to one or more persisted CompanyKpiRows.

    Understands: lfy, lfy-N, mrq, mrq-N, mrp, ltm, ltm-N, annual:N,
    quarterly:N. Scalar selectors return a single ``CompanyKpiRow`` (or
    ``None`` when no row satisfies the filter). Series selectors
    (annual:N, quarterly:N) return ``list[CompanyKpiRow]``, possibly
    empty when the typed filter yields nothing. ``None`` is reserved for
    the unknown-slug / no-rows-at-all case.

    LTM degrades to LFY (and ltm-N to lfy-N). Callers should emit the
    ltm_degraded diagnostic so users see why LTM wasn't computed.
    Unknown selectors fall back to the newest row of any form.
    """
    learned_reg = LearnedRegistry(db_path=registry_path)
    try:
        rows = learned_reg.company_kpi_list(cik=cik, slug=slug)
        if not rows:
            return None

        def _is_annual(r: CompanyKpiRow) -> bool:
            ft = (r.form_type or "").upper()
            return ft.startswith("10-K") or ft in {"20-F", "40-F"}

        def _is_quarterly(r: CompanyKpiRow) -> bool:
            return (r.form_type or "").upper().startswith("10-Q")

        def _sort_key(r: CompanyKpiRow) -> tuple[int, str, str]:
            return (r.fiscal_year or 0, r.period_end or "", r.extracted_at)

        p = period.strip().lower()

        # LTM degrades to LFY before we branch on anything else.
        if p == "ltm":
            p = "lfy"
        elif p.startswith("ltm-"):
            p = "lfy-" + p.split("-", 1)[1]

        if p == "lfy":
            annual = sorted((r for r in rows if _is_annual(r)), key=_sort_key, reverse=True)
            return annual[0] if annual else None

        if p.startswith("lfy-"):
            try:
                n = int(p.split("-", 1)[1])
            except ValueError:
                return None
            annual = sorted((r for r in rows if _is_annual(r)), key=_sort_key, reverse=True)
            return annual[n] if 0 <= n < len(annual) else None

        if p == "mrq":
            q = sorted((r for r in rows if _is_quarterly(r)), key=_sort_key, reverse=True)
            return q[0] if q else None

        if p.startswith("mrq-"):
            try:
                n = int(p.split("-", 1)[1])
            except ValueError:
                return None
            q = sorted((r for r in rows if _is_quarterly(r)), key=_sort_key, reverse=True)
            return q[n] if 0 <= n < len(q) else None

        if p == "mrp":
            all_rows = sorted(rows, key=_sort_key, reverse=True)
            return all_rows[0] if all_rows else None

        if p.startswith("annual:"):
            try:
                n = int(p.split(":", 1)[1])
            except ValueError:
                return None
            annual = sorted((r for r in rows if _is_annual(r)), key=_sort_key, reverse=True)
            return annual[:n]

        if p.startswith("quarterly:"):
            try:
                n = int(p.split(":", 1)[1])
            except ValueError:
                return None
            q = sorted((r for r in rows if _is_quarterly(r)), key=_sort_key, reverse=True)
            return q[:n]

        # Unknown selector: preserve prior most-recent-fallback behavior.
        all_rows = sorted(rows, key=_sort_key, reverse=True)
        return all_rows[0] if all_rows else None
    finally:
        learned_reg.close()


# ---------------------------------------------------------------------------
# Framing-metric extraction (TAM / market size / CAGR)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FramingHit:
    """A market-framing claim (TAM, CAGR, market opportunity) extracted from prose."""

    claim: str
    pattern: str
    offset: int
    metric_kind: str = "framing"


_FRAMING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "tam_dollar",
        re.compile(
            r"(?:total\s+addressable\s+market|TAM)[^.\n]{0,40}?\$[0-9][0-9.,]*\s*(?:billion|million|trillion|B|M|T)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "addressable_market_dollar",
        re.compile(
            r"(?:addressable\s+market)[^.\n]{0,40}?\$[0-9][0-9.,]*\s*(?:billion|million|trillion|B|M|T)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cagr",
        re.compile(
            r"(?:growing|growth|expand(?:ing|s)?)[^.\n]{0,40}?\d{1,3}(?:\.\d+)?\s*%\s*(?:CAGR|compound\s+annual\s+growth)",
            re.IGNORECASE,
        ),
    ),
    (
        "cagr_simple",
        re.compile(
            r"\b\d{1,3}(?:\.\d+)?\s*%\s*CAGR\b",
            re.IGNORECASE,
        ),
    ),
    (
        "dollar_opportunity",
        re.compile(
            r"\$[0-9][0-9.,]*\s*(?:billion|trillion|B|T)\s+(?:market\s+)?opportunity",
            re.IGNORECASE,
        ),
    ),
]


def extract_framing_claims(text: str) -> list[FramingHit]:
    """Scan prose for TAM / market-size / CAGR / opportunity claims."""
    if not text:
        return []
    return [
        FramingHit(claim=m.group(0).strip(), pattern=name, offset=m.start())
        for name, pattern in _FRAMING_PATTERNS
        for m in pattern.finditer(text)
    ]


@dataclass(frozen=True)
class DisclosureHit:
    """An S-1-only disclosure: use of proceeds, dilution, lockup, or principal holder."""

    claim: str
    disclosure_type: str
    offset: int
    metric_kind: str = "s1_disclosure"


_USE_OF_PROCEEDS_ITEM = re.compile(
    r"(?:approximately\s+)?\$[0-9][0-9.,]*\s*(?:billion|million|B|M)\s+for\s+[^.,;]{3,80}",
    re.IGNORECASE,
)

_DILUTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"immediate\s+dilution\s+of\s+\$[0-9][0-9.,]*(?:\s*per\s+share)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"pro\s+forma\s+net\s+tangible\s+book\s+value\s+of\s+\$[0-9][0-9.,]*(?:\s*per\s+share)?",
        re.IGNORECASE,
    ),
]

_LOCKUP_PATTERN = re.compile(
    r"lock\s*[-\s]?up\s+(?:period|agreement)[^.\n]{0,60}?\b(\d{2,4})\s*days\b",
    re.IGNORECASE,
)

_PRINCIPAL_HOLDER_ROW = re.compile(
    r"^(?P<name>[A-Z][\w &.,'\-]{2,80}?)\s{2,}"
    r"(?P<shares>[0-9][0-9,]*)\s{2,}"
    r"(?P<pct>\d{1,3}(?:\.\d+)?)\s*%",
    re.MULTILINE,
)


def _find_disclosures(
    text: str,
    patterns: list[re.Pattern[str]],
    disclosure_type: str,
) -> list[DisclosureHit]:
    if not text:
        return []
    return [
        DisclosureHit(
            claim=m.group(0).strip(),
            disclosure_type=disclosure_type,
            offset=m.start(),
        )
        for pattern in patterns
        for m in pattern.finditer(text)
    ]


def extract_use_of_proceeds(text: str) -> list[DisclosureHit]:
    return _find_disclosures(text, [_USE_OF_PROCEEDS_ITEM], "use_of_proceeds")


def extract_dilution(text: str) -> list[DisclosureHit]:
    return _find_disclosures(text, _DILUTION_PATTERNS, "dilution")


def extract_lockup(text: str) -> list[DisclosureHit]:
    return _find_disclosures(text, [_LOCKUP_PATTERN], "lockup")


def extract_principal_holders(text: str) -> list[DisclosureHit]:
    # Whitespace-permissive on purpose: SEC HTML-to-markdown leaves column
    # tables as space-aligned plaintext rather than pipe-delimited markdown.
    if not text:
        return []
    return [
        DisclosureHit(
            claim=f"{m.group('name').strip()} | {m.group('shares')} shares | {m.group('pct')}%",
            disclosure_type="principal_holder",
            offset=m.start(),
        )
        for m in _PRINCIPAL_HOLDER_ROW.finditer(text)
    ]


def _section_scoped_text(
    pack_dir: Path,
    *,
    name_fragments: tuple[str, ...],
    fallback: str,
) -> str:
    """Read matching section markdown when available, else return full filing text."""
    sections_dir = pack_dir / "sections"
    if not sections_dir.exists():
        return fallback

    selected: list[str] = []
    for section_path in sorted(sections_dir.glob("*.md")):
        section_name = section_path.name.lower()
        if not any(fragment in section_name for fragment in name_fragments):
            continue
        try:
            selected.append(section_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n\n".join(selected) if selected else fallback


@dataclass(frozen=True)
class S1MetricsBundle:
    """All S-1-specific extractor output for one registration-class pack.

    Wraps the five text extractors (framing + four disclosure kinds) behind a
    single entry point so callers don't have to re-read pack markdown per kind.
    """

    accession: str
    form_type: str
    framing: list[FramingHit]
    use_of_proceeds: list[DisclosureHit]
    dilution: list[DisclosureHit]
    lockup: list[DisclosureHit]
    principal_holders: list[DisclosureHit]

    @property
    def total_hits(self) -> int:
        return (
            len(self.framing)
            + len(self.use_of_proceeds)
            + len(self.dilution)
            + len(self.lockup)
            + len(self.principal_holders)
        )


def extract_s1_metrics_from_pack(pack_dir: Path) -> S1MetricsBundle | None:
    """Run all five S-1 extractors over the most relevant pack sections.

    Returns None when the pack is not registration-class (so callers can
    drop it from an aggregation pass) or when `filing.full.md` is missing.
    """
    pack_dir = Path(pack_dir)
    manifest_path = pack_dir / "manifest.json"
    markdown_path = pack_dir / "filing.full.md"
    if not manifest_path.exists() or not markdown_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    filing = manifest.get("filing") or {}
    form_type = str(filing.get("form_type", ""))
    from ..sec.submissions import is_registration_form

    if not is_registration_form(form_type):
        return None

    text = markdown_path.read_text(encoding="utf-8", errors="replace")
    framing_text = _section_scoped_text(
        pack_dir,
        name_fragments=("prospectus_summary", "summary", "business"),
        fallback=text,
    )
    use_of_proceeds_text = _section_scoped_text(
        pack_dir,
        name_fragments=("use_of_proceeds",),
        fallback=text,
    )
    dilution_text = _section_scoped_text(
        pack_dir,
        name_fragments=("dilution",),
        fallback=text,
    )
    lockup_text = _section_scoped_text(
        pack_dir,
        name_fragments=("underwriting", "lockup", "shares_eligible"),
        fallback=text,
    )
    principal_holders_text = _section_scoped_text(
        pack_dir,
        name_fragments=("principal_stock", "principal_share", "security_ownership"),
        fallback=text,
    )
    return S1MetricsBundle(
        accession=str(filing.get("accession", "")),
        form_type=form_type,
        framing=extract_framing_claims(framing_text),
        use_of_proceeds=extract_use_of_proceeds(use_of_proceeds_text),
        dilution=extract_dilution(dilution_text),
        lockup=extract_lockup(lockup_text),
        principal_holders=extract_principal_holders(principal_holders_text),
    )


__all__ = [
    "CompanyKpiAggregate",
    "DisclosureHit",
    "DiscoveryDiagnostics",
    "DiscoveryProgressEvent",
    "FramingHit",
    "PeriodPoint",
    "S1MetricsBundle",
    "discover_kpis",
    "extract_dilution",
    "extract_framing_claims",
    "extract_lockup",
    "extract_principal_holders",
    "extract_s1_metrics_from_pack",
    "extract_use_of_proceeds",
    "lookup_company_kpi",
]
