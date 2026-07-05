"""Single-company financial queries with full citation provenance."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date as _date
from datetime import datetime as _datetime
from pathlib import Path
from typing import Any, cast

from ..config import DEFAULT_PACKS_DIR
from ..sec.archives import fetch_file
from ..sec.client import HTTPError
from ..sec.submissions import FilingMeta, fetch_submissions
from ..sec.tickers import resolve_ticker
from ..sec.xbrl import XBRLFetchError, fetch_company_facts
from . import kpi_extract as _kpi_extract_mod
from .concepts import (
    ALL_METRICS,
    METRIC_MAP,
    MetricMeta,
    _normalize_component,
    get_scope_warning,
    resolve_concept,
)
from .formula import eval_formula
from .kpi_discover import lookup_company_kpi
from .kpi_extract import KPI_CATALOG
from .layer_zero import MetricNotFound, resolve_alias, suggest_metrics
from .learned_registry import CompanyKpiRow, LearnedRegistry
from .metric_map import AccountingStandard
from .models import CitedValue, DerivedValue, Diagnostic, MetricScalar, MetricValue, QueryResult
from .periods import (
    _annual_for_fy,
    _extract_values,
    _unit_for_concept,
    _value_to_cited,
    parse_fact_ids_from_html,
    select_period,
)
from .self_heal import try_learn

logger = logging.getLogger(__name__)

_DerivedCache = dict[str, CitedValue | None]
_SERIES_PERIOD_RE = re.compile(r"^(annual|quarterly):(\d+)$")


def _requested_metrics_list(metrics: str | list[str] | None) -> list[str]:
    if metrics is None:
        return []
    if isinstance(metrics, str):
        return [m.strip() for m in metrics.split(",") if m.strip()]
    return list(metrics)


# Staleness thresholds: max fiscal-year gap (current_year - fy) before
# a value is rejected as stale.  Series queries ("annual:N", "quarterly:N")
# and explicit offset selectors (``lfy-N``, ``ltm-N``, ``mrq-N`` for N>=1)
# skip the check entirely since the caller explicitly asks for history.
_STALENESS_YEARS: dict[str, int] = {}
_STALENESS_DEFAULT = 2
_OFFSET_PERIOD_RE = re.compile(r"^(lfy|ltm|mrq)-(\d+)$")


def _staleness_limit(period: str) -> int:
    """Max fiscal-year age before a value is rejected as stale."""
    p = period.strip().lower()
    if p.startswith("annual:") or p.startswith("quarterly:"):
        return 999
    m = _OFFSET_PERIOD_RE.match(p)
    if m and int(m.group(2)) >= 1:
        return 999
    return _STALENESS_YEARS.get(p, _STALENESS_DEFAULT)


def _is_stale(cited: CitedValue, period: str) -> bool:
    """True when a CitedValue's fiscal year is too far behind the current year."""
    limit = _staleness_limit(period)
    if limit >= 999:
        return False
    return cited.fiscal_year < _date.today().year - limit


def _stale_rejected_diagnostic(metric: str, cited: CitedValue, period: str) -> Diagnostic:
    return Diagnostic(
        metric=metric,
        kind="stale_rejected",
        message=(
            f"{metric} resolved to FY{cited.fiscal_year}, more than "
            f"{_staleness_limit(period)} years behind {_date.today().year}; "
            f"rejected as stale for period '{period}'."
        ),
    )


def _series_period(period: str) -> tuple[str, int] | None:
    """Return (kind, count) for annual:N / quarterly:N selectors."""
    match = _SERIES_PERIOD_RE.fullmatch(period.strip().lower())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def _period_alignment_key(cited: CitedValue) -> tuple[int, str, _date | None]:
    """Key used to ensure derived components describe the same reporting window."""
    return cited.fiscal_year, cited.fiscal_period.upper(), cited.period_end


def _discovered_slugs_for_cik(cik: str) -> set[str]:
    """Return every discovered slug the company_kpis cache has for this CIK.

    Used as the third tier of the unknown-metric guard so a query like
    `edgarpack query FIG paid_seats --period lfy` doesn't fail
    MetricNotFound before even trying the discovered path. Empty set when
    no discovery pass has run or the registry lookup fails.
    """
    reg = LearnedRegistry()
    try:
        return set(reg.company_kpi_distinct_slugs(cik))
    except Exception:  # pragma: no cover - registry DB should always open
        return set()
    finally:
        reg.close()


def _apply_magnitude(value: float | None, magnitude: str | None) -> float | None:
    """Expand a magnitude hint into base units.

    The `which` discovery pass stores values with an associated magnitude
    (e.g. value=3.44 magnitude='billions'). `financials()` consumers expect
    base units, so expand before returning.
    """
    if value is None:
        return None
    if magnitude == "thousands":
        return value * 1_000.0
    if magnitude == "millions":
        return value * 1_000_000.0
    if magnitude == "billions":
        return value * 1_000_000_000.0
    return value


def _cited_from_company_kpi_row(
    row: CompanyKpiRow,
    *,
    cik: str,
    company: str,
) -> CitedValue:
    """Turn a stored CompanyKpiRow into a CitedValue query consumers expect.

    `concept` is set to the display_name (or slug) since there's no XBRL
    concept behind a discovered metric. `source='learned:kpi-discovered'`
    distinguishes these rows from catalog Layer B hits so downstream
    renderers can flag them. `excerpt_text` is the verbatim source
    substring (populates document_url's text-fragment anchor).
    """
    try:
        period_end = _date.fromisoformat(row.period_end) if row.period_end else _date.min
    except ValueError:
        period_end = _date.min
    try:
        extracted_iso = row.extracted_at.split("T", 1)[0] if row.extracted_at else ""
        filed = _date.fromisoformat(extracted_iso) if extracted_iso else _date.min
    except ValueError:
        filed = _date.min

    expanded_value = _apply_magnitude(row.value, row.magnitude)
    unit = row.unit or "pure"

    return CitedValue(
        value=expanded_value,
        unit=unit,
        metric=row.slug,
        concept=row.display_name or row.slug,
        period_end=period_end,
        fiscal_year=row.fiscal_year,
        fiscal_period=row.fiscal_period,
        form_type=row.form_type or "",
        filed=filed,
        accession=row.accession,
        cik=cik,
        company=company,
        taxonomy="kpi-discovered",
        primary_document="",
        fact_id="",
        excerpt_text=row.source_substring or "",
        source="learned:kpi-discovered",
    )


async def _build_doc_map(cik: str, force: bool = False) -> dict[str, str]:
    """Build {accession: primaryDocument} from submissions (cached 1hr).

    On known transient failures (network, HTTP, malformed JSON) returns an
    empty dict and logs a warning so downstream anchor_url falls back to the
    document URL. Unknown exceptions bubble up.
    """
    try:
        data = await fetch_submissions(cik, force=force)
    except (HTTPError, OSError, ValueError) as e:
        logger.warning("submissions fetch failed for CIK %s: %s", cik, e)
        return {}

    filings = data.get("filings", {}).get("recent", {})
    accessions = filings.get("accessionNumber", [])
    docs = filings.get("primaryDocument", [])

    doc_map: dict[str, str] = {}
    for acc, doc in zip(accessions, docs):
        if acc and doc:
            doc_map[acc] = doc
    return doc_map


async def _fetch_fact_id_maps(
    cik: str,
    doc_map: dict[str, str],
    accessions: set[str],
) -> dict[str, dict[tuple[str, float], str]]:
    """Fetch filing HTML and parse fact IDs for each accession.

    Returns ``{accession: {(concept, value): fact_id}}``.
    One HTTP request per unique accession (cached by ``fetch_file``).
    """
    result: dict[str, dict[tuple[str, float], str]] = {}
    cik_bare = cik.lstrip("0")

    async def _fetch_one(accn: str) -> None:
        primary_doc = doc_map.get(accn, "")
        if not primary_doc:
            return
        meta = FilingMeta(
            cik=cik_bare,
            accession=accn,
            form_type="",
            filing_date=_date.min,
            primary_document=primary_doc,
            company_name="",
        )
        try:
            html_bytes = await fetch_file(meta, primary_doc)
            result[accn] = parse_fact_ids_from_html(html_bytes)
        except (HTTPError, OSError, ValueError) as e:
            # anchor_url falls back to document_url; log so the degradation is visible.
            logger.warning("fact_id map fetch failed for %s: %s", accn, e)

    await asyncio.gather(*[_fetch_one(accn) for accn in accessions])
    return result


def _collect_accessions(result: QueryResult) -> set[str]:
    """Collect all unique accession numbers from a QueryResult."""
    accessions: set[str] = set()
    for v in result.metrics.values():
        if v is None:
            continue
        items = v if isinstance(v, list) else [v]
        for item in items:
            if item.accession:
                accessions.add(item.accession)
            if isinstance(item, DerivedValue):
                for comp in item.components.values():
                    if comp.accession:
                        accessions.add(comp.accession)
    return accessions


