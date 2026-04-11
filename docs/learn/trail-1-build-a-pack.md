# Trail 1: How `edgarpack build` turns a filing into deterministic markdown

**Time**: ~14 minutes
**Prereq**: [Trail 0](trail-0-full-loop.md). It introduces the SEC client and the citation model you'll see again here.
**Covers**: `cli.py`, `pack/build.py`, `sec/submissions.py`, `sec/archives.py`, the five-step parse pipeline, `pack/manifest.py`

The query path is half the system. The other half is `build`: turn a filing's raw HTML into clean markdown with stable section IDs and a hash-addressed manifest. This trail walks the build path end to end and explains what "deterministic" means in practice.

---

## 1. You run the command

```bash
edgarpack build --cik 0001045810 --form 10-K
```

The CLI parses `--cik` and `--form` and dispatches to `_cmd_build` at `edgarpack/cli.py:348`. The function does a quick validation (`--accession` or `--form` must be present) and otherwise mirrors the shape of `_cmd_query`: define an inner `_run()` coroutine, lazily import `build_pack`, run it under `asyncio.run`.

The real work starts when `build_pack(cik, form_type="10-K", out_dir=Path("./packs"), ...)` is called at `edgarpack/cli.py:357`.

**Code**: `edgarpack/cli.py:348` (`_cmd_build`)

---

## 2. Resolve the filing metadata

`build_pack` at `edgarpack/pack/build.py:55` is a 13-step orchestrator. The first step is resolving which filing to fetch.

```python
if accession:
    meta = await get_filing_by_accession(cik, accession, force=force)
elif form_type:
    meta = await get_latest_filing(cik, form_type, force=force)
else:
    raise ValueError("Either accession or form_type must be provided")
```

`get_latest_filing` at `edgarpack/sec/submissions.py:87` fetches `submissions/CIK{cik}.json` from SEC, walks the `filings.recent` arrays, and returns the most recent filing whose form type matches (normalized, so "10K/A" normalizes to "10-K"). The returned `FilingMeta` carries everything the rest of the pipeline needs: `cik`, `accession`, `accession_nodash`, `form_type`, `filing_date`, `primary_document`, `company_name`.

For NVIDIA's latest 10-K, `accession` comes back as `0001045810-24-000123` (example) and `accession_nodash` as `000104581024000123`. Both forms matter: the dashed form is the display/canonical form; the undashed form is what shows up in SEC Archives URL paths.

**Code**: `edgarpack/sec/submissions.py:87` (`get_latest_filing`), `edgarpack/sec/submissions.py:133` (`get_filing_by_accession`)

---

## 3. Figure out where to write

Before doing any work, `build_pack` decides where the pack lives on disk and whether it already exists.

```python
pack_dir = out_dir / meta.cik / meta.accession
legacy_pack_dir = out_dir / meta.cik / meta.accession_nodash
sections_dir = pack_dir / "sections"
```

Two checks run in sequence at `edgarpack/pack/build.py:95-122`:

1. **Idempotent early-return**: if `pack_dir/manifest.json` already exists and `--force` wasn't passed, read the existing manifest and return a `PackResult` immediately with a "pack already exists" warning. The pack is a pure function of the filing; there's no point rebuilding it.
2. **Legacy-layout compatibility**: older versions of EdgarPack used `accession_nodash` as the directory name. If the new directory doesn't exist but the legacy one does, return from the legacy manifest instead. Same early return, different path.

If `--force` was passed, the existing `pack_dir` gets wiped with `shutil.rmtree` at line 124. Then the directories are created fresh.

**Code**: `edgarpack/pack/build.py:89-127`

---

## 4. Fetch the filing HTML

```python
html_files = await fetch_filing_html(meta, force=force)
```

`fetch_filing_html` at `edgarpack/sec/archives.py:132` fetches two things:

1. The filing index JSON at `.../{cik}/{accession_nodash}/index.json`, which lists every file in the filing directory.
2. Every HTML file listed in the index, starting with the primary document.

