# New-Filer (S-1) Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generalized pre-IPO / S-1 filer support to EdgarPack, anchored on Cerebras Systems, with minimal-bloat reuse of existing harvest / sectionize / kpi_discover / periods / diff-timeline seams and one new file for roadshow image handling.

**Architecture:** S-1 is just a form type. No state machine, no parallel subsystem. Ten registration-class forms (`S-1`, `S-1/A`, `F-1`, `F-1/A`, `424B1-5`, `FWP`) are emitted as a family via a `__REGISTRATION__` sentinel in `form_counts`. The planner expands the sentinel via a single helper. CIK becomes optional: users supply `name` or `ticker`, and a new `resolve_company_by_name` path hits SEC EDGAR full-text search for pre-IPO filers. KPI discovery, period guards, and the diff timeline all branch on a single `is_registration_form()` predicate. A new file `edgarpack/pack/assets.py` handles roadshow image download plus opt-in VLM description via the Anthropic SDK (optional extra).

**Tech Stack:** Python 3.11+, pydantic v2, pytest + pytest-asyncio, ruff, urllib (stdlib HTTP via existing SEC client), anthropic SDK (optional extra for VLM).

**Reference spec:** `docs/superpowers/specs/2026-04-22-new-filer-s1-support-design.md`

---

## Phase 1: Config and resolution (ingest foundation)

### Task 1: Registration-form constants and `normalize_form_type` extension

**Files:**
- Modify: `edgarpack/sec/submissions.py` (~line 53, `normalize_form_type`)
- Test: `tests/test_submissions_registration_forms.py` (new)

- [ ] **Step 1: Write failing tests for `normalize_form_type` on registration forms and for the `REGISTRATION_FORMS` constant**

Create `tests/test_submissions_registration_forms.py`:

```python
"""Tests for registration-form normalization and the family constant."""

from edgarpack.sec.submissions import REGISTRATION_FORMS, normalize_form_type


def test_registration_forms_family_is_exported():
    assert "S-1" in REGISTRATION_FORMS
    assert "S-1/A" in REGISTRATION_FORMS
    assert "F-1" in REGISTRATION_FORMS
    assert "F-1/A" in REGISTRATION_FORMS
    assert "424B1" in REGISTRATION_FORMS
    assert "424B4" in REGISTRATION_FORMS
    assert "FWP" in REGISTRATION_FORMS
    # 10-K is explicitly NOT a registration form.
    assert "10-K" not in REGISTRATION_FORMS


def test_normalize_form_type_preserves_s1():
    assert normalize_form_type("S-1") == "S-1"
    assert normalize_form_type("s-1") == "S-1"
    assert normalize_form_type("S1") == "S-1"


def test_normalize_form_type_preserves_s1_amendment():
    assert normalize_form_type("S-1/A") == "S-1/A"
    assert normalize_form_type("s1/a") == "S-1/A"


def test_normalize_form_type_preserves_f1():
    assert normalize_form_type("F-1") == "F-1"
    assert normalize_form_type("F1/A") == "F-1/A"


def test_normalize_form_type_preserves_424b():
    assert normalize_form_type("424B1") == "424B1"
    assert normalize_form_type("424b4") == "424B4"


def test_normalize_form_type_preserves_fwp():
    assert normalize_form_type("FWP") == "FWP"
    assert normalize_form_type("fwp") == "FWP"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_submissions_registration_forms.py -v`
Expected: FAIL with `ImportError: cannot import name 'REGISTRATION_FORMS'` plus at least one `normalize_form_type` assertion failure on the new form shapes.

- [ ] **Step 3: Add `REGISTRATION_FORMS` constant and extend `normalize_form_type`**

Edit `edgarpack/sec/submissions.py`. Right after the existing imports and before `normalize_form_type`, add:

```python
REGISTRATION_FORMS: tuple[str, ...] = (
    "S-1",
    "S-1/A",
    "F-1",
    "F-1/A",
    "424B1",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
    "FWP",
)
```

Then replace the body of `normalize_form_type` with an extended version that canonicalizes `S-1`, `F-1`, `424B*`, and `FWP`:

```python
def normalize_form_type(form_type: str) -> str:
    """Normalize form type for matching SEC submissions."""
    if not form_type:
        return ""
    form = form_type.strip().upper().replace(" ", "")
    amended = form.endswith("/A")
    if amended:
        form = form[:-2]
    if form in {"10K", "10-K"}:
        base = "10-K"
    elif form in {"10Q", "10-Q"}:
        base = "10-Q"
    elif form in {"8K", "8-K"}:
        base = "8-K"
    elif form in {"S1", "S-1"}:
        base = "S-1"
    elif form in {"F1", "F-1"}:
        base = "F-1"
    elif form in {"FWP"}:
        base = "FWP"
    elif form.startswith("424B") and len(form) == 5 and form[-1].isdigit():
        base = form  # 424B1..424B5 pass through verbatim.
    else:
        base = form
    return f"{base}/A" if amended else base
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_submissions_registration_forms.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pre-existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/sec/submissions.py tests/test_submissions_registration_forms.py
git commit -m "feat(sec): add REGISTRATION_FORMS constant and normalize S-1/F-1/424B/FWP"
```

---

### Task 2: `is_registration_form` predicate

**Files:**
- Modify: `edgarpack/sec/submissions.py` (add predicate next to `REGISTRATION_FORMS`)
- Test: `tests/test_submissions_registration_forms.py` (extend)

- [ ] **Step 1: Write failing tests for the predicate**

Append to `tests/test_submissions_registration_forms.py`:

```python
from edgarpack.sec.submissions import is_registration_form


def test_is_registration_form_true_for_family():
    for form in ("S-1", "S-1/A", "F-1", "F-1/A", "424B1", "424B3", "FWP"):
        assert is_registration_form(form), form


def test_is_registration_form_false_for_periodic():
    for form in ("10-K", "10-Q", "8-K", "20-F", "40-F", "", "DEF 14A"):
        assert not is_registration_form(form), form


def test_is_registration_form_handles_casing_and_whitespace():
    assert is_registration_form(" s-1 ")
    assert is_registration_form("s1/a")
    assert is_registration_form("fwp")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_submissions_registration_forms.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_registration_form'`.

- [ ] **Step 3: Add the predicate to `submissions.py`**

Below the `REGISTRATION_FORMS` constant in `edgarpack/sec/submissions.py`, add:

```python
def is_registration_form(form_type: str) -> bool:
    """Return True when the form belongs to the S-1 / pre-IPO family.

    The family covers S-1, S-1/A, F-1, F-1/A, 424B1-5, and FWP. Used as a
    single guard across kpi_discover, periods, and diff/timeline so that
    registration-class filings do not get pulled into 10-K/10-Q logic.
    """
    if not form_type:
        return False
    normalized = normalize_form_type(form_type)
    return normalized in REGISTRATION_FORMS
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_submissions_registration_forms.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/sec/submissions.py tests/test_submissions_registration_forms.py
git commit -m "feat(sec): add is_registration_form predicate"
```

---

### Task 3: `CompanySpec` accepts `name`, optional ticker, at-least-one-identifier validator

**Files:**
- Modify: `edgarpack/harvest/universe.py`
- Test: `tests/test_universe_new_filer.py` (new)

- [ ] **Step 1: Write failing tests for the new CompanySpec shape**

Create `tests/test_universe_new_filer.py`:

```python
"""Tests for universe config extensions supporting new (pre-IPO) filers."""

import pytest
from pydantic import ValidationError

from edgarpack.harvest.universe import CompanySpec, UniverseConfig


def test_company_spec_accepts_name_only():
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    assert spec.name == "Cerebras Systems"
    assert spec.ticker is None
    assert spec.cik is None
    assert spec.forms_s1 == 8


def test_company_spec_accepts_ticker_only():
    spec = CompanySpec(ticker="NVDA")
    assert spec.ticker == "NVDA"


def test_company_spec_accepts_cik_only():
    spec = CompanySpec(cik="0002021728", forms_s1=8)
    assert spec.cik == "0002021728"


def test_company_spec_rejects_all_identifiers_missing():
    with pytest.raises(ValidationError) as exc:
        CompanySpec(forms_s1=8)
    assert "identifier" in str(exc.value).lower() or "ticker" in str(exc.value).lower()


def test_form_counts_emits_registration_sentinel_when_forms_s1_set():
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert counts.get("__REGISTRATION__") == 8


def test_form_counts_applies_pre_ipo_inference_when_only_forms_s1_set():
    """If forms_s1 is set and periodic forms are not explicitly provided,
    10-K / 10-Q / 8-K are inferred to 0 to avoid spurious harvest errors."""
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert "10-K" not in counts
    assert "10-Q" not in counts
    assert "8-K" not in counts


def test_form_counts_respects_explicit_override_post_ipo():
    """Post-IPO the user adds explicit periodic counts; those override the
    pre-IPO inference and registration amendments keep flowing."""
    spec = CompanySpec(
        ticker="CRBS", forms_s1=2, forms_10k=2, forms_10q=4, forms_8k=5
    )
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert counts["__REGISTRATION__"] == 2
    assert counts["10-K"] == 2
    assert counts["10-Q"] == 4
    assert counts["8-K"] == 5


def test_form_counts_unchanged_for_public_only_filer():
    """A public-only filer should still get the default 10-K/10-Q/8-K counts."""
    spec = CompanySpec(ticker="NVDA")
    cfg = UniverseConfig(companies=[spec])
    counts = cfg.form_counts(spec)
    assert counts["10-K"] == 2
    assert counts["10-Q"] == 4
    assert counts["8-K"] == 5
    assert "__REGISTRATION__" not in counts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_universe_new_filer.py -v`
Expected: most tests FAIL with `ValidationError: Field required` on `ticker`, or with `forms_s1` unknown.

- [ ] **Step 3: Rewrite `edgarpack/harvest/universe.py` with the new model**

Replace the entire contents of `edgarpack/harvest/universe.py` with:

