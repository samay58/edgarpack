# How EdgarPack Works

EdgarPack turns SEC EDGAR filings into clean markdown with stable section IDs and deterministic artifacts. It exists to make filings easier to inspect, quote, diff, and query without hand-cleaning inline XBRL markup. In typical 10-K runs, the markdown output is much smaller than raw filing HTML and easier to load section by section.

## The Pipeline

Use NVIDIA's 10-K (`CIK 0001045810`) as the concrete example. EdgarPack fetches the filing files, converts the HTML into clean markdown, builds a pack directory, and optionally queries XBRL facts for metrics.

## Design Decisions and Tradeoffs

A few choices shaped how this project works.

Stdlib HTTP keeps deployment predictable. The rate-limit behavior is fully visible in our code, not buried in a third-party client.

Regex plus `html.parser` for the parsing stack means we control exactly how filing noise gets stripped and section text gets preserved. A DOM parser would add a dependency and hide behavior behind tree traversal.

Artifacts are deterministic. Reruns produce the same output, so diffs are meaningful and hash-addressed manifests stay stable across builds.

Citations live in the data model, not in formatting or side metadata. Every returned value carries its filing provenance by default, not as an opt-in.

Missing facts return `None` instead of guesses. Silent imputation is worse than explicit gaps in financial work.

### Stage 1: Fetch from SEC EDGAR

EdgarPack first resolves filing metadata from SEC submissions data, then fetches filing files from the SEC Archives path. The HTTP client enforces SEC-friendly pacing with a token-bucket rate limiter and retry handling for throttling or transient server errors.

Responses are stored in a SHA256-keyed disk cache so repeat runs do not re-download unchanged data. Cache writes are atomic, so concurrent processes do not leave partial files.

### Stage 2: Parse HTML to Markdown

The parser runs six steps in strict order:

- `ixbrl_strip`: removes inline XBRL tags while keeping visible values. The annotation noise goes away; the number text stays.
- `html_clean`: removes scripts, hidden blocks, and unsafe attributes. Only visible structural HTML survives.
- `semantic_html`: normalizes tag shapes (`<b>` to `<strong>`, safe link normalization, unwraps presentational tags). Fewer rendering edge cases before markdown conversion.
- `md_render`: converts semantic HTML into markdown using deterministic regex passes. Handles nested lists recursively, expands colspan/rowspan into aligned table grids, and guards against empty or malformed links.
- `md_polish`: post-processing pass that cleans up cosmetic noise in the raw markdown. Strips repeated TOC headings (page-break artifacts), removes bold from dollar amounts and all-bold paragraphs, recovers bullet lists trapped in table markup, drops empty table columns, normalizes heading levels so `#` is reserved for the filing title, simplifies wide financial tables into a blockquote format, and collapses excess whitespace. Eight rules chained in sequence, all idempotent.
- `sectionize`: detects form-specific headings (`10-K`, `10-Q`, `8-K`) and splits output into section-addressable chunks.

Most dramatic transformation example:

```html
<!-- before -->
<p>Revenue: <ix:nonFraction name="us-gaap:Revenues">130,497</ix:nonFraction></p>
```

```md
<!-- after -->
Revenue: 130,497
```

### Stage 3: Build the Pack

After parsing, the pack builder prepends a filing title line (`# Company Name | Form Type | Filed YYYY-MM-DD`) to the top of the markdown. This gives the document a clear identity and reserves the `#` heading level that the polish pass normalizes against.

A pack is a directory for one filing accession. It includes:

- `filing.full.md`: full markdown output (titled, polished)
- `sections/*.md`: one file per detected section
- `manifest.json`: filing metadata, section offsets, token counts, and SHA256 hashes
- `llms.txt`: index-style entry file for the pack
- Optional `optional/chunks.ndjson` and `optional/xbrl.json`

The manifest hashes content by artifact path. That makes integrity checks and reproducible comparisons straightforward across runs.

### Stage 4: Query Financial Data

The query layer starts from SEC companyfacts XBRL data. For each metric, it resolves concept tags, selects the requested period, and returns values with filing-level citations. Three data quality guards run on every metric: staleness rejection (values too many fiscal years behind get dropped), segment filtering (prefers consolidated entries over segment breakouts using the SEC `frame` field), and concept scope warnings (flags when the resolved XBRL tag is broader or narrower than the metric name implies).

Example: how EdgarPack gets NVIDIA's LTM revenue.

1. Resolve `NVDA` to `CIK 0001045810`.
2. Fetch `companyfacts` JSON for that CIK.
3. Map metric `revenue` to the best available concept for NVIDIA (`Revenues`).
4. For period `ltm`, select:
   - MRP: most recent quarterly cumulative revenue entry
   - LFY: prior fiscal year annual revenue
   - MRP prior: same fiscal quarter one fiscal year earlier
