from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from ..query.metric_map import CANONICAL_METRICS, METRIC_MAP, AccountingStandard
from .extract import HKFact, _scope_for_section


class LLMClient(Protocol):
    def send(self, prompt: str) -> str: ...


_PROMPT = (
    "You are extracting a financial value from a Hong Kong listed company's prospectus.\n\n"
    "Section: {section_id}\n"
    "Metric: {metric}\n"
    "Accounting standard: {standard}\n\n"
    "Text:\n{text}\n\n"
    'Return a JSON object with two fields: "value" (the number, no formatting, null if not found), '
    '"label" (the line-item label you matched, null if not found). '
    "Reply with JSON only, no other text."
)


def cache_key_for(accession: str, section_id: str, metric: str, prompt: str) -> str:
    raw = f"{accession}|{section_id}|{metric}|{prompt}".encode()
    return hashlib.sha256(raw).hexdigest()


def _default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "cache" / "llm_extract"


def extract_metric_via_llm(
    section_text: str,
    section_id: str,
    metric: str,
    accession: str,
    cache_dir: Path,
    client: LLMClient,
    standard: str = "HKFRS",
) -> dict[str, Any]:
    prompt = _PROMPT.format(
        section_id=section_id,
        metric=metric,
        standard=standard,
        text=section_text[:8000],
    )
    key = cache_key_for(accession, section_id, metric, prompt)
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if not isinstance(cached, dict):
            raise ValueError(f"Cached HKEX LLM extraction at {cache_file} was not an object")
        return cached

    response = client.send(prompt)
    parsed = json.loads(response)
    if not isinstance(parsed, dict):
        raise ValueError("HKEX LLM extraction response was not an object")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(parsed))
    return parsed


def fill_missing_with_llm(
    existing: list[HKFact],
    sections_dir: Path,
    standard: AccountingStandard,
    accession: str,
    cache_dir: Path | None = None,
    client: LLMClient | None = None,
) -> list[HKFact]:
    extracted_metrics = {f.metric for f in existing}
    missing = [m for m in CANONICAL_METRICS if m not in extracted_metrics]
    if not missing:
        return existing

    cache_dir = cache_dir or _default_cache_dir()
    if client is None:
        return existing

    out = list(existing)
    for section_file in sorted(sections_dir.glob("*.md")):
        section_id = section_file.stem
        scope = _scope_for_section(section_id) or set()
        if not scope:
            continue
        text = section_file.read_text()
        for metric in list(missing):
            if metric not in scope:
                continue
            try:
                parsed = extract_metric_via_llm(
                    text, section_id, metric, accession, cache_dir, client, standard
                )
            except Exception:
                continue
            if parsed.get("value") is None:
                continue
            concept = (METRIC_MAP[standard].get(metric) or [metric])[0]
            out.append(
                HKFact(
                    metric=metric,
                    concept=concept,
                    value=parsed["value"],
                    unit="USD",
                    section_id=section_id,
                    extraction_method="learned:llm",
                    matched_label=parsed.get("label", "") or "",
                )
            )
            missing.remove(metric)
    return out
