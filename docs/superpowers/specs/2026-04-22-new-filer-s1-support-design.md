# Generalized New-Filer (Pre-IPO / S-1) Support

**Date:** 2026-04-22
**Status:** Design approved, ready for implementation plan
**Anchor case:** Cerebras Systems (CIK 0002021728), S-1 accession 0001628280-25-025762

## Product framing

S-1s are not leaner 10-Ks. They carry disclosures that never appear in periodic reports: use-of-proceeds allocation, dilution waterfalls, principal-stockholder ownership at IPO, pre-IPO capital structure, underwriter economics, lock-up terms, founder voting classes, pro-forma capitalization, roadshow framing (TAM/SAM, category narrative, competitive positioning), company-specific operating metrics (systems deployed, ARR composition, customer concentration at the named-account level), and visual material (roadshow infographics, product photography, customer-logo walls).

EdgarPack's unique value on a pre-IPO filer is surfacing exactly this S-1-only content and contrasting it across S-1/A redlines (what the company changed between drafts as it responded to SEC comments and investor feedback). The extraction, diff, and query layers below are designed around that promise, not around treating S-1 like a 10-K and hoping.

## Design constraints

1. Minimally bloated. No parallel S-1 subsystem. One new file in the entire project.
2. Reuse existing form-type machinery (`universe.py` `form_counts`, `sectionize.py`, `kpi_discover.py`, `periods.py`, `diff/timeline.py`, `insights/*`) wherever reuse is defensible.
3. Modular. Every new branch is isolated to the smallest seam possible: a form-type parameter, a guard function, or a filter edit.
4. Generalizable. The same pipeline handles future IPOs (Klarna, Databricks, foreign filers via F-1) without per-issuer code.
5. S-1/A amendment redlines are the diff primitive. No attempt to shoehorn pre-IPO filings into 10-K time-series logic.

## Architectural spine

S-1 is just a form type. No state machine, no parallel subsystem. The form type IS the pre-IPO signal.

Recognized registration-class forms (treated as one family):

`S-1`, `S-1/A`, `F-1`, `F-1/A`, `424B1`, `424B2`, `424B3`, `424B4`, `424B5`, `FWP`

Graduation is implicit. When a filer posts its first 10-K, flipping `forms_10k` to a nonzero count routes the filing into the existing 10-K/10-Q pipeline. Historical S-1 packs remain queryable, excluded from 10-K/10-Q logic by a single `is_registration_form()` guard. No retroactive reclassification.

## Harvest and universe config

### CompanySpec changes (`edgarpack/harvest/universe.py`)

1. Add `forms_s1: int | None = None`.
2. Add `name: str | None = None` (company name for pre-IPO filers without tickers).
3. Make `ticker: str | None = None` (previously required).
4. Make `cik: str | None = None` (previously optional, now explicitly an escape hatch rather than a required field for pre-IPO).
5. Model validator: at least one of `{ticker, name, cik}` must be set. If multiple are set, resolution checks them in order.
6. Pre-IPO inference rule: when `forms_s1 > 0` and the filer has not explicitly set `forms_10k`, `forms_10q`, or `forms_8k`, treat the unset periodic forms as 0 for that filer. Prevents spurious `harvest_errors` entries from attempts to fetch filings that do not exist yet. Once the filer IPOs, the user adds explicit periodic counts and the inference is overridden.
7. In `UniverseConfig.form_counts`, when `forms_s1 > 0`, emit a single budget across the registration-class family (most-recent-first across all family forms combined, capped at N total).

### Resolution layer (`edgarpack/sec/tickers.py`)

The file already has `resolve_ticker(company)` that queries SEC's `company_tickers.json`. That map only covers companies with assigned tickers, so pre-IPO filers are not in it. Add a name-search fallback:

- New function `resolve_company_by_name(name)` queries SEC's EDGAR full-text search endpoint (`https://efts.sec.gov/LATEST/search-index`) with the company name filtered to registration-class forms. Returns the unique matching CIK, or raises if zero or multiple matches.
- New function `resolve_filer(spec)` at the top of the harvest planner: tries `cik` first (if supplied), then `ticker` via existing `resolve_ticker`, then `name` via `resolve_company_by_name`. Caches the resolved CIK back onto the spec for the rest of the run.

