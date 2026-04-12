"""Layer B of the self-heal stack: extract industry KPIs from pack prose.

Layer A (self_heal.py) handles GAAP concept drift within XBRL. Layer B
handles metrics that exist only in management prose and segment tables:
ARR, NRR, RPO, DAU, GMV, same-store sales, and so on.

See docs/superpowers/specs/2026-04-11-self-heal-v2-layer-b-design.md for
the full design rationale.

Entry point: try_extract_kpi(metric, cik, company, period, ...).

Resolution order inside this module:
    1. KPI_CATALOG lookup (fail fast if metric isn't a known KPI)
    2. _resolve_filing_for_period: find the pack that represents the period
    3. _select_sections: read manifest, filter to MD&A + key-metrics
    4. _read_section_text: concat markdown from disk
    5. _trim_to_budget: stay under the LLM token budget
    6. _build_extraction_prompt: tight prompt with KPI phrases + text
    7. _extract_via_llm: subprocess to codex/claude, parse JSON
    8. _verify_excerpt_in_text: anti-hallucination substring check
    9. _build_cited_from_extraction: CitedValue with excerpt_text and badge
    10. _verify_against_prior_filing: recursive order-of-magnitude check
    11. Persist to learned_concepts with accession key
"""

from __future__ import annotations

import json
import logging
import math
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path

from ..harvest.registry import PackRecord, PackRegistry
from .learned_registry import LearnedRegistry
from .models import CitedValue


@dataclass(frozen=True)
class KpiDef:
    """Metadata about a hand-curated KPI the extractor knows how to look for.

    phrases: the forms the LLM should search for in prose. Multiple forms
        are useful because companies use different phrasings (e.g. 'ARR' in
        one filing and 'annual recurring revenue' in another).
    unit_hint: the expected unit type. The LLM is told this so it can
        normalize or reject mismatched units.
    industry: SIC prefix tuple. Empty tuple means 'all industries'. Not
        used by the v2 selector but recorded for a future industry-aware
        suggester.
    description: human-readable description for `edgarpack learned show`.
    """

    phrases: tuple[str, ...]
    unit_hint: str
    industry: tuple[str, ...] = field(default=())
    description: str = ""


def _parse_filing_date_safe(filing_date: str | None) -> tuple[int, _date]:
    """Parse a pack filing_date into (fiscal_year, filed_date), degrading
    gracefully on malformed input.

    Returns (0, _date.min) if filing_date is None, empty, or unparseable.
    """
    if not filing_date:
        return 0, _date.min
    try:
        filed = _date.fromisoformat(filing_date)
        return filed.year, filed
    except ValueError:
        return 0, _date.min


def _load_pack_manifest(pack_dir: Path) -> dict:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No manifest.json at {manifest_path}. Pack may be incomplete."
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


_PERIOD_TO_FORM: dict[str, str] = {
    "lfy": "10-K",
    "mrq": "10-Q",
}


