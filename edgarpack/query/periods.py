"""Period selection and LTM math for SEC financial data.

Handles selecting the right data points from SEC companyfacts JSON based on
period selectors like ``lfy`` (last fiscal year), ``mrq`` (most recent quarter),
``ltm`` (last twelve months), ``annual:N``, and ``quarterly:N``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .concepts import MetricMeta
from .models import CitedValue, DerivedValue


def _parse_date(s: str) -> date | None:
    """Parse ISO date string, returning None on failure."""
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _extract_values(
    facts: dict[str, Any],
    concept: str,
    taxonomy: str = "us-gaap",
) -> list[dict[str, Any]]:
    """Pull all reported values for a concept across all units.

    Returns list of raw SEC value dicts with keys:
        val, start, end, fy, fp, form, accn, filed
    """
    tax = facts.get(taxonomy, {})
    concept_data = tax.get(concept, {})
    units = concept_data.get("units", {})

    # Collect from all unit types, but prefer USD > shares > pure
    for unit_key in ("USD", "shares", "USD/shares", "pure"):
        values = units.get(unit_key)
        if values:
            return list(values)

    # Fallback: first available unit
    for values in units.values():
        if values:
            return list(values)

    return []


def _unit_for_concept(
    facts: dict[str, Any],
    concept: str,
    taxonomy: str = "us-gaap",
) -> str:
    """Determine the unit type for a concept."""
    tax = facts.get(taxonomy, {})
    concept_data = tax.get(concept, {})
    units = concept_data.get("units", {})

    for unit_key in ("USD", "shares", "USD/shares", "pure"):
        if unit_key in units:
            return unit_key

    for key in units:
        return str(key)

    return "USD"


def _value_to_cited(
    v: dict[str, Any],
    metric: str,
    concept: str,
    unit: str,
    company: str,
    cik: str,
) -> CitedValue:
    """Convert a raw SEC value dict to a CitedValue."""
    return CitedValue(
        value=v.get("val"),
        unit=unit,
        metric=metric,
        concept=concept,
        period_start=_parse_date(v.get("start", "")),
        period_end=_parse_date(v.get("end", "")) or date.min,
        fiscal_year=int(v.get("fy", 0)),
        fiscal_period=str(v.get("fp", "")),
        form_type=str(v.get("form", "")),
        filed=_parse_date(v.get("filed", "")) or date.min,
        accession=str(v.get("accn", "")),
        cik=cik,
        company=company,
    )


def _is_annual(v: dict[str, Any]) -> bool:
    """Check if a value is from an annual filing."""
    return str(v.get("fp", "")).upper() == "FY" or str(v.get("form", "")) == "10-K"


def _is_quarterly(v: dict[str, Any]) -> bool:
    """Check if a value is from a quarterly filing."""
    fp = str(v.get("fp", "")).upper()
    return fp in ("Q1", "Q2", "Q3", "Q4")


def _duration_days(v: dict[str, Any]) -> int | None:
    """Compute the number of days between start and end dates.

    Returns None if either date is missing or unparseable.
    """
    start = _parse_date(v.get("start", ""))
    end = _parse_date(v.get("end", ""))
    if start is None or end is None:
        return None
    return (end - start).days


def _is_standalone_quarter(v: dict[str, Any]) -> bool:
    """Check if a duration value is a standalone ~3-month quarter (not cumulative YTD).

    SEC companyfacts often contains both cumulative (e.g. 9-month Q3) and standalone
    (e.g. 3-month Q3) entries for the same quarter and end date. This filter picks
    the standalone one by requiring duration <= 100 days. The 100-day threshold
    accounts for fiscal quarters that aren't exactly 90 days (4-4-5 calendars, etc.).
    """
    days = _duration_days(v)
    if days is None:
        return False
    return days <= 100


def _is_cumulative_quarter(v: dict[str, Any]) -> bool:
    """Check if a duration value is a cumulative YTD value (not standalone quarter).

    For Q1, cumulative and standalone are identical (~90 days). For Q2+, cumulative
    values span from fiscal year start to the quarter end (>100 days).
    """
    days = _duration_days(v)
    if days is None:
        return False
    # Q1 cumulative = standalone (~90 days), so we accept anything with a valid duration
    fp = str(v.get("fp", "")).upper()
    if fp == "Q1":
        return days <= 100  # Q1 cumulative = standalone
    return days > 100


def _quarter_months(fp: str) -> int:
    """Return the cumulative months for a fiscal period (Q1=3, Q2=6, Q3=9)."""
    return {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12, "FY": 12}.get(fp.upper(), 0)


def select_lfy(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
) -> CitedValue | None:
    """Select the last fiscal year value (most recent 10-K annual)."""
    values = _extract_values(facts, concept)
    unit = _unit_for_concept(facts, concept)

    if meta.duration:
        # For P&L/CF: pick most recent FY value
        annual = [v for v in values if _is_annual(v) and v.get("val") is not None]
        if not annual:
            return None
        annual.sort(key=lambda v: (int(v.get("fy", 0)), v.get("end", "")), reverse=True)
        return _value_to_cited(annual[0], metric, concept, unit, company, cik)
    else:
        # For balance sheet: pick most recent 10-K instant
        annual = [
            v for v in values if _is_annual(v) and v.get("val") is not None and not v.get("start")
        ]
        if not annual:
            # Fallback: any annual value
            annual = [v for v in values if _is_annual(v) and v.get("val") is not None]
        if not annual:
            return None
        annual.sort(key=lambda v: (int(v.get("fy", 0)), v.get("end", "")), reverse=True)
        return _value_to_cited(annual[0], metric, concept, unit, company, cik)


def select_mrq(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
) -> CitedValue | None:
    """Select the most recent quarter value.

    For duration concepts (P&L, CF), filters to standalone ~90-day values to avoid
    picking cumulative YTD numbers. SEC companyfacts often has both a 9-month
    cumulative and a 3-month standalone entry for Q3 with the same end date.
    """
    values = _extract_values(facts, concept)
    unit = _unit_for_concept(facts, concept)

    if meta.duration:
        # For P&L/CF: want standalone (3-month) values, not cumulative YTD.
        # Filter by duration <= 100 days to exclude cumulative entries.
        quarterly = [
            v
            for v in values
            if str(v.get("fp", "")).upper() in ("Q1", "Q2", "Q3", "Q4")
            and v.get("val") is not None
            and str(v.get("form", "")) in ("10-Q", "10-K")
            and _is_standalone_quarter(v)
        ]
        if not quarterly:
            return None
        quarterly.sort(
            key=lambda v: (v.get("end", ""), _parse_date(v.get("filed", "")) or date.min),
            reverse=True,
        )
        return _value_to_cited(quarterly[0], metric, concept, unit, company, cik)
    else:
        # For balance sheet: most recent quarterly instant
        quarterly = [v for v in values if _is_quarterly(v) and v.get("val") is not None]
        if not quarterly:
            return None
        quarterly.sort(key=lambda v: v.get("end", ""), reverse=True)
        return _value_to_cited(quarterly[0], metric, concept, unit, company, cik)


def select_mrp(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
) -> CitedValue | None:
    """Select the most recent period (whatever was filed last)."""
    values = _extract_values(facts, concept)
    unit = _unit_for_concept(facts, concept)

    valid = [v for v in values if v.get("val") is not None]
    if not valid:
        return None
    valid.sort(
        key=lambda v: (_parse_date(v.get("filed", "")) or date.min, v.get("end", "")),
        reverse=True,
    )
    return _value_to_cited(valid[0], metric, concept, unit, company, cik)


def select_ltm(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
) -> CitedValue | DerivedValue | None:
    """Compute last twelve months value.

    For duration concepts (P&L, CF):
        LTM = MRP_value + LFY_value - MRP_prior_year_value

    For instant concepts (balance sheet):
        LTM = most recent reported value.
    """
    if not meta.duration:
        # Balance sheet: just return the most recent value
        return select_mrp(facts, concept, metric, meta, company, cik)

    values = _extract_values(facts, concept)
    unit = _unit_for_concept(facts, concept)

    # Find the most recent 10-Q cumulative value (MRP).
    # The LTM formula requires cumulative YTD values. When multiple entries exist
    # for the same quarter end date (cumulative + standalone), pick the longest
    # duration (the cumulative one).
    quarterly = [
        v
        for v in values
        if str(v.get("form", "")) == "10-Q"
        and v.get("val") is not None
        and v.get("start")
        and v.get("end")
    ]
    if not quarterly:
        # No quarterly data; fall back to last annual
        return select_lfy(facts, concept, metric, meta, company, cik)

    # Sort by end date (most recent first), then by duration descending (longest = cumulative)
    quarterly.sort(
        key=lambda v: (v.get("end", ""), _duration_days(v) or 0),
        reverse=True,
    )
    mrp = quarterly[0]

    mrp_fp = str(mrp.get("fp", "")).upper()
    mrp_fy = int(mrp.get("fy", 0))

    # If MRP is Q4/FY equivalent, no LTM calc needed
    if mrp_fp in ("FY", "Q4"):
        return _value_to_cited(mrp, metric, concept, unit, company, cik)

    # Find the LFY (annual value for the prior fiscal year)
    annual = [v for v in values if _is_annual(v) and v.get("val") is not None]
    if not annual:
        return _value_to_cited(mrp, metric, concept, unit, company, cik)

    annual.sort(key=lambda v: int(v.get("fy", 0)), reverse=True)

    # LFY should be the fiscal year before or equal to the MRP's fiscal year
    lfy = None
    for v in annual:
        fy = int(v.get("fy", 0))
        if fy <= mrp_fy:
            lfy = v
            break

    if lfy is None:
        return _value_to_cited(mrp, metric, concept, unit, company, cik)

    lfy_fy = int(lfy.get("fy", 0))

    # Find MRP_prior: same fiscal period, one year earlier.
    # Must also be cumulative (longest duration) to match the MRP we picked.
    prior_year = [
        v
        for v in values
        if str(v.get("form", "")) == "10-Q"
        and str(v.get("fp", "")).upper() == mrp_fp
        and int(v.get("fy", 0)) == lfy_fy
        and v.get("val") is not None
    ]

    if not prior_year:
        # Can't compute LTM without prior year comparable
        return _value_to_cited(mrp, metric, concept, unit, company, cik)

    # Pick the cumulative (longest duration) entry
    prior_year.sort(key=lambda v: _duration_days(v) or 0, reverse=True)
    mrp_prior = prior_year[0]

    # LTM = MRP + LFY - MRP_prior
    mrp_val = float(mrp.get("val", 0))
    lfy_val = float(lfy.get("val", 0))
    prior_val = float(mrp_prior.get("val", 0))
    ltm_val = mrp_val + lfy_val - prior_val

    mrp_cited = _value_to_cited(mrp, metric, concept, unit, company, cik)
    lfy_cited = _value_to_cited(lfy, metric, concept, unit, company, cik)
    prior_cited = _value_to_cited(mrp_prior, metric, concept, unit, company, cik)

    return DerivedValue(
        value=ltm_val,
        unit=unit,
        metric=metric,
        concept=concept,
        period_start=mrp_cited.period_start,
        period_end=mrp_cited.period_end,
        fiscal_year=mrp_cited.fiscal_year,
        fiscal_period="LTM",
        form_type="LTM",
        filed=mrp_cited.filed,
        accession=mrp_cited.accession,
        cik=cik,
        company=company,
        derived=True,
        components={
            "mrp": mrp_cited,
            "lfy": lfy_cited,
            "mrp_prior": prior_cited,
        },
    )


def select_annual_series(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    n: int = 3,
) -> list[CitedValue]:
    """Select the last N fiscal year values."""
    values = _extract_values(facts, concept)
    unit = _unit_for_concept(facts, concept)

    annual = [v for v in values if _is_annual(v) and v.get("val") is not None]
    annual.sort(key=lambda v: int(v.get("fy", 0)), reverse=True)

    results = []
    seen_fy: set[int] = set()
    for v in annual:
        fy = int(v.get("fy", 0))
        if fy in seen_fy:
            continue
        seen_fy.add(fy)
        results.append(_value_to_cited(v, metric, concept, unit, company, cik))
        if len(results) >= n:
            break

    return results


def select_quarterly_series(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    n: int = 4,
) -> list[CitedValue]:
    """Select the last N quarterly values.

    For duration concepts, filters to standalone ~90-day values (same logic as MRQ)
    to avoid returning cumulative YTD numbers in the series.
    """
    values = _extract_values(facts, concept)
    unit = _unit_for_concept(facts, concept)

    if meta.duration:
        # Duration concepts: filter to standalone quarters only
        quarterly = [
            v
            for v in values
            if _is_quarterly(v) and v.get("val") is not None and _is_standalone_quarter(v)
        ]
    else:
        # Instant concepts: no duration filtering needed
        quarterly = [v for v in values if _is_quarterly(v) and v.get("val") is not None]

    quarterly.sort(
        key=lambda v: (int(v.get("fy", 0)), _quarter_months(str(v.get("fp", "")))),
        reverse=True,
    )

    results = []
    seen: set[tuple[int, str]] = set()
    for v in quarterly:
        key = (int(v.get("fy", 0)), str(v.get("fp", "")))
        if key in seen:
            continue
        seen.add(key)
        results.append(_value_to_cited(v, metric, concept, unit, company, cik))
        if len(results) >= n:
            break

    return results


def select_period(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    period: str = "lfy",
) -> CitedValue | DerivedValue | list[CitedValue] | None:
    """Route to the appropriate period selector.

    Args:
        facts: The ``facts`` dict from SEC companyfacts JSON.
        concept: GAAP concept name.
        metric: Normalized metric name.
        meta: Metric metadata.
        company: Company name.
        cik: CIK number.
        period: Period selector string.

    Returns:
        CitedValue, list of CitedValues (for series), or None.
    """
    period = period.strip().lower()

    if period == "lfy":
        return select_lfy(facts, concept, metric, meta, company, cik)
    elif period == "mrq":
        return select_mrq(facts, concept, metric, meta, company, cik)
    elif period == "mrp":
        return select_mrp(facts, concept, metric, meta, company, cik)
    elif period == "ltm":
        return select_ltm(facts, concept, metric, meta, company, cik)
    elif period.startswith("annual:"):
        n = int(period.split(":")[1])
        return select_annual_series(facts, concept, metric, meta, company, cik, n=n)
    elif period.startswith("quarterly:"):
        n = int(period.split(":")[1])
        return select_quarterly_series(facts, concept, metric, meta, company, cik, n=n)
    else:
        raise ValueError(f"Unknown period selector: {period}")
