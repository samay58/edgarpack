"""Period selection and LTM math for SEC financial data.

Handles selecting the right data points from SEC companyfacts JSON based on
period selectors like ``lfy`` (last fiscal year), ``mrq`` / ``mrq-N`` (most
recent quarter, same fiscal quarter N years back), ``ltm`` / ``ltm-N``
(trailing twelve month windows, current and N years back), ``annual:N``,
``quarterly:N``, and ``lfy-N`` (fiscal year N positions back from the latest;
e.g. ``lfy-1`` = prior FY, ``lfy-0`` is equivalent to ``lfy``).

The top-level CLI also accepts a comma-separated list of scalar selectors
(parsed by ``parse_period_spec``) to render a multi-period grid.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .concepts import MetricMeta
from .models import CitedValue, DerivedValue, Diagnostic

# Regex to capture entire ix:nonFraction elements (opening tag + inner text).
_IX_NONFRACTION_TAG_RE = re.compile(
    r"<ix:nonFraction\b([^>]*)>([^<]*)</ix:nonFraction>",
    re.IGNORECASE | re.DOTALL,
)
# Attribute extractors (order-independent)
_ATTR_NAME_RE = re.compile(r'\bname="([^"]+)"', re.IGNORECASE)
_ATTR_ID_RE = re.compile(r'\bid="([^"]+)"', re.IGNORECASE)
_ATTR_SCALE_RE = re.compile(r'\bscale="([^"]*)"', re.IGNORECASE)
_ATTR_SIGN_RE = re.compile(r'\bsign="([^"]*)"', re.IGNORECASE)

_FULL_YEAR_MIN_DAYS = 350
_FULL_YEAR_MAX_DAYS = 380


def _parse_display_value(text: str, scale: str, sign: str) -> float | None:
    """Parse the displayed value from an ix:nonFraction element.

    Strips formatting (commas, parens, whitespace), applies the XBRL ``scale``
    multiplier, and the optional ``sign`` attribute. The ``sign`` attribute is
    authoritative for the value's sign; parentheses in the display text are
    purely visual formatting.
    """
    text = text.strip()
    if not text:
        return None
    # Remove non-breaking spaces
    text = text.replace("\xa0", "").replace("&nbsp;", "")
    # Strip parens (display-only formatting; sign attr is authoritative)
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    text = text.replace(",", "").replace("$", "").replace("%", "").strip()
    if not text:
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    # sign attribute is the authoritative sign indicator
    if sign == "-":
        val = -val
    if scale:
        try:
            val *= 10 ** int(scale)
        except ValueError:
            pass
    return val


def parse_fact_ids_from_html(html: str | bytes) -> dict[tuple[str, float], str]:
    """Extract ``(concept_short, scaled_value) -> fact_id`` from inline XBRL HTML.

    The matching strategy: within a single filing, the same concept at different
    periods almost always has a different dollar value. So ``(concept, value)``
    is a reliable composite key. If duplicates exist (rare), the first occurrence
    wins. Financial statements appear before the notes section, so the canonical
    element keeps its fact_id.
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")

    result: dict[tuple[str, float], str] = {}

    for m in _IX_NONFRACTION_TAG_RE.finditer(html):
        attrs, display_text = m.groups()

        name_m = _ATTR_NAME_RE.search(attrs)
        id_m = _ATTR_ID_RE.search(attrs)
        if not name_m or not id_m:
            continue

        concept_full = name_m.group(1)
        fact_id = id_m.group(1)

        scale_m = _ATTR_SCALE_RE.search(attrs)
        sign_m = _ATTR_SIGN_RE.search(attrs)
        scale = scale_m.group(1) if scale_m else ""
        sign = sign_m.group(1) if sign_m else ""

        # Strip taxonomy prefix: "us-gaap:Revenues" -> "Revenues"
        concept_short = concept_full.split(":")[-1] if ":" in concept_full else concept_full

        parsed_val = _parse_display_value(display_text, scale, sign)
        if parsed_val is not None:
            key = (concept_short, parsed_val)
            # First occurrence wins (financial statements appear before notes)
            if key not in result:
                result[key] = fact_id

    return result


def _lookup_fact_id(
    fact_id_map: dict[tuple[str, float], str] | None,
    concept: str,
    val: float | int | None,
) -> str:
    """Look up a fact_id from the parsed map using (concept, value)."""
    if not fact_id_map or val is None:
        return ""
    # Strip taxonomy prefix if present
    concept_short = concept.split(":")[-1] if ":" in concept else concept
    fact_id = fact_id_map.get((concept_short, float(val)), "")
    return fact_id


