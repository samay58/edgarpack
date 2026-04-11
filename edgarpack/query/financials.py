"""Single-company financial queries with full citation provenance."""

from __future__ import annotations

import asyncio
import logging
from datetime import date as _date
from typing import Any

from ..sec.archives import fetch_file
from ..sec.client import HTTPError
from ..sec.submissions import FilingMeta, fetch_submissions
from ..sec.tickers import resolve_ticker
from ..sec.xbrl import fetch_company_facts
from .concepts import ALL_METRICS, METRIC_MAP, MetricMeta, get_scope_warning, resolve_concept
from .layer_zero import MetricNotFound, resolve_alias, suggest_metrics
from .models import CitedValue, DerivedValue, QueryResult
from .periods import parse_fact_ids_from_html, select_period
from .self_heal import try_learn

logger = logging.getLogger(__name__)

_DerivedCache = dict[str, CitedValue | None]

# Staleness thresholds: max fiscal-year gap (current_year - fy) before
# a value is rejected as stale.  Series queries ("annual:N", "quarterly:N")
# skip the check entirely since the caller explicitly asks for history.
_STALENESS_YEARS: dict[str, int] = {"ltm-1": 3}
_STALENESS_DEFAULT = 2


def _staleness_limit(period: str) -> int:
    """Max fiscal-year age before a value is rejected as stale."""
    p = period.strip().lower()
    if p.startswith("annual:") or p.startswith("quarterly:"):
        return 999
    return _STALENESS_YEARS.get(p, _STALENESS_DEFAULT)


def _is_stale(cited: CitedValue, period: str) -> bool:
    """True when a CitedValue's fiscal year is too far behind the current year."""
    limit = _staleness_limit(period)
    if limit >= 999:
        return False
    return cited.fiscal_year < _date.today().year - limit


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


async def financials(
    company: str,
    metrics: str | list[str] | None = None,
    period: str = "lfy",
    force: bool = False,
) -> QueryResult:
    """Query financial metrics for a single company.

    Args:
        company: Ticker symbol ("NVDA") or CIK number ("1045810").
        metrics: Metric name(s). String for single, list for multiple,
                 None for all available metrics.
        period: Period selector: "lfy", "mrq", "ltm", "ltm-1", "mrp",
                "annual:N", "quarterly:N".
        force: Bypass cache.

    Returns:
        QueryResult with cited values for each requested metric.
    """
    cik, company_name = await resolve_ticker(company, force=force)

    facts_data = await fetch_company_facts(cik, force=force)
    facts = facts_data.get("facts", {})

    doc_map = await _build_doc_map(cik, force=force)

    if metrics is None:
        metric_list = list(ALL_METRICS)
    elif isinstance(metrics, str):
        metric_list = [m.strip() for m in metrics.split(",")]
    else:
        metric_list = list(metrics)

    # Layer 0: alias dereferencing + unknown-metric guard
    # A metric is "known" if it's in METRIC_MAP OR in KPI_CATALOG (Layer B).
    from .kpi_extract import KPI_CATALOG

    resolved_list: list[str] = []
    for m in metric_list:
        resolved = resolve_alias(m)
        if resolved not in METRIC_MAP and resolved not in KPI_CATALOG:
            combined_known = set(METRIC_MAP.keys()) | set(KPI_CATALOG.keys())
            suggestions = suggest_metrics(resolved, combined_known, n=3)
            raise MetricNotFound(m, suggestions=suggestions)
        resolved_list.append(resolved)
    metric_list = resolved_list

    result_metrics: dict[str, CitedValue | list[CitedValue] | None] = {}
    derived_cache: _DerivedCache = {}

    for metric in metric_list:
        meta = METRIC_MAP.get(metric)
        if meta is None:
            # KPI-only metric (in KPI_CATALOG but not METRIC_MAP).
            # Task 12 will wire try_extract_kpi here. For now, set to None
            # so the test passes and the structure is ready.
            result_metrics[metric] = None
            continue

        if meta.derived:
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
            )
            if cited is not None and _is_stale(cited, period):
                cited = None
            result_metrics[metric] = cited
        else:
            resolved = resolve_concept(metric, facts)
            if resolved is None:
                # Concept resolution failed: try self-heal before giving up.
                learned = try_learn(
                    metric=metric,
                    meta=meta,
                    facts=facts,
                    cik=cik,
                    company=company_name,
                    prior_year_cited=None,
                    doc_map=doc_map,
                )
                result_metrics[metric] = learned
                continue

            concept, taxonomy = resolved
            value = select_period(
                facts,
                concept,
                metric,
                meta,
                company_name,
                cik,
                period,
                taxonomy=taxonomy,
                doc_map=doc_map,
            )

            if isinstance(value, list):
                scope_warn = get_scope_warning(concept)
                if scope_warn:
                    for v in value:
                        v.warnings.append(scope_warn)
                result_metrics[metric] = value if value else None
            else:
                if value is not None and _is_stale(value, period):
                    result_metrics[metric] = None
                    continue
                if value is not None:
                    scope_warn = get_scope_warning(concept)
                    if scope_warn:
                        value.warnings.append(scope_warn)
                    result_metrics[metric] = value
                    continue

                # Deterministic path returned None. Try self-heal with the
                # prior-year annual value as verification ground truth.
                prior = _fetch_prior_year_for_self_heal(
                    facts=facts,
                    concept=concept,
                    metric=metric,
                    company=company_name,
                    cik=cik,
                    doc_map=doc_map,
                )
                learned = try_learn(
                    metric=metric,
                    meta=meta,
                    facts=facts,
                    cik=cik,
                    company=company_name,
                    prior_year_cited=prior,
                    doc_map=doc_map,
                )
                result_metrics[metric] = learned

    # Post-resolution sanity check: flag anomalously low total_debt relative
    # to total_liabilities.  Companies with captive finance subsidiaries
    # (e.g. Ford) may stop tagging consolidated debt in standard XBRL while
    # total liabilities remain correctly reported.
    _check_low_debt(result_metrics, facts, company_name, cik, period, doc_map)

    result = QueryResult(company=company_name, cik=cik, period=period, metrics=result_metrics)

    # Enrich CitedValues with XBRL fact IDs for stable deep-link anchors.
    # One HTTP fetch per unique accession number (cached).
    accessions = _collect_accessions(result)
    if accessions and doc_map:
        fact_id_maps = await _fetch_fact_id_maps(cik, doc_map, accessions)
        _enrich_fact_ids(result, fact_id_maps)

    return result


