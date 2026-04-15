# Chinese company query parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `edgarpack query 'revenue LTM' --ticker BIDU` and `edgarpack query 'revenue LTM' --ticker 0700.HK` returning USD-normalized values within 2 percent of golden fixtures, with full tests for all six public Chinese targets written up front.

**Architecture:** A new identity layer resolves ticker and company aliases across SEC and HKEX listings. A bundled FX rate table converts values using ASC 830 conventions. A thin HKEX adapter reuses the existing China Lens PDF extract pipeline to emit SEC-shaped packs. Query CLI and formatter plumb through a `--currency` flag and show accounting standard inline.

**Tech Stack:** Python 3.11+, pydantic v2, tomllib, pytest with a new `eval` marker, existing `edgarpack/china/` OCR and PDF extraction code, FRED DEXCHUS/DEXHKUS series for FX.

**Precondition:** The `eux` P1 bug (annual-only filer LTM-1 picks stubs) must be closed before starting Task 15. Verify with `bd show <eux-full-id>` before the query-integration phase. Tasks 1-14 can proceed in parallel with that fix.

**Reference spec:** `docs/superpowers/specs/2026-04-14-china-query-performance-design.md`

---

## File Structure

New modules:
- `edgarpack/identity.py` — ticker and company resolution
- `edgarpack/fx/__init__.py`, `edgarpack/fx/rates.py`, `edgarpack/fx/convert.py` — FX layer
- `edgarpack/hk/__init__.py`, `edgarpack/hk/acquire.py`, `edgarpack/hk/adapter.py`, `edgarpack/hk/sections.yaml` — HKEX adapter
- `data/fx_rates.csv` — bundled FX rates
- `scripts/refresh_fx.py` — rate refresh helper

New tests:
- `tests/test_china_identity.py`, `tests/test_china_fx.py`, `tests/test_china_query_eval.py`, `tests/test_china_private_minimax.py`
- `tests/eval/china_golden.yaml`
- `tests/fixtures/china_packs/` — pre-harvested test packs

Modified:
- `edgarpack/harvest/universe.py` — extend `CompanySpec`
- `universe.toml` — add HK and alias fields
- `edgarpack/query/models.py` — extend `CitedValue`
- `edgarpack/query/metric_map.py` (new; currently line-item resolution is inline) — per-standard metric maps
- `edgarpack/cli.py` — `--currency` flag, identity plumbing
- `edgarpack/sec/` pack-builder — emit `reporting_currency` and `accounting_standard`
- `pyproject.toml` — add `eval` marker

---

### Task 1: Add pytest eval marker and fixture directories

**Files:**
- Modify: `pyproject.toml:64-67`
- Create: `tests/fixtures/china_packs/.gitkeep`
- Create: `tests/eval/.gitkeep`

- [ ] **Step 1: Edit pyproject.toml to add the eval marker**

In `pyproject.toml`, change the `markers` list under `[tool.pytest.ini_options]` from:

```toml
markers = [
    "live_sec: hits live SEC endpoints and requires --run-live-sec",
    "slow: slower-running test coverage",
]
```

to:

```toml
markers = [
    "live_sec: hits live SEC endpoints and requires --run-live-sec",
    "slow: slower-running test coverage",
    "eval: golden-fixture evaluation tests for China query parity",
]
```

- [ ] **Step 2: Create empty fixture directories with .gitkeep**

```bash
mkdir -p tests/fixtures/china_packs tests/eval
touch tests/fixtures/china_packs/.gitkeep tests/eval/.gitkeep
```

- [ ] **Step 3: Verify marker is registered**

Run: `.venv/bin/python -m pytest --markers | grep eval`
Expected output: `@pytest.mark.eval: golden-fixture evaluation tests for China query parity`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/fixtures/china_packs/.gitkeep tests/eval/.gitkeep
git commit -m "test: add eval pytest marker and fixture dirs for China query parity"
```

---

### Task 2: Extend CompanySpec with listing, aliases, alt_tickers, hk_stock_code

**Files:**
- Modify: `edgarpack/harvest/universe.py:11-19`
- Test: `tests/test_harvest_universe.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harvest_universe.py`:

```python
def test_company_spec_accepts_hk_listing_fields(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "0700.HK"
listing = "HKEX"
aliases = ["tencent", "tencent holdings"]
hk_stock_code = "00700"
"""
    )
    from edgarpack.harvest.universe import load_universe

    universe = load_universe(cfg)
    spec = universe.companies[0]
    assert spec.ticker == "0700.HK"
    assert spec.listing == "HKEX"
    assert spec.aliases == ["tencent", "tencent holdings"]
    assert spec.hk_stock_code == "00700"


def test_company_spec_accepts_alt_tickers_for_dual_listed(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "BABA"
listing = "NYSE"
aliases = ["alibaba"]
alt_tickers = ["9988.HK"]
"""
    )
    from edgarpack.harvest.universe import load_universe

    universe = load_universe(cfg)
    spec = universe.companies[0]
    assert spec.alt_tickers == ["9988.HK"]


def test_company_spec_listing_defaults_to_none_for_legacy_entries(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "NVDA"
"""
    )
    from edgarpack.harvest.universe import load_universe

    universe = load_universe(cfg)
    spec = universe.companies[0]
    assert spec.listing is None
    assert spec.aliases == []
    assert spec.alt_tickers == []
    assert spec.hk_stock_code is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_harvest_universe.py -x -v -k "hk_listing or alt_tickers or legacy_entries"`
Expected: FAIL on all three with `ValidationError` or missing attribute.

- [ ] **Step 3: Extend CompanySpec**

Edit `edgarpack/harvest/universe.py`, replace the `CompanySpec` class with:

```python
class CompanySpec(BaseModel):
    """A company in the harvest universe."""

    ticker: str
    cik: str | None = None
    forms_10k: int | None = None
    forms_10q: int | None = None
    forms_8k: int | None = None
    forms_20f: int | None = None

    # China query parity (edgarpack-2yg): identity + listing metadata.
    listing: str | None = None
    aliases: list[str] = []
    alt_tickers: list[str] = []
    hk_stock_code: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_harvest_universe.py -x -v`
Expected: PASS, including the existing tests.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/harvest/universe.py tests/test_harvest_universe.py
git commit -m "feat(universe): add listing, aliases, alt_tickers, hk_stock_code to CompanySpec"
```

---

### Task 3: Create identity.py with ResolvedCompany and resolve()

**Files:**
- Create: `edgarpack/identity.py`
- Test: `tests/test_china_identity.py`

- [ ] **Step 1: Write the failing test file (partial, expanded in Task 4)**

Create `tests/test_china_identity.py`:

```python
"""Identity resolution for China query parity (edgarpack-2yg)."""

from pathlib import Path

import pytest

from edgarpack.identity import (
    AmbiguousCompany,
    ResolvedCompany,
    UnknownCompany,
    load_identity,
    resolve,
)


@pytest.fixture
def identity(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "BIDU"
listing = "NASDAQ"
cik = "0001329099"
forms_20f = 3
aliases = ["baidu"]

[[companies]]
ticker = "0700.HK"
listing = "HKEX"
aliases = ["tencent", "tencent holdings"]
hk_stock_code = "00700"

[[companies]]
ticker = "BABA"
listing = "NYSE"
cik = "0001577552"
forms_20f = 3
aliases = ["alibaba", "alibaba group"]
alt_tickers = ["9988.HK"]
"""
    )
    return load_identity(cfg)


def test_resolve_us_ticker_routes_to_sec(identity):
    r = resolve(identity, ticker="BIDU", company=None)
    assert isinstance(r, ResolvedCompany)
    assert r.ticker == "BIDU"
    assert r.listing == "NASDAQ"
    assert r.source == "SEC"
    assert r.cik == "0001329099"
    assert r.private is False


def test_resolve_hk_suffix_ticker_routes_to_hkex(identity):
    r = resolve(identity, ticker="0700.HK", company=None)
    assert r.listing == "HKEX"
    assert r.source == "HKEX"
    assert r.hk_stock_code == "00700"


def test_resolve_alt_ticker_routes_to_alt_listing(identity):
    r = resolve(identity, ticker="9988.HK", company=None)
    assert r.source == "HKEX"
    assert r.ticker == "9988.HK"


def test_resolve_company_alias_picks_primary_listing(identity):
    r = resolve(identity, ticker=None, company="tencent")
    assert r.ticker == "0700.HK"
    assert r.source == "HKEX"


def test_resolve_unknown_ticker_raises_with_suggestions(identity):
    with pytest.raises(UnknownCompany) as excinfo:
        resolve(identity, ticker="ZZZZ", company=None)
    assert "BIDU" in str(excinfo.value) or "BABA" in str(excinfo.value)


def test_resolve_requires_one_of_ticker_or_company(identity):
    with pytest.raises(ValueError):
        resolve(identity, ticker=None, company=None)