def _parse_date(s: str) -> date | None:
    """Parse ISO date string, returning None on failure."""
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _filter_segment_entries(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer consolidated entries over segment-level breakouts.

    SEC companyfacts includes both consolidated and dimensional/segment values
    for the same concept. Consolidated entries carry a ``frame`` field (e.g.
    ``CY2024Q4I``); segment breakouts do not. When multiple entries share the
    same filing context (accession, fiscal year/period, date span), entries
    with ``frame`` are kept and unframed duplicates are dropped.
    """
    by_context: dict[tuple, list[dict[str, Any]]] = {}
    for v in values:
        key = (
            v.get("accn", ""),
            v.get("fy"),
            v.get("fp", ""),
            v.get("start", ""),
            v.get("end", ""),
        )
        by_context.setdefault(key, []).append(v)

    result: list[dict[str, Any]] = []
    for group in by_context.values():
        if len(group) == 1:
            result.append(group[0])
            continue

        framed = [v for v in group if v.get("frame")]
        if framed:
            result.extend(framed)
        else:
            # No frame data: keep entry with largest absolute value
            # (consolidated totals are larger than segment breakdowns).
            group.sort(key=lambda v: abs(v.get("val") or 0), reverse=True)
            result.append(group[0])

    return result


def _extract_values(
    facts: dict[str, Any],
    concept: str,
    taxonomy: str = "us-gaap",
) -> list[dict[str, Any]]:
    """Pull all reported values for a concept across all units.

    Prefers consolidated values over segment-level breakouts. SEC companyfacts
    tags consolidated entries with a ``frame`` field; segment disclosures lack
    it. When multiple entries share the same filing context, framed entries win.

    Returns list of raw SEC value dicts with keys:
        val, start, end, fy, fp, form, accn, filed
    """
    tax = facts.get(taxonomy, {})
    concept_data = tax.get(concept, {})
    units = concept_data.get("units", {})

    raw: list[dict[str, Any]] = []
    for unit_key in ("USD", "shares", "USD/shares", "pure"):
        values = units.get(unit_key)
        if values:
            raw = list(values)
            break

    if not raw:
        for values in units.values():
            if values:
                raw = list(values)
                break

    if not raw:
        return []

    return _filter_segment_entries(raw)


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
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
) -> CitedValue:
    """Convert a raw SEC value dict to a CitedValue."""
    accn = str(v.get("accn", ""))
    primary_doc = ""
    if doc_map and accn:
        primary_doc = doc_map.get(accn, "")
    return CitedValue(
        value=v.get("val"),
        unit=unit,
        metric=metric,
        concept=concept,
        period_start=_parse_date(v.get("start", "")),
        period_end=_parse_date(v.get("end", "")) or date.min,
        fiscal_year=int(v.get("fy") or 0),
        fiscal_period=str(v.get("fp", "")),
        form_type=str(v.get("form", "")),
        filed=_parse_date(v.get("filed", "")) or date.min,
        accession=accn,
        cik=cik,
        company=company,
        taxonomy=taxonomy,
        primary_document=primary_doc,
    )


def _is_annual(v: dict[str, Any]) -> bool:
    """Check if a value is from an annual filing."""
    form = str(v.get("form", "")).upper()
    return str(v.get("fp", "")).upper() == "FY" or form in ("10-K", "10-K/A", "20-F", "20-F/A")


def _is_quarterly(v: dict[str, Any]) -> bool:
    """Check if a value is from a quarterly filing."""
    fp = str(v.get("fp", "")).upper()
    return fp in ("Q1", "Q2", "Q3", "Q4")


def _is_quarter_form_type(form: str) -> bool:
    """Check if a form type can carry quarterly values."""
    form_upper = form.strip().upper()
    return form_upper.startswith("10-Q") or form_upper in ("10-K", "10-K/A", "20-F", "20-F/A")


def _duration_days(v: dict[str, Any]) -> int | None:
    """Compute the number of days between start and end dates.

    Returns None if either date is missing or unparseable.
    """
    start = _parse_date(v.get("start", ""))
    end = _parse_date(v.get("end", ""))
    if start is None or end is None:
        return None
    days = (end - start).days
    return days if days >= 0 else None


def _is_full_fiscal_year(v: dict[str, Any]) -> bool:
    """Check whether an annual duration spans a full fiscal year."""
    days = _duration_days(v)
    if days is None:
        return False
    return _FULL_YEAR_MIN_DAYS <= days <= _FULL_YEAR_MAX_DAYS


def _annual_sort_key(v: dict[str, Any]) -> tuple[int, date, date]:
    """Sort annual entries by fiscal year then filing/end recency."""
    return (
        int(v.get("fy") or 0),
        _parse_date(v.get("filed", "")) or date.min,
        _parse_date(v.get("end", "")) or date.min,
    )


def _best_annual_entry(values: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the best annual entry for one fiscal year.

    Preference order:
    1. Full-year annual durations (350-380 days)
    2. Any annual entry (for sparse/no-duration datasets)
    """
    if not values:
        return None
    full_year = [v for v in values if _is_full_fiscal_year(v)]
    candidates = full_year if full_year else values
    candidates.sort(key=_annual_sort_key, reverse=True)
    return candidates[0] if candidates else None


def _annual_history(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a de-duplicated annual history with one best entry per FY."""
    annual_raw: list[dict[str, Any]] = []
    for v in values:
        if _is_annual(v) and v.get("val") is not None:
            annual_raw.append(v)

    has_full_year = any(_is_full_fiscal_year(v) for v in annual_raw)

    by_fy: dict[int, list[dict[str, Any]]] = {}
    for v in annual_raw:
        if has_full_year:
            days = _duration_days(v)
            if days is not None and not _is_full_fiscal_year(v):
                # Drop known stub/partial annual windows when full-year entries exist.
                continue
        fy = int(v.get("fy") or 0)
        if fy <= 0:
            continue
        by_fy.setdefault(fy, []).append(v)

    annual: list[dict[str, Any]] = []
    for entries in by_fy.values():
        best = _best_annual_entry(entries)
        if best is not None:
            annual.append(best)

    annual.sort(key=_annual_sort_key, reverse=True)
    return annual


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


def _is_per_share_metric(metric: str) -> bool:
    """Check if a metric is per-share (sensitive to stock splits)."""
    m = metric.lower()
    return "per_share" in m or "eps" in m


def _quarter_months(fp: str) -> int:
    """Return the cumulative months for a fiscal period (Q1=3, Q2=6, Q3=9)."""
    return {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12, "FY": 12}.get(fp.upper(), 0)


def _quarter_recency_key(v: dict[str, Any]) -> tuple[date, int, int, date]:
    """Sort quarterly entries by period recency and filing recency."""
    return (
        _parse_date(v.get("end", "")) or date.min,
        int(v.get("fy") or 0),
        _quarter_months(str(v.get("fp", ""))),
        _parse_date(v.get("filed", "")) or date.min,
    )


def _pick_cumulative_quarter(values: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the best cumulative quarter entry from a single fiscal period."""
    if not values:
        return None
    cumulative = [v for v in values if _is_cumulative_quarter(v)]
    candidates = cumulative if cumulative else values
    candidates.sort(
        key=lambda v: (_duration_days(v) or -1, _parse_date(v.get("filed", "")) or date.min),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _pick_anchor_quarter(
    quarterly: list[dict[str, Any]],
    newest: dict[str, Any],
    years_back: int,
) -> dict[str, Any]:
    """Pick the quarter anchor for LTM-like windows.

    ``years_back=0`` anchors to the newest quarter (LTM).
    ``years_back=1`` anchors one fiscal year earlier (LTM-1).
    """
    newest_fp = str(newest.get("fp", "")).upper()
    newest_fy = int(newest.get("fy") or 0)

    if years_back <= 0:
        return newest

    same_period = [
        v
        for v in quarterly
        if str(v.get("fp", "")).upper() == newest_fp and v.get("val") is not None
    ]
    target_fy = newest_fy - years_back
    target = [v for v in same_period if int(v.get("fy") or 0) == target_fy]
    if target:
        picked = _pick_cumulative_quarter(target)
        if picked is not None:
            return picked

    # Graceful fallback for sparse histories: nearest prior fiscal year same quarter.
    prior = [v for v in same_period if int(v.get("fy") or 0) < newest_fy]
    if prior:
        best_fy = max(int(v.get("fy") or 0) for v in prior)
        best = [v for v in prior if int(v.get("fy") or 0) == best_fy]
        picked = _pick_cumulative_quarter(best)
        if picked is not None:
            return picked

    return newest


def _annual_for_fy(values: list[dict[str, Any]], fiscal_year: int) -> dict[str, Any] | None:
    """Pick the most recently filed annual value for a specific fiscal year."""
    annual = [
        v
        for v in values
        if _is_annual(v) and v.get("val") is not None and int(v.get("fy") or 0) == fiscal_year
    ]
    return _best_annual_entry(annual)


def _assert_ltm_invariant(
    result: CitedValue | DerivedValue | None,
    fiscal_period_label: str,
) -> None:
    """Enforce the LTM citation contract at every _select_ltm_like return point.

    Valid shapes:
    - ``None``: caller will see a Diagnostic in QueryResult.
    - ``DerivedValue`` with fiscal_period in {LTM, LTM-1} and components
      carrying roles {mrp, lfy, mrp_prior}. This is a genuine trailing-twelve
      computation: MRP + LFY - MRP_prior.
    - Plain ``CitedValue`` with fiscal_period in {FY, Q4}. MRP anchor was a
      full fiscal year, so the 10-K/20-F annual value IS the LTM and no
      math was needed.

    Any other shape means the silent-fallback path reopened and is returning
    a 9-month or 6-month YTD mislabeled as LTM. Fail loudly.
    """
    if result is None:
        return
    if isinstance(result, DerivedValue):
        roles = set(result.components.keys())
        if not roles >= {"mrp", "lfy", "mrp_prior"}:
            raise RuntimeError(
                f"LTM invariant: DerivedValue missing roles. "
                f"Got {roles}, need {{mrp, lfy, mrp_prior}} "
                f"(fiscal_period_label={fiscal_period_label})"
            )
        if not result.fiscal_period.upper().startswith("LTM"):
            raise RuntimeError(
                f"LTM invariant: DerivedValue fiscal_period={result.fiscal_period!r}, "
                f"expected LTM* (fiscal_period_label={fiscal_period_label})"
            )
        return
    if result.fiscal_period.upper() not in ("FY", "Q4"):
        raise RuntimeError(
            f"LTM invariant: plain CitedValue with fiscal_period={result.fiscal_period!r}, "
            f"expected FY or Q4 (annual early-exit) "
            f"(fiscal_period_label={fiscal_period_label})"
        )


def _select_ltm_like(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    years_back: int,
    fiscal_period_label: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    diagnostics: list[Diagnostic] | None = None,
) -> CitedValue | DerivedValue | None:
    """Compute LTM-style periods anchored to a shifted quarter."""

    def _finalize(
        result: CitedValue | DerivedValue | None,
    ) -> CitedValue | DerivedValue | None:
        _assert_ltm_invariant(result, fiscal_period_label)
        return result

    def _record_incomputable(reason: str) -> None:
        if diagnostics is None:
            return
        diagnostics.append(
            Diagnostic(
                metric=metric,
                kind="ltm_incomputable",
                message=(
                    f"LTM ({fiscal_period_label}) for {metric} not computable: {reason}. "
                    f"Need MRP cumulative + prior FY annual + same-quarter prior-year "
                    f"cumulative; refusing to return YTD as LTM."
                ),
            )
        )

    if _is_per_share_metric(metric):
        # EPS/per-share metrics are non-additive; use annual values for LTM-like
        # selectors so comparisons are mathematically sound.
        values = _extract_values(facts, concept, taxonomy=taxonomy)
        unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)
        annual = _annual_history(values)
        if len(annual) <= years_back:
            return _finalize(None)
        return _finalize(
            _value_to_cited(
                annual[years_back],
                metric,
                concept,
                unit,
                company,
                cik,
                taxonomy=taxonomy,
                doc_map=doc_map,
            )
        )

    if not meta.duration:
        # Balance sheet: just return the most recent value.
        # Balance-sheet metrics are instants; the MRP balance is the LTM-end
        # balance by definition, so we intentionally bypass the LTM invariant
        # (fiscal_period will be Q1/Q2/Q3 for mid-year queries).
        return select_mrp(
            facts, concept, metric, meta, company, cik, taxonomy=taxonomy, doc_map=doc_map
        )

    values = _extract_values(facts, concept, taxonomy=taxonomy)
    unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)

    quarterly = [
        v
        for v in values
        if _is_quarter_form_type(str(v.get("form", "")))
        and _is_quarterly(v)
        and v.get("val") is not None
        and v.get("start")
        and v.get("end")
    ]
    if not quarterly:
        if years_back == 0:
            # Annual-only filer, current period: LFY annual IS the LTM.
            return _finalize(
                select_lfy(
                    facts,
                    concept,
                    metric,
                    meta,
                    company,
                    cik,
                    taxonomy=taxonomy,
                    doc_map=doc_map,
                )
            )
        # Annual-only filer, prior-year LTM-1: return the (years_back+1)th most
        # recent full-year annual value, skipping short stub periods.
        annual = _annual_history(values)
        if len(annual) <= years_back:
            _record_incomputable(
                f"annual-only filer with insufficient history "
                f"(have {len(annual)}, need > {years_back})"
            )
            return _finalize(None)
        target = annual[years_back]
        return _finalize(
            _value_to_cited(
                target, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
            )
        )

    quarterly.sort(key=_quarter_recency_key, reverse=True)
    newest = quarterly[0]
    newest_key = (
        int(newest.get("fy") or 0),
        str(newest.get("fp", "")).upper(),
        _parse_date(newest.get("end", "")) or date.min,
    )
    newest_candidates = [
        v
        for v in quarterly
        if (
            int(v.get("fy") or 0),
            str(v.get("fp", "")).upper(),
            _parse_date(v.get("end", "")) or date.min,
        )
        == newest_key
    ]
    newest_mrp = _pick_cumulative_quarter(newest_candidates) or newest
    mrp = _pick_anchor_quarter(quarterly, newest_mrp, years_back)

    mrp_fp = str(mrp.get("fp", "")).upper()
    mrp_fy = int(mrp.get("fy") or 0)

    if years_back == 0 and mrp_fp in ("FY", "Q4"):
        annual_mrp = _annual_for_fy(values, mrp_fy)
        if annual_mrp is not None:
            return _finalize(
                _value_to_cited(
                    annual_mrp,
                    metric,
                    concept,
                    unit,
                    company,
                    cik,
                    taxonomy=taxonomy,
                    doc_map=doc_map,
                )
            )
        return _finalize(
            _value_to_cited(
                mrp, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
            )
        )

    annual = _annual_history(values)
    if not annual:
        _record_incomputable(
            f"no annual history for concept (MRP={mrp_fp} FY{mrp_fy})"
        )
        return _finalize(None)

    lfy_target_fy = mrp_fy - 1
    lfy = next((v for v in annual if int(v.get("fy") or 0) == lfy_target_fy), None)
    if lfy is None:
        lfy = next((v for v in annual if int(v.get("fy") or 0) < mrp_fy), None)
    if lfy is None:
        _record_incomputable(
            f"no prior FY annual (looking for FY{lfy_target_fy} or earlier; MRP={mrp_fp} FY{mrp_fy})"
        )
        return _finalize(None)

    lfy_fy = int(lfy.get("fy") or 0)
    prior_year = [
        v
        for v in quarterly
        if str(v.get("fp", "")).upper() == mrp_fp
        and int(v.get("fy") or 0) == lfy_fy
        and v.get("val") is not None
    ]
    mrp_prior = _pick_cumulative_quarter(prior_year)
    if mrp_prior is None:
        _record_incomputable(
            f"no matching {mrp_fp} cumulative entry for FY{lfy_fy} "
            f"(MRP={mrp_fp} FY{mrp_fy})"
        )
        return _finalize(None)

    mrp_val = float(mrp.get("val") or 0)
    lfy_val = float(lfy.get("val") or 0)
    prior_val = float(mrp_prior.get("val") or 0)
    ltm_val = mrp_val + lfy_val - prior_val

    mrp_cited = _value_to_cited(
        mrp, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
    )
    lfy_cited = _value_to_cited(
        lfy, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
    )
    prior_cited = _value_to_cited(
        mrp_prior, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
    )

    # Stock split contamination check for per-share metrics
    split_warnings: list[str] = []
    if _is_per_share_metric(metric) and lfy_cited.value and lfy_cited.value != 0:
        ratio = abs(ltm_val / lfy_cited.value)
        if ratio > 5.0 or ratio < 0.2:
            split_warnings.append(
                f"Possible stock split contamination: LTM-derived value differs "
                f"from annual by {ratio:.1f}x"
            )

    return _finalize(
        DerivedValue(
            value=ltm_val,
            unit=unit,
            metric=metric,
            concept=concept,
            period_start=lfy_cited.period_start,
            period_end=mrp_cited.period_end,
            fiscal_year=mrp_cited.fiscal_year,
            fiscal_period=fiscal_period_label,
            form_type=mrp_cited.form_type,
            filed=mrp_cited.filed,
            accession=mrp_cited.accession,
            cik=cik,
            company=company,
            taxonomy=taxonomy,
            primary_document=mrp_cited.primary_document,
            derived=True,
            components={
                "mrp": mrp_cited,
                "lfy": lfy_cited,
                "mrp_prior": prior_cited,
            },
            warnings=split_warnings,
        )
    )


def select_lfy(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    period_offset: int = 0,
) -> CitedValue | None:
    """Select the last fiscal year value (most recent 10-K/20-F annual).

    When ``period_offset`` is negative, walk back N fiscal years from the
    latest. E.g. ``period_offset=-1`` returns the prior fiscal year.
    """
    values = _extract_values(facts, concept, taxonomy=taxonomy)
    unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)

    # offset=-1 means "one FY back", so the target index is abs(offset).
    target_idx = -period_offset if period_offset <= 0 else 0

    if meta.duration:
        # For P&L/CF: pick most recent FY value
        annual = _annual_history(values)
        if not annual or target_idx >= len(annual):
            return None
        return _value_to_cited(
            annual[target_idx],
            metric,
            concept,
            unit,
            company,
            cik,
            taxonomy=taxonomy,
            doc_map=doc_map,
        )
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
        annual.sort(key=lambda v: (int(v.get("fy") or 0), v.get("end", "")), reverse=True)
        if target_idx >= len(annual):
            return None
        return _value_to_cited(
            annual[target_idx],
            metric,
            concept,
            unit,
            company,
            cik,
            taxonomy=taxonomy,
            doc_map=doc_map,
        )