`planner.py:64` changes from `await resolve_ticker(spec.ticker)` to `await resolve_filer(spec)`. CIK is cached in the registry the first time a filer is resolved, so subsequent runs skip the network roundtrip.

`registry.py`, `runner.py` are unchanged.

### Minimal universe entries

Pre-IPO filer (name-only):

```toml
[[companies]]
name = "Cerebras Systems"
forms_s1 = 8
```

Public filer (ticker-only, the common case):

```toml
[[companies]]
ticker = "NVDA"
```

CIK-only (escape hatch when name is ambiguous):

```toml
[[companies]]
cik = "0002021728"
forms_s1 = 8
```

Post-IPO (explicit counts override the inference):

```toml
[[companies]]
ticker = "CRBS"
forms_s1 = 2      # keep pulling post-IPO amendments
forms_10k = 2
forms_10q = 4
forms_8k = 5
```

### Resolution errors

If `name` resolution returns multiple matches (e.g., "Acme Corp" matches three different filers), the error message lists the candidates with their CIKs and tickers-if-any, and tells the user to disambiguate by supplying `cik` explicitly. If zero matches, the error suggests checking spelling or providing `cik` directly.

## Sectionizer

`sectionize.py:543` already has an `is_general_form` branch handling bold headings and markdown `#` headings. `normalize_form_type_for_sections` already strips `/A`, so S-1/A normalizes to S-1 for free.

First attempt: zero new code. Run Cerebras S-1 through the existing general-form path and inspect section IDs. Add an S-1 anchor whitelist (Prospectus Summary, Risk Factors, Use of Proceeds, Capitalization, Dilution, MD&A, Business, Principal Stockholders, Underwriting) inside the existing branch only if empirical parsing is weak. The whitelist, if needed, is a 5-10 line pattern addition, not a new dispatch.

## Visuals pipeline

New module `edgarpack/pack/assets.py` (~60 LOC). Only new file in the project.

Functions:

1. `download_assets(base_url, html, out_dir)` parses `<img>` tags in cleaned HTML, downloads referenced images into `<pack>/assets/`, returns a URL-to-local-path map.

2. `describe_asset(image_path)` optional, gated by `--describe-images` flag. Calls Claude Haiku 4.5 vision with this prompt:

   > Extract in under 75 words: what this figure shows (chart type, product shot, org chart, etc.); any numeric claims stated on the image (market size, growth rates, customer counts, performance benchmarks); and the one-line thesis the figure supports. If the image is decorative, say so.

   Output cached by `sha256(image_bytes)` in `<pack>/assets/.descriptions.json`. Re-harvests never re-bill.

3. Alt-text from `<img alt>` is harvested free when present and used as a fallback when description is absent or flag is off.

Wiring:

- `parse/html_clean.py` gains `preserve_images: bool = False`. True for registration-class forms.
- `parse/md_render.py` rewrites `<img src>` to local relative paths and emits the description (or alt-text) as a markdown caption directly below the image.
- `pack/build.py` creates `<pack>/assets/` when form is registration-class, invokes `download_assets` and optionally `describe_asset`.

The description flows into existing chunks and FTS5 search with zero new indexing code. Roadshow infographics become queryable alongside body text.

Rationale for VLM over OCR: roadshow infographics use stylized typography and icon-heavy composition that OCR mangles. A VLM produces clean paragraph-level descriptions that integrate with the existing pipeline as plain text. Haiku 4.5 at roughly $0.005 per image means a 50-image S-1 costs about $0.25, gated behind an opt-in flag.

## Extraction: framing, operating metrics, S-1-only disclosures, snapshot financials

