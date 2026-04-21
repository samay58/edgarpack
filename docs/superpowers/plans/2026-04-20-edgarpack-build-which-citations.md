# EdgarPack UX: older filings, diagnostics, citation density — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three coordinated UX changes — range-based `build`, a `doctor` diagnostic command with split manifest states, and denser/linked citations with de-duplicated formulas — so the CLI scales past one-pack-per-ticker without rewriting any parser or storage layer.

**Architecture:** Two new small modules (`pack/doctor.py`, `query/links.py`), one new async helper (`build_pack_range`) in `pack/build.py`, targeted splits of diagnostics state + formula-vs-calc keying in `query/kpi_discover.py`, `query/kpi_extract.py`, `query/comps.py`, and CLI wiring in `edgarpack/cli.py` (subcommand, argparse flags, citation/remediation renderers). No schema or registry changes.

**Tech Stack:** Python 3.11+, Pydantic, argparse, asyncio, textwrap, SQLite-backed registries already in place. Tests use `unittest.IsolatedAsyncioTestCase` + `AsyncMock` + `tempfile`. Lint: ruff; types: mypy.

**Spec:** `docs/superpowers/specs/2026-04-20-edgarpack-build-which-citations-design.md`

**Test entrypoint:** `.venv/bin/python -m pytest ...` (never use system python — see MEMORY.md)

---

## File map (who owns what)

New files:
- `edgarpack/pack/doctor.py` — `PackDiagnosis` pydantic model + `diagnose_pack()` shared between `_cmd_doctor` single-pack and ticker-sweep modes. Classifies manifest state into one of five enumerated values.
- `edgarpack/query/links.py` — `osc8()`, `supports_osc8()`, `compact_url()`. Pure functions. No I/O beyond reading env vars + `sys.stdout.isatty()`.

Modified files:
- `edgarpack/cli.py` — argparse entries for `--last`/`--after`/`--before` on `build`; new `p_doctor` subparser; `_cmd_doctor` handler; range branch in `_cmd_build`; `_render_citation_lines` routed through new link helpers; `_render_which_diagnostics` shows split counts with remediation hints; main dispatcher routes `doctor`.
- `edgarpack/pack/build.py` — `build_pack_range()` helper that enumerates via `list_filings`, filters by date + `--last`, fan-outs through `asyncio.Semaphore`. The "already built" return branch (`build.py:100`) gets two remediation hint strings.
- `edgarpack/query/kpi_discover.py` — `DiscoveryDiagnostics` gains four fields replacing `unreadable_manifest_packs`; `_discover_pack` splits the exception catch at line 195; the status→counter mapping in the aggregate loop (line 408) is updated.
- `edgarpack/query/kpi_extract.py` — same exception-class split at lines 822 and 876 so `doctor`'s classification stays consistent with Layer B's own logging.
- `edgarpack/query/comps.py` — `_register_calculation()` gains a `formula_records` dict keyed by `(metric_name, kind)`; citation rendering loop removes the separate `link(…)` line and routes through `osc8`/`compact_url`; footer prints each formula exactly once.

Not touched: `pack/manifest.py`, `sec/submissions.py`, `harvest/registry.py`, `web/`, `api/`.

---

## Task ordering rationale

Three independent task groups (A/B/C) each produce working software on their own. Within each group: test first, then implement, then wire into CLI, then commit. Groups run in the order the spec lists them — A unblocks end-to-end verification fixtures for B (more packs to diagnose) and C (more periods to render). But nothing in B or C hard-depends on A's code.

---

## Group A — `build --last/--after/--before` (older filings)

### Task A1: Add argparse flags + mutual-exclusion validation

Add three new flags to `p_build` and a validator that rejects `--accession` combined with any range flag.

**Files:**
- Modify: `edgarpack/cli.py:182-227` (add flags to `p_build`)
- Modify: `edgarpack/cli.py:767-770` (replace single-line error guard with range-aware validator)
- Test: `tests/test_cli_build_range.py` (new file)

- [ ] **A1.1: Write the failing tests**

Create `tests/test_cli_build_range.py`:

```python
"""CLI-level tests for `build` range flags."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from edgarpack.cli import main


class TestBuildRangeArgValidation(unittest.TestCase):
    def test_accession_plus_last_rejected(self) -> None:
        rc = main(["build", "AAPL", "--accession", "0000320193-24-000123", "--last", "3"])
        self.assertEqual(rc, 2)

    def test_accession_plus_after_rejected(self) -> None:
        rc = main(["build", "AAPL", "--accession", "0000320193-24-000123", "--after", "2020-01-01"])
        self.assertEqual(rc, 2)

    def test_accession_plus_before_rejected(self) -> None:
        rc = main(["build", "AAPL", "--accession", "0000320193-24-000123", "--before", "2022-12-31"])
        self.assertEqual(rc, 2)

    def test_no_args_still_rejected(self) -> None:
        rc = main(["build", "AAPL"])
        self.assertEqual(rc, 2)

    def test_last_without_form_defaults_to_10k(self) -> None:
        # --last alone is accepted; --form defaults to 10-K. We patch
        # _cmd_build to capture the resolved args without hitting SEC.
        captured: dict[str, object] = {}

        def _fake_cmd_build(args: object) -> int:
            captured["form"] = getattr(args, "form", None)
            captured["last"] = getattr(args, "last", None)
            return 0

        with patch("edgarpack.cli._cmd_build", side_effect=_fake_cmd_build):
            rc = main(["build", "AAPL", "--last", "3"])
        self.assertEqual(rc, 0)
        self.assertEqual(captured["last"], 3)
        # argparse default lands as None; the range handler picks "10-K".
        # We verify the defaulting in task A3.
        self.assertIn("last", captured)

    def test_bad_date_format_rejected(self) -> None:
        rc = main(["build", "AAPL", "--after", "2020/01/01"])
        self.assertEqual(rc, 2)
```

- [ ] **A1.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli_build_range.py -v`
Expected: FAIL (new flags don't exist; validator still only checks accession/form).

- [ ] **A1.3: Add flags to the `p_build` parser**

In `edgarpack/cli.py`, inside the `p_build` block (currently lines 182-227), append after the `--force` argument:

```python
    p_build.add_argument(
        "--last",
        type=int,
        default=None,
        help="Build the N most recent filings of --form. Mutually exclusive with --accession.",
    )
    p_build.add_argument(
        "--after",
        type=_parse_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Lower bound on filing date for range builds.",
    )
    p_build.add_argument(
        "--before",
        type=_parse_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Upper bound on filing date for range builds.",
    )
```

Add a small argparse type helper near the top of the `build_parser` function (or near other CLI helpers — match local style):

```python
def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected YYYY-MM-DD, got {value!r}"
        ) from exc
```

Ensure `from datetime import date` and `import argparse` are available at module scope (check the existing imports — argparse is already imported as `argparse`, `date` is imported elsewhere; if not, add it).

- [ ] **A1.4: Replace the current validator in `_cmd_build`**

In `edgarpack/cli.py:767-770`, replace:

```python
def _cmd_build(args: Any) -> int:
    if not args.accession and not args.form:
        print("Error: either --accession or --form must be provided", file=sys.stderr)
        return 2
```

with:

```python
def _cmd_build(args: Any) -> int:
    range_flags = (args.last is not None, args.after is not None, args.before is not None)
    is_range = any(range_flags)

    if args.accession and is_range:
        print(
            "Error: use either --accession (one filing) or "
            "--last/--after/--before (a range), not both.",
            file=sys.stderr,
        )
        return 2

    if not args.accession and not args.form and not is_range:
        print(
            "Error: provide --accession, --form, or --last/--after/--before",
            file=sys.stderr,
        )
        return 2

    if is_range and not args.form:
        args.form = "10-K"
```

- [ ] **A1.5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_build_range.py -v`
Expected: PASS.

- [ ] **A1.6: Commit**

```bash
git add tests/test_cli_build_range.py edgarpack/cli.py
git commit -m "build: add --last/--after/--before flags with accession mutex"
```

---

### Task A2: Implement `build_pack_range()`

The enumerate + fan-out helper. Mocks `list_filings` and `build_pack` in the test.

**Files:**
- Modify: `edgarpack/pack/build.py` (append helper after `build_pack`)
- Test: `tests/test_build_range.py` (new file)

- [ ] **A2.1: Write the failing tests**

Create `tests/test_build_range.py`:

```python
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.pack.build import PackResult
from edgarpack.sec.submissions import FilingMeta


def _meta(accn: str, filing_date: date) -> FilingMeta:
    return FilingMeta(
        cik="0000320193",
        accession=accn,
        form_type="10-K",
        filing_date=filing_date,
        primary_document="aapl.htm",
        company_name="Apple Inc.",
    )


def _result(accn: str) -> PackResult:
    return PackResult(
        output_dir=Path(f"/tmp/packs/0000320193/{accn}"),
        filing_meta={"accession": accn, "form_type": "10-K"},
        sections_count=1,
        tokens_total=100,
        warnings=[],
        artifacts=["filing.full.md"],
    )


class TestBuildPackRange(unittest.IsolatedAsyncioTestCase):
    async def test_last_slices_to_n(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [
            _meta("0000320193-24-000001", date(2024, 11, 1)),
            _meta("0000320193-23-000001", date(2023, 11, 1)),
            _meta("0000320193-22-000001", date(2022, 11, 1)),
            _meta("0000320193-21-000001", date(2021, 11, 1)),
        ]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession)),
            ) as mock_build,
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                last=2,
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].filing_meta["accession"], "0000320193-24-000001")
        self.assertEqual(results[1].filing_meta["accession"], "0000320193-23-000001")
        self.assertEqual(mock_build.await_count, 2)

    async def test_after_before_filters_date_window(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [
            _meta("a", date(2024, 11, 1)),
            _meta("b", date(2022, 6, 15)),
            _meta("c", date(2021, 3, 3)),
            _meta("d", date(2019, 12, 1)),
        ]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession)),
            ),
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                after=date(2020, 1, 1),
                before=date(2022, 12, 31),
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        accns = [r.filing_meta["accession"] for r in results]
        self.assertEqual(accns, ["b", "c"])

    async def test_last_and_date_window_compose(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [
            _meta("a", date(2024, 11, 1)),
            _meta("b", date(2022, 6, 15)),
            _meta("c", date(2021, 3, 3)),
            _meta("d", date(2019, 12, 1)),
        ]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession)),
            ),
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                last=1,
                after=date(2020, 1, 1),
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        self.assertEqual([r.filing_meta["accession"] for r in results], ["a"])

    async def test_force_is_passed_through(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [_meta("a", date(2024, 11, 1))]
        mock_build = AsyncMock(side_effect=lambda cik, accession, **kw: _result(accession))
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch("edgarpack.pack.build.build_pack", new=mock_build),
        ):
            await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                last=1,
                out_dir=Path("/tmp/packs"),
                with_chunks=True,
                with_xbrl=True,
                force=True,
            )
        kwargs = mock_build.await_args.kwargs
        self.assertTrue(kwargs["force"])
        self.assertTrue(kwargs["with_chunks"])
        self.assertTrue(kwargs["with_xbrl"])

    async def test_empty_window_returns_empty_list(self) -> None:
        from edgarpack.pack.build import build_pack_range

        filings = [_meta("a", date(2024, 11, 1))]
        with (
            patch(
                "edgarpack.pack.build.list_filings",
                new=AsyncMock(return_value=filings),
            ),
            patch("edgarpack.pack.build.build_pack", new=AsyncMock()) as mock_build,
        ):
            results = await build_pack_range(
                cik="0000320193",
                form_type="10-K",
                after=date(2030, 1, 1),
                out_dir=Path("/tmp/packs"),
                with_chunks=False,
                with_xbrl=False,
                force=False,
            )
        self.assertEqual(results, [])
        self.assertEqual(mock_build.await_count, 0)
```

- [ ] **A2.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_build_range.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_pack_range'`.

- [ ] **A2.3: Implement `build_pack_range`**

In `edgarpack/pack/build.py`, append this import line at the top (alongside the existing `from ..sec.submissions import get_filing_by_accession, get_latest_filing`):

```python
from ..sec.submissions import get_filing_by_accession, get_latest_filing, list_filings
```

Then at the end of the module, add:

```python
import asyncio


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
) -> list[PackResult]:
    fetch_limit = max(last or 50, 50)
    candidates = await list_filings(cik, form_type=form_type, limit=fetch_limit)

    filtered: list = []
    for meta in candidates:
        if after is not None and meta.filing_date < after:
            continue
        if before is not None and meta.filing_date > before:
            continue
        filtered.append(meta)

    filtered.sort(key=lambda m: m.filing_date, reverse=True)
    if last is not None:
        filtered = filtered[:last]

    if not filtered:
        return []

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one(accession: str) -> PackResult:
        async with semaphore:
            return await build_pack(
                cik=cik,
                accession=accession,
                form_type=None,
                out_dir=out_dir,
                with_chunks=with_chunks,
                with_xbrl=with_xbrl,
                force=force,
            )

    tasks = [_one(m.accession) for m in filtered]
    return await asyncio.gather(*tasks)
```

(The `import asyncio` belongs at the top of the module — move it there if ruff complains. Also add `from datetime import date` to the top if not already present.)

- [ ] **A2.4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_build_range.py -v`
Expected: PASS.

- [ ] **A2.5: Commit**

```bash
git add edgarpack/pack/build.py tests/test_build_range.py
git commit -m "pack: add build_pack_range helper with --last/--after/--before semantics"
```

---

### Task A3: Wire `_cmd_build` range branch + already-built remediation hint

**Files:**
- Modify: `edgarpack/cli.py:790-806` (range dispatch in `_cmd_build`)
- Modify: `edgarpack/cli.py:817-825` (already-built warning now surfaces remediation commands)
- Test: extend `tests/test_cli_build_range.py`

- [ ] **A3.1: Write the failing tests**

Append to `tests/test_cli_build_range.py`:

```python
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.pack.build import PackResult


def _result(accn: str, warnings: list[str] | None = None) -> PackResult:
    return PackResult(
        output_dir=Path(f"/tmp/packs/0000320193/{accn}"),
        filing_meta={"accession": accn, "company_name": "Apple Inc.", "form_type": "10-K"},
        sections_count=1,
        tokens_total=100,
        warnings=warnings or [],
        artifacts=["filing.full.md"],
    )


class TestBuildRangeDispatch(unittest.TestCase):
    def test_range_flag_invokes_build_pack_range(self) -> None:
        with (
            patch(
                "edgarpack.cli._cik_from_company_args",
                new=AsyncMock(return_value=(0, "0000320193")),
            ),
            patch(
                "edgarpack.pack.build.build_pack_range",
                new=AsyncMock(return_value=[_result("a"), _result("b")]),
            ) as mock_range,
            patch(
                "edgarpack.cli._register_pack_result",
                return_value=None,
            ),
        ):
            rc = main(["build", "AAPL", "--form", "10-K", "--last", "2"])
        self.assertEqual(rc, 0)
        self.assertEqual(mock_range.await_count, 1)
        kwargs = mock_range.await_args.kwargs
        self.assertEqual(kwargs["last"], 2)
        self.assertEqual(kwargs["form_type"], "10-K")

    def test_already_built_hint_appears_in_single_filing_mode(self) -> None:
        warnings = ["Pack already exists, use --force to rebuild"]
        with (
            patch(
                "edgarpack.cli._cik_from_company_args",
                new=AsyncMock(return_value=(0, "0000320193")),
            ),
            patch(
                "edgarpack.pack.build.build_pack",
                new=AsyncMock(return_value=_result("a", warnings=warnings)),
            ),
            patch("edgarpack.cli._register_pack_result", return_value=None),
            patch("sys.stdout") as mock_stdout,
        ):
            rc = main(["build", "AAPL", "--form", "10-K"])
        self.assertEqual(rc, 0)
        printed = "".join(
            call.args[0] for call in mock_stdout.write.call_args_list if call.args
        )
        self.assertIn("edgarpack list AAPL", printed)
        self.assertIn("--last 5", printed)
```

- [ ] **A3.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli_build_range.py::TestBuildRangeDispatch -v`
Expected: FAIL (range branch missing; remediation hint absent).

- [ ] **A3.3: Wire the range branch in `_cmd_build`**

In `edgarpack/cli.py`, replace the `_run` body's build call (currently at `cli.py:792-806`) with:

```python
        try:
            if is_range:
                from .pack.build import build_pack_range

                results = await build_pack_range(
                    cik=cik,
                    form_type=args.form,
                    last=args.last,
                    after=args.after,
                    before=args.before,
                    out_dir=args.out,
                    with_chunks=bool(args.with_chunks),
                    with_xbrl=bool(args.with_xbrl),
                    force=bool(args.force),
                )
            else:
                result = await build_pack(
                    cik=cik,
                    accession=args.accession,
                    form_type=args.form,
                    out_dir=args.out,
                    with_chunks=bool(args.with_chunks),
                    with_xbrl=bool(args.with_xbrl),
                    force=bool(args.force),
                )
                results = [result]
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        built = 0
        skipped = 0
        for result in results:
            _register_pack_result(result, ticker=resolved_ticker)
            already_built = any(
                "Pack already exists" in w for w in result.warnings
            )
            if already_built:
                skipped += 1
            else:
                built += 1

        if is_range:
            print(
                f"{built} pack(s) built, {skipped} skipped (already registered)",
                file=sys.stderr,
            )
            for result in results[:5]:
                accn = result.filing_meta.get("accession", "?")
                print(f"  ✓ {accn}  {result.output_dir}")
            if len(results) > 5:
                print(f"  ... and {len(results) - 5} more")
            return 0

        result = results[0]
        print("✓ Pack built")
        print(f"  Output: {result.output_dir}")
        print(f"  Company: {result.filing_meta.get('company_name', 'Unknown')}")
        print(f"  Form: {result.filing_meta.get('form_type', 'Unknown')}")
        print(f"  Filing Date: {result.filing_meta.get('filing_date', 'Unknown')}")
        print(f"  Sections: {result.sections_count}")
        print(f"  Tokens: {result.tokens_total:,}")
        print(f"  Registry: ready for `edgarpack which {resolved_label}`")

        if any("Pack already exists" in w for w in result.warnings):
            print(
                "  Already built. To list other filings: "
                f"`edgarpack list {resolved_label} --form {args.form or '10-K'}`"
            )
            print(
                "  To pull older filings: "
                f"`edgarpack build {resolved_label} --form {args.form or '10-K'} --last 5`"
            )

        if result.warnings:
            grouped = _group_build_warnings(result.warnings)
            print(
                f"\nNon-fatal warnings ({len(grouped)} groups from {len(result.warnings)} events):"
            )
            for w in grouped[:10]:
                print(f"  - {w}")
            if len(grouped) > 10:
                print(f"  ... and {len(grouped) - 10} more groups")

        return 0
```

