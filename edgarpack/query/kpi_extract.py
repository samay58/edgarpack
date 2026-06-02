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

import hashlib
import json
import logging
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any, Protocol

from ..harvest.registry import PackRecord, PackRegistry
from ..pack.manifest import load_manifest_dict
from ..sec.submissions import is_registration_form
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


def _load_pack_manifest(pack_dir: Path) -> dict[str, Any]:
    """Load manifest.json from a pack directory.

    Thin wrapper around `pack.manifest.load_manifest_dict`. Re-exported via
    `_load_pack_manifest` so existing imports in `kpi_discover` keep working;
    new callers should import the shared helper directly.
    """
    return load_manifest_dict(pack_dir, on_missing="raise")


def _infer_fiscal_period_label(form_type: str, period_end: _date) -> str:
    """Derive a fiscal_period label ('FY' or 'Q1'..'Q4') from form + period_end.

    10-K -> 'FY'. 10-Q -> Q from the calendar-quarter the period_end falls in.
    Non-calendar fiscal years won't map their Q1-Q4 to calendar quarters, but
    the value remains stable per (company, filing) and preserves ordering for
    the `which` command's period matrix. Returns '' for unknown form types so
    downstream code can detect the uninferred case.
    """
    form = (form_type or "").upper()
    if form.startswith("10-K") or form.startswith("20-F"):
        return "FY"
    if form.startswith("10-Q"):
        if period_end == _date.min:
            return ""
        month = period_end.month
        quarter = (month - 1) // 3 + 1  # 1..4
        return f"Q{quarter}"
    return ""


def _resolve_period_end(
    pack_manifest: dict[str, Any],
    pack_record: PackRecord,
) -> tuple[_date, int, str]:
    """Resolve (period_end, fiscal_year, fiscal_period) for a pack.

    Resolution order:
      1. manifest.filing.period_of_report (canonical, set from SEC reportDate
         for packs built with the post-Layer-B-period-fix build pipeline).
      2. pack_record.filing_date (older packs; approximation that's off by
         up to 60-90 days for 10-Ks and 40-45 days for 10-Qs, but stable and
         monotone per company).
      3. (_date.min, 0, '') sentinel when both sources are unparseable.
    """
    filing = pack_manifest.get("filing", {}) if isinstance(pack_manifest, dict) else {}

    raw = filing.get("period_of_report")
    if isinstance(raw, str) and raw.strip():
        try:
            period_end = _date.fromisoformat(raw.strip())
            return (
                period_end,
                period_end.year,
                _infer_fiscal_period_label(pack_record.form_type, period_end),
            )
        except ValueError:
            pass

    fallback_raw = filing.get("filing_date") or pack_record.filing_date
    if isinstance(fallback_raw, str) and fallback_raw.strip():
        try:
            filed = _date.fromisoformat(fallback_raw.strip())
            return (
                filed,
                filed.year,
                _infer_fiscal_period_label(pack_record.form_type, filed),
            )
        except ValueError:
            pass

    return _date.min, 0, ""


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
        phrases=("annual recurring revenue", "ARR", "ending ARR", "ARR of approximately"),
        unit_hint="USD",
        description="Annualized subscription revenue at period end.",
    ),
    "nrr": KpiDef(
        phrases=(
            "net revenue retention",
            "dollar-based net retention",
            "net dollar retention",
            "NRR",
            "NDR",
        ),
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
        phrases=("current remaining performance obligations", "cRPO", "current RPO"),
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
        phrases=("total customers", "number of customers", "customers with ARR over"),
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
        phrases=(
            "gross merchandise volume",
            "GMV",
            "gross transaction value",
            "gross booking value",
        ),
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
        phrases=("number of transactions", "total transactions", "transactions processed"),
        unit_hint="count",
    ),
    # Retail / consumer goods
    "same_store_sales": KpiDef(
        phrases=("same-store sales", "comparable store sales", "comparable sales"),
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
    # MD&A is Part II Item 7 in a 10-K. Match both "parti_" and "partii_"
    # so we also catch any Part I Item 7 edge case from unusual filers.
    re.compile(r"^10k_parti+_item7(?=_|$)"),  # MD&A (10-K, Part I or II)
    re.compile(r"^10k_parti+_item7a(?=_|$)"),  # Quant/Qual market risk
    re.compile(r"^10q_parti+_item2(?=_|$)"),  # MD&A (10-Q, Part I)
    # Item 1 Business often contains the "Key Operating Metrics" narrative
    # where tech companies report DAU, ARR, NRR, and similar KPIs. The
    # sectionizer sometimes captures a thin MD&A stub while the actual
    # metrics live in Item 1. Including it costs ~30-50K chars but stays
    # within the 60K budget for most filings.
    re.compile(r"^10k_parti+_item1(?=_|$)"),  # Business (10-K, Part I)
    # Unanchored: slug patterns fire anywhere in the section ID.
    # A segment overview nested inside Item 1 Business is a valid target.
    re.compile(r"_segment"),
    re.compile(r"_key_metric"),
    re.compile(r"_operating_data"),
    re.compile(r"_key_performance"),
    re.compile(r"^s1_itemother_prospectus_summary(?=_|$)"),
    re.compile(r"^s1_itemother_managements_discussion(?=_|$)"),
    re.compile(r"^s1_itemother_business(?=_|$)"),
    re.compile(r"^s1_itemother_summary_consolidated(?=_|$)"),
    re.compile(r"_non_gaap"),
)


