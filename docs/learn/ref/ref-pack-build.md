# Reference: pack/build.py

`edgarpack/pack/build.py` (273 lines)

The pack orchestrator. A single `async def build_pack()` walks a 13-step pipeline from filing metadata to a deterministic directory on disk. [Trail 1](../trail-1-build-a-pack.md) walks it narratively; this ref is the lookup.

---

## Data types

### PackResult

```python
class PackResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    output_dir: Path
    filing_meta: dict[str, Any]
    sections_count: int
    tokens_total: int
    warnings: list[str]
    artifacts: list[str]
```

Return type for `build_pack`. `output_dir` is the final pack directory. `filing_meta` is a flat dict with `cik`, `accession`, `form_type`, `filing_date`, `company_name`. `sections_count` / `tokens_total` / `warnings` / `artifacts` are self-explanatory counters and logs. The CLI's `_cmd_build` uses this to print the success summary.

---

## Public functions

### build_pack(cik, accession, form_type, out_dir, with_chunks, with_xbrl, force)

`edgarpack/pack/build.py:55`. The 13-step orchestrator.

**Parameters:**

- `cik` (str): CIK number, with or without leading zeros.
- `accession` (str | None): a specific accession (e.g. `"0001045810-24-000123"`), or `None` to fetch the latest.
- `form_type` (str | None): a form type (e.g. `"10-K"`), used when `accession` is `None`.
- `out_dir` (Path): where to write. Default `Path(".")`. A subdirectory is created at `{out_dir}/{cik}/{accession}`.
- `with_chunks` (bool): if True, also generate `optional/chunks.ndjson`.
- `with_xbrl` (bool): if True, also fetch and write `optional/xbrl.json`.
- `force` (bool): bypass the "already built" early return and rebuild from scratch.

**Raises:** `ValueError` if neither `accession` nor `form_type` is provided, or if no HTML files were returned for the filing.

**Returns:** `PackResult`.

**Pipeline steps:**

1. **Resolve filing metadata**. Call `get_filing_by_accession` or `get_latest_filing`. Returns a `FilingMeta`.
2. **Create output directory structure**. `pack_dir = out_dir / meta.cik / meta.accession`, `sections_dir = pack_dir / "sections"`.
3. **Idempotent early-return checks**. If `pack_dir/manifest.json` already exists (and not `force`), parse it and return a `PackResult` from the existing manifest. Also checks a legacy layout at `out_dir / cik / accession_nodash` for backward compatibility with older pack directories.
4. **Fetch the primary HTML file** via `fetch_primary_filing_html(meta)`. Returns `list[(filename, bytes)]` so the parse pipeline can stay generic.
5. **Run the parse pipeline** via `_process_html_files`. Returns a single markdown string.
6. **Sectionize** via `sectionize(markdown, form_type)`. Returns `list[Section]` and collects any per-section warnings.
7. **Write `filing.full.md`**. The full markdown content.
8. **Write `sections/<id>.md`** for each section.
9. **Optionally write `optional/chunks.ndjson`** via `generate_chunks` + `write_chunks_ndjson`. Failure appends a warning but doesn't abort.
10. **Optionally fetch and write `optional/xbrl.json`** via `fetch_xbrl_facts`. Failure appends a warning but doesn't abort.
11. **Count tokens** via `count_tokens(markdown)`. If tiktoken is unavailable, append a "counts are approximate" warning.
12. **Write `llms.txt`** via `generate_llms_txt` + `write_llms_txt`. Note this happens **before** the manifest so its hash can be included.
13. **Hash all artifacts** via `compute_sha256` over `sorted(set(artifacts))`. Write `manifest.json` via `create_manifest` + `write_manifest`.

The function returns a `PackResult` with the final counts, warnings, and artifact list.

### build_company_llms(cik, out_dir)

`edgarpack/pack/build.py:235`. Generates a company-level `llms.txt` by scanning the packs that already exist for a CIK. Called from `_cmd_company_llms`. Returns the path to the generated file. Raises `ValueError` if no pack directory exists for the CIK or if no processed filings are found.

---

## Private helpers

### `_decode_html_blob(content)`

`edgarpack/pack/build.py:38`. Decode SEC filing bytes using UTF-8, with Latin-1 fallback on `UnicodeDecodeError`. SEC filings are supposed to be UTF-8 but occasionally aren't. The fallback is good enough for ASCII-compatible content.

### `_process_html_files(html_files, base_url)`

`edgarpack/pack/build.py:46`. Runs the parse pipeline on a list of `(filename, bytes)` tuples:

```python
combined_html = "\n".join(_decode_html_blob(content) for _, content in html_files)
html_stripped = strip_ixbrl(combined_html)
html_cleaned = clean_html(html_stripped)
html_semantic = reduce_to_semantic(html_cleaned, base_url=base_url)
return render_markdown(html_semantic)
```

The order is not reorderable. Each pass assumes the previous one has already run. See [Trail 1 step 5](../trail-1-build-a-pack.md#5-the-parse-pipeline-strict-order) for why.

---

## Invariants

- **The parse pipeline is ordered**: strip iXBRL, clean, reduce to semantic, render markdown. `_process_html_files` is the only function that invokes it; reorder here and you break every caller. Enforced at line 48-52.
- **Writes happen before hashes**. The hash step at line 200 enumerates `artifacts` list and hashes files from disk. Any write that happens after the hash step won't appear in the manifest's `artifacts` hash map. The llms.txt write is deliberately at step 11, before the hash step.
- **`manifest.json` is excluded from its own hash map**. Enforced at line 203 (`and artifact != "manifest.json"`). Hashing it would be circular: the manifest contains the hashes of everything else, so its own hash would change every time any other file changed.
- **Artifacts are sorted before hashing**. `sorted(set(artifacts))` at line 201. Sorting gives deterministic hash-map key order, which makes the serialized JSON reproducible byte-for-byte across runs.
- **Manifest timestamps come from the filing date, not wall-clock**. See `pack/manifest.py`: `generated_at` and `source.fetched_at` are both derived from `meta.filing_date` so reruns produce identical timestamps.
- **Idempotent builds**. If the pack already exists and `force` is not set, the function returns from the existing manifest. Running `build` twice on the same filing is free the second time.
- **`--force` means rebuild**. If the directory exists and `force` is set, the directory is removed via `shutil.rmtree` (line 124) and rebuilt from scratch. Any manual edits to files inside the pack are lost.

---

## What this module does not do

- **It does not download companyfacts XBRL data unless `with_xbrl=True`.** The pack's financial content comes from the parsed markdown. XBRL is an optional sidecar.
- **It does not generate chunks unless `with_chunks=True`.** Chunking is for RAG use cases; it's not needed for reading the pack.
- **It does not touch the harvest registry.** Pack building is a pure function of `(cik, accession, form_type)` input and filesystem state. Harvest orchestration is `edgarpack/harvest/`; see that module for batch workflows.
- **It does not fetch related exhibit HTML by default.** Normal builds use the primary filing document and skip `index.json`, consents, certifications, and other exhibit pages. The older multi-file archive helper still exists for explicit callers.
- **It does not re-fetch on a cache hit.** The parse pipeline is rerun every time even if the HTML is cached (SEC filings are immutable, but `_process_html_files` is fast enough that re-running it is cheaper than tracking parse-version staleness). Compare this to the idempotent early-return, which short-circuits the entire build when the pack itself is already on disk.
- **It does not validate section IDs against the manifest.** The manifest records whatever `sectionize` returned. If sectionize is wrong, the manifest is wrong in the same way.
