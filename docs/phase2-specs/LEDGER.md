# Phase 2 token ledger

Per the Fable orchestration doctrine (~/.claude/FABLE-ORCHESTRATION.md): Fable owns specs, decomposition, gates, and integration; execution goes down-ladder. Success bar: Fable at or below 20 percent of output tokens for the phase, all gates green.

## Measurement command

Output tokens by model over this session's transcripts (main loop + subagents):

```bash
SESS=~/.claude/projects/-Users-samaydhawan-Projects-active-edgarpack
jq -rs '[ .[] | select(.type=="assistant" and .message.usage.output_tokens != null)
  | {m: (.message.model // "unknown"), t: .message.usage.output_tokens} ]
  | group_by(.m) | map({model: .[0].m, out: (map(.t) | add)}) | .[]
  | "\(.model)\t\(.out)"' \
  $SESS/8e5eb144-2eff-4376-aa9a-90b86b3e60b8.jsonl \
  $SESS/8e5eb144-2eff-4376-aa9a-90b86b3e60b8/subagents/**/*.jsonl 2>/dev/null
```

## Entries

- 2026-07-06 kickoff. Debit recorded: the first Phase 2 fan-out (run wf_8e3df4b5-35d) was launched with untyped agents that inherited Fable, exactly the leak the doctrine names. Stopped before any branch landed a commit; its partial spend counts toward Fable's share in the final report. Relaunch routes: sonnet x6 (sse-facts, cninfo-acquire, fx-average, sectionize-cn, translate-hardening, registration-periphery), opus x2 (china-provenance, s1-core), Fable for integration + taste gate, opus effort-high for adversarial review.

- 2026-07-05 build phase. Packet run wf_ed3f9cd0-2e6 completed 8/8 across a session restart (297,679 subagent output tokens). Six sonnet packets green, all fixes done. The two opus packets were interrupted by the restart; re-run duplicates detected the live continuation agents (run wf_d5bf5156-31f), aborted with zero writes, and reported red honestly. Continuation in flight on phase2/china-provenance and phase2/s1-core.

## Integration review checklist (verify before calling Phase 2 done)

1. china-provenance: the interrupted WIP added a `_fiscal_year_end` fallback fabricating `<fy>-12-31` when the manifest states no fiscal year end, contradicting the spec's "absent rather than fabricated" rule; a WIP test enshrined it. Verify the final branch returns absent dates and the test asserts absence.
2. fx-average: the packet fixed `fx/convert.py` but reported `edgarpack/query/currency.py` as the possible production `--currency usd` path, outside its ownership. Verify the production path actually flows through the corrected `convention="average"` logic.
3. sse-facts: the agent read "key-table-only" as whole-第二节 scope (both sub-tables) with 主要会计数据 as the priority tiebreak, to keep R&D intensity extracting. Reasonable; verify the ESG-row exclusion test and R&D intensity both hold.

<!-- Update at each phase boundary: model/output-token table from the command above, gate results, and at close: Fable share, all-Fable counterfactual estimate. -->