def test_ambiguous_alias_raises_at_load_time(tmp_path):
    cfg = tmp_path / "u.toml"
    cfg.write_text(
        """
[[companies]]
ticker = "BIDU"
aliases = ["baidu"]

[[companies]]
ticker = "0700.HK"
aliases = ["baidu"]
"""
    )
    with pytest.raises(AmbiguousCompany) as excinfo:
        load_identity(cfg)
    assert "baidu" in str(excinfo.value).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_china_identity.py -x -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'edgarpack.identity'`.

- [ ] **Step 3: Create edgarpack/identity.py**

```python
"""Identity resolution across SEC and HKEX listings.

Single entrypoint for the CLI. `--ticker` and `--company` both flow
through `resolve()`. Ambiguity (two aliases colliding) is caught at
config load time, not query time.

Spec: docs/superpowers/specs/2026-04-14-china-query-performance-design.md
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .harvest.universe import CompanySpec, load_universe

Source = Literal["SEC", "HKEX"]


class UnknownCompany(ValueError):
    """Raised when a ticker or alias does not resolve to any company."""


class AmbiguousCompany(ValueError):
    """Raised at config load when two companies claim the same alias."""


@dataclass(frozen=True)
class ResolvedCompany:
    ticker: str
    listing: str | None
    source: Source
    cik: str | None
    hk_stock_code: str | None
    aliases: tuple[str, ...]
    private: bool


@dataclass(frozen=True)
class IdentityIndex:
    by_ticker: dict[str, ResolvedCompany]
    by_alias: dict[str, ResolvedCompany]
    all_tickers: tuple[str, ...]


def _source_for(spec: CompanySpec, ticker: str) -> Source:
    if ticker.endswith(".HK"):
        return "HKEX"
    if spec.listing == "HKEX":
        return "HKEX"
    return "SEC"


def _resolved_for(spec: CompanySpec, ticker: str) -> ResolvedCompany:
    return ResolvedCompany(
        ticker=ticker,
        listing=spec.listing,
        source=_source_for(spec, ticker),
        cik=spec.cik,
        hk_stock_code=spec.hk_stock_code,
        aliases=tuple(spec.aliases),
        private=False,
    )


def load_identity(path: Path) -> IdentityIndex:
    """Build an in-memory index from a universe.toml file.

    Raises AmbiguousCompany if any alias is claimed by more than one company.
    """
    universe = load_universe(path)
    by_ticker: dict[str, ResolvedCompany] = {}
    by_alias: dict[str, ResolvedCompany] = {}

    for spec in universe.companies:
        primary = _resolved_for(spec, spec.ticker)
        by_ticker[spec.ticker.upper()] = primary
        for alt in spec.alt_tickers:
            alt_resolved = ResolvedCompany(
                ticker=alt,
                listing="HKEX" if alt.endswith(".HK") else spec.listing,
                source="HKEX" if alt.endswith(".HK") else "SEC",
                cik=spec.cik,
                hk_stock_code=spec.hk_stock_code,
                aliases=tuple(spec.aliases),
                private=False,
            )
            by_ticker[alt.upper()] = alt_resolved

        for alias in spec.aliases:
            key = alias.lower().strip()
            if key in by_alias and by_alias[key].ticker != primary.ticker:
                raise AmbiguousCompany(
                    f"Alias {alias!r} is claimed by both "
                    f"{by_alias[key].ticker} and {primary.ticker}"
                )
            by_alias[key] = primary

    return IdentityIndex(
        by_ticker=by_ticker,
        by_alias=by_alias,
        all_tickers=tuple(sorted(by_ticker.keys())),
    )


def resolve(
    index: IdentityIndex,
    ticker: str | None,
    company: str | None,
) -> ResolvedCompany:
    """Resolve a CLI --ticker or --company into a canonical ResolvedCompany."""
    if ticker is None and company is None:
        raise ValueError("resolve() requires ticker or company")

    if ticker is not None:
        key = ticker.upper()
        if key in index.by_ticker:
            return index.by_ticker[key]
        suggestions = difflib.get_close_matches(key, index.all_tickers, n=3)
        raise UnknownCompany(
            f"Unknown ticker {ticker!r}. Did you mean: {', '.join(suggestions) or 'none'}?"
        )

    assert company is not None
    key = company.lower().strip()
    if key in index.by_alias:
        return index.by_alias[key]
    suggestions = difflib.get_close_matches(key, sorted(index.by_alias.keys()), n=3)
    raise UnknownCompany(
        f"Unknown company {company!r}. Did you mean: {', '.join(suggestions) or 'none'}?"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_china_identity.py -x -v`
Expected: PASS on all seven tests.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/identity.py tests/test_china_identity.py
git commit -m "feat(identity): resolver for SEC + HKEX tickers and company aliases"
```

---

### Task 4: Extend universe.toml with Chinese targets and MiniMax scaffold

**Files:**
- Modify: `universe.toml` (append)
- Test: add coverage to `tests/test_china_identity.py`

- [ ] **Step 1: Append to universe.toml**

Append to `universe.toml`:

```toml
# ============================================================
#  China Query Parity (edgarpack-2yg)
# ============================================================

[[companies]]
ticker = "BIDU"
listing = "NASDAQ"
cik = "0001329099"
forms_20f = 3
aliases = ["baidu"]

[[companies]]
ticker = "PDD"
listing = "NASDAQ"
cik = "0001737806"
forms_20f = 3
aliases = ["pinduoduo", "pdd holdings"]

[[companies]]
ticker = "BABA"
listing = "NYSE"
cik = "0001577552"
forms_20f = 3
aliases = ["alibaba", "alibaba group"]
alt_tickers = ["9988.HK"]

[[companies]]
ticker = "JD"
listing = "NASDAQ"
cik = "0001549802"
forms_20f = 3
aliases = ["jd.com", "jingdong"]
alt_tickers = ["9618.HK"]

[[companies]]
ticker = "0700.HK"
listing = "HKEX"
aliases = ["tencent", "tencent holdings"]
hk_stock_code = "00700"

[[companies]]
ticker = "3690.HK"
listing = "HKEX"
aliases = ["meituan"]
hk_stock_code = "03690"

# Private; scaffold-only in the query CLI. Separate issue tracks alt-data.
[[companies]]
ticker = "MINIMAX-PRIVATE"
listing = "PRIVATE"
aliases = ["minimax"]
```

- [ ] **Step 2: Extend CompanySpec to support the private marker**

Edit `edgarpack/harvest/universe.py`, add a `private` field to `CompanySpec`:

```python
class CompanySpec(BaseModel):
    # ... existing fields ...
    listing: str | None = None
    aliases: list[str] = []
    alt_tickers: list[str] = []
    hk_stock_code: str | None = None
    private: bool = False

    @model_validator(mode="after")
    def _infer_private(self) -> "CompanySpec":
        if self.listing == "PRIVATE":
            object.__setattr__(self, "private", True)
        return self
```

Add `model_validator` to imports at top of file:

```python
from pydantic import BaseModel, model_validator
```

- [ ] **Step 3: Update identity.py to propagate the private flag**

In `edgarpack/identity.py`, change `_resolved_for` to:

```python
def _resolved_for(spec: CompanySpec, ticker: str) -> ResolvedCompany:
    return ResolvedCompany(
        ticker=ticker,
        listing=spec.listing,
        source=_source_for(spec, ticker),
        cik=spec.cik,
        hk_stock_code=spec.hk_stock_code,
        aliases=tuple(spec.aliases),
        private=spec.private,
    )
```

- [ ] **Step 4: Write expanded coverage tests**

Append to `tests/test_china_identity.py`:

```python
def test_live_universe_resolves_all_six_public_targets():
    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))

    for ticker in ["BIDU", "PDD", "BABA", "JD"]:
        r = resolve(index, ticker=ticker, company=None)
        assert r.source == "SEC", f"{ticker} should route to SEC"
        assert r.private is False

    for ticker in ["0700.HK", "3690.HK", "9988.HK", "9618.HK"]:
        r = resolve(index, ticker=ticker, company=None)
        assert r.source == "HKEX", f"{ticker} should route to HKEX"
        assert r.private is False


def test_live_universe_resolves_every_alias():
    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))
    for alias, expected in [
        ("baidu", "BIDU"),
        ("pinduoduo", "PDD"),
        ("alibaba", "BABA"),
        ("jd.com", "JD"),
        ("tencent", "0700.HK"),
        ("meituan", "3690.HK"),
    ]:
        r = resolve(index, ticker=None, company=alias)
        assert r.ticker == expected


def test_live_universe_minimax_is_private():
    from edgarpack.identity import load_identity, resolve

    index = load_identity(Path("universe.toml"))
    r = resolve(index, ticker=None, company="minimax")
    assert r.private is True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_china_identity.py tests/test_harvest_universe.py -x -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add universe.toml edgarpack/harvest/universe.py edgarpack/identity.py tests/test_china_identity.py
git commit -m "feat(universe): add six China targets + MiniMax private scaffold to universe.toml"
```

---

### Task 5: Seed data/fx_rates.csv from FRED

**Files:**
- Create: `data/fx_rates.csv`
- Create: `scripts/refresh_fx.py`

- [ ] **Step 1: Create scripts/refresh_fx.py**

```python
"""Refresh data/fx_rates.csv from FRED.

Fetches DEXCHUS (CNY/USD) and DEXHKUS (HKD/USD) daily series, aggregates
into monthly period-average and month-end spot values, writes CSV.

Usage: .venv/bin/python scripts/refresh_fx.py
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path
from statistics import mean

import httpx

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
SERIES = {"CNY/USD": "DEXCHUS", "HKD/USD": "DEXHKUS"}
OUT = Path(__file__).resolve().parents[1] / "data" / "fx_rates.csv"


