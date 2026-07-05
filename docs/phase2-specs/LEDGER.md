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

<!-- Update at each phase boundary: model/output-token table from the command above, gate results, and at close: Fable share, all-Fable counterfactual estimate. -->