def select_mrq(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
) -> CitedValue | None:
    """Select the most recent quarter value.

    For duration concepts (P&L, CF), filters to standalone ~90-day values to avoid
    picking cumulative YTD numbers. SEC companyfacts often has both a 9-month
    cumulative and a 3-month standalone entry for Q3 with the same end date.
    """
    return select_mrq_n(
        facts, concept, metric, meta, company, cik, taxonomy=taxonomy, doc_map=doc_map, years_back=0
    )


def select_mrq_n(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    years_back: int = 0,
) -> CitedValue | None:
    """Select the MRQ anchored N fiscal years back.

    For ``years_back=0`` reduces to current MRQ (latest standalone quarter).
    For ``years_back>=1`` returns the same fiscal quarter (``fp``) N fiscal
    years before the latest quarter. Degrades to the nearest prior FY that has
    an entry for the same ``fp`` when the exact target is missing.
    """
    values = _extract_values(facts, concept, taxonomy=taxonomy)
    unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)

    if meta.duration:
        # Duration concepts: want standalone 3-month values, not YTD cumulative.
        quarterly = [
            v
            for v in values
            if str(v.get("fp", "")).upper() in ("Q1", "Q2", "Q3", "Q4")
            and v.get("val") is not None
            and _is_quarter_form_type(str(v.get("form", "")))
            and _is_standalone_quarter(v)
        ]
        if not quarterly:
            return None
        quarterly.sort(
            key=lambda v: (v.get("end", ""), _parse_date(v.get("filed", "")) or date.min),
            reverse=True,
        )
        newest = quarterly[0]
        if years_back <= 0:
            return _value_to_cited(
                newest, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
            )

        newest_fp = str(newest.get("fp", "")).upper()
        newest_fy = int(newest.get("fy") or 0)
        target_fy = newest_fy - years_back
        same_fp = [
            v
            for v in quarterly
            if str(v.get("fp", "")).upper() == newest_fp and v.get("val") is not None
        ]
        exact = [v for v in same_fp if int(v.get("fy") or 0) == target_fy]
        if exact:
            exact.sort(
                key=lambda v: (v.get("end", ""), _parse_date(v.get("filed", "")) or date.min),
                reverse=True,
            )
            return _value_to_cited(
                exact[0], metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
            )

        # Degrade: nearest prior FY with a matching fp.
        prior = [v for v in same_fp if int(v.get("fy") or 0) < newest_fy]
        if prior:
            best_fy = max(int(v.get("fy") or 0) for v in prior)
            candidates = [v for v in prior if int(v.get("fy") or 0) == best_fy]
            candidates.sort(
                key=lambda v: (v.get("end", ""), _parse_date(v.get("filed", "")) or date.min),
                reverse=True,
            )
            return _value_to_cited(
                candidates[0],
                metric,
                concept,
                unit,
                company,
                cik,
                taxonomy=taxonomy,
                doc_map=doc_map,
            )
        return None
    else:
        # Instant concepts: most recent quarterly snapshot, years_back ignored
        # because a balance sheet has one point per period, and mrq-N for a
        # balance sheet is conceptually indistinguishable from the most recent
        # reported value (same semantics as select_ltm_n on instant metrics).
        quarterly = [v for v in values if _is_quarterly(v) and v.get("val") is not None]
        if not quarterly:
            return None
        quarterly.sort(key=lambda v: v.get("end", ""), reverse=True)
        return _value_to_cited(
            quarterly[0], metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
        )


