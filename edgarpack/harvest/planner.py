"""Delta planner: determine which filings need to be built."""

from __future__ import annotations

from pydantic import BaseModel

from ..sec.submissions import FilingMeta, list_filings, normalize_cik
from ..sec.tickers import resolve_ticker
from .registry import PackRegistry
from .universe import UniverseConfig


class HarvestItem(BaseModel):
    """A single filing to be built."""

    model_config = {"arbitrary_types_allowed": True}

    cik: str
    ticker: str
    company_name: str
    accession: str
    form_type: str
    filing_date: str
    primary_document: str
    already_built: bool = False


class HarvestPlan(BaseModel):
    """Plan for a harvest run."""

    items: list[HarvestItem]
    skipped: list[HarvestItem]
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

    Args:
        universe: Universe configuration with company specs
        registry: Pack registry to check existing builds
        refresh: If True, only include filings not yet built

    Returns:
        HarvestPlan with items to build and items to skip
    """
    items: list[HarvestItem] = []
    skipped: list[HarvestItem] = []

    for spec in universe.companies:
        # Resolve CIK if not provided
        cik = spec.cik
        if cik is None:
            resolved_cik, _ = await resolve_ticker(spec.ticker)
            cik = resolved_cik
        cik = normalize_cik(cik)

        form_counts = universe.form_counts(spec)

        for form_type, count in form_counts.items():
            filings: list[FilingMeta] = await list_filings(cik, form_type=form_type, limit=count)

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
        total_filings=total,
        new_filings=new,
        already_built=built,
    )