def _fetch_prior_year_for_self_heal(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    company: str,
    cik: str,
    doc_map: dict[str, str] | None,
) -> CitedValue | None:
    """Try to get a prior-year ground truth for verifying a learned mapping.

    Walks the annual history for the resolved concept and returns the second
    most recent full-year entry (prior fiscal year). Returns None if fewer
    than two annual entries exist. Used only as a sanity-check input for
    the self-heal verifier — never for user-visible output.
    """
    from .periods import _annual_history, _extract_values, _unit_for_concept, _value_to_cited

    values = _extract_values(facts, concept, taxonomy="us-gaap")
    annual = _annual_history(values)
    if len(annual) < 2:
        return None
    unit = _unit_for_concept(facts, concept, taxonomy="us-gaap")
    return _value_to_cited(
        annual[1], metric, concept, unit, company, cik, doc_map=doc_map,
    )


def _check_low_debt(
    result_metrics: dict,
    facts: dict,
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
) -> CitedValue | None:
    """Compute a derived metric from its components with cycle protection."""
    if cache is None:
        cache = {}
    if in_progress is None:
        in_progress = set()

    if metric in cache:
        return cache[metric]
    if metric in in_progress:
        cache[metric] = None
        return None

    if not meta.components or not meta.formula:
        cache[metric] = None
        return None

    in_progress.add(metric)
    components: dict[str, CitedValue] = {}

    for comp_name in meta.components:
        comp_meta = METRIC_MAP.get(comp_name)
        if comp_meta is None:
            in_progress.discard(metric)
            cache[metric] = None
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
            )
        else:
            resolved = resolve_concept(comp_name, facts)
            if resolved is None:
                in_progress.discard(metric)
                cache[metric] = None
                return None
            concept, taxonomy = resolved
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
            )
            if isinstance(value, list):
                comp_value = value[0] if value else None
            else:
                comp_value = value

            # Staleness guard on components
            if comp_value is not None and _is_stale(comp_value, period):
                in_progress.discard(metric)
                cache[metric] = None
                return None

            # Scope warning on component
            if comp_value is not None:
                scope_warn = get_scope_warning(concept)
                if scope_warn:
                    comp_value.warnings.append(scope_warn)

        if comp_value is None or comp_value.value is None:
            in_progress.discard(metric)
            cache[metric] = None
            return None

        components[comp_name] = comp_value

    # Cross-year validation: all components must share the same fiscal year
    fiscal_years = {comp.fiscal_year for comp in components.values()}
    if len(fiscal_years) > 1:
        in_progress.discard(metric)
        cache[metric] = None
        return None

    # Evaluate formula
    result_value = _eval_formula(meta.formula, components)
    if result_value is None:
        in_progress.discard(metric)
        cache[metric] = None
        return None

    # Use the first component's provenance for the derived value
    first_comp = next(iter(components.values()))

    # Determine unit for derived metrics
    unit = _derived_unit(metric, components)

    derived = DerivedValue(
        value=result_value,
        unit=unit,
        metric=metric,
        concept=meta.formula,
        period_start=first_comp.period_start,
        period_end=first_comp.period_end,
        fiscal_year=first_comp.fiscal_year,
        fiscal_period=first_comp.fiscal_period,
        form_type=first_comp.form_type,
        filed=first_comp.filed,
        accession=first_comp.accession,
        cik=cik,
        company=company,
        taxonomy=first_comp.taxonomy,
        primary_document=first_comp.primary_document,
        derived=True,
        components=components,
    )
    in_progress.discard(metric)
    cache[metric] = derived
    return derived


def _eval_formula(formula: str, components: dict[str, CitedValue]) -> float | None:
    """Evaluate a simple arithmetic formula with component values."""
    vals = {k: float(v.value) for k, v in components.items() if v.value is not None}

    parts = formula.split()
    if len(parts) == 3:
        left_name, op, right_name = parts
        left = vals.get(left_name)
        right = vals.get(right_name)
        if left is None or right is None:
            return None
        if op == "+":
            return left + right
        elif op == "-":
            return left - right
        elif op == "*":
            return left * right
        elif op == "/":
            if right == 0:
                return None
            return left / right
    elif len(parts) == 5:
        # a + b - c  or  a + b + c
        a_name, op1, b_name, op2, c_name = parts
        a = vals.get(a_name)
        b = vals.get(b_name)
        c = vals.get(c_name)
        if a is None or b is None or c is None:
            return None
        result = a
        result = result + b if op1 == "+" else result - b
        result = result + c if op2 == "+" else result - c
        return result

    return None


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
    }
    if metric in ratio_metrics:
        return "pure"

    # Additive/subtractive: inherit from first component
    first = next(iter(components.values()), None)
    return first.unit if first else "USD"
