# EdgarPack UX: older filings, diagnostics, and citation density

Status: spec, awaiting approval
Author: brainstorming pass via /forge
Target branch: `samay58/build-which-citations`

## Context

Three pieces of friction showed up in user testing that all point at the same root: the CLI is discoverable enough to start but not to scale. `build --form 10-K` fetches only the latest annual, so the registry ends up with one pack per ticker, which then makes `which` look thin and makes diffs uninteresting. When something goes sideways the user sees a lumped `skipped (missing/corrupt manifest)` message that tells them nothing actionable. And when a multi-metric multi-period `query` finally works, the citation block below the table is long, duplicative, and flat text in a terminal that could render hyperlinks.

The fix is three coordinated changes in one spec. They share code paths and motivation; splitting them would mean revisiting the same helpers three times.

## Non-goals

Not in scope: rewriting the KPI extractor, changing the pack-on-disk layout, adding a new storage backend, redesigning `harvest`, or touching `web/` or the FastAPI surface. The sparse-KPI complaint (META, SNAP, AAPL) gets diagnostics via `doctor`; once those reports land, a follow-up spec can target the actual extraction gap.

## Item 1. Older filings through `build`

Capability already exists via `build --accession <accn>`. The gap is that nobody will find it and there is no bulk path.

### Behavior

Add three flags to `build`:

- `--last N` selects the N most recent filings of the chosen form.
- `--after YYYY-MM-DD` lower-bounds the filing-date range.
- `--before YYYY-MM-DD` upper-bounds it.

When any of these is present, `build` enumerates filings through the same `list_filings` path (`edgarpack/sec/submissions.py`) that `_cmd_list` uses, then fans out to `build_pack` for each accession. `--form` defaults to `10-K` in this multi-pack mode, matching what `diff` already does.

Single-filing invocations are unchanged. Existing `--accession` and `--form` (latest) keep today's behavior. The error path at `edgarpack/cli.py:768` keeps guarding against no-argument calls, and grows one hint: when a user runs `build AAPL --form 10-K` and the registry already has that latest pack, print `edgarpack list AAPL --form 10-K` and `edgarpack build AAPL --form 10-K --last 5` as remediation on the "already built" branch at `edgarpack/pack/build.py:100`.

Already-built packs are skipped by default, matching `harvest --refresh` ergonomics (`edgarpack/cli.py:388`). The skipped-count is printed to stderr so users know the enumerate succeeded but didn't rebuild. `--force` forces rebuild of every pack in the range.

### Implementation sketch

One new helper in `edgarpack/pack/build.py`:

```
async def build_pack_range(
    cik: str,
    form_type: str,
    *,
    last: int | None = None,
    after: date | None = None,
    before: date | None = None,
    out_dir: Path,
    with_chunks: bool,
    with_xbrl: bool,
    force: bool,
    concurrency: int = 3,
) -> list[PackResult]
```

It calls `list_filings(cik, form_type=form_type, limit=max(last or 50, 50))`, filters by date window, slices to `--last`, and runs `build_pack` for each under an `asyncio.Semaphore`. The concurrency knob reuses the SEC client throttling that `harvest` already relies on.

`_cmd_build` (`edgarpack/cli.py:767`) branches: if any of `--last`, `--after`, `--before` is set, route to `build_pack_range` and print a one-row summary per accession (reusing `_register_pack_result` per pack). Otherwise keep the single-filing path.

### Argument precedence

`--accession` remains mutually exclusive with range flags. If a user passes both, error with "Either `--accession` (one filing) or `--last`/`--after`/`--before` (a range), not both." Argparse handles this via a small validator in `_cmd_build`.

### Help text

The help for `--form` changes from "Form type: 10-K, 10-Q, 8-K (fetches latest)" to "Form type (default: 10-K when combined with `--last` or a date range; fetches latest when alone)." The `build` top-level description grows a one-line example of `build AAPL --form 10-K --last 5`.

## Item 2. `doctor` command and manifest diagnostics