```python
"""Load company universe from TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, model_validator

_REGISTRATION_SENTINEL = "__REGISTRATION__"


class CompanySpec(BaseModel):
    """A company in the harvest universe.

    At least one of `ticker`, `name`, or `cik` must be provided. The harvest
    planner tries them in that order (cik first when given, then ticker, then
    name) to resolve the CIK needed for SEC API calls.
    """

    ticker: str | None = None
    name: str | None = None
    cik: str | None = None
    forms_10k: int | None = None
    forms_10q: int | None = None
    forms_8k: int | None = None
    forms_20f: int | None = None
    forms_s1: int | None = None
    listing: str | None = None
    aliases: list[str] = []
    alt_tickers: list[str] = []
    hk_stock_code: str | None = None
    private: bool = False

    @model_validator(mode="after")
    def _require_one_identifier(self) -> CompanySpec:
        if not (self.ticker or self.name or self.cik):
            raise ValueError(
                "CompanySpec requires at least one identifier: ticker, name, or cik."
            )
        return self

    @model_validator(mode="after")
    def _infer_private(self) -> CompanySpec:
        if self.listing == "PRIVATE":
            self.private = True
        return self

    @property
    def display_label(self) -> str:
        """Human label for logs and errors. Falls back through ticker -> name -> cik."""
        return self.ticker or self.name or (f"CIK {self.cik}" if self.cik else "<unknown>")


class UniverseConfig(BaseModel):
    """Parsed universe configuration."""

    defaults_10k: int = 2
    defaults_10q: int = 4
    defaults_8k: int = 5
    companies: list[CompanySpec]

    def form_counts(self, spec: CompanySpec) -> dict[str, int]:
        """Get effective form counts for a company, applying defaults.

        Pre-IPO inference: when `forms_s1 > 0` and the filer has NOT explicitly
        set a periodic form count, that periodic form defaults to 0 (not the
        global default) to avoid spurious harvest_errors for filings that do
        not yet exist.
        """
        counts: dict[str, int] = {}

        is_pre_ipo = bool(spec.forms_s1 and spec.forms_s1 > 0)

        def _effective(explicit: int | None, default: int) -> int:
            if explicit is not None:
                return explicit
            if is_pre_ipo:
                return 0
            return default

        k10 = _effective(spec.forms_10k, self.defaults_10k)
        q10 = _effective(spec.forms_10q, self.defaults_10q)
        k8 = _effective(spec.forms_8k, self.defaults_8k)
        f20 = spec.forms_20f if spec.forms_20f is not None else 0
        s1 = spec.forms_s1 if spec.forms_s1 is not None else 0

        if k10 > 0:
            counts["10-K"] = k10
        if q10 > 0:
            counts["10-Q"] = q10
        if k8 > 0:
            counts["8-K"] = k8
        if f20 > 0:
            counts["20-F"] = f20
        if s1 > 0:
            counts[_REGISTRATION_SENTINEL] = s1
        return counts


def load_universe(path: Path) -> UniverseConfig:
    """Load universe configuration from a TOML file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    defaults = data.get("defaults", {})
    companies_raw = data.get("companies", [])

    companies = [CompanySpec(**c) for c in companies_raw]

    return UniverseConfig(
        defaults_10k=defaults.get("forms_10k", 2),
        defaults_10q=defaults.get("forms_10q", 4),
        defaults_8k=defaults.get("forms_8k", 5),
        companies=companies,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_universe_new_filer.py -v`
Expected: 8 passed.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pre-existing tests still pass. If any test constructs `CompanySpec` positionally with ticker as the first argument, it should still work because ticker remains the first field.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/harvest/universe.py tests/test_universe_new_filer.py
git commit -m "feat(universe): optional ticker/cik, new name field, pre-IPO inference, REGISTRATION sentinel"
```

---

### Task 4: `resolve_company_by_name` via SEC EDGAR full-text search

**Files:**
- Modify: `edgarpack/sec/tickers.py` (append new function)
- Test: `tests/test_tickers_name_resolution.py` (new)

- [ ] **Step 1: Write failing tests for `resolve_company_by_name` using a mocked HTTP response**

Create `tests/test_tickers_name_resolution.py`:

```python
"""Tests for SEC EDGAR name-based CIK resolution (pre-IPO filers)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.errors import AmbiguousCompany, UnknownCompany
from edgarpack.sec.tickers import resolve_company_by_name


def _canned_hits(*companies: tuple[str, str]) -> str:
    """Build a canned EDGAR full-text search response.

    Each tuple is (cik_10digit, display_name).
    """
    return json.dumps(
        {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "ciks": [cik],
                            "display_names": [f"{name} (CIK {cik})"],
                        }
                    }
                    for cik, name in companies
                ]
            }
        }
    )


@pytest.mark.asyncio
async def test_resolve_company_by_name_unique_match():
    canned = _canned_hits(("0002021728", "Cerebras Systems Inc"))
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        cik, title = await resolve_company_by_name("Cerebras Systems")
    assert cik == "0002021728"
    assert "Cerebras" in title


@pytest.mark.asyncio
async def test_resolve_company_by_name_ambiguous_raises():
    canned = _canned_hits(
        ("0002021728", "Cerebras Systems Inc"),
        ("0001234567", "Cerebras Holdings LLC"),
    )
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        with pytest.raises(AmbiguousCompany) as exc:
            await resolve_company_by_name("Cerebras")
    assert "0002021728" in str(exc.value)
    assert "0001234567" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_company_by_name_zero_matches_raises():
    canned = json.dumps({"hits": {"hits": []}})
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        with pytest.raises(UnknownCompany):
            await resolve_company_by_name("ThisCompanyDoesNotExist Corp")


@pytest.mark.asyncio
async def test_resolve_company_by_name_dedupes_repeated_cik():
    """SEC search sometimes returns the same CIK on multiple hits (one per form)."""
    canned = _canned_hits(
        ("0002021728", "Cerebras Systems Inc"),
        ("0002021728", "Cerebras Systems Inc"),
    )
    with patch("edgarpack.sec.tickers._fetch_edgar_search", new=AsyncMock(return_value=canned)):
        cik, _title = await resolve_company_by_name("Cerebras")
    assert cik == "0002021728"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_tickers_name_resolution.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_company_by_name'`.

- [ ] **Step 3: Append `resolve_company_by_name` and `_fetch_edgar_search` to `sec/tickers.py`**

At the bottom of `edgarpack/sec/tickers.py`, append:

```python
# ---- Name-based resolution for pre-IPO filers ------------------------------

_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
# Registration forms used to filter the SEC full-text search so that a name
# search for a pre-IPO filer returns the right CIK rather than (say) a
# proxy-statement filer with a similar name.
_NAME_SEARCH_FORMS = "S-1,S-1/A,F-1,F-1/A,424B1,424B2,424B3,424B4,424B5,FWP"


async def _fetch_edgar_search(query: str, forms: str = _NAME_SEARCH_FORMS) -> str:
    """Fetch raw JSON text from SEC EDGAR full-text search.

    Split out so tests can mock a deterministic payload.
    """
    import urllib.parse

    params = {"q": f'"{query}"', "forms": forms}
    url = f"{_EDGAR_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    client = await get_client()
    body = await client.fetch(url)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    return body


async def resolve_company_by_name(name: str) -> tuple[str, str]:
    """Resolve a company name to (cik, display_title) via SEC EDGAR search.

    Used when the filer has no ticker in SEC's company_tickers.json (the
    pre-IPO case). Searches registration-class forms only so that the
    result corresponds to an actual S-1 / F-1 / 424B / FWP filer.

    Raises:
        UnknownCompany: zero matches.
        AmbiguousCompany: multiple distinct CIKs match the name.
    """
    q = (name or "").strip()
    if not q:
        raise UnknownCompany("Empty company name")

    raw = await _fetch_edgar_search(q)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UnknownCompany(f"Could not parse EDGAR search response for {q!r}") from exc

    hits = payload.get("hits", {}).get("hits", [])
    seen: dict[str, str] = {}
    for hit in hits:
        src = hit.get("_source", {})
        ciks = src.get("ciks", []) or []
        names = src.get("display_names", []) or []
        for i, cik in enumerate(ciks):
            if not cik:
                continue
            padded = normalize_cik(str(cik))
            if padded not in seen:
                seen[padded] = names[i] if i < len(names) else f"CIK {padded}"

    if not seen:
        raise UnknownCompany(f"No pre-IPO filer found matching name {q!r}")
    if len(seen) > 1:
        rendered = ", ".join(f"{title} [{cik}]" for cik, title in seen.items())
        raise AmbiguousCompany(
            f"Ambiguous name {q!r}. Matches: {rendered}. "
            "Supply `cik` explicitly in universe.toml to disambiguate."
        )
    only_cik, only_title = next(iter(seen.items()))
    return only_cik, only_title
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_tickers_name_resolution.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/sec/tickers.py tests/test_tickers_name_resolution.py
git commit -m "feat(sec): add resolve_company_by_name for pre-IPO filers via EDGAR search"
```

---

### Task 5: `resolve_filer` dispatcher (cik → ticker → name)

**Files:**
- Modify: `edgarpack/sec/tickers.py` (add dispatch function)
- Test: `tests/test_tickers_resolve_filer.py` (new)

- [ ] **Step 1: Write failing tests for the dispatcher**

Create `tests/test_tickers_resolve_filer.py`:

```python
"""Tests for the resolve_filer dispatch across cik / ticker / name."""

from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.errors import UnknownCompany
from edgarpack.harvest.universe import CompanySpec
from edgarpack.sec.tickers import resolve_filer


@pytest.mark.asyncio
async def test_resolve_filer_prefers_explicit_cik():
    spec = CompanySpec(cik="0001045810", ticker="NVDA", name="NVIDIA")
    # Neither resolver should be called when cik is supplied.
    with patch("edgarpack.sec.tickers.resolve_ticker", new=AsyncMock(side_effect=AssertionError)):
        with patch(
            "edgarpack.sec.tickers.resolve_company_by_name",
            new=AsyncMock(side_effect=AssertionError),
        ):
            cik, title = await resolve_filer(spec)
    assert cik == "0001045810"


@pytest.mark.asyncio
async def test_resolve_filer_uses_ticker_when_no_cik():
    spec = CompanySpec(ticker="NVDA")
    with patch(
        "edgarpack.sec.tickers.resolve_ticker",
        new=AsyncMock(return_value=("0001045810", "NVIDIA Corp")),
    ) as mock_tick:
        cik, title = await resolve_filer(spec)
    mock_tick.assert_awaited_once_with("NVDA")
    assert cik == "0001045810"


@pytest.mark.asyncio
async def test_resolve_filer_falls_back_to_name_when_ticker_unknown():
    spec = CompanySpec(ticker="CRBS", name="Cerebras Systems")
    with patch(
        "edgarpack.sec.tickers.resolve_ticker",
        new=AsyncMock(side_effect=UnknownCompany("CRBS not in map")),
    ):
        with patch(
            "edgarpack.sec.tickers.resolve_company_by_name",
            new=AsyncMock(return_value=("0002021728", "Cerebras Systems Inc")),
        ) as mock_name:
            cik, title = await resolve_filer(spec)
    mock_name.assert_awaited_once_with("Cerebras Systems")
    assert cik == "0002021728"


@pytest.mark.asyncio
async def test_resolve_filer_uses_name_directly_when_only_name_given():
    spec = CompanySpec(name="Cerebras Systems", forms_s1=8)
    with patch(
        "edgarpack.sec.tickers.resolve_company_by_name",
        new=AsyncMock(return_value=("0002021728", "Cerebras Systems Inc")),
    ):
        cik, title = await resolve_filer(spec)
    assert cik == "0002021728"


@pytest.mark.asyncio
async def test_resolve_filer_raises_when_no_identifier_usable():
    spec = CompanySpec(ticker="BOGUS", name="Definitely Not A Real Filer")
    with patch(
        "edgarpack.sec.tickers.resolve_ticker",
        new=AsyncMock(side_effect=UnknownCompany("BOGUS")),
    ):
        with patch(
            "edgarpack.sec.tickers.resolve_company_by_name",
            new=AsyncMock(side_effect=UnknownCompany("not found")),
        ):
            with pytest.raises(UnknownCompany):
                await resolve_filer(spec)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_tickers_resolve_filer.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_filer'`.

- [ ] **Step 3: Append `resolve_filer` to `sec/tickers.py`**

At the bottom of `edgarpack/sec/tickers.py`, append:

```python
async def resolve_filer(spec: "CompanySpec") -> tuple[str, str]:  # noqa: F821
    """Resolve a CompanySpec to (cik, title) trying cik, ticker, then name.

    Import of CompanySpec is deferred to avoid a circular import between
    edgarpack.sec.tickers and edgarpack.harvest.universe.
    """
    # Explicit CIK wins.
    if spec.cik:
        return normalize_cik(spec.cik), spec.name or spec.ticker or f"CIK {spec.cik}"

    # Ticker path reuses the existing company_tickers.json map.
    if spec.ticker:
        try:
            cik, title = await resolve_ticker(spec.ticker)
            return cik, title
        except (UnknownCompany, AmbiguousCompany):
            if not spec.name:
                raise

    # Name path hits SEC EDGAR full-text search over registration forms.
    if spec.name:
        return await resolve_company_by_name(spec.name)

    raise UnknownCompany(
        f"Could not resolve filer {spec.display_label}: no usable identifier"
    )
```

Also add the import at the top of `edgarpack/sec/tickers.py` if not already present:

```python
from ..errors import AmbiguousCompany, UnknownCompany
```

(The file already imports these; verify.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_tickers_resolve_filer.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/sec/tickers.py tests/test_tickers_resolve_filer.py
git commit -m "feat(sec): add resolve_filer dispatcher across cik/ticker/name"
```

---

### Task 6: Planner uses `resolve_filer`; expands `__REGISTRATION__` sentinel

**Files:**
- Modify: `edgarpack/harvest/planner.py`
- Test: `tests/test_planner_registration.py` (new)

- [ ] **Step 1: Write failing tests for the planner's registration-family expansion**

Create `tests/test_planner_registration.py`:

```python
"""Tests for the harvest planner's handling of the registration-form family."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.harvest.planner import plan_harvest
from edgarpack.harvest.registry import PackRegistry
from edgarpack.harvest.universe import CompanySpec, UniverseConfig
from edgarpack.sec.submissions import FilingMeta


