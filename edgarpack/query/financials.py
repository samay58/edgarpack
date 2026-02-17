"""Single-company financial queries with full citation provenance."""

from __future__ import annotations

from typing import Any

from ..sec.submissions import fetch_submissions
from ..sec.tickers import resolve_ticker
from ..sec.xbrl import fetch_company_facts
from .concepts import ALL_METRICS, METRIC_MAP, MetricMeta, resolve_concept
from .models import CitedValue, DerivedValue, QueryResult
from .periods import select_period

_DerivedCache = dict[str, CitedValue | None]


async def _build_doc_map(cik: str, force: bool = False) -> dict[str, str]:
    """Build {accession: primaryDocument} from submissions (cached 1hr).

    Returns empty dict on failure so callers degrade gracefully.
    """
    try:
        data = await fetch_submissions(cik, force=force)
    except Exception:
        return {}

    filings = data.get("filings", {}).get("recent", {})
    accessions = filings.get("accessionNumber", [])
    docs = filings.get("primaryDocument", [])

    doc_map: dict[str, str] = {}
    for acc, doc in zip(accessions, docs):
        if acc and doc:
            doc_map[acc] = doc
    return doc_map


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

    result_metrics: dict[str, CitedValue | list[CitedValue] | None] = {}
    derived_cache: _DerivedCache = {}

    for metric in metric_list:
        meta = METRIC_MAP.get(metric)
        if meta is None:
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
            result_metrics[metric] = cited
        else:
            resolved = resolve_concept(metric, facts)
            if resolved is None:
                result_metrics[metric] = None
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
                result_metrics[metric] = value if value else None
            else:
                result_metrics[metric] = value

    # Post-resolution sanity check: flag anomalously low total_debt relative
    # to total_liabilities.  Companies with captive finance subsidiaries
    # (e.g. Ford) may stop tagging consolidated debt in standard XBRL while
    # total liabilities remain correctly reported.
    _check_low_debt(result_metrics, facts, company_name, cik, period, doc_map)

    return QueryResult(company=company_name, cik=cik, period=period, metrics=result_metrics)


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