def _enrich_fact_ids(
    result: QueryResult,
    fact_id_maps: dict[str, dict[tuple[str, float], str]],
) -> None:
    """Populate ``fact_id`` on all CitedValues in-place using parsed maps."""
    from .periods import _lookup_fact_id

    def _enrich_one(cited: CitedValue) -> None:
        if cited.fact_id:
            return  # Already set
        fmap = fact_id_maps.get(cited.accession)
        if fmap:
            cited.fact_id = _lookup_fact_id(fmap, cited.concept, cited.value)

    for v in result.metrics.values():
        if v is None:
            continue
        items = v if isinstance(v, list) else [v]
        for item in items:
            _enrich_one(item)
            if isinstance(item, DerivedValue):
                for comp in item.components.values():
                    _enrich_one(comp)


def _candidate_concepts_for_metric(
    metric: str,
    meta: MetricMeta,
    facts: dict[str, Any],
) -> list[tuple[str, str]]:
    """Return hardcoded concepts present in facts, ordered by current resolver priority."""
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    resolved = resolve_concept(metric, facts)
    if resolved is not None:
        candidates.append(resolved)
        seen.add(resolved)

    for taxonomy, concepts in (
        ("us-gaap", meta.concepts),
        (
            "ifrs-full",
            meta.ifrs_concepts + meta.concepts if meta.ifrs_concepts else meta.concepts,
        ),
    ):
        tax_data = facts.get(taxonomy, {})
        if not isinstance(tax_data, dict):
            continue
        for concept in concepts:
            key = (concept, taxonomy)
            if key in seen or concept not in tax_data:
                continue
            candidates.append(key)
            seen.add(key)

    return candidates


_ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "ANNUAL-REPORT", "ANNUAL REPORT"}


def _company_latest_annual_fy(facts: dict[str, Any]) -> int | None:
    """Best company-level FY anchor for exact lfy/annual period matching."""
    best: int | None = None
    for tax_data in facts.values():
        if not isinstance(tax_data, dict):
            continue
        for concept_data in tax_data.values():
            if not isinstance(concept_data, dict):
                continue
            units = concept_data.get("units", {})
            if not isinstance(units, dict):
                continue
            for entries in units.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict) or entry.get("val") is None:
                        continue
                    fp = str(entry.get("fp", "")).upper()
                    form = str(entry.get("form", "")).upper()
                    if fp != "FY" and form not in _ANNUAL_FORMS:
                        continue
                    fy = int(entry.get("fy") or 0)
                    if fy > 0 and (best is None or fy > best):
                        best = fy
    return best


def _expected_fiscal_years(
    facts: dict[str, Any],
    period: str,
    period_offset: int = 0,
) -> tuple[int, ...] | None:
    """Return exact fiscal years a company-level FY selector is allowed to satisfy."""
    anchor = _company_latest_annual_fy(facts)
    if anchor is None:
        return None

    p = period.strip().lower()

    def _effective_back(years_back: int) -> int:
        return max(0, years_back - period_offset)

    if p == "lfy":
        return (anchor - _effective_back(0),)

    lfy_match = re.fullmatch(r"lfy-(\d+)", p)
    if lfy_match:
        return (anchor - _effective_back(int(lfy_match.group(1))),)

    annual_match = re.fullmatch(r"annual:(\d+)", p)
    if annual_match:
        count = int(annual_match.group(1))
        return tuple(anchor - _effective_back(idx) for idx in range(count))

    return None


def _filter_to_expected_fiscal_years(
    value: CitedValue | DerivedValue | list[CitedValue] | None,
    *,
    facts: dict[str, Any],
    metric: str,
    concept: str,
    period: str,
    period_offset: int,
    diagnostics: list[Diagnostic],
) -> CitedValue | DerivedValue | list[CitedValue] | None:
    expected = _expected_fiscal_years(facts, period, period_offset)
    if value is None or expected is None:
        return value

    if isinstance(value, list):
        by_fy: dict[int, CitedValue] = {}
        for item in value:
            if item.fiscal_year in expected and item.fiscal_year not in by_fy:
                by_fy[item.fiscal_year] = item
        filtered = [by_fy[fy] for fy in expected if fy in by_fy]
        if len(filtered) < len(expected):
            missing = [fy for fy in expected if fy not in by_fy]
            diagnostics.append(
                Diagnostic(
                    metric=metric,
                    kind="period_mismatch",
                    message=(
                        f"{metric} concept {concept} did not have exact fiscal-year "
                        f"coverage for {period}; missing FY{', FY'.join(map(str, missing))}."
                    ),
                )
            )
        return filtered

    if value.fiscal_year != expected[0]:
        diagnostics.append(
            Diagnostic(
                metric=metric,
                kind="period_mismatch",
                message=(
                    f"{metric} concept {concept} returned FY{value.fiscal_year} for "
                    f"{period}, expected FY{expected[0]}; rejecting nearest-period value."
                ),
            )
        )
        return None

    return value


def _select_exact_annual_values_for_concept(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    company: str,
    cik: str,
    taxonomy: str,
    doc_map: dict[str, str] | None,
    expected: tuple[int, ...],
) -> list[CitedValue]:
    values = _extract_values(facts, concept, taxonomy=taxonomy)
    unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)
    cited_values: list[CitedValue] = []
    for fiscal_year in expected:
        entry = _annual_for_fy(values, fiscal_year)
        if entry is None:
            continue
        cited_values.append(
            _value_to_cited(
                entry,
                metric,
                concept,
                unit,
                company,
                cik,
                taxonomy=taxonomy,
                doc_map=doc_map,
            )
        )
    return cited_values


def _select_metric_period_value(
    facts: dict[str, Any],
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    period: str,
    doc_map: dict[str, str] | None,
    diagnostics: list[Diagnostic],
    period_offset: int = 0,
) -> tuple[str | None, str | None, MetricValue]:
    """Resolve a metric only when a candidate concept satisfies the requested period."""
    candidates = _candidate_concepts_for_metric(metric, meta, facts)
    first_failure_diagnostics: list[Diagnostic] = []
    expected = _expected_fiscal_years(facts, period, period_offset)
    merge_annual_series = expected is not None and period.strip().lower().startswith("annual:")
    merged_by_fy: dict[int, CitedValue] = {}

    for concept, taxonomy in candidates:
        local_diagnostics: list[Diagnostic] = []
        if expected is not None:
            exact_values = _select_exact_annual_values_for_concept(
                facts,
                concept,
                metric,
                company,
                cik,
                taxonomy,
                doc_map,
                expected,
            )
            if exact_values:
                value: MetricValue = exact_values if merge_annual_series else exact_values[0]
            else:
                value = [] if merge_annual_series else None
                local_diagnostics.append(
                    Diagnostic(
                        metric=metric,
                        kind="period_mismatch",
                        message=(
                            f"{metric} concept {concept} did not have exact fiscal-year "
                            f"coverage for {period}; missing FY"
                            f"{', FY'.join(map(str, expected))}."
                        ),
                    )
                )
        else:
            raw_value = select_period(
                facts,
                concept,
                metric,
                meta,
                company,
                cik,
                period,
                taxonomy=taxonomy,
                doc_map=doc_map,
                period_offset=period_offset,
                diagnostics=local_diagnostics,
            )
            value = _filter_to_expected_fiscal_years(
                raw_value,
                facts=facts,
                metric=metric,
                concept=concept,
                period=period,
                period_offset=period_offset,
                diagnostics=local_diagnostics,
            )
        if isinstance(value, list):
            if value:
                if merge_annual_series:
                    assert expected is not None
                    for item in value:
                        if item.fiscal_year in expected and item.fiscal_year not in merged_by_fy:
                            merged_by_fy[item.fiscal_year] = item
                    if len(merged_by_fy) >= len(expected):
                        merged = [merged_by_fy[fy] for fy in expected]
                        return merged[0].concept, merged[0].taxonomy, merged
                elif expected is None or len(value) >= len(expected):
                    diagnostics.extend(local_diagnostics)
                    return concept, taxonomy, value
        elif value is not None and merge_annual_series:
            assert expected is not None
            if value.fiscal_year in expected and value.fiscal_year not in merged_by_fy:
                merged_by_fy[value.fiscal_year] = value
            if len(merged_by_fy) >= len(expected):
                merged = [merged_by_fy[fy] for fy in expected]
                return merged[0].concept, merged[0].taxonomy, merged
        elif value is not None:
            diagnostics.extend(local_diagnostics)
            return concept, taxonomy, value

        if not first_failure_diagnostics:
            first_failure_diagnostics = local_diagnostics

    if merge_annual_series and merged_by_fy:
        assert expected is not None
        values = [merged_by_fy[fy] for fy in expected if fy in merged_by_fy]
        missing = [fy for fy in expected if fy not in merged_by_fy]
        if missing:
            diagnostics.append(
                Diagnostic(
                    metric=metric,
                    kind="period_mismatch",
                    message=(
                        f"{metric} candidate concepts did not have exact fiscal-year "
                        f"coverage for {period}; missing FY{', FY'.join(map(str, missing))}."
                    ),
                )
            )
        return values[0].concept, values[0].taxonomy, values

    diagnostics.extend(first_failure_diagnostics)
    if candidates:
        concept, taxonomy = candidates[0]
        return concept, taxonomy, None
    return None, None, None


