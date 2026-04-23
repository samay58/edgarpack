"""Extract headline financial figures from pre-IPO S-1 filings.

SEC's companyfacts API is empty for pre-IPO filers (it's populated from
10-K / 10-Q / 20-F only), and Cerebras-era S-1 primary documents carry
no embedded iXBRL tags. The real numbers live in the filing's rendered
prose and tables. This module extracts them with a single Haiku 4.5
call per filing, caches the result to disk, and exposes them through
the existing `edgarpack query` surface via a fallback in
`edgarpack/query/financials.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

# Canonical slug set. Must stay in sync with METRIC_MAP in
# edgarpack/query/metric_map.py so CitedValue conversions resolve
# correctly downstream.
METRIC_SLUGS: frozenset[str] = frozenset(
    {
        "revenue",
        "gross_profit",
        "operating_income_loss",
        "net_income_loss",
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

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotResult:
    """All extracted facts for one S-1 pack, plus extraction metadata.

    Persisted as `<pack_dir>/s1_financials.json`. `source_sha256` is the
    sha256 of the first 50KB of `<pack_dir>/filing.full.md`, used to
    invalidate the cache when the source markdown changes.
    """

    schema_version: int
    accession: str
    extracted_at: str  # ISO 8601 UTC
    extraction_status: str  # "ok" | "llm_parse_failed" | "no_financial_data_found" | "no_api_key"
    source_sha256: str
    model: str
    facts: list[SnapshotFact]

    def to_json(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "accession": self.accession,
            "extracted_at": self.extracted_at,
            "extraction_status": self.extraction_status,
            "source_sha256": self.source_sha256,
            "model": self.model,
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
        )


def _utc_iso_now() -> str:
    """Single source of truth for ISO-8601 UTC timestamps used in caches."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# S-1 filers use a handful of canonical phrasings for the financial
# summary section. Match the opening heading, stop at the next level-1
# or level-2 heading. Case-insensitive so Cerebras's "Selected Financial
# Data" and Klarna's "SELECTED FINANCIAL DATA" both fire.
_FINANCIAL_DATA_HEADINGS = [
    r"selected consolidated financial data",
    r"summary consolidated financial data",
    r"selected financial data",
    r"summary financial data",
    r"selected historical financial data",
]

_FINDATA_RE = re.compile(
    r"^\#{1,3}\s+(?:" + "|".join(_FINANCIAL_DATA_HEADINGS) + r")\b",
    re.IGNORECASE | re.MULTILINE,
)

# Section content is capped to keep the prompt well under Haiku's context
# window and to prevent runaway costs when the filing has a malformed TOC
# that absorbs 100KB+ of body text.
_SECTION_CAP_CHARS = 50_000


def find_financial_data_section(markdown: str) -> str | None:
    """Return the Selected Financial Data section body, or None if absent.

    Matches any of the canonical S-1 phrasings, truncates to 50KB, and
    stops at the next heading line so adjacent sections don't bleed in.
    """
    if not markdown:
        return None
    match = _FINDATA_RE.search(markdown)
    if not match:
        return None
    start = match.start()
    rest = markdown[start:]
    # End at the next H1/H2 heading after at least one newline of body.
    next_heading = re.search(r"\n\#{1,2}\s+\S", rest[1:])
    if next_heading is not None:
        end = 1 + next_heading.start()
        rest = rest[:end]
    return rest[:_SECTION_CAP_CHARS]


PROMPT_SYSTEM = (
    "You are extracting historical and pro-forma financial figures from an "
    "SEC Form S-1 filing. Return ONLY a JSON array. Do not fabricate: emit "
    "ONLY facts the filing explicitly states. Skip any figure you are less "
    "than 90% confident about."
)

