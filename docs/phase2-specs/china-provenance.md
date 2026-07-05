# Packet: china-provenance

Goal: kill fabricated provenance on the China read path: synthesized fiscal periods, invented filed dates, and the production code path that reads `tests/fixtures/` with a frozen year.

Files owned: `edgarpack/hk/extract.py`, `edgarpack/hk/adapter.py`, `edgarpack/query/financials.py` (China sections only), `edgarpack/query/periods.py` (China point selection only), `edgarpack/query/models.py` (the `filed` field change below), `edgarpack/cli.py` (only the two vestigial lines ~2447-2448), committed fixture packs under `tests/fixtures/china_packs/` (facts.json regeneration only), tests.
Forbidden: `tests/eval/china_golden.yaml` (owned by fx-average). If your changes break a golden value, your change is wrong; if they break golden metadata expectations, mark the fix `blocked` with the detail instead of editing the file.

## Pre-made design decision: `filed` becomes optional

`CitedValue.filed` is currently a required `date` (`edgarpack/query/models.py:38`). Change it to `date | None`. Known serialization/format sites: `models.py:175` (`__str__`), `:256`, `:372`, `:604` (all `str(self.filed)` style); mypy strict will surface the rest (renderers, comps, formatting). Rendering rule: `None` renders as `n/a` in tables and `null` in JSON. The SEC path always sets a real date, so SEC behavior must not change; add a regression test asserting an SEC-path CitedValue still carries its real filed date through table and JSON output.

## Fixes

1. `real-periods`. `hk/extract.py` (~577-578, ~622-623) stamps every fact with synthesized Jan-1/Dec-31 bounds: wrong for non-December HK year-ends, and flow-style bounds are the wrong shape for balance-sheet instants. Carry the real fiscal-year-end where the pack manifest states it; otherwise leave period dates absent rather than fabricated. Balance-sheet concepts (total_assets, total_equity, cash) become instant-style (single date or absent), flow concepts keep ranges.

2. `matched-label`. `HKFact.matched_label` is read by the consumer (`query/financials.py:2362`) but never written into `facts.json` (`hk/extract.py` ~621-631). Serialize it. The reader must tolerate its absence in old packs.

3. `unknown-filer-fail-closed`. `hk/adapter.py` (~133-140) silently defaults unknown filers to CNY/HKFRS. Raise a typed, actionable error naming the stock code and how to supply metadata.

4. `no-fabricated-filed`. `query/financials.py` fabricates `filed = date(fy, 12, 31)` for China facts (`_china_manifest_filed_date` ~2076, assigned ~2111-2113) and `tests/test_china_query_hk.py` asserts the fabricated value (`filed.isoformat() == "2024-12-31"`). Use the manifest's real announcement/filing date when present and parseable; otherwise `filed=None`. Update the enshrining test deliberately (assert `filed is None` for the fixture whose manifest says `announcement_date: "N/A"`).

5. `pack-root-config`. Production probes `tests/fixtures/china_packs/` with `fy = 2024` hardcoded (`query/financials.py` ~1975-2007). Replace with China pack discovery rooted at the standard packs root (`DEFAULT_PACKS_DIR` / the query `--packs` value) plus an env override `EDGARPACK_CHINA_PACK_ROOT` that tests set to the fixtures directory. Derive available fiscal years from the packs actually found, never from a constant. Migrate `tests/test_cli_json_contract.py` and `tests/test_china_query_hk.py` to set the env var (fixture-based behavior itself is fine; it just must be opt-in via config, not baked into production code).

6. `deterministic-selection`. `query/periods.py` (~164-166, ~324): frame-tagged duplicate China points share identical (fy, filed) sort keys, so Python's stable sort makes document order pick the winner. Make selection deterministic with an explicit priority (key-financials/income-statement section id first), and when equal-priority points still conflict on value, return `None` plus a `conflicting_facts`-style diagnostic instead of an arbitrary winner. Regression test: two same-fy points in reversed insertion orders produce identical output.

7. `vestigial`. Remove the never-read `resolved = _synthetic_sse_company(args.company)` assignment at `cli.py` ~2447-2448.

## Fixture regeneration

After changing the facts.json shape, regenerate the committed fixture `facts.json` files by running `extract_facts_from_pack` over each fixture pack under `tests/fixtures/china_packs/` (their `sections/` are committed; the source PDFs are not, and you must not need them). Commit the regenerated files. Native golden values must be unchanged.

## Done definition

All seven fixes tested and green; mypy strict clean across the `filed: date | None` ripple; fixture facts.json regenerated; full offline suite green.
