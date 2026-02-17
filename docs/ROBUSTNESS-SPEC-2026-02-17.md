# EdgarPack Robustness Spec (2026-02-17)

Status: Implemented in `main` on 2026-02-17 (`ltm-1` support, docs, and regression coverage).

## Context
Production testing surfaced follow-up work tracked in beads, with `edgarpack-jfm` (`P1`) as the primary correctness gap. The goal is to improve reliability without adding abstraction bloat.

## Goals
- Implement `period=ltm-1` with the same citation guarantees as `ltm`.
- Preserve existing graceful-degradation behavior when SEC history is incomplete.
- Keep the codepath lightweight by sharing LTM logic instead of branching copies.
- Keep public behavior explicit in CLI/docs/tests.

## Non-goals
- No broad period-framework rewrite.
- No fetch/cache architecture churn unless a bug demands it.
- No sectionize refactor in this pass.

## Design
### 1) Shared LTM Engine
Create one internal selector that computes LTM-like periods by anchor shift:
- `ltm` uses the latest cumulative quarter anchor.
- `ltm-1` shifts anchor one fiscal year back, same fiscal quarter.

Formula remains:

`anchor_mrp + anchor_lfy - anchor_mrp_prior`

Where:
- `anchor_mrp` = cumulative value for anchor quarter
- `anchor_lfy` = annual value for fiscal year before anchor
- `anchor_mrp_prior` = same quarter, one year before `anchor_lfy`

### 2) Fallback Policy
If any required component is missing:
- Return the best available anchored reported value (not an exception).
- Keep provenance fields populated from the anchored filing.

This matches current EdgarPack behavior: explicit real values beat guessed math.

### 3) Output Model Consistency
Treat `LTM` and `LTM-1` as the same derivation family for citation/lean JSON:
- Both expose component-backed citation.
- Both emit `ltm_components` in lean JSON.

### 4) Verification
Add tests for:
- Correct `ltm-1` math.
- Missing-history fallback.
- Period routing via `select_period(..., "ltm-1")`.
- `financials(..., period="ltm-1")` output semantics.

## Implementation Order
1. Period selector and routing.
2. Model output consistency.
3. CLI/docs updates.
4. Tests and regression run.
5. Bead reconciliation and ship.
