# Phase 1 diff and adjudication: Claude vs Codex

Status: written adjudication only. No product code touched. Read-only.

Inputs adjudicated:
- `docs/rebuild/030_PHASE1_CLAUDE_REPORT.md` (409 lines, 12 sections)
- `docs/rebuild/030_PHASE1_CODEX_REPORT.md` (662 lines, 12 sections; the file is named `030_...CODEX`, not `031`)
- `docs/rebuild/010_PHASE0_BEHAVIOR_CORPUS.md` (the shared evidence base both reports cross-checked against)
- `tests/parity/corpus.yaml` (49 cases; levels: exact 7, normalized 5, semantic 24, manual 4, known_bad 6, deprecated 3; families: sec 28, local 9, hkex 7, mixed 2, sse 2, cninfo 1)

Method and conflict-of-interest note: I (the adjudicator) am the same model that authored the Claude report. To keep this honest I do not side with the Claude report by default. Where Claude is sharper I say why and confirm the claim traces to a `file:line`; where Codex caught something Claude missed I credit it plainly; where they contradict on fact I mark it for verification rather than picking the home team. Citations below are `Claude §N` and `Codex §N`.

The single strongest signal up front: the two independent passes converged on the same sequencing without coordinating. Build the offline parity + determinism harness first, settle a small set of Samay decisions that finalize the corpus, spike EdgarTools, then re-architect behind the harness. Neither recommends writing vNext product code now. That convergence is the most load-bearing output of this whole comparison and it leads section 5.

---

## 1. High-confidence agreements

These are findings both passes reached independently. Independent convergence raises confidence above Phase 0's single pass, so each row below should be treated as a near-settled input to Phase 2 (the exceptions are flagged).