`identify_html_files` at `edgarpack/sec/archives.py:77` walks the index and picks just the HTML files, putting the primary document first. The remaining files (exhibits, amendments) come next. Each file is fetched via `asyncio.create_task`, so they run in parallel. The SEC rate limiter in `sec/client.py` still governs the request pacing, but the coroutines don't block on each other.

Failures on individual files emit a warning and continue. The filing is partially useful even if one exhibit is unreachable.

The return is `list[tuple[filename, bytes]]`. For a 10-K this is usually 1-3 files: the primary document and maybe an exhibit or two.

**Code**: `edgarpack/sec/archives.py:132` (`fetch_filing_html`), `edgarpack/sec/archives.py:77` (`identify_html_files`)

---

## 5. The parse pipeline (strict order)

This is the core of the build path. `_process_html_files` at `edgarpack/pack/build.py:46` runs the five transforms in a fixed order:

```python
combined_html = "\n".join(_decode_html_blob(content) for _, content in html_files)
html_stripped = strip_ixbrl(combined_html)
html_cleaned = clean_html(html_stripped)
html_semantic = reduce_to_semantic(html_cleaned, base_url=base_url)
return render_markdown(html_semantic)
```

The order is not negotiable. Each pass assumes the previous pass has already run, and reordering breaks invariants downstream.

### Step 5a: `strip_ixbrl`

`edgarpack/parse/ixbrl_strip.py:38` removes inline XBRL tags while keeping their text content. Before:

```html
<p>Revenue: <ix:nonFraction name="us-gaap:Revenues" scale="6">130,497</ix:nonFraction></p>
```

After:

```html
<p>Revenue: 130,497</p>
```

The implementation is pure regex, no DOM parser. It walks `IXBRL_PREFIXES` (the hardcoded list of XBRL namespace prefixes) plus any custom prefixes found in `xmlns:` declarations, builds a single combined regex, and replaces every opening or closing tag with the empty string. The text inside is preserved because the regex only matches the tags themselves.

Why regex instead of a DOM parser? Because namespaced tags like `<ix:nonFraction>` confuse most DOM parsers, and the behavior of EdgarPack's stripper needs to be visible in the code, not hidden in a third-party tree walker.

**Code**: `edgarpack/parse/ixbrl_strip.py:38` (`strip_ixbrl`)

### Step 5b: `clean_html`

`edgarpack/parse/html_clean.py:89` runs a streaming `HTMLParser` (stdlib) that:

- Skips entire subtrees for `<script>`, `<style>`, `<noscript>`, `<nav>`, `<header>`, `<footer>`, `<iframe>`, `<object>`, `<embed>` (`REMOVE_TAGS` at line 18).
- Skips elements that are hidden via inline `style` (display:none, visibility:hidden, zero font-size or dimensions, opacity:0, off-screen absolute positioning).
- Strips `class`, `id`, `style`, `on*` event handlers, and `data-*` attributes from every remaining tag.
- Preserves structural tags even if unknown; `md_render` will drop them later.

The skip logic uses a depth counter (`_skip_depth`), so nested removed subtrees get fully cleared without recursion. Comments are dropped. The result is normalized whitespace: tabs -> spaces, multi-blank-lines collapsed to max 2, trailing/leading whitespace stripped.

This is where SEC filings lose most of their bulk. The raw HTML for a 10-K is often 10-20 MB; after `clean_html` it's a small fraction of that.

**Code**: `edgarpack/parse/html_clean.py:89` (`clean_html`)

### Step 5c: `reduce_to_semantic`

`edgarpack/parse/semantic_html.py:42` normalizes tag shapes so `md_render` has fewer cases to handle:

- Rename presentational tags to semantic equivalents (`<b>` -> `<strong>`, `<i>` -> `<em>`, etc.).
- Unwrap tags that don't have a markdown equivalent (span, font, center, etc.); keep the text, drop the tag.
- If `base_url` was passed in (it always is from `build_pack`), resolve `href` attributes to absolute URLs via `urljoin(base_url, href)`. This is how links in the pack point back to real SEC URLs instead of dangling relative paths.
- Unwrap empty or javascript-only links.

The output is still HTML, but it only uses a small whitelisted set of tags: `<p>`, `<strong>`, `<em>`, `<a>`, `<table>`, `<tr>`, `<td>`, `<th>`, `<ul>`, `<ol>`, `<li>`, `<h1>`-`<h6>`, `<pre>`, `<code>`, `<blockquote>`.

