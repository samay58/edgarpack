# Reference: query layer zero

`edgarpack/query/layer_zero.py` + `edgarpack/query/presets.py`

The metric-name front door. Everything a user types as a metric argument passes through alias resolution (`layer_zero.py`) and, for `--preset` flags, through list expansion (`presets.py`) before any extractor runs. Both modules are deterministic, stateless, and deliberately small; they exist so the rest of the query pipeline never has to guess what "fcf" means or what the `perf` preset contains.

---

## Data types

### `METRIC_ALIASES` (layer_zero.py)

```python
METRIC_ALIASES: dict[str, str] = {
    "fcf": "free_cash_flow",
    "opinc": "operating_income",
    "rev": "revenue",
    "ni": "net_income",
    "da": "depreciation_amortization",
    "sbc": "stock_based_compensation",
    "rd": "rd_expense",
    "cogs": "cost_of_revenue",
    "gp": "gross_profit",
    "ocf": "operating_cash_flow",
    # ... a handful more
}
```

Hand-curated typo-class map. Keys are lowercase informal shorthands; values are the canonical metric slugs the rest of the system knows. Adding an entry here is the right fix for any "user typed X, we meant Y" miss. Removing an entry is backwards-incompatible; users' shell history still has those flags.

### `MetricNotFoundError` (layer_zero.py)

```python
class MetricNotFoundError(ValueError):
    def __init__(self, metric_name: str, suggestions: list[str] | None = None) -> None:
        self.metric_name = metric_name
        self.suggestions = suggestions or []
```

Structured error the CLI catches to render "Unknown metric: 'revenu'. Did you mean: revenue?" Callers populate `suggestions` from `suggest_metrics`. `MetricNotFound` is re-exported as an alias at the bottom of the module.

### `PRESETS` (presets.py)

```python
PRESETS: dict[str, tuple[str, ...]] = {
    "perf": (
        "revenue", "revenue_growth_yoy", "revenue_cagr_3y",
        "gross_margin", "operating_margin", "net_margin",
        "r_and_d_intensity", "sga_intensity", "fcf_margin",
    ),
}
```

Curated metric bundles for common requests. `perf` is the one production preset today: the nine-number performance view that `compare` and `query` both accept as `--preset perf`. Order in the tuple is output order; don't alphabetize.

---

## Functions

### `resolve_alias(name: str) -> str` (layer_zero.py)

**Purpose**: Turn a user-typed metric name into its canonical slug.

**Inputs**:
- `name`: raw user input, any case, may have surrounding whitespace.

**Returns**: canonical slug if aliased, otherwise the lowercased/stripped input unchanged. Never raises; unknown names are the caller's problem.

**How it works**: lowercases and strips the input, then returns `METRIC_ALIASES.get(key, key)`. One-liner in spirit.

**Design notes**: This function does not know which canonical slugs are valid. It only knows the alias table. A caller like `financials()` runs `resolve_alias` first, then checks the result against its own known-metric set and raises `MetricNotFoundError` on miss. Separating alias from validity keeps this module free of any metric-map dependency.

### `suggest_metrics(name: str, known: set[str] | frozenset[str], n: int = 3) -> list[str]` (layer_zero.py)

**Purpose**: Populate the "did you mean" list for a `MetricNotFoundError`.

**Inputs**:
- `name`: the already-failed metric name.
- `known`: the set of valid canonical slugs the caller knows about. Sorted internally.
- `n`: max number of suggestions to return.

**Returns**: up to `n` close matches from `known`, ordered by similarity. Empty list when no match passes the cutoff.

**How it works**: wraps `difflib.get_close_matches` with cutoff 0.6. The caller decides the known-set, which is what lets different callers suggest different canonical vocabularies (the top-level metric map vs. the KPI catalog vs. discovered company KPIs).

**Design notes**: 0.6 is tuned against "revenu" -> "revenue" (match) and "x" -> nothing. Lowering it gives noisy suggestions; raising it makes small typos silent.

### `expand_metrics(metrics_csv: str | None, preset: str | None) -> list[str] | None` (presets.py)

**Purpose**: Combine `--preset` and `--metrics` CLI inputs into a single ordered metric list.

**Inputs**:
- `metrics_csv`: value of `--metrics`, comma-separated, possibly `None`.
- `preset`: value of `--preset`, a key into `PRESETS`, possibly `None`.

**Returns**:
- `None` when both inputs are absent. Callers treat this as "use the default metric set".
- A list of canonical slugs otherwise: preset first, then `--metrics` appended, duplicates removed preserving first-seen order.

Raises `ValueError` for an unknown preset name (the message lists known presets).

**How it works**:

1. If `preset` is provided, look it up in `PRESETS` (lowercased, stripped). Unknown preset is a hard error.
2. Walk the preset tuple, appending to `result` while tracking `seen` to dedupe.
3. Walk `metrics_csv.split(",")`, stripping each entry, skipping blanks and already-seen slugs.
4. Return `None` if the combined list is empty so callers can fall through to their default path.

**Design notes**: Preset metrics come first intentionally; `--preset perf --metrics revenue_growth_yoy` should still render the preset's order with the explicit metric either slotted in its preset position (if it's in the preset) or appended at the end. Callers can depend on order.

---

## Invariants

- `resolve_alias` never raises; enforced by `resolve_alias` (dict `.get` with fallback).
- `expand_metrics` returns `None` only when both inputs are `None` or empty; enforced by the final `if not result: return None` check; this is what lets the caller distinguish "user said nothing" from "user said empty".
- `PRESETS` values preserve intended output order; enforced by using `tuple` (not `set`) and walking with `in` checks.
- Alias collisions don't happen silently; `METRIC_ALIASES` is a flat dict, so a duplicate key is a syntax error at import time.

---

## What these modules do not do

- They do not know which canonical metric slugs are valid. `financials()` owns that knowledge. These modules just resolve shorthand and expand presets.
- They do not fetch. No network, no database.
- `resolve_alias` does not recurse. If an alias maps to another alias, the second hop is not chased. Keep the alias table flat.
- `layer_zero.py` does not store company-specific aliases. Those live in the KPI discovery path (`kpi_discover.py`, `learned_registry.py`) and are applied inside extractors, not here.
