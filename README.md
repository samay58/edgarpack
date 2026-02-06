# EdgarPack

**llms.txt for SEC filings.** Transform SEC EDGAR filings into clean, section-addressable markdown packs optimized for LLM consumption.

## Why This Exists

SEC filings aren't PDFs. They're HTML with embedded iXBRL (inline XBRL) markup. Every financial number in a 10-K looks like this:

```html
<ix:nonFraction contextRef="c-1" decimals="-6"
  format="ixt:num-dot-decimal" name="us-gaap:Revenues"
  scale="6" unitRef="usd">130,497</ix:nonFraction>
```

When what you actually want is: `Revenue: $130,497 million`

If you're building an LLM app that needs to understand SEC filings, you have two options:

1. Feed the raw HTML to your model and burn tokens on thousands of iXBRL tags, hidden elements, and formatting noise
2. Use EdgarPack and get clean markdown with 3x fewer tokens

The math is simple:

| What you get | Raw SEC HTML | EdgarPack |
|--------------|--------------|-----------|
| File size | ~2-3 MB | ~400 KB |
| Tokens | ~300K+ | ~107K |
| Sections | 1 blob | 27 files |
| RAG chunks | DIY | Ready to go |
| API cost | 3x more | 3x less |

For RAG specifically: instead of chunking a 300K token blob yourself and dealing with table formatting hell, you get 27 semantic sections (Item 1, Item 1A, Item 7, etc.) plus pre-chunked pieces with token counts already calculated.

The real win is section-level addressing. Instead of "find the risk factors somewhere in this massive filing", you just load `10k_parti_item1a_risk_factors.md` directly. That's what [llms.txt](https://llmstxt.org/) is about. Give LLMs a table of contents they can navigate.

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
├── llms.txt              # Entry point for LLMs
├── manifest.json         # Metadata + section index + hashes
├── filing.full.md        # Complete filing as markdown
├── sections/
│   ├── 10k_parti_item1_business.md
│   ├── 10k_parti_item1a_risk_factors.md
│   ├── 10k_partii_item7_mdna.md
│   └── ...
└── optional/
    ├── chunks.ndjson     # RAG-ready chunks (with --with-chunks)
    └── xbrl.json         # Financial data (with --with-xbrl)
```

## Pack Format

### llms.txt

Entry point following the [llms.txt specification](https://llmstxt.org/). Lists all artifacts with brief descriptions:

```markdown
# Apple Inc. 10-K (2024-01-15)

> CIK: 0000320193 | Accession: 0000320193-24-000123

## Filing Pack

- [Full Filing](filing.full.md)
- [Manifest](manifest.json)

## Sections

- [Business](sections/10k_parti_item1_business.md)
- [Risk Factors](sections/10k_parti_item1a_risk_factors.md)
...
```

### manifest.json

Everything you need to verify and process the pack:
- Schema and parser versions (for determinism)
- Filing metadata (CIK, accession, dates, company name)
- Section index with character offsets and token counts
- SHA256 hashes of all artifacts
- Warnings from processing

### Sections

Individual markdown files for each detected section (ITEM 1, ITEM 1A, etc.). Section IDs follow a consistent pattern:
- 10-K: `10k_part{I/II}_item{N}_{slug}`
- 10-Q: `10q_part{I/II}_item{N}_{slug}`
- 8-K: `8k_item_{N.NN}_{slug}`

### chunks.ndjson (Optional)

Semantic chunks suitable for RAG pipelines:

```json
{"chunk_id": "abc123...", "section_id": "10k_parti_item1a_risk_factors", "chunk_index": 0, "text": "...", "tokens": 892}
{"chunk_id": "def456...", "section_id": "10k_parti_item1a_risk_factors", "chunk_index": 1, "text": "...", "tokens": 1047}
```

### xbrl.json (Optional)

Structured financial data from SEC's companyfacts API, filtered to the specific filing.

## SEC Compliance

EdgarPack respects SEC EDGAR fair access policies:

- **User-Agent**: Declared with contact info (configurable via `EDGARPACK_USER_AGENT`)
- **Rate Limiting**: 10 requests/second (enforced internally)
- **Caching**: Aggressive caching to minimize redundant requests

Configure your contact info:
```bash
export EDGARPACK_USER_AGENT="MyApp/1.0 (me@example.com)"
```

## Cache

EdgarPack caches SEC responses in `~/.edgarpack/cache/` to avoid redundant requests. Manage cache with:

```bash
edgarpack cache           # Show cache info
edgarpack cache --clear   # Clear cache
```

Or set a custom location:
```bash
export EDGARPACK_CACHE_DIR=/path/to/cache
```

## Static Site

EdgarPack can generate a minimal, offline-friendly static filing browser from a packs directory:

```bash
edgarpack site --packs ./packs --out ./site
```

Hosting options (any static host works):
- **GitHub Pages**: publish the `site/` directory via the `gh-pages` branch (or `/docs`).
- **Netlify**: set the publish directory to `site/`.
- **S3**: sync `site/` to a bucket and enable static website hosting.

## Development

```bash
git clone https://github.com/samay58/edgarpack
cd edgarpack
uv pip install -e ".[dev]"

# Run tests
python3 -m unittest discover -s tests

# Lint + format
ruff check . && ruff format .
```

## Design Principles

- **Determinism**: Same input + version = byte-identical output
- **Fidelity**: Preserve all visible text, remove only noise
- **Best-effort**: Never silently fail. Emit warnings, create `unknown_XX.md` for unmatched content
- **SEC-compliant**: Respect rate limits, declare User-Agent, cache aggressively

## Supported Forms

- **10-K**: Annual reports (Item 1-15 detection)
- **10-Q**: Quarterly reports (Item 1-4 detection)
- **8-K**: Current reports (Item X.XX detection)

## Tested On

We've run EdgarPack on gnarly filings from AI-native public companies:

| Company | Form | Tokens | Sections | Chunks |
|---------|------|--------|----------|--------|
| BigBear.ai | 10-K | 222,462 | 77 | 225 |
| SoundHound AI | 10-K | 143,352 | 27 | 139 |
| Palantir | 10-K | 137,684 | 27 | 140 |
| C3.ai | 10-K | 135,146 | 55 | 145 |
| NVIDIA | 10-K | 106,870 | 27 | 115 |

BigBear.ai's 10-K is a monster. 222K tokens, 77 sections (lots of financial notes that get split out), and it processes cleanly. If your filing is weirder than that, open an issue.

## License

MIT
