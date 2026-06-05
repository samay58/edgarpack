# Trail 1: Build a filing pack

Time: about 12 minutes.

Run:

```bash
edgarpack build NVDA --form 10-K --with-chunks --out ./packs
```

This creates a local pack from one SEC filing. A pack is the folder that text-heavy features read later: `diff`, `timeline`, `which`, `distill`, the static site, fixtures, and any workflow that needs filing sections instead of only companyfacts values.

For ordinary SEC metric queries, EdgarPack can often use companyfacts directly. For filing text, you need a pack.

## Try it

Build one pack:

```bash
edgarpack build NVDA --form 10-K --with-chunks --out ./packs
```

Then list what was written:

```bash
find ./packs -type f | grep 0001045810 | sort | head -20
```

Open the pack folder and look for these files:

- `filing.full.md`, the whole filing as markdown;
- `sections/`, one file per detected section;
- `manifest.json`, the filing identity and artifact hashes;
- `optional/chunks.ndjson`, because you passed `--with-chunks`.

Now run the same build again:

```bash
edgarpack build NVDA --form 10-K --with-chunks --out ./packs
```

If the pack already has `manifest.json`, EdgarPack should avoid rebuilding it unless you pass `--force`. That behavior is part of how packs stay stable.

## What the pack contains

The main artifacts are:

```text
filing.full.md
sections/<section-id>.md
llms.txt
manifest.json
optional/chunks.ndjson        when --with-chunks is set
optional/xbrl.json            when --with-xbrl is set
```

`manifest.json` records filing identity, section metadata, warnings, token count, source URL, and artifact hashes. That makes the pack auditable. If parser output changes, the manifest changes too.

## The build path

The CLI resolves the filing before the pack builder starts. You can ask for a specific accession, the latest form, or a range through date/count flags. Once one filing has been chosen, `build_pack()` follows a fixed order:

```text
choose the filing
  -> choose packs/<cik>/<accession>/
  -> skip if manifest.json already exists and --force is not set
  -> fetch the primary filing HTML
  -> clean and render markdown
  -> prepend a filing title
  -> split sections
  -> write the full markdown and section files
  -> optionally write chunks and filing-local XBRL
  -> write llms.txt
  -> hash artifacts
  -> write manifest.json
```

The order is part of the contract. If you add a pack artifact that should be tracked, write it before manifest hashing. If it is scratch output, keep it out of the artifact list.

## The parser is a cleanup chain, not a browser

The HTML path is intentionally small:

| Pass | What it does |
| --- | --- |
| `strip_ixbrl()` | removes inline XBRL tag markup while keeping visible text |
| `clean_html()` | drops scripts, hidden blocks, event handlers, and unsafe attributes |
| `reduce_to_semantic()` | normalizes the HTML shape and resolves filing links |
| `render_markdown()` | turns headings, tables, lists, links, and prose into markdown |
| `sectionize()` | splits the markdown into form-aware section files |

Do not reorder those passes casually. The renderer assumes noisy HTML has already been cleaned. The sectionizer assumes the markdown is already normalized.

## Registration filings take one extra step

S-1 and F-1 filings often have weak body headings. Some use table-of-contents links and body `id=` anchors instead of useful `<h1>` or `<h2>` tags. EdgarPack handles that before normal cleanup.

For registration forms, the build path injects headings from the TOC before `clean_html()` strips attributes. Then it runs the same render and sectionize path. That is why `build_pack()` uses the resolved filing form instead of trusting the form string the caller typed.

This matters later. If the S-1 pack does not have usable sections, S-1 financial extraction, registration timelines, and distill bundles have much less to anchor on.

## What to check when this changes

Parser changes are easy to underestimate. A small cleanup rule can alter section IDs, chunk spans, manifest hashes, and every downstream fixture that reads a pack.

For normal pack changes:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
```

For riskier parser changes, add the live and determinism lanes from [docs/TESTING.md](../TESTING.md):

```bash
uv run pytest tests/test_live_sec_integration.py -q --run-live-sec
uv run pytest tests/test_determinism.py -q --run-live-sec --run-slow
```

## In the code

- `edgarpack/cli.py:363` registers `build`; `_cmd_build()` starts at `edgarpack/cli.py:1334`.
- `edgarpack/pack/build.py:145` is `build_pack()`.
- `edgarpack/pack/build.py:173` through `edgarpack/pack/build.py:329` show the fixed build order.
- `edgarpack/pack/build.py:91` runs the form-aware HTML processing path.
- `edgarpack/pack/build.py:232` through `edgarpack/pack/build.py:245` pass the resolved form type into that processing path.
- Parse passes start at `edgarpack/parse/ixbrl_strip.py:38`, `edgarpack/parse/html_clean.py:106`, `edgarpack/parse/semantic_html.py:42`, `edgarpack/parse/md_render.py:43`, and `edgarpack/parse/sectionize.py:864`.
- Manifest hashing and construction start at `edgarpack/pack/manifest.py:97` and `edgarpack/pack/manifest.py:111`.
