# Packet: one-command-china

Goal: `edgarpack query 002594 revenue --period lfy` works cold. When an A-share filer has no local pack, the query command acquires and builds the latest annual report itself (the `f1`/`s1` build-if-needed pattern), instead of erroring with instructions to run `build-sse` and edit files. This is the zero-knowledge-investor acceptance scenario's first half.

Files owned: `edgarpack/cli.py` (ONLY the China build-if-needed block you add inside `_cmd_query`; the venue pre-pass region at the top of `_cmd_query` and the query parser flags belong to dual-listing-adr, except `--no-build` which is yours), `edgarpack/query/financials.py` (only a pack-existence helper if one must be exposed; prefer reusing the existing China pack discovery), tests.

## Pre-made design decisions

- Auto-build is the DEFAULT. A `--no-build` flag restores today's behavior (clean missing-pack error). No prompt, no confirmation: print one stderr line before building: `No local pack for 002594; fetching the latest annual report from CNINFO (typically 2-4 minutes)...`
- Reference implementation pattern: `_cmd_registration_shortcut` (`cli.py` ~1598) which builds-if-needed then delegates to the ordinary query path. Follow its structure.
- Scope is A-share/SSE codes only (universe-configured or bare 6-digit). HKEX filers keep today's behavior until build-hk lands. `comps`/`compare` are out of scope; note in the report if the helper you build would serve them.
- Pack destination: the `--packs` root (default `DEFAULT_PACKS_DIR`), identical layout to `build-sse`.
- Build path: the SAME internals `build-sse --latest-annual` uses (CNINFO latest-annual selection from Phase 2, with its staleness floor and 英文版 exclusion). Do not reimplement selection.
- Existence pre-check, not error-catch: detect the missing pack via the existing China pack discovery used by the query layer, then build, then run the normal query once. A second miss after a successful build is a real error, not a retry loop.
- Failure honesty: a build failure (CNINFO LookupError, download failure, staleness rejection) surfaces the underlying message and exits non-zero; no partial pack directory is left behind (build to a temp dir or rely on the builder's existing atomicity; verify which it is and say so in the report).
- Lazy-startup invariant: all new imports inside `_cmd_query` / the helper, never module top level.
- Loop-trap message (sweep friction finding): when a pack DIRECTORY exists but has no `facts.json`, today's error says `No SSE pack found... Run build-sse ... first` (discovery globs `*/facts.json`, `financials.py` ~1976; message ~2166-2171), sending the user in a circle since rebuild no-ops. Distinguish the two states: pack-with-no-facts gets `Pack for 002594 was built but no facts were extracted; see the build warnings (rebuild with --force after fixing).` and auto-build does NOT trigger for it (building again cannot help).

## Tests

- Cold path: mocked CNINFO selection + mocked PDF download; assert build invoked exactly once, then the query returns values from the freshly built pack.
- Warm path: pack already present; assert no build attempt (mock would fail the test if called).
- `--no-build`: exact current error message and exit code preserved.
- Build failure: staleness LookupError from the selector propagates with its message, non-zero exit, packs root unchanged.
- HKEX filer: behavior unchanged (no auto-build attempt).

## Done definition

All five tests green; the stderr acquisition notice appears in the cold path only; full offline suite green.