def select_mrp(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
) -> CitedValue | None:
    """Select the most recent period (whatever was filed last)."""
    values = _extract_values(facts, concept, taxonomy=taxonomy)
    unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)

    valid = [v for v in values if v.get("val") is not None]
    if not valid:
        return None
    valid.sort(
        key=lambda v: (_parse_date(v.get("filed", "")) or date.min, v.get("end", "")),
        reverse=True,
    )
    return _value_to_cited(
        valid[0], metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
    )


def select_ltm(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    diagnostics: list[Diagnostic] | None = None,
) -> CitedValue | DerivedValue | None:
    """Compute trailing twelve months for a metric.

    Duration metrics use ``MRP + LFY - same-quarter-prior-year`` with cumulative
    quarter matching based on duration (Q2+ entries >100 days). Instant metrics
    degrade to the latest reported value.

    When the three-filing citation contract cannot be satisfied, returns
    ``None`` and appends a ``Diagnostic(kind="ltm_incomputable")`` to the
    ``diagnostics`` collector if one is provided.
    """
    return _select_ltm_like(
        facts,
        concept,
        metric,
        meta,
        company,
        cik,
        years_back=0,
        fiscal_period_label="LTM",
        taxonomy=taxonomy,
        doc_map=doc_map,
        diagnostics=diagnostics,
    )


