"""Snapshot dataclasses and the on-disk cache for S-1 financial extraction.

`SnapshotFact` / `SnapshotResult` are the persisted shape of one registration
pack's extracted figures; the rest of this module is the cache gatekeeping
(hashing, schema versioning, freshness, retry cooldowns) shared by the table
parser, the LLM extractor, and the query integration layer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Canonical slug set. Must stay in sync with METRIC_MAP in
# edgarpack/query/metric_map.py so CitedValue conversions resolve
# correctly downstream.
METRIC_SLUGS: frozenset[str] = frozenset(
    {
        "revenue",
        "gross_profit",
        "adjusted_gross_profit",
        "operating_income_loss",
        "net_income_loss",
        "operating_cash_flow",
        "capex",
        "adjusted_ebitda",
        "cash_and_equivalents",
        "total_assets",
        "stockholders_equity",
        "shares_outstanding_basic",
        "eps_basic",
    }
)


@dataclass(frozen=True)
class SnapshotFact:
    """One financial figure extracted from an S-1 filing.

    value_cents is an integer in the reporting currency's smallest unit
    (cents for USD, öre for SEK, and so on). The currency field names the
    ISO 4217 code so callers can convert later if they want; v1 renders
    native-currency only.
    """

    accession: str
    fiscal_year: int
    period_end: str  # ISO date YYYY-MM-DD
    metric: str  # member of METRIC_SLUGS
    value_cents: int
    currency: str  # ISO 4217
    is_audited: bool
    is_pro_forma: bool
    pro_forma_note: str | None
    fiscal_period: str = "FY"
    source_text: str | None = None
    section_id: str | None = None
    chunk_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotResult:
    """All extracted facts for one S-1 pack, plus extraction metadata.

    Persisted as `<pack_dir>/s1_financials.json`. `source_sha256` is the
    sha256 of the whole `<pack_dir>/filing.full.md`, used to invalidate the
    cache when the source markdown changes.

    extraction_status is one of: "ok", "no_api_key" (missing key / anthropic
    ImportError only), "llm_call_failed" (runtime API failure, exception text
    in `detail`), "llm_parse_failed", "no_financial_data_found". The last
    three are retryable: `retry_after` holds the ISO-8601 timestamp before
    which a cached failure is served, after which a read re-attempts. `ok`
    snapshots never expire (invalidated by hash / schema only). `truncated`
    marks a snapshot salvaged from a truncated JSON array. `gate_rejections`
    records LLM rows dropped by the magnitude sanity gates.
    """

    schema_version: int
    accession: str
    extracted_at: str  # ISO 8601 UTC
    extraction_status: str
    source_sha256: str
    model: str
    facts: list[SnapshotFact]
    detail: str | None = None
    retry_after: str | None = None
    truncated: bool = False
    gate_rejections: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "accession": self.accession,
            "extracted_at": self.extracted_at,
            "extraction_status": self.extraction_status,
            "source_sha256": self.source_sha256,
            "model": self.model,
            "detail": self.detail,
            "retry_after": self.retry_after,
            "truncated": self.truncated,
            "gate_rejections": self.gate_rejections,
            "facts": [f.to_dict() for f in self.facts],
        }
        return json.dumps(payload, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> SnapshotResult:
        data = json.loads(raw)
        facts = [SnapshotFact(**f) for f in data.get("facts", [])]
        return cls(
            schema_version=int(data["schema_version"]),
            accession=str(data["accession"]),
            extracted_at=str(data["extracted_at"]),
            extraction_status=str(data["extraction_status"]),
            source_sha256=str(data["source_sha256"]),
            model=str(data["model"]),
            facts=facts,
            detail=(str(data["detail"]) if data.get("detail") is not None else None),
            retry_after=(str(data["retry_after"]) if data.get("retry_after") is not None else None),
            truncated=bool(data.get("truncated", False)),
            gate_rejections=[str(r) for r in data.get("gate_rejections", [])],
        )


def _utc_iso_now() -> str:
    """Single source of truth for ISO-8601 UTC timestamps used in caches."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


SCHEMA_VERSION = 9
_CACHE_FILENAME = "s1_financials.json"

# Statuses that describe a transient / recoverable failure. They are cached
# with a retry_after cooldown so a later read re-attempts instead of serving
# the failure forever. no_api_key is deliberately excluded: it is not cached,
# so adding the key and re-reading extracts immediately.
_RETRYABLE_STATUSES: frozenset[str] = frozenset(
    {"llm_call_failed", "llm_parse_failed", "no_financial_data_found"}
)
_RETRY_COOLDOWN = timedelta(minutes=30)


def _retry_after_iso() -> str:
    return (
        (datetime.now(UTC) + _RETRY_COOLDOWN)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _retry_cooldown_active(retry_after: str | None) -> bool:
    if not retry_after:
        return False
    try:
        deadline = datetime.fromisoformat(retry_after.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(UTC) < deadline


def source_sha256_for_pack(pack_dir: Path) -> str:
    md_path = Path(pack_dir) / "filing.full.md"
    if not md_path.exists():
        return ""
    # Hash the whole file: a parser fix or amendment past the first 50KB must
    # still invalidate the cached snapshot.
    blob = md_path.read_text(encoding="utf-8", errors="replace")
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_validated_snapshot(pack_dir: Path) -> tuple[SnapshotResult | None, str]:
    """Load s1_financials.json only when readable, schema-current, and fresh.

    Returns (snapshot, extraction_status) on success, else (None, reason)
    with reason in {"not_extracted", "cache_unreadable",
    "cache_stale_schema", "cache_stale_source"}. The single gatekeeper for
    every consumer of the cache (registration profile, distill).
    """
    cache = Path(pack_dir) / _CACHE_FILENAME
    if not cache.exists():
        return None, "not_extracted"
    try:
        snapshot = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None, "cache_unreadable"
    if snapshot.schema_version != SCHEMA_VERSION:
        return None, "cache_stale_schema"
    if snapshot.source_sha256 != source_sha256_for_pack(pack_dir):
        return None, "cache_stale_source"
    return snapshot, snapshot.extraction_status


def _read_manifest_accession(pack_dir: Path) -> str:
    manifest = Path(pack_dir) / "manifest.json"
    if not manifest.exists():
        return pack_dir.name
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pack_dir.name
    return str(data.get("filing", {}).get("accession", pack_dir.name))


def _write_snapshot(cache_path: Path, result: SnapshotResult) -> SnapshotResult:
    # no_api_key is never cached: re-attempt on the next read so adding the key
    # extracts immediately instead of serving a permanent placeholder.
    if result.extraction_status != "no_api_key":
        cache_path.write_text(result.to_json(), encoding="utf-8")
    return result