def _select_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return manifest section entries whose IDs match MD&A / key-metrics patterns.

    Preserves manifest order. Empty list if none match. The caller handles
    the 'malformed pack' case.
    """
    result: list[dict[str, Any]] = []
    for sec in sections:
        sec_id = str(sec.get("id", ""))
        if any(pat.search(sec_id) for pat in _SECTION_PATTERNS):
            result.append(sec)
    return result


def _section_prompt_priority(section: dict[str, object]) -> int:
    """Rank selected sections for KPI prompt packing.

    Some 10-Ks put long Item 1 Business text before MD&A in the manifest.
    If we concatenate that order and then trim to the LLM budget, the actual
    KPI tables can disappear. Keep the filter separate from ordering so cache
    and diagnostics still know which sections were selected.
    """
    sec_id = str(section.get("id", "")).lower()
    title = str(section.get("title", "")).lower()
    haystack = f"{sec_id} {title}"

    if any(token in haystack for token in ("key_metric", "key metric", "key performance")):
        return 0
    if "operating_data" in haystack or "operating data" in haystack:
        return 0
    if "prospectus_summary" in haystack or "prospectus summary" in haystack:
        return 0
    if "managements_discussion" in haystack or "management's discussion" in haystack:
        return 1
    if re.match(r"^10k_parti+_item7(?=_|$)", sec_id) or re.match(
        r"^10q_parti+_item2(?=_|$)", sec_id
    ):
        return 1
    if "_segment" in sec_id or "segment" in title:
        return 2
    if re.match(r"^10k_parti+_item1(?=_|$)", sec_id):
        return 3
    if "business" in haystack:
        return 3
    if re.match(r"^10k_parti+_item7a(?=_|$)", sec_id):
        return 4
    return 5


def _order_sections_for_kpi_prompt(
    sections: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return selected sections in prompt-priority order.

    Sorting is stable inside each priority bucket so comparable sections keep
    their manifest order.
    """
    return [
        section
        for _, section in sorted(
            enumerate(sections),
            key=lambda item: (_section_prompt_priority(item[1]), item[0]),
        )
    ]


_SECTION_SEPARATOR = "\n\n--- [{id}] ---\n\n"


def _read_section_text(pack_dir: Path, sections: list[dict[str, Any]]) -> str:
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
            logger.warning("Section file missing: %s (pack=%s)", section_file, pack_dir)
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
for _candidate in ("claude", "codex"):
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


def _run_llm_raw(prompt: str, timeout: int = _LLM_TIMEOUT_SECONDS_KPI) -> str | None:
    """Run the detected KPI LLM backend on a prompt and return stdout.

    Factored out so _extract_via_llm (catalog extraction) and the discovery
    pipeline (edgarpack which) share the same subprocess invocation shape
    but can parse the response differently. Returns None on any failure.
    """
    if _LLM_CMD_KPI is None:
        return None

    output_path: Path | None = None
    stdin_text: str | None = None
    if _LLM_CMD_KPI == "codex":
        # Codex CLI emits session logs on stdout. Ask it to write only the
        # final model response to a temp file and pass the prompt through stdin
        # so long SEC filing excerpts do not ride through argv.
        output_file = tempfile.NamedTemporaryFile(
            prefix="edgarpack-kpi-",
            suffix=".json",
            delete=False,
        )
        output_path = Path(output_file.name)
        output_file.close()
        cmd = [
            _LLM_CMD_KPI,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(output_path),
            "-",
        ]
        stdin_text = prompt
    elif _LLM_CMD_KPI == "claude":
        cmd = [_LLM_CMD_KPI, "--bare", "--tools", "", "-p", prompt]
    else:
        cmd = [_LLM_CMD_KPI, "-p", prompt]

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            input=stdin_text,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.info("KPI LLM call failed: %s", e)
        if output_path is not None:
            output_path.unlink(missing_ok=True)
        return None

    if completed.returncode != 0:
        logger.info(
            "KPI LLM returned non-zero: %s",
            (completed.stderr or "")[:200],
        )
        if output_path is not None:
            output_path.unlink(missing_ok=True)
        return None

    raw = ""
    if output_path is not None:
        try:
            raw = output_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            logger.info("KPI LLM output file read failed: %s", e)
        finally:
            output_path.unlink(missing_ok=True)

    if not raw:
        raw = (completed.stdout or "").strip()
    return raw or None


