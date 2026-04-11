"""Self-heal Layer A: discover the right GAAP concept when METRIC_MAP misses.

Resolution order inside this module:
    1. LearnedRegistry cache hit (handled in try_learn)
    2. _fuzzy_match: token-based scoring over the company's actual concepts
    3. _llm_propose: subprocess to codex/claude if available
    4. _verify_order_of_magnitude against a prior-year ground truth

See docs/superpowers/specs/2026-04-11-self-heal-v1-design.md for the full
design rationale.
"""

from __future__ import annotations

import re
from typing import Any

# Synonym hints for fuzzy-matching metric names against GAAP concept names.
# Each hint tuple is OR'd into the token pool when scoring candidates.
METRIC_HINTS: dict[str, tuple[str, ...]] = {
    "revenue":                ("revenue", "revenues", "sales", "contract"),
    "cost_of_revenue":        ("cost", "revenue", "goods", "sold"),
    "gross_profit":           ("gross", "profit"),
    "operating_income":       ("operating", "income", "profit", "loss"),
    "net_income":             ("net", "income", "profit", "loss"),
    "rd_expense":             ("research", "development"),
    "sga_expense":            ("selling", "general", "administrative"),
    "stock_based_compensation": ("share", "based", "compensation"),
    "depreciation_amortization": ("depreciation", "amortization"),
    "operating_cash_flow":    ("cash", "provided", "used", "operating", "activities"),
    "investing_cash_flow":    ("cash", "provided", "used", "investing", "activities"),
    "financing_cash_flow":    ("cash", "provided", "used", "financing", "activities"),
    "free_cash_flow":         ("free", "cash", "flow"),
    "capex":                  ("payments", "acquire", "property", "plant", "equipment"),
    "total_assets":           ("assets",),
    "total_liabilities":      ("liabilities",),
    "total_equity":           ("stockholders", "equity"),
    "cash_and_equivalents":   ("cash", "equivalents"),
    "total_debt":             ("debt", "longtermdebt", "notespayable"),
    "eps_basic":              ("earnings", "per", "share", "basic"),
    "eps_diluted":            ("earnings", "per", "share", "diluted"),
}

_ALLOWED_TAXONOMIES = ("us-gaap", "ifrs-full")

_CAMEL_SPLIT = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALPHA = re.compile(r"[^a-zA-Z]+")


def _tokenize_concept(name: str) -> list[str]:
    """Split a CamelCase GAAP concept name into lowercased word tokens."""
    parts = _CAMEL_SPLIT.split(name)
    tokens: list[str] = []
    for part in parts:
        cleaned = _NON_ALPHA.sub(" ", part).strip()
        if not cleaned:
            continue
        tokens.extend(t.lower() for t in cleaned.split() if t)
    return tokens


def _tokenize_metric(metric: str) -> list[str]:
    """Split a metric name like 'operating_cash_flow' into tokens."""
    return [t for t in re.split(r"[_\W]+", metric.lower()) if t]


def _company_concepts(facts: dict[str, Any]) -> list[tuple[str, str]]:
    """Return every us-gaap / ifrs-full concept that reports a non-None value.

    Returns a list of (concept_name, taxonomy) tuples.
    """
    result: list[tuple[str, str]] = []
    for taxonomy in _ALLOWED_TAXONOMIES:
        tax_data = facts.get(taxonomy, {})
        for concept_name, concept_data in tax_data.items():
            units = concept_data.get("units", {}) if isinstance(concept_data, dict) else {}
            has_value = False
            for unit_values in units.values():
                if not isinstance(unit_values, list):
                    continue
                for v in unit_values:
                    if isinstance(v, dict) and v.get("val") is not None:
                        has_value = True
                        break
                if has_value:
                    break
            if has_value:
                result.append((concept_name, taxonomy))
    return result


def _fuzzy_match(
    metric: str,
    candidates: list[tuple[str, str]],
    facts: dict[str, Any],
    threshold: float = 0.5,
) -> tuple[str, str] | None:
    """Score each candidate against the metric's token pool. Return best or None.

    The token pool for scoring combines:
      - metric's own tokens (e.g. 'operating_cash_flow' -> operating, cash, flow)
      - hint tokens from METRIC_HINTS[metric] if present

    Score = |metric_tokens & concept_tokens| / |metric_tokens|.
    Returns (concept_name, taxonomy) with the highest score >= threshold,
    or None.
    """
    metric_tokens: set[str] = set(_tokenize_metric(metric))
    metric_tokens.update(METRIC_HINTS.get(metric, ()))
    # Remove very short stop-ish tokens that match too many things
    metric_tokens = {t for t in metric_tokens if len(t) >= 3}
    if not metric_tokens:
        return None

    best_score = 0.0
    best: tuple[str, str] | None = None
    for concept_name, taxonomy in candidates:
        concept_tokens = set(_tokenize_concept(concept_name))
        if not concept_tokens:
            continue
        overlap = metric_tokens & concept_tokens
        if not overlap:
            continue
        score = len(overlap) / len(metric_tokens)
        if score > best_score:
            best_score = score
            best = (concept_name, taxonomy)

    if best is None or best_score < threshold:
        return None
    return best