| # | Agreement | Why it matters | Evidence (Claude / Codex) | Phase 2 implication |
|---|---|---|---|---|
| A1 | **No blank-slate clean room. Any rebuild must be narrower and behavior-pinned first.** | The dominant failure mode of a from-scratch rewrite is silently dropping scar tissue. Both rate this the central risk. | Claude §1 "not as a from-scratch clean room... harness-first, in-place re-architecture" / Codex §1 "proceed only if it is narrower... begins from behavior-pinning. A blank-slate rewrite is too risky." | Build the harness before any product code. If a clean room is mandated, gate its start on the harness. |
| A2 | **The provenance/citation contract is the product and is preserved exactly.** | A single uncited-wrong number breaks the reason to exist. This is the non-negotiable. | Claude §3 "the moat"; §10 non-negotiables / Codex §3 product promises; §10 "Citation/evidence layer KEEP OWNED" | `CitedValue`/`DerivedValue`, None-not-guess, the LTM three-citation rule become semantic invariants in the harness, not formatting tests. |
| A3 | **EdgarPack should exist, but narrower: an evidence/citation layer wrapping mature SEC plumbing.** | Settles the "why not just use EdgarTools" question directionally. Both at medium-high confidence. | Claude §8 "yes, but narrower" / Codex §8 "Yes, but narrower... wrapper/evidence layer over mature SEC plumbing where parity holds" | Scope vNext as differentiated IP (provenance model, period engine, China Lens, diff suppression, distill) + thin SEC acquisition. The *depth* of delegation is disputed (see D1). |
| A4 | **Biggest regression risk is losing edge-case behavior that lives in control flow, not in clean contracts.** | Tells you where to spend harness effort: the scar tissue, not the happy path. | Claude §1, §9 (19-item register) / Codex §1, §9 (15-item register) | The high-risk-edge corpus group is the priority. Both registers overlap ~80%; union them. |
| A5 | **Determinism is under-tested offline; the gated NVDA-only live test cannot catch a regression.** | Determinism keys the pack cache and the diff engine; an undetected break corrupts both. | Claude §7 (offline test exists but `with_chunks=False`, same-process) / Codex §7 "one offline fixture pack byte contract plus one live smoke" P0 | Add an offline, with-chunks, cross-process determinism parity case as P0. |
| A6 | **FastAPI/Next web, `insights/`, VLM asset descriptions, demo seed fixtures, `site --base-url`, `--cik` shims are parked or accidental and must not shape vNext unless revived.** | Prevents parked scope from re-entering the rewrite by gravity. | Claude §6.4, §3 / Codex §6.2, §6.4, §3 | Physically isolate (extra/namespace) before the rewrite so they cannot bleed in. Disposition of `insights/` is disputed (see D4). |
| A7 | **`cli.py` is overburdened; the ~400-line inline `translate-sse` orchestrator belongs in a service.** | It is real business logic, unreachable from the API path, untested at unit level. | Claude §1, §6.2 (`cli.py:1888-2290`) / Codex §4.1 "too large and contains orchestration that belongs in services" | Extract to `china/translate/pipeline.py` (or equivalent) as an early, low-risk structural win. |
| A8 | **`financials.py` is overburdened; it crosses SEC companyfacts + S-1 + China discovery + metric selection + serialization.** | The module most likely to carry a cross-source bug; the China fixture read and the in-place mutation both live here. | Claude §4 table, §3 / Codex §4.1 "doing too many source-specific jobs", §4 accidental boundaries | Split into a source-agnostic facts interface with per-family adapters behind it. |
| A9 | **Production code reading `tests/fixtures/china_packs/` is wrong and must move to a pack-root config.** | Shipping code resolving against the tests directory + a CWD==repo-root assumption. | Claude §6.2 (`financials.py:1977-1987`, "accidental") / Codex §6.3 (same, "uncertain") | Pin the offline-HK query behavior, then introduce a pack-root config. Classification differs (D3) but both agree on the fix. |
| A10 | **The known-bad provenance bugs need a Samay pin-vs-fix ruling before the parity corpus can be finalized.** | The corpus cannot pin a number until you decide whether it pins the current (wrong) or intended value. | Claude §11 Q2 / Codex §11 Q3,Q10; both name HKEX LLM 1000x, China `filed=Dec-31`, FX one-month-average | Blocks finalizing `corpus.yaml`'s 6 `known_bad` rows. This is the highest-value Samay decision. |
| A11 | **Backward-compat scope (pack bytes, CLI flags, json-full, learned registry) is a Samay decision that gates the whole shim strategy.** | The architecture answer changes materially depending on whether old artifacts must stay readable. | Claude §11 Q4 / Codex §1, §11 Q2,Q3,Q4,Q10 | Freeze the compatibility policy before designing any boundary. Blocking. |
| A12 | **Translation magnitude safety (wan/yi never delegated to the LLM; fail-closed validators) is essential and non-negotiable.** | A wan/yi error is a 10,000x mistake in a financial figure. | Claude §6.1 (`china/translate/numbers.py:109-154`) / Codex §6.1 "fail-closed validators and resumable cache" | Preserve exactly; never let the rewrite "simplify" numbers into the LLM call. |
| A13 | **The HK column-count guard (silence over misattribution) is essential.** | Worst-case provenance failure is a value attributed to the wrong fiscal year; silence is the correct trade. | Claude §6.1, §9 #8 (`hk/extract.py:278-279`) / Codex §6.1, §9 | Preserve exactly; pin the 9 regressions as a high-risk-edge parity group. |
| A14 | **The corpus.yaml-as-rebuild-oracle strategy is correct; the existing tests-become-parity approach is right.** | Confirms the Phase 0 D2 artifact is the right seed. | Claude §7 "tests that should become parity tests" / Codex §7 same heading | Make `corpus.yaml` executable, starting with the P0 rows. It is not executable yet. |

Two agreements deserve a sentence of expansion because they carry the most weight downstream.

On A1/A3 together: both passes reject the two extreme options. They reject "rewrite from scratch" (too much undocumented scar tissue) and they reject "delete EdgarPack, just use EdgarTools" (the evidence layer is genuinely differentiated). The agreed shape is a narrower owned core plus a delegated commodity SEC tier. The disagreement is only about where the line sits, which is D1.

On A10: this is the agreement with the most immediate operational consequence. The parity corpus already carries 6 `known_bad` rows. Until Samay rules pin-vs-fix on the three provenance bugs, those rows are ambiguous, and an executable harness built on top of them would either enshrine the bugs as parity or fail against a not-yet-decided target. The corpus cannot be finalized around them.

---

## 2. Disagreements requiring judgment

Honest framing: most apparent gaps between the two reports are differences of specificity, not contradiction. Claude tends to name `file:line` break paths; Codex tends to stay at the category level and inventory more breadth. I isolate below the disagreements that actually require a decision or a verification, and I drop the ones that are just "one said it louder."

### D1. How deep does EdgarTools delegation go, especially the SEC cache/client?

