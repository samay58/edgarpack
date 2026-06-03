# Reference: query/models.py

`edgarpack/query/models.py` (558 lines)

The citation contract. Every public number in EdgarPack's query path flows through one of three Pydantic models: `CitedValue` (a single fact), `DerivedValue` (a fact computed from components), or `QueryResult` (a company-wide result). All of them are serializable and deep-link-aware.

---

## Data types

### CitedValue

```python
class CitedValue(BaseModel):
    value: float | int | None
    unit: str              # "USD", "shares", "USD/shares", "pure"
    metric: str            # normalized name: "revenue", "eps_diluted"
    concept: str           # GAAP tag: "Revenues"

    period_start: date | None = None
    period_end: date
    fiscal_year: int
    fiscal_period: str     # "FY", "Q1", "Q2", "Q3", "Q4"

    form_type: str         # "10-K", "10-Q"
    filed: date
    accession: str
    cik: str
    company: str

    taxonomy: str = "us-gaap"
    primary_document: str = ""
    fact_id: str = ""
    warnings: list[str] = Field(default_factory=list)
```

A single reported value plus everything you need to cite it and link back to the filing. `edgarpack/query/models.py:22-45`.

**Fields by category:**

- **The value**: `value`, `unit`, `metric`, `concept`. `metric` is EdgarPack's normalized name (e.g. `"revenue"`); `concept` is the underlying GAAP/IFRS tag (e.g. `"Revenues"`). Unit is a short string describing dimensionality.
- **Period**: `period_start`, `period_end`, `fiscal_year`, `fiscal_period`. Instant metrics (balance sheet) have `period_start=None`. Duration metrics (income statement, cash flow) have both dates. `fiscal_year` / `fiscal_period` are the XBRL-reported fiscal identifiers, which may diverge from calendar periods for companies with off-calendar fiscal years.
- **Source**: `form_type`, `filed`, `accession`, `cik`, `company`. Everything needed to build a citation string.
- **Deep linking**: `taxonomy`, `primary_document`, `fact_id`. Populated by the enrichment pass in `financials.py` (see [Trail 4](../trail-4-citation-anchors.md)). All three are optional at construction time.
- **Warnings**: per-value advisory strings. Used for scope warnings, staleness flags, low-debt sanity check, etc. Never silently replace a value; accumulate warnings and return.

### DerivedValue

```python
class DerivedValue(CitedValue):
    derived: bool = True
    components: dict[str, CitedValue] = Field(default_factory=dict)
```

Subclass of `CitedValue` for computed metrics (LTM, EBITDA, margins, ratios). `edgarpack/query/models.py:236`. Adds a `components` dict keyed by role name (`"mrp"`, `"lfy"`, `"mrp_prior"` for LTM; `"operating_income"`, `"depreciation_amortization"` for EBITDA). Each component is itself a fully-formed `CitedValue`.

**Why subclass**: derived values need all the same fields as cited values (they have a value, a unit, a fiscal period, etc.) plus the components dict. Subclassing means every consumer that handles `CitedValue` also handles `DerivedValue` without needing two code paths. Consumers that need to unpack the components do an `isinstance` check.

The `citation` property is overridden at line 274: LTM-like derived values return `"LTM computed from: <three citations joined>"` instead of a single filing citation. Other derived values (EBITDA, margins) fall back to the parent `citation` property.

### QueryResult

```python
class QueryResult(BaseModel):
    company: str
    cik: str
    period: str = "lfy"
    metrics: dict[str, CitedValue | list[CitedValue] | None]
```

The top-level result for one company and one period. `edgarpack/query/models.py:308`. The `metrics` dict maps each requested metric name to one of:

- A single `CitedValue` or `DerivedValue` (scalar period like `lfy`, `mrq`, `ltm`).
- A list of `CitedValue` for series queries (`annual:N`, `quarterly:N`).
- `None` if the metric couldn't be resolved or was rejected as stale.

---

## URL properties on CitedValue

### filing_url

`edgarpack/query/models.py:82`. Returns `.../{cik}/{accession_nodash}/{accession}-index.htm`, the SEC index page for the filing. Always available; derived from `cik` and `accession` only.

### concept_url