def _attach_scope_warning(
    value: MetricValue,
    concept: str,
) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            scope_warn = get_scope_warning(item.concept)
            if scope_warn:
                item.warnings.append(scope_warn)
        return

    scope_warn = get_scope_warning(concept)
    if not scope_warn:
        return
    value.warnings.append(scope_warn)


def _resolve_direct_metric_value(
    facts: dict[str, Any],
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    period: str,
    doc_map: dict[str, str] | None,
    diagnostics: list[Diagnostic],
    period_offset: int = 0,
) -> MetricValue:
    """Resolve one non-derived metric through hardcoded and guarded learned paths."""
    concept, taxonomy, value = _select_metric_period_value(
        facts,
        metric,
        meta,
        company,
        cik,
        period,
        doc_map,
        diagnostics,
        period_offset=period_offset,
    )
    if concept is None or taxonomy is None:
        learned = try_learn(
            metric=metric,
            meta=meta,
            facts=facts,
            cik=cik,
            company=company,
            doc_map=doc_map,
            period=period,
            period_offset=period_offset,
            diagnostics=diagnostics,
        )
        if learned is None:
            return None

        learned_concept = learned[0].concept if isinstance(learned, list) else learned.concept
        learned = _filter_to_expected_fiscal_years(
            learned,
            facts=facts,
            metric=metric,
            concept=learned_concept,
            period=period,
            period_offset=period_offset,
            diagnostics=diagnostics,
        )
        if learned is None:
            return None

        _attach_scope_warning(learned, learned_concept)
        return learned

    if value is None:
        return None

    _attach_scope_warning(value, concept)
    return value