`corrupt manifest` is a lumped state. The catch at `edgarpack/query/kpi_discover.py:195` swallows four different failures into one label, and there is no way to ask the tool "what is wrong with this pack."

### Refined states

Split the `unreadable_manifest` status into four, all tracked in `DiscoveryDiagnostics` (`edgarpack/query/kpi_discover.py:40`):

- `manifest_missing`: `manifest.json` does not exist.
- `manifest_invalid_json`: file exists, `json.loads` raises `JSONDecodeError`.
- `manifest_schema_mismatch`: JSON parses but `schema_version`, `parser_version`, or required fields are missing or out of range for the current `SCHEMA_VERSION` in `edgarpack/config.py`.
- `manifest_io_error`: `OSError` or `UnicodeDecodeError`.

The `_discover_pack` handler at line 193 catches each exception class separately and returns the narrower status. `_render_which_diagnostics` at `edgarpack/cli.py:2163` prints the count per state with a remediation hint:

```
Discovery summary: 3 cached, 2 skipped (manifest missing; run `edgarpack build <ticker>`)
```

### `doctor` subcommand

Two invocation shapes, one command.

`edgarpack doctor <pack-path>` inspects one pack directory. Reports:

- manifest state (one of the five: `ok`, `manifest_missing`, `manifest_invalid_json`, `manifest_schema_mismatch`, `manifest_io_error`), with the specific parse error when applicable.
- artifact inventory: which of `sections/`, `chunks.ndjson`, `xbrl.json`, `llms.txt` are present, with file sizes.
- KPI coverage: number of catalog concepts resolved (using `kpi_extract.KPI_CATALOG`) and number of discovered MD&A KPIs in the learned registry for this accession.
- remediation hint matched to the failure class.

`edgarpack doctor <ticker>` walks every pack registered for that CIK (using `PackRegistry.list_packs`, same path `which` uses) and emits a compact per-pack row plus an aggregate summary. Output mode is text by default, `--format json` for scripting.

A shared function `diagnose_pack(pack_dir: Path, registry: PackRegistry | None) -> PackDiagnosis` lives in a new `edgarpack/pack/doctor.py` and is used by both CLI shapes. `PackDiagnosis` is a pydantic model so the JSON surface is stable.

### KPI coverage stat

For each pack, `diagnose_pack` computes:

- `catalog_concepts_resolved`: count of `KPI_CATALOG` entries for the form type that have a non-null value in this pack's learned registry row.
- `catalog_concepts_total`: size of the catalog for this form type.
- `discovered_kpi_count`: number of rows in `learned_registry.company_kpi_list(cik, accession)`.
- `sections_count`: from manifest.
- `tokens_total`: from manifest.

A pack is "healthy" when `catalog_concepts_resolved / catalog_concepts_total >= 0.5`. Below that threshold the report flags it as "low coverage" with the specific missing concept names. This is the diagnostic layer the user asked for in META, SNAP, AAPL cases. Actual fixes to the extractor follow separately based on what the report surfaces.

## Item 3. Citation density and the FCF duplication

### OSC-8 clickable markers

`primary_link` already constructs real SEC URLs (`edgarpack/query/models.py:152`). The only missing piece is wrapping the marker in the terminal escape that makes it clickable in iTerm2, Ghostty, Warp, WezTerm, modern VS Code terminal, and current macOS Terminal.

New helper in a new `edgarpack/query/links.py`:

```
def osc8(url: str, label: str) -> str:
    return f"\x1b]8;;{url}\x1b\\{label}\x1b]8;;\x1b\\"

def supports_osc8(stream=sys.stdout) -> bool:
    if not stream.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    term_program = os.environ.get("TERM_PROGRAM", "")
    return term_program in {"iTerm.app", "WezTerm", "ghostty", "Apple_Terminal", "vscode", "Warp"} \
        or os.environ.get("TERM", "").startswith("xterm")
```

`--show-links` retargets without a breaking flag change:

- `primary` (default): OSC-8-wrap the data-cell marker and the footer citation id. Do not print a separate `link(...)` line. When OSC-8 is not supported, fall back to a single compact URL appended after the footer id on the same line, for example `[C1] 10-K FY2024 | period 2024-06-29 | accn 0001...  sec.gov/.../goog-20240629.htm#f-123`.
- `all`: OSC-8-wrap plus append the compact URL after the footer id in both supported and unsupported terminals.
- `none`: marker only, no URL, no OSC-8.

The separate `link(...)` line at `edgarpack/cli.py:1237` and `edgarpack/query/comps.py:263` is removed.

`_render_citation_lines` (`edgarpack/cli.py:1211`) and the citations loop in `format_comps_table` (`edgarpack/query/comps.py:247`) both route through the new helpers. The data-cell rendering in `_render_query_table` (`edgarpack/cli.py:1322`) wraps the `[{marker}]` string through `osc8(primary_link, marker)` when OSC-8 is on.

### Compact URL form

When the fallback prints a URL inline, shorten the host by stripping `https://www.`:

- `https://www.sec.gov/Archives/edgar/data/1326801/000132680124000073/goog-20240629.htm#f-123`
- shortens to `sec.gov/Archives/edgar/data/1326801/000132680124000073/goog-20240629.htm#f-123`

No further shortening; path segments are meaningful and the user asked for "shorthand, not obfuscation."

### Formula dedup in multi-period grids

The root cause is in `_register_calculation` (`edgarpack/query/comps.py:83`). Today `calc_key = f"{metric_name}|{item.citation_key}"` gives each period its own `calc_id` because `citation_key` varies by period. This is correct for component tracking but wrong for formula display.

Split the concept into two keys:

- `formula_key = (metric_name, kind)`: stable per metric (all FCF rows share one formula string).
- `calc_key` stays as it is, so per-period components still get unique ids.

New `formula_records: dict[str, FormulaRecord]` alongside `calc_records`. A `FormulaRecord` holds the one-line formula, the kind (`ltm`, `derived`, `cagr`), and a list of component bindings keyed by `calc_id`.

In the footer, `Calculations:` becomes:

```
Calculations:
  free_cash_flow = cashFlowFromOperations - capitalExpenditures
    [D1] FY2024: operatingCashFlow[C4] - capitalExpenditure[C5]
    [D2] FY2023: operatingCashFlow[C6] - capitalExpenditure[C7]
    [D3] FY2022: operatingCashFlow[C8] - capitalExpenditure[C9]
    [D4] FY2021: operatingCashFlow[C10] - capitalExpenditure[C11]
```

Formula appears once per metric. Component citation ids stay period-specific so data-cell markers still point at the right row.

The components subtable is gated behind `--audit`. Without `--audit`, the footer shows the one-line formula only:

```
Calculations:
  [D1..D4] free_cash_flow = cashFlowFromOperations - capitalExpenditures  (FY2024, FY2023, FY2022, FY2021)
```

### Single-period path alignment

The single-period path in `_render_query_table` already dedupes naturally (one period, one calc_id). The per-row formula lines at `edgarpack/cli.py:1360-1396` stay the same; this only touches multi-period rendering.

## Files touched

New:
- `edgarpack/pack/doctor.py`: `diagnose_pack`, `PackDiagnosis`.
- `edgarpack/query/links.py`: `osc8`, `supports_osc8`, `compact_url`.

Modified:
- `edgarpack/cli.py`: add `--last`/`--after`/`--before` args to `p_build`, add `p_doctor` subparser, extend `_cmd_build`, add `_cmd_doctor`, update `_render_citation_lines` and `_render_which_diagnostics`, remove the separate link line.
- `edgarpack/pack/build.py`: add `build_pack_range`, extend the "already built" branch with list/build-range hints.
- `edgarpack/query/comps.py`: split formula vs calc keys in `_register_calculation`, update `format_financial_perf_table` and `format_comps_table` footer rendering, route link rendering through `osc8`.
- `edgarpack/query/kpi_discover.py`: split manifest statuses into four classes in `DiscoveryDiagnostics` and `_discover_pack`.
- `edgarpack/query/kpi_extract.py`: similar split at lines 822 and 876 so `doctor` surfaces the same classification.