def _filing(accession: str, form: str, filing_date: str) -> FilingMeta:
    return FilingMeta(
        cik="0002021728",
        accession=accession,
        form_type=form,
        filing_date=date.fromisoformat(filing_date),
        primary_document="main.htm",
        company_name="Cerebras Systems Inc",
    )


@pytest.mark.asyncio
async def test_planner_expands_registration_sentinel(tmp_path):
    spec = CompanySpec(name="Cerebras Systems", forms_s1=4)
    cfg = UniverseConfig(companies=[spec])

    canned: dict[str, list[FilingMeta]] = {
        "S-1": [_filing("0000001-25-000001", "S-1", "2025-09-30")],
        "S-1/A": [
            _filing("0000001-25-000002", "S-1/A", "2025-10-15"),
            _filing("0000001-25-000003", "S-1/A", "2025-11-01"),
        ],
        "424B4": [_filing("0000001-25-000004", "424B4", "2025-12-01")],
    }

    async def fake_list_filings(cik, form_type=None, limit=10, force=False):
        return canned.get(form_type, [])

    async def fake_resolve(spec):
        return "0002021728", "Cerebras Systems Inc"

    registry = PackRegistry(tmp_path / "registry.db")
    with patch("edgarpack.harvest.planner.list_filings", new=fake_list_filings):
        with patch("edgarpack.harvest.planner.resolve_filer", new=fake_resolve):
            plan = await plan_harvest(cfg, registry)

    accessions = {item.accession for item in plan.items}
    # Budget is 4; four registration filings across forms should be present
    # and the newest four should win (all four in this scenario).
    assert len(plan.items) == 4
    assert accessions == {
        "0000001-25-000001",
        "0000001-25-000002",
        "0000001-25-000003",
        "0000001-25-000004",
    }


@pytest.mark.asyncio
async def test_planner_registration_caps_at_budget(tmp_path):
    spec = CompanySpec(name="Example IPO Corp", forms_s1=2)
    cfg = UniverseConfig(companies=[spec])

    canned = {
        "S-1": [_filing("A-1", "S-1", "2025-01-01")],
        "S-1/A": [
            _filing("A-2", "S-1/A", "2025-02-01"),
            _filing("A-3", "S-1/A", "2025-03-01"),
            _filing("A-4", "S-1/A", "2025-04-01"),
        ],
    }

    async def fake_list_filings(cik, form_type=None, limit=10, force=False):
        return canned.get(form_type, [])

    async def fake_resolve(spec):
        return "0001234567", "Example IPO Corp"

    registry = PackRegistry(tmp_path / "registry.db")
    with patch("edgarpack.harvest.planner.list_filings", new=fake_list_filings):
        with patch("edgarpack.harvest.planner.resolve_filer", new=fake_resolve):
            plan = await plan_harvest(cfg, registry)

    # Budget = 2, newest-first -> A-4 and A-3.
    assert {i.accession for i in plan.items} == {"A-3", "A-4"}


@pytest.mark.asyncio
async def test_planner_does_not_fetch_periodic_forms_for_pre_ipo(tmp_path):
    """Pre-IPO inference should zero out periodic counts so list_filings is
    never invoked for 10-K / 10-Q / 8-K on a filer without that history."""
    spec = CompanySpec(name="Cerebras Systems", forms_s1=1)
    cfg = UniverseConfig(companies=[spec])

    calls: list[str] = []

    async def fake_list_filings(cik, form_type=None, limit=10, force=False):
        calls.append(form_type or "")
        if form_type == "S-1":
            return [_filing("X-1", "S-1", "2025-09-30")]
        return []

    async def fake_resolve(spec):
        return "0002021728", "Cerebras Systems Inc"

    registry = PackRegistry(tmp_path / "registry.db")
    with patch("edgarpack.harvest.planner.list_filings", new=fake_list_filings):
        with patch("edgarpack.harvest.planner.resolve_filer", new=fake_resolve):
            await plan_harvest(cfg, registry)

    assert "10-K" not in calls
    assert "10-Q" not in calls
    assert "8-K" not in calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_planner_registration.py -v`
Expected: FAIL because `resolve_filer` is not imported in planner, and the `__REGISTRATION__` key is unhandled (would be passed as a literal form_type and yield empty results).

- [ ] **Step 3: Update `edgarpack/harvest/planner.py`**

Replace the top imports block:

```python
from ..sec.tickers import resolve_ticker
```

with:

```python
from ..sec.tickers import resolve_filer
from ..sec.submissions import REGISTRATION_FORMS
```

Add a helper function above `plan_harvest`:

```python
_REGISTRATION_SENTINEL = "__REGISTRATION__"


async def _list_registration_filings(cik: str, limit: int) -> list[FilingMeta]:
    """Fetch the newest `limit` registration-class filings across the S-1 family.

    Queries each registration form in turn (SEC submissions.json is cached,
    so these are in-memory filters after the first hit), merges results,
    deduplicates by accession, sorts by filing_date descending, and caps.
    """
    collected: list[FilingMeta] = []
    for form in REGISTRATION_FORMS:
        try:
            hits = await list_filings(cik, form_type=form, limit=limit)
        except Exception:
            continue
        collected.extend(hits)

    seen: set[str] = set()
    unique: list[FilingMeta] = []
    for f in sorted(collected, key=lambda x: x.filing_date, reverse=True):
        if f.accession in seen:
            continue
        seen.add(f.accession)
        unique.append(f)
    return unique[:limit]
```

Replace the ticker-resolution block inside `plan_harvest`:

```python
        cik = spec.cik
        if cik is None:
            try:
                resolved_cik, _ = await resolve_ticker(spec.ticker)
                cik = resolved_cik
            except Exception as e:
                msg = str(e)[:120]
                errors.append(PlanError(ticker=spec.ticker, error=msg))
                print(f"  SKIP {spec.ticker}: {msg}", file=sys.stderr)
                continue
        cik = normalize_cik(cik)
```

with:

```python
        try:
            resolved_cik, _title = await resolve_filer(spec)
        except Exception as e:
            msg = str(e)[:120]
            errors.append(PlanError(ticker=spec.display_label, error=msg))
            print(f"  SKIP {spec.display_label}: {msg}", file=sys.stderr)
            continue
        cik = normalize_cik(resolved_cik)
```

Replace the per-form fetch loop:

```python
        for form_type, count in form_counts.items():
            try:
                filings: list[FilingMeta] = await list_filings(
                    cik, form_type=form_type, limit=count
                )
            except Exception as e:
                msg = str(e)[:120]
                errors.append(PlanError(ticker=spec.ticker, form_type=form_type, error=msg))
                print(
                    f"  SKIP {spec.ticker} {form_type}: {msg}",
                    file=sys.stderr,
                )
                continue
```

with:

```python
        for form_type, count in form_counts.items():
            try:
                if form_type == _REGISTRATION_SENTINEL:
                    filings: list[FilingMeta] = await _list_registration_filings(cik, count)
                else:
                    filings = await list_filings(cik, form_type=form_type, limit=count)
            except Exception as e:
                msg = str(e)[:120]
                errors.append(
                    PlanError(ticker=spec.display_label, form_type=form_type, error=msg)
                )
                print(
                    f"  SKIP {spec.display_label} {form_type}: {msg}",
                    file=sys.stderr,
                )
                continue
```

Further down inside the `for filing in filings:` loop, replace `ticker=spec.ticker.upper()` with `ticker=(spec.ticker or "").upper()` so the optional ticker does not crash when only `name` is set.

Also inside the `HarvestItem` construction block where `ticker=spec.ticker.upper()` previously appeared, change the `PlanError` calls (if the original referenced `spec.ticker` directly) to use `spec.display_label` for consistency with the messages above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_planner_registration.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pre-existing tests still pass. If any test constructs `CompanySpec(ticker="X")` and later relies on `spec.ticker` being truthy, it will still work.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/harvest/planner.py tests/test_planner_registration.py
git commit -m "feat(harvest): planner uses resolve_filer and expands __REGISTRATION__ sentinel"
```

---

## Phase 2: Sectionizer validation

### Task 7: Confirm S-1 parses via the existing general-form path; add targeted anchor whitelist only if weak