_PROMPT_USER_TEMPLATE = """Return a JSON array. Each element is one fact:

{{
  "fiscal_year": 2024,
  "period_end": "2024-12-31",
  "metric": "revenue" | "gross_profit" | "operating_income_loss" | "net_income_loss"
          | "cash_and_equivalents" | "total_assets" | "stockholders_equity"
          | "shares_outstanding_basic" | "eps_basic",
  "value_cents": 78287000000,
  "currency": "USD",
  "is_audited": true,
  "is_pro_forma": false,
  "pro_forma_note": null
}}

RULES:
- Values are integers in the reporting currency's smallest unit (cents for USD).
- Do NOT scale: if the filing says "78,287" and the preamble says "in thousands"
  then value_cents = 78,287 * 1000 * 100 = 7,828,700,000.
- Losses are negative integers (e.g. "Net loss (259,251)" with "in thousands"
  becomes value_cents = -25,925,100,000).
- Per-share figures: value_cents is cents per share. "$(1.08)" becomes -108.
- Share counts: shares_outstanding_basic uses value_cents for the count itself
  (scaled by 100). "240,123,456" shares becomes value_cents = 24,012,345,600.
- Pro-forma rows MUST set is_pro_forma=true and record the assumption verbatim
  in pro_forma_note. Historical audited rows set is_pro_forma=false.
- period_end must be ISO YYYY-MM-DD.
- Return [] when the text contains no extractable financial data.

TEXT:
{text}
"""


def build_extraction_prompt(section_text: str) -> str:
    enum_line = " | ".join(f'"{s}"' for s in sorted(METRIC_SLUGS))
    return _PROMPT_USER_TEMPLATE.format(text=section_text) + (
        f"\n\n# Metric slugs allowed: {enum_line}"
    )


def _strip_code_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


_REQUIRED_KEYS = (
    "fiscal_year",
    "period_end",
    "metric",
    "value_cents",
    "currency",
    "is_audited",
    "is_pro_forma",
)


MODEL_ID = "claude-haiku-4-5-20251001"
_MAX_OUTPUT_TOKENS = 4000


async def _call_haiku_extract(section_text: str) -> str:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError(
            "S-1 financial extraction requires the `anthropic` package. "
            "Install with `pip install edgarpack[vlm]` and export "
            "ANTHROPIC_API_KEY."
        ) from exc

    client = AsyncAnthropic()
    prompt = build_extraction_prompt(section_text)
    message = await client.messages.create(
        model=MODEL_ID,
        max_tokens=_MAX_OUTPUT_TOKENS,
        system=PROMPT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [block.text for block in message.content if getattr(block, "type", "") == "text"]
    return "".join(text_blocks).strip()


def parse_llm_response(raw: str, *, accession: str) -> list[SnapshotFact]:
    """Parse the model's JSON response into SnapshotFact objects.

    Drops any row missing required keys or whose metric is not in
    METRIC_SLUGS. Raises ValueError for unparseable output so callers
    can mark the extraction as failed and cache accordingly.
    """
    stripped = _strip_code_fences(raw)
    if not stripped:
        raise ValueError("invalid JSON: empty response")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"expected JSON array, got {type(payload).__name__}")

    facts: list[SnapshotFact] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        if any(k not in row for k in _REQUIRED_KEYS):
            continue
        if row.get("metric") not in METRIC_SLUGS:
            continue
        try:
            fact = SnapshotFact(
                accession=accession,
                fiscal_year=int(row["fiscal_year"]),
                period_end=str(row["period_end"]),
                metric=str(row["metric"]),
                value_cents=int(row["value_cents"]),
                currency=str(row["currency"]),
                is_audited=bool(row["is_audited"]),
                is_pro_forma=bool(row["is_pro_forma"]),
                pro_forma_note=(
                    str(row["pro_forma_note"]) if row.get("pro_forma_note") is not None else None
                ),
            )
        except (ValueError, TypeError):
            continue
        facts.append(fact)
    return facts


SCHEMA_VERSION = 1
_CACHE_FILENAME = "s1_financials.json"
_SOURCE_SCAN_CHARS = 50_000


def source_sha256_for_pack(pack_dir: Path) -> str:
    md_path = Path(pack_dir) / "filing.full.md"
    if not md_path.exists():
        return ""
    blob = md_path.read_text(encoding="utf-8", errors="replace")[:_SOURCE_SCAN_CHARS]
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_manifest_accession(pack_dir: Path) -> str:
    manifest = Path(pack_dir) / "manifest.json"
    if not manifest.exists():
        return pack_dir.name
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pack_dir.name
    return str(data.get("filing", {}).get("accession", pack_dir.name))