def verify_order_of_magnitude(
    proposed_value: float | None,
    prior_year_value: float | None,
    min_ratio: float = 0.25,
    max_ratio: float = 4.0,
) -> bool:
    """True when ``proposed_value`` is within [min_ratio, max_ratio] of the prior year.

    Compares absolute values so a sign flip is tolerated as long as the
    magnitude is in the right ballpark. This is a sanity check, not a
    correctness proof. Bad concept mappings often return values that are
    one or two orders of magnitude off (segment pieces, per-share instead
    of absolute, thousands vs millions, etc.) and this catches them.

    Returns False if there's no prior year to compare against. Callers
    should treat False as 'unverified', not 'wrong'. The value still gets
    persisted with verified=0.
    """
    if proposed_value is None:
        return False
    if prior_year_value is None or prior_year_value == 0:
        return False
    ratio = abs(proposed_value) / abs(prior_year_value)
    return min_ratio <= ratio <= max_ratio


import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Detect an available LLM CLI at import time. Module-level constant so tests
# can monkey-patch it. None means no backend is available.
_LLM_CMD: str | None = None
for _candidate in ("codex", "claude"):
    if shutil.which(_candidate):
        _LLM_CMD = _candidate
        break


def _llm_backend_available() -> bool:
    return _LLM_CMD is not None


_LLM_TIMEOUT_SECONDS = 30
_LLM_MAX_CANDIDATES = 40  # Keep prompt tight; more than this and we rely on fuzzy


def _latest_value_for(
    facts: dict[str, Any] | None,
    concept: str,
    taxonomy: str,
) -> float | int | None:
    if facts is None:
        return None
    tax_data = facts.get(taxonomy, {})
    concept_data = tax_data.get(concept, {})
    units = concept_data.get("units", {}) if isinstance(concept_data, dict) else {}
    for unit_values in units.values():
        if not isinstance(unit_values, list):
            continue
        for v in reversed(unit_values):
            if isinstance(v, dict) and v.get("val") is not None:
                return v.get("val")
    return None


def _build_llm_prompt(
    metric: str,
    company: str,
    candidates: list[tuple[str, str]],
    facts: dict[str, Any] | None = None,
) -> str:
    # Trim the candidate list and annotate with a sample value where possible
    trimmed = candidates[:_LLM_MAX_CANDIDATES]
    lines = []
    for concept, taxonomy in trimmed:
        sample = _latest_value_for(facts, concept, taxonomy) if facts else None
        if sample is not None:
            lines.append(f"  {concept}: {sample}")
        else:
            lines.append(f"  {concept}")
    concepts_block = "\n".join(lines)

    return (
        f"You are resolving a financial metric to an XBRL concept tag.\n\n"
        f"Company: {company}\n"
        f'Requested metric: "{metric}"\n\n'
        f"Candidate concepts reported by this company (with latest USD value "
        f"where known):\n{concepts_block}\n\n"
        f"Which concept represents the requested metric?\n"
        f"Return strict JSON with no prose:\n"
        f'  {{"concept": "ExactConceptName", "taxonomy": "us-gaap"}}\n'
        f"or:\n"
        f"  null\n"
    )


def _llm_propose(
    metric: str,
    company: str,
    candidates: list[tuple[str, str]],
    facts: dict[str, Any] | None = None,
) -> tuple[str, str] | None:
    """Ask an external LLM CLI to pick a concept from the candidate list.

    Returns (concept_name, taxonomy) on success, or None on any failure:
    no backend, timeout, non-zero exit, malformed JSON, hallucinated concept.
    """
    if _LLM_CMD is None:
        return None
    if not candidates:
        return None

    prompt = _build_llm_prompt(metric, company, candidates, facts=facts)

    try:
        completed = subprocess.run(
            [_LLM_CMD, "exec", "--prompt", prompt],
            capture_output=True,
            text=True,
            timeout=_LLM_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("LLM propose failed: %s", e)
        return None

    if completed.returncode != 0:
        logger.warning(
            "LLM propose returned non-zero: %s",
            (completed.stderr or "")[:200],
        )
        return None

    raw = (completed.stdout or "").strip()
    if not raw or raw.lower() == "null":
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try to salvage a JSON object out of a wrapper like markdown
        match = re.search(r"\{[^}]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict):
        return None
    concept = parsed.get("concept")
    taxonomy = parsed.get("taxonomy")
    if not isinstance(concept, str) or not isinstance(taxonomy, str):
        return None

    # Reject hallucinated concepts: must be in the candidate list
    candidate_set = {(c, t) for c, t in candidates}
    if (concept, taxonomy) not in candidate_set:
        return None

    return (concept, taxonomy)
