# Packet: hk-construct-prototype (report-only; no repo code)

Goal: de-risk the two things the HKEX spike said not to spec blind, so Fable can write the final build-hk construction spec from evidence: (1) TOC-page-driven sectioning variance across issuers, (2) whether `hk/extract.py`'s table machinery holds up at large-cap nesting depth.

Ownership: NOTHING in the repo. All prototype code, downloads, and outputs live under the session scratchpad `hk-construct-prototype/`. Your deliverable is the report.

Inputs: the spike already downloaded Tencent's FY2025 AR (scratchpad `hkex-spike/tencent_ar2025.pdf`) and recorded the acquisition flow (build-hk.md documents it; `hkex-spike/hkex_probe.py` has working request code to crib). Acquire the English FY2024-or-later ARs for: Meituan 3690, BYD 1211, HSBC 0005, and one mid-cap of your choosing outside the mega-caps (e.g. Anta 02020 or Xiaomi 01810) for shape diversity.

Questions to answer, per issuer:
1. Contents page: does a parseable TOC with per-section page numbers exist? Record its exact format (page, line shapes, whether page numbers lead or trail titles). Prototype a parser producing (title, start_page) pairs; report hit rate and the format variance table.
2. Section slicing: using those pairs, slice the financial-statement sections (income statement, balance sheet/financial position, cash flows, notes) by page boundary. Do the four statements land in the right slices for all issuers? Note title variance (the spike saw "Consolidated Income Statement" vs the legacy map's "Consolidated Statement of Profit or Loss"): produce the keyword map seed the real sectionizer should ship with.
3. Table extraction: run the sliced statement pages (raw pypdf text, NOT pymupdf4llm, per the spike verdict) through `hk/extract.py`'s parsing machinery (import it read-only from the repo; adapt in scratch as needed). Per issuer, report per-metric hit/miss for the ~10 standard metrics, every wrong value with its mechanism (nesting subtotal confusion, multiplier misdetection, wrapped labels), and what minimal extensions the parser needs.
4. Metadata anchors: confirm the basis-of-preparation and presentation-currency notes are findable in all five documents; record the exact sentences.
5. Pack-shape wiring notes: what of dual-counter codes, DOD_WEB_PATH, and results announcements needs manifest/facts.json fields vs can be ignored.

Report format: per-issuer table (TOC parseable / sections sliced / metrics hit rate / metadata anchors found), the keyword map seed, the parser extension list ranked by necessity, and a go/no-go recommendation for the construction approach (TOC-sliced + extended extract.py) with any fallback needed. Include exact artifact paths.