**Code**: `edgarpack/parse/semantic_html.py:42` (`reduce_to_semantic`)

### Step 5d: `render_markdown`

`edgarpack/parse/md_render.py:7` converts the semantic HTML into CommonMark. The pass order inside `render_markdown` is itself strict, and the comment at line 16 says so:

1. Extract `<body>` content if present.
2. Insert a space between adjacent tags (`> <`) so later tag-stripping doesn't concatenate words.
3. Process tables first; they have the most complex structure.
4. Process headings `h1`-`h6`.
5. Process `<pre>` blocks (before inline code, because `<pre>` can contain `<code>`).
6. Process inline `<code>`.
7. Process `<blockquote>`.
8. Process lists.
9. Process `<a>` links.
10. (further passes for strong/em, paragraphs, cleanup.)

Reordering these passes re-wraps table content or collapses section text. Don't do it.

The output is a single markdown string, ready for sectioning.

**Code**: `edgarpack/parse/md_render.py:7` (`render_markdown`)

---

## 6. Sectionize

```python
sections = sectionize(markdown, meta.form_type)
```

`sectionize` at `edgarpack/parse/sectionize.py:742` is form-aware. For a 10-K it knows to look for `PART I`, `PART II`, `PART III`, `PART IV` and `Item 1`, `Item 1A`, etc. For a 10-Q the sections are different. For 8-K, different again.

The flow:

1. Call `find_sections(markdown, form_type)` (line 216) which returns a list of `SectionMatch` namedtuples with position and identifier info.
2. If no matches, return a single `unknown_01` section covering the full document.
3. If there's substantial content before the first match, prepend an `unknown_00` "Preamble" section.
4. For each match, carve out `markdown[match.char_pos : next_match.char_pos]`, generate a slug-based ID via `section_id()` at line 160, wrap in a `Section` object.
5. Run `_filter_toc_stubs` (line 718) to drop table-of-contents entries that look like real sections but are just page-number rows from the TOC.
6. Resolve duplicate IDs by appending a suffix and attaching a warning.

The `section_id` contract is important: for a given `(form_type, part, item, title)` the ID is stable across runs. The `char_start` and `char_end` are stored so readers can map sections back to the full markdown without re-running sectionize.

TOC stub filtering is non-obvious and worth knowing about. SEC filings often contain an ASCII table of contents at the top that lists "Item 1A. Risk Factors ... 17". The regex-based matcher sometimes picks this up as a section match, with a few dozen characters of "page 17" content. `_is_toc_stub` at line 680 walks the section content and checks if it's mostly numeric. If two sections share the same ID and one is a stub, the stub gets dropped so the real content keeps the clean ID.

**Code**: `edgarpack/parse/sectionize.py:742` (`sectionize`), `edgarpack/parse/sectionize.py:216` (`find_sections`), `edgarpack/parse/sectionize.py:680` (`_is_toc_stub`)

---

## 7. Write files in a specific order

Back in `build_pack`, writes happen in a deliberate sequence at `edgarpack/pack/build.py:147-197`:

1. `filing.full.md`: the full markdown, exactly what came out of `render_markdown`.
2. `sections/<section_id>.md`: one file per section, in `sections/`.
3. `optional/chunks.ndjson`: only if `--with-chunks` was passed. Generated by `generate_chunks(sections)` from `pack/chunks.py`.
4. `optional/xbrl.json`: only if `--with-xbrl` was passed. Fetched via `fetch_xbrl_facts(cik, accession)`.
5. Compute `tokens_total` via `count_tokens(markdown)` (tiktoken if available, stdlib fallback otherwise). A warning is appended if tiktoken is missing.
6. `llms.txt`: an index-style entry file for the pack, generated via `generate_llms_txt` and written via `write_llms_txt` from `pack/llms_txt.py`. Note this is written **before** manifest.json so its hash can be included.

The order matters for hashing: step 7 will hash every file on disk, and anything that isn't on disk yet won't be in the manifest.

**Code**: `edgarpack/pack/build.py:147-197`