async def financials(
    company: str,
    metrics: str | list[str] | None = None,
    period: str = "lfy",
    force: bool = False,
    display_token: str | None = None,
    pack_root: Path | None = None,
) -> QueryResult:
    """Query financial metrics for a single company.

    Args:
        company: Ticker symbol ("NVDA"), CIK number ("1045810"), or
                 company name ("NVIDIA"). Resolution falls back to a
                 fuzzy name match across the SEC ticker list.
        metrics: Metric name(s). String for single, list for multiple,
                 None for all available metrics.
        period: Period selector. Scalars: "lfy", "mrq", "ltm", "mrp",
                and offset forms "lfy-N", "mrq-N", "ltm-N" (N >= 1).
                "mrp" does not take an offset. Series: "annual:N",
                "quarterly:N". The CLI additionally accepts a
                comma-separated list of scalars to render a multi-period
                grid; callers of this function should pre-parse that with
                ``parse_period_spec`` and dispatch per selector.
        force: Bypass the on-disk cache for SEC lookups.

    Returns:
        QueryResult with cited values for each requested metric.
    """
    from pathlib import Path as _Path

    from .. import identity as _identity

    _universe_path = _Path("universe.toml")
    if _universe_path.exists():
        try:
            _idx = _identity.load_identity(_universe_path)
        except Exception as _e:
            # A malformed universe should not silently disable HKEX routing;
            # log and continue so the SEC path still works.
            logger.warning("universe.toml unreadable, skipping HKEX pre-pass: %s", _e)
        else:
            _resolved_id = None
            try:
                _resolved_id = _identity.resolve(_idx, ticker=company, company=None)
            except _identity.UnknownCompany:
                try:
                    _resolved_id = _identity.resolve(_idx, ticker=None, company=company)
                except _identity.UnknownCompany:
                    pass
            if _resolved_id is not None and _resolved_id.source in {"HKEX", "SSE"}:
                return await _query_china_pack(
                    _resolved_id,
                    metrics,
                    period,
                    display_token=display_token,
                    pack_root=pack_root,
                )
            if _resolved_id is not None and _resolved_id.source == "SEC":
                company = _resolved_id.ticker

    if _identity.looks_like_china_a_share_code(company):
        resolved_code = _identity.ResolvedCompany(
            ticker=company.strip(),
            listing="SSE",
            source="SSE",
            cik=None,
            hk_stock_code=None,
            stock_code=company.strip(),
            aliases=(),
            private=False,
        )
        return await _query_china_pack(
            resolved_code,
            metrics,
            period,
            display_token=display_token,
            pack_root=pack_root,
        )

    try:
        cik, company_name = await resolve_ticker(company, force=force)
    except _identity.UnknownCompany:
        # Fallback for pre-IPO filers: not in company_tickers.json.
        from ..sec.tickers import resolve_company_by_name as _resolve_by_name

        cik, company_name = await _resolve_by_name(company)

    fetch_error_message: str | None = None
    try:
        facts_data = await fetch_company_facts(cik, force=force)
    except XBRLFetchError as e:
        facts_data = {}
        fetch_error_message = f"SEC XBRL fetch failed: {e.cause!r}"
    facts = facts_data.get("facts", {})

    doc_map = await _build_doc_map(cik, force=force)

    pack_root_path = Path(pack_root) if pack_root is not None else DEFAULT_PACKS_DIR
    if metrics is None:
        from .s1_financials import (
            default_registration_query_metrics,
            has_registration_pack_for_cik,
        )

        if has_registration_pack_for_cik(cik, pack_root_path):
            metric_list = default_registration_query_metrics()
        else:
            metric_list = list(ALL_METRICS)
    elif isinstance(metrics, str):
        metric_list = [m.strip() for m in metrics.split(",")]
    else:
        metric_list = list(metrics)

    # Layer 0: alias dereferencing + unknown-metric guard.
    # Resolution order: METRIC_MAP -> KPI_CATALOG -> company_kpis
    # (company-specific discovered slugs, populated by `edgarpack which`).
    # S-1 snapshot slugs are also accepted; they pass through the guard and
    # resolve via augment_with_s1_snapshot at the end of the function.
    from .s1_financials import METRIC_SLUGS as _S1_METRIC_SLUGS

    discovered_slugs = _discovered_slugs_for_cik(cik)
    resolved_list: list[str] = []
    for m in metric_list:
        resolved = resolve_alias(m)
        if (
            resolved not in METRIC_MAP
            and resolved not in KPI_CATALOG
            and resolved not in discovered_slugs
            and resolved not in _S1_METRIC_SLUGS
        ):
            combined_known = (
                set(METRIC_MAP.keys())
                | set(KPI_CATALOG.keys())
                | discovered_slugs
                | _S1_METRIC_SLUGS
            )
            suggestions = suggest_metrics(resolved, combined_known, n=3)
            raise MetricNotFound(m, suggestions=suggestions)
        resolved_list.append(resolved)
    metric_list = resolved_list

    result_metrics: dict[str, MetricValue] = {}
    derived_cache: _DerivedCache = {}
    diagnostics_list: list[Diagnostic] = []

    for metric in metric_list:
        meta = METRIC_MAP.get(metric)
        if meta is None:
            if metric in KPI_CATALOG:
                # KPI-only metric (in KPI_CATALOG but not METRIC_MAP).
                # Layer B extracts these from the pack's MD&A/segment sections.
                cited = _kpi_extract_mod.try_extract_kpi(
                    metric=metric,
                    cik=cik,
                    company=company_name,
                    period=period,
                )
                if cited is not None:
                    result_metrics[metric] = cited
                else:
                    result_metrics[metric] = None
                    diagnostics_list.append(
                        Diagnostic(
                            metric=metric,
                            kind="layer_b_unresolved",
                            message=(
                                f"Layer B could not resolve '{metric}': no pack, "
                                f"no LLM backend, or the value was not found in "
                                f"MD&A/segment sections."
                            ),
                        )
                    )
                continue

            if metric in _S1_METRIC_SLUGS:
                result_metrics[metric] = None
                continue

            # Company-specific discovered KPI (populated by `edgarpack which`).
            # Resolves against the cached company_kpis rows; no LLM call.
            p_lower = period.strip().lower()
            looked_up = lookup_company_kpi(cik=cik, slug=metric, period=period)
            if looked_up is None:
                result_metrics[metric] = None
                diagnostics_list.append(
                    Diagnostic(
                        metric=metric,
                        kind="layer_b_unresolved",
                        message=(
                            f"Discovered KPI '{metric}' has no cached row for "
                            f"period '{period}'. Run `edgarpack which "
                            f"{cik}` to refresh discovery, or check the "
                            f"period against what's available."
                        ),
                    )
                )
            elif isinstance(looked_up, list):
                cited_list = [
                    _cited_from_company_kpi_row(row, cik=cik, company=company_name)
                    for row in looked_up
                ]
                result_metrics[metric] = cited_list
                # Partial-coverage diagnostic for series selectors.
                if p_lower.startswith("annual:") or p_lower.startswith("quarterly:"):
                    try:
                        requested = int(p_lower.split(":", 1)[1])
                    except ValueError:
                        requested = 0
                    if 0 < len(cited_list) < requested:
                        earliest = cited_list[-1].fiscal_year
                        diagnostics_list.append(
                            Diagnostic(
                                metric=metric,
                                kind="partial_coverage",
                                message=(
                                    f"Only {len(cited_list)} of {requested} "
                                    f"requested periods available for "
                                    f"'{metric}'; earliest is FY{earliest}."
                                ),
                            )
                        )
            else:
                result_metrics[metric] = _cited_from_company_kpi_row(
                    looked_up, cik=cik, company=company_name
                )

            # LTM-degraded diagnostic. Emitted whether the lookup returned
            # a scalar row (ltm/ltm-N degraded to lfy/lfy-N inside
            # lookup_company_kpi) or nothing, so the caller sees why LTM
            # wasn't computed.
            if p_lower == "ltm" or p_lower.startswith("ltm-"):
                diagnostics_list.append(
                    Diagnostic(
                        metric=metric,
                        kind="ltm_degraded",
                        message=(
                            f"LTM not computed for discovered KPI "
                            f"'{metric}'; showing latest annual (10-K) "
                            f"value instead."
                        ),
                    )
                )
            continue

        if meta.derived:
            series_kind = _series_period(period)
            if series_kind is not None:
                cited_series = _compute_derived_series(
                    facts,
                    metric,
                    meta,
                    company_name,
                    cik,
                    period,
                    doc_map,
                    diagnostics=diagnostics_list,
                )
                result_metrics[metric] = cited_series if cited_series else None
            else:
                cited = _compute_derived(
                    facts,
                    metric,
                    meta,
                    company_name,
                    cik,
                    period,
                    doc_map,
                    cache=derived_cache,
                    in_progress=set(),
                    diagnostics=diagnostics_list,
                )
                if cited is not None and _is_stale(cited, period):
                    diagnostics_list.append(_stale_rejected_diagnostic(metric, cited, period))
                    cited = None
                result_metrics[metric] = cited
        else:
            value = _resolve_direct_metric_value(
                facts,
                metric,
                meta,
                company_name,
                cik,
                period,
                doc_map,
                diagnostics_list,
            )
            if isinstance(value, list):
                result_metrics[metric] = value if value else None
                continue

            if value is not None and _is_stale(value, period):
                diagnostics_list.append(_stale_rejected_diagnostic(metric, value, period))
                result_metrics[metric] = None
                continue
            result_metrics[metric] = value

    if "headcount" in metric_list and result_metrics.get("headcount") is None:
        subs = await fetch_submissions(cik, force=force)
        filings = subs.get("filings", {}).get("recent", {})
        accession_meta: dict[str, dict[str, str]] = {}
        accs = filings.get("accessionNumber", [])
        rdates = filings.get("reportDate", [])
        fdates = filings.get("filingDate", [])
        forms = filings.get("form", [])
        for i, acc in enumerate(accs):
            accession_meta[acc] = {
                "reportDate": rdates[i] if i < len(rdates) else "",
                "filingDate": fdates[i] if i < len(fdates) else "",
                "form": forms[i] if i < len(forms) else "",
            }
        accessions_sorted = sorted(
            (a for a in doc_map if accession_meta.get(a, {}).get("form") in ("10-K", "20-F")),
            key=lambda a: accession_meta[a].get("reportDate", ""),
            reverse=True,
        )
        fallback = await _scan_headcount_fallback(
            cik, doc_map, accessions_sorted, accession_meta, force=force
        )
        if fallback is not None:
            headcount_value, accn, accession_info = fallback
            report_date_str = accession_info.get("reportDate") or ""
            filing_date_str = accession_info.get("filingDate") or report_date_str
            form_str = accession_info.get("form") or "10-K"
            try:
                report_date = (
                    _date.fromisoformat(report_date_str) if report_date_str else _date.today()
                )
            except ValueError:
                report_date = _date.today()
            try:
                filing_date = (
                    _date.fromisoformat(filing_date_str) if filing_date_str else report_date
                )
            except ValueError:
                filing_date = report_date
            result_metrics["headcount"] = CitedValue(
                value=headcount_value,
                unit="headcount",
                metric="headcount",
                concept="EntityNumberOfEmployees",
                period_end=report_date,
                period_start=report_date,
                fiscal_year=report_date.year,
                fiscal_period="FY",
                form_type=form_str,
                filed=filing_date,
                accession=accn,
                cik=cik,
                company=company_name,
                taxonomy="dei",
                accounting_standard="US-GAAP",
                reporting_currency="USD",
                source="text-scan",
            )

            # Inject the text-scan value into facts so any derived metric that
            # depends on headcount (revenue_per_employee, etc.) can resolve it
            # via the normal _compute_derived path. resolve_concept only
            # searches us-gaap and ifrs-full taxonomies, so the synthetic
            # fact is registered there (not under the semantically-correct
            # dei namespace) to stay reachable.
            synthetic_entry = {
                "label": "Entity Number of Employees",
                "units": {
                    "pure": [
                        {
                            "val": headcount_value,
                            "fy": report_date.year,
                            "fp": "FY",
                            "start": report_date.isoformat(),
                            "end": report_date.isoformat(),
                            "form": form_str,
                            "filed": filing_date.isoformat(),
                            "accn": accn,
                        }
                    ]
                },
            }
            facts.setdefault("us-gaap", {})
            facts["us-gaap"]["EntityNumberOfEmployees"] = synthetic_entry

            # Re-run derivations whose component list mentions headcount and
            # whose current value is None. Uses a fresh cache so a prior None
            # is not retained from the main loop.
            for m in metric_list:
                if result_metrics.get(m) is not None:
                    continue
                meta_m = METRIC_MAP.get(m)
                if meta_m is None or not meta_m.derived:
                    continue
                deps = {_normalize_component(c)[0] for c in meta_m.components}
                if "headcount" not in deps:
                    continue
                cited_retry = _compute_derived(
                    facts,
                    m,
                    meta_m,
                    company_name,
                    cik,
                    period,
                    doc_map,
                    cache={},
                    in_progress=set(),
                    diagnostics=diagnostics_list,
                )
                if cited_retry is not None and not _is_stale(cited_retry, period):
                    result_metrics[m] = cited_retry

    # Post-resolution sanity check: flag anomalously low total_debt relative
    # to total_liabilities.  Companies with captive finance subsidiaries
    # (e.g. Ford) may stop tagging consolidated debt in standard XBRL while
    # total liabilities remain correctly reported.
    _check_low_debt(result_metrics, facts, company_name, cik, period, doc_map)

    # Surface XBRL fetch failures as structured diagnostics rather than
    # silent N/A. Only attach to metrics that actually came back None
    # (a successful prose-based resolution beats the fetch_error story).
    if fetch_error_message is not None:
        for metric_name in metric_list:
            if result_metrics.get(metric_name) is None and not any(
                d.metric == metric_name and d.kind == "layer_a_fetch_error"
                for d in diagnostics_list
            ):
                diagnostics_list.append(
                    Diagnostic(
                        metric=metric_name,
                        kind="layer_a_fetch_error",
                        message=fetch_error_message,
                    )
                )

    result = QueryResult(
        company=company_name,
        cik=cik,
        period=period,
        metrics=result_metrics,
        diagnostics=diagnostics_list,
        display_token=display_token,
    )

    # Enrich CitedValues with XBRL fact IDs for stable deep-link anchors.
    # One HTTP fetch per unique accession number (cached).
    accessions = _collect_accessions(result)
    if accessions and doc_map:
        fact_id_maps = await _fetch_fact_id_maps(cik, doc_map, accessions)
        _enrich_fact_ids(result, fact_id_maps)

    # Pre-IPO fallback: if any requested metric still has no value, try
    # pulling it from cached S-1 snapshots for this CIK. 10-K rows already
    # filled their cells, so those are left alone. Also fires when the user
    # explicitly asked for the pro-forma pseudo-period.
    #
    # result.metrics is keyed on the RESOLVED (alias-normalized, lowercased)
    # metric slug, so alias the raw request names the same way before
    # checking emptiness. Without this normalization, a caller passing
    # `metrics=["Revenue"]` or `metrics=["rev"]` would compute any_empty=True
    # even when the cell was successfully resolved, spuriously triggering
    # the S-1 lazy-extraction path on every periodic-filer query.
    requested_for_s1_aug = metric_list if metrics is None else _requested_metrics_list(metrics)
    resolved_requested = [resolve_alias((m or "").strip().lower()) for m in requested_for_s1_aug]
    any_empty = any(result.metrics.get(m) is None for m in resolved_requested)
    if any_empty or period == "pro-forma":
        from .s1_financials import augment_with_s1_snapshot

        result = await augment_with_s1_snapshot(
            result=result,
            cik=cik,
            metrics=list(result.metrics.keys()),
            period=period,
            pack_root=pack_root_path,
            company=company_name,
            form_type="S-1",
        )

    return result


