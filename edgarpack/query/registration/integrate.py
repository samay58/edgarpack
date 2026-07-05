"""Turn cached S-1 snapshots into cited query values.

Registration-pack discovery on disk, the snapshot pickers, `CitedValue` /
`DerivedValue` construction (including the S-1 derived-metric formulas), and
`augment_with_s1_snapshot`, the entry point that fills a QueryResult's empty
cells with cited registration figures.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date as _date_cls
from pathlib import Path
from typing import Any

from ...sec.submissions import is_registration_form
from ..formula import eval_formula
from ..models import CitedValue, DerivedValue, Diagnostic
from .llm import extract_or_load_snapshot
from .snapshot import (
    _CACHE_FILENAME,
    METRIC_SLUGS,
    SCHEMA_VERSION,
    SnapshotFact,
    SnapshotResult,
    source_sha256_for_pack,
)


@dataclass(frozen=True)
class _RegistrationPack:
    pack_dir: Path
    accession: str
    filing_date: _date_cls
    form_type: str


@dataclass(frozen=True)
class _SnapshotCandidate:
    fact: SnapshotFact
    filing_date: _date_cls
    form_type: str


# Maps a snapshot metric slug to (unit, divisor) for CitedValue conversion.
# For monetary and per-share metrics the divisor is 100 (cents -> USD).
# For share counts the divisor is 100 (we stored count * 100 in cents).
_UNIT_FOR_METRIC: dict[str, tuple[str, int]] = {
    "revenue": ("USD", 100),
    "gross_profit": ("USD", 100),
    "adjusted_gross_profit": ("USD", 100),
    "operating_income_loss": ("USD", 100),
    "net_income_loss": ("USD", 100),
    "operating_cash_flow": ("USD", 100),
    "capex": ("USD", 100),
    "adjusted_ebitda": ("USD", 100),
    "cash_and_equivalents": ("USD", 100),
    "total_assets": ("USD", 100),
    "stockholders_equity": ("USD", 100),
    "shares_outstanding_basic": ("shares", 100),
    "eps_basic": ("USD/shares", 100),
}

# Default GAAP concept label per slug; used for the CitedValue.concept field
# on snapshot rows. Purely cosmetic, since snapshots are not sourced from
# GAAP tags, but keeps existing renderers that read .concept happy.
_DEFAULT_CONCEPTS: dict[str, str] = {
    "revenue": "Revenues",
    "gross_profit": "GrossProfit",
    "adjusted_gross_profit": "AdjustedGrossProfit",
    "operating_income_loss": "OperatingIncomeLoss",
    "net_income_loss": "NetIncomeLoss",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
    "adjusted_ebitda": "AdjustedEBITDA",
    "cash_and_equivalents": "CashAndCashEquivalentsAtCarryingValue",
    "total_assets": "Assets",
    "stockholders_equity": "StockholdersEquity",
    "shares_outstanding_basic": "WeightedAverageNumberOfSharesOutstandingBasic",
    "eps_basic": "EarningsPerShareBasic",
}

_PUBLIC_TO_SNAPSHOT_METRIC: dict[str, str] = {
    "operating_income": "operating_income_loss",
    "net_income": "net_income_loss",
    "cash": "cash_and_equivalents",
}

S1_DEFAULT_QUERY_METRICS: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "gross_margin",
    "operating_income",
    "operating_margin",
    "net_income",
    "net_margin",
    "adjusted_gross_profit",
    "adjusted_ebitda",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash_and_equivalents",
    "total_assets",
    "stockholders_equity",
    "shares_outstanding_basic",
    "eps_basic",
)

_S1_DERIVED_FORMULAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "free_cash_flow": ("operating_cash_flow - capex", ("operating_cash_flow", "capex")),
    "gross_margin": ("gross_profit / revenue", ("gross_profit", "revenue")),
    "operating_margin": ("operating_income / revenue", ("operating_income", "revenue")),
    "net_margin": ("net_income / revenue", ("net_income", "revenue")),
    "fcf_margin": ("free_cash_flow / revenue", ("free_cash_flow", "revenue")),
    "capex_intensity": ("capex / revenue", ("capex", "revenue")),
}


def snapshot_fact_to_cited_value(
    fact: SnapshotFact,
    *,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls,
    concept: str,
    public_metric: str | None = None,
) -> CitedValue:
    unit, divisor = _UNIT_FOR_METRIC[fact.metric]
    if fact.currency != "USD":
        unit = unit.replace("USD", fact.currency)
    value = fact.value_cents / divisor if divisor else fact.value_cents
    source = "s1_pro_forma" if fact.is_pro_forma else "s1_snapshot"

    # An absent or unparseable period_end (bare-year FY column with no
    # stated month-day) carries no fabricated date; fiscal_year still drives
    # lfy/mrp selection, and FX conversion fails closed on the missing date.
    try:
        period_end: _date_cls | None = _date_cls.fromisoformat(fact.period_end)
    except ValueError:
        period_end = None

    return CitedValue(
        value=value,
        unit=unit,
        metric=public_metric or fact.metric,
        concept=concept,
        period_start=None,
        period_end=period_end,
        fiscal_year=fact.fiscal_year,
        fiscal_period=fact.fiscal_period or "FY",
        form_type=form_type,
        filed=filed,
        accession=fact.accession,
        cik=cik,
        company=company,
        source=source,
        reporting_currency=fact.currency,
        is_pro_forma=fact.is_pro_forma,
        pro_forma_note=fact.pro_forma_note,
        excerpt_text=fact.source_text or "",
    )


def pick_snapshot_fact(
    facts: list[SnapshotFact],
    *,
    metric: str,
    period: str,
) -> SnapshotFact | None:
    candidates = [f for f in facts if f.metric == metric]
    if not candidates:
        return None

    if period == "pro-forma":
        pf = [f for f in candidates if f.is_pro_forma]
        if not pf:
            return None
        pf.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)
        return pf[0]

    non_pro_forma = [f for f in candidates if not f.is_pro_forma]
    if not non_pro_forma:
        return None

    # mrp = most recent period, which may be an unaudited interim quarter, so
    # select on period regardless of is_audited. lfy / lfy-N are annual only,
    # so they keep the audited-FY filter.
    if period == "mrp":
        non_pro_forma.sort(key=lambda f: (f.period_end, f.fiscal_year), reverse=True)
        return non_pro_forma[0]

    annual = [
        f for f in non_pro_forma if f.is_audited and (f.fiscal_period or "FY").upper() == "FY"
    ]
    annual.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)

    if period == "lfy":
        return annual[0] if annual else None

    match_lfy_n = re.match(r"^lfy-(\d+)$", period)
    if match_lfy_n:
        offset = int(match_lfy_n.group(1))
        return annual[offset] if offset < len(annual) else None

    return None


def _parse_manifest_date(raw: object) -> _date_cls:
    try:
        return _date_cls.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return _date_cls.min


def _read_registration_pack(manifest: Path, *, cik: str) -> _RegistrationPack | None:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    filing = data.get("filing") or {}
    filing_cik = str(filing.get("cik", "")).lstrip("0")
    requested_cik = str(cik).lstrip("0")
    if filing_cik != requested_cik:
        return None
    form_type = str(filing.get("form_type", ""))
    if not is_registration_form(form_type):
        return None
    accession = str(filing.get("accession") or manifest.parent.name)
    return _RegistrationPack(
        pack_dir=manifest.parent,
        accession=accession,
        filing_date=_parse_manifest_date(filing.get("filing_date", "")),
        form_type=form_type or "S-1",
    )


def _registration_packs_for_cik(cik: str, pack_root: Path) -> list[_RegistrationPack]:
    packs: list[_RegistrationPack] = []
    for manifest in Path(pack_root).rglob("manifest.json"):
        pack = _read_registration_pack(manifest, cik=cik)
        if pack is not None:
            packs.append(pack)
    packs.sort(key=lambda p: (p.filing_date, p.accession), reverse=True)
    return packs


def has_registration_pack_for_cik(
    cik: str,
    pack_root: Path,
    *,
    form_type: str | None = None,
    accession: str | None = None,
) -> bool:
    from ...sec.submissions import matches_registration_family, normalize_form_type

    target_form = normalize_form_type(form_type) if form_type else None
    target_accession = accession.replace("-", "") if accession else None
    for pack in _registration_packs_for_cik(cik, pack_root):
        if target_form is not None and not matches_registration_family(pack.form_type, target_form):
            continue
        if target_accession is not None and pack.accession.replace("-", "") != target_accession:
            continue
        return True
    return False


def default_registration_query_metrics() -> list[str]:
    return list(S1_DEFAULT_QUERY_METRICS)


def _current_cached_snapshot(pack: _RegistrationPack) -> SnapshotResult | None:
    cache = pack.pack_dir / _CACHE_FILENAME
    if not cache.exists():
        return None
    try:
        result = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if result.schema_version != SCHEMA_VERSION:
        return None
    if result.source_sha256 != source_sha256_for_pack(pack.pack_dir):
        return None
    return result


def _snapshot_candidates(
    result: SnapshotResult,
    pack: _RegistrationPack,
) -> list[_SnapshotCandidate]:
    return [
        _SnapshotCandidate(
            fact=fact,
            filing_date=pack.filing_date,
            form_type=pack.form_type,
        )
        for fact in result.facts
    ]


def _pick_snapshot_candidate(
    candidates: list[_SnapshotCandidate],
    *,
    metric: str,
    period: str,
) -> _SnapshotCandidate | None:
    metric_candidates = [c for c in candidates if c.fact.metric == metric]
    if not metric_candidates:
        return None

    if period == "pro-forma":
        pro_forma = [c for c in metric_candidates if c.fact.is_pro_forma]
        if not pro_forma:
            return None
        pro_forma.sort(
            key=lambda c: (c.fact.fiscal_year, c.fact.period_end, c.filing_date),
            reverse=True,
        )
        return pro_forma[0]

    non_pro_forma = [c for c in metric_candidates if not c.fact.is_pro_forma]
    if not non_pro_forma:
        return None

    # mrp = most recent period; an interim quarter is unaudited but still the
    # most recent period, so select on period regardless of is_audited.
    if period == "mrp":
        non_pro_forma.sort(
            key=lambda c: (c.fact.period_end, c.fact.fiscal_year, c.filing_date),
            reverse=True,
        )
        return non_pro_forma[0]

    audited = [
        c
        for c in non_pro_forma
        if c.fact.is_audited and (c.fact.fiscal_period or "FY").upper() == "FY"
    ]
    if not audited:
        return None

    newest_per_period: dict[tuple[int, str], _SnapshotCandidate] = {}
    for candidate in sorted(
        audited,
        key=lambda c: (c.filing_date, c.fact.accession),
        reverse=True,
    ):
        key = (candidate.fact.fiscal_year, candidate.fact.period_end)
        newest_per_period.setdefault(key, candidate)

    ordered = sorted(
        newest_per_period.values(),
        key=lambda c: (c.fact.fiscal_year, c.fact.period_end),
        reverse=True,
    )

    if period == "lfy":
        return ordered[0] if ordered else None

    match_lfy_n = re.match(r"^lfy-(\d+)$", period)
    if match_lfy_n:
        offset = int(match_lfy_n.group(1))
        return ordered[offset] if offset < len(ordered) else None

    return None


def _resolve_concept_for_metric(metric: str) -> str:
    snapshot_metric = _snapshot_metric_for_query_metric(metric)
    if snapshot_metric in _DEFAULT_CONCEPTS:
        return _DEFAULT_CONCEPTS[snapshot_metric]
    formula = _S1_DERIVED_FORMULAS.get(metric)
    if formula is not None:
        return formula[0]
    return _DEFAULT_CONCEPTS.get(metric, metric)


def _snapshot_metric_for_query_metric(metric: str) -> str:
    return _PUBLIC_TO_SNAPSHOT_METRIC.get(metric, metric)


def _filed_date_for_candidate(
    candidate: _SnapshotCandidate,
    *,
    filed: _date_cls | None,
) -> _date_cls:
    if candidate.filing_date != _date_cls.min:
        return candidate.filing_date
    if filed is not None:
        return filed
    try:
        return _date_cls.fromisoformat(candidate.fact.period_end)
    except ValueError:
        return _date_cls.today()


def _candidate_to_cited_value(
    candidate: _SnapshotCandidate,
    *,
    public_metric: str,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls | None,
) -> CitedValue:
    fact = candidate.fact
    return snapshot_fact_to_cited_value(
        fact,
        cik=cik,
        company=company,
        form_type=candidate.form_type or form_type,
        filed=_filed_date_for_candidate(candidate, filed=filed),
        concept=_resolve_concept_for_metric(public_metric),
        public_metric=public_metric,
    )


def _eval_s1_formula(
    formula: str,
    components: dict[str, CitedValue],
) -> float | None:
    values = {
        name: float(value.value) for name, value in components.items() if value.value is not None
    }
    return eval_formula(formula, values)


def _s1_derived_unit(metric: str) -> str:
    if metric == "free_cash_flow":
        return "USD"
    return "pure"


def _s1_value_from_candidates(
    candidates: list[_SnapshotCandidate],
    *,
    metric: str,
    period: str,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls | None,
    resolving: set[str] | None = None,
) -> CitedValue | DerivedValue | None:
    resolving = set() if resolving is None else resolving
    if metric in resolving:
        return None

    formula = _S1_DERIVED_FORMULAS.get(metric)
    if formula is not None:
        resolving.add(metric)
        expression, component_names = formula
        components: dict[str, CitedValue] = {}
        for component_name in component_names:
            component = _s1_value_from_candidates(
                candidates,
                metric=component_name,
                period=period,
                cik=cik,
                company=company,
                form_type=form_type,
                filed=filed,
                resolving=resolving,
            )
            if component is None or component.value is None:
                resolving.discard(metric)
                return None
            components[component_name] = component

        fiscal_years = {component.fiscal_year for component in components.values()}
        period_ends = {component.period_end for component in components.values()}
        if len(fiscal_years) != 1 or len(period_ends) != 1:
            resolving.discard(metric)
            return None

        value = _eval_s1_formula(expression, components)
        if value is None:
            resolving.discard(metric)
            return None

        first_component = next(iter(components.values()))
        resolving.discard(metric)
        return DerivedValue(
            value=value,
            unit=_s1_derived_unit(metric),
            metric=metric,
            concept=expression,
            period_start=first_component.period_start,
            period_end=first_component.period_end,
            fiscal_year=first_component.fiscal_year,
            fiscal_period=first_component.fiscal_period,
            form_type=first_component.form_type,
            filed=first_component.filed,
            accession=first_component.accession,
            cik=cik,
            company=company,
            taxonomy=first_component.taxonomy,
            primary_document=first_component.primary_document,
            source=first_component.source,
            reporting_currency=first_component.reporting_currency,
            derived=True,
            components=components,
        )

    snapshot_metric = _snapshot_metric_for_query_metric(metric)
    if snapshot_metric not in METRIC_SLUGS:
        return None
    candidate = _pick_snapshot_candidate(
        candidates,
        metric=snapshot_metric,
        period=period,
    )
    if candidate is None:
        return None
    return _candidate_to_cited_value(
        candidate,
        public_metric=metric,
        cik=cik,
        company=company,
        form_type=form_type,
        filed=filed,
    )


_REGISTRATION_VALUE_SOURCES = {"s1_snapshot", "s1_pro_forma", "no_api_key"}


def _periodic_context_fiscal_years(result: Any) -> set[int]:
    years: set[int] = set()
    for value in getattr(result, "metrics", {}).values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            if getattr(item, "source", "") in _REGISTRATION_VALUE_SOURCES:
                continue
            fiscal_year = getattr(item, "fiscal_year", 0)
            if isinstance(fiscal_year, int) and fiscal_year > 0:
                years.add(fiscal_year)
    return years


def snapshots_for_cik(cik: str, pack_root: Path) -> list[SnapshotFact]:
    pack_root = Path(pack_root)
    out: list[SnapshotFact] = []
    for manifest in pack_root.rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        filing = data.get("filing") or {}
        if str(filing.get("cik", "")).lstrip("0") != str(cik).lstrip("0"):
            continue
        if not is_registration_form(str(filing.get("form_type", ""))):
            continue
        cache = manifest.parent / _CACHE_FILENAME
        if not cache.exists():
            continue
        try:
            result = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        out.extend(result.facts)
    return out


def _find_latest_registration_pack(cik: str, pack_root: Path) -> Path | None:
    """Return the newest-filing_date registration-class pack directory for a CIK."""
    packs = _registration_packs_for_cik(cik, pack_root)
    if not packs:
        return None
    return packs[0].pack_dir


_SUPPORTED_REGISTRATION_PERIODS = frozenset({"lfy", "mrp", "pro-forma"})
_REGISTRATION_EXTRACTION_DIAGNOSTIC_PREFIX = "registration extraction "


def _is_supported_registration_period(period: str) -> bool:
    if period in _SUPPORTED_REGISTRATION_PERIODS:
        return True
    return re.match(r"^lfy-\d+$", period) is not None


def _add_registration_diagnostic(result: Any, *, metric: str, message: str) -> None:
    diagnostics = getattr(result, "diagnostics", None)
    if diagnostics is None:
        return
    diagnostics.append(Diagnostic(metric=metric, kind="layer_b_unresolved", message=message))


def _inject_no_api_key_placeholders(
    result: Any,
    *,
    metrics: list[str],
    cik: str,
    company: str,
    form_type: str,
    latest_pack: _RegistrationPack,
) -> None:
    placeholder_date = (
        latest_pack.filing_date if latest_pack.filing_date != _date_cls.min else _date_cls.today()
    )
    for metric in metrics:
        if result.metrics.get(metric) is not None:
            continue
        snapshot_metric = _snapshot_metric_for_query_metric(metric)
        unit, _ = _UNIT_FOR_METRIC.get(snapshot_metric, ("USD", 100))
        result.metrics[metric] = CitedValue(
            value=None,
            unit=unit,
            metric=metric,
            concept=_resolve_concept_for_metric(metric),
            period_end=placeholder_date,
            fiscal_year=0,
            fiscal_period="FY",
            form_type=latest_pack.form_type or form_type,
            filed=placeholder_date,
            accession="",
            cik=cik,
            company=company,
            source="no_api_key",
        )


async def augment_with_s1_snapshot(
    *,
    result: Any,  # QueryResult; kept as Any to avoid circular import pressure
    cik: str,
    metrics: list[str],
    period: str,
    pack_root: Path,
    company: str = "",
    form_type: str = "S-1",
    filed: _date_cls | None = None,
) -> Any:
    """Fill result.metrics cells that are still None with S-1 snapshot rows.

    When no cached snapshots exist, lazily extract from the most recent
    registration-class pack for this CIK. If that extraction fails due to a
    missing ANTHROPIC_API_KEY, inject placeholder CitedValue rows with
    source="no_api_key" so the CLI can surface a helpful hint. Non-ok
    extraction statuses, unsupported period selectors, dropped magnitude-gate
    rows, and a silently-empty latest pack each surface a Diagnostic.
    """
    packs = _registration_packs_for_cik(cik, pack_root)
    if not packs:
        return result

    periodic_context_years = (
        set() if period == "pro-forma" else _periodic_context_fiscal_years(result)
    )
    registration_only = not periodic_context_years

    if registration_only and not _is_supported_registration_period(period):
        _add_registration_diagnostic(
            result,
            metric="period",
            message=(
                f"period selector '{period}' is not supported for registration-only "
                "filers; use lfy, lfy-N, mrp, or pro-forma."
            ),
        )
        return result

    latest_pack = packs[0]
    latest_result = await extract_or_load_snapshot(latest_pack.pack_dir)

    if registration_only and latest_result.extraction_status != "ok":
        detail = f": {latest_result.detail}" if latest_result.detail else ""
        _add_registration_diagnostic(
            result,
            metric="extraction",
            message=(
                f"{_REGISTRATION_EXTRACTION_DIAGNOSTIC_PREFIX}"
                f"{latest_result.extraction_status}{detail}"
            ),
        )
    if registration_only:
        for rejection in latest_result.gate_rejections:
            slug = rejection.split(" ", 1)[0]
            _add_registration_diagnostic(result, metric=slug, message=rejection)

    if not latest_result.facts:
        # Latest pack yielded nothing: inject a missing-key placeholder, or
        # explain why we do not silently fall back to an older filing.
        if registration_only and latest_result.extraction_status == "no_api_key":
            _inject_no_api_key_placeholders(
                result,
                metrics=metrics,
                cik=cik,
                company=company,
                form_type=form_type,
                latest_pack=latest_pack,
            )
        elif registration_only and any(
            _current_cached_snapshot(pack) is not None for pack in packs[1:]
        ):
            _add_registration_diagnostic(
                result,
                metric="registration",
                message=(
                    "latest registration pack yielded no snapshot facts; not falling "
                    "back to an older filing's cached snapshot."
                ),
            )
        return result

    candidates = _snapshot_candidates(latest_result, latest_pack)
    for pack in packs[1:]:
        cached = _current_cached_snapshot(pack)
        if cached is not None:
            candidates.extend(_snapshot_candidates(cached, pack))

    if periodic_context_years:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.fact.fiscal_year in periodic_context_years
        ]
        if not candidates:
            return result

    for metric in metrics:
        current = result.metrics.get(metric)
        if current is not None:
            continue
        value = _s1_value_from_candidates(
            candidates,
            metric=metric,
            period=period,
            cik=cik,
            company=company,
            form_type=form_type,
            filed=filed,
        )
        if value is not None:
            result.metrics[metric] = value

    # A no_api_key snapshot can still carry deterministic facts; those filled
    # their cells above. For any requested metric still empty, inject the
    # placeholder so the CLI hint fires.
    if registration_only and latest_result.extraction_status == "no_api_key":
        _inject_no_api_key_placeholders(
            result,
            metrics=metrics,
            cik=cik,
            company=company,
            form_type=form_type,
            latest_pack=latest_pack,
        )
    return result
