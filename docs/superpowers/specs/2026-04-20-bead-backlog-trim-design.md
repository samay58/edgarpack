# Bead Backlog Trim

## Context

EdgarPack's bead list has ballooned to 30 open issues, most from a recent code-review pass that spun up 16 new refactor beads in one session. The CLI is the product; China Lens and the observatory web view are parked experiments, not live surfaces. The cost of carrying 30 beads is that every `bd ready` returns noise and the genuinely load-bearing work gets drowned. Goal for this session: close the beads that don't back a concrete CLI user story, ship the ones that do, and leave a six-item backlog that reflects what's actually next.

## Disposition

### Keep and complete this session (6)

| ID | Title | Why it stays |
|---|---|---|
| edgarpack-4jc (P1) | Query: companyfacts typed FetchResult | Silent `{}` fallback in `fetch_company_facts` makes network failures indistinguishable from "filer has no XBRL." Both surface as `N/A`. Truthfulness bug on the core CLI read path. |
| edgarpack-zfr (P2) | Sectionizer fragments as fake sections | Cross-ref sentences and exhibit footnotes get promoted to sections; they show up as junk `added` rows in diff output. Core CLI surface. |
| edgarpack-wbm (P2) | revenue_per_employee unit handling | `unit: ratio` skips FX conversion; correct for dimensionless ratios, wrong for per-employee currency scalars. Bites any non-USD filer. |
| edgarpack-x1y (P2) | --strict parity across query / comps / compare | `--strict` means different things across the three CLI paths today. Real consistency bug users already hit. |
| edgarpack-r9a (P2) | Compare: rebase on async comps primitives | `compare` has its own sequential `for ticker in tickers: await fetch(...)`. Deduping it against `comps` removes one implementation and speeds compare up. |
| edgarpack-3yv (P2) | Tencent (0700.HK) + Meituan (3690.HK) HKEX packs | Extends the compare narrative ('AI labs vs domestic funders') with real filings. Infra already exists from the HKEX work. |

### Close as wontfix (25)

Each close gets `--reason="Closed per docs/superpowers/specs/2026-04-20-bead-backlog-trim-design.md: <one-line reason>"` so a future session can find the context and reopen with one command.

*China Lens (parked surface):* `lb1` (epic, all P1 children shipped), `lb1.4`, `lb1.7`, `lb1.11`, `lb1.12`, `lb1.14`, `4o4`, `kax`.

*Observatory web (parked surface):* `8o5`, `s7k`, `cl6`, `82n`.

*Pure refactors with no user story:* `6sl` (split build.py), `y5l` (typed-stage pipeline), `7vl` (god-files split), `42z` (docs consolidation), `12t` (mypy-to-green), `may` (shared asset resolver), `y7e` (section/form helpers), `76u` (compare parallelize + observatory cache), `cm0` (structured try_extract_kpi return for finer Diagnostic kinds).

*HKEX code-org polish:* `czk` (split `_query_hkex_pack`), `5jr` (principled HKEX sign convention).

*P3 features without a concrete trigger:* `707` (MDA expected-rewrite handling), `8zb` (cross-company diff pattern detection).

## Implementation Notes

### edgarpack-4jc — companyfacts typed result

`edgarpack/sec/xbrl.py` gains a `FactsFetchResult` dataclass with fields `status: Literal["ok","unavailable","fetch_error"]`, `facts: dict`, `error: str | None`, and a new async function `fetch_company_facts_result(cik, force)` that returns it. `fetch_company_facts` stays as a thin wrapper returning `result.facts` so the roughly 50 existing test patches keep working unchanged.

The one real caller, `edgarpack/query/financials.py:304`, switches to `fetch_company_facts_result`. When status is `fetch_error` we emit one `layer_a_fetch_error` Diagnostic per metric with the underlying error string; when status is `unavailable` the loop proceeds as today. `Diagnostic.kind` in `edgarpack/query/models.py` gains the new kind.

Tests: one new case asserting that a fetch_error path emits the diagnostic, one asserting the unavailable path behaves identically to today.

### edgarpack-zfr — sectionizer fragments

`edgarpack/parse/sectionize.py` gains rejection heuristics for heading candidates that look like cross-refs rather than real section titles. Reject if the candidate (a) starts with `(`, (b) is mostly lowercase after stripping leading bullets and punctuation, (c) is shorter than a minimum length post-strip, or (d) matches a cross-reference pattern (reuse `_CROSS_REF_PATTERN` already defined in `edgarpack/diff/section_diff.py`, move to a shared spot if imports get awkward). Add a fixture-based test using a real junk fragment from the bead description.

### edgarpack-wbm — revenue_per_employee unit

Introduce `unit: scalar_native` in the eval golden format. In the compare FX path, `scalar_native` triggers FX conversion same as `scalar` but preserves per-person semantics. Update `tests/eval/china_golden.yaml` to tag revenue_per_employee correctly. Add a regression test covering a non-USD filer.

### edgarpack-x1y — --strict parity

Factor one `_strict_filter(values) -> (kept, rejected)` helper in `edgarpack/query/strict.py` (new file). Semantics: under `--strict`, reject any `CitedValue` whose `source` starts with `learned:`. Call from all three CLI paths (`query`, `comps`, `compare`). Add a per-command test asserting identical rejection semantics.

### edgarpack-r9a — compare async rebase

Replace the sequential fetch in `edgarpack/compare.py` with `asyncio.gather(*[fetch(t) for t in tickers], return_exceptions=True)`. Failed fetches render as error rows rather than sinking the batch. Keep existing formatters unchanged. Smoke test asserts concurrent task count or wall-clock improvement on a mock.

### edgarpack-3yv — Tencent + Meituan

Run the existing HKEX build path for 0700 and 3690 (most recent annual filing). Register the packs. Extend `tests/eval/china_golden.yaml` with a minimal golden per company (revenue + one KPI). Time-box: 45 minutes. If the pipeline hits an unknown concept shape for either filer, document the gap in the commit message, close anyway, open a narrow follow-up bead for the specific concept.

## Execution Order

1. Batch-close the 25 wontfix beads with `bd close ... --reason="..."` in one shot.
2. Execute the KEEP set in order: 4jc, zfr, x1y, wbm, r9a, 3yv. Each is its own commit.
3. Run `pytest tests/ -q` after each commit.
4. End with `ruff check . && ruff format --check .` and `bd sync && git push`.

## Verification

- `bd list --status=open` returns 0 beads after the execute pass.
- `bd stats` reflects 25 wontfix closes plus 6 completed.
- `pytest tests/ -q` stays at or above the 988 pass / 41 skip / 12 xfail baseline. Actual counts should rise slightly as new regression tests land.
- `ruff check .` and `ruff format --check .` clean.
- `git log --oneline` shows one close-batch commit plus six feature commits, each reference-linked to its bead ID.

## Risks and Escape Hatches

The aggressive close risks shuttering something that turns out to be load-bearing. Mitigation: every close points at this spec and the original bead title stays intact, so `bd reopen <id>` restores full context.

The 4jc test surface is the largest unknown. Roughly 50 tests patch `fetch_company_facts` with `return_value={...}`. If the thin-wrapper approach produces unexpected breakage, the fallback is to catch a typed exception inside the existing `fetch_company_facts` wrapper and have financials.py catch it at the call site; no signature change.

3yv depends on the HKEX build pipeline handling 0700 and 3690 without new concept-mapping work. The 45-minute time-box plus fail-open-with-follow-up is the escape hatch.
