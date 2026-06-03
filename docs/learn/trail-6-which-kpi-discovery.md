# Trail 6: How `edgarpack which FIG` finds the KPIs a company actually discloses

**Time**: ~14 minutes
**Prereq**: [Trail 1](trail-1-build-a-pack.md) (you know what a pack contains). Trail 0 helps for period labels but is not required.
**Covers**: `edgarpack/cli.py:_cmd_which`, `edgarpack/query/kpi_discover.py`, `edgarpack/query/kpi_extract.py`, `edgarpack/query/learned_registry.py`

`query` answers "what was Figma's revenue last year". `which` answers "what KPIs does Figma actually disclose". The first question has a canonical answer drawn from a known metric catalog. The second does not: every company invents a slightly different vocabulary for its business metrics. You run `edgarpack which FIG` and the system opens every pack on disk for Figma, reads MD&A prose, and builds a matrix of (metric slug) x (fiscal period).

---

## 1. The subparser is deliberately narrow

```python
p_which = sub.add_parser("which", help="List the qualitative / MD&A KPIs a company discloses...")
p_which.add_argument("company", help="Ticker or company name (e.g. FIG, Figma).")
p_which.add_argument("--format", choices=["table", "json"], default="table")
p_which.add_argument("--no-cache", action="store_true", help="Re-run discovery on every filing")
p_which.add_argument("--only", choices=["all", "discovered", "catalog"], default="all")
p_which.add_argument("--max-periods", type=int, default=6)
```

Three flags to tune the view. `--no-cache` forces an LLM rerun on every pack (one call per filing; this is expensive). `--only discovered` hides catalog KPIs to show only the free-form metrics the company invented. `--max-periods` caps how many columns render in the table view; JSON always returns everything.

**Code**: `edgarpack/cli.py:552-586` (subparser), `edgarpack/cli.py:1973` (`_cmd_which`).

---

## 2. Company resolution feeds an SEC CIK

`_cmd_which` calls `_resolve_cli_company(args.company)` (the same helper `query` uses), extracts the resolved CIK, and hard-stops if the result isn't a public SEC filer:

```python
cik = getattr(resolved, "cik", None)
if not isinstance(cik, str) or not cik.strip():
    print(f"Error: {args.company} does not resolve to a public SEC filer with a CIK.", ...)
    return 2
```

HKEX-only and private companies have no CIK. `which` currently requires one because every downstream lookup keys on `cik`. If you want Chinese company coverage, that change starts here, not in `kpi_discover.py`.

**Code**: `edgarpack/cli.py:1991-2007`.

---

## 3. The pack registry is the universe

```python
registry = PackRegistry()
packs = registry.list_packs(cik=cik, limit=200)
```

`which` never fetches from the SEC. Every filing it considers has already been built into a pack (that is what made its MD&A prose searchable in the first place). No packs, no KPIs: the command prints `Run edgarpack build ... first` and returns 1. This is why `which` is fast on a warm cache and completely skipped on a cold one.

`discover_kpis(cik=...)` then filters to eligible forms:

```python
eligible_packs = [p for p in packs if (p.form_type or "").upper().startswith(("10-K", "10-Q", "20-F"))]
```

8-Ks, S-1s, and DEF 14As are registered but skipped. They rarely carry the kind of recurring operating metrics this view is designed to surface.

**Code**: `edgarpack/cli.py:2009-2018` (registry load), `edgarpack/query/kpi_discover.py:339` (`discover_kpis`), `edgarpack/query/kpi_discover.py:378-380` (eligibility filter).

---

## 4. Per-pack: cache hit or LLM call

The central function is `_discover_pack`. For each eligible pack:

```python
if not force and learned_reg.company_kpi_has_accession(cik, accession):
    cached_rows = learned_reg.company_kpi_list(cik=cik, accession=accession)
    return PackDiscoveryResult(discovered=..., status="cached")

manifest = _load_pack_manifest(pack_dir)
existing_slugs = learned_reg.company_kpi_distinct_slugs(cik)
extraction = extract_discoveries_detailed(pack_dir=..., existing_slugs=existing_slugs)
```

Two critical behaviors here. First, cache lookup keys on `(cik, accession)`, not on pack path: if you rebuild a pack to the same accession number, the cached discoveries still apply. Second, when the LLM does run, it receives `existing_slugs`; every slug this company has ever disclosed across any filing; so it can reuse a canonical slug instead of reinventing `active_users` as `monthly_active_users` in a later filing. Naming drift is still tracked (as an alias) but the slug is stable.

Failure modes are deliberate, not exceptional:
- `unreadable_manifest`: pack directory exists in the registry but can't be opened. Logged and skipped.
- `llm_failed`: LLM backend unavailable or returned nonsense. Logged; no sentinel persisted.
- `empty`: the LLM scan ran successfully but found no qualifying KPIs. A sentinel row is written so the next `which` call skips the LLM on this filing entirely.

The empty sentinel is the reason a second run is cheap even for filings with no KPIs. Without it, every call would pay the full LLM cost to rediscover nothing.

