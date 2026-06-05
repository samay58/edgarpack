# Reference: identity

`edgarpack/identity.py`

The routing path. Every multi-company command (`compare`, `comps`, `query` when given a name rather than a ticker) first resolves user input into a `ResolvedCompany`, which tells the rest of the system where to look for facts: SEC EDGAR over HTTP, a prebuilt HKEX pack's `facts.json`, or a private-company exit. Identity is purely in-memory and config-driven; the index builds from `universe.toml` at load time and never touches the network.

---

## Data types

### `Source`

```python
Source = Literal["SEC", "HKEX"]
```

Routing key. `SEC` means reach companyfacts + archives over the rate-limited client. `HKEX` means the company's facts come from a pack built from an HKEX filing; downstream code reads `pack/facts.json` rather than hitting the SEC. The literal type makes the branches static-checkable.

### `ResolvedCompany`

```python
@dataclass(frozen=True)
class ResolvedCompany:
    ticker: str              # canonical ticker, uppercase
    listing: str | None      # "NYSE" | "NASDAQ" | "HKEX" | None
    source: Source           # SEC | HKEX
    cik: str | None          # populated for SEC filers
    hk_stock_code: str | None  # populated for HKEX listings
    aliases: tuple[str, ...]  # immutable for frozen dataclass hashing
    private: bool            # True when the company has no public facts feed
```

Load-bearing fields: `source` drives routing, `cik` is the SEC key, `hk_stock_code` is the HKEX key. `private=True` short-circuits queries into the private-company exit (clear error, no fetch attempt). `aliases` is kept around so callers can display "did you mean" hints.

### `IdentityIndex`

```python
@dataclass(frozen=True)
class IdentityIndex:
    by_ticker: dict[str, ResolvedCompany]  # keys uppercased
    by_alias: dict[str, ResolvedCompany]   # keys lowercased, stripped
    all_tickers: tuple[str, ...]           # sorted, for difflib suggestions
```

Two maps and a sorted tuple. `by_ticker` handles short-symbol lookups (including HKEX `.HK` tickers); `by_alias` handles name lookups. `all_tickers` exists so `difflib.get_close_matches` has a stable input for "did you mean" rendering.

---

## Functions

### `load_identity(path: Path) -> IdentityIndex`

**Purpose**: Build the in-memory routing index from a `universe.toml` file.

**Inputs**:
- `path` (`Path`): path to a universe TOML, typically `./universe.toml`.

**Returns**: an `IdentityIndex`. On alias collision, raises `AmbiguousCompany` immediately (config error; fix before any query runs).

**How it works**:

1. Calls `harvest.universe.load_universe(path)` to parse TOML into `CompanySpec` objects.
2. For each spec, builds one primary `ResolvedCompany` keyed by `spec.ticker.upper()`.
3. For every entry in `spec.alt_tickers`, builds a secondary `ResolvedCompany`; if the alt ends in `.HK` it is forced to `source="HKEX"` regardless of the primary's listing, which is how a dual-listed company surfaces a SEC ticker and an HKEX ticker from one spec.
4. Walks `spec.aliases` into `by_alias`, lowercased and stripped; on collision with a different ticker, raises `AmbiguousCompany`.

**Design notes**: Ambiguity is caught at load time, not query time. The universe is small and config-owned; a query-time ambiguity check would mean every call paid for a check that only ever fails when the config is broken. `.HK` suffix detection on alt tickers is the one place identity routing leaks knowledge about exchange conventions.

### `resolve(index: IdentityIndex, ticker: str | None, company: str | None) -> ResolvedCompany`

**Purpose**: Look up a user's input (either a ticker symbol or a company alias) against the index.

**Inputs**:
- `index`: the `IdentityIndex` from `load_identity`.
- `ticker`: pass this if the input is shaped like a ticker.
- `company`: pass this if the input is shaped like a name.

Exactly one must be provided. The CLI's pattern is to try both in sequence (`resolve(idx, ticker=name, ...)` then `resolve(idx, ticker=None, company=name)`) rather than asking this function to guess.

**Returns**: the matching `ResolvedCompany`. Raises `UnknownCompany` with `difflib`-backed suggestions on miss.

**How it works**:

1. If both inputs are `None`, raises `ValueError` (programmer error, not user error).
2. Ticker path: uppercase the input, look in `by_ticker`. On miss, compute up to three close matches from `all_tickers` and raise `UnknownCompany` with the list baked into the message.
3. Company path: lowercase-and-strip, look in `by_alias`. On miss, compute close matches from `by_alias.keys()` and render them as `alias (TICKER)` pairs in the error.

**Design notes**: Suggestions always appear. If no close match is found, the error falls back to the first three sorted keys so the user at least sees valid examples. This matters most for HKEX tickers where `.HK` suffix is non-obvious. No partial matching; this is strict equality after case normalization. Partial matching would create ambiguity between, say, "Apple" and "Applied Materials".

---

## Invariants

- `by_ticker` keys are uppercase; enforced by `_resolved_for` and `load_identity`.
- `by_alias` keys are lowercase and whitespace-stripped; enforced by `load_identity` at insert time and `resolve` at lookup time.
- Every primary ticker also has an entry in `by_ticker` for itself; enforced by `load_identity` (`by_ticker[spec.ticker.upper()] = primary`).
- No two different tickers claim the same alias; enforced by `load_identity` (raises `AmbiguousCompany`).
- `.HK`-suffixed tickers always have `source="HKEX"`; enforced by `_source_for` and `load_identity`.

---

## What this module does not do

- It does not fetch anything. `source="SEC"` is a flag; the fetch happens in `edgarpack/sec/client.py`.
- It does not decide which facts feed to read for an HKEX company. That lives in `edgarpack/query/financials.py`, which sees `source="HKEX"` and routes to pack-local `facts.json`.
- It does not validate that a CIK is a real SEC filer. A typo in `universe.toml` resolves cleanly here and fails later at fetch time.
- It does not handle tickers that aren't in `universe.toml`. `compare` and related commands catch `UnknownCompany` here and fall back to SEC ticker lookup in `edgarpack/sec/tickers.py`. That fallback is what makes the command work for any public SEC filer, not just the ones in your universe.
