# Packet: s1-structure

Goal: the registration extraction layer becomes maintainable without behavior change: the ~1,900-line `s1_financials.py` splits into a package, the two near-duplicate snapshot pickers become one, and LLM row gating becomes a declarative pydantic model. This is a behavior-PRESERVING structural packet; its acceptance test is byte-equality of snapshots on fixtures.

Files owned: `edgarpack/query/s1_financials.py` (becomes a compat shim), new package `edgarpack/query/registration/`, `pyproject.toml` (the one extras line below), tests (existing `test_s1_financials_*` stay green with at most import-path changes, called out in the report).

## Pre-made design decisions

- Package layout: `edgarpack/query/registration/` with `table_parse.py` (the deterministic summary-table parser), `llm.py` (prompt build, Anthropic call, salvage, retry, env overrides), `snapshot.py` (snapshot dataclasses, cache read/write, hashing, schema version), `integrate.py` (`augment_with_s1_snapshot`, the unified picker, CitedValue construction). Target: no module over ~700 lines.
- Compat shim: `s1_financials.py` re-exports every name currently imported elsewhere (grep callers and tests first; the mid-file import block near the old line 1002 disappears). Public call sites (`financials.py`, `cli.py`, distill) keep their imports working unchanged this packet; migrating them is a follow-up note, not your work.
- Picker unification: `pick_snapshot_fact` and `_pick_snapshot_candidate` (near-duplicates with subtle ordering differences) merge into one selector in `integrate.py`. FIRST pin parity: a test that runs both current implementations across a fixture matrix (periods lfy / lfy-N / mrp / pro-forma, single- and multi-pack, tie cases) and asserts identical choices; if they genuinely diverge on a case, STOP and report that case as blocked (the divergence is a behavior decision, not yours). Then delete the loser and point both call sites at the survivor.
- Pydantic row validation: pydantic>=2 is already a core dependency (harvest uses it). Replace the hand-rolled `_REQUIRED_KEYS` + coercion in the LLM row gate with a `LlmFactRow` pydantic model whose validators encode EXACTLY the current acceptance semantics (required keys, int coercion including the bool-as-int rejection, period-context and metric-context gates, the Phase 2 magnitude gates and ISO currency check). Prove equivalence with a table-driven test: a corpus of ~20 row dicts (valid, each missing-key case, wrong-typed, bool-as-int, out-of-gate values) asserting accept/reject identical to the old gate (keep the old function in the test module as the oracle, then delete it from production).
- Extras rename: add `llm = ["anthropic>=0.40"]` to pyproject; keep `vlm` as a deprecated alias with the same list; error/hint strings that mention the extra switch to `[llm]`. Run `uv lock` after.
- Byte-equality gate: before refactoring, capture the serialized snapshot JSON produced from the existing extraction fixtures; after, assert identical bytes (excluding the `extracted_at` timestamp field). Add this as a committed test so future refactors inherit the guard.

## Done definition

Suite green with at most import-path edits to tests (enumerated in the report); parity test green (or the divergent case reported blocked); pydantic gate equivalence test green; byte-equality snapshot test green; no module in the new package over ~700 lines; `uv lock` committed.