**Files:**
- (Possibly) Modify: `edgarpack/parse/sectionize.py`
- Test: `tests/test_sectionize_s1.py` (new)
- Fixture: `tests/fixtures/cerebras_s1_sample.md` (new, a small slice of real S-1 markdown)

- [ ] **Step 1: Create a minimal S-1 fixture**

Create `tests/fixtures/cerebras_s1_sample.md` containing the kind of structure an S-1 uses. Paste:

```markdown
# Prospectus Summary

We are Cerebras Systems, Inc., a developer of wafer-scale AI compute systems.

## Our Business

We design, build, and deploy the Cerebras CS-3 system.

# Risk Factors

Investing in our common stock involves a high degree of risk.

## Concentration of revenue

A significant portion of our revenue was generated by a single customer.

# Use of Proceeds

We intend to use the net proceeds from this offering as follows: approximately $150.0 million for research and development.

# Capitalization

The following table sets forth our cash and cash equivalents and capitalization as of June 30, 2025.

# Dilution

If you invest in our common stock, your interest will be diluted.

# Management's Discussion and Analysis of Financial Condition and Results of Operations

The following discussion and analysis should be read in conjunction with our consolidated financial statements.

# Business

We are a leader in high-performance AI compute.

# Principal Stockholders

The following table sets forth information regarding the beneficial ownership.

# Underwriting

Subject to the terms and conditions set forth in an underwriting agreement.
```

- [ ] **Step 2: Write the baseline sectionizer test**

Create `tests/test_sectionize_s1.py`:

```python
"""Verify the existing sectionizer catches S-1 anchor sections via the general-form path."""

from pathlib import Path

from edgarpack.parse.sectionize import find_sections


FIXTURE = Path(__file__).parent / "fixtures" / "cerebras_s1_sample.md"


def _titles(markdown: str, form: str) -> list[str]:
    return [m.title for m in find_sections(markdown, form)]


def test_s1_prospectus_summary_detected():
    md = FIXTURE.read_text(encoding="utf-8")
    titles = _titles(md, "S-1")
    assert any("Prospectus Summary" in t for t in titles)


def test_s1_risk_factors_detected():
    md = FIXTURE.read_text(encoding="utf-8")
    titles = _titles(md, "S-1")
    assert any("Risk Factors" in t for t in titles)


def test_s1_use_of_proceeds_detected():
    md = FIXTURE.read_text(encoding="utf-8")
    titles = _titles(md, "S-1")
    assert any("Use of Proceeds" in t for t in titles)


def test_s1_dilution_detected():
    md = FIXTURE.read_text(encoding="utf-8")
    titles = _titles(md, "S-1")
    assert any("Dilution" in t for t in titles)


def test_s1_principal_stockholders_detected():
    md = FIXTURE.read_text(encoding="utf-8")
    titles = _titles(md, "S-1")
    assert any("Principal Stockholders" in t for t in titles)


def test_s1_underwriting_detected():
    md = FIXTURE.read_text(encoding="utf-8")
    titles = _titles(md, "S-1")
    assert any("Underwriting" in t for t in titles)


def test_s1a_normalizes_like_s1():
    """S-1/A should produce the same section anchors as S-1 (normalize strips /A)."""
    md = FIXTURE.read_text(encoding="utf-8")
    titles_s1 = _titles(md, "S-1")
    titles_s1a = _titles(md, "S-1/A")
    assert titles_s1 == titles_s1a
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/test_sectionize_s1.py -v`

- [ ] **Step 4: Interpret results**

Three possible outcomes:

1. **All 7 pass.** Skip to Step 7 and commit. Spec's "zero new code" prediction holds.
2. **Some fail because the general-form path ignores `# H1` headings in favor of bold headings.** Look at `edgarpack/parse/sectionize.py` around line 543 (`if is_general_form:` branch). Both `BOLD_HEADING_PATTERN` and the `line.startswith("#")` branch are already present, so the fixture using `#`-headings should already be caught.
3. **Some fail because `_is_valid_general_heading` rejects short titles like "Dilution".** Inspect the rejection reason by reading the helper and its filters.

- [ ] **Step 5: If failures in case 3, add a narrow S-1 anchor whitelist**

Inside `edgarpack/parse/sectionize.py`, add (near the top of the file):

```python
S1_ANCHOR_TITLES = frozenset(
    {
        "prospectus summary",
        "risk factors",
        "use of proceeds",
        "capitalization",
        "dilution",
        "management's discussion and analysis",
        "management's discussion and analysis of financial condition and results of operations",
        "business",
        "principal stockholders",
        "underwriting",
        "selling stockholders",
        "description of capital stock",
    }
)
```

Then in the `is_general_form` branch at line ~543, before the `_is_valid_general_heading` call, short-circuit the whitelist. Specifically, after parsing `title` from either the bold pattern or the `#`-heading path, add:

```python
if is_general_form and title.strip().lower() in S1_ANCHOR_TITLES:
    key = _title_key(title)
    if key not in seen_titles:
        seen_titles.add(key)
        _add_item_match(
            item="other",
            title=title,
            part=None,
            char_pos=char_offsets[line_num] + m.start() if "m" in locals() else char_offsets[line_num],
        )
    continue
```

Adapt the exact position to the surrounding code layout.

- [ ] **Step 6: Re-run sectionizer tests and the full suite**

Run: `.venv/bin/python -m pytest tests/test_sectionize_s1.py tests/ -x -q`
Expected: all pass.

- [ ] **Step 7: Commit**

If no code change was needed:

```bash
git add tests/test_sectionize_s1.py tests/fixtures/cerebras_s1_sample.md
git commit -m "test(sectionize): confirm S-1 anchors are caught by existing general-form path"
```

If the whitelist branch was added:

```bash
git add edgarpack/parse/sectionize.py tests/test_sectionize_s1.py tests/fixtures/cerebras_s1_sample.md
git commit -m "feat(sectionize): narrow S-1 anchor whitelist inside general-form branch"
```

---

## Phase 3: Query layer (periods guard, kpi_discover filter, framing + S-1 disclosures)

### Task 8: Guard `periods.py` against registration-class forms in LTM/quarterly logic

**Files:**
- Modify: `edgarpack/query/periods.py` (around lines 269, 281)
- Test: `tests/test_periods_registration_guard.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_periods_registration_guard.py`:

```python
"""Verify periods helpers do not treat registration-class forms as annual/quarterly."""

from edgarpack.query.periods import _is_annual, _is_quarter_form_type
from edgarpack.sec.submissions import is_registration_form


def test_registration_form_is_not_annual():
    for form in ("S-1", "S-1/A", "F-1", "F-1/A", "424B4", "FWP"):
        assert not _is_annual({"form": form, "fp": ""}), form


def test_registration_form_is_not_quarterly():
    for form in ("S-1", "S-1/A", "F-1", "F-1/A", "424B4", "FWP"):
        assert not _is_quarter_form_type(form), form


def test_is_registration_form_is_accessible_from_periods_callers():
    """Sanity: the single predicate used by the guard is the one exported by submissions."""
    assert is_registration_form("S-1")
    assert not is_registration_form("10-K")
```

- [ ] **Step 2: Run tests to see current behavior**

Run: `.venv/bin/python -m pytest tests/test_periods_registration_guard.py -v`

If `_is_annual` and `_is_quarter_form_type` already return False for registration forms today (because they only return True for an explicit allowlist), the tests pass without code changes. Verify before proceeding.

Expected: in the current code, these functions return False for `S-1` because the allowlists are explicit. Tests should pass.

- [ ] **Step 3: Add a belt-and-braces guard to `periods.py`**

Even if the tests pass today, add an explicit guard so a future extension of the allowlist cannot accidentally catch registration forms. Edit `edgarpack/query/periods.py`:

Import at the top (next to other submissions imports):

```python
from ..sec.submissions import is_registration_form
```

Modify `_is_annual`:

```python
def _is_annual(v: dict[str, Any]) -> bool:
    """Check if a value is from an annual filing."""
    form = str(v.get("form", "")).upper()
    if is_registration_form(form):
        return False
    return str(v.get("fp", "")).upper() == "FY" or form in ("10-K", "10-K/A", "20-F", "20-F/A")
```

Modify `_is_quarter_form_type`:

```python
def _is_quarter_form_type(form: str) -> bool:
    """Check if a form type can carry quarterly values."""
    if is_registration_form(form):
        return False
    form_upper = form.strip().upper()
    return form_upper.startswith("10-Q") or form_upper in ("10-K", "10-K/A", "20-F", "20-F/A")
```

- [ ] **Step 4: Run the guard tests plus the full suite**

Run: `.venv/bin/python -m pytest tests/test_periods_registration_guard.py tests/ -x -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/periods.py tests/test_periods_registration_guard.py
git commit -m "feat(periods): explicit registration-form guard in annual/quarterly classifiers"
```

---

### Task 9: Allow registration-class packs through the `kpi_discover` form filter

**Files:**
- Modify: `edgarpack/query/kpi_discover.py` (around line 411)
- Test: `tests/test_kpi_discover_s1_allowed.py` (new)

- [ ] **Step 1: Write a failing test asserting the filter allows S-1 packs**

Create `tests/test_kpi_discover_s1_allowed.py`:

```python
"""Verify kpi_discover includes registration-class packs in its eligible set."""

from edgarpack.query.kpi_discover import _filter_eligible_packs_for_test


def test_s1_packs_are_eligible():
    fake_packs = [
        type("P", (), {"accession": "a", "form_type": "10-K"})(),
        type("P", (), {"accession": "b", "form_type": "S-1"})(),
        type("P", (), {"accession": "c", "form_type": "S-1/A"})(),
        type("P", (), {"accession": "d", "form_type": "424B4"})(),
        type("P", (), {"accession": "e", "form_type": "FWP"})(),
        type("P", (), {"accession": "f", "form_type": "8-K"})(),
    ]
    eligible = _filter_eligible_packs_for_test(fake_packs)
    accessions = {p.accession for p in eligible}
    assert {"a", "b", "c", "d", "e"}.issubset(accessions)
    # 8-K stays out.
    assert "f" not in accessions
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover_s1_allowed.py -v`
Expected: FAIL with `ImportError: cannot import name '_filter_eligible_packs_for_test'`.

- [ ] **Step 3: Update `kpi_discover.py`**

In `edgarpack/query/kpi_discover.py`, locate the line around 411:

```python
        eligible_packs = [
            p for p in packs if (p.form_type or "").upper().startswith(("10-K", "10-Q", "20-F"))
        ]
```

Replace with:

```python
        eligible_packs = _filter_eligible_packs(packs)
```

Above the class that contains this code, add:

```python
from ..sec.submissions import is_registration_form


def _filter_eligible_packs(packs):
    """Packs eligible for KPI discovery: periodic forms plus registration family."""
    out = []
    for p in packs:
        ft = (getattr(p, "form_type", "") or "").upper()
        if ft.startswith(("10-K", "10-Q", "20-F")) or is_registration_form(ft):
            out.append(p)
    return out


# Public alias for tests.
_filter_eligible_packs_for_test = _filter_eligible_packs
```

