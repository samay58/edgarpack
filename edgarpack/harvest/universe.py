"""Load company universe from TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel


class CompanySpec(BaseModel):
    """A company in the harvest universe."""

    ticker: str
    cik: str | None = None
    forms_10k: int | None = None
    forms_10q: int | None = None
    forms_8k: int | None = None
    forms_20f: int | None = None
    # China query parity (edgarpack-2yg): identity + listing metadata.
    listing: str | None = None
    aliases: list[str] = []
    alt_tickers: list[str] = []
    hk_stock_code: str | None = None


class UniverseConfig(BaseModel):
    """Parsed universe configuration."""

    defaults_10k: int = 2
    defaults_10q: int = 4
    defaults_8k: int = 5
    companies: list[CompanySpec]

    def form_counts(self, spec: CompanySpec) -> dict[str, int]:
        """Get effective form counts for a company, applying defaults."""
        counts: dict[str, int] = {}
        k10 = spec.forms_10k if spec.forms_10k is not None else self.defaults_10k
        q10 = spec.forms_10q if spec.forms_10q is not None else self.defaults_10q
        k8 = spec.forms_8k if spec.forms_8k is not None else self.defaults_8k
        f20 = spec.forms_20f if spec.forms_20f is not None else 0
        if k10 > 0:
            counts["10-K"] = k10
        if q10 > 0:
            counts["10-Q"] = q10
        if k8 > 0:
            counts["8-K"] = k8
        if f20 > 0:
            counts["20-F"] = f20
        return counts


def load_universe(path: Path) -> UniverseConfig:
    """Load universe configuration from a TOML file.

    Args:
        path: Path to universe.toml

    Returns:
        Parsed UniverseConfig
    """
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
