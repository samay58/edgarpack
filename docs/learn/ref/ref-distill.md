# Ref: `edgarpack/distill/`

Use this ref when you are changing the distill bundle contract.

## Modules

| Module | Role |
| --- | --- |
| `edgarpack/distill/models.py` | frozen dataclasses and the fixed output file list |
| `edgarpack/distill/builder.py` | pack-to-bundle extraction |
| `edgarpack/distill/writers.py` | writes markdown, CSV, JSONL, and manifest output |
| `edgarpack/distill/checks.py` | validates required files and evidence references |

## Data Contract

The model file defines the schema version and the fixed eight-file output list at
`edgarpack/distill/models.py:9` through `edgarpack/distill/models.py:20`.

The row types are small:

| Type | Lines | Meaning |
| --- | --- | --- |
| `EvidenceRecord` | `edgarpack/distill/models.py:23` | source text plus accession, form, date, section, chunk, and metadata |
| `FindingRow` | `edgarpack/distill/models.py:40` | a non-financial statement with one or more evidence ids |
| `MetricRow` | `edgarpack/distill/models.py:53` | a metric value with period, unit, currency, and evidence ids |
| `GapRow` | `edgarpack/distill/models.py:69` | a missing, unsupported, stale, or review-needed area |
| `DistillBundle` | `edgarpack/distill/models.py:86` | full in-memory bundle before writing |

`DistillBundle.manifest()` returns schema version, slug, pack path, filing data,
source URL, file list, row counts, and warnings. See
`edgarpack/distill/models.py:100`.

## Builder Contract

`build_distill_bundle()` starts at `edgarpack/distill/builder.py:65`.

Inputs:

- `slug`: output slug under the report root;
- `pack_dir`: existing pack directory;
- `output_root`: root for report output;
- `company_hint`: optional fallback for display metadata.

Output:

- a `DistillBundle` whose rows are ready to write.

Rules:

- The slug must pass `validate_slug()` at `edgarpack/distill/builder.py:32`.
- The pack must have a readable manifest with a filing object.
- Non-registration forms are allowed to produce a bundle, but they record an
  unsupported-form gap.
- Findings are generated from `build_registration_profile()`.
- Metrics are generated only from a current `s1_financials.json` cache.
- Missing or stale sources create `GapRow` entries instead of unsupported claims.

The S-1 metric reader checks cache existence, JSON readability, schema version,
source hash, normal registration-window bounds, section/chunk locators, and
partial extraction status. See `edgarpack/distill/builder.py:250` through
`edgarpack/distill/builder.py:413`.

## Writer Contract

`write_distill_bundle()` starts at `edgarpack/distill/writers.py:13`.

It refuses to overwrite a non-empty output directory unless `force=True`. It then
writes:

- `index.md`;
- `findings.csv`;
- `metrics.csv`;
- `gaps.csv`;
- `evidence.jsonl`;
- `filing-map.md`;
- `run-log.md`;
- `bundle.json`.

CSV tuple fields are joined with semicolons. Evidence records are JSONL using
`EvidenceRecord.to_dict()`. The index is a human scan surface; it is not the
source of truth. See `edgarpack/distill/writers.py:33`,
`edgarpack/distill/writers.py:51`, and `edgarpack/distill/writers.py:56`.

## Check Contract

`check_distill_bundle()` starts at `edgarpack/distill/checks.py:24`.

It validates:

- bundle path exists and is a directory;
- every required output file exists;
- `evidence.jsonl` is valid JSONL and each record has `id` and `text`;
- `bundle.json` has required top-level keys;
- finding and metric rows have evidence ids;
- every evidence id referenced by a row exists in `evidence.jsonl`;
- gaps have `area` and `issue`.

The evidence reference check is the load-bearing rule. It lives at
`edgarpack/distill/checks.py:112`.

## Tests

Run:

```bash
uv run pytest tests/test_distill.py -q
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
```

If the S-1 financial cache shape changes, run the S-1 extraction tests too.
