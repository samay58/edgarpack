# Trail 9: Shrink One Filing Pack Into Cited Rows

Time: about 9 minutes.

`distill` does not fetch filings. It reads one existing pack and writes a small
bundle you can scan or hand to another tool.

Run:

```bash
edgarpack distill run lime-s1 --pack packs/0001699963/0001628280-26-032523
edgarpack distill check reports/lime-s1
```

## The Shape

```
existing pack
  -> load manifest
  -> read registration profile
  -> read S-1 financial cache when present
  -> write evidence records
  -> write finding and metric rows that reference evidence ids
  -> write gaps for missing or unsafe areas
  -> validate files and evidence references
```

The output is intentionally boring. It is not a memo. It is a compact evidence
surface.

## The CLI Is A Small Wrapper

The command is registered in `edgarpack/cli.py:462`; the handler starts at
`edgarpack/cli.py:1279`.

`distill run` resolves the pack path, builds a `DistillBundle`, writes the bundle,
and tells you to run the check. `distill check` validates an existing bundle and
returns non-zero if required files or evidence references are broken. See
`edgarpack/cli.py:1288` through `edgarpack/cli.py:1331`.

## The Builder Reads Existing Evidence

The builder starts at `edgarpack/distill/builder.py:65`.

First it validates the slug and loads `manifest.json`. Then it builds a filing
metadata dict from the manifest, initializes four row lists, and checks the form
family. Version 1 only has first-class registration support. If you run it on a
different form type, it records a gap instead of pretending the extraction is
complete. See `edgarpack/distill/builder.py:72` through
`edgarpack/distill/builder.py:113`.

Then two extractors run:

| Extractor | Code | What it adds |
| --- | --- | --- |
| registration findings | `edgarpack/distill/builder.py:171` | business, use-of-proceeds, dilution, lockup, holders, and related disclosure rows |
| S-1 metrics | `edgarpack/distill/builder.py:250` | financial rows from `s1_financials.json` when the cache is current |

Every finding row gets an `EvidenceRecord` first, then stores that evidence id.
The same rule applies to metric rows. The row is never the proof; the evidence
record is.

## Gaps Are Part Of The Output

The builder writes gaps when something is missing or unsafe:

- unsupported form type;
- no registration profile;
- no extracted findings;
- missing, unreadable, stale, or hash-mismatched `s1_financials.json`;
- metric rows outside the normal registration window;
- metric cache entries without section or chunk locators;
- partial S-1 extraction status.

That is the right failure mode. If the source cannot support a claim, the bundle
should tell the reader where confidence stops.

## The Writer Produces Eight Files

The data contracts are in `edgarpack/distill/models.py:23` through
`edgarpack/distill/models.py:116`. The fixed output list is:

```text
index.md
findings.csv
metrics.csv
evidence.jsonl
gaps.csv
filing-map.md
run-log.md
bundle.json
```

`write_distill_bundle()` writes those files in `edgarpack/distill/writers.py:13`.
The human scan surface is `index.md`; the machine evidence surface is
`evidence.jsonl`; `bundle.json` records counts and schema version. See
`edgarpack/distill/writers.py:19` through `edgarpack/distill/writers.py:30`.

## The Checker Enforces Evidence References

`check_distill_bundle()` starts at `edgarpack/distill/checks.py:24`.

It verifies required files, reads `evidence.jsonl`, validates `bundle.json`, and
checks that every `findings.csv` and `metrics.csv` row has evidence ids that
exist. It also warns when `gaps.csv` has no rows. See
`edgarpack/distill/checks.py:33` through `edgarpack/distill/checks.py:43` and
`edgarpack/distill/checks.py:112` through `edgarpack/distill/checks.py:127`.

The important constraint is simple: every row needs evidence. A row without an
evidence id fails validation. An evidence id that points nowhere fails
validation. Missing source areas belong in `gaps.csv`.

## What To Run

For distill work:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
uv run pytest tests/test_distill.py -q
```

If you change S-1 extraction upstream, also run the S-1 tests listed in
`docs/TESTING.md`.
