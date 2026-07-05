"""LLM-backed extraction for the S-1 financial snapshot.

Prompt construction, the Haiku call (with env overrides and a single retry),
JSON parsing with truncation salvage, the declarative row-acceptance gate
(`LlmFactRow`), the cross-row magnitude sanity gates, and the
`extract_or_load_snapshot` orchestrator that merges deterministic table facts
with LLM enrichment and writes the disk cache.
"""

from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from . import table_parse
from .snapshot import (
    _CACHE_FILENAME,
    _RETRYABLE_STATUSES,
    METRIC_SLUGS,
    SCHEMA_VERSION,
    SnapshotFact,
    SnapshotResult,
    _read_manifest_accession,
    _retry_after_iso,
    _retry_cooldown_active,
    _utc_iso_now,
    _write_snapshot,
    source_sha256_for_pack,
)
from .table_parse import (
    _DETERMINISTIC_TABLE_MODEL,
    _SECTION_CAP_CHARS,
    _dedupe_deterministic_facts,
    _financial_section_texts,
    _supplement_cash_flow_facts_from_full_filing,
)

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
  "metric": "revenue" | "gross_profit" | "adjusted_gross_profit"
          | "operating_income_loss" | "net_income_loss"
          | "operating_cash_flow" | "capex" | "adjusted_ebitda" | "cash_and_equivalents"
          | "total_assets" | "stockholders_equity"
          | "shares_outstanding_basic" | "eps_basic",
  "value_cents": 78287000000,
  "currency": "USD",
  "is_audited": true,
  "is_pro_forma": false,
  "pro_forma_note": null,
  "source_text": "Total revenue ... $1,306,404 / $671,053 / $387,067"
}}

RULES:
- Values are integers in the reporting currency's smallest unit (cents for USD).
- Do NOT scale: if the filing says "78,287" and the preamble says "in thousands"
  then value_cents = 78,287 * 1000 * 100 = 7,828,700,000.
- Losses are negative integers (e.g. "Net loss (259,251)" with "in thousands"
  becomes value_cents = -25,925,100,000).
- Per-share figures: value_cents is cents per share. "$(1.08)" becomes -108.
- Capital expenditures should be stored as a positive cash outflow. If the filing
  prints purchases of property and equipment in parentheses, return the absolute
  value.
- For net_income_loss, use the consolidated row labeled "Net income (loss)" or
  "Net income". Do not use rows labeled "attributable to shareholders",
  "attributable to controlling interests", or "attributable to non-controlling
  interests" for this metric.
- Share counts: shares_outstanding_basic uses value_cents for the count itself
  (scaled by 100). "240,123,456" shares becomes value_cents = 24,012,345,600.
- Pro-forma rows MUST set is_pro_forma=true and record the assumption verbatim
  in pro_forma_note. Historical audited rows set is_pro_forma=false.
- period_end must be ISO YYYY-MM-DD.
- fiscal_period should be "FY" for annual rows and "Q1" / "Q2" / "Q3" for interim rows.
- source_text should be the shortest verbatim row or sentence that contains the value.
- Every object must include source_text. If you cannot identify the source row or sentence,
  skip the fact.
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


# ISO-4217 codes we accept from either extractor. Kept small on purpose: an
# unrecognized code is treated as an extraction error, not passed through.
_ACCEPTED_CURRENCIES: frozenset[str] = frozenset(
    {"USD", "EUR", "GBP", "JPY", "CNY", "HKD", "SEK", "CHF", "CAD", "AUD", "SGD"}
)


def _llm_row_has_period_context(row: dict[str, object]) -> bool:
    fiscal_period = str(row.get("fiscal_period") or "FY").upper()
    period_end = str(row.get("period_end") or "")
    source_text = str(row.get("source_text") or "").lower()
    if fiscal_period != "FY":
        return True
    if period_end.endswith("-12-31"):
        return True
    annual_markers = ("year ended", "fiscal year", "annual")
    return any(marker in source_text for marker in annual_markers)


def _llm_row_has_metric_context(row: dict[str, object]) -> bool:
    metric = str(row.get("metric") or "")
    source_text = str(row.get("source_text") or "").lower()
    if metric == "net_income_loss" and "attributable to" in source_text:
        return False
    return True


# Keys the LLM row must carry before any coercion; a row missing any of these
# is dropped. Optional keys (fiscal_period, pro_forma_note, section_id,
# chunk_id) fall back to their defaults.
_LLM_ROW_REQUIRED_KEYS = (
    "fiscal_year",
    "period_end",
    "metric",
    "value_cents",
    "currency",
    "is_audited",
    "is_pro_forma",
    "source_text",
)


