"""Canonical --strict filter shared across query, comps, and compare CLIs.

Semantics: under --strict, only values whose `source` is 'hardcoded' survive.
Anything resolved via the self-heal path (source starts with 'learned:'),
text scans, or any other non-deterministic resolution is rejected and
replaced with None. The caller gets back the list of rejected metric
names so it can surface the rejection in output.
"""

from __future__ import annotations

from .models import CitedValue, MetricValue, QueryResult


def is_strict_allowed(value: CitedValue) -> bool:
    """True if this CitedValue survives --strict.

    Only values with source='hardcoded' (the default for METRIC_MAP
    resolutions that hit canonical XBRL concepts) are allowed. Anything
    else — learned:fuzzy, learned:llm, learned:kpi-*, text-scan, any
    future non-deterministic source tag — is rejected.
    """
    return getattr(value, "source", "hardcoded") == "hardcoded"


def _strict_value(value: MetricValue) -> MetricValue:
    """Zero out a metric value under strict mode.

    Scalars become None, list values lose any non-hardcoded entries.
    Derived/LTM values are allowed through only if the derived result
    itself is hardcoded (i.e. it was computed from fully-hardcoded
    components via the deterministic _compute_derived path).
    """
    if value is None:
        return None
    if isinstance(value, list):
        kept = [v for v in value if is_strict_allowed(v)]
        return kept if kept else None
    return value if is_strict_allowed(value) else None


def apply_strict(result: QueryResult) -> list[str]:
    """Mutate `result.metrics` in place, dropping any non-hardcoded values.

    Returns the list of metric names whose values were rejected so the CLI
    renderer can annotate the output ('N/A [strict]' + a rejection summary).
    """
    rejected: list[str] = []
    for metric_name, raw_value in list(result.metrics.items()):
        filtered = _strict_value(raw_value)
        if filtered is None and raw_value is not None:
            rejected.append(metric_name)
        result.metrics[metric_name] = filtered
    return rejected
