"""Registration-filing profile assembly for S-1 and F-1 packs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..sec.submissions import is_registration_form
from .kpi_discover import DisclosureHit, FramingHit, extract_s1_metrics_from_pack
from .s1_financials import SCHEMA_VERSION, SnapshotResult, source_sha256_for_pack

PROFILE_SCHEMA_VERSION = 1

_DISPLAY_FOR_SNAPSHOT_METRIC = {
    "operating_income_loss": "operating_income",
    "net_income_loss": "net_income",
    "cash_and_equivalents": "cash",
}

_REGISTRATION_FINANCIAL_ORDER = [
    "revenue",
    "gross_profit",
    "gross_margin",
    "operating_income",
    "operating_margin",
    "net_income",
    "net_margin",
    "adjusted_gross_profit",
    "adjusted_ebitda",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash",
    "total_assets",
    "stockholders_equity",
    "shares_outstanding_basic",
    "eps_basic",
]


@dataclass(frozen=True)
class RegistrationDisclosureGroup:
    label: str
    claims: tuple[str, ...]


@dataclass(frozen=True)
class RegistrationProfile:
    schema_version: int
    accession: str
    form_type: str
    filing_date: str
    financial_metrics: tuple[str, ...]
    financial_status: str
    disclosures: tuple[RegistrationDisclosureGroup, ...]
    source_status: str

    @property
    def has_content(self) -> bool:
        return bool(self.financial_metrics or any(group.claims for group in self.disclosures))


def _manifest_filing(pack_dir: Path) -> dict[str, object] | None:
    manifest = pack_dir / "manifest.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    filing = data.get("filing")
    return filing if isinstance(filing, dict) else None


def _normalize_claim(claim: str) -> str:
    return re.sub(r"\s+", " ", claim).strip().lower().rstrip(".")


def _dedupe_claims(hits: list[FramingHit] | list[DisclosureHit]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for hit in hits:
        claim = hit.claim.strip()
        key = _normalize_claim(claim)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(claim)
    return tuple(out)


def _financial_metrics_from_cache(pack_dir: Path) -> tuple[tuple[str, ...], str]:
    cache = pack_dir / "s1_financials.json"
    if not cache.exists():
        return (), "not_extracted"
    try:
        snapshot = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return (), "cache_unreadable"
    if snapshot.schema_version != SCHEMA_VERSION:
        return (), "cache_stale"
    if snapshot.source_sha256 != source_sha256_for_pack(pack_dir):
        return (), "cache_stale"

    raw_metrics = {
        fact.metric
        for fact in snapshot.facts
        if fact.is_audited
        and not fact.is_pro_forma
        and (fact.fiscal_period or "FY").upper() == "FY"
    }
    display_metrics = {
        _DISPLAY_FOR_SNAPSHOT_METRIC.get(metric, metric)
        for metric in raw_metrics
    }
    if {"gross_profit", "revenue"}.issubset(raw_metrics):
        display_metrics.add("gross_margin")
    if {"operating_income_loss", "revenue"}.issubset(raw_metrics):
        display_metrics.add("operating_margin")
    if {"net_income_loss", "revenue"}.issubset(raw_metrics):
        display_metrics.add("net_margin")
    if {"operating_cash_flow", "capex"}.issubset(raw_metrics):
        display_metrics.add("free_cash_flow")

    ordered = [metric for metric in _REGISTRATION_FINANCIAL_ORDER if metric in display_metrics]
    ordered.extend(sorted(display_metrics - set(ordered)))
    if ordered:
        return tuple(ordered), snapshot.extraction_status
    return (), snapshot.extraction_status or "empty"


def build_registration_profile(pack_dir: Path) -> RegistrationProfile | None:
    pack_dir = Path(pack_dir)
    filing = _manifest_filing(pack_dir)
    if filing is None:
        return None
    form_type = str(filing.get("form_type", ""))
    if not is_registration_form(form_type):
        return None

    bundle = extract_s1_metrics_from_pack(pack_dir)
    disclosures: list[RegistrationDisclosureGroup] = []
    if bundle is not None:
        for label, hits in (
            ("framing claims", bundle.framing),
            ("use of proceeds", bundle.use_of_proceeds),
            ("dilution", bundle.dilution),
            ("lockup terms", bundle.lockup),
            ("principal holders", bundle.principal_holders),
        ):
            claims = _dedupe_claims(hits)
            if claims:
                disclosures.append(RegistrationDisclosureGroup(label=label, claims=claims))

    financial_metrics, financial_status = _financial_metrics_from_cache(pack_dir)
    source_status = "ok" if financial_metrics or disclosures else "empty"
    return RegistrationProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        accession=str(filing.get("accession") or pack_dir.name),
        form_type=form_type,
        filing_date=str(filing.get("filing_date") or ""),
        financial_metrics=financial_metrics,
        financial_status=financial_status,
        disclosures=tuple(disclosures),
        source_status=source_status,
    )