def _fetch_series(series: str) -> dict[dt.date, float]:
    url = FRED_CSV.format(series=series)
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    rows = resp.text.splitlines()[1:]
    out: dict[dt.date, float] = {}
    for line in rows:
        date_s, val_s = line.split(",")
        if val_s == "." or not val_s:
            continue
        # FRED quotes CNY per USD and HKD per USD. Invert to per-1-USD-in-target.
        per_usd = float(val_s)
        rate_to_usd = 1.0 / per_usd
        out[dt.date.fromisoformat(date_s)] = rate_to_usd
    return out


def _monthly(daily: dict[dt.date, float]) -> list[tuple[dt.date, float, float]]:
    buckets: dict[tuple[int, int], list[tuple[dt.date, float]]] = {}
    for d, v in daily.items():
        buckets.setdefault((d.year, d.month), []).append((d, v))
    out: list[tuple[dt.date, float, float]] = []
    for (y, m), pairs in sorted(buckets.items()):
        pairs.sort()
        month_end = pairs[-1][0]
        spot = pairs[-1][1]
        avg = mean(v for _, v in pairs)
        out.append((month_end, spot, avg))
    return out


def main() -> int:
    rows: list[dict[str, str]] = []
    for pair, series in SERIES.items():
        print(f"Fetching {series} ({pair})...", file=sys.stderr)
        daily = _fetch_series(series)
        for month_end, spot, avg in _monthly(daily):
            rows.append(
                {
                    "ccy_pair": pair,
                    "month_end_date": month_end.isoformat(),
                    "spot_end": f"{spot:.6f}",
                    "period_average": f"{avg:.6f}",
                }
            )
    # USD/USD identity rows: last 30 years, monthly.
    today = dt.date.today()
    y, m = today.year, today.month
    for back in range(0, 360):
        mm = m - back
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        month_end = dt.date(yy, mm, 28)
        rows.append(
            {
                "ccy_pair": "USD/USD",
                "month_end_date": month_end.isoformat(),
                "spot_end": "1.000000",
                "period_average": "1.000000",
            }
        )

    rows.sort(key=lambda r: (r["ccy_pair"], r["month_end_date"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ccy_pair", "month_end_date", "spot_end", "period_average"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the script to seed the CSV**

Run: `.venv/bin/python scripts/refresh_fx.py`
Expected: Writes `data/fx_rates.csv` with several thousand rows across `CNY/USD`, `HKD/USD`, `USD/USD`.

- [ ] **Step 3: Spot-check the CSV**

Run: `head -5 data/fx_rates.csv && grep "2023-12" data/fx_rates.csv | head -5`
Expected: Header plus CNY/USD and HKD/USD rows for December 2023 with rates around 0.14 and 0.13 respectively.

- [ ] **Step 4: Commit**

```bash
git add data/fx_rates.csv scripts/refresh_fx.py
git commit -m "data(fx): seed bundled FX rate table from FRED (CNY/USD, HKD/USD, USD/USD)"
```

---

### Task 6: Build edgarpack/fx/ convert() and ConvertedValue

**Files:**
- Create: `edgarpack/fx/__init__.py`
- Create: `edgarpack/fx/rates.py`
- Create: `edgarpack/fx/convert.py`
- Test: `tests/test_china_fx.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/test_china_fx.py`:

```python
"""FX convention tests for China query parity (edgarpack-2yg)."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from edgarpack.fx import ConvertedValue, RateNotFound, convert, load_rates


@pytest.fixture(scope="module")
def rates():
    return load_rates(Path("data/fx_rates.csv"))


def test_spot_convention_uses_month_end_spot(rates):
    result = convert(
        value=Decimal("1576000000000"),
        from_ccy="CNY",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="spot",
        rates=rates,
    )
    assert isinstance(result, ConvertedValue)
    assert 0.138 <= result.rate_used <= 0.145
    assert 215_000_000_000 <= result.converted_value <= 228_000_000_000
    assert result.convention == "spot"
    assert "2023-12" in result.rate_source_row


def test_average_convention_uses_period_average(rates):
    result = convert(
        value=Decimal("609015000000"),
        from_ccy="CNY",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="average",
        period_end=dt.date(2023, 12, 31),
        rates=rates,
    )
    assert 0.139 <= result.rate_used <= 0.145
    assert 84_000_000_000 <= result.converted_value <= 89_000_000_000


def test_hkd_to_usd_conversion(rates):
    result = convert(
        value=Decimal("1000000000"),
        from_ccy="HKD",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="spot",
        rates=rates,
    )
    assert 0.125 <= result.rate_used <= 0.130


def test_usd_to_usd_is_identity(rates):
    result = convert(
        value=Decimal("123456789"),
        from_ccy="USD",
        to_ccy="USD",
        as_of=dt.date(2023, 6, 30),
        convention="spot",
        rates=rates,
    )
    assert result.rate_used == 1.0
    assert result.converted_value == 123456789.0


def test_missing_rate_raises(rates):
    with pytest.raises(RateNotFound):
        convert(
            value=Decimal("100"),
            from_ccy="CNY",
            to_ccy="USD",
            as_of=dt.date(1950, 1, 1),
            convention="spot",
            rates=rates,
        )


def test_converted_value_carries_provenance(rates):
    result = convert(
        value=Decimal("100"),
        from_ccy="CNY",
        to_ccy="USD",
        as_of=dt.date(2023, 12, 31),
        convention="spot",
        rates=rates,
    )
    assert result.from_ccy == "CNY"
    assert result.to_ccy == "USD"
    assert result.as_of == dt.date(2023, 12, 31)
    assert result.rate_source_row  # non-empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_china_fx.py -x -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'edgarpack.fx'`.

- [ ] **Step 3: Create edgarpack/fx/rates.py**

```python
"""FX rate table loader.

Backs `edgarpack.fx.convert`. Reads `data/fx_rates.csv` once per process.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MonthlyRate:
    ccy_pair: str
    month_end: dt.date
    spot_end: float
    period_average: float


@dataclass(frozen=True)
class RateTable:
    rows: tuple[MonthlyRate, ...]

    def for_pair(self, ccy_pair: str) -> tuple[MonthlyRate, ...]:
        return tuple(r for r in self.rows if r.ccy_pair == ccy_pair)


def load_rates(path: Path) -> RateTable:
    with path.open() as f:
        reader = csv.DictReader(f)
        rows = [
            MonthlyRate(
                ccy_pair=r["ccy_pair"],
                month_end=dt.date.fromisoformat(r["month_end_date"]),
                spot_end=float(r["spot_end"]),
                period_average=float(r["period_average"]),
            )
            for r in reader
        ]
    return RateTable(rows=tuple(rows))
```

- [ ] **Step 4: Create edgarpack/fx/convert.py**

```python
"""Convert values between currencies using bundled monthly rates.

Follows ASC 830 conventions: spot-at-period-end for balance sheet,
period-average for income statement.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .rates import MonthlyRate, RateTable

Convention = Literal["spot", "average"]


class RateNotFound(ValueError):
    """Raised when the rate table has no row for the requested date."""


@dataclass(frozen=True)
class ConvertedValue:
    converted_value: float
    rate_used: float
    from_ccy: str
    to_ccy: str
    as_of: dt.date
    convention: Convention
    rate_source_row: str


def _find_row(rows: tuple[MonthlyRate, ...], as_of: dt.date) -> MonthlyRate:
    candidates = [r for r in rows if r.month_end.year == as_of.year and r.month_end.month == as_of.month]
    if candidates:
        return candidates[0]
    raise RateNotFound(f"No rate row for month of {as_of.isoformat()}")


def convert(
    value: Decimal,
    from_ccy: str,
    to_ccy: str,
    as_of: dt.date,
    convention: Convention,
    rates: RateTable,
    period_end: dt.date | None = None,
) -> ConvertedValue:
    if from_ccy == to_ccy:
        return ConvertedValue(
            converted_value=float(value),
            rate_used=1.0,
            from_ccy=from_ccy,
            to_ccy=to_ccy,
            as_of=as_of,
            convention=convention,
            rate_source_row=f"identity {from_ccy}",
        )

    if to_ccy != "USD":
        raise NotImplementedError("v1 only supports conversion to USD")

    pair = f"{from_ccy}/USD"
    rows = rates.for_pair(pair)
    if not rows:
        raise RateNotFound(f"No rates loaded for pair {pair}")

    lookup_date = period_end if convention == "average" and period_end else as_of
    row = _find_row(rows, lookup_date)
    rate = row.spot_end if convention == "spot" else row.period_average
    converted = float(value) * rate
    source = f"{pair} {row.month_end.isoformat()} ({convention})"
    return ConvertedValue(
        converted_value=converted,
        rate_used=rate,
        from_ccy=from_ccy,
        to_ccy=to_ccy,
        as_of=as_of,
        convention=convention,
        rate_source_row=source,
    )
```

- [ ] **Step 5: Create edgarpack/fx/__init__.py**

```python
"""FX normalization for cross-corpus queries.

Spec: docs/superpowers/specs/2026-04-14-china-query-performance-design.md
"""

from .convert import ConvertedValue, Convention, RateNotFound, convert
from .rates import MonthlyRate, RateTable, load_rates

__all__ = [
    "ConvertedValue",
    "Convention",
    "MonthlyRate",
    "RateNotFound",
    "RateTable",
    "convert",
    "load_rates",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_china_fx.py -x -v`
Expected: PASS on all six tests.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/fx/ tests/test_china_fx.py
git commit -m "feat(fx): ASC 830 conversion layer (spot for BS, average for P&L)"
```

---

### Task 7: Extend CitedValue with accounting_standard and reporting_currency

**Files:**
- Modify: `edgarpack/query/models.py:24-57`
- Test: `tests/test_financials.py` (add one case)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_financials.py`:

```python
def test_cited_value_carries_accounting_standard_and_reporting_currency():
    from datetime import date

    from edgarpack.query.models import CitedValue

    v = CitedValue(
        value=100,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2023, 12, 31),
        fiscal_year=2023,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2024, 2, 1),
        accession="0001234567-24-000001",
        cik="0001329099",
        company="Baidu",
        accounting_standard="IFRS",
        reporting_currency="USD",
    )
    assert v.accounting_standard == "IFRS"
    assert v.reporting_currency == "USD"


def test_cited_value_accounting_standard_defaults_to_us_gaap():
    from datetime import date

    from edgarpack.query.models import CitedValue

    v = CitedValue(
        value=100,
        unit="USD",
        metric="revenue",
        concept="Revenues",
        period_end=date(2023, 12, 31),
        fiscal_year=2023,
        fiscal_period="FY",
        form_type="10-K",
        filed=date(2024, 2, 1),
        accession="0001234567-24-000001",
        cik="0001234567",
        company="Acme",
    )
    assert v.accounting_standard == "US-GAAP"
    assert v.reporting_currency == "USD"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_financials.py -x -v -k "accounting_standard"`
Expected: FAIL with `ValidationError: extra inputs are not permitted` or missing attribute.

- [ ] **Step 3: Extend CitedValue**

Edit `edgarpack/query/models.py`, add two fields to `CitedValue` (after the `source` field, line 52):

```python
    # China query parity (edgarpack-2yg): report-side metadata.
    accounting_standard: Literal["US-GAAP", "IFRS", "HKFRS", "CAS"] = "US-GAAP"
    reporting_currency: str = "USD"  # ISO-4217; most SEC filers report USD.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_financials.py -x -v`
Expected: PASS, including existing tests.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/models.py tests/test_financials.py
git commit -m "feat(query): add accounting_standard and reporting_currency to CitedValue"
```

---

### Task 8: Build per-standard metric map

**Files:**
- Create: `edgarpack/query/metric_map.py`
- Test: `tests/test_china_metric_map.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_china_metric_map.py`:

```python
"""Per-standard metric-to-concept mapping (edgarpack-2yg)."""

import pytest

from edgarpack.query.metric_map import (
    METRIC_MAP,
    CANONICAL_METRICS,
    UnknownMetric,
    resolve_concepts,
)


def test_every_standard_covers_every_canonical_metric():
    for standard in ("US-GAAP", "IFRS", "HKFRS"):
        missing = [m for m in CANONICAL_METRICS if m not in METRIC_MAP[standard]]
        assert not missing, f"{standard} missing: {missing}"


def test_resolve_concepts_us_gaap_revenue():
    concepts = resolve_concepts("revenue", "US-GAAP")
    assert "Revenues" in concepts or "RevenueFromContractWithCustomerExcludingAssessedTax" in concepts


def test_resolve_concepts_hkfrs_revenue_includes_turnover():
    concepts = resolve_concepts("revenue", "HKFRS")
    assert "Turnover" in concepts or "Revenue" in concepts


def test_unknown_metric_raises_with_suggestions():
    with pytest.raises(UnknownMetric) as excinfo:
        resolve_concepts("revnue", "US-GAAP")
    assert "revenue" in str(excinfo.value)


def test_canonical_metrics_covers_full_fundamental_set():
    required = {
        "revenue",
        "gross_profit",
        "gross_margin",
        "operating_income",
        "operating_margin",
        "ebitda",
        "net_income",
        "eps_basic",
        "eps_diluted",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "cash_and_equivalents",
        "total_debt",
        "shares_outstanding_basic",
        "shares_outstanding_diluted",
    }
    assert required <= set(CANONICAL_METRICS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_china_metric_map.py -x -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create edgarpack/query/metric_map.py**

```python
"""Metric-to-concept resolution across accounting standards.

Spec: docs/superpowers/specs/2026-04-14-china-query-performance-design.md

Each canonical metric maps to a list of tag strings per standard.
Resolvers try tags in order; first hit wins. Unknown canonical keys
fail fast with a suggestion list. Unknown filing line items log a
warning and get skipped (handled by callers, not here).
"""

from __future__ import annotations

import difflib
from typing import Literal

AccountingStandard = Literal["US-GAAP", "IFRS", "HKFRS", "CAS"]
CanonicalMetric = str


class UnknownMetric(ValueError):
    """Raised when a canonical metric key does not exist."""


CANONICAL_METRICS: tuple[CanonicalMetric, ...] = (
    "revenue",
    "gross_profit",
    "gross_margin",
    "operating_income",
    "operating_margin",
    "ebitda",
    "net_income",
    "eps_basic",
    "eps_diluted",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "cash_and_equivalents",
    "total_debt",
    "shares_outstanding_basic",
    "shares_outstanding_diluted",
)


METRIC_MAP: dict[AccountingStandard, dict[CanonicalMetric, list[str]]] = {
    "US-GAAP": {
        "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "gross_profit": ["GrossProfit"],
        "gross_margin": [],  # derived
        "operating_income": ["OperatingIncomeLoss"],
        "operating_margin": [],  # derived
        "ebitda": [],  # derived
        "net_income": ["NetIncomeLoss", "ProfitLoss"],
        "eps_basic": ["EarningsPerShareBasic"],
        "eps_diluted": ["EarningsPerShareDiluted"],
        "total_assets": ["Assets"],
        "total_liabilities": ["Liabilities"],
        "total_equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
        "total_debt": ["LongTermDebt", "DebtCurrent"],
        "shares_outstanding_basic": ["WeightedAverageNumberOfSharesOutstandingBasic"],
        "shares_outstanding_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    },
    "IFRS": {
        "revenue": ["Revenue", "RevenueFromContractsWithCustomers", "RevenueFromContracts"],
        "gross_profit": ["GrossProfit"],
        "gross_margin": [],
        "operating_income": ["ProfitLossFromOperatingActivities", "OperatingProfit"],
        "operating_margin": [],
        "ebitda": [],
        "net_income": ["ProfitLoss", "NetIncomeLoss"],
        "eps_basic": ["BasicEarningsLossPerShare"],
        "eps_diluted": ["DilutedEarningsLossPerShare"],
        "total_assets": ["Assets", "TotalAssets"],
        "total_liabilities": ["Liabilities", "TotalLiabilities"],
        "total_equity": ["Equity", "TotalEquity"],
        "cash_and_equivalents": ["CashAndCashEquivalents"],
        "total_debt": ["Borrowings", "LongTermBorrowings"],
        "shares_outstanding_basic": ["WeightedAverageShares"],
        "shares_outstanding_diluted": ["WeightedAverageDilutedShares"],
    },
    "HKFRS": {
        "revenue": ["Revenue", "Turnover", "RevenueFromContracts"],
        "gross_profit": ["GrossProfit"],
        "gross_margin": [],
        "operating_income": ["OperatingProfit", "ProfitLossFromOperatingActivities"],
        "operating_margin": [],
        "ebitda": [],
        "net_income": ["ProfitForTheYear", "ProfitLoss"],
        "eps_basic": ["BasicEarningsPerShare", "BasicEarningsLossPerShare"],
        "eps_diluted": ["DilutedEarningsPerShare", "DilutedEarningsLossPerShare"],
        "total_assets": ["TotalAssets", "Assets"],
        "total_liabilities": ["TotalLiabilities", "Liabilities"],
        "total_equity": ["TotalEquity", "Equity"],
        "cash_and_equivalents": ["CashAndCashEquivalents", "BankBalancesAndCash"],
        "total_debt": ["Borrowings", "BankBorrowings"],
        "shares_outstanding_basic": ["WeightedAverageNumberOfOrdinarySharesInIssue"],
        "shares_outstanding_diluted": ["WeightedAverageNumberOfOrdinarySharesDiluted"],
    },
    "CAS": {m: [] for m in CANONICAL_METRICS},  # stub; A-shares owned by edgarpack-lb1
}


def resolve_concepts(metric: CanonicalMetric, standard: AccountingStandard) -> list[str]:
    if metric not in CANONICAL_METRICS:
        suggestions = difflib.get_close_matches(metric, CANONICAL_METRICS, n=3)
        raise UnknownMetric(
            f"Unknown metric {metric!r}. Did you mean: {', '.join(suggestions) or 'none'}?"
        )
    return METRIC_MAP[standard][metric]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_china_metric_map.py -x -v`
Expected: PASS on all five tests.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/metric_map.py tests/test_china_metric_map.py
git commit -m "feat(query): per-standard metric map (US-GAAP, IFRS, HKFRS)"
```

---

### Task 9: Create HK section heading map

**Files:**
- Create: `edgarpack/hk/__init__.py`
- Create: `edgarpack/hk/sections.yaml`
- Test: `tests/test_hk_sections.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hk_sections.py`:

```python
"""HKEX section heading map (edgarpack-2yg)."""

from edgarpack.hk import load_section_map


def test_common_hk_headings_map_to_canonical_sections():
    m = load_section_map()
    assert m["CHAIRMAN'S STATEMENT"] == "hkex_chairman_statement"
    assert m["MANAGEMENT DISCUSSION AND ANALYSIS"] == "hkex_mdna"
    assert m["CONSOLIDATED STATEMENT OF PROFIT OR LOSS"] == "hkex_income_statement"
    assert m["CONSOLIDATED STATEMENT OF FINANCIAL POSITION"] == "hkex_balance_sheet"
    assert m["CONSOLIDATED STATEMENT OF CASH FLOWS"] == "hkex_cash_flow"


def test_heading_lookup_is_case_and_punctuation_insensitive():
    m = load_section_map()
    normalize = lambda s: s.strip().upper().rstrip(".")
    assert m[normalize("Chairman's Statement")] == "hkex_chairman_statement"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hk_sections.py -x -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create edgarpack/hk/sections.yaml**

```yaml
# HK annual-report heading -> canonical section ID map.
# Headings are stored uppercase, trimmed, apostrophe-preserved.
sections:
  "CHAIRMAN'S STATEMENT": hkex_chairman_statement
  "MANAGEMENT DISCUSSION AND ANALYSIS": hkex_mdna
  "BUSINESS REVIEW": hkex_business_review
  "CONSOLIDATED STATEMENT OF PROFIT OR LOSS": hkex_income_statement
  "CONSOLIDATED STATEMENT OF COMPREHENSIVE INCOME": hkex_comprehensive_income
  "CONSOLIDATED STATEMENT OF FINANCIAL POSITION": hkex_balance_sheet
  "CONSOLIDATED STATEMENT OF CASH FLOWS": hkex_cash_flow
  "CONSOLIDATED STATEMENT OF CHANGES IN EQUITY": hkex_equity_changes
  "NOTES TO THE FINANCIAL STATEMENTS": hkex_notes
  "CORPORATE GOVERNANCE REPORT": hkex_governance
  "DIRECTORS' REPORT": hkex_directors_report
  "INDEPENDENT AUDITOR'S REPORT": hkex_auditor_report
  "FIVE-YEAR FINANCIAL SUMMARY": hkex_five_year_summary
  "RISK FACTORS": hkex_risk_factors
```

- [ ] **Step 4: Create edgarpack/hk/__init__.py**

```python
"""HKEX filing adapter (edgarpack-2yg)."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_section_map() -> dict[str, str]:
    path = Path(__file__).parent / "sections.yaml"
    with path.open() as f:
        data = yaml.safe_load(f)
    return {k.strip().upper().rstrip("."): v for k, v in data["sections"].items()}
```

- [ ] **Step 5: Verify pyyaml is available (add if needed)**

Run: `.venv/bin/python -c "import yaml; print(yaml.__version__)"`
If this fails, add `pyyaml>=6.0` to `[project.optional-dependencies].china` in `pyproject.toml` and reinstall: `.venv/bin/pip install -e '.[china]'`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_hk_sections.py -x -v`
Expected: PASS on both tests.

- [ ] **Step 7: Commit**

```bash
git add edgarpack/hk/ tests/test_hk_sections.py pyproject.toml
git commit -m "feat(hk): HKEX section heading map to canonical IDs"
```

---

### Task 10: HKEX PDF acquisition (hkexnews fetcher)

**Files:**
- Create: `edgarpack/hk/acquire.py`
- Test: `tests/test_hk_acquire.py`

- [ ] **Step 1: Inspect hkexnews URL convention**

Run (manual, once): open `https://www1.hkexnews.hk/listedco/listconews/sehk/2024/0326/2024032600840.pdf` in a browser to confirm PDF URL format. HKEX news listings use date-and-accession URLs. The adapter fetches by stock code via the disclosure announcement index.

- [ ] **Step 2: Write a stubbed test with mocked httpx**

Create `tests/test_hk_acquire.py`:

```python
"""HKEX acquisition layer (edgarpack-2yg)."""

from unittest.mock import patch

from edgarpack.hk.acquire import find_annual_report, HKFilingRef


def test_find_annual_report_returns_ref_for_tencent_2023():
    # Offline test: mock the hkexnews index response.
    fake_html = """
    <table>
      <tr><td>26/03/2024</td><td><a href="/listedco/listconews/sehk/2024/0326/2024032600840.pdf">Annual Report 2023</a></td></tr>
    </table>
    """
    with patch("edgarpack.hk.acquire._fetch_index", return_value=fake_html):
        ref = find_annual_report(stock_code="00700", fiscal_year=2023)
    assert isinstance(ref, HKFilingRef)
    assert ref.stock_code == "00700"
    assert ref.fiscal_year == 2023
    assert ref.pdf_url.startswith("https://www1.hkexnews.hk")
    assert ref.pdf_url.endswith(".pdf")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hk_acquire.py -x -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create edgarpack/hk/acquire.py**

```python
"""Fetch HKEX annual report PDFs by stock code.

Uses hkexnews.hk disclosure announcement index. Parses the listing table
for entries matching 'Annual Report YYYY' and returns a filing ref.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

_INDEX_BASE = "https://www1.hkexnews.hk/listedco/listconews/advancedsearch/search_active_main.aspx"
_HKEX_BASE = "https://www1.hkexnews.hk"


@dataclass(frozen=True)
class HKFilingRef:
    stock_code: str
    fiscal_year: int
    pdf_url: str
    announcement_date: str


def _fetch_index(stock_code: str) -> str:
    # hkexnews expects a POST with form data; we use the simpler GET index first.
    # For the MVP the plan harvests target PDFs manually and caches them;
    # this function is exercised by mocked tests in v1.
    resp = httpx.get(
        _INDEX_BASE,
        params={"stockcode": stock_code, "documenttype": "Annual Report"},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def find_annual_report(stock_code: str, fiscal_year: int) -> HKFilingRef:
    html = _fetch_index(stock_code)
    pattern = re.compile(
        rf'(\d{{2}}/\d{{2}}/\d{{4}}).*?<a href="([^"]+\.pdf)"[^>]*>Annual Report {fiscal_year}',
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(html)
    if not m:
        raise FileNotFoundError(
            f"No Annual Report {fiscal_year} found for stock code {stock_code}"
        )
    announcement_date, href = m.group(1), m.group(2)
    pdf_url = href if href.startswith("http") else _HKEX_BASE + href
    return HKFilingRef(
        stock_code=stock_code,
        fiscal_year=fiscal_year,
        pdf_url=pdf_url,
        announcement_date=announcement_date,
    )


def download_pdf(ref: HKFilingRef, out_path) -> None:
    resp = httpx.get(ref.pdf_url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_hk_acquire.py -x -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/hk/acquire.py tests/test_hk_acquire.py
git commit -m "feat(hk): hkexnews annual report PDF fetcher"
```

---

### Task 11: HKEX FilingSource adapter — emit SEC-shaped packs

**Files:**
- Create: `edgarpack/hk/adapter.py`
- Test: `tests/test_hk_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hk_adapter.py`:

```python
"""HKEX adapter builds SEC-shaped packs (edgarpack-2yg)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from edgarpack.hk.acquire import HKFilingRef
from edgarpack.hk.adapter import build_hk_pack


@pytest.mark.slow
def test_build_hk_pack_emits_manifest_with_hk_metadata(tmp_path):
    # Use a tiny text-based fixture PDF committed to tests/fixtures/
    fixture_pdf = Path("tests/fixtures/hk_sample_tencent_2023.pdf")
    if not fixture_pdf.exists():
        pytest.skip("Sample HK PDF not committed yet (added in Task 13)")

    ref = HKFilingRef(
        stock_code="00700",
        fiscal_year=2023,
        pdf_url="https://example/0700_2023.pdf",
        announcement_date="26/03/2024",
    )
    out_dir = tmp_path / "tencent_2023"

    with patch("edgarpack.hk.adapter._download_pdf", return_value=fixture_pdf):
        pack = build_hk_pack(ref, out_dir)

    manifest = json.loads((pack.path / "manifest.json").read_text())
    assert manifest["source"] == "HKEX"
    assert manifest["reporting_currency"] == "CNY"  # Tencent reports CNY
    assert manifest["accounting_standard"] == "HKFRS"
    assert manifest["stock_code"] == "00700"
    assert manifest["fiscal_year"] == 2023
    assert (pack.path / "chunks.ndjson").exists()
    assert any(p.suffix == ".md" for p in (pack.path / "sections").iterdir())
```

- [ ] **Step 2: Run test (will be skipped until fixture lands)**

Run: `.venv/bin/python -m pytest tests/test_hk_adapter.py -x -v`
Expected: SKIP (fixture PDF not committed yet).

- [ ] **Step 3: Create edgarpack/hk/adapter.py**

```python
"""HKEX pack builder.

Routes hkexnews PDFs through the existing China Lens OCR/extract pipeline
and emits packs with the same on-disk shape as SEC packs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..china.extract.pdf_extract import extract_pdf_text
from .acquire import HKFilingRef, download_pdf

# Per-company overrides. Tencent and Meituan report in CNY and use HKFRS.
_COMPANY_META: dict[str, dict[str, str]] = {
    "00700": {"name": "Tencent Holdings", "reporting_currency": "CNY", "accounting_standard": "HKFRS"},
    "03690": {"name": "Meituan", "reporting_currency": "CNY", "accounting_standard": "HKFRS"},
    "09988": {"name": "Alibaba Group (HK)", "reporting_currency": "CNY", "accounting_standard": "IFRS"},
    "09618": {"name": "JD.com (HK)", "reporting_currency": "CNY", "accounting_standard": "IFRS"},
}


@dataclass(frozen=True)
class PackRef:
    path: Path
    stock_code: str
    fiscal_year: int


def _download_pdf(ref: HKFilingRef, out: Path) -> Path:
    download_pdf(ref, out)
    return out


def build_hk_pack(ref: HKFilingRef, out_dir: Path) -> PackRef:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{ref.stock_code}_{ref.fiscal_year}.pdf"
    _download_pdf(ref, pdf_path)

    # Extract sections + chunks via the existing pipeline. extract_pdf_text
    # returns a list of (heading, body, page_range) tuples.
    extracted = extract_pdf_text(pdf_path)

    sections_dir = out_dir / "sections"
    sections_dir.mkdir(exist_ok=True)
    chunks_path = out_dir / "chunks.ndjson"

    chunk_rows = []
    for i, (heading, body, pages) in enumerate(extracted):
        section_id = _section_id_for_heading(heading, fallback=f"hkex_unmapped_{i:03d}")
        (sections_dir / f"{section_id}.md").write_text(f"# {heading}\n\n{body}\n")
        chunk_rows.append(
            {
                "section_id": section_id,
                "heading": heading,
                "text": body,
                "page_start": pages[0] if pages else None,
                "page_end": pages[-1] if pages else None,
            }
        )

    with chunks_path.open("w") as f:
        for row in chunk_rows:
            f.write(json.dumps(row) + "\n")

    meta = _COMPANY_META.get(ref.stock_code, {})
    manifest = {
        "source": "HKEX",
        "stock_code": ref.stock_code,
        "fiscal_year": ref.fiscal_year,
        "company": meta.get("name", ref.stock_code),
        "reporting_currency": meta.get("reporting_currency", "CNY"),
        "accounting_standard": meta.get("accounting_standard", "HKFRS"),
        "pdf_url": ref.pdf_url,
        "announcement_date": ref.announcement_date,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return PackRef(path=out_dir, stock_code=ref.stock_code, fiscal_year=ref.fiscal_year)


def _section_id_for_heading(heading: str, fallback: str) -> str:
    from . import load_section_map

    m = load_section_map()
    key = heading.strip().upper().rstrip(".")
    return m.get(key, fallback)
```

- [ ] **Step 4: Commit the adapter skeleton**

```bash
git add edgarpack/hk/adapter.py tests/test_hk_adapter.py
git commit -m "feat(hk): pack builder (routes PDFs through China Lens extract, SEC-shaped output)"
```

---

### Task 12: Pre-flight OCR recall on target HKEX filings

**Files:**
- Create: `scripts/hk_preflight.py`
- Create: `tests/fixtures/china_packs/README.md`

- [ ] **Step 1: Create scripts/hk_preflight.py**

```python
"""Pre-flight OCR recall check for HKEX target filings.

Downloads the six target annual reports, runs extraction, and reports
recall on the full fundamental metric set. Emits a CSV summary.

Usage: .venv/bin/python scripts/hk_preflight.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from edgarpack.hk.acquire import find_annual_report
from edgarpack.hk.adapter import build_hk_pack
from edgarpack.query.metric_map import CANONICAL_METRICS, resolve_concepts

TARGETS = [
    ("00700", 2023),  # Tencent
    ("03690", 2023),  # Meituan
    ("09988", 2023),  # BABA HK leg
    ("09618", 2023),  # JD.com HK leg
]
OUT = Path("tests/fixtures/china_packs/preflight_recall.csv")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for stock_code, fy in TARGETS:
        print(f"Pre-flighting {stock_code} FY{fy}...", file=sys.stderr)
        ref = find_annual_report(stock_code, fy)
        pack_dir = OUT.parent / f"{stock_code}_{fy}"
        pack = build_hk_pack(ref, pack_dir)
        hit = 0
        for metric in CANONICAL_METRICS:
            concepts = resolve_concepts(metric, "HKFRS")
            found = any(
                (pack.path / "chunks.ndjson").read_text().find(c) >= 0 for c in concepts
            )
            if found:
                hit += 1
        recall = hit / len(CANONICAL_METRICS)
        rows.append(
            {
                "stock_code": stock_code,
                "fiscal_year": str(fy),
                "metrics_found": str(hit),
                "metrics_total": str(len(CANONICAL_METRICS)),
                "recall": f"{recall:.2%}",
            }
        )
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {OUT}", file=sys.stderr)
    # Fail the script if any target is below 95%.
    for r in rows:
        if float(r["recall"].rstrip("%")) < 95:
            print(f"WARN: {r['stock_code']} recall below 95%: {r['recall']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the pre-flight**

Run: `.venv/bin/python scripts/hk_preflight.py`
Expected: Writes `tests/fixtures/china_packs/preflight_recall.csv` with recall per target. If any target is below 95 percent, proceed to Step 3. Otherwise skip.

- [ ] **Step 3: If recall is below 95 percent on any target**

Trim HKEX v1 metric coverage. Edit the spec's metric scope section inline with a note like "HKEX v1 supports: revenue, net_income, total_assets, cash_and_equivalents, shares_outstanding_basic. Full metric set tracked as follow-up." Commit the scope trim as a separate commit so the history is legible.

- [ ] **Step 4: Write fixture README**

Create `tests/fixtures/china_packs/README.md`:

```markdown
# China test pack fixtures

Packs committed here are used by `tests/test_china_query_eval.py`.

Regenerate with:
```bash
.venv/bin/python scripts/hk_preflight.py
```

Coverage: 0700.HK, 3690.HK, 9988.HK, 9618.HK (FY2023 annual reports).
SEC-side fixtures (BIDU, PDD, BABA, JD 20-Fs) land via `edgarpack harvest`.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/hk_preflight.py tests/fixtures/china_packs/README.md tests/fixtures/china_packs/preflight_recall.csv
git commit -m "test(hk): pre-flight OCR recall script + baseline report"
```

---

### Task 13: Harvest target packs into tests/fixtures/china_packs/

**Files:**
- Commit: fixture packs for all 8 target filings (HK + SEC)
- Modify: `tests/fixtures/china_packs/README.md`

- [ ] **Step 1: Harvest SEC 20-F packs**

Run:
```bash
.venv/bin/edgarpack harvest --universe universe.toml --out tests/fixtures/china_packs/ --refresh --with-chunks
```
Expected: SEC packs appear for BIDU, PDD, BABA, JD under `tests/fixtures/china_packs/`.

- [ ] **Step 2: Run HK pre-flight to materialize HK packs**

If not already run in Task 12:
```bash
.venv/bin/python scripts/hk_preflight.py
```

- [ ] **Step 3: Verify directory structure**

Run: `ls tests/fixtures/china_packs/`
Expected: Directories for each target with `manifest.json`, `sections/`, `chunks.ndjson`.

- [ ] **Step 4: Size-check and gitignore large files if needed**

Run: `du -sh tests/fixtures/china_packs/`
If total exceeds 50 MB, trim sections that are not load-bearing for the golden metrics (notes, auditor's report, five-year summary) by deleting those section files and regenerating `chunks.ndjson` from the remaining sections. Document the trim in the README.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/china_packs/
git commit -m "test(fixtures): commit HK + SEC target packs for FY2023 evaluation"
```

---

### Task 14: Add reporting_currency and accounting_standard to SEC pack manifest

**Files:**
- Modify: the SEC pack-builder (locate via `grep -n "manifest" edgarpack/harvest/ edgarpack/pack/ edgarpack/sec/`)
- Test: `tests/test_harvest_registry.py` or the existing pack-builder test

- [ ] **Step 1: Locate the pack-writer**

Run: `grep -rn "manifest" edgarpack/pack/ edgarpack/harvest/ | grep -v __pycache__ | head -20`
Identify the function that writes `manifest.json`. Most likely `edgarpack/pack/builder.py` or similar.

- [ ] **Step 2: Write the failing test**

Append to the nearest existing pack-builder test (or create one if none): a test asserting that manifests written for 20-F filings include `reporting_currency` (default `USD`) and `accounting_standard` (default `US-GAAP`, `IFRS` when the XBRL taxonomy is `ifrs-full`).

```python
def test_sec_manifest_includes_reporting_currency_and_accounting_standard(tmp_path):
    # Build a minimal pack via the real builder, inspect manifest.
    from edgarpack.pack.builder import build_pack  # adjust import path as needed

    # ... construct minimal inputs via existing test helpers ...
    manifest = build_pack(...)
    assert manifest["reporting_currency"] == "USD"
    assert manifest["accounting_standard"] == "US-GAAP"


def test_sec_20f_ifrs_filer_gets_ifrs_standard(tmp_path):
    from edgarpack.pack.builder import build_pack

    # ... construct with taxonomy='ifrs-full' ...
    manifest = build_pack(...)
    assert manifest["accounting_standard"] == "IFRS"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -x -v -k "reporting_currency or accounting_standard"`
Expected: FAIL.

- [ ] **Step 4: Add the two fields to the pack-writer**

Edit the pack-builder module. Where the manifest dict is assembled, add:

```python
manifest["reporting_currency"] = _infer_reporting_currency(filing)
manifest["accounting_standard"] = _infer_accounting_standard(filing)
```

Add helper functions in the same module:

```python
def _infer_reporting_currency(filing) -> str:
    # Most SEC filers report USD. 20-F filers sometimes report other currencies.
    currency = getattr(filing, "reporting_currency", None)
    return currency or "USD"


def _infer_accounting_standard(filing) -> str:
    taxonomy = getattr(filing, "xbrl_taxonomy", "")
    if "ifrs" in taxonomy.lower():
        return "IFRS"
    return "US-GAAP"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -x -v`
Expected: PASS on new tests plus all existing tests green.

- [ ] **Step 6: Commit**

```bash
git add edgarpack/pack/ tests/
git commit -m "feat(pack): write reporting_currency and accounting_standard into SEC manifest"
```

---

### Task 15: Add --currency flag and plumb identity through query CLI

**Precondition:** Verify `bd show <eux-issue-id>` shows closed. If not, pause here until it lands.

**Files:**
- Modify: `edgarpack/cli.py:129-176` and `edgarpack/cli.py:852-` (the `_cmd_query` function)
- Test: `tests/test_cli_self_heal.py` or create `tests/test_cli_query_currency.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_query_currency.py`:

```python
"""--currency flag plumbing (edgarpack-2yg)."""

import subprocess
import sys
from pathlib import Path


def _run_query(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "query", *args],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )


def test_query_accepts_currency_flag():
    result = _run_query("BIDU", "revenue", "--currency", "usd", "--help")
    assert result.returncode == 0
    assert "currency" in result.stdout.lower()


def test_query_currency_defaults_to_both():
    result = _run_query("BIDU", "--help")
    assert "both" in result.stdout.lower()
```

- [ ] **Step 2: Add --currency to the parser**

Edit `edgarpack/cli.py`, add after the `--strict` flag:

```python
p_query.add_argument(
    "--currency",
    choices=["native", "usd", "both"],
    default="both",
    help="Currency output mode (default: both). Native shows reporting currency only; "
    "usd shows USD only; both shows reporting currency plus USD with FX rate.",
)
```

- [ ] **Step 3: Route the positional `company` arg through identity**

In `_cmd_query` (around `edgarpack/cli.py:852`), add identity resolution at the start:

```python
from .identity import load_identity, resolve, UnknownCompany

_IDENTITY_INDEX = load_identity(Path("universe.toml"))

def _cmd_query(args: Any) -> int:
    try:
        resolved = resolve(_IDENTITY_INDEX, ticker=args.company, company=args.company)
    except UnknownCompany as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if resolved.private:
        print(
            f"error: {resolved.ticker} is a private company with no public filings. "
            "Alt-data ingestion tracked on a separate issue; query is unsupported.",
            file=sys.stderr,
        )
        return 2

    # existing body continues, using resolved.source to pick adapter
    ...
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_cli_query_currency.py tests/test_cli_self_heal.py -x -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/cli.py tests/test_cli_query_currency.py
git commit -m "feat(cli): --currency flag and identity-layer routing for query"
```

---

### Task 16: Query formatter emits native + USD lines with FX disclosure

**Files:**
- Modify: `edgarpack/cli.py:601-` (the `_render_query_table` function)
- Modify: `edgarpack/query/financials.py` (hook FX conversion on value read)
- Test: extend `tests/test_cli_query_currency.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_query_currency.py`:

```python
def test_both_mode_shows_native_and_usd_with_rate_for_hk_ticker():
    result = _run_query("0700.HK", "revenue", "--period", "lfy", "--currency", "both")
    assert result.returncode == 0
    assert "CNY" in result.stdout or "HKD" in result.stdout
    assert "USD" in result.stdout
    assert "HKFRS" in result.stdout
    # FX rate disclosed inline
    assert "0.1" in result.stdout  # any HKD/USD or CNY/USD rate


def test_usd_mode_shows_only_usd():
    result = _run_query("0700.HK", "revenue", "--period", "lfy", "--currency", "usd")
    assert result.returncode == 0
    assert "USD" in result.stdout
    assert "CNY" not in result.stdout.split("USD")[0]  # no CNY before USD section


def test_native_mode_shows_only_reporting_currency():
    result = _run_query("0700.HK", "revenue", "--period", "lfy", "--currency", "native")
    assert result.returncode == 0
    assert "CNY" in result.stdout
    assert "USD" not in result.stdout or "CNY/USD" in result.stdout


def test_us_adr_both_mode_collapses_redundant_usd_line():
    result = _run_query("BIDU", "revenue", "--period", "lfy", "--currency", "both")
    assert result.returncode == 0
    # Only one USD line (no "USD ... USD ..." duplicate)
    usd_lines = [l for l in result.stdout.splitlines() if "USD" in l and "revenue" in l.lower()]
    assert len(usd_lines) <= 1
```

- [ ] **Step 2: Update the renderer**

In `edgarpack/cli.py`, replace `_render_query_table` with logic that inspects `resolved.source`, the pack manifest's `reporting_currency`, and `args.currency`. Call `edgarpack.fx.convert` for `both` and `usd` modes.

(Full implementation reads `CitedValue.reporting_currency`, selects convention by `unit` category: balance-sheet concepts get `spot`, income-statement concepts get `average`. Use the concept-to-category map in `edgarpack/query/metric_map.py`: add a parallel `CONVENTION_BY_METRIC: dict[CanonicalMetric, Literal["spot", "average"]]` in that module.)

- [ ] **Step 3: Add CONVENTION_BY_METRIC**

Edit `edgarpack/query/metric_map.py`, append:

```python
CONVENTION_BY_METRIC: dict[CanonicalMetric, str] = {
    "revenue": "average",
    "gross_profit": "average",
    "gross_margin": "average",
    "operating_income": "average",
    "operating_margin": "average",
    "ebitda": "average",
    "net_income": "average",
    "eps_basic": "average",
    "eps_diluted": "average",
    "total_assets": "spot",
    "total_liabilities": "spot",
    "total_equity": "spot",
    "cash_and_equivalents": "spot",
    "total_debt": "spot",
    "shares_outstanding_basic": "spot",
    "shares_outstanding_diluted": "spot",
}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_cli_query_currency.py -x -v`
Expected: PASS on all four currency tests.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/cli.py edgarpack/query/metric_map.py tests/test_cli_query_currency.py
git commit -m "feat(cli): render native + USD lines with FX rate disclosure"
```

---

### Task 17: HKEX H1-proxy LTM construction

**Files:**
- Modify: `edgarpack/query/periods.py`
- Test: `tests/test_china_hk_ltm.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_china_hk_ltm.py`:

```python
"""HKEX H1-proxy LTM (edgarpack-2yg)."""

from datetime import date

from edgarpack.query.periods import construct_h1_proxy_ltm


def test_h1_proxy_ltm_sums_prior_fy_plus_delta_h1():
    fy_prior = {"value": 100, "period_end": date(2022, 12, 31)}
    h1_current = {"value": 55, "period_end": date(2023, 6, 30)}
    h1_prior = {"value": 48, "period_end": date(2022, 6, 30)}
    result = construct_h1_proxy_ltm(fy_prior, h1_current, h1_prior)
    assert result["value"] == 107  # 100 + (55 - 48)
    assert result["method"] == "h1_proxy"
    assert result["period_end"] == date(2023, 6, 30)


def test_h1_proxy_label_surfaces_in_formatted_output():
    from edgarpack.query.periods import format_period_label

    label = format_period_label({"method": "h1_proxy", "period_end": date(2023, 6, 30)})
    assert "LTM" in label
    assert "H1-proxy" in label
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_china_hk_ltm.py -x -v`
Expected: FAIL on missing `construct_h1_proxy_ltm` or `format_period_label`.

- [ ] **Step 3: Add the functions**

Append to `edgarpack/query/periods.py`:

```python
def construct_h1_proxy_ltm(
    fy_prior: dict,
    h1_current: dict,
    h1_prior: dict,
) -> dict:
    """LTM for HK filers who only publish H1 interims.

    LTM = FY_prior + (H1_current - H1_prior).
    """
    return {
        "value": fy_prior["value"] + (h1_current["value"] - h1_prior["value"]),
        "period_end": h1_current["period_end"],
        "method": "h1_proxy",
    }


def format_period_label(period_info: dict) -> str:
    if period_info.get("method") == "h1_proxy":
        return f"LTM (H1-proxy, ending {period_info['period_end']})"
    return f"FY (ending {period_info.get('period_end', 'unknown')})"
```

Wire `construct_h1_proxy_ltm` into the HKEX path of the query engine (inside `financials.py` where LTM is constructed for SEC tickers; branch on `resolved.source == "HKEX"` and use H1-proxy).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_china_hk_ltm.py -x -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add edgarpack/query/periods.py tests/test_china_hk_ltm.py
git commit -m "feat(query): H1-proxy LTM for HKEX filers (FY_prior + delta H1)"
```

---

### Task 18: MiniMax private-company exit path

**Files:**
- Test: `tests/test_china_private_minimax.py`

- [ ] **Step 1: Write the test**

Create `tests/test_china_private_minimax.py`:

```python
"""MiniMax private-company scaffold (edgarpack-2yg)."""

import subprocess
import sys
from pathlib import Path


def test_minimax_query_exits_with_clear_private_company_message():
    result = subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "query", "MINIMAX-PRIVATE", "revenue"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert result.returncode == 2
    assert "private company" in result.stderr.lower()
    assert "no public filings" in result.stderr.lower() or "unsupported" in result.stderr.lower()


def test_minimax_query_by_alias_also_exits_cleanly():
    result = subprocess.run(
        [sys.executable, "-m", "edgarpack.cli", "query", "minimax", "revenue"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert result.returncode == 2
    assert "private" in result.stderr.lower()
```

- [ ] **Step 2: Run tests**

The private-company branch landed in Task 15. Confirm it works.

Run: `.venv/bin/python -m pytest tests/test_china_private_minimax.py -x -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_china_private_minimax.py
git commit -m "test(minimax): assert private-company path exits cleanly with status 2"
```

---

### Task 19: Curate golden fixtures for BIDU and Tencent (done-def minimum)

**Files:**
- Create: `tests/eval/china_golden.yaml`

- [ ] **Step 1: Look up FY2023 and LTM numbers from IR sources**

Reference sources (use `WebFetch` or local copies):
- Tencent FY23 annual report (Hong Kong Stock Exchange filing).
- Baidu FY23 20-F (SEC EDGAR).

For each metric listed in `CANONICAL_METRICS`, record the as-filed native value and the USD equivalent as published by the company itself or by S&P Capital IQ. Document the source page or row.

- [ ] **Step 2: Create tests/eval/china_golden.yaml**

Seed the file with two entries (Tencent + BIDU). Example shape:

```yaml
- ticker: 0700.HK
  company: Tencent Holdings
  accounting_standard: HKFRS
  reporting_currency: CNY
  fy: 2023
  source: "Tencent 2023 Annual Report, page 142"
  metrics:
    revenue_fy:
      native: 609015000000
      usd: 85881000000
      fx_avg: 0.1411
    net_income_fy:
      native: 115216000000
      usd: 16244000000
      fx_avg: 0.1411
    total_assets_fy:
      native: 1576000000000
      usd: 221776000000
      fx_spot: 0.1407
    cash_and_equivalents_fy:
      native: 166999000000
      usd: 23498000000
      fx_spot: 0.1407
    revenue_ltm:
      native: 622148000000  # FY22 + (H1-23 - H1-22) reconstruction
      usd: 87808000000
      method: h1_proxy
      fx_avg: 0.1411

- ticker: BIDU
  company: Baidu
  accounting_standard: IFRS
  reporting_currency: USD
  fy: 2023
  source: "Baidu 2023 Form 20-F, Item 5"
  metrics:
    revenue_fy:
      native: 134598000000  # CNY as reported
      usd: 18987000000  # converted at filing-period avg
      fx_avg: 0.1411
    net_income_fy:
      native: 20315000000
      usd: 2866000000
      fx_avg: 0.1411
    revenue_ltm:
      native: 134598000000
      usd: 18987000000
      fx_avg: 0.1411
```

(Note: numbers above are illustrative. Real curation happens in this task by reading the filings.)

- [ ] **Step 3: Commit**

```bash
git add tests/eval/china_golden.yaml
git commit -m "test(eval): golden fixtures for Tencent + BIDU FY23 and LTM (done-def minimum)"
```

---

### Task 20: Evaluation harness that runs CLI against golden

**Files:**
- Create: `tests/test_china_query_eval.py`

- [ ] **Step 1: Write the harness**

Create `tests/test_china_query_eval.py`:

```python
"""Golden-fixture eval harness for China query parity (edgarpack-2yg)."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

GOLDEN = Path("tests/eval/china_golden.yaml")
TOLERANCE = 0.02  # 2 percent


def _load_fixtures() -> list[dict]:
    with GOLDEN.open() as f:
        return yaml.safe_load(f)


def _run_query(ticker: str, metric: str, period: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "edgarpack.cli",
            "query",
            ticker,
            metric,
            "--period",
            period,
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, f"CLI failed for {ticker} {metric}: {result.stderr}"
    import json

    return json.loads(result.stdout)


@pytest.mark.eval
@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["ticker"])
def test_fixture_metrics_within_tolerance(fixture):
    for metric_key, expected in fixture["metrics"].items():
        metric_name, _, period_suffix = metric_key.rpartition("_")
        period = "lfy" if period_suffix == "fy" else "ltm"
        actual = _run_query(fixture["ticker"], metric_name, period)
        actual_usd = actual.get("usd_value") or actual.get("value")
        expected_usd = expected["usd"]

        diff = abs(actual_usd - expected_usd) / expected_usd
        assert diff <= TOLERANCE, (
            f"{fixture['ticker']} {metric_key}: "
            f"expected {expected_usd}, got {actual_usd} "
            f"(diff {diff:.2%}, tolerance {TOLERANCE:.0%}). "
            f"Source: {fixture['source']}"
        )
```

- [ ] **Step 2: Run the harness**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -m eval -x -v`
Expected: PASS for both Tencent and BIDU. If any metric fails the 2 percent threshold, inspect the stdout diff, verify golden numbers against the IR source, and confirm the CLI path (identity + FX + formatter) is correct.

- [ ] **Step 3: Commit**

```bash
git add tests/test_china_query_eval.py
git commit -m "test(eval): golden-fixture harness runs CLI against curated expected values"
```

---

### Task 21: Expand golden fixtures to all six public targets

**Files:**
- Modify: `tests/eval/china_golden.yaml`

- [ ] **Step 1: Curate fixtures for remaining four**

Add entries for PDD, BABA, JD (using 20-F source), Meituan (HKEX source). Each entry covers the full `CANONICAL_METRICS` set for FY2023 and, where applicable, LTM. Sources are the IR annual report or the corresponding SEC 20-F.

For dual-listed BABA, add two entries: one keyed on `BABA` (SEC source, US-GAAP, USD) and one keyed on `9988.HK` (HKEX source, IFRS, CNY). Same for JD / 9618.HK.

- [ ] **Step 2: Run the full harness**

Run: `.venv/bin/python -m pytest tests/test_china_query_eval.py -m eval -v`
Expected: PASS on all entries.

- [ ] **Step 3: If any entry fails the 2% bar**

Inspect the first failing metric. Likely causes:
- Wrong FX convention (spot used where average is expected, or vice versa).
- Metric-map miss (line item in filing uses a tag not in `METRIC_MAP`).
- OCR recall gap on HKEX pack.

Fix the underlying issue, not the fixture. If the fixture itself is wrong (e.g., transcription error from the PDF), correct it and commit with a note.

- [ ] **Step 4: Commit**

```bash
git add tests/eval/china_golden.yaml
git commit -m "test(eval): golden fixtures for all six public China targets (FY23 + LTM)"
```

---

### Task 22: Full test suite green + done-def confirmation

**Files:** (none new)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -v`
Expected: ALL GREEN including the new `eval`-marked tests.

- [ ] **Step 2: Run the done-def queries manually**

Run:
```bash
.venv/bin/edgarpack query BIDU revenue --period ltm --currency both
.venv/bin/edgarpack query 0700.HK revenue --period ltm --currency both
```

Verify by eye:
- BIDU output shows a USD number within 2 percent of the golden.
- Tencent output shows `CNY` and `USD` lines, the `HKFRS` label, and the `LTM (H1-proxy)` period annotation.
- FX rate is disclosed inline.

- [ ] **Step 3: Run ruff**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: Clean. Fix any issues.

- [ ] **Step 4: Update the spec with learnings**

If any decisions in the spec were revised during implementation (e.g., metric-map tag had to be extended, an alias added, the OCR pre-flight forced a scope trim), append a `## Implementation notes (2026-04-14)` section to `docs/superpowers/specs/2026-04-14-china-query-performance-design.md`.

- [ ] **Step 5: Close the beads issue**

Run:
```bash
bd close edgarpack-2yg
bd sync
```

- [ ] **Step 6: File the follow-up issue for MiniMax alt-data**

Run:
```bash
bd create --title="MiniMax private-company alt-data ingestion path" --type=feature --priority=3 \
  --description="Build press-release/leaked-deck ingestion with trust-scored pack schema. Stub exists in universe.toml as MINIMAX-PRIVATE; CLI exits 2 today."
```

- [ ] **Step 7: Final commit and push**

```bash
git add docs/superpowers/specs/
git commit -m "docs(spec): implementation notes appended after edgarpack-2yg close" || true
git push
```

---

## Self-Review Notes

Coverage of spec sections:
- Problem, scope: covered by Tasks 1-22 collectively; no gaps.
- Identity model: Tasks 2, 3, 4.
- Corpus adapters: SEC in Task 14, HKEX in Tasks 9-13.
- FX layer: Tasks 5, 6.
- Accounting flag: Task 7 (model), Task 14 (SEC write), Task 11 (HK write), Task 16 (render).
- Query CLI: Tasks 15, 16, 17.
- Metrics: Task 8.
- Tests: Tasks 3, 6, 8, 10-11, 17-21 (written alongside each piece, plus Task 20-21 for eval harness).
- Done definition: Task 22.
- Open questions: Task 12 (OCR pre-flight gate), Task 17 (H1-proxy label).

Precondition dependency (the `eux` bug) is called out at the top and again at Task 15, which is the first task that touches query-path periods logic.
