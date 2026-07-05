# Packet: build-hk (STUB. Do not launch.)

Status: awaiting the HKEX acquisition spike (in flight). This stub records scope so the wave plan is complete; Fable finalizes it into a full spec when the spike lands.

Goal: `edgarpack build-hk <ticker-or-code>` acquires and builds an HKEX pack for ANY listed issuer: no fixture scripts, no hand-edited sections.yaml, no hardcoded 6-company metadata dict.

Known scope (to be sharpened by spike evidence):
- Acquisition: HKEX news search endpoint flow (stockId resolution, annual-report listing, edition selection preferring the ENGLISH edition when available, staleness guard mirroring the CNINFO one).
- Pack construction: decide reuse-vs-new between the hand-mapped `hk/adapter.py` approach and the SSE-style pymupdf4llm + sectionizer approach, per spike verdict on English AR extractability.
- Metadata: reporting currency and accounting standard sourced from the filing or search metadata, replacing `_COMPANY_META`.
- Facts: whatever construction path wins must feed the existing `facts.json` contract (column-count guard and Phase 2 provenance rules intact).
- One-command integration: after this packet, the one-command-china build-if-needed flow extends to HKEX filers (follow-up noted in one-command-china.md).

Open questions the spike must answer before spec finalization: endpoint request/response shapes and rate behavior; English-edition availability rate; text-embedded vs OCR reality on modern HK ARs; whether section conventions in English ARs are regular enough for a heading-based sectionizer.