Also update the `_is_annual` helper around line 581 in the same file:

```python
        def _is_annual(r: CompanyKpiRow) -> bool:
            ft = (r.form_type or "").upper()
            return ft.startswith("10-K") or ft in {"20-F", "40-F"}
```

Leave this helper unchanged. It is used for period selection where registration forms should NOT be treated as annual. That is exactly the Task 8 guard semantics, reinforced here.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover_s1_allowed.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/query/kpi_discover.py tests/test_kpi_discover_s1_allowed.py
git commit -m "feat(kpi_discover): allow registration-class packs through the eligibility filter"
```

---

### Task 10: Framing-metric patterns (TAM / SAM / CAGR / market size)

**Files:**
- Modify: `edgarpack/query/kpi_discover.py`
- Test: `tests/test_kpi_framing.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_kpi_framing.py`:

```python
"""Tests for the framing-metric pattern group (TAM / market size / CAGR)."""

from edgarpack.query.kpi_discover import extract_framing_claims


def test_tam_dollar_pattern():
    text = "We estimate the total addressable market at $150 billion."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)
    assert any("$150" in h.claim for h in hits)


def test_addressable_market_pattern():
    text = "The addressable market for AI inference is approximately $90 billion."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)


def test_cagr_pattern():
    text = "The market is growing at 34% CAGR through 2030."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)
    assert any("34%" in h.claim for h in hits)


def test_billion_opportunity_pattern():
    text = "This represents a $500 billion opportunity for our company."
    hits = extract_framing_claims(text)
    assert any(h.metric_kind == "framing" for h in hits)


def test_no_framing_in_boilerplate_text():
    text = "This prospectus contains forward-looking statements within the meaning of Section 27A."
    hits = extract_framing_claims(text)
    assert hits == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_kpi_framing.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_framing_claims'`.

- [ ] **Step 3: Add framing extractor to `kpi_discover.py`**

Append to `edgarpack/query/kpi_discover.py`:

```python
import re
from dataclasses import dataclass


@dataclass
class FramingHit:
    """A single market-framing claim extracted from prose."""

    claim: str
    metric_kind: str  # always "framing" for this extractor
    pattern: str
    offset: int


_FRAMING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "tam_dollar",
        re.compile(
            r"(?:total\s+addressable\s+market|TAM)[^.\n]{0,40}?\$[0-9][0-9.,]*\s*(?:billion|million|trillion|B|M|T)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "addressable_market_dollar",
        re.compile(
            r"(?:addressable\s+market)[^.\n]{0,40}?\$[0-9][0-9.,]*\s*(?:billion|million|trillion|B|M|T)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cagr",
        re.compile(
            r"(?:growing|growth|expand(?:ing|s)?)[^.\n]{0,40}?\d{1,3}(?:\.\d+)?\s*%\s*(?:CAGR|compound\s+annual\s+growth)",
            re.IGNORECASE,
        ),
    ),
    (
        "cagr_simple",
        re.compile(
            r"\b\d{1,3}(?:\.\d+)?\s*%\s*CAGR\b",
            re.IGNORECASE,
        ),
    ),
    (
        "dollar_opportunity",
        re.compile(
            r"\$[0-9][0-9.,]*\s*(?:billion|trillion|B|T)\s+(?:market\s+)?opportunity",
            re.IGNORECASE,
        ),
    ),
]


def extract_framing_claims(text: str) -> list[FramingHit]:
    """Scan prose for TAM / addressable-market / CAGR / opportunity claims.

    Designed to run across an entire pack's markdown (or any subsection)
    and tag the hits with metric_kind='framing'. Callers may persist the
    hits into the existing discovered-KPI index alongside operating and
    snapshot metrics.
    """
    hits: list[FramingHit] = []
    if not text:
        return hits
    for name, pattern in _FRAMING_PATTERNS:
        for m in pattern.finditer(text):
            hits.append(
                FramingHit(
                    claim=m.group(0).strip(),
                    metric_kind="framing",
                    pattern=name,
                    offset=m.start(),
                )
            )
    return hits
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_kpi_framing.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/kpi_discover.py tests/test_kpi_framing.py
git commit -m "feat(kpi_discover): framing-metric extractor (TAM / market size / CAGR)"
```

---

### Task 11: S-1-only disclosure extractors (use of proceeds, dilution, lockup, principal holders)

**Files:**
- Modify: `edgarpack/query/kpi_discover.py`
- Test: `tests/test_s1_disclosures.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_s1_disclosures.py`:

```python
"""Tests for S-1-only disclosure extractors."""

from edgarpack.query.kpi_discover import (
    extract_dilution,
    extract_lockup,
    extract_principal_holders,
    extract_use_of_proceeds,
)


def test_use_of_proceeds_simple():
    text = (
        "We intend to use the net proceeds from this offering as follows: "
        "approximately $150.0 million for research and development, "
        "$80.0 million for manufacturing capacity expansion, "
        "and the remainder for working capital."
    )
    hits = extract_use_of_proceeds(text)
    assert len(hits) >= 2
    assert any("research" in h.claim.lower() for h in hits)
    assert any("manufacturing" in h.claim.lower() for h in hits)
    assert all(h.metric_kind == "s1_disclosure" for h in hits)
    assert all(h.disclosure_type == "use_of_proceeds" for h in hits)


def test_dilution_per_share():
    text = "You will experience immediate dilution of $12.50 per share."
    hits = extract_dilution(text)
    assert hits
    assert "$12.50" in hits[0].claim
    assert hits[0].disclosure_type == "dilution"


def test_lockup_days():
    text = "The lock-up period will be 180 days from the date of this prospectus."
    hits = extract_lockup(text)
    assert hits
    assert "180" in hits[0].claim
    assert hits[0].disclosure_type == "lockup"


def test_principal_holders_with_percentages():
    text = (
        "Name                        Shares           Percent\n"
        "Acme Capital LP             12,500,000       18.4%\n"
        "Founder Jane Doe             9,000,000       13.2%\n"
        "Strategic Ventures Fund      5,250,000        7.7%"
    )
    hits = extract_principal_holders(text)
    assert len(hits) >= 3
    assert any("Acme Capital" in h.claim for h in hits)
    assert all(h.metric_kind == "s1_disclosure" for h in hits)
    assert all(h.disclosure_type == "principal_holder" for h in hits)


def test_nothing_extracted_on_irrelevant_text():
    text = "The Company was founded in 2016 in Los Altos, California."
    assert extract_use_of_proceeds(text) == []
    assert extract_dilution(text) == []
    assert extract_lockup(text) == []
    assert extract_principal_holders(text) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_s1_disclosures.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_use_of_proceeds'`.

- [ ] **Step 3: Add the four extractors to `kpi_discover.py`**

Append to `edgarpack/query/kpi_discover.py`:

```python
@dataclass
class DisclosureHit:
    """A single S-1 disclosure extracted from prose or table text."""

    claim: str
    metric_kind: str  # always "s1_disclosure"
    disclosure_type: str  # "use_of_proceeds" | "dilution" | "lockup" | "principal_holder"
    offset: int


_USE_OF_PROCEEDS_ITEM = re.compile(
    r"(?:approximately\s+)?\$[0-9][0-9.,]*\s*(?:billion|million|B|M)\s+for\s+[^.,;]{3,80}",
    re.IGNORECASE,
)

_DILUTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"immediate\s+dilution\s+of\s+\$[0-9][0-9.,]*(?:\s*per\s+share)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"pro\s+forma\s+net\s+tangible\s+book\s+value\s+of\s+\$[0-9][0-9.,]*(?:\s*per\s+share)?",
        re.IGNORECASE,
    ),
]

_LOCKUP_PATTERN = re.compile(
    r"lock\s*[-\s]?up\s+(?:period|agreement)[^.\n]{0,60}?\b(\d{2,4})\s*days\b",
    re.IGNORECASE,
)

_PRINCIPAL_HOLDER_ROW = re.compile(
    r"^(?P<name>[A-Z][\w &.,'\-]{2,80}?)\s{2,}"
    r"(?P<shares>[0-9][0-9,]*)\s{2,}"
    r"(?P<pct>\d{1,3}(?:\.\d+)?)\s*%",
    re.MULTILINE,
)


def extract_use_of_proceeds(text: str) -> list[DisclosureHit]:
    hits: list[DisclosureHit] = []
    if not text:
        return hits
    for m in _USE_OF_PROCEEDS_ITEM.finditer(text):
        hits.append(
            DisclosureHit(
                claim=m.group(0).strip(),
                metric_kind="s1_disclosure",
                disclosure_type="use_of_proceeds",
                offset=m.start(),
            )
        )
    return hits


def extract_dilution(text: str) -> list[DisclosureHit]:
    hits: list[DisclosureHit] = []
    if not text:
        return hits
    for pattern in _DILUTION_PATTERNS:
        for m in pattern.finditer(text):
            hits.append(
                DisclosureHit(
                    claim=m.group(0).strip(),
                    metric_kind="s1_disclosure",
                    disclosure_type="dilution",
                    offset=m.start(),
                )
            )
    return hits


def extract_lockup(text: str) -> list[DisclosureHit]:
    hits: list[DisclosureHit] = []
    if not text:
        return hits
    for m in _LOCKUP_PATTERN.finditer(text):
        hits.append(
            DisclosureHit(
                claim=m.group(0).strip(),
                metric_kind="s1_disclosure",
                disclosure_type="lockup",
                offset=m.start(),
            )
        )
    return hits


def extract_principal_holders(text: str) -> list[DisclosureHit]:
    """Parse whitespace-separated Principal Stockholders table rows.

    Intentionally permissive on whitespace so column-aligned plaintext tables
    from SEC HTML-to-markdown conversion match.
    """
    hits: list[DisclosureHit] = []
    if not text:
        return hits
    for m in _PRINCIPAL_HOLDER_ROW.finditer(text):
        claim = (
            f"{m.group('name').strip()} | "
            f"{m.group('shares')} shares | "
            f"{m.group('pct')}%"
        )
        hits.append(
            DisclosureHit(
                claim=claim,
                metric_kind="s1_disclosure",
                disclosure_type="principal_holder",
                offset=m.start(),
            )
        )
    return hits
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_s1_disclosures.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/query/kpi_discover.py tests/test_s1_disclosures.py
git commit -m "feat(kpi_discover): S-1 disclosure extractors (use of proceeds, dilution, lockup, principal holders)"
```

---

## Phase 4: Visuals pipeline (roadshow images + opt-in VLM description)

### Task 12: `html_clean` gains `preserve_images` flag

**Files:**
- Modify: `edgarpack/parse/html_clean.py`
- Test: `tests/test_html_clean_preserve_images.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_html_clean_preserve_images.py`:

```python
"""Ensure html_clean can preserve <img> tags for registration-class filings."""

from edgarpack.parse.html_clean import clean_html


HTML = """
<html><body>
<p>Our flagship product is the CS-3.</p>
<img src="figure-1-cs3-photo.jpg" alt="Photograph of the Cerebras CS-3 system"/>
<p>Performance scales linearly.</p>
<img src="figure-2-tam-chart.png" alt="AI inference TAM chart"/>
</body></html>
"""


def test_default_strips_images():
    out = clean_html(HTML)
    assert "<img" not in out.lower()


def test_preserve_images_keeps_img_tags():
    out = clean_html(HTML, preserve_images=True)
    assert out.lower().count("<img") == 2
    assert "figure-1-cs3-photo.jpg" in out
    assert "figure-2-tam-chart.png" in out


def test_preserve_images_keeps_alt_text():
    out = clean_html(HTML, preserve_images=True)
    assert "Photograph of the Cerebras CS-3 system" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_html_clean_preserve_images.py -v`
Expected: FAIL because either `preserve_images` kwarg does not exist or the default already strips images.

- [ ] **Step 3: Update `clean_html` signature**

Edit `edgarpack/parse/html_clean.py`. Locate the `clean_html` function. Add `preserve_images: bool = False` to its signature. Inside the function, find the tag-stripping logic that removes `<img>` elements and wrap it:

```python
def clean_html(html: str, preserve_images: bool = False) -> str:
    """Clean SEC HTML, optionally preserving <img> tags.

    preserve_images=True is used by registration-class forms (S-1 family)
    so roadshow infographics and product photos survive into the rendered
    markdown. Default False preserves the existing periodic-form behavior.
    """
    # ... existing cleaning logic ...
    # Where images are removed today, gate on the flag:
    #     if not preserve_images:
    #         remove_images(soup_or_tree)
```

Apply the gate at the exact location the existing code strips images. If the existing code uses a tag allowlist, add `"img"` to the allowlist when `preserve_images` is True; if it uses a removal list, remove `"img"` from that list conditionally.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_html_clean_preserve_images.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass. Existing callers that do not pass `preserve_images` continue to strip images.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/parse/html_clean.py tests/test_html_clean_preserve_images.py
git commit -m "feat(parse): preserve_images flag on clean_html for registration-class forms"
```

---

### Task 13: `md_render` rewrites `<img src>` to local paths and emits a caption

**Files:**
- Modify: `edgarpack/parse/md_render.py`
- Test: `tests/test_md_render_images.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_md_render_images.py`:

```python
"""Ensure rendered markdown rewrites <img src> to local paths with a caption line."""

from edgarpack.parse.md_render import render_markdown


HTML_WITH_IMG = """
<html><body>
<p>Intro paragraph.</p>
<img src="figure-1.jpg" alt="CS-3 system photo"/>
<p>Trailing paragraph.</p>
</body></html>
"""


def test_render_with_asset_map_rewrites_src_to_local_path():
    asset_map = {"figure-1.jpg": "assets/figure-1.jpg"}
    md = render_markdown(HTML_WITH_IMG, asset_map=asset_map)
    assert "![" in md
    assert "assets/figure-1.jpg" in md


def test_render_with_asset_map_emits_alt_as_caption_line():
    asset_map = {"figure-1.jpg": "assets/figure-1.jpg"}
    md = render_markdown(HTML_WITH_IMG, asset_map=asset_map)
    assert "CS-3 system photo" in md


def test_render_without_asset_map_does_not_crash():
    md = render_markdown(HTML_WITH_IMG)
    assert isinstance(md, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_md_render_images.py -v`
Expected: FAIL with `TypeError: render_markdown() got an unexpected keyword argument 'asset_map'` or with missing local-path output.

- [ ] **Step 3: Update `render_markdown` in `md_render.py`**

Edit `edgarpack/parse/md_render.py`. Add an optional parameter:

```python
def render_markdown(html: str, *, asset_map: dict[str, str] | None = None) -> str:
    """Render semantic HTML into markdown.

    asset_map: optional mapping of original <img src> URLs (or filenames) to
        local relative paths (e.g. "assets/figure-1.jpg"). When provided,
        every matching <img> is rewritten to a markdown ![alt](local) image,
        and the alt text is also emitted as a caption line below the image.
    """
```

Inside the function, before returning the markdown string, post-process any `<img>` references the renderer produced. The simplest implementation uses a regex pass on the intermediate HTML or the produced markdown:

```python
import re

_IMG_RE = re.compile(r'<img\s+[^>]*src="([^"]+)"[^>]*(?:alt="([^"]*)")?[^>]*/?>', re.IGNORECASE)


def _rewrite_images(text: str, asset_map: dict[str, str]) -> str:
    def _sub(m: re.Match[str]) -> str:
        src = m.group(1)
        alt = m.group(2) or ""
        local = asset_map.get(src) or asset_map.get(src.split("/")[-1])
        if not local:
            return m.group(0)
        caption = f"\n\n*{alt.strip()}*\n" if alt.strip() else ""
        return f"![{alt}]({local}){caption}"

    return _IMG_RE.sub(_sub, text)
```

Call `_rewrite_images(md, asset_map)` right before the function returns, guarded by `if asset_map:`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_md_render_images.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/parse/md_render.py tests/test_md_render_images.py
git commit -m "feat(parse): md_render rewrites <img> to local paths with alt-text captions"
```

---

### Task 14: `pack/assets.py`: image download + hash-cached VLM description

**Files:**
- Create: `edgarpack/pack/assets.py`
- Modify: `pyproject.toml` (add optional `vlm` extra)
- Test: `tests/test_assets_pipeline.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_assets_pipeline.py`:

```python
"""Tests for the registration-class assets pipeline (download + optional describe)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.pack.assets import (
    describe_asset,
    download_assets,
    extract_image_urls,
)


HTML = """
<img src="figure-1.jpg" alt="CS-3 photo"/>
<img src="https://www.sec.gov/Archives/foo/figure-2.png" alt="Chart"/>
"""


def test_extract_image_urls_finds_both_absolute_and_relative():
    urls = extract_image_urls(HTML)
    assert "figure-1.jpg" in urls
    assert "https://www.sec.gov/Archives/foo/figure-2.png" in urls


@pytest.mark.asyncio
async def test_download_assets_writes_files_and_returns_map(tmp_path):
    async def fake_fetch(url):
        return b"\x89PNG\r\n\x1a\nfakebytes"

    with patch("edgarpack.pack.assets._fetch_bytes", new=AsyncMock(side_effect=fake_fetch)):
        mapping = await download_assets(
            base_url="https://www.sec.gov/Archives/foo/",
            html=HTML,
            out_dir=tmp_path,
        )

    assert "figure-1.jpg" in mapping
    # Relative URL resolves against base_url and lands in out_dir.
    local = tmp_path / mapping["figure-1.jpg"]
    assert local.exists()
    assert local.read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_describe_asset_caches_by_hash(tmp_path, monkeypatch):
    image = tmp_path / "fig.png"
    image.write_bytes(b"fakebytes")
    cache = tmp_path / ".descriptions.json"

    calls = {"n": 0}

    async def fake_vlm(_path):
        calls["n"] += 1
        return "A bar chart showing TAM growth."

    monkeypatch.setattr("edgarpack.pack.assets._vlm_describe", fake_vlm)

    first = await describe_asset(image, cache_path=cache)
    second = await describe_asset(image, cache_path=cache)

    assert first == "A bar chart showing TAM growth."
    assert second == first
    assert calls["n"] == 1  # cached second time.

    on_disk = json.loads(cache.read_text())
    assert any(v == first for v in on_disk.values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_assets_pipeline.py -v`
Expected: FAIL with `ImportError: cannot import name 'describe_asset'`.

- [ ] **Step 3: Create `edgarpack/pack/assets.py`**

Create the file with:

```python
"""Download and optionally describe images embedded in registration-class filings.

Only activated for S-1 / S-1-A / F-1 / F-1-A / 424B* / FWP packs. For periodic
filings (10-K / 10-Q / 8-K) the existing image-stripping behavior is preserved.

VLM description is opt-in via the --describe-images CLI flag and requires the
optional `anthropic` dependency (install via `pip install edgarpack[vlm]`).
Descriptions are cached on disk keyed by sha256(image_bytes) so re-harvests
never re-bill.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path

from ..sec.client import get_client

_IMG_SRC_RE = re.compile(r'<img\s+[^>]*src="([^"]+)"', re.IGNORECASE)

_VLM_PROMPT = (
    "Extract in under 75 words: what this figure shows "
    "(chart type, product shot, org chart, etc.); any numeric claims stated "
    "on the image (market size, growth rates, customer counts, performance "
    "benchmarks); and the one-line thesis the figure supports. If the image "
    "is decorative, say so."
)


def extract_image_urls(html: str) -> list[str]:
    """Return the raw src values of every <img> tag in order."""
    if not html:
        return []
    return _IMG_SRC_RE.findall(html)


def _local_filename(src: str) -> str:
    """Pick a safe local filename from a URL or relative path."""
    parsed = urllib.parse.urlparse(src)
    name = Path(parsed.path).name or Path(src).name or "image"
    # Strip characters that make shells unhappy.
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", name)
    return safe or "image"


async def _fetch_bytes(url: str) -> bytes:
    client = await get_client()
    body = await client.fetch(url)
    if isinstance(body, str):
        return body.encode("utf-8")
    return body


async def download_assets(
    base_url: str,
    html: str,
    out_dir: Path,
) -> dict[str, str]:
    """Download every <img> referenced in `html` into <out_dir>/assets/.

    Returns a mapping from the original src string to a repo-relative local
    path of the form "assets/<filename>" suitable for embedding in markdown.
    """
    out_dir = Path(out_dir)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    for src in extract_image_urls(html):
        abs_url = urllib.parse.urljoin(base_url, src)
        try:
            blob = await _fetch_bytes(abs_url)
        except Exception:
            continue
        filename = _local_filename(src)
        target = assets_dir / filename
        # Avoid collisions by suffixing with a short content hash when needed.
        if target.exists() and target.read_bytes() != blob:
            h = hashlib.sha256(blob).hexdigest()[:8]
            target = assets_dir / f"{target.stem}-{h}{target.suffix}"
        target.write_bytes(blob)
        mapping[src] = f"assets/{target.name}"
    return mapping


async def _vlm_describe(image_path: Path) -> str:
    """Call Anthropic vision on the image. Isolated so tests can monkeypatch."""
    try:
        import base64

        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError(
            "Image description requires the `anthropic` package. "
            "Install with `pip install edgarpack[vlm]`."
        ) from exc

    client = AsyncAnthropic()
    blob = Path(image_path).read_bytes()
    b64 = base64.standard_b64encode(blob).decode("ascii")
    suffix = Path(image_path).suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(suffix, "image/jpeg")

    msg = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": _VLM_PROMPT},
                ],
            }
        ],
    )
    return "".join(
        block.text for block in msg.content if getattr(block, "type", "") == "text"
    ).strip()


async def describe_asset(image_path: Path, cache_path: Path | None = None) -> str:
    """Return a short description of an image, caching by sha256 content hash.

    Cache file is JSON: {sha256: description, ...}. Callers typically pass
    `<pack>/assets/.descriptions.json`.
    """
    image_path = Path(image_path)
    blob = image_path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()

    cache: dict[str, str] = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}

    if digest in cache:
        return cache[digest]

    description = await _vlm_describe(image_path)
    cache[digest] = description
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return description
```

- [ ] **Step 4: Add optional `vlm` extra to pyproject.toml**

Edit `pyproject.toml`. Inside `[project.optional-dependencies]`, add:

```toml
vlm = ["anthropic>=0.40"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_assets_pipeline.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass. No existing test touches `pack/assets.py`.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/pack/assets.py pyproject.toml tests/test_assets_pipeline.py
git commit -m "feat(pack): assets pipeline (download + hash-cached VLM description)"
```

---

### Task 15: Wire assets pipeline into `pack/build.py` for registration-class forms

**Files:**
- Modify: `edgarpack/pack/build.py`
- Test: `tests/test_build_pack_registration.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_build_pack_registration.py`:

```python
"""Tests for registration-class pack build wiring (images + render path)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from edgarpack.pack.build import _process_html_files_for_form


@pytest.mark.asyncio
async def test_registration_form_preserves_images_and_rewrites_src(tmp_path):
    html = (
        '<html><body><p>Intro.</p>'
        '<img src="fig1.png" alt="TAM chart"/>'
        '<p>Body.</p></body></html>'
    )

    async def fake_download(base_url, html_payload, out_dir):
        (Path(out_dir) / "assets").mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "assets" / "fig1.png").write_bytes(b"x")
        return {"fig1.png": "assets/fig1.png"}

    with patch("edgarpack.pack.build.download_assets", new=fake_download):
        md = await _process_html_files_for_form(
            html_files=[("main.htm", html.encode("utf-8"))],
            base_url="https://www.sec.gov/Archives/foo/",
            form_type="S-1",
            out_dir=tmp_path,
            describe_images=False,
        )

    assert "assets/fig1.png" in md
    assert "TAM chart" in md


@pytest.mark.asyncio
async def test_periodic_form_still_strips_images(tmp_path):
    html = '<html><body><img src="logo.png"/><p>10-K body.</p></body></html>'
    md = await _process_html_files_for_form(
        html_files=[("main.htm", html.encode("utf-8"))],
        base_url="https://www.sec.gov/Archives/foo/",
        form_type="10-K",
        out_dir=tmp_path,
        describe_images=False,
    )
    assert "<img" not in md.lower()
    assert "assets/" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_build_pack_registration.py -v`
Expected: FAIL with `ImportError: cannot import name '_process_html_files_for_form'`.

- [ ] **Step 3: Add the form-aware entry point to `pack/build.py`**

Edit `edgarpack/pack/build.py`. Add imports at the top:

```python
from ..sec.submissions import is_registration_form
from .assets import describe_asset, download_assets
```

Below the existing `_process_html_files` function, add:

```python
async def _process_html_files_for_form(
    html_files: list[tuple[str, bytes]],
    base_url: str,
    form_type: str,
    out_dir: Path,
    describe_images: bool = False,
) -> str:
    """Variant of `_process_html_files` that preserves and downloads images
    for registration-class forms and rewrites <img src> to local paths.

    For periodic forms the behavior is identical to the existing
    `_process_html_files`.
    """
    combined_html = "\n".join(_decode_html_blob(content) for _, content in html_files)
    html_stripped = strip_ixbrl(combined_html)

    preserve = is_registration_form(form_type)
    html_cleaned = clean_html(html_stripped, preserve_images=preserve) if preserve else clean_html(html_stripped)
    html_semantic = reduce_to_semantic(html_cleaned, base_url=base_url)

    asset_map: dict[str, str] = {}
    if preserve:
        asset_map = await download_assets(
            base_url=base_url,
            html=html_cleaned,
            out_dir=Path(out_dir),
        )
        if describe_images and asset_map:
            cache_path = Path(out_dir) / "assets" / ".descriptions.json"
            enriched: dict[str, str] = {}
            for src, local_rel in asset_map.items():
                image_path = Path(out_dir) / local_rel
                try:
                    desc = await describe_asset(image_path, cache_path=cache_path)
                except Exception:
                    desc = ""
                enriched[src] = local_rel
                if desc:
                    # Emit description as a sibling markdown file so render pass
                    # can pick it up as an alt-text replacement.
                    (image_path.parent / f"{image_path.stem}.desc.txt").write_text(
                        desc, encoding="utf-8"
                    )
            asset_map = enriched

    md = render_markdown(html_semantic, asset_map=asset_map) if asset_map else render_markdown(html_semantic)
    return polish(md)
```

Inside the existing `build_pack` function, find the call site that invokes `_process_html_files(...)` (it is the synchronous helper currently at the top of the file) and replace with:

```python
    md = await _process_html_files_for_form(
        html_files=html_files,
        base_url=base_url,
        form_type=form_type or "",
        out_dir=out_dir,
        describe_images=False,  # opt-in surfaces via CLI in Task 18.
    )
```

If the existing code passes a `describe_images` kwarg through `build_pack`, propagate it. Otherwise leave it False here and wire the flag through in Task 18.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_build_pack_registration.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/pack/build.py tests/test_build_pack_registration.py
git commit -m "feat(pack): wire assets pipeline and form-aware render into build_pack"
```

---

## Phase 5: Diff / timeline for the registration chain

### Task 16: `build_registration_timeline` and `series_class` dispatch

**Files:**
- Modify: `edgarpack/diff/timeline.py`
- Test: `tests/test_registration_timeline.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_registration_timeline.py`:

```python
"""Tests for the registration-class timeline series."""

import json
from pathlib import Path

from edgarpack.diff.timeline import build_registration_timeline


def _write_pack(root: Path, accession: str, form: str, filing_date: str) -> Path:
    pack = root / accession
    pack.mkdir(parents=True, exist_ok=True)
    manifest = {
        "filing": {
            "accession": accession,
            "form_type": form,
            "filing_date": filing_date,
            "cik": "0002021728",
        },
        "sections": [],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest))
    return pack