async def extract_or_load_snapshot(pack_dir: Path, *, force: bool = False) -> SnapshotResult:
    pack_dir = Path(pack_dir)
    accession = _read_manifest_accession(pack_dir)
    source_hash = source_sha256_for_pack(pack_dir)
    cache_path = pack_dir / _CACHE_FILENAME

    if not force and cache_path.exists():
        try:
            cached = SnapshotResult.from_json(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            cached = None
        if (
            cached is not None
            and cached.schema_version == SCHEMA_VERSION
            and cached.source_sha256 == source_hash
        ):
            return cached

    markdown = ""
    md_path = pack_dir / "filing.full.md"
    if md_path.exists():
        markdown = md_path.read_text(encoding="utf-8", errors="replace")

    section = find_financial_data_section(markdown)
    if section is None:
        result = SnapshotResult(
            schema_version=SCHEMA_VERSION,
            accession=accession,
            extracted_at=_utc_iso_now(),
            extraction_status="no_financial_data_found",
            source_sha256=source_hash,
            model=MODEL_ID,
            facts=[],
        )
        cache_path.write_text(result.to_json(), encoding="utf-8")
        return result

    try:
        raw = await _call_haiku_extract(section)
    except RuntimeError:
        return SnapshotResult(
            schema_version=SCHEMA_VERSION,
            accession=accession,
            extracted_at=_utc_iso_now(),
            extraction_status="no_api_key",
            source_sha256=source_hash,
            model=MODEL_ID,
            facts=[],
        )

    try:
        facts = parse_llm_response(raw, accession=accession)
        status = "ok"
    except ValueError:
        facts = []
        status = "llm_parse_failed"

    result = SnapshotResult(
        schema_version=SCHEMA_VERSION,
        accession=accession,
        extracted_at=_utc_iso_now(),
        extraction_status=status,
        source_sha256=source_hash,
        model=MODEL_ID,
        facts=facts,
    )
    cache_path.write_text(result.to_json(), encoding="utf-8")
    return result


from datetime import date as _date_cls  # noqa: E402

from edgarpack.query.models import CitedValue  # noqa: E402
from edgarpack.sec.submissions import is_registration_form  # noqa: E402

# Maps a snapshot metric slug to (unit, divisor) for CitedValue conversion.
# For monetary and per-share metrics the divisor is 100 (cents -> USD).
# For share counts the divisor is 100 (we stored count * 100 in cents).
_UNIT_FOR_METRIC: dict[str, tuple[str, int]] = {
    "revenue": ("USD", 100),
    "gross_profit": ("USD", 100),
    "operating_income_loss": ("USD", 100),
    "net_income_loss": ("USD", 100),
    "cash_and_equivalents": ("USD", 100),
    "total_assets": ("USD", 100),
    "stockholders_equity": ("USD", 100),
    "shares_outstanding_basic": ("shares", 100),
    "eps_basic": ("USD/shares", 100),
}

# Default GAAP concept label per slug; used for the CitedValue.concept field
# on snapshot rows. Purely cosmetic, since snapshots are not sourced from
# GAAP tags, but keeps existing renderers that read .concept happy.
_DEFAULT_CONCEPTS: dict[str, str] = {
    "revenue": "Revenues",
    "gross_profit": "GrossProfit",
    "operating_income_loss": "OperatingIncomeLoss",
    "net_income_loss": "NetIncomeLoss",
    "cash_and_equivalents": "CashAndCashEquivalentsAtCarryingValue",
    "total_assets": "Assets",
    "stockholders_equity": "StockholdersEquity",
    "shares_outstanding_basic": "WeightedAverageNumberOfSharesOutstandingBasic",
    "eps_basic": "EarningsPerShareBasic",
}


def snapshot_fact_to_cited_value(
    fact: SnapshotFact,
    *,
    cik: str,
    company: str,
    form_type: str,
    filed: _date_cls,
    concept: str,
) -> CitedValue:
    unit, divisor = _UNIT_FOR_METRIC[fact.metric]
    if fact.currency != "USD":
        unit = unit.replace("USD", fact.currency)
    value = fact.value_cents / divisor if divisor else fact.value_cents
    source = "s1_pro_forma" if fact.is_pro_forma else "s1_snapshot"

    try:
        period_end = _date_cls.fromisoformat(fact.period_end)
    except ValueError:
        period_end = _date_cls(fact.fiscal_year, 12, 31)

    return CitedValue(
        value=value,
        unit=unit,
        metric=fact.metric,
        concept=concept,
        period_start=None,
        period_end=period_end,
        fiscal_year=fact.fiscal_year,
        fiscal_period="FY",
        form_type=form_type,
        filed=filed,
        accession=fact.accession,
        cik=cik,
        company=company,
        source=source,
        reporting_currency=fact.currency,
        is_pro_forma=fact.is_pro_forma,
        pro_forma_note=fact.pro_forma_note,
    )


def pick_snapshot_fact(
    facts: list[SnapshotFact],
    *,
    metric: str,
    period: str,
) -> SnapshotFact | None:
    candidates = [f for f in facts if f.metric == metric]
    if not candidates:
        return None

    if period == "pro-forma":
        pf = [f for f in candidates if f.is_pro_forma]
        if not pf:
            return None
        pf.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)
        return pf[0]

    audited = [f for f in candidates if f.is_audited and not f.is_pro_forma]
    if not audited:
        return None
    audited.sort(key=lambda f: (f.fiscal_year, f.period_end), reverse=True)

    if period in ("lfy", "mrp"):
        return audited[0]

    match_lfy_n = re.match(r"^lfy-(\d+)$", period)
    if match_lfy_n:
        offset = int(match_lfy_n.group(1))
        return audited[offset] if offset < len(audited) else None

    return None