def _extract_via_llm(prompt: str) -> dict[str, Any] | None:
    raw = _run_llm_raw(prompt)
    if raw is None:
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

    return dict(parsed)


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
    response: dict[str, Any],
    metric: str,
    kpi_def: KpiDef,
    pack_record: PackRecord,
    pack_manifest: dict[str, Any],
    primary_document: str,
) -> CitedValue:
    filing = pack_manifest.get("filing", {})

    filing_date_str = str(filing.get("filing_date", pack_record.filing_date))
    try:
        filed = _date.fromisoformat(filing_date_str)
    except ValueError:
        filed = _date.min

    # Layer B period fix: pull period_of_report from the manifest when
    # available (post-period-fix builds); fall back to filing_date for older
    # packs. Either is strictly better than the legacy date.min sentinel
    # which broke downstream period filtering.
    period_end, fiscal_year, fiscal_period = _resolve_period_end(pack_manifest, pack_record)

    concept = kpi_def.phrases[0] if kpi_def.phrases else metric

    return CitedValue(
        value=response["value"],
        unit=str(response.get("unit") or kpi_def.unit_hint),
        metric=metric,
        concept=concept,
        period_end=period_end,
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
            cik=cik,
            metric=metric,
            accession=prior_pack.accession,
        )
    finally:
        learned_reg.close()

    prior_value: float | None = None
    if cached is not None and cached.value_sample is not None:
        prior_value = float(cached.value_sample)
    else:
        # If the LearnedRegistry entry lacks a value_sample, we fall back to
        # re-running the full extractor on the prior filing. Look up via
        # globals() so this stays resilient to future module reorganizations
        # that might temporarily break the direct reference.
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
            pack_record: PackRecord | None = _override_pack
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
                except FileNotFoundError:
                    logger.warning("Layer B cache hit but manifest missing at %s", pack_dir)
                    return None
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Layer B cache hit but manifest is invalid JSON at %s: %s",
                        pack_dir,
                        e,
                    )
                    return None
                except (OSError, UnicodeDecodeError) as e:
                    logger.warning(
                        "Layer B cache hit but manifest I/O error at %s: %s",
                        pack_dir,
                        e,
                    )
                    return None
                primary_doc = manifest.get("filing", {}).get("primary_document", "")
                _, filed_cached = _parse_filing_date_safe(pack_record.filing_date)
                period_end_cached, fiscal_year_cached, fiscal_period_cached = _resolve_period_end(
                    manifest, pack_record
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
                    period_end=period_end_cached,
                    fiscal_year=fiscal_year_cached,
                    fiscal_period=fiscal_period_cached,
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
                    cik=cik,
                    metric=metric,
                    accession=accession,
                )
                return cited
        finally:
            learned_reg.close()

        # 3. Load pack manifest
        pack_dir = Path(pack_record.pack_dir)
        try:
            manifest = _load_pack_manifest(pack_dir)
        except FileNotFoundError:
            logger.warning("Layer B extraction skipped: manifest missing at %s", pack_dir)
            return None
        except json.JSONDecodeError as e:
            logger.warning(
                "Layer B extraction skipped: manifest invalid JSON at %s: %s",
                pack_dir,
                e,
            )
            return None
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(
                "Layer B extraction skipped: manifest I/O error at %s: %s",
                pack_dir,
                e,
            )
            return None

        # 4. Select sections
        sections = manifest.get("sections", [])
        selected = _select_sections(sections)
        if not selected:
            return None

        # 5. Read and trim text
        raw_text = _read_section_text(pack_dir, _order_sections_for_kpi_prompt(selected))
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
                cik,
                metric,
                excerpt[:100],
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
                    value_sample=float(cited.value)
                    if isinstance(cited.value, (int, float))
                    else None,
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
                "prior_filing_crosscheck": (
                    "Value was outside the expected order of magnitude vs. prior filing."
                ),
            }.get(verif_method or "", "Unverified learned KPI mapping.")
            cited.warnings.append(f"Unverified: {reason}")

        return cited
    finally:
        # Safe on recursion: _verify_against_prior_filing passes pack_registry
        # back to the inner try_extract_kpi call, so the inner call's
        # own_registry=False and only the outer (this) call closes it.
        if own_registry:
            pack_registry.close()


# Per-company KPI discovery (`edgarpack which`)


@dataclass(frozen=True)
class DiscoveredKpi:
    """A single free-form KPI the LLM discovered in a filing.

    Distinct from catalog KPIs: these are mined per-company (e.g. Figma's
    'paid seats', Costco's 'warehouse count') rather than matched against a
    fixed list. Written one row per filing-disclosure into company_kpis and
    aggregated across filings by kpi_discover.discover_kpis.
    """

    slug: str
    display_name: str
    unit: str | None
    magnitude: str | None
    value: float | None
    period_end: str
    fiscal_year: int
    fiscal_period: str
    definition: str | None
    section_id: str | None
    chunk_id: str | None
    source_substring: str
    confidence: float
    reused_slug: bool = False


@dataclass(frozen=True)
class DiscoveryExtractResult:
    """Detailed result for one filing's free-form KPI discovery pass."""

    kpis: list[DiscoveredKpi]
    status: str  # success | no_kpis | no_backend | llm_failed
    candidate_windows: list[KpiCandidateWindow] = field(default_factory=list)
    rejections: list[KpiDiscoveryRejection] = field(default_factory=list)
    model_attempts: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    retryable_failures: int = 0

    @property
    def candidate_count(self) -> int:
        return len(self.candidate_windows)

    @property
    def retryable(self) -> bool:
        return self.status in {"no_backend", "llm_failed"} or self.retryable_failures > 0


@dataclass(frozen=True)
class KpiCandidateWindow:
    """Bounded evidence window for staged free-form KPI discovery."""

    candidate_id: str
    cik: str
    accession: str
    section_id: str | None
    chunk_id: str | None
    window_text: str
    label_hint: str | None
    value_hints: tuple[str, ...]
    signal_names: tuple[str, ...]
    char_start: int
    char_end: int


@dataclass(frozen=True)
class KpiDiscoveryRejection:
    """Rejected staged discovery payload with enough context for diagnostics."""

    candidate_id: str | None
    stage: str
    reason: str
    raw_payload: str | None = None


class KpiModelClient(Protocol):
    """Pure text-in/text-out JSON completion interface for KPI extraction."""

    def complete_json(self, prompt: str, *, timeout: int) -> str | None: ...


_DISCOVERY_MAX_ITEMS = 40  # sane bound; real filings rarely list more than 15
_DISCOVERY_TIMEOUT_SECONDS = 90  # longer than single-KPI extract; more work


_SLUG_SAFE = re.compile(r"[^a-z0-9_]+")