def _check_low_debt(
    result_metrics: dict[str, MetricValue],
    facts: dict[str, Any],
    company_name: str,
    cik: str,
    period: str,
    doc_map: dict[str, str] | None,
) -> None:
    """Attach a warning when total_debt is anomalously low vs total_liabilities."""
    debt_cv = result_metrics.get("total_debt")
    if debt_cv is None or isinstance(debt_cv, list):
        return
    debt_val = getattr(debt_cv, "value", None)
    if debt_val is None:
        return

    # Resolve total_liabilities for the same period
    liab_meta = METRIC_MAP.get("total_liabilities")
    if liab_meta is None:
        return
    resolved = resolve_concept("total_liabilities", facts)
    if resolved is None:
        return
    concept, taxonomy = resolved
    liab_cv = select_period(
        facts,
        concept,
        "total_liabilities",
        liab_meta,
        company_name,
        cik,
        period,
        taxonomy=taxonomy,
        doc_map=doc_map,
    )
    if liab_cv is None or isinstance(liab_cv, list):
        return
    liab_val = getattr(liab_cv, "value", None)
    if liab_val is None or liab_val <= 0:
        return

    if debt_val / liab_val < 0.02:
        warnings = getattr(debt_cv, "warnings", None)
        if warnings is None:
            return
        warnings.append(
            f"Resolved total debt ({debt_val / 1e9:.1f}B) is less than 2% of "
            f"total liabilities ({liab_val / 1e9:.1f}B). May be missing "
            f"captive finance or financial services subsidiary debt."
        )


async def _scan_headcount_fallback(
    cik: str,
    doc_map: dict[str, str],
    accessions: list[str],
    accession_meta: dict[str, dict[str, str]],
    force: bool = False,
) -> tuple[int, str, dict[str, str]] | None:
    """Return (value, accession, meta) for the first in-bounds headcount match."""
    from ..sec.headcount_text import scan_headcount_from_text

    cik_bare = cik.lstrip("0")
    for accn in accessions:
        primary_doc = doc_map.get(accn, "")
        if not primary_doc:
            continue
        filing_meta = FilingMeta(
            cik=cik_bare,
            accession=accn,
            form_type="",
            filing_date=_date.min,
            primary_document=primary_doc,
            company_name="",
        )
        try:
            html_bytes = await fetch_file(filing_meta, primary_doc)
        except (HTTPError, OSError, ValueError) as e:
            logger.warning("headcount fallback fetch failed for %s: %s", accn, e)
            continue
        text = html_bytes.decode("utf-8", errors="replace")
        value = scan_headcount_from_text(text)
        if value is not None:
            return value, accn, accession_meta.get(accn, {})
    return None


def _series_values_for_component(
    facts: dict[str, Any],
    comp_name: str,
    comp_meta: MetricMeta,
    company: str,
    cik: str,
    period: str,
    doc_map: dict[str, str] | None,
    diagnostics: list[Diagnostic] | None,
) -> list[MetricScalar]:
    """Resolve one component as a period series."""
    if comp_meta.derived:
        derived_series: list[MetricScalar] = list(
            _compute_derived_series(
                facts,
                comp_name,
                comp_meta,
                company,
                cik,
                period,
                doc_map,
                diagnostics=diagnostics,
            )
        )
        return derived_series

    hkex_concept = _hkex_concept_for_metric(facts, comp_name)
    if hkex_concept is not None:
        concept, taxonomy = hkex_concept
        value = select_period(
            facts,
            concept,
            comp_name,
            comp_meta,
            company,
            cik,
            period,
            taxonomy=taxonomy,
            doc_map=doc_map,
            diagnostics=diagnostics,
        )
        if not isinstance(value, list):
            return [value] if value is not None else []

        scope_warn = get_scope_warning(concept)
        if scope_warn:
            for item in value:
                item.warnings.append(scope_warn)
        return value

    resolved_value = _resolve_direct_metric_value(
        facts,
        comp_name,
        comp_meta,
        company,
        cik,
        period,
        doc_map,
        diagnostics if diagnostics is not None else [],
    )
    if not isinstance(resolved_value, list):
        return [resolved_value] if resolved_value is not None else []
    return list(resolved_value)


def _compute_derived_series(
    facts: dict[str, Any],
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    period: str,
    doc_map: dict[str, str] | None = None,
    diagnostics: list[Diagnostic] | None = None,
) -> list[DerivedValue]:
    """Compute a derived annual:N / quarterly:N series from aligned components."""
    parsed = _series_period(period)
    if parsed is None or not meta.components or not meta.formula:
        return []

    kind, count = parsed
    if count <= 0:
        return []

    shifted_components = [
        component
        for component in meta.components
        if isinstance(component, tuple) and len(component) == 2 and component[1] != 0
    ]
    if shifted_components:
        if kind != "annual":
            return []
        results: list[DerivedValue] = []
        for idx in range(count):
            value = _compute_derived(
                facts,
                metric,
                meta,
                company,
                cik,
                "lfy",
                doc_map,
                cache={},
                in_progress=set(),
                period_offset=-idx,
                diagnostics=diagnostics,
            )
            if isinstance(value, DerivedValue):
                results.append(value)
        return results

    component_maps: dict[str, dict[tuple[int, str, _date | None], CitedValue]] = {}
    component_order: list[tuple[int, str, _date | None]] = []

    for raw_comp in meta.components:
        comp_name, raw_comp_offset = _normalize_component(raw_comp)
        if raw_comp_offset != 0:
            return []

        comp_meta = METRIC_MAP.get(comp_name)
        if comp_meta is None:
            return []

        series = _series_values_for_component(
            facts,
            comp_name,
            comp_meta,
            company,
            cik,
            period,
            doc_map,
            diagnostics,
        )
        if not series:
            return []

        by_key: dict[tuple[int, str, _date | None], CitedValue] = {}
        for cited in series:
            if cited.value is None:
                continue
            key = _period_alignment_key(cited)
            by_key.setdefault(key, cited)

        if not by_key:
            return []
        if not component_order:
            component_order = [
                _period_alignment_key(cited) for cited in series if cited.value is not None
            ]
        component_maps[comp_name] = by_key

    derived_results: list[DerivedValue] = []
    for key in component_order:
        components: dict[str, CitedValue] = {}
        for raw_comp in meta.components:
            comp_name, _raw_comp_offset = _normalize_component(raw_comp)
            comp_value = component_maps.get(comp_name, {}).get(key)
            if comp_value is None:
                components = {}
                break
            components[comp_name] = comp_value
        if not components:
            continue

        result_value = _eval_formula(meta.formula, components)
        if result_value is None:
            continue

        derived_results.append(
            _make_derived_value(metric, result_value, meta.formula, components, cik, company)
        )
        if len(derived_results) >= count:
            break

    if 0 < len(derived_results) < count and diagnostics is not None:
        diagnostics.append(
            Diagnostic(
                metric=metric,
                kind="partial_coverage",
                message=(
                    f"Only {len(derived_results)} of {count} requested periods available for "
                    f"derived metric '{metric}' because component periods did not align."
                ),
            )
        )

    return derived_results


def _compute_derived(
    facts: dict[str, Any],
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    period: str,
    doc_map: dict[str, str] | None = None,
    cache: _DerivedCache | None = None,
    in_progress: set[str] | None = None,
    period_offset: int = 0,
    diagnostics: list[Diagnostic] | None = None,
) -> CitedValue | None:
    """Compute a derived metric from its components with cycle protection."""
    if cache is None:
        cache = {}
    if in_progress is None:
        in_progress = set()

    cache_key = metric if period_offset == 0 else f"{metric}@off{period_offset}"
    if cache_key in cache:
        return cache[cache_key]
    if cache_key in in_progress:
        cache[cache_key] = None
        return None

    if meta.kind == "cagr":
        result = _compute_cagr(
            facts,
            metric,
            meta,
            company,
            cik,
            period,
            doc_map,
            period_offset=period_offset,
            diagnostics=diagnostics,
        )
        cache[cache_key] = result
        return result

    if not meta.components or not meta.formula:
        cache[cache_key] = None
        return None

    in_progress.add(cache_key)
    components: dict[str, CitedValue] = {}

    for raw_comp in meta.components:
        comp_name, raw_comp_offset = _normalize_component(raw_comp)
        # Propagate the parent's offset into nested component lookups so that,
        # e.g., gross_margin_trend's gross_margin_prev1 resolves to FY-1.
        comp_offset = raw_comp_offset + period_offset
        comp_meta = METRIC_MAP.get(comp_name)
        if comp_meta is None:
            in_progress.discard(cache_key)
            cache[cache_key] = None
            return None

        if comp_meta.derived:
            # Recursive derived metric (e.g., ebitda needs operating_income + d&a)
            comp_value = _compute_derived(
                facts,
                comp_name,
                comp_meta,
                company,
                cik,
                period,
                doc_map,
                cache=cache,
                in_progress=in_progress,
                period_offset=comp_offset,
                diagnostics=diagnostics,
            )
        else:
            # HKEX packs tag concepts under their own taxonomy (hkfrs); use
            # that directly. For SEC facts we route through resolve_concept.
            hkex_concept = _hkex_concept_for_metric(facts, comp_name)
            if hkex_concept is not None:
                concept: str
                taxonomy: str
                concept, taxonomy = hkex_concept
                value = select_period(
                    facts,
                    concept,
                    comp_name,
                    comp_meta,
                    company,
                    cik,
                    period,
                    taxonomy=taxonomy,
                    doc_map=doc_map,
                    period_offset=comp_offset,
                    diagnostics=diagnostics,
                )
                if isinstance(value, list):
                    comp_value = value[0] if value else None
                else:
                    comp_value = value

                if comp_value is not None:
                    scope_warn = get_scope_warning(concept)
                    if scope_warn:
                        comp_value.warnings.append(scope_warn)
            else:
                direct_value = _resolve_direct_metric_value(
                    facts,
                    comp_name,
                    comp_meta,
                    company,
                    cik,
                    period,
                    doc_map,
                    diagnostics if diagnostics is not None else [],
                    period_offset=comp_offset,
                )
                if isinstance(direct_value, list):
                    comp_value = direct_value[0] if direct_value else None
                else:
                    comp_value = direct_value

                if comp_value is None:
                    in_progress.discard(cache_key)
                    cache[cache_key] = None
                    return None

            # Staleness guard on components (skip when an offset is requested
            # because prior-year lookbacks are expected to be "stale").
            if comp_value is not None and comp_offset == 0 and _is_stale(comp_value, period):
                in_progress.discard(cache_key)
                cache[cache_key] = None
                return None

        if comp_value is None or comp_value.value is None:
            in_progress.discard(cache_key)
            cache[cache_key] = None
            return None

        # Key by offset-suffixed name so the same metric can appear at two
        # different periods (e.g. revenue[fy] and revenue[fy-1]). Use the
        # raw (formula-specified) offset for the key, not the propagated
        # effective offset, so formulas always reference the same name.
        if raw_comp_offset == 0:
            components[comp_name] = comp_value
        else:
            suffix = (
                f"_prev{abs(raw_comp_offset)}" if raw_comp_offset < 0 else f"_next{raw_comp_offset}"
            )
            components[f"{comp_name}{suffix}"] = comp_value

    # Cross-period validation: when no component has an offset, every component
    # should resolve to the same fiscal year/period/end date. Offsetted formulas
    # (YoY, trend) intentionally cross FYs, so skip the check for those.
    any_shifted = any(isinstance(c, tuple) and len(c) == 2 and c[1] != 0 for c in meta.components)
    if not any_shifted and period_offset == 0:
        alignment_keys = {_period_alignment_key(comp) for comp in components.values()}
        if len(alignment_keys) > 1:
            in_progress.discard(cache_key)
            cache[cache_key] = None
            return None

    # Evaluate formula
    result_value = _eval_formula(meta.formula, components)
    if result_value is None:
        in_progress.discard(cache_key)
        cache[cache_key] = None
        return None

    derived = _make_derived_value(metric, result_value, meta.formula, components, cik, company)
    in_progress.discard(cache_key)
    cache[cache_key] = derived
    return derived