def _resolve_concept_for_metric(metric: str) -> str:
    return _DEFAULT_CONCEPTS.get(metric, metric)


def snapshots_for_cik(cik: str, pack_root: Path) -> list[SnapshotFact]:
    pack_root = Path(pack_root)
    out: list[SnapshotFact] = []
    for manifest in pack_root.rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        filing = data.get("filing") or {}
        if str(filing.get("cik", "")) != cik:
            continue
        if not is_registration_form(str(filing.get("form_type", ""))):
            continue
        cache = manifest.parent / _CACHE_FILENAME
        if not cache.exists():
            continue
        try:
            result = SnapshotResult.from_json(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        out.extend(result.facts)
    return out


def _find_latest_registration_pack(cik: str, pack_root: Path) -> Path | None:
    """Return the newest-filing_date registration-class pack directory for a CIK."""
    candidates: list[tuple[str, Path]] = []
    for manifest in Path(pack_root).rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        filing = data.get("filing") or {}
        if str(filing.get("cik", "")) != cik:
            continue
        if not is_registration_form(str(filing.get("form_type", ""))):
            continue
        candidates.append((str(filing.get("filing_date", "")), manifest.parent))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


async def augment_with_s1_snapshot(
    *,
    result,  # QueryResult; kept as Any to avoid circular import pressure
    cik: str,
    metrics: list[str],
    period: str,
    pack_root: Path,
    company: str = "",
    form_type: str = "S-1",
    filed: _date_cls | None = None,
):
    """Fill result.metrics cells that are still None with S-1 snapshot rows.

    When no cached snapshots exist, lazily extract from the most recent
    registration-class pack for this CIK. If that extraction fails due to
    missing ANTHROPIC_API_KEY, inject placeholder CitedValue rows with
    source="no_api_key" so the CLI can surface a helpful hint.
    """
    facts = snapshots_for_cik(cik, pack_root=pack_root)

    if not facts:
        latest_pack = _find_latest_registration_pack(cik, pack_root)
        if latest_pack is not None:
            extract_result = await extract_or_load_snapshot(latest_pack)
            if extract_result.extraction_status == "no_api_key":
                for metric in metrics:
                    if result.metrics.get(metric) is None:
                        result.metrics[metric] = CitedValue(
                            value=None,
                            unit="USD",
                            metric=metric,
                            concept=_resolve_concept_for_metric(metric),
                            period_end=_date_cls.today(),
                            fiscal_year=0,
                            fiscal_period="FY",
                            form_type=form_type,
                            filed=_date_cls.today(),
                            accession="",
                            cik=cik,
                            company=company,
                            source="no_api_key",
                        )
                return result
            facts = extract_result.facts

    if not facts:
        return result

    if filed is None:
        filed = _date_cls.today()

    for metric in metrics:
        current = result.metrics.get(metric)
        if current is not None:
            continue
        fact = pick_snapshot_fact(facts, metric=metric, period=period)
        if fact is None:
            continue
        cv = snapshot_fact_to_cited_value(
            fact,
            cik=cik,
            company=company,
            form_type=form_type,
            filed=filed,
            concept=_resolve_concept_for_metric(metric),
        )
        result.metrics[metric] = cv
    return result
