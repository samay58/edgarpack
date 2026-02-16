"""Citation data models for financial query results."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from ..config import SEC_ARCHIVES_BASE


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

    @property
    def filing_url(self) -> str:
        """SEC EDGAR filing URL."""
        acc_nodash = self.accession.replace("-", "")
        return f"{SEC_ARCHIVES_BASE}/{self.cik.lstrip('0')}/{acc_nodash}/{self.accession}-index.htm"

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
            filings[acc] = {
                "form_type": cited.form_type,
                "filed": str(cited.filed),
                "fiscal_year": cited.fiscal_year,
                "fiscal_period": cited.fiscal_period,
                "url": cited.filing_url,
            }

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
