"""Load company universe from TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, model_validator

from ..sec.submissions import REGISTRATION_SENTINEL


class CompanySpec(BaseModel):
    """A company in the harvest universe.

    At least one of `ticker`, `name`, or `cik` must be provided. The harvest
    planner tries them in that order (cik first when given, then ticker, then
    name) to resolve the CIK needed for SEC API calls.
    """

    ticker: str | None = None
    name: str | None = None
    cik: str | None = None
    forms_10k: int | None = None
    forms_10q: int | None = None
    forms_8k: int | None = None
    forms_20f: int | None = None
    forms_s1: int | None = None
    listing: str | None = None
    aliases: list[str] = []
    alt_tickers: list[str] = []
    hk_stock_code: str | None = None
    stock_code: str | None = None
    private: bool = False

    @model_validator(mode="after")
    def _require_one_identifier(self) -> CompanySpec:
        if not (self.ticker or self.name or self.cik):
            raise ValueError("CompanySpec requires at least one identifier: ticker, name, or cik.")
        return self

    @model_validator(mode="after")
    def _infer_private(self) -> CompanySpec:
        if self.listing == "PRIVATE":
            self.private = True
        return self

    @property
    def display_label(self) -> str:
        """Human label for logs and errors: ticker, else name, else CIK."""
        return self.ticker or self.name or f"CIK {self.cik}"


class UniverseConfig(BaseModel):
    """Parsed universe configuration."""

    defaults_10k: int = 2
    defaults_10q: int = 4
    defaults_8k: int = 5
    companies: list[CompanySpec]

    def form_counts(self, spec: CompanySpec) -> dict[str, int]:
        """Get effective form counts for a company, applying defaults.

        Pre-IPO inference: when `forms_s1 > 0` and the filer has NOT explicitly
        set a periodic form count, that periodic form defaults to 0 (not the
        global default) to avoid spurious harvest_errors for filings that do
        not yet exist.
        """
        counts: dict[str, int] = {}

        is_pre_ipo = bool(spec.forms_s1 and spec.forms_s1 > 0)

        def _effective(explicit: int | None, default: int) -> int:
            if explicit is not None:
                return explicit
            if is_pre_ipo:
                return 0
            return default

        k10 = _effective(spec.forms_10k, self.defaults_10k)
        q10 = _effective(spec.forms_10q, self.defaults_10q)
        k8 = _effective(spec.forms_8k, self.defaults_8k)
        f20 = spec.forms_20f if spec.forms_20f is not None else 0
        s1 = spec.forms_s1 if spec.forms_s1 is not None else 0

        if k10 > 0:
            counts["10-K"] = k10
        if q10 > 0:
            counts["10-Q"] = q10
        if k8 > 0:
            counts["8-K"] = k8
        if f20 > 0:
            counts["20-F"] = f20
        if s1 > 0:
            counts[REGISTRATION_SENTINEL] = s1
        return counts


def load_universe(path: Path) -> UniverseConfig:
    """Load universe configuration from a TOML file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    defaults = data.get("defaults", {})
    companies_raw = data.get("companies", [])

    companies = [CompanySpec(**c) for c in companies_raw]

    return UniverseConfig(
        defaults_10k=defaults.get("forms_10k", 2),
        defaults_10q=defaults.get("forms_10q", 4),
        defaults_8k=defaults.get("forms_8k", 5),
        companies=companies,
    )