**Code**: `edgarpack/query/kpi_discover.py:166` (`_discover_pack`), `edgarpack/query/kpi_discover.py:219-234` (empty sentinel), `edgarpack/query/kpi_extract.py:1350` (`extract_discoveries_detailed`).

---

## 5. Catalog hits come from a different table

`KPI_CATALOG` in `kpi_extract.py` is the named-metric canon (ARR, paid seats, customer count, and similar). Those metrics don't go through the discovery LLM; they're extracted by Layer B when a user runs `edgarpack query FIG arr`, and the result lands in `learned_concepts` rows tagged `source='kpi-llm'`.

`_catalog_points_for_cik` reads those back:

```python
rows = learned_reg.list_rows(cik=cik, source="kpi-llm")
for row in rows:
    if row.metric not in KPI_CATALOG:
        continue
    # look up the pack for that accession, build a PeriodPoint
```

A catalog KPI only appears in `which` if somebody has previously queried it for this company. This is the intended behavior for the first release: `which` surfaces what a company has *disclosed and been asked about*, not catalog coverage aspirations. Query NVDA's `arr` once, and it shows up in `edgarpack which NVDA` forever after.

`--only discovered` hides catalog rows entirely; `--only catalog` flips it. The default `all` shows both.

**Code**: `edgarpack/query/kpi_discover.py:284` (`_catalog_points_for_cik`), `edgarpack/query/kpi_extract.py:217` (`KPI_CATALOG` definition).

---

## 6. Aggregation collapses across filings

Each filing produces its own `DiscoveredKpi` rows. `discover_kpis` groups those by slug, turning "paid_seats appeared in three quarterly filings" into one `CompanyKpiAggregate` with three `PeriodPoint` entries:

```python
per_slug_points.setdefault(slug, []).append(PeriodPoint(
    label=_period_label(pack.form_type, kpi.fiscal_year, kpi.fiscal_period, kpi.period_end),
    sort_key=kpi.period_end or pack.filing_date,
    ...
))
```

The `label` is the human string: `FY2024` for annuals, `Q2'24` for quarterlies, the raw ISO date when fiscal labels aren't available. The `sort_key` is always the ISO period_end, so chronological ordering is stable across form mixes.

Latest-wins for display name: if a company called the metric "Paid Users" in FY2022 and "Paid Seats" in FY2024, the aggregate's `display_name` is "Paid Seats" and "Paid Users" lands in `aliases`. Readers see current phrasing first but naming drift is visible.

After aggregation, the list sorts discovered rows before catalog rows alphabetically. Users care most about what *this company* discloses beyond the canon; catalog metrics go to the bottom.

**Code**: `edgarpack/query/kpi_discover.py:419-460` (per-slug merge), `edgarpack/query/kpi_discover.py:495-511` (final sort), `edgarpack/query/kpi_discover.py:96` (`CompanyKpiAggregate`).

---

## 7. The side door: querying a discovered KPI

Discovered KPIs aren't just a view. `lookup_company_kpi(cik, slug, period)` at the bottom of the module is what lets `edgarpack query FIG paid_seats --period lfy` resolve a metric that was discovered by `which` rather than defined in the global metric map:

```python
if p == "lfy":
    filtered = [r for r in rows if (r.form_type or "").upper().startswith("10-K")]
elif p == "mrq":
    filtered = [r for r in rows if (r.form_type or "").upper().startswith("10-Q")]
else:
    filtered = list(rows)
filtered.sort(key=lambda r: (r.period_end or "", r.extracted_at), reverse=True)
return filtered[0]
```

No LLM call on this path. The row must already be in the `company_kpis` cache, which `which` populates. This is how the extended `financials()` resolution order works: if the ordinary metric map doesn't have `paid_seats`, the query falls back to `lookup_company_kpi` and finds it only if `which` has already surfaced it.

**Code**: `edgarpack/query/kpi_discover.py:518` (`lookup_company_kpi`).

---

## 8. The handoff

`_cmd_which` receives the aggregate list and renders it. Table mode calls `_render_which_table(aggregates, max_periods)` and prints the per-row period matrix capped at `max_periods` columns. JSON mode dumps `CompanyKpiAggregate.to_json()` for every aggregate; every period, no cap. Diagnostics print to stderr so they don't pollute a piped JSON response.

From here, the next `which` call replays from cache unless you pass `--no-cache`, and any `query` against a discovered slug uses `lookup_company_kpi` as the shortcut. The LLM cost is paid exactly once per (company, filing) pair.

---

## Recap

`which` is the qualitative counterpart to `query`. It never hits the SEC directly; it walks registered packs, runs an LLM discovery pass on each (cache-guarded), folds in already-cached catalog hits, and rolls everything up into a per-slug matrix. The load-bearing files are `edgarpack/query/kpi_discover.py` (aggregation, caching, catalog merge), `edgarpack/query/kpi_extract.py` (the LLM pass itself and the `KPI_CATALOG` canon), and `edgarpack/query/learned_registry.py` (the SQLite-backed persistent cache). The one design choice worth internalizing is that `which` trades latency for determinism: the first run is expensive, every subsequent run is free, and the `existing_slugs` feedback loop is what keeps slug naming stable as a company adds filings.
