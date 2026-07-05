"""Compatibility shim for the S-1 financial extraction package.

The implementation moved to `edgarpack.query.registration` (split into
`snapshot`, `table_parse`, `llm`, `integrate`). This module re-exports the
names other modules and tests still import from here. New code should import
from `edgarpack.query.registration.*` directly.
"""

from __future__ import annotations

from .registration.integrate import (
    augment_with_s1_snapshot,
    default_registration_query_metrics,
    has_registration_pack_for_cik,
    pick_snapshot_fact,
    snapshot_fact_to_cited_value,
    snapshots_for_cik,
)
from .registration.llm import (
    _MAX_OUTPUT_TOKENS,
    MODEL_ID,
    PROMPT_SYSTEM,
    MissingAnthropicKeyError,
    _call_haiku_extract,
    _gate_llm_facts,
    _s1_max_output_tokens,
    _s1_model_id,
    build_extraction_prompt,
    extract_or_load_snapshot,
    parse_llm_response,
    parse_llm_response_with_salvage,
)
from .registration.snapshot import (
    METRIC_SLUGS,
    SCHEMA_VERSION,
    SnapshotFact,
    SnapshotResult,
    load_validated_snapshot,
    source_sha256_for_pack,
)
from .registration.table_parse import (
    _detect_presentation_currency,
    _extract_summary_table_facts,
    _summary_period_from_context,
    find_financial_data_section,
)

__all__ = [
    "MODEL_ID",
    "METRIC_SLUGS",
    "PROMPT_SYSTEM",
    "SCHEMA_VERSION",
    "MissingAnthropicKeyError",
    "SnapshotFact",
    "SnapshotResult",
    "_MAX_OUTPUT_TOKENS",
    "_call_haiku_extract",
    "_detect_presentation_currency",
    "_extract_summary_table_facts",
    "_gate_llm_facts",
    "_s1_max_output_tokens",
    "_s1_model_id",
    "_summary_period_from_context",
    "augment_with_s1_snapshot",
    "build_extraction_prompt",
    "default_registration_query_metrics",
    "extract_or_load_snapshot",
    "find_financial_data_section",
    "has_registration_pack_for_cik",
    "load_validated_snapshot",
    "parse_llm_response",
    "parse_llm_response_with_salvage",
    "pick_snapshot_fact",
    "snapshot_fact_to_cited_value",
    "snapshots_for_cik",
    "source_sha256_for_pack",
]
