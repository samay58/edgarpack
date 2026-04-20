# Learn EdgarPack

How the system works, traced through what actually happens.

## The napkin sketch

```
You run a CLI command (build, query, comps, compare, which, list).
  The CLI parses your args and dispatches to a subcommand.
    v
  Resolve identity: name/ticker/CIK -> ResolvedCompany (source = sec | hkex | private)
    v
  Route by source:
    sec   -> submissions / archives / companyfacts / filing HTML over SECClient
            (rate-limited token bucket, SHA256 disk cache, atomic writes)
    hkex  -> read prebuilt pack's facts.json (HKEX extractor ran at pack time)
    v
  Parse (build only):  strip iXBRL -> clean HTML -> semantic normalize -> render markdown -> sectionize
  Pack  (build only):  write full.md, sections/*.md, llms.txt, facts.json, manifest.json (hashes)
  Period (query):      alias -> metric (layer_zero, presets), pick ltm/lfy/lfy-N/mrq facts, run formulas
  Discover (which):    LLM-scan MD&A + cached catalog -> DiscoveredKpi rows across periods
  Compare:             fan out query(company, period) per input, USD-convert, mismatch-guard
    v
  Cite:                every value carries company, accession, filing date, anchor URL
    v
  Render:              table / json / markdown / pack directory on disk
```

That is the entire lifecycle. Everything below fills in the details. For the higher-level "what is this and why" answer, read [`ARCHITECTURE.md`](../../ARCHITECTURE.md) at the repo root. This learn pack picks up where ARCHITECTURE.md leaves off and walks the actual code.

## Trails

Trails trace a concrete action through the code. Each one starts with something you do and follows the chain of what happens next.

**Start here:**

- [Trail 0: From `edgarpack query NVDA revenue` to a cited number](trail-0-full-loop.md) (~18 min)
  The most common command, walked end to end. Ticker resolution, companyfacts fetch, concept resolution, period selection, citation enrichment, table render. Touches every load-bearing module in the query path.

**Then go deeper:**

- [Trail 1: How `edgarpack build` turns a filing into deterministic markdown](trail-1-build-a-pack.md) (~14 min)
  The other half of the system. The 13-step pack orchestrator and the strict-order parse pipeline. What "deterministic" means in practice.

- [Trail 2: What happens during a single SEC HTTP call](trail-2-rate-limited-fetch.md) (~8 min)
  The seam everything else depends on. Token-bucket rate limiting, retry-with-backoff, atomic disk caching, gzip handling.

- [Trail 3: How `--period ltm` becomes three filings and one formula](trail-3-period-selection.md) (~16 min)
  The single subtlest part of the system. LTM math, anchor selection, fiscal-year matching, staleness rejection, segment filtering. Most reasoning bugs in financial code live here.

- [Trail 4: How a number gets a deep-link URL back to the filing](trail-4-citation-anchors.md) (~10 min)
  The part the README says "really matters". Inline XBRL fact_id parsing, the (concept, value) compound key, the URL fallback chain.

- [Trail 5: How `edgarpack compare AAPL MSFT GOOGL --period lfy` builds a side-by-side table](trail-5-compare-companies.md) (~12 min)
  Fan-out over `financials()`. Identity routing (SEC vs HKEX vs private), sequential resolution, spot-vs-average currency conversion, and the fiscal-year mismatch guard that keeps a multi-company table honest.

- [Trail 6: How `edgarpack which FIG` finds the KPIs a company actually discloses](trail-6-which-kpi-discovery.md) (~14 min)
  The qualitative counterpart to `query`. Per-pack LLM scans over MD&A, cached catalog merge, per-slug aggregation across filings, and the `lookup_company_kpi` side door that lets `query` hit discovered metrics without a second LLM call.

## Reference

When you need to look up a specific function or module, use the reference docs. They cover every exported function with purpose, inputs, outputs, design choices, and invariants.

Trails tell you the story. Reference is the dictionary.

- [`ref/ref-sec-client.md`](ref/ref-sec-client.md) covers `edgarpack/sec/client.py`. The SEC HTTP seam. Token bucket, retry, gzip, per-loop singleton.
- [`ref/ref-cache.md`](ref/ref-cache.md) covers `edgarpack/sec/cache.py`. SHA256-keyed disk cache with atomic writes. Encodes the determinism guarantee.
- [`ref/ref-pack-build.md`](ref/ref-pack-build.md) covers `edgarpack/pack/build.py`. The 13-step pack orchestrator. Order matters; this ref says why.
- [`ref/ref-sectionize.md`](ref/ref-sectionize.md) covers `edgarpack/parse/sectionize.py`. Form-aware section detection. Slug stability, TOC stub filtering, the section_id contract.
- [`ref/ref-financials.md`](ref/ref-financials.md) covers `edgarpack/query/financials.py`. The query orchestrator. Derived metrics with cycle protection, staleness, the low-debt sanity check.
- [`ref/ref-periods.md`](ref/ref-periods.md) covers `edgarpack/query/periods.py`. The hairiest module in the codebase. Period semantics, LTM math, anchor selection, ix:nonFraction parsing.
- [`ref/ref-query-models.md`](ref/ref-query-models.md) covers `edgarpack/query/models.py`. The citation contract. CitedValue, DerivedValue, QueryResult.
- [`ref/ref-identity.md`](ref/ref-identity.md) covers `edgarpack/identity.py`. The routing seam. `IdentityIndex`, `ResolvedCompany`, SEC vs HKEX routing, ambiguity caught at load time.
- [`ref/ref-query-layer-zero.md`](ref/ref-query-layer-zero.md) covers `edgarpack/query/layer_zero.py` + `edgarpack/query/presets.py`. Metric alias resolution, `suggest_metrics` for "did you mean", and preset expansion.

## How to use this

**Before a session**: glance at the napkin sketch. Orient yourself to where you'll be working.

**During a session**: when something is unclear, ask "walk me through this" and reference the relevant trail.

**After a session**: walk the trail for what you just built. The code references point you to the exact lines.

## What's deliberately not covered (yet)

This learn pack focuses on the core CLI lifecycle: `build`, `query`, `comps`, `compare`, `which`, `list`. The following are deliberately omitted from the first pass and will get their own learn packs (or extensions to this one) later:

- `edgarpack/harvest/`: batch orchestrator on top of `build_pack`. Separate concern.
- `edgarpack/diff/`, `edgarpack/index/`, `edgarpack/insights/`: analytical layers on top of built packs. Useful but not load-bearing for understanding the core lifecycle.
- `edgarpack/china/`: China Lens is a separate sub-product with its own pipeline (acquire / extract / translate / synthesize / qa). Deserves its own learn pack.
- `edgarpack/hk/`: HKEX extractor. Runs at pack time and populates `facts.json`; `identity.py` routing reads the output. Linked from Trail 5; promote to a ref if it grows.
- `edgarpack/api/`, `edgarpack/site/`: rendering and serving layers. Once you understand the core CLI lifecycle these become straightforward wrappers.
- `edgarpack/fx/`: USD conversion tables. Linked from Trail 5 as a pure data lookup.
- `edgarpack/sse/`: server-sent events for the translation pipeline. Outside the core query/pack lifecycle.

The current omissions are tracked in [`manifest.yml`](manifest.yml) under `omitted:`. Future runs will reconsider them.

## Keeping it current

These trails reference actual source files and line numbers. When the code changes, the trails should be updated in the same commit. If a trail reference is wrong, that is a bug.