(Delete the original single-filing rendering block that this replaces. Keep the outer `asyncio.run(_run())` return at the bottom of `_cmd_build`.)

- [ ] **A3.4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_build_range.py -v`
Expected: PASS (all A1 + A3 tests).

- [ ] **A3.5: Commit**

```bash
git add edgarpack/cli.py tests/test_cli_build_range.py
git commit -m "cli: route build --last/--after/--before to build_pack_range + add remediation hints"
```

---

### Task A4: Update help text

**Files:**
- Modify: `edgarpack/cli.py:182-205` (`p_build` help strings)

- [ ] **A4.1: Update `p_build` description and `--form` help**

Locate `p_build = sub.add_parser(...)` at `cli.py:182`. Replace the `help=` string and add a `description=`:

```python
    p_build = sub.add_parser(
        "build",
        help="Build a single filing pack, or a range via --last/--after/--before",
        description=(
            "Build and register a filing pack. "
            "Examples: `edgarpack build AAPL --form 10-K` (latest), "
            "`edgarpack build AAPL --form 10-K --last 5` (five most recent), "
            "`edgarpack build AAPL --form 10-K --after 2020-01-01 --before 2022-12-31`."
        ),
    )
```

At `cli.py:201`, replace the `--form` help:

```python
    p_build.add_argument(
        "--form",
        "-f",
        help=(
            "Form type: 10-K, 10-Q, 8-K. "
            "Defaults to 10-K when combined with --last/--after/--before; "
            "fetches latest when used alone."
        ),
    )
```

- [ ] **A4.2: Verify help output**

Run: `.venv/bin/edgarpack build --help`
Expected: the description now mentions `--last` and the date-range example. `--form` help mentions the default behavior.

- [ ] **A4.3: Commit**

```bash
git add edgarpack/cli.py
git commit -m "cli: document build --last/--after/--before in help text"
```

---

## Group B — `doctor` subcommand + split manifest diagnostics

### Task B1: Split `DiscoveryDiagnostics` manifest counters

**Files:**
- Modify: `edgarpack/query/kpi_discover.py:40-51` (dataclass)
- Modify: `edgarpack/query/kpi_discover.py:193-202` (exception catch in `_discover_pack`)
- Modify: `edgarpack/query/kpi_discover.py:408-418` (status→counter mapping)
- Modify: `edgarpack/query/kpi_discover.py:64-68` (`PackDiscoveryResult` status literal)
- Test: `tests/test_kpi_discover_diagnostics.py` (new file)

- [ ] **B1.1: Write the failing tests**

Create `tests/test_kpi_discover_diagnostics.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from edgarpack.harvest.registry import PackRecord
from edgarpack.query.kpi_discover import _discover_pack
from edgarpack.query.learned_registry import LearnedRegistry


def _pack_record(pack_dir: Path) -> PackRecord:
    return PackRecord(
        accession="0000320193-24-000001",
        cik="0000320193",
        ticker="AAPL",
        company_name="Apple Inc.",
        form_type="10-K",
        filing_date="2024-11-01",
        sections_count=10,
        tokens_total=1000,
        pack_dir=str(pack_dir),
        built_at="2024-11-01T00:00:00Z",
    )


