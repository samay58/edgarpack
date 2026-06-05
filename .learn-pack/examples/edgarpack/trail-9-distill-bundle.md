# Trail 9: Distill one pack into cited rows

Time: about 9 minutes.

`distill` reads one existing pack and writes a smaller bundle under `reports/<slug>/`.

Run:

```bash
edgarpack distill run lime-s1 --pack packs/0001699963/0001628280-26-032523
edgarpack distill check reports/lime-s1
```

The output is not a memo. It is a compact evidence surface: findings, metrics, evidence records, gaps, a filing map, and a run log.

## Try it

Start with a registration pack that already has S-1 financial extraction:

```bash
edgarpack distill run lime-s1 --pack packs/0001699963/0001628280-26-032523
```

Then validate it:

```bash
edgarpack distill check reports/lime-s1
```

Open the output folder:

```bash
ls reports/lime-s1
```

Read `index.md` first. Then open `findings.csv`, `metrics.csv`, `evidence.jsonl`, and `gaps.csv`. The exercise is simple: every finding or metric row should point to evidence, and every missing area should show up as a gap.

## What it reads

`distill run` resolves the pack path and loads `manifest.json`. Version 1 has first-class support for registration forms. If you point it at a different form family, it records a gap instead of pretending coverage is complete.

Then it reads two sources:

- the registration profile, for business framing, use of proceeds, dilution, lockup terms, and principal holders;
- `s1_financials.json`, for S-1 metric rows when the cache exists and matches the pack.

Every supported row gets an evidence record first. The finding or metric row stores the evidence id. The row is not its own proof.

## Gaps are part of the bundle

Distill writes gaps when source support is missing or unsafe. Common gaps include:

- unsupported form type;
- no registration profile;
- no extracted findings;
- missing or unreadable `s1_financials.json`;
- stale S-1 financial cache schema;
- hash mismatch against `filing.full.md`;
- metric rows outside the normal S-1 annual or interim window;
- metric cache rows with no section or chunk locator;
- partial extraction status.

Query works the same way. Missing evidence should be visible, not smoothed away.

## The bundle files

The fixed output set is:

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

`index.md` is the scan surface. `evidence.jsonl` is the proof surface. `bundle.json` records schema version, file list, counts, filing identity, and warnings.

## The checker enforces references

`distill check` validates an existing bundle. It verifies required files, reads `evidence.jsonl`, validates `bundle.json`, and checks that every `findings.csv` and `metrics.csv` row has evidence ids that exist.

A row without evidence fails. A row pointing to a missing evidence id fails. A bundle with no gaps gets a warning, because a perfectly complete source surface is unusual enough to deserve review.

## In the code

- `edgarpack/cli.py:462` registers `distill`; `_cmd_distill()` starts at `edgarpack/cli.py:1279`.
- `edgarpack/cli.py:1288` handles `distill check`; `edgarpack/cli.py:1303` through `edgarpack/cli.py:1331` handles `distill run`.
- `edgarpack/distill/builder.py:65` builds a bundle from one pack.
- `edgarpack/distill/builder.py:97` records an unsupported-form gap.
- `edgarpack/distill/builder.py:171` adds registration findings.
- `edgarpack/distill/builder.py:250` adds S-1 metrics.
- `edgarpack/distill/builder.py:283` through `edgarpack/distill/builder.py:307` reject stale or hash-mismatched S-1 financial caches.
- `edgarpack/distill/builder.py:318` through `edgarpack/distill/builder.py:370` create metric evidence records and metric rows.
- `edgarpack/distill/models.py:23` through `edgarpack/distill/models.py:116` define the bundle rows and manifest.
- `edgarpack/distill/writers.py:13` writes the eight output files.
- `edgarpack/distill/checks.py:24` validates a bundle.
- `edgarpack/distill/checks.py:112` rejects rows with missing or unknown evidence ids.

For distill work, run:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
uv run pytest tests/test_distill.py -q
```

If you change S-1 extraction upstream, also run the S-1 tests listed in [docs/TESTING.md](../TESTING.md).
