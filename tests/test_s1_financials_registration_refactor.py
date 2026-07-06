"""Guards for the registration-extraction package split (Phase 3 s1-structure).

Three behavior-preserving guards captured while `s1_financials.py` was split
into `edgarpack.query.registration.*`:

1. byte-equality of a deterministic snapshot's serialized JSON,
2. the `LlmFactRow` pydantic gate matches the former hand-rolled row gate
   (oracle) across a table-driven corpus,
3. a parity probe over the two snapshot pickers, pinning where they agree
   (single-pack) and the multi-pack / duplicate-period cases where they
   genuinely diverge (why unifying them is a deferred behavior decision).
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

from edgarpack.query.registration import integrate, llm
from edgarpack.query.registration.integrate import (
    _candidate_to_cited_value,
    _pick_snapshot_candidate,
    _SnapshotCandidate,
    pick_snapshot_fact,
)
from edgarpack.query.registration.llm import LlmFactRow, extract_or_load_snapshot
from edgarpack.query.registration.snapshot import METRIC_SLUGS, SnapshotFact

# --------------------------------------------------------------------------
# 1. Byte-equality of a deterministic snapshot's serialized JSON
# --------------------------------------------------------------------------

_BYTE_EQUALITY_MARKDOWN = (
    "\n Summary Consolidated Financial Data\n"
    " The following tables set forth our summary consolidated financial data.\n\n"
    "> 2025 / 2024\n"
    "> (in thousands, except per share amounts) / (in thousands, except per share amounts)\n"
    "> Consolidated Statement of Operations:\n"
    "> Total revenue ... $509,991 / $290,252\n"
    "> Net cash provided by (used in) operating activities ... $(10,050) / $451,978\n\n"
    "# Consolidated Statements of Cash Flows\n\n"
    "> Purchases of property and equipment ... (382,739) / (23,435)\n"
    "> Purchases of property and equipment included in accounts payable ... 9,453 / $4,286\n"
)

# The serialized SnapshotResult (minus the volatile `extracted_at` field) that
# the deterministic path produced before the package split. Any future refactor
# that changes these bytes must be deliberate.
_OCF_SRC = "Net cash provided by (used in) operating activities ... $(10,050) / $451,978"
_BYTE_EQUALITY_GOLDEN = {
    "schema_version": 9,
    "accession": "0001628280-26-025762",
    "extraction_status": "ok",
    "source_sha256": "7a1331fed32eeb7aeb66618e9a9b1fed6f4fa88e13b42294c5d5be3ba2c0c87c",
    "model": "deterministic-summary-table",
    "detail": None,
    "retry_after": None,
    "truncated": False,
    "gate_rejections": [],
    "facts": [
        {
            "accession": "0001628280-26-025762",
            "fiscal_year": 2025,
            "period_end": "",
            "metric": "revenue",
            "value_cents": 50999100000,
            "currency": "USD",
            "is_audited": True,
            "is_pro_forma": False,
            "pro_forma_note": None,
            "fiscal_period": "FY",
            "source_text": "Total revenue ... $509,991 / $290,252",
            "section_id": None,
            "chunk_id": None,
        },
        {
            "accession": "0001628280-26-025762",
            "fiscal_year": 2024,
            "period_end": "",
            "metric": "revenue",
            "value_cents": 29025200000,
            "currency": "USD",
            "is_audited": True,
            "is_pro_forma": False,
            "pro_forma_note": None,
            "fiscal_period": "FY",
            "source_text": "Total revenue ... $509,991 / $290,252",
            "section_id": None,
            "chunk_id": None,
        },
        {
            "accession": "0001628280-26-025762",
            "fiscal_year": 2025,
            "period_end": "",
            "metric": "operating_cash_flow",
            "value_cents": -1005000000,
            "currency": "USD",
            "is_audited": True,
            "is_pro_forma": False,
            "pro_forma_note": None,
            "fiscal_period": "FY",
            "source_text": _OCF_SRC,
            "section_id": None,
            "chunk_id": None,
        },
        {
            "accession": "0001628280-26-025762",
            "fiscal_year": 2024,
            "period_end": "",
            "metric": "operating_cash_flow",
            "value_cents": 45197800000,
            "currency": "USD",
            "is_audited": True,
            "is_pro_forma": False,
            "pro_forma_note": None,
            "fiscal_period": "FY",
            "source_text": _OCF_SRC,
            "section_id": None,
            "chunk_id": None,
        },
        {
            "accession": "0001628280-26-025762",
            "fiscal_year": 2025,
            "period_end": "",
            "metric": "capex",
            "value_cents": 38273900000,
            "currency": "USD",
            "is_audited": True,
            "is_pro_forma": False,
            "pro_forma_note": None,
            "fiscal_period": "FY",
            "source_text": "Purchases of property and equipment ... (382,739) / (23,435)",
            "section_id": None,
            "chunk_id": None,
        },
        {
            "accession": "0001628280-26-025762",
            "fiscal_year": 2024,
            "period_end": "",
            "metric": "capex",
            "value_cents": 2343500000,
            "currency": "USD",
            "is_audited": True,
            "is_pro_forma": False,
            "pro_forma_note": None,
            "fiscal_period": "FY",
            "source_text": "Purchases of property and equipment ... (382,739) / (23,435)",
            "section_id": None,
            "chunk_id": None,
        },
    ],
}


@pytest.mark.asyncio
async def test_deterministic_snapshot_serialization_is_byte_stable(tmp_path, monkeypatch):
    pack = tmp_path / "0001628280-26-025762"
    pack.mkdir(parents=True)
    (pack / "filing.full.md").write_text(_BYTE_EQUALITY_MARKDOWN, encoding="utf-8")
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "filing": {
                    "accession": "0001628280-26-025762",
                    "form_type": "S-1",
                    "filing_date": "2024-09-30",
                    "cik": "0002021728",
                    "company_name": "Cerebras Systems Inc",
                },
            }
        ),
        encoding="utf-8",
    )

    async def empty_llm(_section):
        return "[]"

    monkeypatch.setattr("edgarpack.query.registration.llm._call_haiku_extract", empty_llm)

    result = await extract_or_load_snapshot(pack, force=True)
    payload = json.loads(result.to_json())
    del payload["extracted_at"]
    assert payload == _BYTE_EQUALITY_GOLDEN


# --------------------------------------------------------------------------
# 2. LlmFactRow pydantic gate == former hand-rolled row gate (oracle)
# --------------------------------------------------------------------------

# The oracle is the pre-refactor per-row acceptance logic, copied verbatim from
# the old parse_llm_response loop. It is the source of truth the pydantic model
# must match exactly.
_ORACLE_REQUIRED_KEYS = (
    "fiscal_year",
    "period_end",
    "metric",
    "value_cents",
    "currency",
    "is_audited",
    "is_pro_forma",
    "source_text",
)
_ORACLE_ACCEPTED_CURRENCIES = frozenset(
    {"USD", "EUR", "GBP", "JPY", "CNY", "HKD", "SEK", "CHF", "CAD", "AUD", "SGD"}
)


def _oracle_has_period_context(row):
    fiscal_period = str(row.get("fiscal_period") or "FY").upper()
    period_end = str(row.get("period_end") or "")
    source_text = str(row.get("source_text") or "").lower()
    if fiscal_period != "FY":
        return True
    if period_end.endswith("-12-31"):
        return True
    annual_markers = ("year ended", "fiscal year", "annual")
    return any(marker in source_text for marker in annual_markers)


def _oracle_has_metric_context(row):
    metric = str(row.get("metric") or "")
    source_text = str(row.get("source_text") or "").lower()
    if metric == "net_income_loss" and "attributable to" in source_text:
        return False
    return True


def _oracle_accept(row, *, accession):
    if not isinstance(row, dict):
        return None
    if any(k not in row for k in _ORACLE_REQUIRED_KEYS):
        return None
    if row.get("metric") not in METRIC_SLUGS:
        return None
    if not _oracle_has_period_context(row):
        return None
    if not _oracle_has_metric_context(row):
        return None
    currency = str(row.get("currency") or "").strip().upper()
    if currency not in _ORACLE_ACCEPTED_CURRENCIES:
        return None
    try:
        return SnapshotFact(
            accession=accession,
            fiscal_year=int(row["fiscal_year"]),
            period_end=str(row["period_end"]),
            metric=str(row["metric"]),
            value_cents=int(row["value_cents"]),
            currency=currency,
            is_audited=bool(row["is_audited"]),
            is_pro_forma=bool(row["is_pro_forma"]),
            pro_forma_note=(
                str(row["pro_forma_note"]) if row.get("pro_forma_note") is not None else None
            ),
            fiscal_period=str(row.get("fiscal_period") or "FY"),
            source_text=(
                str(row["source_text"]).strip() if row.get("source_text") is not None else None
            ),
            section_id=(
                str(row["section_id"]).strip() if row.get("section_id") is not None else None
            ),
            chunk_id=(str(row["chunk_id"]).strip() if row.get("chunk_id") is not None else None),
        )
    except (ValueError, TypeError):
        return None


def _pydantic_accept(row, *, accession):
    from pydantic import ValidationError

    if not isinstance(row, dict):
        return None
    try:
        model = LlmFactRow.model_validate(row)
    except (ValidationError, ValueError, TypeError):
        return None
    return model.to_snapshot_fact(accession)


def _valid_row(**overrides):
    row = {
        "fiscal_year": 2024,
        "period_end": "2024-12-31",
        "metric": "revenue",
        "value_cents": 100,
        "currency": "USD",
        "is_audited": True,
        "is_pro_forma": False,
        "source_text": "Total revenue ... $100",
    }
    row.update(overrides)
    return row


def _drop(key):
    row = _valid_row()
    del row[key]
    return row


_GATE_CORPUS = [
    _valid_row(),
    _valid_row(metric="net_income_loss", value_cents=-500, source_text="Net loss ... (500)"),
    _valid_row(fiscal_period="Q1", period_end="2024-03-31", source_text="Three months ended"),
    _valid_row(period_end="2024-06-30", source_text="Year ended June 30, 2024 revenue"),
    _drop("fiscal_year"),
    _drop("period_end"),
    _drop("metric"),
    _drop("value_cents"),
    _drop("currency"),
    _drop("is_audited"),
    _drop("is_pro_forma"),
    _drop("source_text"),
    _valid_row(value_cents="not-a-number"),
    _valid_row(fiscal_year=None),
    _valid_row(value_cents=True),
    _valid_row(fiscal_year=False),
    _valid_row(value_cents=1.9),
    _valid_row(metric="not_a_slug"),
    _valid_row(currency="XYZ"),
    _valid_row(currency="usd"),
    _valid_row(currency=" eur "),
    _valid_row(
        metric="net_income_loss",
        source_text="Net income attributable to shareholders ... (137)",
    ),
    _valid_row(period_end="2024-06-30", source_text="as of June 30, 2024"),
    _valid_row(is_pro_forma=True, pro_forma_note="assuming the offering"),
    _valid_row(section_id="sec-3", chunk_id="chunk-9"),
    _valid_row(source_text=None, metric="revenue"),
]


@pytest.mark.parametrize("row", _GATE_CORPUS)
def test_llm_fact_row_matches_oracle_gate(row):
    accession = "0001628280-24-041596"
    assert _pydantic_accept(row, accession=accession) == _oracle_accept(row, accession=accession)


# --------------------------------------------------------------------------
# 3. Snapshot picker parity probe (unification deferred: they diverge)
# --------------------------------------------------------------------------


def _cand(fact, filing_date, form="S-1"):
    return _SnapshotCandidate(fact=fact, filing_date=filing_date, form_type=form)


_ONE_DAY = date(2024, 9, 30)

# Single pack, distinct (fiscal_year, period_end) per row: the domain the public
# `pick_snapshot_fact` is actually called with. The two pickers must agree here,
# because the shim's `pick_snapshot_fact` and production's candidate picker both
# resolve real snapshots from this shape.
_SINGLE_PACK_FACTS = [
    SnapshotFact("a", 2023, "2023-12-31", "revenue", 100, "USD", True, False, None),
    SnapshotFact("a", 2024, "2024-12-31", "revenue", 200, "USD", True, False, None),
    SnapshotFact("a", 2025, "2025-03-31", "revenue", 130, "USD", False, False, None, "Q1"),
    SnapshotFact("a", 2024, "2024-12-31", "revenue", 999, "USD", False, True, "assume"),
]
_SINGLE_PACK_CANDS = [_cand(f, _ONE_DAY) for f in _SINGLE_PACK_FACTS]


@pytest.mark.parametrize("period", ["lfy", "lfy-1", "lfy-2", "mrp", "pro-forma"])
def test_pickers_agree_on_single_pack(period):
    by_fact = pick_snapshot_fact(_SINGLE_PACK_FACTS, metric="revenue", period=period)
    by_cand = _pick_snapshot_candidate(_SINGLE_PACK_CANDS, metric="revenue", period=period)
    assert by_fact == (by_cand.fact if by_cand is not None else None)


def test_pickers_agree_on_supersession():
    # Unified 2026-07-05: production semantics won. With filing dates, the
    # newer filing's value supersedes; without them, the wrapper tie-breaks
    # identical periods by accession, descending, deterministically.
    facts = [
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 200, "USD", True, False, None),
        SnapshotFact("b", 2024, "2024-12-31", "revenue", 210, "USD", True, False, None),
    ]
    cands = [_cand(facts[0], date(2024, 1, 1)), _cand(facts[1], date(2024, 6, 1))]
    by_fact = pick_snapshot_fact(facts, metric="revenue", period="lfy")
    by_cand = _pick_snapshot_candidate(cands, metric="revenue", period="lfy")
    assert by_fact is not None and by_cand is not None
    assert by_fact.value_cents == 210
    assert by_cand.fact.value_cents == 210


def test_pickers_agree_on_duplicate_period_lfy_offset():
    # Unified 2026-07-05: duplicate (fiscal_year, period_end) audited rows
    # dedupe before offset indexing on both paths, so lfy-1 means the prior
    # fiscal year, never a same-year duplicate row.
    facts = [
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 200, "USD", True, False, None),
        SnapshotFact("a", 2024, "2024-12-31", "revenue", 201, "USD", True, False, None),
        SnapshotFact("a", 2023, "2023-12-31", "revenue", 100, "USD", True, False, None),
    ]
    cands = [_cand(f, _ONE_DAY) for f in facts]
    by_fact = pick_snapshot_fact(facts, metric="revenue", period="lfy-1")
    by_cand = _pick_snapshot_candidate(cands, metric="revenue", period="lfy-1")
    assert by_fact is not None and by_fact.value_cents == 100
    assert by_cand is not None and by_cand.fact.value_cents == 100


def test_integrate_module_exposes_both_pickers():
    # pick_snapshot_fact is the public single-pack wrapper over the candidate
    # picker; both names stay importable.
    assert hasattr(integrate, "pick_snapshot_fact")
    assert hasattr(integrate, "_pick_snapshot_candidate")


def test_llm_module_orchestrator_is_patchable_at_source():
    # Guard the monkeypatch contract downstream tests rely on: the extraction
    # orchestrator lives in llm and calls the module-local haiku entry point.
    assert asyncio.iscoroutinefunction(llm._call_haiku_extract)
    assert asyncio.iscoroutinefunction(llm.extract_or_load_snapshot)


def test_snapshot_candidate_without_filing_date_keeps_filed_absent():
    fact = SnapshotFact(
        accession="0001628280-26-025762",
        fiscal_year=2025,
        period_end="",
        metric="revenue",
        value_cents=509_991_000_00,
        currency="USD",
        is_audited=True,
        is_pro_forma=False,
        pro_forma_note=None,
    )
    candidate = _SnapshotCandidate(fact=fact, filing_date=date.min, form_type="S-1")

    value = _candidate_to_cited_value(
        candidate,
        public_metric="revenue",
        cik="0002021728",
        company="Cerebras Systems Inc.",
        form_type="S-1",
        filed=None,
    )

    assert value.filed is None