def _eval_formula(formula: str, components: dict[str, CitedValue]) -> float | None:
    """Evaluate a simple arithmetic formula with component values.

    The evaluator is positional and left-associative only. Supported shapes:

    - ``a op b`` (3 tokens): single binary operation.
    - ``a op1 b op2 c`` (5 tokens): left-associative; ``op1`` is applied first,
      then ``op2`` is applied to that result and ``c``.

    Do not use this for formulas that rely on operator precedence. For
    ``(a / b) - c``, write exactly that token sequence (``a / b - c``).
    For ``a * (b + c)``, decompose ``b + c`` into a named component first.

    Numeric literals are supported in any operand position (e.g. ``revenue - 1``).
    """
    vals = {k: float(v.value) for k, v in components.items() if v.value is not None}
    return eval_formula(formula, vals)


def _fy_equivalent(period: str) -> str:
    """Map a parent period to its FY-anchored equivalent for CAGR math.

    CAGR is computed over annual values regardless of whether the caller asked
    for ``ltm``, ``mrq``, or an FY-anchored selector. ``ltm`` / ``mrq`` /
    ``mrp`` collapse to ``lfy``; ``ltm-N`` / ``mrq-N`` collapse to ``lfy-N``.
    ``lfy`` / ``lfy-N`` pass through unchanged.
    """
    p = period.strip().lower()
    if p in ("ltm", "mrq", "mrp"):
        return "lfy"
    m = re.match(r"^(ltm|mrq)-(\d+)$", p)
    if m:
        return f"lfy-{m.group(2)}"
    return p


def _parent_fy_back(period: str) -> int | None:
    """Return the FY offset (years back) for a parent period, or None if unknown.

    ``lfy``, ``ltm``, ``mrq``, ``mrp`` -> 0.
    ``lfy-N`` / ``ltm-N`` / ``mrq-N`` -> N.
    Series selectors and anything else -> None.
    """
    p = period.strip().lower()
    if p in ("lfy", "ltm", "mrq", "mrp"):
        return 0
    m = re.match(r"^(lfy|ltm|mrq)-(\d+)$", p)
    if m:
        return int(m.group(2))
    return None


def _compute_cagr(
    facts: dict[str, Any],
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    period: str,
    doc_map: dict[str, str] | None,
    period_offset: int = 0,
    diagnostics: list[Diagnostic] | None = None,
) -> DerivedValue | None:
    """Compute ``(end / start) ** (1/N) - 1`` on FY-anchored components.

    Returns ``None`` when the base metric cannot be resolved for either
    endpoint, when the start value is zero, or when the signs differ (crossing
    zero makes CAGR meaningless). A sign-flip or zero-start condition adds a
    warning to the returned value if the value is otherwise computable.
    """
    n = meta.cagr_years
    base = meta.cagr_base
    if n <= 0 or not base:
        return None

    base_meta = METRIC_MAP.get(base)
    if base_meta is None:
        return None

    # Total years back from the current FY for the parent period. This lets
    # us bake the offset into a canonical ``lfy-K`` period string so the
    # router (which hardcodes period_offset from the regex group) still
    # returns the right FY.
    parent_back = _parent_fy_back(period)
    if parent_back is None:
        return None
    # Combine with an explicit caller-provided period_offset (negative offsets
    # walk further back; positive would walk forward but CAGR doesn't use it).
    parent_back -= period_offset

    def _period_for_back(years_back_total: int) -> str:
        yrs = max(0, years_back_total)
        return "lfy" if yrs == 0 else f"lfy-{yrs}"

    def _resolve_at(years_back_total: int) -> CitedValue | None:
        """Resolve the base metric at FY - years_back_total using a canonical lfy-K string."""
        back = parent_back + years_back_total
        anchor_period = _period_for_back(back)
        if base_meta.derived:
            return _compute_derived(
                facts,
                base,
                base_meta,
                company,
                cik,
                anchor_period,
                doc_map,
                cache={},
                in_progress=set(),
                diagnostics=diagnostics,
            )
        hkex_concept = _hkex_concept_for_metric(facts, base)
        if hkex_concept is not None:
            concept, taxonomy = hkex_concept
            value = select_period(
                facts,
                concept,
                base,
                base_meta,
                company,
                cik,
                anchor_period,
                taxonomy=taxonomy,
                doc_map=doc_map,
            )
        else:
            direct_value = _resolve_direct_metric_value(
                facts,
                base,
                base_meta,
                company,
                cik,
                anchor_period,
                doc_map,
                diagnostics if diagnostics is not None else [],
            )
            if isinstance(direct_value, list):
                return direct_value[0] if direct_value else None
            return direct_value
        if isinstance(value, list):
            return value[0] if value else None
        return value

    end_cv = _resolve_at(0)
    start_cv = _resolve_at(n)

    if end_cv is None or start_cv is None:
        return None
    if end_cv.value is None or start_cv.value is None:
        return None

    end_val = float(end_cv.value)
    start_val = float(start_cv.value)
    if start_val == 0:
        return None
    if (end_val > 0) != (start_val > 0):
        # Sign flip across the window makes CAGR meaningless.
        return None

    try:
        ratio = end_val / start_val
        # Guard against negative ratio (defensive; sign-flip check above
        # should already cover this).
        if ratio <= 0:
            return None
        cagr = ratio ** (1.0 / n) - 1.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None

    return DerivedValue(
        value=cagr,
        unit="pure",
        metric=metric,
        concept=meta.formula or f"cagr({base},{n})",
        period_start=start_cv.period_end,
        period_end=end_cv.period_end,
        fiscal_year=end_cv.fiscal_year,
        fiscal_period=f"CAGR-{n}Y",
        form_type=end_cv.form_type,
        filed=end_cv.filed,
        accession=end_cv.accession,
        cik=cik,
        company=company,
        taxonomy=end_cv.taxonomy,
        primary_document=end_cv.primary_document,
        derived=True,
        components={"end": end_cv, "start": start_cv},
    )


def _derived_unit(metric: str, components: dict[str, CitedValue]) -> str:
    """Determine the unit for a derived metric."""
    # Ratios produce "pure" (dimensionless)
    ratio_metrics = {
        "gross_margin",
        "operating_margin",
        "net_margin",
        "ebitda_margin",
        "fcf_margin",
        "roe",
        "roa",
        "current_ratio",
        "debt_to_equity",
        # Growth family
        "revenue_growth_yoy",
        "net_income_growth_yoy",
        "operating_income_growth_yoy",
        "eps_growth_yoy",
        # Margin trend family
        "gross_margin_trend",
        "operating_margin_trend",
        "net_margin_trend",
        # Intensity family
        "r_and_d_intensity",
        "sga_intensity",
        "sm_intensity",
        "capex_intensity",
        # Quality / composite
        "fcf_to_net_income",
        "rule_of_40",
    }
    if metric in ratio_metrics:
        return "pure"

    # Additive/subtractive: inherit from first component
    first = next(iter(components.values()), None)
    return first.unit if first else "USD"


