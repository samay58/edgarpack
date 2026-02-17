# EdgarPack

EdgarPack converts SEC EDGAR filings (10-K, 10-Q, 8-K) into clean markdown packs with stable section IDs.
It keeps visible filing text, removes inline XBRL tags, and writes deterministic artifacts for repeatable analysis.

## Why It Exists

Raw SEC filing HTML is noisy and hard to work with at section level.
EdgarPack turns one large filing blob into:

- One full filing markdown file
- One markdown file per detected section
- A manifest with hashes and offsets
- Optional chunk and XBRL artifacts

## Why It Works This Way

The stack is small on purpose.

- Stdlib HTTP. Deployments stay simple and dependency drift stays low.
- Regex and `html.parser` for parsing. Behavior stays explicit and easy to debug without a DOM dependency.
- Deterministic output. Diffs are meaningful and downstream caches stay valid.
- Citation fields on every query value. Every number traces back to a filing.

## Install

```bash
pip install edgarpack
# or editable install for local development
uv pip install -e ".[dev]"
```

## Required Environment

Set a SEC-compliant User-Agent before network calls:

```bash
export EDGARPACK_USER_AGENT="Your Name your.email@example.com"
```

Optional cache settings:

```bash
# Primary cache directory
export EDGARPACK_CACHE_DIR="$HOME/.edgarpack/cache"

# Fallback cache directory if primary creation fails
export EDGARPACK_CACHE_DIR_FALLBACK="/tmp/edgarpack-cache"
```

## Quickstart

### Build a pack

```bash
edgarpack build --cik 0001045810 --form 10-K --out ./packs
```

### Query one company

```bash
edgarpack query NVDA revenue,net_income --period ltm
edgarpack query NVDA revenue --period ltm-1
```

### Run a comps table

```bash
edgarpack comps NVDA AMD INTC --metrics revenue,net_income,ebitda --period ltm
edgarpack comps NVDA AMD INTC --metrics revenue --period ltm-1
```

### Query Periods At A Glance

- `lfy`: last fiscal year
- `mrq`: most recent quarter (standalone 3-month value for duration metrics)
- `mrp`: most recent reported period
- `ltm`: trailing twelve months
- `ltm-1`: prior-year trailing twelve months (same formula, one fiscal-year-shifted anchor)
- `annual:N`: last `N` fiscal years
- `quarterly:N`: last `N` quarters

For complete query behavior, JSON format details, and citation model notes, see `docs/QUERY.md`.

## Output Layout

```text
packs/
└── 0001045810/
    └── 0001045810-25-000001/
        ├── filing.full.md
        ├── llms.txt
        ├── manifest.json
        ├── sections/
        │   ├── 10k_parti_item1_business.md
        │   ├── 10k_parti_item1a_risk_factors.md
        │   └── ...
        └── optional/
            ├── chunks.ndjson
            └── xbrl.json
```

## Common Commands

```bash
# List recent filings
edgarpack list --cik 0001045810 --form 10-K --limit 5

# Generate company-level llms.txt index
edgarpack company-llms --cik 0001045810 --out ./packs

# Build a static site from packs
edgarpack site --packs ./packs --out ./site

# Cache inspection / cleanup
edgarpack cache
edgarpack cache --clear
```

## Development

```bash
# Lint
ruff check .
ruff format --check .

# Tests
python3 -m pytest tests/ -x -v
```

## SEC Compliance Notes

- EdgarPack sends a User-Agent header on every SEC request.
- Requests are rate-limited to 10 per second.
- Responses are cached on disk to reduce repeated SEC traffic.