def select_ltm_minus_1(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    diagnostics: list[Diagnostic] | None = None,
) -> CitedValue | DerivedValue | None:
    """Compute prior-year trailing twelve months (LTM-1)."""
    return _select_ltm_like(
        facts,
        concept,
        metric,
        meta,
        company,
        cik,
        years_back=1,
        fiscal_period_label="LTM-1",
        taxonomy=taxonomy,
        doc_map=doc_map,
        diagnostics=diagnostics,
    )


def select_ltm_n(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    years_back: int = 0,
    diagnostics: list[Diagnostic] | None = None,
) -> CitedValue | DerivedValue | None:
    """Compute a trailing twelve months window N fiscal years back.

    ``years_back=0`` matches ``select_ltm``. ``years_back=1`` matches
    ``select_ltm_minus_1``. Higher values walk further back using the same
    ``MRP + LFY - MRP_prior_year`` formula with a shifted anchor.
    """
    yrs = max(0, years_back)
    label = "LTM" if yrs == 0 else f"LTM-{yrs}"
    return _select_ltm_like(
        facts,
        concept,
        metric,
        meta,
        company,
        cik,
        years_back=yrs,
        fiscal_period_label=label,
        taxonomy=taxonomy,
        doc_map=doc_map,
        diagnostics=diagnostics,
    )


