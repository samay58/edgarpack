# Trail 1: Build A Deterministic Filing Pack

Time: about 12 minutes.

The query path answers questions from facts. The build path creates the local
object that the rest of the product reads: a pack.

Run:

```bash
edgarpack build NVDA --form 10-K --with-chunks
```

## The Pack Is The Shared Object

```
SEC primary filing HTML
  -> strip iXBRL tags
  -> remove hidden/noisy HTML
  -> keep semantic tags and real links
  -> render markdown
  -> split into stable sections
  -> write pack files
  -> hash artifacts in manifest.json
```

`diff`, `timeline`, `which`, `distill`, `site`, and a lot of test fixtures all
depend on this object being stable.

## The CLI Resolves What To Build

The `build` parser accepts a company, form, accession, range flags, and optional
artifact flags. It is registered in `edgarpack/cli.py:363`. The command handler
starts at `edgarpack/cli.py:1334`.

The handler validates that you are asking for one filing or a range, not both.
It defaults range builds to `10-K` when you give date or count bounds without a
form. It resolves company input before calling the pack builder. The real work
then moves to `build_pack()` in `edgarpack/pack/build.py:145`.

## `build_pack()` Has A Fixed Order

The order is the product contract. The main steps are visible in
`edgarpack/pack/build.py:173` through `edgarpack/pack/build.py:329`:

| Step | Code | Why it exists |
| --- | --- | --- |
| resolve filing | `get_filing_by_accession()` or `get_latest_filing()` | choose one accession before doing IO |
| choose output dir | `packs/<cik>/<accession>/` | make path stable and display-friendly |
| early return | existing `manifest.json` without `--force` | avoid rebuilding a pure output |
| fetch HTML | `fetch_primary_filing_html()` | keep the pack focused on the primary filing |
| parse markdown | `_process_html_files_for_form()` | strip and normalize before sectioning |
| add title | filing title prepended to markdown | give the document identity |
| sectionize | `sectionize(markdown, form_type)` | create section-addressable files |
| optional chunks | `generate_chunks()` | support RAG and evidence lookup |
| optional XBRL | `fetch_xbrl_facts()` | include filing-local facts when requested |
| write `llms.txt` | before manifest hashing | include it in artifact hashes |
| hash artifacts | sorted paths, excluding manifest | keep manifest deterministic |
| write manifest | `create_manifest()` | record source, sections, hashes, warnings |

If you add a new artifact, put it before hashing if it belongs in the manifest.
If it is diagnostic scratch output, do not let it pollute the pack contract.

## The Parse Stack Is Small On Purpose

The parser is not a general browser. It is a filing cleanup chain.

| Pass | Function | Job |
| --- | --- | --- |
| iXBRL strip | `strip_ixbrl()` at `edgarpack/parse/ixbrl_strip.py:38` | remove tag markup while keeping visible text |
| HTML clean | `clean_html()` at `edgarpack/parse/html_clean.py:106` | drop hidden blocks, scripts, event handlers, unsafe attrs |
| semantic HTML | `reduce_to_semantic()` at `edgarpack/parse/semantic_html.py:42` | normalize tags and resolve filing links |
| markdown render | `render_markdown()` at `edgarpack/parse/md_render.py:43` | convert tables, headings, lists, links, code, and prose |
| sectionize | `sectionize()` at `edgarpack/parse/sectionize.py:864` | split by form-aware section rules |

Do not reorder these passes casually. The renderer assumes noisy HTML has already
been stripped. The sectionizer assumes the markdown has already been normalized.

## Registration Filings Get One Extra Gate

`_process_html_files_for_form()` runs the parse pipeline for each filing form.
For registration-class forms, it preserves and prepares enough structure for S-1
heading injection and optional image description work. That gate lives in
`edgarpack/pack/build.py:91` and is why `build_pack()` uses the resolved
`meta.form_type` instead of blindly trusting the caller's form string. See
`edgarpack/pack/build.py:232` through `edgarpack/pack/build.py:245`.

That matters for pre-IPO work. If an S-1 has weak headings, later code cannot
find summary financial data or registration timeline sections unless the pack
was built with the right form context.

## Determinism Comes From The Manifest

The manifest is not just metadata. It is the checksum ledger for the pack.
`build_pack()` computes SHA256 hashes for sorted artifact paths and then writes
`manifest.json`. The hash helper is `compute_sha256()` in
`edgarpack/pack/manifest.py:97`; manifest construction starts at
`edgarpack/pack/manifest.py:111`.

That is why pack changes should show up as meaningful diffs. If you change the
parser, section IDs, chunking, or artifact order, rerun focused tests before
trusting downstream features.

## What To Check After Editing

For normal parser or pack changes:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
```

For riskier parse changes, use the live and determinism lanes in
`docs/TESTING.md`:

```bash
uv run pytest tests/test_live_sec_integration.py -q --run-live-sec
uv run pytest tests/test_determinism.py -q --run-live-sec --run-slow
```

The second lane builds the same filing twice and checks that output does not
drift.
