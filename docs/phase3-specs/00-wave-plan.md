# Phase 3 wave plan

Doctrine: ~/.claude/FABLE-ORCHESTRATION.md. Fable authored these specs and pre-made every design decision in them; builders execute, escalate on anything unanswered, and never inherit the session model.

## Entry gate: RESULT (2026-07-05 sweep)

Trust cleared, coverage not: 0 wrong values across 25 filers, all 3 regression anchors pass, but only 4/25 filers yield cited values. Per the gate rule, the traced coverage gaps became the pre-wave `sweep-fixes` packet. Wave A launches only after the RE-SWEEP over the cached 25-filer corpus reaches >= 20/25 filers with cited values and 0 wrongs. Wave B and the HK packets are independent of A-share extraction health and launch immediately with sweep-fixes.

## Packets and routing

| Packet | Model | Wave | Depends on | Spec |
|---|---|---|---|---|
| sweep-fixes | sonnet | pre-A | none (launched now) | sweep-fixes.md |
| one-command-china | sonnet | A | re-sweep gate | one-command-china.md |
| dual-listing-adr | sonnet | A | re-sweep gate | dual-listing-adr.md |
| starter-universe | sonnet | A | dual-listing-adr branch | starter-universe.md |
| harvest-china-sse | sonnet | A | re-sweep gate | harvest-china-sse.md |
| build-hk-acquire | sonnet | now | none (launched now) | build-hk.md (finalized from the 2026-07-05 spike) |
| hk-construct-prototype | sonnet | now | none (launched now) | hk-construct-prototype.md (report-only, no repo code) |
| build-hk-construct | tbd | A'' | hk-construct-prototype report | spec to be authored by Fable from the prototype evidence |
| s1-structure | opus | now | none (launched now) | s1-structure.md |
| english-surface | sonnet | now | none (launched now) | english-surface.md |

Wave B has no dependency on the sweep and may launch alongside Wave A. Deferred to a later wave, recorded here so they are not lost: registration real-filing golden fixtures + metric expansion (needs live SEC + ANTHROPIC_API_KEY lanes), find_tables migration for SSE (decision waits on sweep evidence), comps/compare venue support (interface noted in dual-listing-adr), HK harvest lane (after build-hk).

## cli.py shared-file map (region ownership, merge order)

cli.py is touched by three packets in disjoint regions: dual-listing-adr (identify output + `--venue` flag on the query parser + venue pre-pass at the top of `_cmd_query`), one-command-china (the build-if-needed block inside `_cmd_query`'s China path), english-surface (none). Integration merges dual-listing-adr before one-command-china.

## Conventions

docs/phase2-specs/00-conventions.md applies verbatim with three substitutions: base branch is `streamline/phase3-build`, branch prefix is `phase3/`, specs live in docs/phase3-specs/. The starter-universe packet branches from `phase3/dual-listing-adr` instead of the base (its spec says so).