class TestManifestStateClassification(unittest.TestCase):
    def test_missing_manifest(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            reg = LearnedRegistry(db_path=Path(td) / "reg.db")
            try:
                result = _discover_pack(
                    pack_record=_pack_record(pack_dir),
                    learned_reg=reg,
                    force=False,
                )
            finally:
                reg.close()
        self.assertEqual(result.status, "manifest_missing")

    def test_invalid_json_manifest(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text("not json", encoding="utf-8")
            reg = LearnedRegistry(db_path=Path(td) / "reg.db")
            try:
                result = _discover_pack(
                    pack_record=_pack_record(pack_dir),
                    learned_reg=reg,
                    force=False,
                )
            finally:
                reg.close()
        self.assertEqual(result.status, "manifest_invalid_json")

    def test_io_error_surfaces_distinct_state(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            # A directory where manifest.json should be → triggers OSError on read.
            (pack_dir / "manifest.json").mkdir()
            reg = LearnedRegistry(db_path=Path(td) / "reg.db")
            try:
                result = _discover_pack(
                    pack_record=_pack_record(pack_dir),
                    learned_reg=reg,
                    force=False,
                )
            finally:
                reg.close()
        self.assertEqual(result.status, "manifest_io_error")
```

- [ ] **B1.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover_diagnostics.py -v`
Expected: FAIL — all three currently return `status="unreadable_manifest"`.

- [ ] **B1.3: Update `DiscoveryDiagnostics` dataclass**

In `edgarpack/query/kpi_discover.py`, replace the `DiscoveryDiagnostics` definition (lines 40-50) with:

```python
@dataclass
class DiscoveryDiagnostics:
    """Structured per-run stats for a `which` invocation."""

    total_registered_packs: int = 0
    eligible_packs: int = 0
    cached_packs: int = 0
    discovered_packs: int = 0
    manifest_missing_packs: int = 0
    manifest_invalid_json_packs: int = 0
    manifest_schema_mismatch_packs: int = 0
    manifest_io_error_packs: int = 0
    llm_failed_packs: int = 0
    empty_packs: int = 0

    @property
    def unreadable_manifest_packs(self) -> int:
        return (
            self.manifest_missing_packs
            + self.manifest_invalid_json_packs
            + self.manifest_schema_mismatch_packs
            + self.manifest_io_error_packs
        )
```

(The property preserves the old aggregate read for any caller that still needs it.)

- [ ] **B1.4: Update `PackDiscoveryResult` status literal**

Replace the status comment in `PackDiscoveryResult` (around `kpi_discover.py:68`):

```python
    status: str
    # one of: cached | discovered | manifest_missing | manifest_invalid_json
    #       | manifest_schema_mismatch | manifest_io_error | llm_failed | empty
```

- [ ] **B1.5: Split the exception catch in `_discover_pack`**

Replace the `try/except` block at `kpi_discover.py:193-202` with:

```python
    pack_dir = Path(pack_record.pack_dir)
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        logger.info("Discovery: manifest.json missing at %s (accn=%s)", pack_dir, accession)
        return PackDiscoveryResult(discovered=[], status="manifest_missing")
    try:
        manifest = _load_pack_manifest(pack_dir)
    except json.JSONDecodeError as e:
        logger.info(
            "Discovery: invalid JSON manifest at %s (accn=%s): %s", pack_dir, accession, e
        )
        return PackDiscoveryResult(discovered=[], status="manifest_invalid_json")
    except (OSError, UnicodeDecodeError) as e:
        logger.info(
            "Discovery: manifest I/O error at %s (accn=%s): %s", pack_dir, accession, e
        )
        return PackDiscoveryResult(discovered=[], status="manifest_io_error")

    # Schema mismatch: manifest parsed but is the wrong shape for this EdgarPack.
    schema_version = manifest.get("schema_version") if isinstance(manifest, dict) else None
    from ..config import SCHEMA_VERSION as _SCHEMA_VERSION

    required_top_level = {"filing", "sections", "parser_version"}
    missing = required_top_level - set(manifest.keys() if isinstance(manifest, dict) else [])
    if not isinstance(schema_version, int) or schema_version != _SCHEMA_VERSION or missing:
        logger.info(
            "Discovery: manifest schema mismatch at %s (accn=%s): schema=%r missing=%s",
            pack_dir,
            accession,
            schema_version,
            sorted(missing),
        )
        return PackDiscoveryResult(discovered=[], status="manifest_schema_mismatch")
```

- [ ] **B1.6: Update the status→counter mapping**

Replace the `if pack_result.status ...` chain at `kpi_discover.py:408-418`:

```python
            if diagnostics is not None:
                status_map = {
                    "cached": "cached_packs",
                    "discovered": "discovered_packs",
                    "manifest_missing": "manifest_missing_packs",
                    "manifest_invalid_json": "manifest_invalid_json_packs",
                    "manifest_schema_mismatch": "manifest_schema_mismatch_packs",
                    "manifest_io_error": "manifest_io_error_packs",
                    "llm_failed": "llm_failed_packs",
                    "empty": "empty_packs",
                }
                attr = status_map.get(pack_result.status)
                if attr is not None:
                    setattr(diagnostics, attr, getattr(diagnostics, attr) + 1)
```

- [ ] **B1.7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover_diagnostics.py -v`
Expected: PASS.

Also run the existing `which` tests to guard against regressions:
Run: `.venv/bin/python -m pytest tests/test_cli_which_ux.py -v`
Expected: PASS (the `unreadable_manifest_packs` property preserves the old read path).

- [ ] **B1.8: Commit**

```bash
git add edgarpack/query/kpi_discover.py tests/test_kpi_discover_diagnostics.py
git commit -m "which: split manifest error state into missing/invalid_json/schema_mismatch/io_error"
```

---

### Task B2: Apply the same split in `kpi_extract.py`

Keeps Layer B's log messages consistent with what `doctor` will report.

**Files:**
- Modify: `edgarpack/query/kpi_extract.py:820-828` (cache-hit path)
- Modify: `edgarpack/query/kpi_extract.py:874-882` (fresh-extract path)

- [ ] **B2.1: Write the failing test**

Add to `tests/test_kpi_discover_diagnostics.py`:

```python
import logging
from unittest.mock import MagicMock, patch


class TestKpiExtractManifestLogging(unittest.TestCase):
    def test_missing_manifest_logs_specific_class(self) -> None:
        # Layer B logs at WARNING. Capture the record and check the message.
        with self.assertLogs("edgarpack.query.kpi_extract", level="WARNING") as cm:
            from edgarpack.query.kpi_extract import _load_pack_manifest
            try:
                _load_pack_manifest(Path("/does/not/exist/pack"))
            except FileNotFoundError:
                logging.getLogger("edgarpack.query.kpi_extract").warning(
                    "probe: FileNotFoundError raised"
                )
        self.assertTrue(any("FileNotFoundError" in m for m in cm.output))
```

(This smoke-tests that the module raises the expected class so the split below is meaningful. The actual log-emission test lives in task B3's integration path.)

- [ ] **B2.2: Split the cache-hit catch (`kpi_extract.py:820-828`)**

Replace:

```python
                try:
                    manifest = _load_pack_manifest(pack_dir)
                except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                    logger.warning(
                        "Layer B cache hit but pack manifest unreadable at %s: %s",
                        pack_dir,
                        e,
                    )
                    return None
```

with:

```python
                try:
                    manifest = _load_pack_manifest(pack_dir)
                except FileNotFoundError:
                    logger.warning(
                        "Layer B cache hit but manifest missing at %s", pack_dir
                    )
                    return None
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Layer B cache hit but manifest is invalid JSON at %s: %s",
                        pack_dir,
                        e,
                    )
                    return None
                except (OSError, UnicodeDecodeError) as e:
                    logger.warning(
                        "Layer B cache hit but manifest I/O error at %s: %s",
                        pack_dir,
                        e,
                    )
                    return None
```

- [ ] **B2.3: Split the fresh-extract catch (`kpi_extract.py:874-882`)**

Replace:

```python
        try:
            manifest = _load_pack_manifest(pack_dir)
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(
                "Layer B extraction skipped: pack manifest unreadable at %s: %s",
                pack_dir,
                e,
            )
            return None
```

with:

```python
        try:
            manifest = _load_pack_manifest(pack_dir)
        except FileNotFoundError:
            logger.warning("Layer B extraction skipped: manifest missing at %s", pack_dir)
            return None
        except json.JSONDecodeError as e:
            logger.warning(
                "Layer B extraction skipped: manifest invalid JSON at %s: %s",
                pack_dir,
                e,
            )
            return None
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(
                "Layer B extraction skipped: manifest I/O error at %s: %s",
                pack_dir,
                e,
            )
            return None
```

- [ ] **B2.4: Run tests + lint**

Run: `.venv/bin/python -m pytest tests/test_kpi_discover_diagnostics.py tests/test_cli_which_ux.py -v`
Run: `ruff check edgarpack/query/kpi_extract.py`
Expected: PASS on both.

- [ ] **B2.5: Commit**

```bash
git add edgarpack/query/kpi_extract.py tests/test_kpi_discover_diagnostics.py
git commit -m "kpi_extract: split manifest exception classes to match discovery diagnostics"
```

---

### Task B3: Update `_render_which_diagnostics` to print split counts with remediation

**Files:**
- Modify: `edgarpack/cli.py:2163-2180`
- Test: `tests/test_cli_which_ux.py` (add new test)

- [ ] **B3.1: Write the failing test**

Add to `tests/test_cli_which_ux.py`:

```python
from edgarpack.cli import _render_which_diagnostics
from edgarpack.query.kpi_discover import DiscoveryDiagnostics


class TestWhichDiagnosticsSplit(unittest.TestCase):
    def test_missing_manifest_emits_specific_remediation(self) -> None:
        d = DiscoveryDiagnostics(manifest_missing_packs=3)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("manifest missing", out)
        self.assertIn("edgarpack build", out)

    def test_invalid_json_emits_specific_hint(self) -> None:
        d = DiscoveryDiagnostics(manifest_invalid_json_packs=2)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("invalid JSON", out)
        self.assertIn("doctor", out)

    def test_schema_mismatch_emits_specific_hint(self) -> None:
        d = DiscoveryDiagnostics(manifest_schema_mismatch_packs=1)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("schema mismatch", out)

    def test_io_error_emits_specific_hint(self) -> None:
        d = DiscoveryDiagnostics(manifest_io_error_packs=1)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("I/O", out)

    def test_no_manifest_issues_renders_cleanly(self) -> None:
        d = DiscoveryDiagnostics(cached_packs=2, discovered_packs=1)
        out = _render_which_diagnostics(d)
        self.assertIsNotNone(out)
        self.assertIn("cached", out)
        self.assertIn("analyzed", out)
```

- [ ] **B3.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli_which_ux.py::TestWhichDiagnosticsSplit -v`
Expected: FAIL — renderer currently only prints the lumped "missing/corrupt manifest" fragment.

- [ ] **B3.3: Rewrite `_render_which_diagnostics`**

Replace the function at `cli.py:2163-2180`:

```python
def _render_which_diagnostics(diagnostics: Any) -> str | None:
    fragments: list[str] = []
    if diagnostics.cached_packs:
        fragments.append(f"{diagnostics.cached_packs} cached")
    if diagnostics.discovered_packs:
        fragments.append(f"{diagnostics.discovered_packs} analyzed")
    if diagnostics.manifest_missing_packs:
        fragments.append(
            f"{diagnostics.manifest_missing_packs} skipped "
            "(manifest missing; run `edgarpack build <ticker>`)"
        )
    if diagnostics.manifest_invalid_json_packs:
        fragments.append(
            f"{diagnostics.manifest_invalid_json_packs} skipped "
            "(manifest invalid JSON; run `edgarpack doctor <pack-dir>` for details)"
        )
    if diagnostics.manifest_schema_mismatch_packs:
        fragments.append(
            f"{diagnostics.manifest_schema_mismatch_packs} skipped "
            "(manifest schema mismatch; rebuild with `edgarpack build <ticker> --force`)"
        )
    if diagnostics.manifest_io_error_packs:
        fragments.append(
            f"{diagnostics.manifest_io_error_packs} skipped "
            "(manifest I/O error; check filesystem permissions)"
        )
    if diagnostics.llm_failed_packs:
        fragments.append(f"{diagnostics.llm_failed_packs} discovery failure(s)")
    if diagnostics.empty_packs:
        fragments.append(f"{diagnostics.empty_packs} with no qualifying KPIs")
    if not fragments:
        return None
    return "Discovery summary: " + ", ".join(fragments)
```

- [ ] **B3.4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_which_ux.py -v`
Expected: PASS.

- [ ] **B3.5: Commit**

```bash
git add edgarpack/cli.py tests/test_cli_which_ux.py
git commit -m "which: render manifest state-specific remediation hints in diagnostics summary"
```

---

### Task B4: Create `edgarpack/pack/doctor.py` with `PackDiagnosis` + `diagnose_pack`

**Files:**
- Create: `edgarpack/pack/doctor.py`
- Test: `tests/test_doctor.py` (new file)

- [ ] **B4.1: Write the failing tests**

Create `tests/test_doctor.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from edgarpack.config import PARSER_VERSION, SCHEMA_VERSION


class TestDiagnosePackManifestStates(unittest.TestCase):
    def _write_ok_manifest(self, pack_dir: Path) -> None:
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "parser_version": PARSER_VERSION,
                    "generated_at": "2024-11-01T00:00:00+00:00",
                    "source": {
                        "url": "https://example.test",
                        "fetched_at": "2024-11-01T00:00:00+00:00",
                    },
                    "filing": {
                        "cik": "0000320193",
                        "accession": "0000320193-24-000001",
                        "form_type": "10-K",
                        "filing_date": "2024-11-01",
                        "company_name": "Apple Inc.",
                    },
                    "sections": [
                        {
                            "id": "part1_item1_business",
                            "title": "Business",
                            "path": "sections/part1_item1_business.md",
                            "char_start": 0,
                            "char_end": 10,
                            "tokens_approx": 3,
                            "sha256": "x",
                        }
                    ],
                    "artifacts": {"filing.full.md": "hash"},
                    "warnings": [],
                    "tokens_total": 3,
                }
            ),
            encoding="utf-8",
        )
        (pack_dir / "sections").mkdir(exist_ok=True)
        (pack_dir / "sections" / "part1_item1_business.md").write_text(
            "# Business\n\nBody", encoding="utf-8"
        )

    def test_ok_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            self._write_ok_manifest(pack_dir)
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "ok")
        self.assertIsNone(diag.manifest_error)
        self.assertGreaterEqual(diag.sections_count, 1)
        self.assertIn("filing.full.md", diag.artifacts_present)

    def test_missing_manifest_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_missing")
        self.assertIn("rebuild", diag.remediation or "")

    def test_invalid_json_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text("not json", encoding="utf-8")
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_invalid_json")
        self.assertIsNotNone(diag.manifest_error)

    def test_schema_mismatch_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text(
                json.dumps({"schema_version": 999, "filing": {}}), encoding="utf-8"
            )
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_schema_mismatch")

    def test_io_error_state(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").mkdir()
            diag = diagnose_pack(pack_dir, registry=None)
        self.assertEqual(diag.manifest_state, "manifest_io_error")


class TestDiagnosePackCoverage(unittest.TestCase):
    def test_json_round_trip_stable(self) -> None:
        from edgarpack.pack.doctor import diagnose_pack

        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            diag = diagnose_pack(pack_dir, registry=None)
            payload = diag.model_dump_json()
        data = json.loads(payload)
        self.assertIn("manifest_state", data)
        self.assertIn("artifacts_present", data)
        self.assertIn("catalog_concepts_total", data)
```

- [ ] **B4.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_doctor.py -v`
Expected: FAIL (`ModuleNotFoundError: edgarpack.pack.doctor`).

- [ ] **B4.3: Create `edgarpack/pack/doctor.py`**

```python
"""Pack health diagnostics shared by `edgarpack doctor` single-pack and ticker modes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..config import SCHEMA_VERSION
from ..harvest.registry import PackRecord, PackRegistry
from .manifest import load_manifest_dict


ManifestState = Literal[
    "ok",
    "manifest_missing",
    "manifest_invalid_json",
    "manifest_schema_mismatch",
    "manifest_io_error",
]


_REMEDIATION: dict[str, str] = {
    "manifest_missing": "rebuild the pack with `edgarpack build <ticker> --force`",
    "manifest_invalid_json": (
        "manifest is not valid JSON; rebuild with `edgarpack build <ticker> --force`"
    ),
    "manifest_schema_mismatch": (
        "manifest schema version does not match this EdgarPack; "
        "rebuild with `edgarpack build <ticker> --force`"
    ),
    "manifest_io_error": "check filesystem permissions at the pack directory",
}

_ARTIFACT_NAMES = ("sections", "chunks.ndjson", "xbrl.json", "llms.txt", "filing.full.md")

_HEALTHY_COVERAGE_THRESHOLD = 0.5


class PackDiagnosis(BaseModel):
    pack_dir: str
    manifest_state: ManifestState
    manifest_error: str | None = None
    cik: str | None = None
    accession: str | None = None
    form_type: str | None = None
    filing_date: str | None = None
    company_name: str | None = None
    sections_count: int = 0
    tokens_total: int = 0
    artifacts_present: list[str] = []
    artifact_sizes: dict[str, int] = {}
    catalog_concepts_total: int = 0
    catalog_concepts_resolved: int = 0
    catalog_concepts_missing: list[str] = []
    discovered_kpi_count: int = 0
    healthy: bool = False
    remediation: str | None = None


def _classify_manifest(pack_dir: Path) -> tuple[ManifestState, str | None, dict | None]:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        return "manifest_missing", None, None
    try:
        manifest = load_manifest_dict(pack_dir, on_missing="raise")
    except json.JSONDecodeError as e:
        return "manifest_invalid_json", str(e), None
    except (OSError, UnicodeDecodeError) as e:
        return "manifest_io_error", str(e), None

    schema_version = manifest.get("schema_version") if isinstance(manifest, dict) else None
    required = {"filing", "sections", "parser_version"}
    missing = required - set(manifest.keys() if isinstance(manifest, dict) else [])
    if not isinstance(schema_version, int) or schema_version != SCHEMA_VERSION or missing:
        err = f"schema_version={schema_version!r} missing_fields={sorted(missing)}"
        return "manifest_schema_mismatch", err, None

    return "ok", None, manifest


def _list_artifacts(pack_dir: Path) -> tuple[list[str], dict[str, int]]:
    present: list[str] = []
    sizes: dict[str, int] = {}
    for name in _ARTIFACT_NAMES:
        candidate = pack_dir / name
        if candidate.exists():
            present.append(name)
            if candidate.is_file():
                sizes[name] = candidate.stat().st_size
            elif candidate.is_dir():
                sizes[name] = sum(
                    f.stat().st_size for f in candidate.rglob("*") if f.is_file()
                )
    return present, sizes


def _coverage(
    manifest: dict, pack_record: PackRecord | None
) -> tuple[int, int, list[str], int]:
    from ..query.kpi_extract import KPI_CATALOG
    from ..query.learned_registry import LearnedRegistry

    form_type = (manifest.get("filing", {}) or {}).get("form_type", "")
    relevant = [
        (metric, kpi_def)
        for metric, kpi_def in KPI_CATALOG.items()
        if not kpi_def.industry or form_type.startswith("10-")
    ]
    total = len(relevant)

    resolved_count = 0
    missing: list[str] = []
    discovered_count = 0

    if pack_record is not None:
        reg = LearnedRegistry()
        try:
            cik = pack_record.cik
            accession = pack_record.accession
            for metric, _ in relevant:
                row = reg.lookup(cik=cik, metric=metric, accession=accession)
                if row is not None and row.value_sample is not None:
                    resolved_count += 1
                else:
                    missing.append(metric)
            discovered_rows = reg.company_kpi_list(cik=cik, accession=accession)
            discovered_count = len(discovered_rows)
        finally:
            reg.close()
    else:
        missing = [metric for metric, _ in relevant]

    return total, resolved_count, missing, discovered_count


def diagnose_pack(pack_dir: Path, registry: PackRegistry | None) -> PackDiagnosis:
    state, error, manifest = _classify_manifest(pack_dir)

    if state != "ok" or manifest is None:
        return PackDiagnosis(
            pack_dir=str(pack_dir),
            manifest_state=state,
            manifest_error=error,
            remediation=_REMEDIATION.get(state),
        )

    filing = manifest.get("filing", {}) if isinstance(manifest, dict) else {}
    cik = filing.get("cik") if isinstance(filing, dict) else None
    accession = filing.get("accession") if isinstance(filing, dict) else None
    sections = manifest.get("sections", []) if isinstance(manifest, dict) else []
    tokens_total = manifest.get("tokens_total", 0) if isinstance(manifest, dict) else 0
    artifacts, sizes = _list_artifacts(pack_dir)

    pack_record: PackRecord | None = None
    if registry is not None and isinstance(cik, str) and isinstance(accession, str):
        matches = registry.list_packs(cik=cik)
        for rec in matches:
            if rec.accession == accession:
                pack_record = rec
                break
    if pack_record is None and isinstance(cik, str) and isinstance(accession, str):
        pack_record = PackRecord(
            accession=accession,
            cik=cik,
            ticker=None,
            company_name=filing.get("company_name", "") if isinstance(filing, dict) else "",
            form_type=filing.get("form_type", "") if isinstance(filing, dict) else "",
            filing_date=filing.get("filing_date", "") if isinstance(filing, dict) else "",
            sections_count=len(sections) if isinstance(sections, list) else 0,
            tokens_total=int(tokens_total) if isinstance(tokens_total, int) else 0,
            pack_dir=str(pack_dir),
            built_at="",
        )

    total, resolved, missing, discovered = _coverage(manifest, pack_record)

    healthy = (total > 0 and resolved / total >= _HEALTHY_COVERAGE_THRESHOLD)
    remediation: str | None = None
    if not healthy and total > 0:
        remediation = (
            f"catalog coverage {resolved}/{total} below "
            f"{int(_HEALTHY_COVERAGE_THRESHOLD * 100)}% threshold; "
            f"missing concepts: {', '.join(missing[:5])}"
            + ("..." if len(missing) > 5 else "")
        )

    return PackDiagnosis(
        pack_dir=str(pack_dir),
        manifest_state="ok",
        cik=cik if isinstance(cik, str) else None,
        accession=accession if isinstance(accession, str) else None,
        form_type=filing.get("form_type") if isinstance(filing, dict) else None,
        filing_date=filing.get("filing_date") if isinstance(filing, dict) else None,
        company_name=filing.get("company_name") if isinstance(filing, dict) else None,
        sections_count=len(sections) if isinstance(sections, list) else 0,
        tokens_total=int(tokens_total) if isinstance(tokens_total, int) else 0,
        artifacts_present=artifacts,
        artifact_sizes=sizes,
        catalog_concepts_total=total,
        catalog_concepts_resolved=resolved,
        catalog_concepts_missing=missing,
        discovered_kpi_count=discovered,
        healthy=healthy,
        remediation=remediation,
    )
```

- [ ] **B4.4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_doctor.py -v`
Expected: PASS.

- [ ] **B4.5: Commit**

```bash
git add edgarpack/pack/doctor.py tests/test_doctor.py
git commit -m "pack: add doctor module with PackDiagnosis + diagnose_pack shared helper"
```

---

### Task B5: Add `doctor` subcommand + `_cmd_doctor`

Two invocation shapes: `edgarpack doctor <pack-dir>` (path argument) and `edgarpack doctor <ticker>` (sweep registry). `--format json` for scripting.

**Files:**
- Modify: `edgarpack/cli.py` (add subparser near other subparsers; add `_cmd_doctor`; add dispatcher entry)
- Test: `tests/test_doctor.py` (add CLI integration tests)

- [ ] **B5.1: Write the failing tests**

Append to `tests/test_doctor.py`:

```python
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from edgarpack.cli import main


class TestDoctorCLI(unittest.TestCase):
    def test_doctor_single_pack_path_text(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            (pack_dir / "manifest.json").write_text("not json", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["doctor", str(pack_dir)])
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("manifest_invalid_json", output)

    def test_doctor_single_pack_path_json(self) -> None:
        with TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            pack_dir.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["doctor", str(pack_dir), "--format", "json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["manifest_state"], "manifest_missing")

    def test_doctor_ticker_sweep_empty_registry(self) -> None:
        from edgarpack.harvest.registry import PackRegistry

        with patch.object(PackRegistry, "list_packs", return_value=[]):
            with patch(
                "edgarpack.cli._resolve_cli_company",
                return_value=type(
                    "C", (), {"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."}
                )(),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = main(["doctor", "AAPL"])
            self.assertEqual(rc, 0)
            self.assertIn("No packs registered", buf.getvalue())
```

- [ ] **B5.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_doctor.py::TestDoctorCLI -v`
Expected: FAIL (no `doctor` command).

- [ ] **B5.3: Register the `doctor` subparser**

In `edgarpack/cli.py`, alongside other `sub.add_parser(...)` calls (put it right after `p_build` to keep related commands grouped, lines ~228):

```python
    p_doctor = sub.add_parser(
        "doctor",
        help="Diagnose a pack directory or sweep every pack for a ticker",
        description=(
            "Inspect pack manifest state, artifact inventory, and KPI coverage. "
            "Pass a pack path for a single-pack report, or a ticker for a sweep."
        ),
    )
    p_doctor.add_argument(
        "target",
        help="Pack directory (e.g. ./packs/0000320193/0000320193-24-000001) or ticker (e.g. AAPL)",
    )
    p_doctor.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
```

- [ ] **B5.4: Add `_cmd_doctor` handler**

Add this function (near `_cmd_build`, around `cli.py:830`):

```python
def _cmd_doctor(args: Any) -> int:
    from .harvest.registry import PackRegistry
    from .pack.doctor import diagnose_pack

    target = args.target
    target_path = Path(target)
    is_path = target_path.exists() and target_path.is_dir()

    registry = PackRegistry()
    results: list = []

    if is_path:
        diag = diagnose_pack(target_path, registry=registry)
        results.append(diag)
    else:
        async def _resolve() -> str | None:
            try:
                resolved = await _resolve_cli_company(target)
            except (UnknownCompany, AmbiguousCompany) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return None
            return resolved.cik

        cik = asyncio.run(_resolve())
        if cik is None:
            return 2
        records = registry.list_packs(cik=cik)
        if not records:
            print(f"No packs registered for {target} (CIK: {cik}). Run `edgarpack build {target}`.")
            return 0
        for rec in records:
            diag = diagnose_pack(Path(rec.pack_dir), registry=registry)
            results.append(diag)

    if args.format == "json":
        payload = (
            results[0].model_dump()
            if len(results) == 1
            else {"packs": [r.model_dump() for r in results]}
        )
        print(json.dumps(payload, indent=2, default=str))
        return 0

    for idx, diag in enumerate(results):
        if idx > 0:
            print("")
        header = diag.accession or Path(diag.pack_dir).name
        print(f"Pack: {header}")
        print(f"  Path: {diag.pack_dir}")
        print(f"  Manifest: {diag.manifest_state}", end="")
        if diag.manifest_error:
            print(f" ({diag.manifest_error})")
        else:
            print("")
        if diag.manifest_state == "ok":
            print(f"  Filing: {diag.form_type} filed {diag.filing_date} ({diag.company_name})")
            print(f"  Sections: {diag.sections_count}  Tokens: {diag.tokens_total:,}")
            if diag.artifacts_present:
                art_line = ", ".join(
                    f"{name} ({diag.artifact_sizes.get(name, 0):,}B)"
                    for name in diag.artifacts_present
                )
                print(f"  Artifacts: {art_line}")
            print(
                f"  Coverage: {diag.catalog_concepts_resolved}/"
                f"{diag.catalog_concepts_total} catalog concepts resolved"
            )
            print(f"  Discovered KPIs: {diag.discovered_kpi_count}")
            health = "healthy" if diag.healthy else "low coverage"
            print(f"  Health: {health}")
        if diag.remediation:
            print(f"  Remediation: {diag.remediation}")

    if len(results) > 1:
        healthy = sum(1 for r in results if r.healthy)
        print("")
        print(
            f"Summary: {healthy}/{len(results)} packs healthy, "
            f"{len(results) - healthy} need attention"
        )

    return 0
```

Also ensure `import json` is already at module scope (it is).

- [ ] **B5.5: Wire the dispatcher**

Near `cli.py:662` in the main command router, add:

```python
    if args.cmd == "doctor":
        return _cmd_doctor(args)
```

(Place it adjacent to `_cmd_build` for reading order.)

- [ ] **B5.6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_doctor.py -v`
Expected: PASS.

- [ ] **B5.7: Smoke-check the CLI**

Run: `.venv/bin/edgarpack doctor --help`
Expected: usage text shows the `target` positional and `--format` flag.

- [ ] **B5.8: Commit**

```bash
git add edgarpack/cli.py tests/test_doctor.py
git commit -m "cli: add `doctor` subcommand for per-pack and per-ticker health reports"
```

---

## Group C — Citation density + formula dedup

### Task C1: Create `edgarpack/query/links.py` (osc8, supports_osc8, compact_url)

**Files:**
- Create: `edgarpack/query/links.py`
- Test: `tests/test_links.py` (new file)

- [ ] **C1.1: Write the failing tests**

Create `tests/test_links.py`:

```python
from __future__ import annotations

import io
import unittest
from unittest.mock import patch


class TestOsc8Helper(unittest.TestCase):
    def test_osc8_wraps_url_and_label(self) -> None:
        from edgarpack.query.links import osc8

        out = osc8("https://example.test/path", "label")
        self.assertEqual(out, "\x1b]8;;https://example.test/path\x1b\\label\x1b]8;;\x1b\\")

    def test_osc8_empty_url_returns_label_untouched(self) -> None:
        from edgarpack.query.links import osc8

        self.assertEqual(osc8("", "label"), "label")


class TestSupportsOsc8(unittest.TestCase):
    def _stream(self, *, tty: bool) -> io.StringIO:
        s = io.StringIO()
        s.isatty = lambda: tty  # type: ignore[method-assign]
        return s

    def test_non_tty_returns_false(self) -> None:
        from edgarpack.query.links import supports_osc8

        self.assertFalse(supports_osc8(self._stream(tty=False)))

    def test_no_color_env_returns_false(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=False):
            self.assertFalse(supports_osc8(self._stream(tty=True)))

    def test_iterm2_detected(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict(
            "os.environ", {"TERM_PROGRAM": "iTerm.app", "NO_COLOR": ""}, clear=False
        ):
            self.assertTrue(supports_osc8(self._stream(tty=True)))

    def test_ghostty_detected(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict(
            "os.environ", {"TERM_PROGRAM": "ghostty", "NO_COLOR": ""}, clear=False
        ):
            self.assertTrue(supports_osc8(self._stream(tty=True)))

    def test_xterm_fallback(self) -> None:
        from edgarpack.query.links import supports_osc8

        with patch.dict(
            "os.environ",
            {"TERM_PROGRAM": "", "TERM": "xterm-256color", "NO_COLOR": ""},
            clear=False,
        ):
            self.assertTrue(supports_osc8(self._stream(tty=True)))


class TestCompactUrl(unittest.TestCase):
    def test_strips_https_www(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(
            compact_url(
                "https://www.sec.gov/Archives/edgar/data/1326801/000132680124000073/goog-20240629.htm#f-123"
            ),
            "sec.gov/Archives/edgar/data/1326801/000132680124000073/goog-20240629.htm#f-123",
        )

    def test_strips_https_only(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(compact_url("https://sec.gov/x"), "sec.gov/x")

    def test_leaves_unknown_scheme_alone(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(compact_url("ftp://example.test"), "ftp://example.test")

    def test_empty_returns_empty(self) -> None:
        from edgarpack.query.links import compact_url

        self.assertEqual(compact_url(""), "")
```

- [ ] **C1.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_links.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **C1.3: Implement `edgarpack/query/links.py`**

```python
"""Terminal link rendering helpers for citation output."""

from __future__ import annotations

import os
import sys
from typing import IO


_OSC8_ENABLED_TERMS = {
    "iTerm.app",
    "WezTerm",
    "ghostty",
    "Ghostty",
    "Apple_Terminal",
    "vscode",
    "Warp",
}


def osc8(url: str, label: str) -> str:
    if not url:
        return label
    return f"\x1b]8;;{url}\x1b\\{label}\x1b]8;;\x1b\\"


def supports_osc8(stream: IO[str] | None = None) -> bool:
    s = stream if stream is not None else sys.stdout
    if not hasattr(s, "isatty") or not s.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program in _OSC8_ENABLED_TERMS:
        return True
    term = os.environ.get("TERM", "")
    return term.startswith("xterm")


def compact_url(url: str) -> str:
    if not url:
        return url
    for prefix in ("https://www.", "http://www.", "https://", "http://"):
        if url.startswith(prefix):
            return url[len(prefix):]
    return url
```

- [ ] **C1.4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_links.py -v`
Expected: PASS.

- [ ] **C1.5: Commit**

```bash
git add edgarpack/query/links.py tests/test_links.py
git commit -m "query: add osc8/supports_osc8/compact_url link helpers"
```

---

### Task C2: Route citation rendering through `osc8` + `compact_url`

Remove the separate `link(…)` line from `_render_citation_lines` and the comps.py footer. In supported terminals, the footer id and data-cell marker become OSC-8 clickable; in unsupported terminals, a compact URL trails the footer id on the same line (`--show-links primary`).

**Files:**
- Modify: `edgarpack/cli.py:1211-1251` (`_render_citation_lines`)
- Modify: `edgarpack/cli.py:1304-1347` (data-cell marker wrap)
- Modify: `edgarpack/query/comps.py:243-277` (footer citations loop)
- Test: `tests/test_links.py` (add rendering tests)

- [ ] **C2.1: Write the failing tests**

Append to `tests/test_links.py`:

```python
class TestRenderCitationLinesRouting(unittest.TestCase):
    def _record(self) -> dict[str, object]:
        return {
            "form_type": "10-K",
            "fiscal_label": "FY2024",
            "period": "2024-06-29",
            "accession": "0001652044-24-000073",
            "filed": "2024-07-31",
            "primary_link": (
                "https://www.sec.gov/Archives/edgar/data/1652044/"
                "000165204424000073/goog-20240629.htm#f-123"
            ),
            "primary_link_type": "source_excerpt",
        }

    def test_no_separate_link_line_in_output(self) -> None:
        from edgarpack.cli import _render_citation_lines

        with patch("edgarpack.query.links.supports_osc8", return_value=False):
            lines = _render_citation_lines(
                "C1", self._record(), show_links="primary", width=120
            )
        joined = "\n".join(lines)
        self.assertNotIn("link(source_excerpt)", joined)
        # Fallback appends compact URL to footer id line.
        self.assertIn("sec.gov/Archives", joined)
        self.assertNotIn("https://www.", joined)

    def test_osc8_wrap_when_terminal_supports(self) -> None:
        from edgarpack.cli import _render_citation_lines

        with patch("edgarpack.query.links.supports_osc8", return_value=True):
            lines = _render_citation_lines(
                "C1", self._record(), show_links="primary", width=120
            )
        joined = "\n".join(lines)
        self.assertIn("\x1b]8;;", joined)
        # In OSC-8 mode, do not also print the compact URL inline.
        self.assertNotIn("sec.gov/Archives", joined.replace("\x1b", " "))

    def test_show_links_all_includes_compact_url(self) -> None:
        from edgarpack.cli import _render_citation_lines

        record = self._record()
        record["links"] = {
            "source_excerpt": record["primary_link"],
            "canonical": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1652044",
        }
        with patch("edgarpack.query.links.supports_osc8", return_value=True):
            lines = _render_citation_lines("C1", record, show_links="all", width=120)
        joined = "\n".join(lines)
        self.assertIn("sec.gov/cgi-bin", joined)

    def test_show_links_none_prints_marker_only(self) -> None:
        from edgarpack.cli import _render_citation_lines

        with patch("edgarpack.query.links.supports_osc8", return_value=True):
            lines = _render_citation_lines("C1", self._record(), show_links="none", width=120)
        joined = "\n".join(lines)
        self.assertNotIn("\x1b]8;;", joined)
        self.assertNotIn("sec.gov", joined)
```

- [ ] **C2.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_links.py -v`
Expected: FAIL on the four new rendering tests.

- [ ] **C2.3: Rewrite `_render_citation_lines`**

Replace `edgarpack/cli.py:1211-1251`:

```python
def _render_citation_lines(
    citation_id: str,
    record: dict[str, object],
    *,
    show_links: str,
    width: int,
) -> list[str]:
    from .query.links import compact_url, osc8, supports_osc8

    lines: list[str] = []
    form_type = record.get("form_type")
    fiscal_label = record.get("fiscal_label")
    period = record.get("period")
    accession = record.get("accession")
    filed = record.get("filed")

    primary = record.get("primary_link")
    primary = primary if isinstance(primary, str) else ""
    osc8_on = supports_osc8()

    marker_label = f"[{citation_id}]"
    if show_links != "none" and osc8_on and primary:
        marker_label = osc8(primary, marker_label)

    summary = (
        f"{marker_label} {form_type} {fiscal_label} | period {period} | "
        f"accn {accession} | filed {filed}"
    )
    if show_links != "none" and not osc8_on and primary:
        summary = f"{summary}  {compact_url(primary)}"
    lines.extend(_wrap_cli_text(summary, width, indent="         "))

    if show_links == "all":
        links = record.get("links", {})
        if isinstance(links, dict):
            for link_key, link_value in links.items():
                if not isinstance(link_value, str) or not link_value:
                    continue
                rendered = compact_url(link_value)
                if osc8_on:
                    rendered = osc8(link_value, rendered)
                lines.extend(
                    _wrap_cli_text(
                        f"     {link_key}: {rendered}", width, indent="         "
                    )
                )

    return lines
```

- [ ] **C2.4: Wrap the data-cell marker in `_render_query_table`**

The single-period path at `edgarpack/cli.py:1322` currently prints `lines.append(f"  {item.fiscal_label}: {_format_value(item)}{marker}")`. Introduce a helper above `_render_query_table` that wraps the marker string with OSC-8 when possible. This same helper is reused in C3 (multi-period formatting).

Add after `_render_citation_lines`:

```python
def _marker_with_link(
    marker: str,
    payload: dict[str, object] | None,
    citations_lookup: dict[str, dict[str, object]],
    calculations_lookup: dict[str, dict[str, object]],
    *,
    show_links: str,
) -> str:
    from .query.links import osc8, supports_osc8

    if show_links == "none" or not marker or not supports_osc8():
        return marker

    tag = marker.strip().lstrip("[").rstrip("]").split(",")[0].strip()
    record: dict[str, object] | None = None
    if tag.startswith(("C",)):
        record = citations_lookup.get(tag)
    elif tag.startswith(("L", "D", "G")):
        calc = calculations_lookup.get(tag)
        if isinstance(calc, dict):
            result_cid = calc.get("result_citation_id")
            if isinstance(result_cid, str):
                record = citations_lookup.get(result_cid)
    if not isinstance(record, dict):
        return marker
    link = record.get("primary_link")
    if not isinstance(link, str) or not link:
        return marker
    return osc8(link, marker)
```

Then in the data-cell rendering (lines `1304-1347`), thread the helper through. This is a light touch: replace `marker = f" [{calc_id}]"` and `marker = f" [{','.join(...)}]"` with calls that pass `marker` to `_marker_with_link` using the already-available `citations` / `calculations` dicts from `result.to_lean_dict()`:

```python
            marker = f" [{calc_id}]"
            marker = _marker_with_link(
                marker,
                payload if isinstance(payload, dict) else None,
                citations,
                calculations,
                show_links=args.show_links if hasattr(args, "show_links") else "primary",
            )
```

Apply the same replacement to both the multi-item loop (around line 1317) and the scalar case (around line 1342).

- [ ] **C2.5: Update `comps.py` citations footer**

Replace `edgarpack/query/comps.py:243-277`:

```python
    if citations_mode != "off":
        from .links import compact_url, osc8, supports_osc8

        osc8_on = supports_osc8()

        if citation_records:
            lines.append("")
            lines.append("Citations:")
            for cid, record in citation_records.items():
                period = record.get("period")
                fiscal = record.get("fiscal_label")
                accn = record.get("accession")
                form_type = record.get("form_type")
                filed = record.get("filed")

                primary = record.get("primary_link")
                primary = primary if isinstance(primary, str) else ""
                label = f"[{cid}]"
                if show_links != "none" and osc8_on and primary:
                    label = osc8(primary, label)

                summary = (
                    f"{label} {form_type} {fiscal} | period {period} | accn {accn} | filed {filed}"
                )
                if show_links != "none" and not osc8_on and primary:
                    summary = f"{summary}  {compact_url(primary)}"
                lines.extend(_with_width(summary, indent="       "))

                if show_links == "all":
                    links = record.get("links", {})
                    if isinstance(links, dict):
                        for link_key, link_value in links.items():
                            if not isinstance(link_value, str) or not link_value:
                                continue
                            rendered = compact_url(link_value)
                            if osc8_on:
                                rendered = osc8(link_value, rendered)
                            lines.extend(
                                _with_width(
                                    f"     {link_key}: {rendered}", indent="       "
                                )
                            )
```

(Delete the old loop body that printed the separate `link(...)` line.)

- [ ] **C2.6: Run tests**

Run: `.venv/bin/python -m pytest tests/test_links.py tests/test_comps.py tests/test_financial_perf_table.py -v`
Expected: PASS.

- [ ] **C2.7: Commit**

```bash
git add edgarpack/cli.py edgarpack/query/comps.py tests/test_links.py
git commit -m "query,cli: route citations through osc8 + compact_url, drop separate link line"
```

---

### Task C3: Split `calc_key` vs `formula_key` and print each formula once

**Files:**
- Modify: `edgarpack/query/comps.py:69-133` (`_register_calculation` + new `formula_records` dict)
- Modify: `edgarpack/query/comps.py:279-299` (Calculations footer in `format_comps_table`)
- Modify: `edgarpack/query/comps.py` (equivalent footer in `format_financial_perf_table`; search for `"Calculations:"` literal)
- Test: `tests/test_query_multi_period.py` (new file)

- [ ] **C3.1: Write the failing tests**

Create `tests/test_query_multi_period.py`:

```python
from __future__ import annotations

import unittest

from edgarpack.query.models import CitedValue, DerivedValue


class TestFormulaDedup(unittest.TestCase):
    def _fcf(self, accession: str, period: str) -> DerivedValue:
        ocf = CitedValue(
            value=1000.0,
            unit="USD",
            metric="cashFlowFromOperations",
            concept="CashFlowFromOperations",
            period_start=f"{period}-01-01",
            period_end=f"{period}-12-31",
            fiscal_year=int(period),
            fiscal_period="FY",
            form_type="10-K",
            filed=f"{period}-12-31",
            accession=accession,
            cik="0001326801",
            company="Alphabet",
            taxonomy="us-gaap",
            primary_document="goog.htm",
            fact_id="f-ocf",
        )
        capex = CitedValue(
            value=300.0,
            unit="USD",
            metric="capitalExpenditure",
            concept="CapitalExpenditure",
            period_start=f"{period}-01-01",
            period_end=f"{period}-12-31",
            fiscal_year=int(period),
            fiscal_period="FY",
            form_type="10-K",
            filed=f"{period}-12-31",
            accession=accession,
            cik="0001326801",
            company="Alphabet",
            taxonomy="us-gaap",
            primary_document="goog.htm",
            fact_id="f-capex",
        )
        derived = DerivedValue(
            value=700.0,
            unit="USD",
            metric="free_cash_flow",
            concept="cashFlowFromOperations - capitalExpenditures",
            period_start=f"{period}-01-01",
            period_end=f"{period}-12-31",
            fiscal_year=int(period),
            fiscal_period="FY",
            form_type="10-K",
            filed=f"{period}-12-31",
            accession=accession,
            cik="0001326801",
            company="Alphabet",
            taxonomy="us-gaap",
            primary_document="goog.htm",
            fact_id="f-fcf",
            components={"cashFlowFromOperations": ocf, "capitalExpenditures": capex},
        )
        return derived

    def test_formula_appears_once_across_periods(self) -> None:
        from edgarpack.query.comps import _register_calculation

        citation_ids: dict[str, str] = {}
        citation_records: dict[str, dict[str, object]] = {}
        calc_ids: dict[str, str] = {}
        calc_records: dict[str, dict[str, object]] = {}
        formula_records: dict[tuple[str, str], dict[str, object]] = {}

        for year, accn in [
            ("2024", "a"),
            ("2023", "b"),
            ("2022", "c"),
            ("2021", "d"),
        ]:
            _register_calculation(
                "free_cash_flow",
                self._fcf(accn, year),
                citation_ids,
                citation_records,
                calc_ids,
                calc_records,
                formula_records=formula_records,
            )

        self.assertEqual(len(calc_records), 4, "one calc per period")
        self.assertEqual(
            len(formula_records), 1, "formula string shared across all periods"
        )
        fk = next(iter(formula_records))
        self.assertEqual(fk[0], "free_cash_flow")
        self.assertEqual(fk[1], "derived")
        bound = formula_records[fk].get("calc_ids")
        self.assertIsInstance(bound, list)
        self.assertEqual(len(bound), 4)
```

- [ ] **C3.2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_query_multi_period.py -v`
Expected: FAIL — `_register_calculation` doesn't accept `formula_records`.

- [ ] **C3.3: Update `_register_calculation`**

Replace `edgarpack/query/comps.py:69-133`:

```python
def _register_calculation(
    metric_name: str,
    item: DerivedValue,
    citation_ids: dict[str, str],
    citation_records: dict[str, dict[str, object]],
    calc_ids: dict[str, str],
    calc_records: dict[str, dict[str, object]],
    formula_records: dict[tuple[str, str], dict[str, object]] | None = None,
) -> str:
    calc_key = f"{metric_name}|{item.citation_key}"
    existing = calc_ids.get(calc_key)
    if existing:
        return existing

    fp = item.fiscal_period.upper()
    if fp.startswith("LTM"):
        prefix = "L"
    elif fp.startswith("CAGR"):
        prefix = "G"
    else:
        prefix = "D"
    next_idx = 1 + sum(1 for cid in calc_records if cid.startswith(prefix))
    calc_id = f"{prefix}{next_idx}"
    calc_ids[calc_key] = calc_id

    components: list[dict[str, object]] = []
    for role, component in item.components.items():
        comp_cid = _register_citation(component, citation_ids, citation_records)
        components.append(
            {
                "role": role,
                "citation_id": comp_cid,
                "value": component.value,
                "unit": component.unit,
                "fiscal_label": component.fiscal_label,
                "period": component._period_str(),
                "accession": component.accession,
            }
        )

    result_cid = _register_citation(item, citation_ids, citation_records)
    if prefix == "L":
        kind = "ltm"
        formula = "mrp + lfy - mrp_prior"
    elif prefix == "G":
        kind = "cagr"
        formula = item.concept
    else:
        kind = "derived"
        formula = item.concept
    calc_records[calc_id] = {
        "id": calc_id,
        "metric": metric_name,
        "kind": kind,
        "formula": formula,
        "result_citation_id": result_cid,
        "components": components,
        "warnings": list(item.warnings),
        "fiscal_label": item.fiscal_label,
    }

    if formula_records is not None:
        formula_key = (metric_name, kind)
        rec = formula_records.get(formula_key)
        if rec is None:
            rec = {
                "metric": metric_name,
                "kind": kind,
                "formula": formula,
                "calc_ids": [],
            }
            formula_records[formula_key] = rec
        bound = rec["calc_ids"]
        if isinstance(bound, list):
            bound.append(calc_id)

    return calc_id
```

- [ ] **C3.4: Thread `formula_records` through both rendering paths**

In `format_comps_table` (search for `calc_ids: dict[str, str] = {}` — it's near `comps.py:170`), add:

```python
    formula_records: dict[tuple[str, str], dict[str, object]] = {}
```

In both call sites inside `format_comps_table` (the single data-cell marker path and any other `_register_calculation` invocations; search `_register_calculation(` in `comps.py`), pass `formula_records=formula_records`.

Replace the `Calculations:` footer in `format_comps_table` (lines `279-299`) with:

```python
        if formula_records:
            lines.append("")
            lines.append("Calculations:")
            for (metric_name, _kind), rec in formula_records.items():
                formula = rec.get("formula", "")
                bound = rec.get("calc_ids", [])
                id_list = ", ".join(str(cid) for cid in bound) if isinstance(bound, list) else ""
                periods = []
                for cid in bound if isinstance(bound, list) else []:
                    calc = calc_records.get(str(cid))
                    if isinstance(calc, dict):
                        fl = calc.get("fiscal_label")
                        if isinstance(fl, str):
                            periods.append(fl)
                period_suffix = f"  ({', '.join(periods)})" if periods else ""
                head = f"[{id_list}] {metric_name} = {formula}{period_suffix}"
                lines.extend(_with_width(head, indent="       "))
                if audit:
                    for cid in bound if isinstance(bound, list) else []:
                        calc = calc_records.get(str(cid))
                        if not isinstance(calc, dict):
                            continue
                        fl = calc.get("fiscal_label", "")
                        components = calc.get("components", [])
                        if isinstance(components, list) and components:
                            expr_parts: list[str] = []
                            for comp in components:
                                if not isinstance(comp, dict):
                                    continue
                                role = comp.get("role")
                                c_cid = comp.get("citation_id")
                                expr_parts.append(f"{role}[{c_cid}]")
                            expr = " - ".join(expr_parts) if _kind == "derived" else " ".join(expr_parts)
                            lines.extend(
                                _with_width(
                                    f"  [{cid}] {fl}: {expr}", indent="         "
                                )
                            )
```

- [ ] **C3.5: Apply the same pattern in `format_financial_perf_table`**

Find the `Calculations:` block in `format_financial_perf_table` (search `"Calculations:"` in `comps.py`) and replace it with the same formula-record-driven rendering. Also thread `formula_records` through any `_register_calculation` calls in that function.

- [ ] **C3.6: Run tests**

Run: `.venv/bin/python -m pytest tests/test_query_multi_period.py tests/test_comps.py tests/test_financial_perf_table.py tests/test_query_derivations.py -v`
Expected: PASS.

- [ ] **C3.7: Commit**

```bash
git add edgarpack/query/comps.py tests/test_query_multi_period.py
git commit -m "query: dedupe derived-metric formulas across multi-period renders"
```

---

### Task C4: End-to-end integration check

Spot-check every acceptance criterion from the spec's verification section.

- [ ] **C4.1: Multi-period render shows one FCF formula**

Assumes META 10-K packs exist locally. If not, skip and leave a note for the reviewer — unit tests already covered the behavior.

Run:
```
.venv/bin/edgarpack query meta revenue,net_income,operating_income,free_cash_flow \
    --period lfy,lfy-1,lfy-2,lfy-3 2>&1 | grep -c "free_cash_flow ="
```
Expected: `1`.

- [ ] **C4.2: `doctor` smoke test**

Run: `.venv/bin/edgarpack doctor AAPL`
Expected: per-pack rows with `Manifest: ok` and coverage counts.

Run: `.venv/bin/edgarpack doctor AAPL --format json | head -5`
Expected: JSON object with a top-level `packs` array.

- [ ] **C4.3: `build --last 3` smoke test**

Run: `.venv/bin/edgarpack build AAPL --form 10-K --last 3`
Expected: three packs built (or "3 skipped" if already registered).

- [ ] **C4.4: Final lint + full test suite**

Run: `ruff check . && ruff format --check .`
Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: both green.

- [ ] **C4.5: Commit any final formatting fixes**

```bash
git add -A
git commit -m "chore: ruff/format cleanup for build-which-citations feature"
```

---

## Self-review checklist (run after writing)

- [ ] Every spec section has at least one task implementing it (Items 1, 2, 3 in spec).
- [ ] No "TBD", "TODO", "fill in details" strings in this file.
- [ ] Every step that changes code shows the full code block, not a reference like "similar to task N".
- [ ] Type names used in later tasks match definitions in earlier tasks: `PackResult`, `PackDiagnosis`, `DiscoveryDiagnostics`, `FormulaRecord`-shaped dicts.
- [ ] Function signatures stated in plan match the ones the implementations will expose: `build_pack_range(cik, form_type, *, last, after, before, out_dir, with_chunks, with_xbrl, force, concurrency=3)`; `diagnose_pack(pack_dir, registry)`; `osc8(url, label)`; `supports_osc8(stream=None)`; `compact_url(url)`; `_register_calculation(..., formula_records=None)`.
- [ ] Test commands use `.venv/bin/python -m pytest` not system python (per MEMORY.md).
- [ ] Commit messages follow repo convention (type: short summary, no em-dashes, no AI-slop filler).