def _slugify(text: str) -> str:
    """Normalize a display name to a snake_case slug.

    Fallback used when the LLM returns a malformed slug or we need to coin
    one from a raw display_name. Conservative: lowercase, ASCII-only,
    single underscores between tokens. Empty output when input is empty.
    """
    if not text:
        return ""
    base = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    base = base.lower()
    base = _SLUG_SAFE.sub("_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    return base


def _build_discovery_prompt(
    company: str,
    form_type: str,
    filing_date: str,
    period_of_report: str,
    existing_slugs: list[str],
    text: str,
) -> str:
    """Prompt for the 'list every disclosed business KPI' pass.

    Asks for a JSON list, each entry self-cited with a verbatim substring
    the hallucination firewall can verify. existing_slugs is the list of
    slugs already coined for this company so the LLM can reuse them when
    the raw disclosure name has drifted ('active designers' -> 'paid_seats').
    """
    existing_hint = (
        "Existing slugs for this company (reuse when the disclosure means the same "
        "thing, even if the text uses a different name):\n  "
        + ", ".join(f"'{s}'" for s in existing_slugs)
        + "\n\n"
        if existing_slugs
        else ""
    )
    return (
        "You are cataloguing every recurring business / operating KPI a company "
        "discloses in its SEC filing. Be conservative. Skip anything ambiguous.\n\n"
        f"Company: {company}\n"
        f"Filing: {form_type} filed {filing_date}\n"
        f"Period of report: {period_of_report or 'unknown'}\n\n"
        "Include:\n"
        "- Recurring operating / business metrics that the company uses to run the "
        "business and track health across periods (e.g. 'paid seats', 'daily active "
        "users', 'warehouse count', 'same-store sales', 'net dollar retention', "
        "'remaining performance obligations', 'take rate', 'members').\n"
        "- Metrics disclosed in a 'Key Business Metrics' / 'Key Performance "
        "Indicators' / 'Operating Data' / 'Segment Data' section or in MD&A prose "
        "that reference a specific number.\n\n"
        "Exclude:\n"
        "- GAAP income-statement / balance-sheet line items (revenue, cost of "
        "revenue, gross profit, operating income, net income, EBITDA, assets, "
        "liabilities, equity, cash, debt, interest expense, tax rate, etc.).\n"
        "- One-off / non-recurring numbers (restructuring charges, M&A purchase "
        "price, litigation settlement, a single customer's contract size, named "
        "executive compensation).\n"
        "- Forward-looking guidance, targets, and competitor figures.\n"
        "- Percentages that are just a ratio of two GAAP items (gross margin, "
        "operating margin, R&D intensity, debt to equity).\n\n"
        "For each KPI you include:\n"
        "- slug: lower_snake_case stable identifier. Short and canonical.\n"
        "- display_name: the company's own wording, trimmed.\n"
        "- unit: 'USD' | 'count' | 'percent' | 'days' | 'pure' (pure = dimensionless "
        "ratio) | null if the disclosure doesn't fit any of these.\n"
        "- magnitude: 'thousands' | 'millions' | 'billions' | null when the number "
        "is stated as-is.\n"
        "- value: the numeric value, in the stated magnitude (do NOT scale; e.g. "
        "'$3.44 billion' -> 3.44, magnitude='billions'). Null if no specific "
        "value was disclosed but the metric was named.\n"
        "- period_end: ISO date (YYYY-MM-DD) of the period the value covers, if "
        "stated. Null otherwise.\n"
        "- definition: one-sentence paraphrase of how the company defines it, if "
        "present; null otherwise.\n"
        "- section_id: the `--- [section_id] ---` marker closest above the "
        "source text. Must be one of the section IDs that appear in the text.\n"
        "- source_substring: a verbatim substring of the text (30-200 chars) "
        "containing the value. Must appear EXACTLY in the input. No paraphrasing.\n"
        "- confidence: 0.0-1.0.\n\n"
        f"{existing_hint}"
        "Respond with strict JSON of the shape:\n"
        '  { "kpis": [ { ... }, { ... } ] }\n'
        "No prose, no markdown fences. Empty list if the company does not "
        "disclose any qualifying KPIs.\n\n"
        f"TEXT (with `--- [section_id] ---` markers):\n{text}\n"
    )


def _parse_discovery_response(raw: str) -> list[dict[str, Any]] | None:
    """Parse the discovery LLM response. Tolerates surrounding whitespace,
    markdown fences, and stray prose. Returns the list of KPI dicts or None
    on unrecoverable failure."""
    if not raw:
        return None

    candidates: list[str] = [raw]
    # Strip possible ```json ... ``` fences the LLM sometimes injects
    # despite being told not to.
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", raw)
    if fence_match:
        candidates.insert(0, fence_match.group(1))

    # Also try the first top-level JSON object in the stream.
    obj_match = re.search(r"\{[\s\S]*\}", raw)
    if obj_match:
        candidates.append(obj_match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            kpis = parsed.get("kpis")
            if isinstance(kpis, list):
                return [dict(item) for item in kpis if isinstance(item, dict)]
        elif isinstance(parsed, list):
            return [dict(item) for item in parsed if isinstance(item, dict)]
    return None


def _load_chunks_index(pack_dir: Path) -> list[dict[str, Any]]:
    """Load optional/chunks.ndjson if present. Returns empty list otherwise.

    Chunks give finer-grained provenance than section IDs. The `which`
    command populates chunk_id when available so the resulting CitedValues
    can deep-link to the exact chunk in a downstream reader.
    """
    chunks_path = pack_dir / "optional" / "chunks.ndjson"
    if not chunks_path.exists():
        return []
    chunks: list[dict[str, Any]] = []
    try:
        with chunks_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    chunks.append(obj)
    except OSError as e:
        logger.info("Could not read chunks.ndjson at %s: %s", chunks_path, e)
    return chunks


def _lookup_chunk_id(
    chunks: list[dict[str, Any]],
    section_id: str | None,
    substring: str,
) -> str | None:
    """Find the chunk_id whose text contains the given substring.

    Scopes to the given section_id when possible. Returns None when chunks
    aren't loaded, the substring doesn't match, or the pack wasn't built
    with chunks. Uses the same normalization as the hallucination firewall
    so zero-width / whitespace differences don't cause misses.
    """
    if not chunks or not substring:
        return None
    needle = _normalize_for_match(substring)
    if not needle:
        return None

    scoped: list[dict[str, Any]] = (
        [c for c in chunks if c.get("section_id") == section_id] if section_id else chunks
    )
    for pool in (scoped, chunks):
        for chunk in pool:
            text = chunk.get("text", "")
            if not isinstance(text, str):
                continue
            if needle in _normalize_for_match(text):
                cid = chunk.get("chunk_id")
                if isinstance(cid, str) and cid:
                    return cid
    return None


def _coerce_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, str):
        try:
            f = float(value.replace(",", "").strip())
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


def _coerce_confidence(value: object) -> float:
    f = _coerce_float(value)
    if f is None:
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        # Some models return 80 instead of 0.8; clamp gracefully.
        if f <= 100.0:
            return f / 100.0
        return 1.0
    return f


_DISCOVERY_UNIT_ALLOWED = frozenset({"USD", "count", "percent", "days", "pure"})
_DISCOVERY_MAG_ALLOWED = frozenset({"thousands", "millions", "billions"})
_DISCOVERY_VERSION = "staged-kpi-v2"
_LOCATOR_VERSION = "locator-v1"

_KPI_KEYWORD_RE = re.compile(
    r"\b("
    r"user|users|customer|customers|subscriber|subscribers|account|accounts|asset|assets|"
    r"deposit|deposits|booking|bookings|volume|retention|store|stores|location|locations|"
    r"active|paying|paid|funded|platform|marketplace|cohort|take rate|arpu|auc|mau|dau|"
    r"maau|rvd|rider|riders|trip|trips|city|cities|fleet|vehicle|vehicles|"
    r"operational fleet|market share|retention|arr|nrr|rpo|seat|seats|member|members"
    r")\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z])(?:\$|US\$)?\s*\d[\d,]*(?:\.\d+)?\s*(?:%|percent|million|billion|thousand)?",
    re.IGNORECASE,
)
_HIGH_SIGNAL_SECTION_RE = re.compile(
    r"key[ _-]?(metric|performance)|operating[ _-]?data|business[ _-]?metrics|segment|"
    r"prospectus[ _-]?summary|managements?[ _-]?discussion|non[ _-]?gaap|business",
    re.IGNORECASE,
)
_GAAP_ONLY_SLUGS = frozenset(
    {
        "revenue",
        "net_revenue",
        "total_revenue",
        "cost_of_revenue",
        "gross_profit",
        "operating_income",
        "income_from_operations",
        "net_income",
        "net_loss",
        "ebitda",
        "assets",
        "liabilities",
        "equity",
        "cash",
        "debt",
        "interest_expense",
    }
)
_MAX_REGISTRATION_CANDIDATES = 16


class SubprocessKpiModelClient:
    """Adapter from the legacy subprocess backend to the staged client API."""

    def complete_json(self, prompt: str, *, timeout: int) -> str | None:
        return _run_llm_raw(prompt, timeout=timeout)


def _default_kpi_model_client() -> KpiModelClient | None:
    if not _llm_backend_available_kpi():
        return None
    return SubprocessKpiModelClient()


def _section_signal_name(section: dict[str, object]) -> str | None:
    haystack = f"{section.get('id', '')} {section.get('title', '')}"
    if _HIGH_SIGNAL_SECTION_RE.search(haystack):
        return "high_signal_section"
    return None


def _allow_number_sweep(section: dict[str, object], *, form_type: str) -> bool:
    if not is_registration_form(form_type):
        return True
    haystack = f"{section.get('id', '')} {section.get('title', '')}".lower()
    return any(
        token in haystack
        for token in (
            "key_metric",
            "key metric",
            "operating_data",
            "operating data",
            "business_metrics",
            "business metrics",
            "segment",
            "non_gaap",
            "non-gaap",
        )
    )


def _stable_candidate_id(
    *,
    accession: str,
    section_id: str | None,
    char_start: int,
    char_end: int,
    label_hint: str | None,
) -> str:
    raw = (
        f"{_LOCATOR_VERSION}|{accession}|{section_id or ''}|"
        f"{char_start}|{char_end}|{label_hint or ''}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _bounded_window(
    text: str,
    center: int,
    *,
    min_chars: int = 1500,
    max_chars: int = 4000,
) -> tuple[int, int]:
    size = min(max_chars, max(min_chars, min(len(text), max_chars)))
    start = max(0, center - size // 2)
    end = min(len(text), start + size)
    start = max(0, end - size)

    # Prefer paragraph boundaries when they are close enough to keep the
    # citation text intact without growing the prompt.
    para_start = text.rfind("\n\n", 0, center)
    if para_start >= 0 and center - para_start < size:
        start = max(0, para_start)
        end = min(len(text), start + size)
    para_end = text.find("\n\n", center)
    if para_end >= 0 and para_end - start <= max_chars:
        end = max(end, para_end)
    return start, end


def _label_hint(window_text: str) -> str | None:
    match = _KPI_KEYWORD_RE.search(window_text)
    if match:
        return match.group(0)
    for line in window_text.splitlines():
        stripped = line.strip(" -*|\t")
        if stripped:
            return stripped[:80]
    return None


def _value_hints(window_text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for match in _NUMBER_RE.finditer(window_text):
        value = match.group(0).strip()
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= 8:
            break
    return tuple(seen)


def _candidate_chunk_id(
    chunks: list[dict[str, Any]], section_id: str | None, window_text: str
) -> str | None:
    if not chunks or not section_id:
        return None
    norm_window = _normalize_for_match(window_text)
    for chunk in chunks:
        if chunk.get("section_id") != section_id:
            continue
        text = chunk.get("text")
        chunk_id = chunk.get("chunk_id")
        if not isinstance(text, str) or not isinstance(chunk_id, str) or not chunk_id:
            continue
        norm_chunk = _normalize_for_match(text)
        if norm_chunk and (norm_chunk in norm_window or norm_window in norm_chunk):
            return chunk_id
    return None


def locate_kpi_candidate_windows(
    *,
    pack_dir: Path,
    pack_record: PackRecord,
    sections: list[dict[str, object]],
    chunks: list[dict[str, Any]] | None = None,
) -> list[KpiCandidateWindow]:
    """Deterministically locate bounded operating-KPI evidence windows.

    The locator intentionally over-selects. Final KPI identity still goes
    through model classification plus deterministic validation.
    """
    candidates: list[KpiCandidateWindow] = []
    chunk_index = list(chunks or [])

    for section in sections:
        section_id = str(section.get("id", "") or "") or None
        rel_path = section.get("path")
        if not isinstance(rel_path, str) or not rel_path:
            continue
        section_file = pack_dir / rel_path
        try:
            text = section_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.strip():
            continue

        section_signal = _section_signal_name(section)
        hit_offsets: list[tuple[int, tuple[str, ...]]] = []
        for match in _KPI_KEYWORD_RE.finditer(text):
            left = max(0, match.start() - 350)
            right = min(len(text), match.end() + 350)
            if _NUMBER_RE.search(text[left:right]):
                signals = ["keyword_near_number"]
                if section_signal:
                    signals.append(section_signal)
                hit_offsets.append((match.start(), tuple(signals)))

        if section_signal and _allow_number_sweep(section, form_type=pack_record.form_type):
            for match in _NUMBER_RE.finditer(text):
                hit_offsets.append((match.start(), (section_signal, "number_in_signal_section")))

        if not hit_offsets:
            continue

        accepted_spans: list[tuple[int, int]] = []
        for offset, signal_names in sorted(hit_offsets, key=lambda item: item[0]):
            start, end = _bounded_window(text, offset)
            if any(
                start < prior_end and end > prior_start for prior_start, prior_end in accepted_spans
            ):
                continue
            window_text = text[start:end].strip()
            if not window_text:
                continue
            hints = _value_hints(window_text)
            if not hints:
                continue
            label = _label_hint(window_text)
            candidate = KpiCandidateWindow(
                candidate_id=_stable_candidate_id(
                    accession=pack_record.accession,
                    section_id=section_id,
                    char_start=start,
                    char_end=end,
                    label_hint=label,
                ),
                cik=pack_record.cik,
                accession=pack_record.accession,
                section_id=section_id,
                chunk_id=_candidate_chunk_id(chunk_index, section_id, window_text),
                window_text=window_text,
                label_hint=label,
                value_hints=hints,
                signal_names=tuple(dict.fromkeys(signal_names)),
                char_start=start,
                char_end=end,
            )
            candidates.append(candidate)
            accepted_spans.append((start, end))

    if is_registration_form(pack_record.form_type):
        return candidates[:_MAX_REGISTRATION_CANDIDATES]
    return candidates


def _build_candidate_discovery_prompt(
    *,
    company: str,
    form_type: str,
    filing_date: str,
    period_of_report: str,
    existing_slugs: list[str],
    candidate: KpiCandidateWindow,
) -> str:
    existing_hint = ", ".join(f"'{slug}'" for slug in existing_slugs) or "(none)"
    return (
        "You are extracting recurring business / operating KPIs from one bounded "
        "evidence window. Be conservative and do not use outside knowledge.\n\n"
        f"Company: {company}\n"
        f"Filing: {form_type} filed {filing_date}\n"
        f"Period of report: {period_of_report or 'unknown'}\n"
        f"Candidate ID: {candidate.candidate_id}\n"
        f"Section ID: {candidate.section_id or 'unknown'}\n"
        f"Existing company slugs: {existing_hint}\n"
        f"Locator signals: {', '.join(candidate.signal_names) or '(none)'}\n"
        f"Value hints: {', '.join(candidate.value_hints) or '(none)'}\n\n"
        "Include recurring operating metrics such as users, riders, cities, "
        "operational fleet, vehicles, trips, MAU, RVD, market share, funded customers, "
        "accounts, AUC/assets, net deposits, ARPU, ARR, retention, seats, stores, "
        "members, bookings, volume, or take rate. Exclude GAAP-only line items "
        "such as revenue, gross profit, operating income, net income, cash, debt, "
        "assets, liabilities, and one-off transaction figures.\n\n"
        "For each KPI, return slug, display_name, unit, magnitude, value, "
        "period_end, definition, section_id, source_substring, confidence. "
        "source_substring must be a verbatim substring of the window and contain "
        "the cited value. Return an empty list if there is no qualifying KPI.\n\n"
        "Respond with strict JSON only:\n"
        '  {"kpis": [{...}], "rejections": [{"reason": "..."}]}\n\n'
        f"WINDOW:\n{candidate.window_text}\n"
    )


def _payload_excerpt(payload: object) -> str:
    try:
        return json.dumps(payload, sort_keys=True)[:2000]
    except TypeError:
        return repr(payload)[:2000]


def _canonical_discovered_slug(slug: str, display_name: str, existing_slugs: set[str]) -> str:
    haystack = f"{slug} {display_name}".lower().replace("-", " ")
    normalized = _slugify(haystack)

    groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("arpu", ("arpu", "average_revenues_per_user", "average_revenue_per_user")),
        (
            "assets_under_custody",
            (
                "auc",
                "assets_under_custody",
                "asset_under_custody",
                "total_platform_assets",
                "platform_assets",
            ),
        ),
    )
    for canonical, aliases in groups:
        if any(alias in normalized for alias in aliases):
            for existing in existing_slugs:
                if existing == canonical or existing in aliases:
                    return canonical
            return canonical
    return slug


def _value_expected_text(value: float | None) -> str | None:
    if value is None:
        return None
    if math.isclose(value, round(value)):
        return str(int(round(value)))
    return f"{value:f}".rstrip("0").rstrip(".")


def _value_appears_in_excerpt(value: float | None, excerpt: str) -> bool:
    expected = _value_expected_text(value)
    if expected is None:
        return True
    assert value is not None
    norm_excerpt = _normalize_for_match(excerpt).replace(",", "")
    if expected in norm_excerpt:
        return True
    try:
        compact = f"{float(value):g}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return False
    return bool(compact and compact in norm_excerpt)


def _is_gaap_only_slug(slug: str) -> bool:
    return slug in _GAAP_ONLY_SLUGS


def _clean_discovered_item(
    item: dict[str, Any],
    selected_section_ids: set[str],
    source_text: str,
    existing_slugs: set[str],
) -> DiscoveredKpi | None:
    """Validate one LLM-returned KPI dict into a DiscoveredKpi.

    Rejects items whose source_substring does not appear in the text
    (hallucination firewall), whose section_id is unknown, or whose slug
    is empty after normalization. Silently clamps unknown unit/magnitude
    to None rather than rejecting the whole row.
    """
    display_name = str(item.get("display_name") or "").strip()
    raw_slug = str(item.get("slug") or "").strip().lower()
    slug = _slugify(raw_slug) or _slugify(display_name)
    if not slug:
        return None
    if _is_gaap_only_slug(slug):
        return None

    reused = slug in existing_slugs

    source_substring = str(item.get("source_substring") or "").strip()
    if not source_substring:
        return None

    value = _coerce_float(item.get("value"))
    if not _verify_excerpt_in_text(source_substring, source_text) or not _value_appears_in_excerpt(
        value, source_substring
    ):
        logger.info(
            "Discovery firewall rejected substring for slug=%s: %s",
            slug,
            source_substring[:80],
        )
        return None

    section_id_raw = item.get("section_id")
    section_id: str | None = None
    if isinstance(section_id_raw, str) and section_id_raw.strip():
        cand = section_id_raw.strip()
        if cand in selected_section_ids:
            section_id = cand

    unit_raw = item.get("unit")
    unit: str | None = (
        unit_raw if isinstance(unit_raw, str) and unit_raw in _DISCOVERY_UNIT_ALLOWED else None
    )

    magnitude_raw = item.get("magnitude")
    magnitude: str | None = (
        magnitude_raw
        if isinstance(magnitude_raw, str) and magnitude_raw in _DISCOVERY_MAG_ALLOWED
        else None
    )

    period_end_raw = str(item.get("period_end") or "").strip()
    if period_end_raw:
        try:
            _date.fromisoformat(period_end_raw)
        except ValueError:
            period_end_raw = ""

    definition_raw = item.get("definition")
    definition = (
        str(definition_raw).strip()
        if isinstance(definition_raw, str) and definition_raw.strip()
        else None
    )

    confidence = _coerce_confidence(item.get("confidence"))

    return DiscoveredKpi(
        slug=slug,
        display_name=display_name or slug.replace("_", " ").title(),
        unit=unit,
        magnitude=magnitude,
        value=value,
        period_end=period_end_raw,
        fiscal_year=0,
        fiscal_period="",
        definition=definition,
        section_id=section_id,
        chunk_id=None,
        source_substring=source_substring,
        confidence=confidence,
        reused_slug=reused,
    )


def extract_discoveries_detailed(
    *,
    pack_dir: Path,
    pack_record: PackRecord,
    manifest: dict[str, Any],
    existing_slugs: list[str] | None = None,
) -> DiscoveryExtractResult:
    """Run staged discovery on a single pack and return validated KPIs."""
    existing = list(existing_slugs or [])

    sections = manifest.get("sections", [])
    selected = _select_sections(sections)
    if not selected:
        return DiscoveryExtractResult(kpis=[], status="no_kpis")

    ordered_sections = _order_sections_for_kpi_prompt(selected)
    raw_text = _read_section_text(pack_dir, ordered_sections)
    if not raw_text:
        return DiscoveryExtractResult(kpis=[], status="no_kpis")

    chunks = _load_chunks_index(pack_dir)
    candidates = locate_kpi_candidate_windows(
        pack_dir=pack_dir,
        pack_record=pack_record,
        sections=ordered_sections,
        chunks=chunks,
    )
    if not candidates:
        return DiscoveryExtractResult(kpis=[], status="no_kpis")

    client = _default_kpi_model_client()
    if client is None:
        return DiscoveryExtractResult(
            kpis=[],
            status="no_backend",
            candidate_windows=candidates,
            retryable_failures=len(candidates),
        )

    filing_meta = manifest.get("filing", {})
    period_of_report = str(filing_meta.get("period_of_report") or "")
    selected_ids = {str(s.get("id", "")) for s in selected}
    existing_set = set(existing)

    # Period metadata once per pack (every extracted row inherits it).
    period_end_date, fiscal_year, fiscal_period = _resolve_period_end(manifest, pack_record)
    period_end_str = (
        period_end_date.isoformat() if period_end_date and period_end_date != _date.min else ""
    )

    best_by_slug: dict[str, DiscoveredKpi] = {}
    rejections: list[KpiDiscoveryRejection] = []
    model_attempts = 0
    rejected_rows = 0
    retryable_failures = 0

    for candidate in candidates:
        prompt = _build_candidate_discovery_prompt(
            company=str(filing_meta.get("company_name", pack_record.company_name)),
            form_type=str(filing_meta.get("form_type", pack_record.form_type)),
            filing_date=str(filing_meta.get("filing_date", pack_record.filing_date)),
            period_of_report=period_of_report,
            existing_slugs=sorted(existing_set),
            candidate=candidate,
        )
        model_attempts += 1
        raw = client.complete_json(prompt, timeout=_DISCOVERY_TIMEOUT_SECONDS)
        if raw is None:
            retryable_failures += 1
            rejections.append(
                KpiDiscoveryRejection(
                    candidate_id=candidate.candidate_id,
                    stage="model",
                    reason="model_unavailable_or_timeout",
                )
            )
            continue
        items = _parse_discovery_response(raw)
        if items is None:
            retryable_failures += 1
            rejections.append(
                KpiDiscoveryRejection(
                    candidate_id=candidate.candidate_id,
                    stage="parse",
                    reason="invalid_json",
                    raw_payload=raw[:2000],
                )
            )
            continue
        if not items:
            rejections.append(
                KpiDiscoveryRejection(
                    candidate_id=candidate.candidate_id,
                    stage="model",
                    reason="no_kpis_returned",
                    raw_payload=raw[:2000],
                )
            )
            continue

        for raw_item in items[:_DISCOVERY_MAX_ITEMS]:
            item = dict(raw_item)
            if candidate.section_id and not item.get("section_id"):
                item["section_id"] = candidate.section_id
            cleaned = _clean_discovered_item(
                item,
                selected_ids,
                candidate.window_text,
                existing_set,
            )
            if cleaned is None:
                rejected_rows += 1
                rejections.append(
                    KpiDiscoveryRejection(
                        candidate_id=candidate.candidate_id,
                        stage="validation",
                        reason="validation_firewall_rejected",
                        raw_payload=_payload_excerpt(raw_item),
                    )
                )
                continue

            slug = _canonical_discovered_slug(
                cleaned.slug,
                cleaned.display_name,
                existing_set | set(best_by_slug),
            )

            chunk_id = (
                _lookup_chunk_id(
                    chunks,
                    cleaned.section_id or candidate.section_id,
                    cleaned.source_substring,
                )
                or candidate.chunk_id
            )

            # Each row inherits the pack's period metadata. The model's own
            # period_end guess is kept only when populated and parseable.
            final_period_end = cleaned.period_end or period_end_str
            final_fy = fiscal_year
            final_fp = fiscal_period
            if cleaned.period_end:
                try:
                    d = _date.fromisoformat(cleaned.period_end)
                    final_fy = d.year
                    final_fp = _infer_fiscal_period_label(pack_record.form_type, d)
                except ValueError:
                    pass

            discovered = DiscoveredKpi(
                slug=slug,
                display_name=cleaned.display_name,
                unit=cleaned.unit,
                magnitude=cleaned.magnitude,
                value=cleaned.value,
                period_end=final_period_end,
                fiscal_year=final_fy,
                fiscal_period=final_fp,
                definition=cleaned.definition,
                section_id=cleaned.section_id,
                chunk_id=chunk_id,
                source_substring=cleaned.source_substring,
                confidence=cleaned.confidence,
                reused_slug=cleaned.reused_slug or slug in existing_set,
            )
            prior = best_by_slug.get(slug)
            if prior is None or discovered.confidence >= prior.confidence:
                best_by_slug[slug] = discovered

    results = list(best_by_slug.values())
    if not results:
        status = "llm_failed" if retryable_failures else "no_kpis"
        return DiscoveryExtractResult(
            kpis=[],
            status=status,
            candidate_windows=candidates,
            rejections=rejections,
            model_attempts=model_attempts,
            accepted_rows=0,
            rejected_rows=rejected_rows,
            retryable_failures=retryable_failures,
        )
    return DiscoveryExtractResult(
        kpis=results,
        status="success",
        candidate_windows=candidates,
        rejections=rejections,
        model_attempts=model_attempts,
        accepted_rows=len(results),
        rejected_rows=rejected_rows,
        retryable_failures=retryable_failures,
    )


def extract_discoveries(
    *,
    pack_dir: Path,
    pack_record: PackRecord,
    manifest: dict[str, Any],
    existing_slugs: list[str] | None = None,
) -> list[DiscoveredKpi]:
    """Backward-compatible wrapper returning only discovered KPI rows."""
    return extract_discoveries_detailed(
        pack_dir=pack_dir,
        pack_record=pack_record,
        manifest=manifest,
        existing_slugs=existing_slugs,
    ).kpis
