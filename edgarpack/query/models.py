"""Citation data models for financial query results."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

from pydantic import BaseModel

from ..config import SEC_ARCHIVES_BASE, SEC_DATA_BASE


def _concept_to_label(concept: str) -> str:
    """Convert a camelCase XBRL tag to a space-separated label.

    Example: "NetIncomeLoss" -> "Net Income Loss"
    """
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", concept)


class CitedValue(BaseModel):
    """A single financial data point with full provenance chain."""

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

    @property
    def filing_url(self) -> str:
        """SEC EDGAR filing URL."""
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

        Uses Chrome/Edge #:~:text= to scroll to the concept label.
        Returns None if no primary_document is available.
        """
        if not self.primary_document:
            return None
        acc_nodash = self.accession.replace("-", "")
        cik_bare = self.cik.lstrip("0")
        base = f"{SEC_ARCHIVES_BASE}/{cik_bare}/{acc_nodash}/{self.primary_document}"
        label = _concept_to_label(self.concept)
        return f"{base}#:~:text={quote(label)}"

    @property
    def citation(self) -> str:
        """Human-readable citation string."""
        period = f"{self.fiscal_period}{self.fiscal_year}"
        return f"{self.company} {self.form_type} ({period}), filed {self.filed}"

    def to_cited_dict(self) -> dict[str, object]:
        """JSON-serializable dict with citation baked in."""
        d = self.model_dump(mode="json")
        d["filing_url"] = self.filing_url
        d["citation"] = self.citation
        if self.concept_url:
            d["concept_url"] = self.concept_url
        if self.viewer_url:
            d["viewer_url"] = self.viewer_url
        if self.document_url:
            d["document_url"] = self.document_url
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
        }
        if self.concept_url:
            d["concept_url"] = self.concept_url
        return d


class DerivedValue(CitedValue):
    """For computed metrics (margins, ratios). Carries source components."""

    derived: bool = True
    components: dict[str, CitedValue] = {}

    @property
    def citation(self) -> str:
        """LTM values cite the underlying real filings."""
        if self.fiscal_period == "LTM" and self.components:
            sources = [v.citation for v in self.components.values()]
            return f"LTM computed from: {'; '.join(sources)}"
        return super().citation

    def to_cited_dict(self) -> dict[str, object]:
        d = super().to_cited_dict()
        d["components"] = {k: v.to_cited_dict() for k, v in self.components.items()}
        return d

    def to_lean_metric(self) -> dict[str, object]:
        """Lean dict for a derived metric."""
        d = super().to_lean_metric()
        d["derived"] = True
        d["formula"] = self.concept  # concept holds the formula for derived metrics

        if self.fiscal_period == "LTM" and self.components:
            # LTM components are temporal slices, inline them
            d["formula"] = "mrp + lfy - mrp_prior"
            ltm_comps: dict[str, object] = {}
            for k, v in self.components.items():
                ltm_comps[k] = {
                    "value": v.value,
                    "accession": v.accession,
                }
            d["ltm_components"] = ltm_comps
        else:
            # Standard derived metric (ratio/sum): reference component names
            d["components"] = list(self.components.keys())

        return d


class QueryResult(BaseModel):
    """Result for a single company, multiple metrics."""

    company: str
    cik: str
    period: str = "lfy"
    metrics: dict[str, CitedValue | list[CitedValue] | None]  # metric_name -> value(s) or None

    @property
    def permalink(self) -> str:
        """CLI command that reproduces this query."""
        metric_names = ",".join(self.metrics.keys())
        return f"edgarpack query {self.cik} {metric_names} --period {self.period}"

    def to_cited_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "company": self.company,
            "cik": self.cik,
            "permalink": self.permalink,
        }
        metrics_out: dict[str, object] = {}
        for k, v in self.metrics.items():
            if v is None:
                metrics_out[k] = None
            elif isinstance(v, list):
                metrics_out[k] = [item.to_cited_dict() for item in v]
            else:
                metrics_out[k] = v.to_cited_dict()
        result["metrics"] = metrics_out
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
        if acc and acc not in filings:
            entry: dict[str, object] = {
                "form_type": cited.form_type,
                "filed": str(cited.filed),
                "fiscal_year": cited.fiscal_year,
                "fiscal_period": cited.fiscal_period,
                "url": cited.filing_url,
            }
            if cited.viewer_url:
                entry["viewer_url"] = cited.viewer_url
            filings[acc] = entry

    def to_lean_dict(self) -> dict[str, object]:
        """Lean JSON with filing deduplication and component auto-inclusion."""
        filings = self._collect_filings()

        metrics_out: dict[str, object] = {}
        component_metrics: dict[str, CitedValue] = {}

        for k, v in self.metrics.items():
            if v is None:
                metrics_out[k] = None
            elif isinstance(v, list):
                metrics_out[k] = [item.to_lean_metric() for item in v]
            else:
                metrics_out[k] = v.to_lean_metric()
                # Collect component values for auto-inclusion
                if isinstance(v, DerivedValue) and v.fiscal_period != "LTM":
                    for comp_name, comp_val in v.components.items():
                        if comp_name not in self.metrics:
                            component_metrics[comp_name] = comp_val

        # Auto-include component values not explicitly requested
        for comp_name, comp_val in component_metrics.items():
            if comp_name not in metrics_out:
                d = comp_val.to_lean_metric()
                d["_component"] = True
                metrics_out[comp_name] = d

        return {
            "company": self.company,
            "cik": self.cik,
            "period": self.period,
            "permalink": self.permalink,
            "filings": filings,
            "metrics": metrics_out,
        }
