"""Delta planner: determine which filings need to be built."""

from __future__ import annotations

import sys

from pydantic import BaseModel

from ..sec.submissions import FilingMeta, list_filings, normalize_cik
from ..sec.tickers import resolve_ticker
from .registry import PackRegistry
from .universe import UniverseConfig


class HarvestItem(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    cik: str
    ticker: str
    company_name: str
    accession: str
    form_type: str
    filing_date: str
    primary_document: str
    already_built: bool = False


class PlanError(BaseModel):
    ticker: str
    form_type: str | None = None
    error: str


class HarvestPlan(BaseModel):
    items: list[HarvestItem]
    skipped: list[HarvestItem]
    errors: list[PlanError] = []
    total_filings: int
    new_filings: int
    already_built: int

    @property
    def pending(self) -> list[HarvestItem]:
        return [i for i in self.items if not i.already_built]


async def plan_harvest(
    universe: UniverseConfig,
    registry: PackRegistry,
    refresh: bool = False,
) -> HarvestPlan:
    """Build a delta plan comparing universe spec against registry state.

    Resilient to individual ticker/filing failures — logs errors and continues.
    """
    items: list[HarvestItem] = []
    skipped: list[HarvestItem] = []
    errors: list[PlanError] = []

    for spec in universe.companies:
        cik = spec.cik
        if cik is None:
            try:
                resolved_cik, _ = await resolve_ticker(spec.ticker)
                cik = resolved_cik
            except Exception as e:
                msg = str(e)[:120]
                errors.append(PlanError(ticker=spec.ticker, error=msg))
                print(f"  SKIP {spec.ticker}: {msg}", file=sys.stderr)
                continue
        cik = normalize_cik(cik)

        form_counts = universe.form_counts(spec)

        for form_type, count in form_counts.items():
            try:
                filings: list[FilingMeta] = await list_filings(
                    cik, form_type=form_type, limit=count
                )
            except Exception as e:
                msg = str(e)[:120]
                errors.append(PlanError(ticker=spec.ticker, form_type=form_type, error=msg))
                print(
                    f"  SKIP {spec.ticker} {form_type}: {msg}",
                    file=sys.stderr,
                )
                continue

            for filing in filings:
                already_built = registry.has_accession(filing.accession)
                item = HarvestItem(
                    cik=cik,
                    ticker=spec.ticker.upper(),
                    company_name=filing.company_name,
                    accession=filing.accession,
                    form_type=filing.form_type,
                    filing_date=filing.filing_date.isoformat(),
                    primary_document=filing.primary_document,
                    already_built=already_built,
                )

                if already_built and refresh:
                    skipped.append(item)
                else:
                    items.append(item)

    total = len(items) + len(skipped)
    new = len([i for i in items if not i.already_built])
    built = len([i for i in items if i.already_built]) + len(skipped)

    return HarvestPlan(
        items=items,
        skipped=skipped,
        errors=errors,
        total_filings=total,
        new_filings=new,
        already_built=built,
    )