**Framing metrics (TAM/SAM/CAGR/market thesis):** extend `query/kpi_discover.py` with a new `FRAMING_PATTERNS` group. Patterns target `$Xb? (?:addressable|TAM|total addressable) market`, `growing at X% CAGR`, `$Xb? opportunity`, `category (?:expected to|projected to) reach`, plus common variants. Discovered rows tagged `metric_kind='framing'`. Same storage, same query surface. ~30 LOC.

**Company-specific operating metrics:** `kpi_discover.py:411` filter currently excludes forms outside `{10-K, 10-Q, 20-F}`. Add registration-class forms to the allowlist. Discovered rows tagged `metric_kind='operating'` with `form_class='registration'`. Existing discovery heuristics catch "180 systems deployed", "$X ARR", "N customers with $1M+ contracted spend" without pattern-library changes. One-line filter edit.

**S-1-only disclosure extractors:** four small pattern sets in `kpi_discover.py`, each running only on registration-class packs:

- `_extract_use_of_proceeds` matches "We intend to use the net proceeds... approximately $N for X, $M for Y"
- `_extract_dilution` matches "immediate dilution of $X per share", "pro forma net tangible book value"
- `_extract_lockup` matches "lock-up period of 180 days"
- `_extract_principal_holders` parses the top rows of the Principal Stockholders table by percent column

Each writes rows tagged `metric_kind='s1_disclosure'` with a `disclosure_type` subfield. ~80 LOC total.

**Snapshot financials:** zero new code. S-1 iXBRL follows the same spec as 10-K iXBRL. `query/periods.py` gains `is_registration_form(form)`. Existing LTM, LTM-1, and Q4 selectors early-return `None` when the form is registration-class. Registration-class KPI rows remain queryable by accession and by period label but are excluded from time-series derivation. ~10 LOC.

## Diff and timeline: the S-1 redline chain

The S-1 to S-1/A to S-1/A to 424B chain is the analytical primitive. Every amendment represents a change the company had to make in response to SEC comments or underwriter feedback; 424B locks in final pricing. Diffing consecutive pairs surfaces exactly what got renegotiated: risk factor additions, use-of-proceeds reallocations, dilution recalculations, revised financials, revised lockup terms.

`edgarpack/diff/timeline.py`:

- New function `build_registration_timeline(cik)` returns a chronologically-sorted list of registration-class filings for a CIK.
- `timeline.py` adds a `series_class` concept: `'annual'` for the existing 10-K run, `'registration'` for the S-1 chain. Same data structure, one new dispatch at the top of `build_timeline`.
- Consecutive-pair diffing runs `section_diff.py` unchanged. Jaccard paragraph matching, word-weighted intensity, and SHA256 fast-path all operate on section text, not on form semantics.

`section_diff.py` and `text_diff.py` are untouched.

~30 LOC in `timeline.py`.

## Insights (reuse)

`disclosures.py`, `emerging.py`, `language_shift.py` all operate on a sequence of filings with `form_type` metadata. Feed them the registration timeline instead of the annual timeline. Zero code changes.

What this produces for a pre-IPO filer:

- **language_shift** across S-1/A drafts catches softened risk language or added cautionary phrasing.
- **emerging topics** across drafts surfaces new disclosures the company added (e.g., a new competitor named in amendment 3).
- **new disclosures** on the 424B vs last S-1/A surfaces finalized pricing terms as the delta.

## CLI surface

One small addition: `--series=registration` flag on the diff and timeline CLI entries, scoping output to the registration chain. ~10 LOC in whichever CLI file owns the relevant subcommand.

## Kill-list: explicitly NOT in v1

Hard boundaries to prevent scope creep:

- No LTM, Q4, or LTM-1 derivation for registration-class forms. Snapshot financials only.
- No comps integration with pre-IPO filers as peer baseline.
- No multi-filer trendline charts across S-1s from different issuers.
- No image OCR. Superseded by VLM description.
- No PDF-native FWP parsing. HTML and text attachments only. PDF-only FWPs logged to `harvest_errors` and skipped. Revisit if Cerebras's roadshow deck is PDF-only.
- No DRS (draft confidential registration) support.
- No S-3 shelf, S-4 M&A, S-11 REIT, or other registration variants.
- No auto-graduation state machine. Natural form-count flow handles it.
- No new pack markdown schema. Existing format plus `assets/` subfolder.
- No new insights modules. Reuse the existing three.
- No captioning or figure-number indexing beyond VLM description output.
- No dedicated pre-IPO web UI views. Existing query surfaces return registration rows tagged correctly; UI work is a follow-up.

