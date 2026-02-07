# EdgarPack

EdgarPack turns SEC EDGAR filings into clean, sectioned markdown packs. It preserves visible text, strips iXBRL noise, and gives you stable section IDs.

## Why

SEC filings are HTML with inline XBRL. A revenue number often looks like this.

```html
<ix:nonFraction contextRef="c-1" decimals="-6"
  format="ixt:num-dot-decimal" name="us-gaap:Revenues"
  scale="6" unitRef="usd">130,497</ix:nonFraction>
```

That markup burns tokens and hides the number. EdgarPack removes the noise and keeps the text you read.

Typical 10-K differences show up in these ranges.

| Metric | Raw SEC HTML | EdgarPack |
|--------------|--------------|-----------|
| File size | ~2-3 MB | ~400 KB |
| Tokens | ~300K+ | ~107K |
| Sections | 1 blob | 27 files |
| RAG chunks | DIY | Ready |
| API cost | 3x more | 3x less |

Section-level addressing is the real win. You can load `10k_parti_item1a_risk_factors.md` directly instead of hunting inside a giant blob.

## Installation

```bash
pip install edgarpack
# or
uv pip install edgarpack
```

## Quick Start

```bash
# Build pack for Apple's latest 10-K
edgarpack build --cik 320193 --form 10-K --out ./packs

# Build pack for a specific filing
edgarpack build --cik 320193 --accession 0000320193-24-000123 --out ./packs

# Include optional artifacts for RAG
edgarpack build --cik 320193 --form 10-K --out ./packs --with-chunks --with-xbrl

# List recent filings for a company
edgarpack list --cik 320193 --form 10-K --limit 5

# Generate company-level index
edgarpack company-llms --cik 320193 --out ./packs

# Generate a minimal offline static site
edgarpack site --packs ./packs --out ./site
```

## Output Structure

```
packs/0000320193/0000320193-24-000123/
├── llms.txt
├── manifest.json
├── filing.full.md
├── sections/
│   ├── 10k_parti_item1_business.md
│   ├── 10k_parti_item1a_risk_factors.md
│   ├── 10k_partii_item7_mdna.md
│   └── ...
└── optional/
    ├── chunks.ndjson
    └── xbrl.json
```

## Pack Format

### llms.txt

`llms.txt` is the entry point. It follows the llms.txt spec and lists artifacts with short descriptions.

```markdown
# Apple Inc. 10-K (2024-01-15)

> CIK 0000320193 | Accession 0000320193-24-000123

## Filing Pack

- [Full Filing](filing.full.md)
- [Manifest](manifest.json)

## Sections

- [Business](sections/10k_parti_item1_business.md)
- [Risk Factors](sections/10k_parti_item1a_risk_factors.md)
...
```

### manifest.json

`manifest.json` holds metadata and integrity details. It includes the schema and parser versions, filing metadata, section index with offsets and token counts, hashes, and warnings.

### Sections

Each section is a markdown file with a stable ID.

- 10-K uses `10k_part{I/II}_item{N}_{slug}`
- 10-Q uses `10q_part{I/II}_item{N}_{slug}`
- 8-K uses `8k_item_{N.NN}_{slug}`

### chunks.ndjson

`chunks.ndjson` stores semantic chunks with token counts. Generate it with `--with-chunks`.

```json
{"chunk_id": "abc123...", "section_id": "10k_parti_item1a_risk_factors", "chunk_index": 0, "text": "...", "tokens": 892}
{"chunk_id": "def456...", "section_id": "10k_parti_item1a_risk_factors", "chunk_index": 1, "text": "...", "tokens": 1047}
```

### xbrl.json

`xbrl.json` holds structured financial data from the SEC companyfacts API. Generate it with `--with-xbrl`.

## SEC Compliance

- Set `EDGARPACK_USER_AGENT` with contact info.
- EdgarPack caps requests at 10 per second.
- EdgarPack caches SEC responses to cut repeat calls.

## Cache

The default cache lives at `~/.edgarpack/cache/`. Use these commands.

```bash
edgarpack cache
edgarpack cache --clear
```

Set a custom cache location with this command.

```bash
export EDGARPACK_CACHE_DIR=/path/to/cache
```

## Static Site

Generate a minimal offline site from a packs directory.

```bash
edgarpack site --packs ./packs --out ./site
```

Any static host works.

- GitHub Pages. Publish the `site/` directory via `gh-pages` or `/docs`.
- Netlify. Set the publish directory to `site/`.
- S3. Sync `site/` to a bucket and enable static website hosting.

## Development

```bash
git clone https://github.com/samay58/edgarpack
cd edgarpack
uv pip install -e ".[dev]"

# Run tests
python3 -m unittest discover -s tests

# Lint and format
ruff check . && ruff format .
```

## Design Principles

- EdgarPack produces byte identical output for the same input and version.
- EdgarPack preserves visible text and removes noise.
- EdgarPack emits warnings and creates `unknown_XX.md` for unmatched content.
- EdgarPack enforces rate limits, declares a User-Agent, and caches aggressively.

## Supported Forms

- 10-K. Annual reports with Item 1-15 detection.
- 10-Q. Quarterly reports with Item 1-4 detection.
- 8-K. Current reports with Item X.XX detection.