`edgarpack/query/models.py:98`. Returns the companyconcept API URL `.../api/xbrl/companyconcept/CIK{padded}/{taxonomy}/{concept}.json`. Returns `None` for derived metrics because their `concept` is a formula string (e.g. `"operating_income + depreciation_amortization"`), not a GAAP tag.

### viewer_url

`edgarpack/query/models.py:114`. Returns `https://www.sec.gov/ix?doc={doc_path}`, the SEC Inline XBRL Viewer URL. Returns `None` if `primary_document` is empty.

### document_url

`edgarpack/query/models.py:130`. Returns `.../primary.htm#:~:text={concept_label}`, using a text-fragment URL that scrolls the browser to the first occurrence of the concept label. Works in Chrome/Edge, not in Safari. Falls back to `None` if `primary_document` is empty.

The label transform is in `_concept_to_label` at line 14: `"NetIncomeLoss"` -> `"Net Income Loss"` (space-separate on camelCase boundaries).

### anchor_url

`edgarpack/query/models.py:155`. The preferred URL. Returns `.../primary.htm#{fact_id}` if both `fact_id` and `primary_document` are populated. Otherwise falls back to `document_url`. Produced by the enrichment pass in `financials.py` which parses inline XBRL and writes fact IDs into `CitedValue.fact_id`.

### citation (property)

`edgarpack/query/models.py:110`. Human-readable citation string: `"{company} {form_type} ({fiscal_period}{fiscal_year}), filed {filed}"`. E.g. `"NVIDIA CORP 10-K (FY2024), filed 2024-02-21"`.

Overridden in `DerivedValue` for LTM values to produce `"LTM computed from: {source1}; {source2}; {source3}"`.

### primary_link / primary_link_type

`edgarpack/query/models.py:120-136`. Pick the preferred URL for terminal output. Prefers `anchor_url` when `fact_id` is present, then `viewer_url`, then `filing_url`. `primary_link_type` returns the string name of the chosen type ("anchor_url", etc.) so formatters can decide how to display it.

### links

`edgarpack/query/models.py:139`. Returns all available URLs as a dict keyed by type. Used by JSON output modes.

---

## Serialization helpers

### to_cited_dict()

`edgarpack/query/models.py:190`. Full JSON-serializable dict with every URL baked in. Used by `--format json-full`.

### to_lean_metric()

`edgarpack/query/models.py:215`. Compact dict for a single metric. Omits company/cik/filing fields that would be duplicated across metrics in the same result. Used by `--format json`.

### to_citation_record(citation_id)

`edgarpack/query/models.py:161`. Normalized dict for registry-style outputs (e.g. the citation-linked `QueryResult.to_lean_dict()` used in comps output).

### citation_key

`edgarpack/query/models.py:153`. A stable identity key used to dedupe citations across multiple metrics in one result. Concatenates CIK, accession, taxonomy, concept, period, value, and fact_id. Two `CitedValue`s with the same `citation_key` point at literally the same span of a filing.

---

## Invariants

- **Every value carries its provenance.** `cik`, `accession`, `filed`, `company`, `form_type` are required fields. A `CitedValue` cannot exist without knowing where it came from.
- **Empty fact_id is valid.** The default is `""`. Consumers that need `anchor_url` to fall back to `document_url` rely on this.
- **`DerivedValue.components` carries intact citations.** Every component is a full `CitedValue`, not a compressed summary. Consumers can walk the components to produce multi-source citations.
- **URLs are computed on demand via properties.** The model stores only raw fields; URLs are derived. This means a `CitedValue` loaded from JSON can recompute all its URLs without depending on the serializer.
- **Warnings are additive.** Adding a warning never replaces the value. A stale value returns `None`; a value with a scope caveat returns the value with a warning attached.

---

## What this module does not do

- **It does not resolve concepts or periods.** That's `query/concepts.py` and `query/periods.py`. Models are the target of those resolvers, not the logic.
- **It does not fetch anything.** Pure data models. No network calls in this file.
- **It does not format for terminal output.** That's `cli.py:_render_query_table`. Models produce JSON-serializable dicts and formatters decide how to render them.
- **It does not enforce unit coherence.** If two `CitedValue`s in a single query report different units (e.g. USD and EUR), nothing in the model layer will catch it. Callers that care validate at the point where values are combined (`_compute_derived` in `financials.py` has `_derived_unit` for this).
