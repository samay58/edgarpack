"""Single-company financial queries with full citation provenance."""

from __future__ import annotations

from typing import Any

from ..sec.tickers import resolve_ticker
from ..sec.xbrl import fetch_company_facts
from .concepts import ALL_METRICS, METRIC_MAP, resolve_concept
from .models import CitedValue, DerivedValue, QueryResult
from .periods import select_period


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
        period: Period selector: "lfy", "mrq", "ltm", "mrp",
                "annual:N", "quarterly:N".
        force: Bypass cache.

    Returns:
        QueryResult with cited values for each requested metric.
    """
    cik, company_name = await resolve_ticker(company, force=force)

    facts_data = await fetch_company_facts(cik, force=force)
    facts = facts_data.get("facts", {})

    if metrics is None:
        metric_list = list(ALL_METRICS)
    elif isinstance(metrics, str):
        metric_list = [m.strip() for m in metrics.split(",")]
    else:
        metric_list = list(metrics)

    result_metrics: dict[str, CitedValue | list[CitedValue] | None] = {}

    for metric in metric_list:
        meta = METRIC_MAP.get(metric)
        if meta is None:
            result_metrics[metric] = None
            continue

        if meta.derived:
            cited = _compute_derived(facts, metric, meta, company_name, cik, period)
            result_metrics[metric] = cited
        else:
            resolved = resolve_concept(metric, facts)
            if resolved is None:
                result_metrics[metric] = None
                continue

            concept, taxonomy = resolved
            value = select_period(
                facts, concept, metric, meta, company_name, cik, period, taxonomy=taxonomy
            )

            if isinstance(value, list):
                result_metrics[metric] = value if value else None
            else:
                result_metrics[metric] = value

    return QueryResult(company=company_name, cik=cik, period=period, metrics=result_metrics)


def _compute_derived(
    facts: dict[str, Any],
    metric: str,
    meta: Any,
    company: str,
    cik: str,
    period: str,
) -> CitedValue | None:
    """Compute a derived metric from its components."""
    if not meta.components or not meta.formula:
        return None

    components: dict[str, CitedValue] = {}

    for comp_name in meta.components:
        comp_meta = METRIC_MAP.get(comp_name)
        if comp_meta is None:
            return None

        if comp_meta.derived:
            # Recursive derived metric (e.g., ebitda needs operating_income + d&a)
            comp_value = _compute_derived(facts, comp_name, comp_meta, company, cik, period)
        else:
            resolved = resolve_concept(comp_name, facts)
            if resolved is None:
                return None
            concept, taxonomy = resolved
            value = select_period(
                facts, concept, comp_name, comp_meta, company, cik, period, taxonomy=taxonomy
            )
            if isinstance(value, list):
                comp_value = value[0] if value else None
            else:
                comp_value = value

        if comp_value is None or comp_value.value is None:
            return None

        components[comp_name] = comp_value

    # Cross-year validation: all components must share the same fiscal year
    fiscal_years = {comp.fiscal_year for comp in components.values()}
    if len(fiscal_years) > 1:
        return None

    # Evaluate formula
    result_value = _eval_formula(meta.formula, components)
    if result_value is None:
        return None

    # Use the first component's provenance for the derived value
    first_comp = next(iter(components.values()))

    # Determine unit for derived metrics
    unit = _derived_unit(metric, components)

    return DerivedValue(
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
        derived=True,
        components=components,
    )


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