def _resolve_filing_for_period(
    cik: str,
    period: str,
    registry: PackRegistry,
) -> PackRecord | None:
    """Given a period selector, find the pack that represents it.

    Period semantics:
      lfy              -> most recent 10-K
      mrq              -> most recent 10-Q
      mrp / ltm        -> most recent 10-K OR 10-Q by filing_date
      annual:N         -> Nth most recent 10-K (N is 1-indexed)
      quarterly:N      -> Nth most recent 10-Q (N is 1-indexed)

    Returns None if the required pack does not exist in the registry.
    """
    p = period.strip().lower()

    if p in ("lfy", "mrq"):
        form = _PERIOD_TO_FORM[p]
        packs = registry.list_packs(cik=cik, form_type=form, limit=5)
        return packs[0] if packs else None

    if p in ("mrp", "ltm"):
        tens_k = registry.list_packs(cik=cik, form_type="10-K", limit=5)
        tens_q = registry.list_packs(cik=cik, form_type="10-Q", limit=5)
        merged = sorted(
            tens_k + tens_q,
            key=lambda r: r.filing_date,
            reverse=True,
        )
        return merged[0] if merged else None

    if p.startswith("annual:"):
        try:
            n = int(p.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
        if n < 1:
            return None
        packs = registry.list_packs(cik=cik, form_type="10-K", limit=max(5, n))
        if len(packs) < n:
            return None
        return packs[n - 1]

    if p.startswith("quarterly:"):
        try:
            n = int(p.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
        if n < 1:
            return None
        packs = registry.list_packs(cik=cik, form_type="10-Q", limit=max(5, n))
        if len(packs) < n:
            return None
        return packs[n - 1]

    return None


KPI_CATALOG: dict[str, KpiDef] = {
    # SaaS / subscription
    "arr": KpiDef(
        phrases=("annual recurring revenue", "ARR", "ending ARR",
                 "ARR of approximately"),
        unit_hint="USD",
        description="Annualized subscription revenue at period end.",
    ),
    "nrr": KpiDef(
        phrases=("net revenue retention", "dollar-based net retention",
                 "net dollar retention", "NRR", "NDR"),
        unit_hint="percent",
        description="Cohort-based revenue retention, typically >100% for healthy SaaS.",
    ),
    "grr": KpiDef(
        phrases=("gross revenue retention", "GRR", "gross dollar retention"),
        unit_hint="percent",
    ),
    "rpo": KpiDef(
        phrases=("remaining performance obligations", "RPO"),
        unit_hint="USD",
    ),
    "crpo": KpiDef(
        phrases=("current remaining performance obligations", "cRPO",
                 "current RPO"),
        unit_hint="USD",
    ),
    "billings": KpiDef(
        phrases=("calculated billings", "total billings", "non-GAAP billings"),
        unit_hint="USD",
    ),
    "subscription_rev": KpiDef(
        phrases=("subscription revenue",),
        unit_hint="USD",
    ),
    "customer_count": KpiDef(
        phrases=("total customers", "number of customers",
                 "customers with ARR over"),
        unit_hint="count",
    ),
    # Consumer / internet
    "dau": KpiDef(
        phrases=("daily active users", "DAU"),
        unit_hint="count",
    ),
    "mau": KpiDef(
        phrases=("monthly active users", "MAU"),
        unit_hint="count",
    ),
    "qau": KpiDef(
        phrases=("quarterly active users", "QAU"),
        unit_hint="count",
    ),
    "arpu": KpiDef(
        phrases=("average revenue per user", "ARPU"),
        unit_hint="USD",
    ),
    "arppu": KpiDef(
        phrases=("average revenue per paying user", "ARPPU"),
        unit_hint="USD",
    ),
    "paying_users": KpiDef(
        phrases=("paying users", "paid users", "paying subscribers"),
        unit_hint="count",
    ),

    # Marketplace / platform
    "gmv": KpiDef(
        phrases=("gross merchandise volume", "GMV", "gross transaction value",
                 "gross booking value"),
        unit_hint="USD",
    ),
    "gross_bookings": KpiDef(
        phrases=("gross bookings",),
        unit_hint="USD",
    ),
    "take_rate": KpiDef(
        phrases=("take rate", "net take rate", "effective take rate"),
        unit_hint="percent",
    ),
    "transactions": KpiDef(
        phrases=("number of transactions", "total transactions",
                 "transactions processed"),
        unit_hint="count",
    ),

    # Retail / consumer goods
    "same_store_sales": KpiDef(
        phrases=("same-store sales", "comparable store sales",
                 "comparable sales"),
        unit_hint="percent",
    ),
    "store_count": KpiDef(
        phrases=("number of stores", "total stores", "store count"),
        unit_hint="count",
    ),
    "avg_ticket": KpiDef(
        phrases=("average ticket", "average transaction value", "average check"),
        unit_hint="USD",
    ),

    # Fintech / payments
    "tpv": KpiDef(
        phrases=("total payment volume", "TPV", "payment volume"),
        unit_hint="USD",
    ),
    "active_accounts": KpiDef(
        phrases=("active accounts", "active customer accounts"),
        unit_hint="count",
    ),
    "aum": KpiDef(
        phrases=("assets under management", "AUM"),
        unit_hint="USD",
    ),
    "aua": KpiDef(
        phrases=("assets under administration", "AUA"),
        unit_hint="USD",
    ),
}

logger = logging.getLogger(__name__)

_VALID_LLM_UNITS: frozenset[str] = frozenset({"USD", "count", "percent", "days", "pure"})

_SECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # MD&A is Part II Item 7 in a 10-K. The section_id function produces
    # "10k_partii_item7_..." (lowercase roman "ii" for Part II). Match
    # both "parti_" and "partii_" so we also catch any Part I Item 7 edge
    # case from unusual filers.
    re.compile(r"^10k_parti+_item7(?=_|$)"),   # MD&A (10-K, Part I or II)
    re.compile(r"^10k_parti+_item7a(?=_|$)"),  # Quant/Qual market risk
    re.compile(r"^10q_parti+_item2(?=_|$)"),   # MD&A (10-Q, Part I)
    # Unanchored: slug patterns fire anywhere in the section ID.
    # A segment overview nested inside Item 1 Business is a valid target.
    re.compile(r"_segment"),
    re.compile(r"_key_metric"),
    re.compile(r"_operating_data"),
    re.compile(r"_key_performance"),
)


def _select_sections(sections: list[dict]) -> list[dict]:
    """Return manifest section entries whose IDs match MD&A / key-metrics patterns.

    Preserves manifest order. Empty list if none match. The caller handles
    the 'malformed pack' case.
    """
    result: list[dict] = []
    for sec in sections:
        sec_id = str(sec.get("id", ""))
        if any(pat.search(sec_id) for pat in _SECTION_PATTERNS):
            result.append(sec)
    return result


_SECTION_SEPARATOR = "\n\n--- [{id}] ---\n\n"


def _read_section_text(pack_dir: Path, sections: list[dict]) -> str:
    """Concatenate section markdown from disk in manifest order.

    Missing files are skipped with a warning log; the function never raises.
    Returns an empty string if none of the requested sections exist.
    """
    parts: list[str] = []
    for sec in sections:
        sec_id = str(sec.get("id", ""))
        rel_path = sec.get("path", "")
        if not rel_path:
            continue
        section_file = pack_dir / rel_path
        if not section_file.exists():
            logger.warning(
                "Section file missing: %s (pack=%s)", section_file, pack_dir
            )
            continue
        try:
            content = section_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", section_file, e)
            continue
        parts.append(_SECTION_SEPARATOR.format(id=sec_id))
        parts.append(content)
    return "".join(parts)


_DEFAULT_MAX_CHARS = 60_000


def _trim_to_budget(text: str, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """Trim text to stay under a character budget (rough token proxy).

    Uses a 4 chars/token heuristic: 60K chars ~= 15K tokens. Truncates
    mid-section with a clear '[truncated]' marker so the LLM knows the
    text has a boundary.
    """
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 100]
    return f"{head}\n\n[truncated at {max_chars} chars]"


# Module-level LLM backend detection for Layer B. Separate from Layer A's
# _LLM_CMD so tests can patch each independently.
_LLM_CMD_KPI: str | None = None
for _candidate in ("codex", "claude"):
    if shutil.which(_candidate):
        _LLM_CMD_KPI = _candidate
        break


def _llm_backend_available_kpi() -> bool:
    return _LLM_CMD_KPI is not None


_LLM_TIMEOUT_SECONDS_KPI = 45


def _build_extraction_prompt(
    metric: str,
    kpi_def: KpiDef,
    company: str,
    form_type: str,
    filing_date: str,
    text: str,
) -> str:
    phrases = ", ".join(f'"{p}"' for p in kpi_def.phrases)
    return (
        "You are extracting a reported KPI from SEC filing prose. Be "
        "conservative. Reject ambiguous cases. Never infer or compute; "
        "only extract values that are stated literally.\n\n"
        f"Company: {company}\n"
        f"Filing: {form_type} filed {filing_date}\n"
        f"Metric: {metric}\n"
        f"Metric phrases to search for: {phrases}\n"
        f"Unit hint: {kpi_def.unit_hint}\n\n"
        "Rules:\n"
        "1. Search only the text below. Never use outside knowledge.\n"
        "2. Only return a value if the text states it in unambiguous prose "
        "or a labeled table row. Forward-looking targets, ranges, and "
        "competitor figures do not count.\n"
        f"3. The value's unit must match the hint ({kpi_def.unit_hint}). "
        "Return the number in base units: for USD, raw dollars (not "
        "millions or billions; $3.44 billion -> 3440000000). For count, "
        "individual units (not thousands; 50,000 users -> 50000). For "
        "percent, a whole percentage point (95% NRR -> 95.0, not 0.95). "
        "If the text reports a different unit that cannot be normalized, "
        "return not_found.\n"
        "4. The excerpt must be a verbatim substring of the text. "
        "No paraphrasing.\n"
        "5. If multiple candidate values exist (e.g. historical AND current), "
        "return the most recent as-of the filing date.\n"
        "6. If you cannot find the value with high confidence, return "
        '{"confidence": "not_found", ...} or {"confidence": "ambiguous", ...}.\n\n'
        "Respond with strict JSON, no prose, no markdown fences:\n"
        "  {\n"
        '    "value": <number or null>,\n'
        '    "unit": "USD" | "count" | "percent" | "days" | "pure" | null,\n'
        '    "excerpt": "<verbatim substring of the text>",\n'
        '    "section_id": "<the section ID the excerpt came from>",\n'
        '    "confidence": "high" | "medium" | "low" | "not_found" | "ambiguous"\n'
        "  }\n\n"
        "TEXT:\n"
        f"{text}\n"
    )


def _extract_via_llm(prompt: str) -> dict | None:
    if _LLM_CMD_KPI is None:
        return None

    try:
        completed = subprocess.run(
            [_LLM_CMD_KPI, "exec", "--prompt", prompt],
            capture_output=True,
            text=True,
            timeout=_LLM_TIMEOUT_SECONDS_KPI,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("KPI LLM extract failed: %s", e)
        return None

    if completed.returncode != 0:
        logger.warning(
            "KPI LLM extract returned non-zero: %s",
            (completed.stderr or "")[:200],
        )
        return None

    raw = (completed.stdout or "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict):
        return None

    confidence = parsed.get("confidence")
    if confidence not in ("high", "medium", "low", "not_found", "ambiguous"):
        return None

    # Low-confidence responses pass through for the caller to use as diagnostics.
    if confidence in ("not_found", "ambiguous", "low"):
        return parsed

    # High/medium confidence: require value/unit/excerpt/section_id.
    value = parsed.get("value")
    unit = parsed.get("unit")
    excerpt = parsed.get("excerpt")
    section_id = parsed.get("section_id")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value < 0:
        return None
    if not isinstance(unit, str) or unit not in _VALID_LLM_UNITS:
        return None
    if not isinstance(excerpt, str) or not excerpt.strip():
        return None
    if not isinstance(section_id, str) or not section_id.strip():
        return None

    return parsed


_WS_RUN = re.compile(r"\s+")
# Zero-width, directional, and BOM code points that confuse substring matches.
# EDGAR packs run through HTML/PDF pipelines that inject these into
# filing prose. Stripping them before comparison makes the firewall robust
# against "$3.44\u200Bbillion" vs "$3.44 billion" false negatives.
_ZERO_WIDTH = re.compile(r"[\u200B-\u200F\u202A-\u202E\uFEFF]")


def _normalize_for_match(text: str) -> str:
    """Normalize a string for substring matching in the hallucination firewall.

    NFKC + zero-width replace-with-space + whitespace collapse + casefold.

    Zero-width characters are replaced with a space (not stripped to empty)
    because in EDGAR prose they function as word separators injected by
    HTML/PDF pipelines (e.g. "$3.44\\u200Bbillion" should compare equal to
    "$3.44 billion"). The subsequent _WS_RUN collapse handles any resulting
    double spaces.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub(" ", text)
    text = _WS_RUN.sub(" ", text).strip()
    return text.casefold()


def _verify_excerpt_in_text(
    excerpt: str,
    source_text: str,
    expected_value: str | None = None,
) -> bool:
    """True when ``excerpt`` is a substring of ``source_text`` (and when
    ``expected_value`` is set, also true that it appears inside the excerpt).

    Normalization, in order:
      1. Unicode NFKC (collapses full-width digits, precomposes diacritics).
      2. Strip zero-width marks and BOMs (EDGAR pipelines often inject these).
      3. Collapse whitespace runs to single spaces.
      4. Strip leading/trailing whitespace.
      5. Casefold (handles German ß, Turkish dotless i, etc.).

    Empty excerpt, empty source, or an excerpt that normalizes to empty
    returns False. If ``expected_value`` is set, it must appear (under the
    same normalization) inside the normalized excerpt, not just the source.

    This is the hallucination firewall for Layer B. Two guarantees:
      - The excerpt came from the source document (excerpt in source).
      - The value was attributed to that quote (value in excerpt), not
        pulled from elsewhere in the document.
    """
    if not excerpt or not source_text:
        return False

    norm_excerpt = _normalize_for_match(excerpt)
    norm_source = _normalize_for_match(source_text)
    if not norm_excerpt:
        return False

    if norm_excerpt not in norm_source:
        return False

    if expected_value is not None:
        norm_value = _normalize_for_match(expected_value)
        if not norm_value:
            return False
        if norm_value not in norm_excerpt:
            return False

    return True


def _build_cited_from_extraction(
    response: dict,
    metric: str,
    kpi_def: KpiDef,
    pack_record: PackRecord,
    pack_manifest: dict,
    primary_document: str,
) -> CitedValue:
    filing = pack_manifest.get("filing", {})

    filing_date_str = str(filing.get("filing_date", pack_record.filing_date))
    try:
        filed = _date.fromisoformat(filing_date_str)
    except ValueError:
        filed = _date.min

    fiscal_year = filed.year if filed != _date.min else 0
    # Layer B v2 only extracts from 10-Ks in practice, but guard against
    # the non-10-K case with an empty string sentinel rather than an
    # invalid "Q" placeholder (spec expects FY/Q1/Q2/Q3/Q4).
    fiscal_period = "FY" if pack_record.form_type.startswith("10-K") else ""

    concept = kpi_def.phrases[0] if kpi_def.phrases else metric

    return CitedValue(
        value=response["value"],
        unit=str(response.get("unit") or kpi_def.unit_hint),
        metric=metric,
        concept=concept,
        # Sentinel: pack manifest doesn't carry period_of_report in v2, so we
        # can't reliably set period_end. Using date.min marks it as "unknown"
        # for downstream consumers rather than silently using the filing date
        # (which is semantically different from the fiscal period end).
        # TODO(layer-b): pull period_of_report from the pack manifest once
        # harvest/runner.py writes it.
        period_end=_date.min,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form_type=pack_record.form_type,
        filed=filed,
        accession=pack_record.accession,
        cik=pack_record.cik,
        company=pack_record.company_name,
        taxonomy="kpi-prose",
        primary_document=primary_document,
        fact_id="",
        excerpt_text=str(response.get("excerpt", "")),
        source="learned:kpi-llm",
    )


def _verify_against_prior_filing(
    current_value: float,
    metric: str,
    cik: str,
    current_accession: str,
    current_form_type: str,
    registry: PackRegistry,
    registry_path: Path | None,
) -> tuple[bool, str]:
    """Verify by extracting the same KPI from the prior filing of the same
    form type and comparing.
    """
    # Lazy import: self_heal imports from concepts, which re-exports
    # KPI_CATALOG from this module. Top-level import would create
    # concepts -> kpi_extract -> self_heal -> concepts cycle at import time.
    from .self_heal import verify_order_of_magnitude

    all_prior = registry.list_packs(cik=cik, form_type=current_form_type, limit=10)
    prior = [p for p in all_prior if p.accession != current_accession]
    if not prior:
        return False, "no_prior_filing"

    prior_pack = prior[0]

    learned_reg = LearnedRegistry(db_path=registry_path)
    try:
        cached = learned_reg.lookup(
            cik=cik, metric=metric, accession=prior_pack.accession,
        )
    finally:
        learned_reg.close()

    prior_value: float | None = None
    if cached is not None and cached.value_sample is not None:
        prior_value = float(cached.value_sample)
    else:
        # Forward reference: try_extract_kpi is defined in Task 11. Until
        # Task 11 lands in the same file, this branch can't execute — but
        # if the LearnedRegistry cache is missing or has value_sample=None,
        # we'd otherwise NameError at call time. Guard with a module-level
        # lookup so the fallback is clean.
        try_extract = globals().get("try_extract_kpi")
        if try_extract is None:
            return False, "prior_extract_unavailable"
        cited = try_extract(
            metric=metric,
            cik=cik,
            company=prior_pack.company_name,
            period="lfy",
            registry_path=registry_path,
            pack_registry=registry,
            _verify=False,
            _override_pack=prior_pack,
            _no_persist=True,  # don't cache prior with verified=False
        )
        if cited is None or not isinstance(cited.value, (int, float)):
            return False, "prior_extract_failed"
        prior_value = float(cited.value)

    if prior_value is None:
        return False, "prior_extract_failed"

    if verify_order_of_magnitude(current_value, prior_value):
        return True, "prior_filing_crosscheck"
    return False, "prior_filing_crosscheck"


def try_extract_kpi(
    metric: str,
    cik: str,
    company: str,
    period: str,
    *,
    registry_path: Path | None = None,
    pack_registry: PackRegistry | None = None,
    _verify: bool = True,
    _override_pack: PackRecord | None = None,
    _no_persist: bool = False,
) -> CitedValue | None:
    """Layer B entry point. Extracts a KPI from a pack's MD&A/segment sections.

    Returns a CitedValue with source='learned:kpi-llm' (or 'learned:kpi-cached'
    on a registry hit), or None on any failure path.

    Parameters:
        metric: canonical metric name (must be in KPI_CATALOG)
        cik: zero-padded CIK string
        company: company name (used in the LLM prompt)
        period: lfy / mrq / mrp / ltm / annual:N / quarterly:N
        registry_path: path to the learned_concepts registry db (None -> default)
        pack_registry: PackRegistry instance (None -> new default one)
        _verify: internal, set to False by recursive prior-filing cross-check
        _override_pack: internal, set when the caller has already resolved
                        the prior filing (skips _resolve_filing_for_period)
        _no_persist: internal, set to True by recursive prior-filing calls so
                     a successful prior extraction is not cached with
                     verified=False (cache pollution prevention)
    """
    kpi_def = KPI_CATALOG.get(metric)
    if kpi_def is None:
        return None

    own_registry = False
    if pack_registry is None:
        pack_registry = PackRegistry()
        own_registry = True

    try:
        # 1. Resolve filing
        if _override_pack is not None:
            pack_record = _override_pack
        else:
            pack_record = _resolve_filing_for_period(cik, period, pack_registry)
        if pack_record is None:
            return None

        accession = pack_record.accession

        # 2. Cache check
        learned_reg = LearnedRegistry(db_path=registry_path)
        try:
            cached = learned_reg.lookup(cik=cik, metric=metric, accession=accession)
            if cached is not None:
                # Cached verification is treated as permanent. EDGAR accessions
                # are filing-immutable; restatements arrive as separate
                # accessions under new (cik, accession, metric) keys, so a
                # cached verified=True for this accession remains valid.
                pack_dir = Path(pack_record.pack_dir)
                try:
                    manifest = _load_pack_manifest(pack_dir)
                except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                    logger.warning(
                        "Layer B cache hit but pack manifest unreadable at %s: %s",
                        pack_dir, e,
                    )
                    return None
                primary_doc = manifest.get("filing", {}).get(
                    "primary_document", ""
                )
                fiscal_year_cached, filed_cached = _parse_filing_date_safe(
                    pack_record.filing_date
                )
                # Note: excerpt_text is not persisted in learned_concepts (v2
                # schema), so cached CitedValues fall back to the concept-label
                # text fragment in document_url rather than the tight excerpt
                # anchor the live extraction path produces. A future v3
                # migration could add excerpt_text to LearnedRow; for v2 the
                # degradation is documented and accepted.
                cited = CitedValue(
                    value=cached.value_sample,
                    unit=kpi_def.unit_hint,
                    metric=metric,
                    concept=cached.concept,
                    period_end=_date.min,
                    fiscal_year=fiscal_year_cached,
                    fiscal_period="FY" if pack_record.form_type.startswith("10-K") else "",
                    form_type=pack_record.form_type,
                    filed=filed_cached,
                    accession=accession,
                    cik=cik,
                    company=pack_record.company_name,
                    taxonomy=cached.taxonomy,
                    primary_document=primary_doc,
                    fact_id="",
                    source="learned:kpi-cached",
                )
                if not cached.verified:
                    cited.warnings.append(
                        "Resolved via unverified learned KPI mapping. "
                        f"Verify manually: edgarpack learned verify {cik} {metric}"
                    )
                learned_reg.bump_hit_count(
                    cik=cik, metric=metric, accession=accession,
                )
                return cited
        finally:
            learned_reg.close()

        # 3. Load pack manifest
        pack_dir = Path(pack_record.pack_dir)
        try:
            manifest = _load_pack_manifest(pack_dir)
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(
                "Layer B cache hit but pack manifest unreadable at %s: %s",
                pack_dir, e,
            )
            return None

        # 4. Select sections
        sections = manifest.get("sections", [])
        selected = _select_sections(sections)
        if not selected:
            return None

        # 5. Read and trim text
        raw_text = _read_section_text(pack_dir, selected)
        if not raw_text:
            return None
        text = _trim_to_budget(raw_text)

        # 6. LLM backend check
        if not _llm_backend_available_kpi():
            return None

        # 7. Build prompt + extract
        filing_meta = manifest.get("filing", {})
        prompt = _build_extraction_prompt(
            metric=metric,
            kpi_def=kpi_def,
            company=filing_meta.get("company_name", company),
            form_type=filing_meta.get("form_type", pack_record.form_type),
            filing_date=filing_meta.get("filing_date", pack_record.filing_date),
            text=text,
        )
        response = _extract_via_llm(prompt)
        if response is None:
            return None

        confidence = response.get("confidence")
        if confidence in ("not_found", "ambiguous", "low"):
            return None

        # 8. Verify excerpt is a substring of the source text
        excerpt = str(response.get("excerpt", ""))
        if not _verify_excerpt_in_text(excerpt, text):
            logger.warning(
                "Layer B rejected hallucinated excerpt for %s/%s: %s",
                cik, metric, excerpt[:100],
            )
            return None

        # 9. Build CitedValue
        primary_doc = filing_meta.get("primary_document", "")
        if not primary_doc:
            artifacts = manifest.get("artifacts", {})
            if isinstance(artifacts, dict):
                for path in artifacts:
                    if path.endswith(".htm") and "/" not in path:
                        primary_doc = path
                        break
        cited = _build_cited_from_extraction(
            response=response,
            metric=metric,
            kpi_def=kpi_def,
            pack_record=pack_record,
            pack_manifest=manifest,
            primary_document=primary_doc,
        )

        # 10. Verification (skipped on recursive calls)
        verified = False
        verif_method: str | None = None
        if _verify and isinstance(cited.value, (int, float)):
            verified, verif_method = _verify_against_prior_filing(
                current_value=float(cited.value),
                metric=metric,
                cik=cik,
                current_accession=accession,
                current_form_type=pack_record.form_type,
                registry=pack_registry,
                registry_path=registry_path,
            )

        # 11. Persist (skip on recursive verification calls so a successful
        # prior-filing extraction isn't cached with verified=False)
        if not _no_persist:
            learned_reg = LearnedRegistry(db_path=registry_path)
            try:
                learned_reg.upsert(
                    cik=cik,
                    metric=metric,
                    concept=cited.concept,
                    taxonomy="kpi-prose",
                    source="kpi-llm",
                    verified=verified,
                    verif_method=verif_method,
                    value_sample=float(cited.value) if isinstance(cited.value, (int, float)) else None,
                    accession=accession,
                )
            finally:
                learned_reg.close()

        cited.source = "learned:kpi-llm"
        if not verified:
            reason = {
                "no_prior_filing": "No prior filing available for cross-check.",
                "prior_extract_failed": "Prior-filing extraction failed; could not cross-check.",
                "prior_extract_unavailable": "Prior-filing extractor unavailable.",
                "prior_filing_crosscheck": "Value was outside the expected order of magnitude vs. prior filing.",
            }.get(verif_method or "", "Unverified learned KPI mapping.")
            cited.warnings.append(f"Unverified: {reason}")

        return cited
    finally:
        # Safe on recursion: _verify_against_prior_filing passes pack_registry
        # back to the inner try_extract_kpi call, so the inner call's
        # own_registry=False and only the outer (this) call closes it.
        if own_registry:
            pack_registry.close()
