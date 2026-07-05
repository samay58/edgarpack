# Packet: english-surface

Goal: the zero-knowledge American investor reads English by default and can always see the Chinese receipt. Two concrete rendering changes, no translation pipeline involvement.

Files owned: `edgarpack/query/render.py`, `edgarpack/query/formatting.py`, tests (`tests/test_render_*` / formatting tests as they exist; find them by grepping imports).
Out of scope: JSON output shapes (matched_label already flows there since Phase 2), the translation pipeline, error-message wording elsewhere.

## Pre-made design decisions

- Bilingual metric cells: in TABLE output only, when a China-path value carries a non-empty `matched_label`, the metric cell renders `Revenue (营业收入)` style: English display name, space, parenthesized original label. Truncate labels over 24 characters with a single trailing ellipsis character is FORBIDDEN (kill-list); truncate at 24 chars with no ellipsis marker and show the full label in the citation footer line instead. Non-China values render exactly as today (pin one SEC table byte-identical in a test).
- Filing-type context line: table output for China-path results gains ONE context line directly above the citation footer. Exact strings, verbatim:
  - SSE annual-report packs: `Source: 年度报告 (annual report) filed with CNINFO, the A-share equivalent of a 10-K.`
  - HKEX packs: `Source: annual report filed with HKEX news.`
  No line for SEC filers or registration results. Suppressed in `--format json` and `json-full` (JSON carries structured provenance already). No flag to toggle it this packet; if a reviewer wants one, that is a follow-up.
- Detection of "China-path" is by the value's existing provenance fields (source/section_id/currency provenance the China path already sets); do not add new fields to CitedValue.

## Tests

- A China-path table with matched_label renders the bilingual cell and the context line; footer carries the full label when truncated.
- An SEC table renders byte-identical to before (golden string test).
- JSON outputs unchanged (assert absence of the context line and absence of the parenthesized label in metric keys).

## Done definition

Tests green; full offline suite green; screenshots not required (CLI text), but include one pasted example table in the report for the taste gate.