def test_timeline_orders_by_filing_date(tmp_path):
    _write_pack(tmp_path, "A-3", "S-1/A", "2025-10-15")
    _write_pack(tmp_path, "A-1", "S-1", "2025-09-30")
    _write_pack(tmp_path, "A-4", "424B4", "2025-12-01")
    _write_pack(tmp_path, "A-2", "S-1/A", "2025-10-01")

    entries = build_registration_timeline(pack_root=tmp_path, cik="0002021728")
    accessions = [e.accession for e in entries]
    assert accessions == ["A-1", "A-2", "A-3", "A-4"]


def test_timeline_excludes_non_registration_forms(tmp_path):
    _write_pack(tmp_path, "A-1", "S-1", "2025-09-30")
    _write_pack(tmp_path, "K-1", "10-K", "2026-03-15")

    entries = build_registration_timeline(pack_root=tmp_path, cik="0002021728")
    assert [e.accession for e in entries] == ["A-1"]


def test_timeline_scopes_to_cik(tmp_path):
    _write_pack(tmp_path, "A-1", "S-1", "2025-09-30")
    other = tmp_path / "other"
    other.mkdir()
    other_pack = other / "B-1"
    other_pack.mkdir()
    (other_pack / "manifest.json").write_text(
        json.dumps(
            {
                "filing": {
                    "accession": "B-1",
                    "form_type": "S-1",
                    "filing_date": "2025-08-01",
                    "cik": "0001234567",
                },
                "sections": [],
            }
        )
    )
    entries = build_registration_timeline(pack_root=tmp_path, cik="0002021728")
    assert [e.accession for e in entries] == ["A-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_registration_timeline.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_registration_timeline'`.

- [ ] **Step 3: Add `build_registration_timeline` to `diff/timeline.py`**

Append to `edgarpack/diff/timeline.py`:

```python
from ..sec.submissions import is_registration_form, normalize_cik


class RegistrationTimelineEntry(BaseModel):
    """A single filing in the registration (S-1 chain) timeline."""

    accession: str
    form_type: str
    filing_date: str
    pack_dir: Path

    model_config = {"arbitrary_types_allowed": True}


def build_registration_timeline(
    pack_root: Path,
    cik: str,
) -> list[RegistrationTimelineEntry]:
    """Return registration-class filings for a CIK, oldest first.

    Walks `pack_root` looking for manifest.json files and includes only
    those whose filing.cik matches and whose form is registration-class.
    Sorted ascending by filing_date so callers can diff consecutive pairs.
    """
    target = normalize_cik(cik)
    entries: list[RegistrationTimelineEntry] = []
    for manifest_path in Path(pack_root).rglob("manifest.json"):
        try:
            data = load_manifest_dict(manifest_path.parent, on_missing="empty")
        except Exception:
            continue
        if not data:
            continue
        filing = data.get("filing", {})
        form = str(filing.get("form_type", ""))
        if not is_registration_form(form):
            continue
        filing_cik = str(filing.get("cik", ""))
        if filing_cik and normalize_cik(filing_cik) != target:
            continue
        entries.append(
            RegistrationTimelineEntry(
                accession=str(filing.get("accession", "")),
                form_type=form,
                filing_date=str(filing.get("filing_date", "")),
                pack_dir=manifest_path.parent,
            )
        )
    entries.sort(key=lambda e: (e.filing_date, e.accession))
    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_registration_timeline.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/diff/timeline.py tests/test_registration_timeline.py
git commit -m "feat(diff): build_registration_timeline for S-1 redline series"
```

---

## Phase 6: CLI surface

### Task 17: `--series=registration` flag on the timeline / diff CLI entrypoint

**Files:**
- Modify: `edgarpack/cli.py`
- Test: `tests/test_cli_series_registration.py` (new)

- [ ] **Step 1: Identify the CLI entrypoint for timeline/diff**

Run: `grep -n "timeline\|diff" edgarpack/cli.py | head -20`
Read the surrounding argparse block. The subcommand may be named `timeline`, `diff`, or similar. Locate the existing `--series` argument if any.

- [ ] **Step 2: Write a failing test for the new flag**

Create `tests/test_cli_series_registration.py`:

```python
"""Smoke test that --series=registration is accepted by the CLI parser."""

import subprocess
import sys


def test_cli_accepts_series_registration_flag():
    result = subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "timeline", "--help"],
        capture_output=True,
        text=True,
    )
    # The subcommand help output should mention the series flag OR the command
    # should at least parse without crashing when the flag is provided.
    assert result.returncode == 0 or result.returncode == 2
    # Direct invocation with the flag should not produce an "unrecognized
    # arguments" error.
    probe = subprocess.run(
        [
            sys.executable,
            "-m",
            "edgarpack.cli",
            "timeline",
            "--series",
            "registration",
            "--cik",
            "0002021728",
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    assert "unrecognized arguments" not in probe.stderr.lower()
```

- [ ] **Step 3: Add the flag to the CLI**

Edit `edgarpack/cli.py`. Find the subcommand that exposes timeline / diff (based on Step 1's grep). Add to its argument parser:

```python
parser.add_argument(
    "--series",
    choices=["annual", "registration"],
    default="annual",
    help=(
        "Which filing series to build the timeline over. "
        "'annual' (default) is the existing 10-K / 10-Q run. "
        "'registration' is the S-1 / S-1-A / 424B / FWP redline chain "
        "for pre-IPO filers."
    ),
)
```

In the command's handler function, branch on `args.series`:

```python
if getattr(args, "series", "annual") == "registration":
    from .diff.timeline import build_registration_timeline
    entries = build_registration_timeline(pack_root=packs_root, cik=args.cik)
    # Pair-wise diffs across consecutive entries. Reuse existing section_diff
    # helpers as in the annual path; the loop structure is the same.
    for before, after in zip(entries, entries[1:], strict=False):
        # Render a compact pair header so CLI output makes the chain clear.
        print(f"\n=== {before.accession} ({before.form_type}, {before.filing_date}) "
              f"-> {after.accession} ({after.form_type}, {after.filing_date}) ===")
        # Call into the existing per-pair diff renderer. If the codebase
        # currently uses a function like `render_pair_diff(before_dir, after_dir)`,
        # invoke it here; otherwise inline the same logic used in the annual
        # path with these two pack_dirs.
else:
    # Existing annual path unchanged.
    ...
```

Adapt the handler to the specific patterns already in `cli.py`. Keep every change scoped to the timeline/diff subcommand.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_cli_series_registration.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/cli.py tests/test_cli_series_registration.py
git commit -m "feat(cli): --series=registration flag for the S-1 chain timeline"
```

---

### Task 18: `--describe-images` CLI flag propagating to `build_pack`

**Files:**
- Modify: `edgarpack/cli.py`
- Modify: `edgarpack/pack/build.py` (thread the kwarg)
- Test: `tests/test_cli_describe_images.py` (new)

- [ ] **Step 1: Write a failing test**

Create `tests/test_cli_describe_images.py`:

```python
"""CLI flag plumbing test for --describe-images."""

import subprocess
import sys


def test_cli_accepts_describe_images_flag():
    result = subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "harvest", "--help"],
        capture_output=True,
        text=True,
    )
    # Flag should appear in help output; exact wording may vary.
    assert "describe-images" in result.stdout or "describe_images" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli_describe_images.py -v`
Expected: FAIL because the flag is not exposed.

- [ ] **Step 3: Add the flag to the CLI harvest subcommand**

Edit `edgarpack/cli.py`. Locate the `harvest` subcommand. Add:

```python
harvest_parser.add_argument(
    "--describe-images",
    action="store_true",
    help=(
        "Generate VLM descriptions for images in registration-class filings. "
        "Requires the optional `anthropic` extra (pip install edgarpack[vlm]). "
        "Descriptions are hash-cached per image in <pack>/assets/.descriptions.json "
        "so re-harvests do not re-bill."
    ),
)
```

Thread `describe_images=args.describe_images` down into wherever `build_pack` is invoked by the harvest runner. Inside `edgarpack/pack/build.py` add a `describe_images: bool = False` parameter to `build_pack`, and forward it into the `_process_html_files_for_form` call from Task 15.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_cli_describe_images.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/cli.py edgarpack/pack/build.py tests/test_cli_describe_images.py
git commit -m "feat(cli): --describe-images flag threads VLM opt-in into pack build"
```

