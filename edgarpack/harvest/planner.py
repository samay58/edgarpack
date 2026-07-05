"""Delta planner: determine which filings need to be built."""

from __future__ import annotations

import sys

from pydantic import BaseModel

from ..sec.submissions import (
    REGISTRATION_FORMS,
    REGISTRATION_SENTINEL,
    FilingMeta,
    list_filings,
    normalize_cik,
)
from ..sec.tickers import resolve_filer
from .registry import PackRegistry
from .universe import UniverseConfig


class HarvestItem(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    cik: str | None = None
    ticker: str
    company_name: str
    accession: str | None = None
    form_type: str
    filing_date: str
    primary_document: str | None = None
    already_built: bool = False
    # SSE (A-share) items carry market/stock_code instead of cik/accession;
    # SEC items leave both None.
    market: str | None = None
    stock_code: str | None = None


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


async def _list_registration_filings(cik: str, limit: int) -> list[FilingMeta]:
    collected: list[FilingMeta] = []
    for form in REGISTRATION_FORMS:
        try:
            hits = await list_filings(cik, form_type=form, limit=limit)
        except Exception:
            continue
        collected.extend(hits)

    seen: set[str] = set()
    unique: list[FilingMeta] = []
    for f in sorted(collected, key=lambda x: x.filing_date, reverse=True):
        if f.accession in seen:
            continue
        seen.add(f.accession)
        unique.append(f)
    return unique[:limit]


async def plan_harvest(
    universe: UniverseConfig,
    registry: PackRegistry,
    refresh: bool = False,
) -> HarvestPlan:
    """Build a delta plan comparing universe spec against registry state.

    Resilient to individual ticker/filing failures: logs errors and continues.
    """
    items: list[HarvestItem] = []
    skipped: list[HarvestItem] = []
    errors: list[PlanError] = []

    for spec in universe.companies:
        if spec.private:
            continue

        if spec.listing == "SSE":
            # HKEX is not planned here; that lane waits on build-hk and will
            # need its own branch once an HKEX harvest path exists.
            if not spec.stock_code:
                msg = "SSE entries require a stock_code to plan an annual-report harvest"
                errors.append(
                    PlanError(ticker=spec.display_label, form_type="ANNUAL-REPORT", error=msg)
                )
                print(f"  SKIP {spec.display_label}: {msg}", file=sys.stderr)
                continue

            items.append(
                HarvestItem(
                    cik=None,
                    ticker=(spec.ticker or spec.stock_code).upper(),
                    company_name=spec.name or spec.display_label,
                    accession=None,
                    form_type="ANNUAL-REPORT",
                    filing_date="",
                    primary_document=None,
                    already_built=False,
                    market="SSE",
                    stock_code=spec.stock_code,
                )
            )
            continue

        try:
            resolved_cik, _title = await resolve_filer(spec)
        except Exception as e:
            msg = str(e)[:120]
            errors.append(PlanError(ticker=spec.display_label, error=msg))
            print(f"  SKIP {spec.display_label}: {msg}", file=sys.stderr)
            continue
        cik = normalize_cik(resolved_cik)

        form_counts = universe.form_counts(spec)

        for form_type, count in form_counts.items():
            try:
                if form_type == REGISTRATION_SENTINEL:
                    filings: list[FilingMeta] = await _list_registration_filings(cik, count)
                else:
                    filings = await list_filings(cik, form_type=form_type, limit=count)
            except Exception as e:
                msg = str(e)[:120]
                errors.append(PlanError(ticker=spec.display_label, form_type=form_type, error=msg))
                print(
                    f"  SKIP {spec.display_label} {form_type}: {msg}",
                    file=sys.stderr,
                )
                continue

            for filing in filings:
                already_built = registry.has_accession(filing.accession)
                item = HarvestItem(
                    cik=cik,
                    ticker=(spec.ticker or "").upper(),
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