Not touched: `pack/manifest.py` (schema is fine), `sec/submissions.py` (has the listing primitive already), `web/`, `api/`.

## Reused, not rebuilt

- `list_filings` in `edgarpack/sec/submissions.py` (line 1114 callsite): the enumeration primitive for `build --last`.
- `PackRegistry.list_packs` in `edgarpack/harvest/registry.py`: the per-CIK pack sweep for `doctor <ticker>`.
- `KPI_CATALOG` in `edgarpack/query/kpi_extract.py`: the catalog for coverage stats in `doctor`.
- `_register_citation` in `edgarpack/query/comps.py`: keep as-is; formula split is orthogonal.
- `_wrap_cli_text` in `edgarpack/cli.py:1199`: the width-aware wrapper stays the rendering primitive.

## Verification

Each feature ships with a concrete run-command plus a fixture assertion so the user can see it work in one terminal session.

Older filings:

```
edgarpack build AAPL --form 10-K --last 3
# expects: 3 packs under ./packs/0000320193/, stderr prints "3 pack(s) built, 0 skipped"
edgarpack build AAPL --form 10-K --last 3
# expects: stderr prints "0 pack(s) built, 3 skipped (already registered)"
edgarpack build AAPL --form 10-K --after 2020-01-01 --before 2022-12-31
# expects: builds 10-Ks filed in that window, count depends on AAPL fiscal calendar
edgarpack list AAPL --form 10-K --limit 5
# sanity: accessions align with what build enumerated
```

Doctor:

```
edgarpack doctor ./packs/0000320193/0000320193-24-000123
# expects: "ok", artifact inventory, catalog_concepts_resolved/total, discovered_kpi_count
edgarpack doctor META
# expects: per-pack rows across every META filing in registry with health column
edgarpack doctor META --format json | jq '.packs[0].catalog_concepts_resolved'
# expects: integer
# manufactured corruption test:
echo "not json" > ./packs/0000320193/0000320193-24-000123/manifest.json
edgarpack doctor ./packs/0000320193/0000320193-24-000123
# expects: status "manifest_invalid_json" with remediation "rebuild with `edgarpack build AAPL --force`"
```

Citations:

```
edgarpack query meta revenue,net_income,operating_income,free_cash_flow --period lfy,lfy-1,lfy-2,lfy-3
# expects in iTerm2/Ghostty: clickable [C*] markers in data cells, clickable ids in footer,
#   no separate "link(...)" lines, one formula line per derived metric.
NO_COLOR=1 edgarpack query meta free_cash_flow --period lfy,lfy-1,lfy-2,lfy-3
# expects: fallback compact URL appended to each footer id on the same line.
edgarpack query meta free_cash_flow --period lfy,lfy-1,lfy-2,lfy-3 --audit
# expects: formula once plus per-period component subtable.
edgarpack query meta revenue --period lfy --show-links none
# expects: markers only, no URLs, no OSC-8.
```

Tests to add:

- `tests/test_build_range.py`: `build_pack_range` enumerates and slices correctly, skips already-built, forces when asked.
- `tests/test_doctor.py`: fixture packs covering each of the five manifest states; assert correct classification and remediation hint.
- `tests/test_links.py`: `supports_osc8` detection under `TERM_PROGRAM` and `isatty` combinations; `osc8` wraps correctly; `compact_url` strips `https://www.`.
- `tests/test_query_multi_period.py`: add an assertion that a multi-metric multi-period render prints each derived-metric formula exactly once.

Ruff and mypy pass. Determinism test (`tests/test_determinism.py --run-slow`) still green.

## Open questions

None. All design decisions resolved through the AskUserQuestion pass.

## Transition

After approval and spec commit, hand off to `/superpowers:writing-plans` for the implementation plan. Planning will decompose these three items into ordered work units with per-unit verification. /forge stops here.