def select_annual_series(
    facts: dict[str, Any],
    concept: str,
    metric: str,
    meta: MetricMeta,
    company: str,
    cik: str,
    n: int = 3,
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
) -> list[CitedValue]:
    """Select the last N fiscal year values."""
    values = _extract_values(facts, concept, taxonomy=taxonomy)
    unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)

    annual = _annual_history(values)

    results = []
    seen_fy: set[int] = set()
    for v in annual:
        fy = int(v.get("fy") or 0)
        if fy in seen_fy:
            continue
        seen_fy.add(fy)
        results.append(
            _value_to_cited(
                v, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
            )
        )
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
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
) -> list[CitedValue]:
    """Select the last N quarterly values.

    For duration concepts, filters to standalone ~90-day values (same logic as MRQ)
    to avoid returning cumulative YTD numbers in the series.
    """
    values = _extract_values(facts, concept, taxonomy=taxonomy)
    unit = _unit_for_concept(facts, concept, taxonomy=taxonomy)

    if meta.duration:
        quarterly = [
            v
            for v in values
            if _is_quarterly(v) and v.get("val") is not None and _is_standalone_quarter(v)
        ]
    else:
        quarterly = [v for v in values if _is_quarterly(v) and v.get("val") is not None]

    quarterly.sort(
        key=lambda v: (int(v.get("fy") or 0), _quarter_months(str(v.get("fp", "")))),
        reverse=True,
    )

    results = []
    seen: set[tuple[int, str]] = set()
    for v in quarterly:
        key = (int(v.get("fy") or 0), str(v.get("fp", "")))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            _value_to_cited(
                v, metric, concept, unit, company, cik, taxonomy=taxonomy, doc_map=doc_map
            )
        )
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
    taxonomy: str = "us-gaap",
    doc_map: dict[str, str] | None = None,
    period_offset: int = 0,
    diagnostics: list[Diagnostic] | None = None,
) -> CitedValue | DerivedValue | list[CitedValue] | None:
    """Route to the appropriate period selector.

    Args:
        facts: The ``facts`` dict from SEC companyfacts JSON.
        concept: GAAP/IFRS concept name.
        metric: Normalized metric name.
        meta: Metric metadata.
        company: Company name.
        cik: CIK number.
        period: Period selector string. Valid values: ``"lfy"`` (latest fiscal
            year), ``"mrq"`` (most recent quarter), ``"ltm"`` / ``"ltm-1"``
            (trailing twelve months, current and prior window), ``"annual:N"``
            (series of N annual periods), ``"quarterly:N"`` (series of N
            quarters), and ``"lfy-N"`` (fiscal year N positions back from the
            latest; N must be a non-negative integer). ``lfy-0`` is equivalent
            to ``lfy``.
        taxonomy: XBRL taxonomy ("us-gaap" or "ifrs-full").
        doc_map: Optional mapping of accession -> primaryDocument filename.

    Returns:
        CitedValue, list of CitedValues (for series), or None.
    """
    period = period.strip().lower()

    # lfy-N reads as "N fiscal years before the latest FY". Keep the offset
    # negative so downstream select_lfy walks back through the annual history.
    lfy_back_match = re.fullmatch(r"lfy-(\d+)", period)
    if lfy_back_match:
        years_back = int(lfy_back_match.group(1))
        return select_lfy(
            facts,
            concept,
            metric,
            meta,
            company,
            cik,
            taxonomy=taxonomy,
            doc_map=doc_map,
            period_offset=-years_back,
        )

    # ltm-N and mrq-N share the "N fiscal years back, same anchor" semantics.
    ltm_back_match = re.fullmatch(r"ltm-(\d+)", period)
    if ltm_back_match:
        return select_ltm_n(
            facts,
            concept,
            metric,
            meta,
            company,
            cik,
            taxonomy=taxonomy,
            doc_map=doc_map,
            years_back=int(ltm_back_match.group(1)),
            diagnostics=diagnostics,
        )

    mrq_back_match = re.fullmatch(r"mrq-(\d+)", period)
    if mrq_back_match:
        return select_mrq_n(
            facts,
            concept,
            metric,
            meta,
            company,
            cik,
            taxonomy=taxonomy,
            doc_map=doc_map,
            years_back=int(mrq_back_match.group(1)),
        )

    if period == "lfy":
        return select_lfy(
            facts,
            concept,
            metric,
            meta,
            company,
            cik,
            taxonomy=taxonomy,
            doc_map=doc_map,
            period_offset=period_offset,
        )
    elif period == "mrq":
        return select_mrq(
            facts, concept, metric, meta, company, cik, taxonomy=taxonomy, doc_map=doc_map
        )
    elif period == "mrp":
        return select_mrp(
            facts, concept, metric, meta, company, cik, taxonomy=taxonomy, doc_map=doc_map
        )
    elif period == "ltm":
        return select_ltm(
            facts,
            concept,
            metric,
            meta,
            company,
            cik,
            taxonomy=taxonomy,
            doc_map=doc_map,
            diagnostics=diagnostics,
        )
    elif period.startswith("annual:"):
        n = int(period.split(":")[1])
        return select_annual_series(
            facts, concept, metric, meta, company, cik, n=n, taxonomy=taxonomy, doc_map=doc_map
        )
    elif period.startswith("quarterly:"):
        n = int(period.split(":")[1])
        return select_quarterly_series(
            facts, concept, metric, meta, company, cik, n=n, taxonomy=taxonomy, doc_map=doc_map
        )
    else:
        raise ValueError(f"Unknown period selector: {period}")