def _make_derived_value(
    metric: str,
    value: float,
    concept: str,
    components: dict[str, CitedValue],
    cik: str,
    company: str,
) -> DerivedValue:
    # Shared assembly for _compute_derived and _compute_derived_series: a derived
    # value inherits period/fiscal/filing provenance from its first component.
    # _compute_cagr does NOT use this; it derives those fields from its start/end
    # window, not the first component.
    first = next(iter(components.values()))
    return DerivedValue(
        value=value,
        unit=_derived_unit(metric, components),
        metric=metric,
        concept=concept,
        period_start=first.period_start,
        period_end=first.period_end,
        fiscal_year=first.fiscal_year,
        fiscal_period=first.fiscal_period,
        form_type=first.form_type,
        filed=first.filed,
        accession=first.accession,
        cik=cik,
        company=company,
        taxonomy=first.taxonomy,
        primary_document=first.primary_document,
        derived=True,
        components=components,
    )


_HKEX_CONCEPT_CANONICAL: dict[str, str] = {
    "Revenue": "revenue",
    "GrossProfit": "gross_profit",
    "OperatingIncomeLoss": "operating_income",
    "ProfitLoss": "net_income",
    "TotalAssets": "total_assets",
    "TotalLiabilities": "total_liabilities",
    "TotalEquity": "total_equity",
    "CashAndCashEquivalents": "cash_and_equivalents",
    "ResearchAndDevelopmentExpense": "rd_expense",
    "ResearchAndDevelopmentIntensity": "r_and_d_intensity",
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "EntityNumberOfEmployees": "headcount",
    "NumberOfEmployees": "headcount",
}


def _hkex_concept_for_metric(
    facts: dict[str, Any],
    metric: str,
) -> tuple[str, str] | None:
    """Reverse lookup: find an HKEX concept whose canonical metric matches.

    Returns (concept, taxonomy) for use with select_period, or None if the
    facts dict is not HKEX-shaped or no concept maps to ``metric``.
    """
    for taxonomy, concepts in facts.items():
        if taxonomy in ("us-gaap", "ifrs-full", "dei"):
            continue
        if not isinstance(concepts, dict):
            continue
        for concept in concepts.keys():
            if _HKEX_CONCEPT_CANONICAL.get(concept) == metric:
                return concept, taxonomy
    return None


def _hkex_concept_to_canonical(concept: str, standard: str) -> str:
    if concept in _HKEX_CONCEPT_CANONICAL:
        return _HKEX_CONCEPT_CANONICAL[concept]

    from .metric_map import METRIC_MAP as _MM

    std_key: AccountingStandard = cast(AccountingStandard, standard) if standard in _MM else "HKFRS"
    for metric, concepts in _MM.get(std_key, {}).items():
        if concept in concepts:
            return metric
    return concept.lower()


def _enrich_hkex_cited(
    cited: CitedValue | None,
    standard: str,
    reporting_currency: str,
    company: str,
    cik: str,
) -> CitedValue | None:
    """Fill HKEX-specific metadata that ``select_period`` does not set."""
    if cited is None:
        return None
    cited.accounting_standard = standard  # type: ignore[assignment]
    cited.reporting_currency = reporting_currency
    cited.company = company
    cited.cik = cik
    return cited


async def _query_hkex_pack(
    resolved: object,
    metrics: str | list[str] | None,
    period: str,
    *,
    display_token: str | None = None,
) -> QueryResult:
    return await _query_china_pack(
        resolved, metrics, period, display_token=display_token, pack_root=None
    )


def _china_stock_code(resolved: object) -> str:
    stock_code = getattr(resolved, "stock_code", None) or getattr(resolved, "hk_stock_code", None)
    return str(stock_code or "").strip()


def _discover_china_pack_dir(resolved: object, pack_root: Path | None = None) -> Path | None:
    """Find a local China pack for HKEX/SSE query paths."""
    source = str(getattr(resolved, "source", "") or "").upper()
    stock_code = _china_stock_code(resolved)
    ticker = str(getattr(resolved, "ticker", "") or "")

    roots: list[Path] = []
    if pack_root is not None:
        roots.append(Path(pack_root))
    else:
        roots.extend([DEFAULT_PACKS_DIR, Path(".")])

    exchange_dirs = ["sse"] if source == "SSE" else ["hk", "hkex"]
    variants = [v for v in (stock_code, stock_code.lstrip("0"), ticker, ticker.upper()) if v]
    candidates: list[Path] = []
    for root in roots:
        for exchange_dir in exchange_dirs:
            for variant in variants:
                base = root / exchange_dir / variant
                if base.exists():
                    candidates.extend(path.parent for path in base.glob("*/facts.json"))
        if source == "SSE" and stock_code:
            base = root / "sse" / stock_code
            if base.exists():
                candidates.extend(path.parent for path in base.glob("*/facts.json"))

    # Flat ``{name}_{fiscal_year}`` packs (fixtures and demos) live under an
    # explicit root, opt-in via EDGARPACK_CHINA_PACK_ROOT so production never
    # probes the test tree. Fiscal years come from the directory names found,
    # not a hardcoded constant.
    china_pack_root = os.environ.get("EDGARPACK_CHINA_PACK_ROOT")
    if china_pack_root and source == "HKEX":
        root_dir = Path(china_pack_root)
        if root_dir.is_dir():
            names: set[str] = set()
            for alias in getattr(resolved, "aliases", ()):
                alias_text = str(alias).lower()
                names.add(alias_text.replace(" ", "_"))
                names.add(alias_text)
            names.update(v.lower() for v in variants)
            for child in sorted(root_dir.iterdir()):
                if not (child / "facts.json").exists():
                    continue
                match = re.fullmatch(r"(?P<name>.+)_(?P<fy>\d{4})", child.name)
                if match is None:
                    continue
                if match.group("name").lower() in names:
                    candidates.append(child)

    if not candidates:
        return None

    def _sort_key(path: Path) -> tuple[str, str]:
        manifest_path = path / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                filing = manifest.get("filing", {}) if isinstance(manifest, dict) else {}
                return (str(filing.get("filing_date") or ""), str(path))
            except Exception:
                pass
        return (path.name, str(path))

    return sorted(set(candidates), key=_sort_key, reverse=True)[0]


def _load_china_manifest(pack_dir: Path) -> dict[str, Any]:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def _parse_china_date(value: object) -> _date | None:
    text = str(value or "").strip()
    if not text or text.upper() in {"N/A", "NA", "NONE", "NULL", "-"}:
        return None
    text = text.split(" ", 1)[0]

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return _datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _local_china_source(pack_dir: Path) -> tuple[str, str]:
    for rel in ("source.pdf", "optional/source.pdf"):
        candidate = pack_dir / rel
        if candidate.exists():
            return rel, str(candidate.resolve())
    pdfs = sorted(pack_dir.glob("*.pdf"))
    if len(pdfs) == 1:
        return pdfs[0].name, str(pdfs[0].resolve())
    return "", ""


