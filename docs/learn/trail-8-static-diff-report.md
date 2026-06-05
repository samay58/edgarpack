# Trail 8: Write a static diff report

Time: about 10 minutes.

Run:

```bash
edgarpack diff --before packs/NVDA/2024 --after packs/NVDA/2025 --format html --out report.html
```

The HTML diff command does not summarize filings with a model. It reads two local packs, runs the existing section diff, anchors changed paragraphs back to source positions, and writes a static HTML file.

The report is meant to be opened locally and shared as a file. It has embedded CSS and no JavaScript.

## Try it

Build two packs first:

```bash
edgarpack build NVDA --form 10-K --last 2 --with-chunks --out ./packs
```

Then write the HTML report:

```bash
edgarpack diff --ticker NVDA --form 10-K --format html --out ./reports/nvda-10k.html
```

Open the report and click a few source links. Check whether each changed paragraph has enough source context: accession, section, paragraph number, offsets, and pack link.

For a terminal view of the same pair, run:

```bash
edgarpack diff --ticker NVDA --form 10-K --format full
```

## The CLI still resolves real packs

`--format html` is a renderer choice. The command still resolves `--ticker` or explicit `--before` / `--after` into two pack directories. It still refuses to continue if a pack is missing.

For HTML output, `--out` is required. Once the two packs exist, the handler builds a report model and serializes it.

## The report model adds evidence to the diff

The existing diff engine knows which sections and paragraphs changed. The static report needs more context:

- old and new accession;
- CIK and company name;
- form type and filing date;
- section id and section path;
- paragraph index and character offsets;
- optional chunk id;
- SEC source URL;
- local pack file path.

`build_pair_report()` loads both manifests, builds filing and section refs, loads optional chunk maps, runs `diff_filings()`, and adapts the result into a report model.

Modified paragraphs also get token spans so the renderer can highlight replacements without changing the underlying text.

## Paragraph anchors are source positions

The builder reconstructs paragraph locations from each section file. It splits paragraphs, finds their character offsets in the original section text, and stores repeated paragraphs in a queue.

That queue matters. If the same paragraph appears twice, the first changed copy points to the first location and the second changed copy points to the second location. The report should not collapse repeated language into one vague anchor.

Chunk ids are stricter. A paragraph gets a chunk id only when its full character span sits inside the chunk. Partial overlap is not enough, because a chunk id is an evidence claim.

If chunks are missing, the report still has accession, section, paragraph, and offsets. `chunk_status` records whether coverage is available, partial, or missing.

## Long unchanged stretches collapse

The HTML report is not a full filing dump. It keeps a little context around changed runs and collapses long unchanged runs into a count. The source text is still in the pack. The report surface only needs enough context for review.

## Links are guarded

The renderer accepts narrow href shapes:

- SEC source links must be real `http` or `https` URLs;
- timeline page links must be safe relative paths;
- local pack links are emitted as `file://` URIs only when the target stays inside the pack directory.

Unsafe schemes and `../` paths do not become clickable links. This matters because static HTML gets opened outside the app runtime.

## Registration timelines reuse the same report

`edgarpack timeline --series registration --format html` writes one pair report per filing transition and an `index.html` that links the sequence together.

The timeline gives you the filing chain. The pair report gives you paragraph-level evidence for each transition.

## In the code

- `edgarpack/cli.py:704` registers `diff`; `_cmd_diff()` starts at `edgarpack/cli.py:2725`.
- `edgarpack/cli.py:2851` starts registration timeline rendering.
- `edgarpack/diff/report_builder.py:422` builds one pair report.
- `edgarpack/diff/report_builder.py:187` and `edgarpack/diff/report_builder.py:209` build filing and section refs from manifests.
- `edgarpack/diff/report_builder.py:36` builds token spans for modified paragraphs.
- `edgarpack/diff/report_builder.py:266` and `edgarpack/diff/report_builder.py:282` map paragraph text to source offsets and evidence anchors.
- `edgarpack/diff/report_builder.py:83` returns a chunk id only for fully covered paragraph ranges.
- `edgarpack/diff/report_builder.py:150` through `edgarpack/diff/report_builder.py:184` compute chunk coverage status.
- `edgarpack/diff/report_builder.py:368` through `edgarpack/diff/report_builder.py:419` collapse long unchanged runs.
- `edgarpack/diff/html_report.py:543` renders evidence lines.
- `edgarpack/diff/html_report.py:517` keeps local pack links inside the pack root.
- `edgarpack/diff/html_report.py:581` renders the registration timeline index.