## File-change map

| File | Change | Approx LOC |
|---|---|---|
| `edgarpack/harvest/universe.py` | `forms_s1` field, optional `ticker`/`cik`, new `name` field, identifier validator, pre-IPO inference rule, family expansion in `form_counts` | +25 |
| `edgarpack/sec/tickers.py` | `resolve_company_by_name` via EDGAR search, `resolve_filer` dispatch | +40 |
| `edgarpack/harvest/planner.py` | swap `resolve_ticker` call for `resolve_filer` | +5 |
| `edgarpack/pack/assets.py` | NEW: download + VLM describe + hash cache | +60 |
| `edgarpack/parse/html_clean.py` | `preserve_images` flag | +8 |
| `edgarpack/parse/md_render.py` | local img src rewrite, caption emit | +12 |
| `edgarpack/pack/build.py` | wire assets pipeline for registration-class | +15 |
| `edgarpack/query/kpi_discover.py` | filter edit, framing patterns, S-1 disclosure extractors | +120 |
| `edgarpack/query/periods.py` | `is_registration_form` guards | +10 |
| `edgarpack/diff/timeline.py` | `build_registration_timeline`, `series_class` dispatch | +30 |
| `edgarpack/parse/sectionize.py` | conditional S-1 anchor whitelist (only if empirical parse is weak) | 0–10 |
| CLI wiring | `--series=registration` flag | +10 |
| `universe.toml` | Cerebras entry | +6 |
| Tests: `test_universe_s1.py`, `test_registration_timeline.py`, `test_assets_pipeline.py`, `test_kpi_framing.py`, `test_s1_disclosures.py` | | ~250 |
| **Non-test total** | | **~341** |
| **Total with tests** | | **~591** |

One new file: `edgarpack/pack/assets.py`. Every other change is an addition to an existing seam.

## Open questions deferred to implementation plan

Not blockers for the spec; resolve during planning and coding:

- Exact SEC URL pattern for pulling FWP filings. Verify against Cerebras's FWP (if any exists at time of implementation).
- Whether Cerebras's roadshow deck is filed as FWP or as an S-1 exhibit. Determines image-source routing.
- Haiku 4.5 vs Gemini Flash for VLM description. Default Haiku; swap only if cost or latency becomes a problem in practice.
- Budget-split algorithm for `forms_s1` across the family (most-recent-first by filing date is the working default; confirm during implementation that it behaves sensibly when FWPs are sparse).

## Success criteria

- Running `edgarpack harvest --universe universe.toml` pulls Cerebras S-1 and all amendments into the corpus.
- Running `edgarpack index --incremental` includes the new packs; FTS5 search returns hits from both body text and VLM image descriptions.
- `edgarpack diff --cik 0002021728 --series=registration` produces a consecutive-pair redline timeline across the S-1 chain, with word-weighted intensity per section.
- `edgarpack kpi list --cik 0002021728` returns framing metrics (TAM claims), operating metrics (systems deployed, ARR), snapshot financials (revenue, net loss, cash), and S-1-only disclosures (use of proceeds, dilution, lockup, principal holders), each tagged with `metric_kind` and `form_class`.
- `edgarpack/pack/<accession>/assets/` contains downloaded images with markdown captions in the rendered pack.
- Existing 10-K/10-Q behavior is unchanged. All current tests pass.
- Total non-test delta stays under ~350 LOC.
- A pre-IPO filer can be added to `universe.toml` with only two lines of config (`name` and `forms_s1`) without supplying a CIK or ticker. EdgarPack resolves the CIK via SEC's EDGAR search on first harvest and caches it.
- No spurious harvest errors are logged for periodic forms that do not yet exist for a pre-IPO filer.
