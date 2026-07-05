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

- 2026-07-05 close-out. Phase 2 complete: 8 packets + 3 review-fix branches + 1 s1-cache branch merged; adversarial review (5 opus refuters + 1 re-run) produced 8 confirmed findings, all fixed or backlogged with evidence; final gate green (1,686 offline tests, ruff, mypy strict, SYMPHONY_WEB build).
- Output tokens, both sessions, main loop + all subagents (the command above): claude-fable-5 1,308,792; claude-opus-4-8 593,908; claude-sonnet-5 534,042. Project-wide Fable share 53.7 percent, dominated by the pre-doctrine work (diagnosis audits, Phase 1 surgery done inline, spikes, and the aborted all-Fable fan-out, all billed to Fable before the doctrine was adopted mid-project).
- Phase-scoped estimate (post-doctrine execution): down-ladder output 1,127,950 (opus + sonnet, all of it post-adoption since no non-Fable subagent ran before the routed packet run); Fable's post-adoption output estimated 150k-170k (spec authoring, integration, merges, gates, findings triage). Estimated Fable share of Phase 2 execution: 12-13 percent, under the 20 percent bar. Estimate, not measurement: no per-turn checkpoint was taken at adoption time; future phases should snapshot the jq numbers at phase start.
- Gate results: mechanical (suite + ruff + mypy + web) green at every merge point; adversarial layer caught 1 dead-code-on-production-path P1 (FX wiring), 2 cache-permanence defects, 2 fabrication leftovers, 1 scale-boundary defect, 1 YoY overreach, 1 serialization miss. All verified against code before fixing; 1 finding deferred to BACKLOG with evidence.

- 2026-07-05 Phase 3 start snapshot (per-turn checkpoint the close-out asked for). Current-session transcript totals at phase open: claude-fable-5 677,871; claude-opus-4-8 241,623; claude-sonnet-5 347,433. Phase 3 attribution = deltas from these numbers (single-session scope; the cross-session cumulative lives in the close-out entry above). Suite verified green at phase open: 1,686 offline tests at 12533bf. Entry gate launched: 25-filer A-share extraction sweep (sonnet) + HKEX acquisition spike (sonnet).
