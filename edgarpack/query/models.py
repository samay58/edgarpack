"""Citation data models for financial query results."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, Field

from ..config import SEC_ARCHIVES_BASE, SEC_DATA_BASE


def _concept_to_label(concept: str) -> str:
    """Convert a camelCase XBRL tag to a space-separated label.

    Example: "NetIncomeLoss" -> "Net Income Loss"
    """
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", concept)


class CitedValue(BaseModel):
    value: float | int | None
    unit: str  # "USD", "shares", "USD/shares", "pure"
    metric: str  # normalized name: "revenue", "eps_diluted"
    concept: str  # GAAP tag: "Revenues"

    # Period
    period_start: date | None = None
    period_end: date
    fiscal_year: int
    fiscal_period: str  # "FY", "Q1", "Q2", "Q3", "Q4"

    # Source
    form_type: str  # "10-K", "10-Q"
    filed: date
    accession: str
    cik: str
    company: str

    # Deep linking
    taxonomy: str = "us-gaap"
    primary_document: str = ""
    fact_id: str = ""
    warnings: list[str] = Field(default_factory=list)

    # Provenance marker. Recognized values:
    #   'hardcoded'                  METRIC_MAP resolution (periodic filings).
    #   'learned:cached'             registry hit on a prior self-heal lookup.
    #   'learned:fuzzy' | 'learned:llm' | 'learned:user'
    #                                first-time self-heal discovery persisted.
    #   'learned:kpi-discovered'     row sourced from the `which` LLM pass.
    #   'text-scan'                  text-scan fallback (e.g. headcount).
    #   's1_snapshot'                S-1 audited-historical row (LLM-extracted).
    #   's1_pro_forma'               S-1 pro-forma row with is_pro_forma=True.
    #   'no_api_key'                 placeholder row when ANTHROPIC_API_KEY is
    #                                missing; value is None, accession is empty.
    source: str = "hardcoded"

    accounting_standard: Literal["US-GAAP", "IFRS", "HKFRS", "CAS"] = "US-GAAP"
    reporting_currency: str = "USD"

    # S-1 snapshot provenance. Default False so every existing periodic-
    # filing path works unchanged. Set True only for rows sourced from
    # s1_financials.extract_or_load_snapshot. pro_forma_note holds the
    # filing's stated assumption (e.g. "assumes IPO price $32.50").
    is_pro_forma: bool = False
    pro_forma_note: str | None = None

    # Layer B (Self-heal v2): literal quote from the pack prose that produced
    # this value. Used by document_url to build a tight text-fragment anchor.
    # Empty for v1 values (anchors use the concept label).
    excerpt_text: str = ""

    @property
    def filing_url(self) -> str:
        # S-1 snapshot placeholders (source="no_api_key") carry empty
        # accession / cik; emitting a URL built from empty strings produces
        # a broken link. Return empty string so downstream renderers drop it.
        if not self.accession or not self.cik:
            return ""
        acc_nodash = self.accession.replace("-", "")
        return f"{SEC_ARCHIVES_BASE}/{self.cik.lstrip('0')}/{acc_nodash}/{self.accession}-index.htm"

    @property
    def concept_url(self) -> str | None:
        """SEC XBRL companyconcept API URL for this concept's full history.

        Returns None for derived metrics (concept contains spaces or formula operators).
        """
        if " " in self.concept or "/" in self.concept:
            return None
        cik_padded = self.cik.lstrip("0").zfill(10)
        return (
            f"{SEC_DATA_BASE}/api/xbrl/companyconcept"
            f"/CIK{cik_padded}/{self.taxonomy}/{self.concept}.json"
        )

    @property
    def viewer_url(self) -> str | None:
        """SEC Inline XBRL Viewer URL with highlighted tags.

        Returns None if no primary_document is available.
        """
        if not self.primary_document:
            return None
        acc_nodash = self.accession.replace("-", "")
        cik_bare = self.cik.lstrip("0")
        doc_path = f"/Archives/edgar/data/{cik_bare}/{acc_nodash}/{self.primary_document}"
        return f"https://www.sec.gov/ix?doc={doc_path}"

    @property
    def document_url(self) -> str | None:
        """Direct filing HTML URL with text fragment scroll.

        v1 behavior: uses the concept label as the text fragment.
        v2 behavior: when excerpt_text is set (Layer B), uses the first
        eight words of the excerpt for a tighter anchor into the exact
        sentence that contained the value.

        Returns None if no primary_document is available.
        """
        if not self.primary_document:
            return None
        acc_nodash = self.accession.replace("-", "")
        cik_bare = self.cik.lstrip("0")
        base = f"{SEC_ARCHIVES_BASE}/{cik_bare}/{acc_nodash}/{self.primary_document}"
        if self.excerpt_text:
            words = self.excerpt_text.split()[:8]
            fragment = quote(" ".join(words))
            return f"{base}#:~:text={fragment}"
        label = _concept_to_label(self.concept)
        return f"{base}#:~:text={quote(label)}"

    @property
    def anchor_url(self) -> str | None:
        """Direct filing HTML URL with stable XBRL fact ID anchor.

        Uses ``#f-NNN`` anchor from inline XBRL ``id`` attributes. Works in all
        browsers (unlike text fragments). Falls back to ``document_url`` when
        ``fact_id`` is not populated.
        """
        if not self.fact_id or not self.primary_document:
            return self.document_url
        acc_nodash = self.accession.replace("-", "")
        cik_bare = self.cik.lstrip("0")
        base = f"{SEC_ARCHIVES_BASE}/{cik_bare}/{acc_nodash}/{self.primary_document}"
        return f"{base}#{self.fact_id}"

    @property
    def citation(self) -> str:
        """Human-readable citation string."""
        period = f"{self.fiscal_period}{self.fiscal_year}"
        return f"{self.company} {self.form_type} ({period}), filed {self.filed}"

    @property
    def fiscal_label(self) -> str:
        """Human-readable fiscal label (e.g. 'FY2025', 'Q2 FY2025')."""
        if self.fiscal_period in ("FY", ""):
            return f"FY{self.fiscal_year}"
        return f"{self.fiscal_period} FY{self.fiscal_year}"

    @property
    def primary_link_type(self) -> str:
        """Preferred deep link type for terminal UX."""
        if self.fact_id and self.anchor_url:
            return "anchor_url"
        if self.viewer_url:
            return "viewer_url"
        return "filing_url"

    @property
    def primary_link(self) -> str:
        """Preferred deep link for terminal UX."""
        if self.fact_id and self.anchor_url:
            return self.anchor_url
        if self.viewer_url:
            return self.viewer_url
        return self.filing_url

    @property
    def links(self) -> dict[str, str]:
        """All available deep links."""
        links: dict[str, str] = {"filing_url": self.filing_url}
        if self.concept_url:
            links["concept_url"] = self.concept_url
        if self.viewer_url:
            links["viewer_url"] = self.viewer_url
        if self.document_url:
            links["document_url"] = self.document_url
        if self.anchor_url and self.fact_id:
            links["anchor_url"] = self.anchor_url
        return links

    @property
    def citation_key(self) -> str:
        """Stable identity key for deduplicating citations."""
        period_start = str(self.period_start) if self.period_start else ""
        return (
            f"{self.cik}|{self.accession}|{self.taxonomy}|{self.concept}|"
            f"{period_start}|{self.period_end}|{self.value}|{self.fact_id}"
        )

    def to_citation_record(self, citation_id: str) -> dict[str, object]:
        """Normalized citation record for registry-style outputs."""
        record: dict[str, object] = {
            "id": citation_id,
            "company": self.company,
            "cik": self.cik,
            "metric": self.metric,
            "concept": self.concept,
            "taxonomy": self.taxonomy,
            "value": self.value,
            "unit": self.unit,
            "period": self._period_str(),
            "period_start": str(self.period_start) if self.period_start else None,
            "period_end": str(self.period_end),
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "fiscal_label": self.fiscal_label,
            "form_type": self.form_type,
            "filed": str(self.filed),
            "accession": self.accession,
            "citation": self.citation,
            "primary_link": self.primary_link,
            "primary_link_type": self.primary_link_type,
            "links": self.links,
        }
        if self.warnings:
            record["warnings"] = list(self.warnings)
        return record

    def to_cited_dict(self) -> dict[str, object]:
        """JSON-serializable dict with citation baked in."""
        d = self.model_dump(mode="json")
        d["filing_url"] = self.filing_url
        d["citation"] = self.citation
        d["fiscal_label"] = self.fiscal_label
        d["primary_link"] = self.primary_link
        d["primary_link_type"] = self.primary_link_type
        d["links"] = self.links
        if self.concept_url:
            d["concept_url"] = self.concept_url
        if self.viewer_url:
            d["viewer_url"] = self.viewer_url
        if self.document_url:
            d["document_url"] = self.document_url
        if self.anchor_url and self.anchor_url != self.document_url:
            d["anchor_url"] = self.anchor_url
        # Only surface source when it's not the default, to avoid polluting
        # existing JSON consumers that don't know about this field.
        if self.source == "hardcoded":
            d.pop("source", None)
        if not self.excerpt_text:
            d.pop("excerpt_text", None)
        return d

    def _period_str(self) -> str:
        """Compact period string: 'start/end' or just 'end' for instants."""
        if self.period_start:
            return f"{self.period_start}/{self.period_end}"
        return str(self.period_end)

    def to_lean_metric(self) -> dict[str, object]:
        """Lean dict for a single metric (no company/cik/filing duplication)."""
        d: dict[str, object] = {
            "value": self.value,
            "unit": self.unit,
            "concept": self.concept,
            "period": self._period_str(),
            "accession": self.accession,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "fiscal_label": self.fiscal_label,
            "primary_link": self.primary_link,
            "primary_link_type": self.primary_link_type,
        }
        if self.concept_url:
            d["concept_url"] = self.concept_url
        if self.warnings:
            d["warnings"] = list(self.warnings)
        if self.source != "hardcoded":
            d["source"] = self.source
        return d


class DerivedValue(CitedValue):
    """For computed metrics (margins, ratios). Carries source components."""

    derived: bool = True
    components: dict[str, CitedValue] = Field(default_factory=dict)

    def _is_ltm_like(self) -> bool:
        """True when this derived value represents an LTM-style window."""
        return self.fiscal_period.upper().startswith("LTM")

    def _ltm_components_payload(self) -> dict[str, object]:
        """Expanded metadata for LTM/LTM-1 component windows."""
        ltm_comps: dict[str, object] = {}
        for role, component in self.components.items():
            payload: dict[str, object] = {
                "role": role,
                "metric": component.metric,
                "concept": component.concept,
                "value": component.value,
                "unit": component.unit,
                "accession": component.accession,
                "form_type": component.form_type,
                "filed": str(component.filed),
                "fiscal_year": component.fiscal_year,
                "fiscal_period": component.fiscal_period,
                "fiscal_label": component.fiscal_label,
                "period": component._period_str(),
                "period_start": str(component.period_start) if component.period_start else None,
                "period_end": str(component.period_end),
                "primary_link": component.primary_link,
                "primary_link_type": component.primary_link_type,
            }
            if component.warnings:
                payload["warnings"] = list(component.warnings)
            ltm_comps[role] = payload
        return ltm_comps

    @property
    def citation(self) -> str:
        """LTM values cite the underlying real filings."""
        if self._is_ltm_like() and self.components:
            sources = [v.citation for v in self.components.values()]
            return f"LTM computed from: {'; '.join(sources)}"
        return super().citation

    def to_cited_dict(self) -> dict[str, object]:
        d = super().to_cited_dict()
        d["derived"] = True
        d["formula"] = "mrp + lfy - mrp_prior" if self._is_ltm_like() else self.concept
        d["components"] = {k: v.to_cited_dict() for k, v in self.components.items()}
        if self._is_ltm_like() and self.components:
            d["ltm_components"] = self._ltm_components_payload()
        return d

    def to_lean_metric(self) -> dict[str, object]:
        """Lean dict for a derived metric."""
        d = super().to_lean_metric()
        d["derived"] = True
        d["formula"] = self.concept  # concept holds the formula for derived metrics

        if self._is_ltm_like() and self.components:
            # LTM components are temporal slices, inline them
            d["formula"] = "mrp + lfy - mrp_prior"
            d["ltm_components"] = self._ltm_components_payload()
            d["ltm_variant"] = self.fiscal_period.lower()
        else:
            # Standard derived metric (ratio/sum): reference component names
            d["components"] = list(self.components.keys())

        return d


class Diagnostic(BaseModel):
    """Structured failure diagnostic attached to a QueryResult.

    Produced when Layer B (or any future self-heal layer) cannot resolve
    a requested metric. The `kind` field is a closed enum so CLI
    renderers and downstream consumers can filter reliably.

    Kinds currently emitted:
      - 'layer_a_fetch_error': SEC companyfacts fetch failed (network,
        HTTP 5xx, TLS, parse error). Distinct from 'filer has no XBRL'
        so the CLI can surface 'XBRL fetch failed' instead of silent N/A.
      - 'layer_b_unresolved': catch-all for any Layer B failure path
        (no pack, no LLM backend, not found in sections, hallucinated
        excerpt). `try_extract_kpi` collapses these into one kind; finer
        granularity will return once that function carries a structured
        failure reason back to the orchestrator.
      - 'ltm_incomputable': LTM window could not be assembled because at
        least one of mrp / lfy / mrp_prior is missing.
      - 'ltm_degraded': LTM was requested for a discovered KPI; lookup
        substituted the latest annual (LFY) value so the caller sees why
        LTM wasn't computed.
      - 'partial_coverage': a series selector (``annual:N`` /
        ``quarterly:N``) returned fewer rows than requested because the
        cached discovery window is shorter than N.
    """

    metric: str
    kind: Literal[
        "layer_a_fetch_error",
        "layer_b_unresolved",
        "ltm_incomputable",
        "ltm_degraded",
        "partial_coverage",
    ]
    message: str


class QueryResult(BaseModel):
    """Result for a single company, multiple metrics."""

    company: str
    cik: str
    period: str = "lfy"
    metrics: dict[str, CitedValue | list[CitedValue] | None]  # metric_name -> value(s) or None

    # Self-heal v2: structured diagnostics for Layer B failures.
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    # The user's original input token (e.g. "snap", "SNAP", or a CIK). When
    # present, permalink() renders this verbatim instead of the resolved CIK
    # so the Reproduce line reads back the way the user typed it.
    display_token: str | None = None

    @property
    def permalink(self) -> str:
        """CLI command that reproduces this query. Uses display_token when
        set (e.g., the ticker the user typed); falls back to the resolved CIK."""
        metric_names = ",".join(self.metrics.keys())
        subject = self.display_token or self.cik
        return f"edgarpack query {subject} {metric_names} --period {self.period}"

    def _iter_metric_items(
        self,
    ) -> list[tuple[str, CitedValue]]:
        """Flatten metric values into ``(metric_name, cited_value)`` tuples."""
        items: list[tuple[str, CitedValue]] = []
        for metric_name, value in self.metrics.items():
            if value is None:
                continue
            if isinstance(value, list):
                items.extend((metric_name, item) for item in value)
            else:
                items.append((metric_name, value))
        return items

    def _collect_citation_registry(self) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
        """Build citation registry and lookup map."""
        citations: dict[str, dict[str, object]] = {}
        key_to_id: dict[str, str] = {}
        next_idx = 1

        for _, item in self._iter_metric_items():
            all_values = [item]
            if isinstance(item, DerivedValue):
                all_values.extend(item.components.values())
            for cited in all_values:
                key = cited.citation_key
                if key in key_to_id:
                    continue
                citation_id = f"C{next_idx}"
                next_idx += 1
                key_to_id[key] = citation_id
                citations[citation_id] = cited.to_citation_record(citation_id)

        return citations, key_to_id

    @staticmethod
    def _calculation_record(
        calc_id: str,
        metric_name: str,
        derived: DerivedValue,
        key_to_id: dict[str, str],
    ) -> dict[str, object]:
        """Serialize a derived/LTM value into a normalized calculation record."""
        result_citation_id = key_to_id.get(derived.citation_key)
        formula = "mrp + lfy - mrp_prior" if derived._is_ltm_like() else derived.concept

        components: list[dict[str, object]] = []
        for role, component in derived.components.items():
            entry: dict[str, object] = {
                "role": role,
                "metric": component.metric,
                "concept": component.concept,
                "value": component.value,
                "unit": component.unit,
                "citation_id": key_to_id.get(component.citation_key),
                "fiscal_label": component.fiscal_label,
                "period": component._period_str(),
                "accession": component.accession,
                "form_type": component.form_type,
                "filed": str(component.filed),
                "primary_link": component.primary_link,
                "primary_link_type": component.primary_link_type,
            }
            if component.warnings:
                entry["warnings"] = list(component.warnings)
            components.append(entry)

        record: dict[str, object] = {
            "id": calc_id,
            "metric": metric_name,
            "kind": "ltm" if derived._is_ltm_like() else "derived",
            "formula": formula,
            "result": {
                "value": derived.value,
                "unit": derived.unit,
                "citation_id": result_citation_id,
            },
            "components": components,
        }
        if derived._is_ltm_like():
            record["ltm_variant"] = derived.fiscal_period.lower()
            record["window"] = {
                "start": str(derived.period_start) if derived.period_start else None,
                "end": str(derived.period_end),
            }
            comp_keys = set(derived.components.keys())
            record["method"] = (
                "computed" if {"mrp", "lfy", "mrp_prior"}.issubset(comp_keys) else "fallback"
            )
        if derived.warnings:
            record["warnings"] = list(derived.warnings)
        return record

    def _serialize_metrics(
        self,
        *,
        lean: bool,
    ) -> tuple[dict[str, object], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
        """Serialize metrics with additive citation/calculation IDs."""
        citations, key_to_id = self._collect_citation_registry()
        calculations: dict[str, dict[str, object]] = {}
        calc_counts: dict[str, int] = {"D": 1, "L": 1}

        def _serialize_one(metric_name: str, item: CitedValue) -> dict[str, object]:
            data = item.to_lean_metric() if lean else item.to_cited_dict()
            citation_id = key_to_id.get(item.citation_key)
            if citation_id:
                data["citation_ids"] = [citation_id]

            if isinstance(item, DerivedValue):
                prefix = "L" if item._is_ltm_like() else "D"
                calc_id = f"{prefix}{calc_counts[prefix]}"
                calc_counts[prefix] += 1

                component_citation_ids: dict[str, str] = {}
                for role, component in item.components.items():
                    cid = key_to_id.get(component.citation_key)
                    if cid:
                        component_citation_ids[role] = cid

                data["calculation_id"] = calc_id
                if component_citation_ids:
                    data["component_citation_ids"] = component_citation_ids
                    ltm_components = data.get("ltm_components")
                    if isinstance(ltm_components, dict):
                        for role, cid in component_citation_ids.items():
                            component_payload = ltm_components.get(role)
                            if isinstance(component_payload, dict):
                                component_payload["citation_id"] = cid

                calculations[calc_id] = self._calculation_record(
                    calc_id, metric_name, item, key_to_id
                )

            return data

        metrics_out: dict[str, object] = {}
        component_metrics: dict[str, CitedValue] = {}

        for metric_name, value in self.metrics.items():
            if value is None:
                metrics_out[metric_name] = None
                continue
            if isinstance(value, list):
                metrics_out[metric_name] = [_serialize_one(metric_name, item) for item in value]
                continue

            metrics_out[metric_name] = _serialize_one(metric_name, value)
            if isinstance(value, DerivedValue) and not value.fiscal_period.upper().startswith(
                "LTM"
            ):
                for comp_name, comp_val in value.components.items():
                    if comp_name not in self.metrics:
                        component_metrics[comp_name] = comp_val

        if lean:
            for comp_name, comp_val in component_metrics.items():
                if comp_name in metrics_out:
                    continue
                payload = _serialize_one(comp_name, comp_val)
                payload["_component"] = True
                metrics_out[comp_name] = payload

        return metrics_out, citations, calculations

    def to_cited_dict(self) -> dict[str, object]:
        metrics_out, citations, calculations = self._serialize_metrics(lean=False)
        result: dict[str, object] = {
            "company": self.company,
            "cik": self.cik,
            "permalink": self.permalink,
            "period": self.period,
        }
        result["metrics"] = metrics_out
        result["citations"] = citations
        result["calculations"] = calculations
        if self.diagnostics:
            result["diagnostics"] = [d.model_dump() for d in self.diagnostics]
        return result

    def _collect_filings(self) -> dict[str, dict[str, object]]:
        """Build a deduplicated filings lookup table keyed by accession."""
        filings: dict[str, dict[str, object]] = {}
        for v in self.metrics.values():
            if v is None:
                continue
            items = v if isinstance(v, list) else [v]
            for item in items:
                self._add_filing(filings, item)
                if isinstance(item, DerivedValue):
                    for comp in item.components.values():
                        self._add_filing(filings, comp)
        return filings

    @staticmethod
    def _add_filing(filings: dict[str, dict[str, object]], cited: CitedValue) -> None:
        """Add a filing entry if not already present."""
        acc = cited.accession
        source = cited
        if isinstance(cited, DerivedValue):
            source = next(
                (
                    component
                    for component in cited.components.values()
                    if component.accession and component.accession == cited.accession
                ),
                cited,
            )
        if acc and acc not in filings:
            entry: dict[str, object] = {
                "form_type": source.form_type,
                "filed": str(source.filed),
                "fiscal_year": source.fiscal_year,
                "fiscal_period": source.fiscal_period,
                "url": source.filing_url,
                "primary_link": source.primary_link,
                "primary_link_type": source.primary_link_type,
            }
            if source.viewer_url:
                entry["viewer_url"] = source.viewer_url
            if source.anchor_url and source.fact_id:
                entry["anchor_url"] = source.anchor_url
            filings[acc] = entry

    def to_lean_dict(self) -> dict[str, object]:
        """Lean JSON with filing deduplication and component auto-inclusion."""
        filings = self._collect_filings()
        metrics_out, citations, calculations = self._serialize_metrics(lean=True)

        d: dict[str, object] = {
            "company": self.company,
            "cik": self.cik,
            "period": self.period,
            "permalink": self.permalink,
            "filings": filings,
            "metrics": metrics_out,
            "citations": citations,
            "calculations": calculations,
        }
        if self.diagnostics:
            d["diagnostics"] = [diag.model_dump() for diag in self.diagnostics]
        return d