5. Compute `LTM = MRP + LFY - MRP prior`.
6. Return a `DerivedValue` with component citations so each number can be traced to an accession and filing URL.

`ltm-1` uses the same formula but shifts the quarter anchor one fiscal year back. If components are missing for the shifted window, the selector degrades to the best anchored reported value with provenance preserved.

## The Citation Model

`CitedValue` is a direct SEC fact with provenance fields: company, CIK, accession, form type, filing date, concept tag, and period metadata.

`DerivedValue` is a computed metric built from one or more `CitedValue` components. It keeps the computed value and the full component map.

Citation format example:

```text
NVIDIA CORP 10-K (FY2025), filed 2025-02-18
```

Each value can also provide URLs such as:

- Filing index URL (`...-index.htm`)
- Concept history URL (`/api/xbrl/companyconcept/...`)
- Viewer URL (`/ix?doc=...`) when primary document metadata is available

## How the Code is Organized

### Stage 1 modules

- `edgarpack/sec/client.py`: async SEC HTTP client with rate limiting and retries.
- `edgarpack/sec/cache.py`: disk cache with SHA256 keys and atomic writes.
- `edgarpack/sec/submissions.py`: filing metadata lookup and listing.
- `edgarpack/sec/archives.py`: filing index and file fetch helpers.
- `edgarpack/sec/xbrl.py`: companyfacts fetch and accession filtering.
- `edgarpack/sec/tickers.py`: ticker to CIK resolution.

### Stage 2 modules

- `edgarpack/parse/ixbrl_strip.py`: strip inline XBRL tags and namespaces.
- `edgarpack/parse/html_clean.py`: remove hidden or unsafe HTML content.
- `edgarpack/parse/semantic_html.py`: normalize markup before markdown rendering.
- `edgarpack/parse/md_render.py`: deterministic HTML-to-markdown conversion (nested lists, colspan/rowspan, link cleanup).
- `edgarpack/parse/md_polish.py`: post-render cleanup pass (TOC spam, bold noise, bullet-table recovery, heading normalization, complex table simplification, whitespace normalization).
- `edgarpack/parse/sectionize.py`: form-aware section detection and splitting.
- `edgarpack/parse/tokenize.py`: token counting and truncation helpers.

### Stage 3 modules

- `edgarpack/pack/build.py`: orchestrates pack creation.
- `edgarpack/pack/manifest.py`: manifest model and hash utilities.
- `edgarpack/pack/chunks.py`: optional semantic chunk generation.
- `edgarpack/pack/llms_txt.py`: pack and company index text generation.

### Stage 4 modules

- `edgarpack/query/models.py`: `CitedValue`, `DerivedValue`, and `QueryResult`.
- `edgarpack/query/concepts.py`: metric metadata and concept resolution.
- `edgarpack/query/periods.py`: period selection and LTM math.
- `edgarpack/query/financials.py`: single-company query execution.
- `edgarpack/query/comps.py`: multi-company comparisons.

### Supporting modules

- `edgarpack/site/build.py`: static site generator for built packs.
- `edgarpack/site/templates.py`: HTML template helpers.
- `edgarpack/site/styles.py`: inline CSS.
- `edgarpack/cli.py`: command-line entry points.
- `edgarpack/config.py`: runtime constants and environment bindings.

## Running It

Build a pack from a filing:

```bash
EDGARPACK_USER_AGENT="Your Name your.email@example.com" \
  edgarpack build --cik 0001045810 --form 10-K --out ./packs
```

Query one company's financials:

```bash
EDGARPACK_USER_AGENT="Your Name your.email@example.com" \
  edgarpack query NVDA revenue,net_income --period ltm
EDGARPACK_USER_AGENT="Your Name your.email@example.com" \
  edgarpack query NVDA revenue --period ltm-1
```

Run a comps table:

```bash
EDGARPACK_USER_AGENT="Your Name your.email@example.com" \
  edgarpack comps NVDA AMD INTC --metrics revenue,net_income,ebitda --period ltm
EDGARPACK_USER_AGENT="Your Name your.email@example.com" \
  edgarpack comps NVDA AMD INTC --metrics revenue --period ltm-1
```

Example comps output:

```text
Company                    Revenue   Net Income   Ebitda
-------------------------  --------  -----------  --------
NVIDIA CORP                $130.0B   $72.9B       $86.2B
ADVANCED MICRO DEVICES INC $24.7B    $1.4B        $5.1B
INTEL CORP                 $53.0B    -$2.5B       $8.8B
```