---

## 8. Hash the artifacts

```python
artifact_hashes: dict[str, str] = {}
for artifact in sorted(set(artifacts)):
    artifact_path = pack_dir / artifact
    if artifact_path.exists() and artifact != "manifest.json":
        artifact_hashes[artifact] = compute_sha256(artifact_path.read_bytes())
```

`sorted(set(artifacts))` at `edgarpack/pack/build.py:201` is the determinism hook. Two things:

1. **Set dedup**: an artifact name might have been appended more than once during the build. The set removes duplicates.
2. **Sort**: the hash map is ordered by path name. Since dicts are ordered in Python 3.7+, this means two runs of `build_pack` on the same filing produce identical byte-order in the manifest.

`manifest.json` is deliberately excluded from the hash map. It doesn't exist yet at this point, and it also contains the hashes of everything else, so hashing it would be circular.

`compute_sha256` in `edgarpack/pack/manifest.py:57` is a one-line `hashlib.sha256(content).hexdigest()` wrapper. No salt, no prefix. The hash is a pure function of the file bytes.

**Code**: `edgarpack/pack/build.py:200-204`, `edgarpack/pack/manifest.py:57`

---

## 9. Write the manifest

```python
manifest = create_manifest(
    filing_meta=meta,
    sections=sections,
    artifacts=artifact_hashes,
    warnings=warnings,
    tokens_total=tokens_total,
    source_url=source_url,
)
write_manifest(manifest, pack_dir)
```

`create_manifest` at `edgarpack/pack/manifest.py:71` builds a Pydantic `Manifest` with sections, artifacts, warnings, filing metadata, and timestamps. The timestamp is the most interesting part:

```python
stable_at = datetime(
    filing_meta.filing_date.year,
    filing_meta.filing_date.month,
    filing_meta.filing_date.day,
    tzinfo=UTC,
)
```

The manifest's `generated_at` and `source.fetched_at` come from the filing date, **not** `datetime.now()`. Two builds of the same filing at different wall-clock times produce manifests with identical timestamps. That's the determinism guarantee: rerun any build, get the same bytes.

The section infos are built in the order sectionize returned them. Each one gets its own SHA256 over the section content. The parser version and schema version come from `config.py` constants (`PARSER_VERSION`, `SCHEMA_VERSION`), which is how a future EdgarPack that changes the parse pipeline can signal "these packs were built by old code" in the manifest.

**Code**: `edgarpack/pack/manifest.py:71` (`create_manifest`), `edgarpack/pack/manifest.py:112-117` (stable timestamp)

---

## 10. Return

`build_pack` returns a `PackResult` pydantic model with `output_dir`, `filing_meta`, `sections_count`, `tokens_total`, `warnings`, and `artifacts`. Back in `_cmd_build`, the CLI prints a success summary:

```
✓ Pack built
  Output: packs/1045810/0001045810-24-000123
  Company: NVIDIA CORP
  Form: 10-K
  Filing Date: 2024-02-21
  Sections: 27
  Tokens: 412,583
```

If the warnings list has anything, up to 10 warnings are printed. Everything on disk is now hashed and referenced in `manifest.json`.

**Code**: `edgarpack/pack/build.py:219` (`PackResult` construction), `edgarpack/cli.py:370-385` (CLI output)

---

## Recap

`build_pack` is a 13-step orchestrator and the order is load-bearing at three different levels. The parse pipeline has strict order because each pass assumes the previous one ran (ixbrl -> clean -> semantic -> markdown). The file write order has strict order because the manifest hashes whatever is on disk at step 8. And the manifest's own timestamp comes from the filing date instead of the current wall clock because the whole pack is supposed to be reproducible bit-for-bit across runs. Two builds of the same filing produce the same bytes. That is what "deterministic" means in this codebase, and it is enforced by a handful of quiet design choices rather than by any single big mechanism.

If you want to modify the build path with confidence, start in `pack/build.py:build_pack`. The function is under 200 lines and the numbered comments explicitly spell out the sequence. Before changing any parse pass, read the five modules under `edgarpack/parse/` in pipeline order. Before changing any write step, trace where the new artifact would show up in the hash map.