_SCALAR_PERIOD_RE = re.compile(r"^(lfy|ltm|mrq|mrp)(?:-(\d+))?$")
_SERIES_PERIOD_RE = re.compile(r"^(annual|quarterly):\d+$")


def parse_period_spec(spec: str) -> list[str]:
    """Parse a period spec into an ordered list of canonical scalar selectors.

    Accepts either a single selector (``"lfy"``, ``"ltm-2"``, ``"annual:3"``)
    or a comma-separated list of scalar selectors (``"lfy,lfy-1,lfy-2"``).

    Canonicalizes ``lfy-0`` -> ``lfy``, ``ltm-0`` -> ``ltm``, ``mrq-0`` -> ``mrq``.
    De-dupes while preserving the caller's order. Rejects mixing series
    selectors (``annual:N``, ``quarterly:N``) with any other token.

    Raises ``ValueError`` for unknown selectors or invalid mixing.
    """
    if not spec or not spec.strip():
        raise ValueError("period spec is empty")

    tokens = [p.strip().lower() for p in spec.split(",") if p.strip()]
    if not tokens:
        raise ValueError("period spec is empty")

    has_series = any(_SERIES_PERIOD_RE.match(t) for t in tokens)
    if has_series and len(tokens) > 1:
        raise ValueError(
            "series selectors (annual:N, quarterly:N) cannot be combined with other periods"
        )

    if has_series:
        return [tokens[0]]

    seen: set[str] = set()
    result: list[str] = []
    for tok in tokens:
        m = _SCALAR_PERIOD_RE.match(tok)
        if not m:
            raise ValueError(
                f"unknown period selector: {tok!r} "
                "(expected lfy, ltm, mrq, mrp, lfy-N, ltm-N, mrq-N, "
                "annual:N, or quarterly:N)"
            )
        head, num = m.group(1), m.group(2)
        if num is None or int(num) == 0:
            canonical = head
        else:
            canonical = f"{head}-{int(num)}"
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return result