| | Position |
|---|---|
| Claude | Cache + client **KEEP OWNED** (high confidence): EdgarTools' cache lifecycle and dependency tree both violate the determinism guarantee and the deliberate pydantic+tiktoken-only budget. DELEGATE only the ticker map + archive download. INVESTIGATE submissions/XBRL. The "thin wrap" is optimistic because four invariants each need owned code or a verified library behavior. (Claude §8) |
| Codex | SEC cache/rate-limit = **INVESTIGATE** (high confidence): spike to compare failure semantics, 404 handling, atomic cache, deterministic offline behavior before deciding. More willing to let the cache be delegated if the spike proves parity. (Codex §8, "SEC cache/rate limit behavior INVESTIGATE") |

- Possible explanation: Claude treats the pydantic+tiktoken-only dependency budget as a near-hard constraint and the determinism guarantee as a reason to own the cache outright. Codex treats the budget as itself a Samay question (its Q5) and is willing to let a spike, not a prior, decide the cache.
- Evidence needed: (1) EdgarTools' actual transitive dependency tree (does it pull pandas/lxml/httpx/rich, breaching the budget?). (2) Whether its cache is deterministic and non-evicting, or whether it evicts/varies (EdgarPack explicitly does not want eviction). (3) Whether it exposes raw HTTP status (needed for the 404-vs-error split) or pre-digests to an empty result.
- Recommended Samay decision: settle the dependency-budget question first (it is upstream of everything). My adjudicated lean, medium confidence: **keep the cache and client owned, delegate the ticker map and archive download only.** The cache is ~2 small stdlib modules and is the determinism device; the downside of owning it is low, the downside of a library cache that evicts or varies is a determinism break that no offline test currently catches. I am flagging that this lean coincides with the Claude position, so weight it accordingly, but the reasoning is the dependency-budget asymmetry, not authorship.
- Blocks Phase 2? It blocks the *SEC-acquisition rewrite scope*, not the harness. Gate it behind the spike. The harness can be built before this is settled.

### D2. What is the single biggest regression risk: byte-determinism specifically (Claude) or edge-case-in-control-flow broadly (Codex)?

| | Position |
|---|---|
| Claude | **Byte-determinism**, with four named break paths: tiktoken `len//4` fallback (`tokenize.py:48-55`), SSE+translate manifest mutated after its own hash (`build.py:564-571`), latin-1 whole-blob decode (`build.py:83-88`), silent image-drop (`assets.py:78-82`). (Claude §1, §9) |
| Codex | **Broad edge-case behavior in control flow**: LTM math, section detection, S-1 extraction, malformed tables, HK attribution, translation, diff matching. Determinism is one P0 among many. (Codex §1) |

- Possible explanation: Claude ran a dedicated determinism verification pass and surfaced specific break paths; Codex stayed at the category level. These are not contradictory; Claude's four paths are a *subset* of "edge cases a naive rewrite loses." The disagreement is which to put at #1.
- Evidence needed: none. This is a framing difference, and the synthesis is strictly better than either: Codex's broad list is the superset; Claude's four paths are the named, actionable determinism members of it.
- Recommended resolution: adopt both. Treat Codex's category list as the high-risk-edge corpus scope, and promote Claude's four determinism break paths to named P0 parity cases inside it. The risk map in section 4 ranks them.
- Blocks Phase 2? No. Both point at the same harness work.

### D3. Is the production fixture read "accidental" (clearly removable) or "uncertain" (needs a case)?

| | Position |
|---|---|
| Claude | **Accidental** (§6.2): the fix is a pack-root config; pin the offline-HK query then remove. |
| Codex | **Uncertain** (§6.3): "whether production intentionally supports fixture fallback" is unproven; needs a production-like China pack query case. |

- Possible explanation: Claude judged intent from the code shape (a hardcoded `fy=2024` + `tests/fixtures` path is not a designed feature); Codex held to the Phase 1 rule of not calling something accidental without proof of intent.
- Recommended decision: low-stakes. Honor Codex's caution cheaply: pin the offline-HK behavior as a parity case (both want this), then treat the path as accidental and replace it with a pack-root config. The caution costs one parity case; the fix is the same either way.
- Blocks Phase 2? No.

### D4. `insights/`: delete (Claude) or park (Codex)?

| | Position |
|---|---|
| Claude | Lean **delete or move behind the parked web surface**; calls it orphaned dead-weight (zero callers outside `__init__`/tests; `emerging.py` untested). (§4, §6.2) |
| Codex | **Park** in a separate experimental namespace; keep it isolated, revive if corpus-level analytics is requested. (§6.2, §6.4) |

