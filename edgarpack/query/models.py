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
        return f"{SEC_ARCHIVES_BASE}/{self.cik.lstrip('0')}/{acc_nodash}/"

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


class DerivedValue(CitedValue):
    """For computed metrics (margins, ratios). Carries source components."""

    derived: bool = True
    components: dict[str, CitedValue] = {}

    def to_cited_dict(self) -> dict[str, object]:
        d = super().to_cited_dict()
        d["components"] = {k: v.to_cited_dict() for k, v in self.components.items()}
        return d


class QueryResult(BaseModel):
    """Result for a single company, multiple metrics."""

    company: str
    cik: str
    metrics: dict[str, CitedValue | list[CitedValue] | None]  # metric_name -> value(s) or None

    def to_cited_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "company": self.company,
            "cik": self.cik,
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
