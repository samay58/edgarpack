"""Deterministic citation and calculation registries for query outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _period_str(cited: Any) -> str:
    period_fn = getattr(cited, "_period_str", None)
    if callable(period_fn):
        return str(period_fn())
    start = getattr(cited, "period_start", None)
    end = getattr(cited, "period_end", None)
    return f"{start}/{end}" if start else str(end)


def _filed_str(cited: Any) -> str | None:
    """ISO date string for a component's ``filed``, or ``None`` when unset.

    Some China packs carry no manifest announcement date, so ``filed`` is
    legitimately ``None``. Serializing it must emit JSON null, not the
    literal string ``"None"``.
    """
    filed = getattr(cited, "filed", None)
    if not filed:
        return None
    isoformat = getattr(filed, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(filed)


def _is_derived(item: Any) -> bool:
    return bool(getattr(item, "derived", False)) and isinstance(
        getattr(item, "components", None),
        dict,
    )


def _is_ltm_like(item: Any) -> bool:
    ltm_fn = getattr(item, "_is_ltm_like", None)
    if callable(ltm_fn):
        return bool(ltm_fn())
    return str(getattr(item, "fiscal_period", "")).upper().startswith("LTM")


def calculation_kind(item: Any) -> tuple[str, str]:
    """Return ``(id_prefix, human_kind)`` for a derived value."""
    fiscal_period = str(getattr(item, "fiscal_period", "")).upper()
    if fiscal_period.startswith("LTM"):
        return "L", "ltm"
    if fiscal_period.startswith("CAGR"):
        return "G", "cagr"
    return "D", "derived"


def _has_additive_ltm_components(item: Any) -> bool:
    """True when a value's components are the additive LTM roles.

    Separates a genuine LTM sum (components mrp/lfy/mrp_prior) from a ratio
    evaluated over LTM windows (e.g. gross_margin = LTM gross_profit / LTM
    revenue), whose components are the numerator/denominator metrics.
    """
    components = getattr(item, "components", {}) or {}
    return {"mrp", "lfy", "mrp_prior"} <= set(components)


def calculation_formula(item: Any, kind: str) -> str:
    if kind == "ltm" and _has_additive_ltm_components(item):
        return "mrp + lfy - mrp_prior"
    # A ratio-of-LTMs carries its real formula in ``concept`` (e.g.
    # "gross_profit / revenue"), not the additive LTM template.
    return str(getattr(item, "concept", ""))


@dataclass
class CitationRegistry:
    """Stable C#/D#/L#/G# registry shared by renderers and JSON serializers."""

    citation_ids: dict[str, str] = field(default_factory=dict)
    citations: dict[str, dict[str, object]] = field(default_factory=dict)
    calculation_ids: dict[str, str] = field(default_factory=dict)
    calculations: dict[str, dict[str, object]] = field(default_factory=dict)
    formula_records: dict[tuple[str, str], dict[str, object]] | None = None

    def register_citation(self, cited: Any) -> str:
        """Register a cited value, deduping by its stable citation key."""
        key = str(getattr(cited, "citation_key"))
        existing = self.citation_ids.get(key)
        if existing:
            return existing

        citation_id = f"C{len(self.citation_ids) + 1}"
        self.citation_ids[key] = citation_id
        record = cited.to_citation_record(citation_id)
        record.setdefault("type", "citation")
        self.citations[citation_id] = record
        return citation_id

    def register_calculation(self, metric_name: str, item: Any) -> str:
        """Register a derived value and its component citation IDs."""
        calc_key = f"{metric_name}|{getattr(item, 'citation_key')}"
        existing = self.calculation_ids.get(calc_key)
        if existing:
            return existing

        prefix, kind = calculation_kind(item)
        next_idx = 1 + sum(1 for cid in self.calculations if cid.startswith(prefix))
        calc_id = f"{prefix}{next_idx}"
        self.calculation_ids[calc_key] = calc_id

        components: list[dict[str, object]] = []
        component_citation_ids: dict[str, str] = {}
        for role, component in getattr(item, "components", {}).items():
            comp_cid = self.register_citation(component)
            role_text = str(role)
            component_citation_ids[role_text] = comp_cid
            entry: dict[str, object] = {
                "role": role_text,
                "metric": getattr(component, "metric", ""),
                "concept": getattr(component, "concept", ""),
                "citation_id": comp_cid,
                "value": getattr(component, "value", None),
                "unit": getattr(component, "unit", ""),
                "fiscal_label": getattr(component, "fiscal_label", ""),
                "period": _period_str(component),
                "accession": getattr(component, "accession", ""),
                "form_type": getattr(component, "form_type", ""),
                "filed": _filed_str(component),
                "primary_link": getattr(component, "primary_link", ""),
                "primary_link_type": getattr(component, "primary_link_type", ""),
            }
            warnings = getattr(component, "warnings", [])
            if warnings:
                entry["warnings"] = list(warnings)
            components.append(entry)

        result_cid = self.register_citation(item)
        formula = calculation_formula(item, kind)
        record: dict[str, object] = {
            "id": calc_id,
            "type": "derived",
            "metric": metric_name,
            "kind": kind,
            "formula": formula,
            "result_citation_id": result_cid,
            "result": {
                "value": getattr(item, "value", None),
                "unit": getattr(item, "unit", ""),
                "citation_id": result_cid,
            },
            "component_citation_ids": component_citation_ids,
            "components": components,
            "warnings": list(getattr(item, "warnings", [])),
            "fiscal_label": getattr(item, "fiscal_label", ""),
        }

        if _is_ltm_like(item):
            record["ltm_variant"] = str(getattr(item, "fiscal_period", "")).lower()
            record["window"] = {
                "start": str(getattr(item, "period_start", ""))
                if getattr(item, "period_start", None)
                else None,
                "end": str(getattr(item, "period_end", "")),
            }
            component_roles = set(getattr(item, "components", {}).keys())
            record["method"] = (
                "computed" if {"mrp", "lfy", "mrp_prior"}.issubset(component_roles) else "fallback"
            )

        self.calculations[calc_id] = record
        self._record_formula(metric_name, kind, formula, calc_id)
        return calc_id

    def marker_for(self, metric_name: str, item: Any) -> str:
        """Return the bracketed marker for a direct or derived metric value."""
        if _is_derived(item):
            return f"[{self.register_calculation(metric_name, item)}]"
        return f"[{self.register_citation(item)}]"

    def citation_ids_for(self, item: Any) -> list[str]:
        """Return the direct citation ID for a metric payload."""
        return [self.register_citation(item)]

    def component_citation_ids_for(self, item: Any) -> dict[str, str]:
        """Return role -> citation ID for a derived metric's components."""
        if not _is_derived(item):
            return {}
        return {
            str(role): self.register_citation(component)
            for role, component in getattr(item, "components", {}).items()
        }

    def _record_formula(self, metric_name: str, kind: str, formula: str, calc_id: str) -> None:
        if self.formula_records is None:
            return
        formula_key = (metric_name, kind)
        rec = self.formula_records.get(formula_key)
        if rec is None:
            rec = {
                "metric": metric_name,
                "kind": kind,
                "formula": formula,
                "calc_ids": [],
            }
            self.formula_records[formula_key] = rec
        bound = rec["calc_ids"]
        if isinstance(bound, list):
            bound.append(calc_id)


def citation_summary(citation_id: str, record: dict[str, object]) -> str:
    """One-line human citation used by terminal footers."""
    form_type = record.get("form_type")
    fiscal = record.get("fiscal_label")
    period = record.get("period")
    filing = record.get("accession")
    filed = record.get("filed") or "n/a"
    return (
        f"[{citation_id}] {form_type} {fiscal} | period {period} | filing {filing} | filed {filed}"
    )


def calculation_summary(calculation_id: str, record: dict[str, object]) -> str:
    """One-line human formula summary used by terminal footers."""
    metric_name = record.get("metric", "")
    formula = record.get("formula", "")
    components = record.get("component_citation_ids", {})
    if isinstance(components, dict) and components:
        refs = ", ".join(f"{role}[{cid}]" for role, cid in components.items())
        return f"[{calculation_id}] {metric_name} = {formula} using {refs}"
    return f"[{calculation_id}] {metric_name} = {formula}"