class LlmFactRow(BaseModel):
    """Declarative acceptance gate for one LLM-returned fact row.

    Validators encode exactly the semantics of the former hand-rolled gate:
    required keys, metric-slug membership, the period-context and
    metric-context gates, the ISO currency check, and the `int()`/`bool()`
    coercion (bool coerces to 0/1 the same way `int(True)` does). A row that
    fails any check raises ValidationError and is dropped by the caller.
    """

    model_config = ConfigDict(extra="ignore")

    fiscal_year: int
    period_end: str
    metric: str
    value_cents: int
    currency: str
    is_audited: bool
    is_pro_forma: bool
    source_text: str | None
    pro_forma_note: str | None = None
    fiscal_period: str = "FY"
    section_id: str | None = None
    chunk_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _check_required_and_context(cls, data: object) -> object:
        if not isinstance(data, dict):
            raise ValueError("row is not an object")
        if any(key not in data for key in _LLM_ROW_REQUIRED_KEYS):
            raise ValueError("row is missing a required key")
        if data.get("metric") not in METRIC_SLUGS:
            raise ValueError("metric is not a known slug")
        if not _llm_row_has_period_context(data):
            raise ValueError("row lacks annual period context")
        if not _llm_row_has_metric_context(data):
            raise ValueError("row fails metric context gate")
        currency = str(data.get("currency") or "").strip().upper()
        if currency not in _ACCEPTED_CURRENCIES:
            raise ValueError("currency is not an accepted ISO code")
        normalized = dict(data)
        normalized["currency"] = currency
        return normalized

    @field_validator("fiscal_year", "value_cents", mode="before")
    @classmethod
    def _coerce_int(cls, value: object) -> int:
        try:
            return int(value)  # type: ignore[call-overload, no-any-return]
        except (ValueError, TypeError) as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("is_audited", "is_pro_forma", mode="before")
    @classmethod
    def _coerce_bool(cls, value: object) -> bool:
        return bool(value)

    @field_validator("period_end", "metric", mode="before")
    @classmethod
    def _coerce_str(cls, value: object) -> str:
        return str(value)

    @field_validator("fiscal_period", mode="before")
    @classmethod
    def _coerce_fiscal_period(cls, value: object) -> str:
        return str(value or "FY")

    @field_validator("source_text", "section_id", "chunk_id", mode="before")
    @classmethod
    def _coerce_optional_stripped(cls, value: object) -> str | None:
        return str(value).strip() if value is not None else None

    @field_validator("pro_forma_note", mode="before")
    @classmethod
    def _coerce_pro_forma_note(cls, value: object) -> str | None:
        return str(value) if value is not None else None

    def to_snapshot_fact(self, accession: str) -> SnapshotFact:
        return SnapshotFact(
            accession=accession,
            fiscal_year=self.fiscal_year,
            period_end=self.period_end,
            metric=self.metric,
            value_cents=self.value_cents,
            currency=self.currency,
            is_audited=self.is_audited,
            is_pro_forma=self.is_pro_forma,
            pro_forma_note=self.pro_forma_note,
            fiscal_period=self.fiscal_period,
            source_text=self.source_text,
            section_id=self.section_id,
            chunk_id=self.chunk_id,
        )


MODEL_ID = "claude-haiku-4-5-20251001"
_MAX_OUTPUT_TOKENS = 8000
_RETRY_BACKOFF_SECONDS = 2.0


class MissingAnthropicKeyError(RuntimeError):
    """Raised when the anthropic package or ANTHROPIC_API_KEY is unavailable.

    Distinct from a runtime API failure so the caller can map it to the
    non-retryable `no_api_key` status instead of `llm_call_failed`.
    """


def _s1_model_id() -> str:
    return os.environ.get("EDGARPACK_S1_MODEL") or MODEL_ID


def _s1_max_output_tokens() -> int:
    raw = os.environ.get("EDGARPACK_S1_MAX_TOKENS")
    if not raw:
        return _MAX_OUTPUT_TOKENS
    try:
        return int(raw)
    except ValueError:
        return _MAX_OUTPUT_TOKENS