- Possible explanation: same evidence (no active caller), different risk appetite. Claude optimizes for a smaller surface; Codex optimizes against discarding latent value.
- Recommended decision: tie it to the FastAPI/web ruling (Samay decision in §5). If web is retired, `insights/` is dead and should be deleted after pinning the accession-level emerging-topic counting invariant. If web is revived, `insights/` is dormant and stays parked behind it. Do not decide `insights/` independently of web.
- Blocks Phase 2? No, but it is downstream of the web decision, which is itself a Samay input.

### D5. The diff annual-timeline vs pair-diff divergence: factual contradiction to verify.

| | Position |
|---|---|
| Claude | The timeline diverges from pair-diff **on counts only**; the shared `_compute_section_intensity()` still applies boilerplate filtering. (Claude §9 correction note) |
| Codex | The **annual timeline does not share all pair-diff boilerplate filtering** (`diff/timeline.py` annual path differs). (Codex §9 row, §7 "annual timeline not sharing all pair-diff boilerplate filtering") |

- **RESOLVED 2026-06-16 by code read.** Both are right about different layers. The intensity computation IS shared and identical: `build_timeline` calls `_compute_section_intensity` (`timeline.py:107`), which internally skips `is_boilerplate` paragraphs and applies financial-section damping (`section_diff.py:286,291-294`). So Claude's "shared intensity still applies boilerplate filtering" is correct and precise. What diverges is the reported paragraph counts: the annual timeline counts the raw `diff_paragraphs` output including boilerplate (`timeline.py:86-89,101-104`), while the pair-diff path runs a post-processing pass that makes boilerplate paragraphs invisible and recounts (`section_diff.py:487-501`), which `build_timeline` does not run. So Codex's "does not share all pair-diff boilerplate filtering" is also true, but specifically at the count level, not the intensity level. Noise-section-type suppression (`_SUPPRESSED_SECTION_TYPES`) is absent from the timeline by design (the code comment at `section_diff.py:28-29`): the timeline tracks one explicit section the user asked for, so suppressing it would defeat the purpose.
- Consequence for the harness: an annual-timeline parity case can reuse the intensity expectations from pair-diff fixtures (intensity is shared), but must assert paragraph counts separately because the timeline's counts include boilerplate. The two cannot share count fixtures.
- Blocks Phase 2? No. Resolved; folded into the §5 parity-gap list.

### D6. self-heal / learned registry: measure-then-keep (Claude) or replace-with-explicit-review (Codex)?

| | Position |
|---|---|
| Claude | **Uncertain, empirical**: read-path self-heal "might be load-bearing; needs a corpus case" measuring marginal coverage of filers that only resolve via self-heal, with and without `--strict`. (§6.3) |
| Codex | **Open product question**: "should vNext prefer strict deterministic extraction with explicit user review?" Leans toward possibly replacing the read-path-write behavior. (§11 Q9) |