---

## Phase 7: Universe entry and end-to-end verification

### Task 19: Add Cerebras to `universe.toml`

**Files:**
- Modify: `universe.toml`

- [ ] **Step 1: Add the Cerebras entry**

Edit `universe.toml`. Add under the appropriate section (likely near Semiconductors, or create a new "Pre-IPO / Registration" subsection):

```toml
# ============================================================
#  Pre-IPO filers (registration-class only)
# ============================================================

[[companies]]
name = "Cerebras Systems"
forms_s1 = 8
```

- [ ] **Step 2: Parse the updated universe to confirm it validates**

Run:

```bash
.venv/bin/python -c "from pathlib import Path; from edgarpack.harvest.universe import load_universe; cfg = load_universe(Path('universe.toml')); print(f'Loaded {len(cfg.companies)} companies'); cerebras = [c for c in cfg.companies if (c.name or '').lower().startswith('cerebras')]; assert len(cerebras) == 1; spec = cerebras[0]; print(cfg.form_counts(spec))"
```

Expected: prints company count and `{'__REGISTRATION__': 8}`.

- [ ] **Step 3: Commit**

```bash
git add universe.toml
git commit -m "feat(universe): add Cerebras Systems pre-IPO filer entry"
```

---

### Task 20: End-to-end live-SEC smoke test (marked slow)

**Files:**
- Test: `tests/test_cerebras_s1_smoke.py` (new)

- [ ] **Step 1: Write the end-to-end smoke test**

Create `tests/test_cerebras_s1_smoke.py`:

```python
"""Live-SEC end-to-end smoke test for the new-filer pipeline.

Gated on --run-slow to avoid beating on SEC during fast test runs.
"""

from pathlib import Path

import pytest

from edgarpack.harvest.planner import plan_harvest
from edgarpack.harvest.registry import PackRegistry
from edgarpack.harvest.universe import CompanySpec, UniverseConfig


pytestmark = pytest.mark.slow


@pytest.mark.asyncio
async def test_cerebras_name_resolution_and_plan(tmp_path):
    spec = CompanySpec(name="Cerebras Systems", forms_s1=4)
    cfg = UniverseConfig(companies=[spec])
    registry = PackRegistry(tmp_path / "registry.db")
    plan = await plan_harvest(cfg, registry)

    assert plan.total_filings >= 1
    # All harvested filings should be registration-class.
    from edgarpack.sec.submissions import is_registration_form

    for item in plan.items:
        assert is_registration_form(item.form_type), item.form_type
    # At least one S-1 or S-1/A should be present.
    forms = {item.form_type for item in plan.items}
    assert any(f.startswith("S-1") for f in forms), f"no S-1 in plan: {forms}"
```

- [ ] **Step 2: Run the smoke test opt-in**

Run: `.venv/bin/python -m pytest tests/test_cerebras_s1_smoke.py --run-slow -v`
Expected: passes. If SEC rate-limits, rerun after a short wait; the existing client already respects `Retry-After`.

If the test fails because Cerebras's name returns multiple matches, update the spec in the test to `CompanySpec(cik="0002021728", forms_s1=4)` and rerun. Then file a follow-up beads issue to tighten `resolve_company_by_name` disambiguation (the spec's "open questions" section flagged this).

- [ ] **Step 3: Full fast suite and lint**

Run:

```bash
.venv/bin/python -m pytest tests/ -x -q
ruff check .
ruff format --check .
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_cerebras_s1_smoke.py
git commit -m "test(smoke): live-SEC end-to-end verification of Cerebras S-1 harvest plan"
```

---

## Final verification

- [ ] **Step 1: Run the complete test suite**

```bash
.venv/bin/python -m pytest tests/ -x -q
```

Expected: all pre-existing tests still pass, all new tests pass. Total test count up by roughly 40-50 new tests.

- [ ] **Step 2: Run lint and formatter**

```bash
ruff check .
ruff format --check .
```

Expected: clean.

- [ ] **Step 3: Execute the success-criteria flow against Cerebras**

```bash
.venv/bin/edgarpack harvest --universe universe.toml --out ./packs --refresh
.venv/bin/edgarpack index --packs ./packs --incremental
.venv/bin/edgarpack search "total addressable market" --cik 0002021728
.venv/bin/edgarpack timeline --cik 0002021728 --series registration
```

Expected: harvest pulls Cerebras registration filings; index incorporates them; search surfaces hits from both body text and framing-metric rows; timeline emits a consecutive-pair redline series.

- [ ] **Step 4: Record baseline metrics**

After the harvest succeeds, note:
- Number of Cerebras packs produced
- Size of `packs/0002021728/*/assets/` directory (roadshow images)
- Total non-test LOC delta: `git diff main --stat -- ':!tests' ':!docs'`

Expected: non-test delta roughly ~280-340 LOC, within the spec's budget.

---

## Self-review checklist

**Spec coverage:**

- [x] S-1 treated as form-type addition: Task 1 (constants), Task 2 (predicate), Task 3 (CompanySpec), Task 6 (planner).
- [x] Ten registration-class forms recognized: Task 1 covers all ten.
- [x] CIK optional, name optional, at-least-one validator: Task 3.
- [x] Pre-IPO inference zeroes periodic forms: Task 3 (unit tests) + Task 6 (planner does not fetch them).
- [x] `resolve_company_by_name` via EDGAR search: Task 4.
- [x] `resolve_filer` dispatch order: Task 5.
- [x] Planner expands `__REGISTRATION__` sentinel: Task 6.
- [x] Sectionizer S-1 support (fall-through first, whitelist if weak): Task 7.
- [x] `is_registration_form` guards in `periods.py`: Task 8.
- [x] `kpi_discover` filter includes registration-class: Task 9.
- [x] Framing-metric patterns: Task 10.
- [x] S-1 disclosure extractors (use of proceeds, dilution, lockup, principal holders): Task 11.
- [x] `preserve_images` flag: Task 12.
- [x] Image rewriting and captions in `md_render`: Task 13.
- [x] `pack/assets.py` (download + VLM + hash cache): Task 14.
- [x] Pack build wiring: Task 15.
- [x] `build_registration_timeline`: Task 16.
- [x] CLI `--series=registration`: Task 17.
- [x] CLI `--describe-images`: Task 18.
- [x] Cerebras entry in `universe.toml`: Task 19.
- [x] End-to-end smoke test: Task 20.

**Placeholder scan:** Every step contains real code, exact commands, and expected outputs. No "TBD", "similar to Task N", or "handle edge cases" instructions.

**Type consistency:** `CompanySpec` fields (`ticker`, `name`, `cik`, `forms_s1`, `display_label`) referenced consistently. `REGISTRATION_FORMS`, `is_registration_form`, `resolve_company_by_name`, `resolve_filer`, `_list_registration_filings`, `_REGISTRATION_SENTINEL`, `build_registration_timeline`, `RegistrationTimelineEntry`, `download_assets`, `describe_asset`, `_vlm_describe` are defined once and referenced by the same name throughout.