async def _call_haiku_extract(section_text: str) -> str:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise MissingAnthropicKeyError(
            "S-1 financial extraction requires the `anthropic` package. "
            "Install with `pip install edgarpack[llm]` and export "
            "ANTHROPIC_API_KEY."
        ) from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingAnthropicKeyError(
            "S-1 financial extraction requires ANTHROPIC_API_KEY. Export it and retry."
        )

    client = AsyncAnthropic()
    prompt = build_extraction_prompt(section_text)
    last_exc: Exception | None = None
    # One retry with a short backoff on a transient API failure before the
    # caller surfaces llm_call_failed.
    for attempt in range(2):
        try:
            message = await client.messages.create(
                model=_s1_model_id(),
                max_tokens=_s1_max_output_tokens(),
                system=PROMPT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 (surfaced as llm_call_failed detail)
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise
        text_blocks = [
            str(getattr(block, "text", ""))
            for block in message.content
            if getattr(block, "type", "") == "text"
        ]
        return "".join(text_blocks).strip()
    raise last_exc if last_exc is not None else RuntimeError("extraction failed")


def parse_llm_response(raw: str, *, accession: str) -> list[SnapshotFact]:
    """Parse the model's JSON response into SnapshotFact objects.

    Drops any row rejected by the `LlmFactRow` gate (missing required keys,
    unknown metric, failed period/metric context, or unaccepted currency).
    Raises ValueError for unparseable output so callers can mark the
    extraction as failed and cache accordingly.
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
        try:
            model = LlmFactRow.model_validate(row)
        except ValidationError:
            continue
        facts.append(model.to_snapshot_fact(accession))
    return facts


def _truncate_to_last_complete_object(raw: str) -> str | None:
    """Trim a truncated JSON array to its last complete object.

    Returns a parseable `[...]` string ending at the last `}` that closes a
    top-level array element, or None when no complete object is present.
    """
    text = _strip_code_fences(raw)
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    last_object_end = -1
    for index in range(start + 1, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                last_object_end = index
    if last_object_end == -1:
        return None
    return text[start : last_object_end + 1] + "]"


def parse_llm_response_with_salvage(raw: str, *, accession: str) -> tuple[list[SnapshotFact], bool]:
    """Parse the model response, salvaging a truncated JSON array if needed.

    Returns (facts, truncated). On a clean parse `truncated` is False. When the
    array is truncated mid-stream, trims to the last complete object and parses
    that; a salvage that yields at least one valid row returns truncated=True.
    Re-raises ValueError when nothing parseable can be recovered.
    """
    try:
        return parse_llm_response(raw, accession=accession), False
    except ValueError:
        salvaged = _truncate_to_last_complete_object(raw)
        if salvaged is None:
            raise
        facts = parse_llm_response(salvaged, accession=accession)
        if not facts:
            raise
        return facts, True


# Metrics whose values must be non-negative; a negative here is an extraction
# slip, not a real figure.
_NON_NEGATIVE_METRICS: frozenset[str] = frozenset({"revenue", "total_assets"})
_ADJACENT_RATIO_CAP = Decimal(500)


def _facts_by_period(facts: list[SnapshotFact]) -> dict[tuple[str, int, str], int]:
    return {(f.metric, f.fiscal_year, f.period_end): f.value_cents for f in facts}


def _gate_llm_facts(
    llm_facts: list[SnapshotFact],
    trusted_facts: list[SnapshotFact],
) -> tuple[list[SnapshotFact], list[str]]:
    """Drop implausible LLM rows so an arithmetic slip never becomes a citation.

    Gates: revenue / total_assets must be non-negative; within one period
    revenue >= gross_profit and total_assets >= cash_and_equivalents; an
    adjacent-year same-metric ratio outside [1/500, 500] rejects the newer row.
    Rejected rows are returned as human-readable reasons, never emitted.
    """
    kept: list[SnapshotFact] = []
    rejections: list[str] = []

    def lookup(metric: str, fy: int, end: str) -> int | None:
        for fact in [*trusted_facts, *kept]:
            if fact.metric == metric and fact.fiscal_year == fy and fact.period_end == end:
                return fact.value_cents
        return None

    def adjacent(metric: str, fy: int, period: str) -> int | None:
        for fact in [*trusted_facts, *kept]:
            if (
                fact.metric == metric
                and fact.fiscal_year == fy - 1
                and (fact.fiscal_period or "FY") == period
            ):
                return fact.value_cents
        return None

    for fact in llm_facts:
        reason: str | None = None
        value = fact.value_cents
        if fact.metric in _NON_NEGATIVE_METRICS and value < 0:
            reason = "negative value"
        elif fact.metric == "gross_profit":
            revenue = lookup("revenue", fact.fiscal_year, fact.period_end)
            if revenue is not None and value > revenue:
                reason = "gross_profit exceeds revenue"
        elif fact.metric == "cash_and_equivalents":
            total_assets = lookup("total_assets", fact.fiscal_year, fact.period_end)
            if total_assets is not None and value > total_assets:
                reason = "cash exceeds total_assets"

        if reason is None:
            prior = adjacent(fact.metric, fact.fiscal_year, fact.fiscal_period or "FY")
            if prior is not None and prior != 0 and value != 0:
                ratio = abs(Decimal(value) / Decimal(prior))
                if ratio > _ADJACENT_RATIO_CAP or ratio < (1 / _ADJACENT_RATIO_CAP):
                    reason = "implausible year-over-year change"

        if reason is not None:
            rejections.append(
                f"{fact.metric} {fact.fiscal_year}: dropped implausible row ({reason})"
            )
            continue
        kept.append(fact)

    return kept, rejections


async def _retry_truncated_snapshot(
    *,
    pack_dir: Path,
    cache_path: Path,
    accession: str,
    source_hash: str,
    cached: SnapshotResult,
) -> SnapshotResult:
    """Re-extract the metric slugs a truncation-salvaged snapshot never reached.

    Existing cached facts always win (only slugs still missing from `cached`
    are asked for). A response that parses cleanly (no truncation this time)
    clears the truncated marker and caches permanently, even when some slugs
    stay unresolved: at that point they are genuinely absent from the filing,
    not lost to truncation. Another truncated response keeps the cooldown
    alive so a later read tries again.
    """
    existing_facts = list(cached.facts)
    missing_slugs = METRIC_SLUGS - {fact.metric for fact in existing_facts}
    if not missing_slugs:
        return cached

    markdown = ""
    md_path = pack_dir / "filing.full.md"
    if md_path.exists():
        markdown = md_path.read_text(encoding="utf-8", errors="replace")
    financial_sections = _financial_section_texts(pack_dir, markdown)
    if not financial_sections:
        return cached

    def _finalize(
        *, facts: list[SnapshotFact], model: str, truncated: bool, gate_rejections: list[str]
    ) -> SnapshotResult:
        still_missing = bool(METRIC_SLUGS - {fact.metric for fact in facts})
        retry_after = _retry_after_iso() if truncated and still_missing else None
        return _write_snapshot(
            cache_path,
            SnapshotResult(
                schema_version=SCHEMA_VERSION,
                accession=accession,
                extracted_at=_utc_iso_now(),
                extraction_status="ok",
                source_sha256=source_hash,
                model=model,
                facts=facts,
                detail=None,
                retry_after=retry_after,
                truncated=truncated,
                gate_rejections=gate_rejections,
            ),
        )

    try:
        raw = await _call_haiku_extract("\n\n".join(financial_sections)[:_SECTION_CAP_CHARS])
    except MissingAnthropicKeyError:
        # Never cached, same as the initial extraction: the very next read
        # tries again, so adding a key re-attempts immediately.
        return cached
    except Exception:  # noqa: BLE001 (keep the partial snapshot, refresh cooldown)
        return _finalize(
            facts=existing_facts,
            model=cached.model,
            truncated=True,
            gate_rejections=cached.gate_rejections,
        )

    try:
        parsed, still_truncated = parse_llm_response_with_salvage(raw, accession=accession)
    except ValueError:
        return _finalize(
            facts=existing_facts,
            model=cached.model,
            truncated=True,
            gate_rejections=cached.gate_rejections,
        )

    kept, new_rejections = _gate_llm_facts(parsed, existing_facts)
    new_facts = [fact for fact in kept if fact.metric in missing_slugs]
    gate_rejections = [*cached.gate_rejections, *new_rejections]
    if not new_facts:
        return _finalize(
            facts=existing_facts,
            model=cached.model,
            truncated=still_truncated,
            gate_rejections=gate_rejections,
        )

    model = cached.model
    if _s1_model_id() not in model.split("+"):
        model = f"{model}+{_s1_model_id()}" if model else _s1_model_id()
    return _finalize(
        facts=[*existing_facts, *new_facts],
        model=model,
        truncated=still_truncated,
        gate_rejections=gate_rejections,
    )


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
            # A truncation-salvaged ok snapshot that still has missing slugs
            # carries its own retry_after (set below); treat it like a
            # retryable failure instead of caching the gap forever.
            truncated_with_gap = (
                cached.extraction_status == "ok"
                and cached.truncated
                and cached.retry_after is not None
            )
            if truncated_with_gap:
                if _retry_cooldown_active(cached.retry_after):
                    return cached
                return await _retry_truncated_snapshot(
                    pack_dir=pack_dir,
                    cache_path=cache_path,
                    accession=accession,
                    source_hash=source_hash,
                    cached=cached,
                )
            if cached.extraction_status not in _RETRYABLE_STATUSES:
                return cached
            # A retryable failure is served only inside its cooldown window;
            # past it, fall through and re-attempt extraction.
            if _retry_cooldown_active(cached.retry_after):
                return cached

    def _finalize(
        *,
        status: str,
        facts: list[SnapshotFact],
        model: str,
        detail: str | None = None,
        truncated: bool = False,
        gate_rejections: list[str] | None = None,
    ) -> SnapshotResult:
        retryable = status in _RETRYABLE_STATUSES
        if status == "ok" and truncated and (METRIC_SLUGS - {fact.metric for fact in facts}):
            # Truncation salvage that still leaves slugs missing did not
            # really finish the extraction; give it the same cooldown as a
            # retryable failure so a later read fills the gap.
            retryable = True
        retry_after = _retry_after_iso() if retryable else None
        return _write_snapshot(
            cache_path,
            SnapshotResult(
                schema_version=SCHEMA_VERSION,
                accession=accession,
                extracted_at=_utc_iso_now(),
                extraction_status=status,
                source_sha256=source_hash,
                model=model,
                facts=facts,
                detail=detail,
                retry_after=retry_after,
                truncated=truncated,
                gate_rejections=gate_rejections or [],
            ),
        )

    markdown = ""
    md_path = pack_dir / "filing.full.md"
    if md_path.exists():
        markdown = md_path.read_text(encoding="utf-8", errors="replace")

    financial_sections = _financial_section_texts(pack_dir, markdown)
    if not financial_sections:
        return _finalize(status="no_financial_data_found", facts=[], model=_s1_model_id())

    deterministic_facts: list[SnapshotFact] = []
    for section in financial_sections:
        deterministic_facts.extend(
            table_parse._extract_summary_table_facts(section, accession=accession)
        )
    deterministic_facts = _dedupe_deterministic_facts(deterministic_facts)
    deterministic_facts = _supplement_cash_flow_facts_from_full_filing(
        deterministic_facts,
        full_text=markdown,
        accession=accession,
    )

    covered_slugs = {fact.metric for fact in deterministic_facts}
    missing_slugs = METRIC_SLUGS - covered_slugs

    # Deterministic facts win per-slug; the LLM is invoked only to fill slugs
    # the deterministic label map cannot see (e.g. balance-sheet metrics).
    if not missing_slugs:
        return _finalize(
            status="ok",
            facts=deterministic_facts,
            model=_DETERMINISTIC_TABLE_MODEL,
        )

    llm_status: str | None = None
    detail: str | None = None
    truncated = False
    llm_facts: list[SnapshotFact] = []
    gate_rejections: list[str] = []
    try:
        raw = await _call_haiku_extract("\n\n".join(financial_sections)[:_SECTION_CAP_CHARS])
    except MissingAnthropicKeyError:
        llm_status = "no_api_key"
    except Exception as exc:  # noqa: BLE001 (surfaced as llm_call_failed detail)
        llm_status = "llm_call_failed"
        detail = str(exc)
    else:
        try:
            parsed, truncated = parse_llm_response_with_salvage(raw, accession=accession)
        except ValueError:
            llm_status = "llm_parse_failed"
        else:
            kept, gate_rejections = _gate_llm_facts(parsed, deterministic_facts)
            llm_facts = [fact for fact in kept if fact.metric in missing_slugs]

    if llm_status is not None:
        # The LLM enrichment failed. Keep the deterministic facts (if any) but
        # carry the failure status so the missing slugs are re-attempted later.
        model = _DETERMINISTIC_TABLE_MODEL if deterministic_facts else _s1_model_id()
        return _finalize(
            status=llm_status,
            facts=deterministic_facts,
            model=model,
            detail=detail,
        )

    merged_facts = [*deterministic_facts, *llm_facts]
    if not merged_facts:
        # An empty or fully-gated LLM array with no deterministic facts is
        # indistinguishable from a bad extraction; treat it as retryable
        # rather than caching a permanent ok with zero facts.
        return _finalize(
            status="no_financial_data_found",
            facts=[],
            model=_s1_model_id(),
            gate_rejections=gate_rejections,
        )
    model_parts: list[str] = []
    if deterministic_facts:
        model_parts.append(_DETERMINISTIC_TABLE_MODEL)
    if llm_facts:
        model_parts.append(_s1_model_id())
    model = "+".join(model_parts) if model_parts else _s1_model_id()
    return _finalize(
        status="ok",
        facts=merged_facts,
        model=model,
        truncated=truncated,
        gate_rejections=gate_rejections,
    )