- Possible explanation: Claude frames it as "how much coverage does this actually buy" (an experiment); Codex frames it as "should this be in the product at all" (a direction). Compatible lenses, different order of operations.
- Recommended decision: run Claude's measurement first (it is cheap and factual), then put Codex's product question to Samay armed with the marginal-coverage number. Deciding the product direction without the coverage data is guessing.
- Blocks Phase 2? No. But the read-path DB write is a determinism/parallelism hazard (Claude §9 #14), so the behavior must be pinned regardless of the eventual direction.

Disagreements explicitly **not** escalated (specificity, not contradiction): translate-orchestrator placement (both agree extract it), `financials.py` overload (both agree split it), the parked inventory (both agree), the corpus-as-oracle (both agree). Listing them as "disagreements" would be the mush the task warns against.

---

## 3. Blind spots

Things one or both passes missed. Credited by who caught what, because that itself signals where each pass is weak.

### Caught by Claude, missed by Codex
- **The four named determinism break paths** (tiktoken fallback, SSE+translate manifest-after-hash, latin-1 whole-blob, silent asset-drop). Codex named determinism as a category but never the mechanisms. These are the most actionable single findings in either report.
- **The in-place mutation of the cached companyfacts dict** to inject a synthetic `EntityNumberOfEmployees` under `us-gaap` (`financials.py:1036-1054`). A read op that side-effects fetched data; a parallelism hazard. Codex does not mention it. Phase 0 §3.3 had it.
- **The two divergent universe-load paths** (`cli.py:107-113` silent-None vs `:2417-2424` exit-2). Codex does not surface the inconsistency.
- **The FX averaging bug, specifically** (one FYE-month average, not a fiscal-year average; `fx/convert.py:71-73`, `currency.py:130-133`). Codex mentions "FX rates and currency warnings matter" and the China filed-date fabrication, but never isolates the averaging defect as a distinct provenance risk. It is one of the three known-bad rows.
- **The `formula.py` precedence defect**: `eval_formula` has no operator precedence and the inline "respect precedence" comment is already wrong. Codex treated "no precedence" as a neutral fact (via Phase 0), not a defect to fix.
- **The colspan upper-clamp gap** (lower clamp exists for `colspan="0"`, no upper bound for `colspan="99999"`, unbounded allocation). Codex covered malformed spans but not the missing upper clamp.
- **The two-clock cooldown** (60s-clamped Retry-After vs 600s default; `client.py:141,151,232`), where the user-facing cooldown can be wrong in both directions.
- **The AXP/issuer revenue gotcha** (generic `revenue` returns ASC-606 contract revenue, not the headline net-of-interest figure). This is in project memory as a known gotcha; Codex never mentions AXP.

### Caught by Codex, missed by Claude
- **The full parked-surface env-var contract**: `EDGARPACK_CHINA_STORAGE_BACKEND`, `_STORAGE_DIR`, `_OBJECT_STORE_DIR`, `_POSTGRES_DSN`, `_SEED_FIXTURES`, and the web `NEXT_PUBLIC_*` vars (Codex §2 env table). Claude's report does not enumerate the China storage backends or web env. Low stakes because parked, but it is a real inventory gap, and the Postgres/object-store backends mean the parked surface is bigger than Claude implied.
- **The SSE non-atomic PDF cache** (`sse/client.py`): weaker than the SEC cache, corrupt partial PDFs possible on interrupted download (Codex §9). Claude pinned the SEC cache as the determinism device but did not flag that the SSE PDF cache lacks the same atomicity guarantee.
- **The metric-directory generation as a contract decision** (preserve generation vs replace with a registry export; Codex §5). Claude treated it only as a byte-equality drift guard to preserve, not as a "should this be generated or exported" question.
- **Registration as a first-class adapter framing**: Codex §6.1 explicitly recommends making the S-1/F-1 path "a first-class adapter, not a fallback hidden in SEC query." Claude described the S-1 routing burden inside `financials.py` but did not name the adapter-promotion as cleanly.

### Missed by both (Phase 0 caught it; neither Phase 1 surfaced it)
- **Version reconciliation** (`__version__` 0.1.0 vs `PARSER_VERSION` 0.2.1; Phase 0 Q1). Neither Phase 1 report carries this into its questions. A rewrite needs a canonical version source. Re-surfaced in §5.
- **A-share bare-6-digit routing truth** (does `688696` route to SSE or fall to SEC CIK `0000688696` → 404? Phase 0 Q8). Claude listed it as an open uncertainty; Codex dropped it entirely. Only running code settles it.
- **The cache TTL test collection question** (`test_cache.py`: are the TTL tests collected by pytest, or dead below `if __name__`?). **RESOLVED 2026-06-16: Phase 0 was right, the Claude Phase 1 report was wrong.** `pytest --collect-only` collects exactly 3 tests; the two TTL tests at `test_cache.py:64,78` are indented inside the `if __name__ == "__main__":` block and defined after `unittest.main()` runs, so they are never collected by pytest and never run by direct execution either. They are dead. Consequence: the two documented cache behaviors (`missing meta = expired`, `corrupt meta = expired/refetch`), both determinism-adjacent, have zero live coverage. This is a real parity gap, recorded in §5.
- **`xbrl.json` production path**: Phase 0 flagged it untested and secondary. Both Phase 1 reports treat it lightly (preserve / wrap) without noting it is essentially uncharacterized.

### Missed workflow (both)
- **The corpus-scale Observatory pipeline** (`harvest` → `index` → `search`, at the 631-pack / 38K-chunk scale described in project memory) is an *active* product surface, but both reports treat its analytical tail (`insights/`) as the headline and under-weight the bulk harvest+index+search loop as a coherent, first-class workflow. Phase 0 §3.9 had it; neither Phase 1 report treats it as first-class. If the corpus pipeline is a real product surface, it needs its own parity treatment (incremental index purge contract, emerging-topic accession counting), not just the parked `insights/` mention.

### Missed dependency opportunities (both, lightly)
- Neither investigates the **PDF extraction stack** (`pymupdf4llm`) as either a delegation or a risk for HK/SSE quality, beyond Codex's one line "if quality holds." Given China Lens is the moat, the PDF-table-extraction dependency deserves a spike of its own.

---

## 4. Rebuild risk map

Ranked by blast radius × likelihood, with the causal chain made explicit (several of these are mechanisms for the same ultimate failure: a wrong-but-confident cited number). Each row cites which report(s) carry it and the primary mitigation.

| Rank | Risk | Why this rank | Evidence | Primary mitigation | Blocks Phase 2? |
|---|---|---|---|---|---|
| 1 | **Losing edge-case handling (scar tissue)** | Highest likelihood × high impact, and the *mechanism* by which most other failures occur. The parse pipeline, `periods.py`, HK extraction, translation, and diff suppression each encode a real filing-world condition with thin or no offline coverage. A rewrite re-breaks them blind. | Claude §9 (19 items), Codex §9 (15 items), Phase 0 §9 | The high-risk-edge corpus group, union of both registers, built and green before any rewrite touches that subsystem. | The harness IS the mitigation; build it first. |
| 2 | **Losing citation trust (the provenance contract)** | Highest *impact* (existential), slightly lower likelihood because the contract is well-defended in the data model and the autouse LTM harness. But it is the consequence of rank 1: HK column misattribution = wrong-year citation; FX averaging = wrong USD value with a real-looking citation. | Claude §1,§3, Codex §3,§8 | Lift the LTM invariant from a runtime assert into a constructor; make 404-vs-error and no-imputation-pagination semantic invariants. | Partially: A10/A11 must be ruled first. |
| 3 | **Breaking byte-determinism / artifact consumers** | High likelihood (four named break paths, no offline test) × high impact (cache + diff key off it; agents cache by hash/offset). Distinct from rank 1 because it is about the pack artifact contract, not financial reasoning. | Claude §1,§9 #1-3,#18; Codex §7 P0 | Offline with-chunks cross-process determinism parity case; make tiktoken a hard precondition (drop `len//4`); migrate the SSE+translate manifest to a hashed `translation.json`. | Determinism-scope is a Samay decision (§5); the test is buildable now. |
| 4 | **Freezing bugs (pinning known-bad as parity)** | The parity-first strategy both endorse will, applied naively, enshrine HKEX 1000x / China Dec-31 / FX averaging as "correct." Medium likelihood, medium-high impact (a frozen provenance bug is quiet citation erosion). | Claude §11 Q2, Codex §11 Q3; corpus has 6 `known_bad` rows | The explicit `known_bad` snapshot level already exists; force the Samay pin-vs-fix ruling (A10) before the corpus is executable. | Yes: blocks finalizing the corpus. |
| 5 | **Over-delegating to dependencies** | The EdgarTools-wholesale trap. Medium likelihood, high impact if the 404-vs-error or no-imputation semantics are silently lost behind the library. Claude is more alarmed than Codex; the gap is D1. | Claude §8 ("not thin"), Codex §8 (INVESTIGATE) | The gated EdgarTools spike against the four invariants before any delegation commitment. | Gated behind the spike; not the harness. |
| 6 | **Under-delegating parser plumbing** | The opposite trap: rebuilding commodity ticker-map / archive-download by hand and re-accreting scar tissue. Lower impact (wasted effort + re-introduced bugs) but real, given the team owns a lot it need not. | Claude §8 (DELEGATE map+archive), Codex §8 (DELEGATE/WRAP listing+download) | Same spike; explicitly scope the ticker map and archive download as delegation candidates. | No. |
| 7 | **Breaking CLI muscle memory** | `--cik` shims, three comparison surfaces, exact flag/output compatibility. Medium likelihood, low-medium impact (annoying, not catastrophic), gated by the compatibility decision. | Claude §11 Q4,Q5; Codex §11 Q3 | Freeze the compat policy (A11); decide the three-comparison-surface consolidation and its parity oracle. | Gated by A11. |
| 8 | **Reviving parked surfaces by accident** | FastAPI/web/`insights/`/VLM bleeding into vNext scope. Lower likelihood if the inventory is honored, but real: `web/` still builds in CI behind `SYMPHONY_WEB=1` and `api/` sits beside active code. Impact is scope creep, not correctness. | Claude §6.4, Codex §6.4; A6 | Physically isolate parked surfaces (separate package/extra) before the rewrite so they cannot be imported by gravity. | No. |

The ranking's load-bearing claim: ranks 1, 2, and 3 are not three independent risks. Rank 1 (edge-case loss) is the most common *path* to rank 2 (citation-trust loss), and rank 3 (determinism break) is a parallel path to corrupting the artifacts that rank 2 depends on. The harness that mitigates rank 1 is the same harness that catches ranks 2 and 3. That is why both reports converge on "harness first" as the single highest-value move.

---

## 5. Phase 2 inputs

Clean, deduped lists merged from both reports. Where the two reports both carry an item, it is unattributed; where only one does, it is tagged.

### Non-negotiable behaviors (reproduce exactly or it is not EdgarPack)
- Provenance as a data-model property (`CitedValue`/`DerivedValue`); no bare-number path.
- `None` + typed diagnostic for every miss; never an uncited N/A.
- LTM three-component citation contract (`{mrp, lfy, mrp_prior}`) or `None` + `ltm_incomputable`.
- The 404-vs-`XBRLFetchError` split (real SEC 404 → `{}` diagnostic-free; other failure → raise).
- Byte-determinism of the pack core (`filing.full.md`, `sections/*.md`, `llms.txt`, `manifest.json` modulo `built_at`).
- Translation magnitude safety (wan/yi never delegated to the LLM; fail-closed validators; resumable cache).
- HK column-count guard (silence over wrong-year misattribution).
- Period vocabulary (`lfy`/`mrq`/`ltm`/`mrp`/`annual:N`/`quarterly:N` + offsets) and the staleness guards (>2 FY behind rejected; `ltm-1` allows 3).
- Strict mode = `hardcoded`-only, recursing into derived components.
- Diff mechanical-noise suppression with word-weighted intensity shared by `section_diff` + `timeline`.
- Pack integrity invariants (section hashes resolve; char offsets index into `filing.full.md`; `manifest.json` excluded from its own hashes).

### Intentional break candidates (change deliberately, with a `known_bad` or migration pin)
- The tiktoken `len//4` heuristic → make tiktoken a hard precondition (vendor `cl100k_base` or fail loud). [both, via determinism]
- The SSE+translate manifest mutated after its own hash → hashed `translation.json`. [Claude]
- The positional formula evaluator → precedence-correct, AST-restricted. [Claude]
- Production read of `tests/fixtures/china_packs/` → pack-root config. [both]
- In-place facts-dict mutation for synthetic headcount → thread the value, do not mutate cached SEC data. [Claude]
- Two universe-load paths → one loader (decide silent-None vs exit-2 as canonical). [Claude]
- Absolute-path leaks in distill bundles / manifests / registry rows / site output → normalize. [both]
- `site --base-url` → remove or implement. [both]
- The three known-bad provenance outputs (HKEX 1000x, China `filed=Dec-31`, FX one-month-average) → fix, **only if** Samay rules fix-not-pin (A10).

### Deletion candidates (pin the named contract, then delete)
- `insights/`: pin the accession-level emerging-topic counting invariant; delete only if web is retired (D4). [Claude lean / Codex park]
- Inert HKEX LLM path (`hk/llm_extract.py`): pin the `learned:llm` tag + cache-key + the latent USD/1000x contract. [both]
- `_STALENESS_YEARS` empty dict. [both]
- `--describe-images` VLM `.desc.txt` output: keep the image-fetch + src-rewrite half (load-bearing for registration markdown). [both]
- Dead 2026-06-09-review code (selectolax alias, `simplify_html`, `has_ixbrl`, comps compat wrappers, dead archive skip-patterns); grep for live callers first. [Phase 0; neither Phase 1 re-listed in full]
- Single-item registry companions (`mark_indexed`, `register_pack`) if no external caller. [Phase 0]
- `learned` source `'user'` (no producer). [Phase 0]

### Dependency spike candidates
- **EdgarTools** against three filers (clean 10-K, no-XBRL S-1, renamed ticker) testing the four invariants: 404-vs-error, no-imputation pagination, deterministic + non-evicting cache, pre-IPO content-only-match. Plus a dependency-tree inventory against the pydantic+tiktoken-only budget. This is the single most important spike; it gates D1, risk 5, risk 6, and Samay decision 1. [both]
- A maintained FX rate source vs bundled `data/fx_rates.csv`. [Claude]
- The PDF stack (`pymupdf4llm`) quality hold for HK/SSE extraction. [Codex, lightly; flagged as under-investigated by both in §3]

### Parity gaps (no/weak offline coverage; the harness must add before any rewrite)
- Offline pack byte-determinism **with chunks, cross-process, tiktoken-absent simulated**. P0. [both]
- 404-vs-`XBRLFetchError` split, offline mocked (404 empty / 500 raises / cache not poisoned). P0. [both]
- SSE+translate manifest determinism (translate-block normalization). P1. [Claude]
- China FX fiscal-year-average **independent** oracle (the golden pins the buggy value, so it cannot self-check). P1. [Claude]
- Sectionizer TOC/INDEX disarm regression set. P1. [both]
- Annual-timeline paragraph counts include boilerplate (resolved D5): assert timeline intensity against shared pair-diff fixtures, but assert timeline paragraph counts separately (they are not boilerplate-suppressed). P1.
- Cache TTL behavior (`missing meta = expired`, `corrupt meta = expired/refetch`): the two `test_cache.py:64,78` tests are dead (never collected, resolved 2026-06-16), so these behaviors have zero coverage. Add a real collected test. P1.
- Universe-load divergence parity (both paths). P2. [Claude]
- A-share bare-6-digit routing characterization (running code only). P1. [Phase 0]

### Architecture questions (boundaries to settle, not design yet)
- Extract the `translate-sse` orchestrator out of `cli.py` into a service. [both]
- Split `financials.py` into a source-agnostic facts interface with per-family adapters. [both]
- Promote S-1/F-1 to a first-class registration adapter rather than a hidden fallback in SEC query. [Codex]
- Whether HK `facts.json` generation becomes a first-class `build-hk` command (today it is fixture-only). [Claude / Phase 0]
- Whether the SEC cache/client stays owned (D1), downstream of the dependency-budget decision.
- Whether the corpus-scale `harvest`/`index`/`search` pipeline is a first-class product surface needing its own parity treatment (§3 blind spot).

### Samay decisions required before vNext

Blocking the harness/corpus finalization (settle these first):
1. **Known-bad pin-vs-fix** for HKEX 1000x, China `filed=Dec-31`, FX one-month-average. Finalizes the 6 `known_bad` corpus rows. (A10)
2. **Backward-compat scope**: exact pack-artifact bytes? exact CLI flags/output? `json-full` as a stable external contract? learned-registry migration? Decides the entire shim strategy. (A11)

Blocking specific architecture, not the harness (settle before the relevant subsystem rewrite):
3. **EdgarTools delegation + dependency budget** (breach pydantic+tiktoken-only or not?). Gates how much of `sec/` is in scope. (D1)
4. **FastAPI/web Evidence Explorer: retired or revived?** Decides `insights/`, the observatory HTTP routes, and the China storage backends. (A6/D4)
5. **Determinism scope across machines** (tiktoken present vs absent) → hard precondition? (risk 3)
6. **Three comparison surfaces** (`query`/`comps`/`compare`): keep or consolidate, and which output is the parity oracle?
7. **HKEX/SSE scope + metadata source** (filing vs `universe.toml` vs hardcoded `_COMPANY_META`) + `build-hk` wiring.
8. **self-heal/learned direction**: keep on the read path, or move to explicit review / strict-by-default? Decide *after* the marginal-coverage measurement (D6).

Cheap to settle, non-blocking (resolve opportunistically):
9. **Version reconciliation** (`__version__` 0.1.0 vs `PARSER_VERSION` 0.2.1): the canonical version source. (Phase 0 Q1; both Phase 1 reports dropped it)
10. **A-share bare-6-digit routing truth**: settle by running code, then pin.

---

## Adjudicator's bottom line

The two passes agree on far more than they dispute, and the disputes are mostly about *depth* (how much to delegate, delete-vs-park) rather than *direction*. The direction is settled between them: narrower owned core, delegated commodity SEC tier, harness before rewrite, citation contract untouchable.

The genuine open calls that need a human are small in number and concentrated in two buckets: the known-bad pin-vs-fix ruling and the backward-compat scope (both block the corpus), and the EdgarTools dependency-budget question (gates the SEC-acquisition scope). Everything else is either settled by both reports, resolvable by a cheap spike or a one-line command, or a parity case to write.

Two of the open verification items were settled on 2026-06-16 by direct code read, and one of them reversed a Claude Phase 1 claim, which is worth stating plainly: the cache TTL tests are dead exactly as Phase 0 said, and the Claude report's "likely collected, contra Phase 0" correction was wrong. D5 resolved in Claude's favor (counts diverge, intensity is shared). The net of the verification pass is that three of Claude's four Phase 0 corrections stand (offline-determinism-test-exists-but-narrow, asset-drop-has-no-warning, diff-timeline-counts-only) and one is withdrawn (cache-test collection: Phase 0 was right). These, plus the resolved D5, should be reconciled into the Phase 0 corpus so the next phase starts from a single corrected record rather than three documents that disagree at the margins.