def _china_manifest_source_url(manifest: dict[str, Any], data: dict[str, Any]) -> str:
    filing = manifest.get("filing", {}) if isinstance(manifest.get("filing"), dict) else {}
    for candidate in (
        manifest.get("pdf_url"),
        manifest.get("source_url"),
        filing.get("source_url"),
        filing.get("url"),
        data.get("source_url"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _china_manifest_filed_date(
    manifest: dict[str, Any],
    point: dict[str, Any],
) -> _date | None:
    """Return the pack's real announcement/filing date, or None.

    Never synthesizes a date from the fiscal year or period end: a filing date
    invented from the year-end is false provenance. Callers leave ``filed``
    absent when this returns None.
    """
    filing = manifest.get("filing", {}) if isinstance(manifest.get("filing"), dict) else {}
    for candidate in (
        point.get("filed"),
        filing.get("filing_date"),
        manifest.get("announcement_date"),
        manifest.get("filing_date"),
    ):
        parsed = _parse_china_date(candidate)
        if parsed is not None:
            return parsed
    return None


def _normalize_china_fact_provenance(
    data: dict[str, Any],
    pack_dir: Path,
    manifest: dict[str, Any],
) -> None:
    """Fill missing source/date fields on China pack facts before citation routing."""
    source_document, source_path = _local_china_source(pack_dir)
    manifest_source_url = _china_manifest_source_url(manifest, data)
    source_url_is_local_file = manifest_source_url.lower().startswith("file://")

    facts = data.get("facts", {})
    if not isinstance(facts, dict):
        return

    for concepts in facts.values():
        if not isinstance(concepts, dict):
            continue
        for concept_info in concepts.values():
            if not isinstance(concept_info, dict):
                continue
            units = concept_info.get("units", {})
            if not isinstance(units, dict):
                continue
            for points in units.values():
                if not isinstance(points, list):
                    continue
                for point in points:
                    if not isinstance(point, dict):
                        continue

                    filed = _china_manifest_filed_date(manifest, point)
                    if filed is not None and not point.get("filed"):
                        point["filed"] = filed.isoformat()

                    if source_path and not point.get("source_path"):
                        point["source_path"] = source_path
                    if source_document and not point.get("source_document"):
                        point["source_document"] = source_document

                    if (
                        not point.get("source_url")
                        and manifest_source_url
                        and not (source_url_is_local_file and source_path)
                    ):
                        point["source_url"] = manifest_source_url


async def _query_china_pack(
    resolved: object,
    metrics: str | list[str] | None,
    period: str,
    *,
    display_token: str | None = None,
    pack_root: Path | None = None,
) -> QueryResult:
    import json

    from .models import QueryResult

    pack_dir = _discover_china_pack_dir(resolved, pack_root=pack_root)
    if pack_dir is None:
        source = str(getattr(resolved, "source", "China") or "China")
        stock_code = _china_stock_code(resolved)
        target = display_token or stock_code or getattr(resolved, "ticker", "")
        if source == "SSE":
            raise FileNotFoundError(
                f"No SSE pack found for {stock_code}. "
                f"Run `edgarpack build-sse {target} --latest-annual --with-chunks` first."
            )
        raise FileNotFoundError(
            f"No {source} pack found for {stock_code or getattr(resolved, 'ticker', '')}."
        )

    facts_path = pack_dir / "facts.json"
    if not facts_path.exists():
        raise FileNotFoundError(f"No facts.json at {facts_path}")

    data = json.loads(facts_path.read_text())
    manifest = _load_china_manifest(pack_dir)
    _normalize_china_fact_provenance(data, pack_dir, manifest)

    if metrics is None:
        requested: set[str] | None = None
    elif isinstance(metrics, str):
        requested = {resolve_alias(m.strip()) for m in metrics.split(",") if m.strip()} or None
    else:
        requested = {resolve_alias(str(m).strip()) for m in metrics if str(m).strip()} or None

    company_name = data.get("company", getattr(resolved, "ticker", ""))
    cik_str = _china_stock_code(resolved)

    # Build facts dict in {taxonomy: {concept: {units: {...}}}} shape that
    # select_period understands, and map each HKEX concept back to its
    # canonical metric name.
    standard_by_taxonomy: dict[str, str] = {}
    reporting_currency_by_concept: dict[str, str] = {}
    facts: dict[str, dict[str, Any]] = {}
    concept_to_metric: dict[str, tuple[str, str]] = {}  # concept -> (metric, taxonomy)

    for standard_key, concepts in data["facts"].items():
        taxonomy = standard_key  # "hkfrs", "ifrs", etc.
        standard = standard_key.upper().replace("US_GAAP", "US-GAAP")
        standard_by_taxonomy[taxonomy] = standard
        facts.setdefault(taxonomy, {})
        for concept, info in concepts.items():
            metric = _hkex_concept_to_canonical(concept, standard)
            facts[taxonomy][concept] = info
            concept_to_metric[concept] = (metric, taxonomy)
            units = info.get("units", {})
            if units:
                # Pick first unit as the reporting currency (or "headcount").
                first_unit = next(iter(units.keys()))
                reporting_currency_by_concept[concept] = first_unit

    result_metrics: dict[str, MetricValue] = {}
    diagnostics_list: list[Diagnostic] = []

    # Derive meta lookup per metric: HKFact concepts aren't in METRIC_MAP
    # under GAAP taxonomy, but we know their duration/instant nature from
    # the canonical metric name.
    duration_by_metric: dict[str, bool] = {
        "revenue": True,
        "gross_profit": True,
        "operating_income": True,
        "net_income": True,
        "rd_expense": True,
        "r_and_d_intensity": True,
        "operating_cash_flow": True,
        "total_assets": False,
        "total_liabilities": False,
        "total_equity": False,
        "cash_and_equivalents": False,
        "headcount": False,
    }

    # Metrics available as concrete concepts from the pack.
    metric_to_concept: dict[str, tuple[str, str]] = {}
    for concept, (metric, taxonomy) in concept_to_metric.items():
        # First-concept-wins; HKEX packs only carry one concept per metric.
        metric_to_concept.setdefault(metric, (concept, taxonomy))

    # Decide which metrics to produce. If the caller asked for derived metrics
    # not backed by a concept, compute them via _compute_derived.
    if requested is None:
        target_metrics = list(metric_to_concept.keys())
    else:
        target_metrics = sorted(requested)

    derived_cache: _DerivedCache = {}

    for metric in target_metrics:
        if metric in metric_to_concept:
            concept, taxonomy = metric_to_concept[metric]
            duration = duration_by_metric.get(metric, True)
            meta = MetricMeta(concepts=(concept,), duration=duration)
            unit = reporting_currency_by_concept.get(concept, "USD")
            # Non-currency units (headcount) must not leak into reporting_currency;
            # downstream renderers use reporting_currency to label the column footer.
            reporting_currency = "" if unit == "headcount" else unit
            standard = standard_by_taxonomy[taxonomy]

            value = select_period(
                facts,
                concept,
                metric,
                meta,
                company_name,
                cik_str,
                period,
                taxonomy=taxonomy,
                diagnostics=diagnostics_list,
            )

            if isinstance(value, list):
                enriched = [
                    _enrich_hkex_cited(cv, standard, reporting_currency, company_name, cik_str)
                    for cv in value
                ]
                _apply_extraction_source(enriched, facts[taxonomy][concept])
                result_metrics[metric] = [cv for cv in enriched if cv is not None]
            elif value is not None and not isinstance(value, DerivedValue):
                enriched_single = _enrich_hkex_cited(
                    value, standard, reporting_currency, company_name, cik_str
                )
                _apply_extraction_source([enriched_single], facts[taxonomy][concept])
                result_metrics[metric] = enriched_single
            else:
                result_metrics[metric] = value
            continue

        # Not in the pack as a concrete concept. Try a derived computation.
        derived_meta = METRIC_MAP.get(metric)
        if derived_meta is None or not derived_meta.derived:
            result_metrics[metric] = None
            continue

        cited = _compute_derived(
            facts,
            metric,
            derived_meta,
            company_name,
            cik_str,
            period,
            doc_map=None,
            cache=derived_cache,
            in_progress=set(),
            diagnostics=diagnostics_list,
        )
        if cited is not None:
            # Propagate HKEX metadata (accounting standard + reporting currency).
            raw_standard = next(iter(standard_by_taxonomy.values()), "HKFRS")
            cited.accounting_standard = (
                cast(AccountingStandard, raw_standard)
                if raw_standard in {"US-GAAP", "IFRS", "HKFRS", "CAS"}
                else "HKFRS"
            )
            # Use the native currency of the first non-headcount component.
            ratio_or_growth = metric in {
                "revenue_growth_yoy",
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
                "eps_growth_yoy",
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "r_and_d_intensity",
                "sga_intensity",
                "sm_intensity",
                "capex_intensity",
                "fcf_to_net_income",
                "rule_of_40",
                "gross_margin",
                "operating_margin",
                "net_margin",
                "ebitda_margin",
                "fcf_margin",
            }
            if ratio_or_growth:
                cited.reporting_currency = "pure"
            elif metric == "revenue_per_employee":
                # revenue / headcount -> money per person. Use the revenue
                # component's reporting currency.
                rev_concept = metric_to_concept.get("revenue")
                if rev_concept is not None:
                    cited.reporting_currency = reporting_currency_by_concept.get(
                        rev_concept[0], "USD"
                    )
        result_metrics[metric] = cited

    return QueryResult(
        company=company_name,
        cik=cik_str,
        period=period,
        metrics=result_metrics,
        diagnostics=diagnostics_list,
        display_token=display_token,
    )


def _apply_extraction_source(
    cited_list: list[CitedValue | None],
    concept_info: dict[str, Any],
) -> None:
    """Copy extraction_method from the underlying pack fact onto CitedValues.

    Pack facts carry "extraction_method" metadata per data point; select_period
    only returns the standard SEC fields, so we re-attach the provenance after
    routing so downstream consumers (compare, goldens) see "regex"/"llm" tags.
    """
    units = concept_info.get("units", {})
    by_fy: dict[int, dict[str, str]] = {}
    for _unit, pts in units.items():
        for p in pts:
            fy_val = int(p.get("fy") or 0)
            if fy_val:
                by_fy[fy_val] = {
                    "source": str(p.get("extraction_method") or "regex"),
                    "source_url": str(p.get("source_url") or ""),
                    "source_document": str(p.get("source_document") or ""),
                    "source_path": str(p.get("source_path") or ""),
                    "section_id": str(p.get("section_id") or ""),
                    "matched_label": str(p.get("matched_label") or ""),
                }
    for cv in cited_list:
        if cv is None:
            continue
        meta = by_fy.get(cv.fiscal_year)
        if not meta:
            continue
        cv.source = meta["source"]
        cv.source_url = meta["source_url"]
        cv.source_document = meta["source_document"]
        cv.source_path = meta["source_path"]
        cv.section_id = meta["section_id"]
        cv.matched_label = meta["matched_label"]
