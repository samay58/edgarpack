# NVDA + META 10-K Diff Findings — Thread Draft Notes

*Source: edgarpack diffs over NVDA last 3 10-Ks (FY24/25/26) and META last 3 10-Ks (FY22/23/24). Captured 2026-05-05.*

Underlying artifacts:
- `reports/nvda-10k.html` (NVDA FY25→FY26 HTML diff, intensity 13.2%)
- `/tmp/diffs/nvda_24_25.txt` (NVDA FY24→FY25, intensity 22.4%)
- `/tmp/diffs/meta_22_23.txt` (META FY22→FY23, intensity 28.7%)
- `/tmp/diffs/meta_23_24.txt` (META FY23→FY24, intensity 27.8%)
- Pack roots: `packs/0001045810/` and `packs/0001326801/`

---

## NVIDIA — what the filings say

The fast company is *narrowing*, not widening.

- **Customer concentration nearly doubled.** FY26: one direct customer = 22% of revenue, a second = 14%. FY25 had three customers at 12 / 11 / 11. FY24 had one at 13%. On $215.9B FY26 revenue, the top customer is roughly $47B from a single counterparty.
- **A brand-new top-tier risk: counterparty risk.** FY26 Risk Factors summary added: *"Commercial arrangements expose us to counterparty risks, which may negatively impact our business, financial condition, or results of operations."* Old FY25 bullets about customer bankruptcy and credit risk got rolled up into this one named bucket.
- **The OpenAI tell, in legalese.** FY26 MD&A: *"one AI research and deployment company contributed to a meaningful amount of our revenue purchasing cloud services from our customers in fiscal year 2026."*
- **$4.5B H20 inventory charge** disclosed in FY26 Q1 — the concrete dollar cost of China export restrictions, the driver of gross margin going 75.0% → 71.1%.
- **R&D in passing.** Cumulative R&D since inception: $58.2B → $76.7B in one year. ~$18.5B FY26 alone.
- **Self-description shifted.** "Full-stack computing infrastructure company" → "data center scale AI infrastructure company."
- **New customer categories named.** "AI model makers" and "Neocloud builders" — Coreweave / OpenAI by class, not by name.
- **Quietly dropped from segment descriptions:** DGX Cloud, Jetson, GeForce NOW, vGPU, Omniverse Enterprise.
- **Pitch reframed** from "performance and power efficiency" to "total cost of ownership." CFO sales motion, not engineer.
- **NVLink Fusion** introduced — explicit hedge into the custom-silicon trend by letting hyperscalers plug their own CPUs/ASICs into NVDA's platform.
- **Rubin announced** for H2 FY27, claiming "10x reduction in cost per token compared to Blackwell."
- **Geographic rewrite.** International revenue restated under a new methodology (location of customer HQ): FY25 = 41%, FY26 = 31%. Old method had FY25 at 53%.
- **Top500 share** crept 75% → 78%. Green500 dominance went 38-of-top-50 to 9-of-top-10.
- **Apps supported**: 3,500 (FY24) → 4,400 (FY25) → 6,000 (FY26).
- **10-for-1 stock split** disclosed in FY25 (June 2024).

Three-year arc: filings stabilized as the story matured. Diff intensity went 22.4% → 13.2%, even as financial scale tripled.

---

## Meta — what the filings say

Opposite of NVDA: external pressure keeps rewriting the filing.

- **Mission statement rewritten in FY24.** *"Give people the power to build community and bring the world closer together"* → *"Build the future of human connection and the technology that makes it possible."* Companies almost never do this.
- **Metaverse reframed.** From "next evolution in social technology" → "**next computing platform** and the future of social interaction." Repositioning Reality Labs from a social bet to a generational compute bet.
- **Reality Labs operating drag disclosed at headline level for the first time:** *"reduced our 2024 overall operating profit by approximately $17.73 billion, and we expect our Reality Labs investments and operating losses to increase in 2025."*
- **Capital return pivot in FY24.** First-ever quarterly dividend ($0.50/share) declared February 2024. Additional $50B buyback authorization in January 2024. Stock went $354 → $585 over the year.
- **The regulator war diary:**
  - €1.2B IDPC fine (May 2023, Standard Contractual Clauses).
  - €798M EU Marketplace antitrust fine (Nov 18, 2024).
  - DSA applied from August 2023; DMA enforceable from March 2024.
  - EC opened a DSA investigation into FB/IG (April 30, 2024).
  - CFPB NORA process around financial advertising (Sept 18, 2024).
  - EU preliminary finding that "subscription for no ads" doesn't comply with DMA (July 1, 2024).
- **Generative AI promoted to standalone risk factor in FY24.** Specific callouts of deepfakes, election misinformation, IP infringement, defamation.
- **Zuckerberg key-person risk got specific.** New language: he participates in *"combat sports, extreme sports, and recreational aviation."*
- **Pre-emptive content moderation disclosure** in FY24: *"in January 2025, we announced certain changes to our content policies and enforcement efforts to further free expression on our platform and mitigate over-enforcement."* Written into the filing before the news cycle landed.
- **Threads + WhatsApp Channels** got their first product paragraphs in FY23.
- **Reality Labs vocabulary** expanded VR → "VR and MR" in FY23 (Quest 3 passthrough era), then to AR in FY24.
- **Item 1C Cybersecurity section** was first added in FY23 (new SEC rule).
- **FX losses 4.5x'd** quietly: $81M (2022) → $366M (2023). Didn't make headlines.
- **2022 layoff** memorialized as $4.6B restructuring ($4.10B FoA + $515M RL) in the FY22 filing, ages off in FY23/24.
- **FY23 metric sunset:** announced retiring DAU/MAU/ARPU/MAP for DAP/ARPP starting Q1 2024.
- **Inventory risk** for consumer hardware (Quest) elevated to its own risk factor in FY24, with explicit tariff language.

---

## Side-by-side framing

| Theme | NVDA (FY24 → FY26) | META (FY22 → FY24) |
|-------|---------------------|---------------------|
| Risk factor evolution | Customer concentration → counterparty risk; export controls | Cybersecurity (FY23) → DMA/DSA + AI (FY24) |
| Headline financial event | $4.5B H20 charge | $17.73B Reality Labs drag; €1.2B + €798M EU fines |
| Capital structure | 10-for-1 split | First dividend; +$50B buyback |
| Strategy reframing | "full-stack computing" → "AI infrastructure" | "metaverse" → "next computing platform" |
| Filing churn driver | Internal scale-up | External regulatory pressure |
| Diff intensity trend | 22.4% → 13.2% (stabilizing) | 28.7% → 27.8% (steady churn) |

NVDA is converging on a tighter, more concentrated story. Meta is being forced to keep rewriting theirs.

---

## Edgarpack — usefulness, honest read

**The unlock.** Two large 10-Ks become small enough to fit in working memory and clean enough to compare paragraph-by-paragraph. NVDA's full filing as raw HTML is ~150K+ tokens; section markdown for everything I read across all four diffs was under 50KB. **20–40x token compression**, before the diff narrows to changed paragraphs only.

**Citation by construction.** Section IDs align across years (`10k_parti_item1a_risk_factors.md`). That's what makes "this paragraph in FY24 became this paragraph in FY25" responsible to claim without manually paging through PDFs.

**Triage that mostly works.** Change-intensity rail is useful for prioritizing — Risk Factors and MD&A floated to the top in all four diffs.

**Recurring failure mode: sectionizer drift.** Every NVDA diff flagged Item 9A "Controls and Procedures" with absurd +130-style deltas. Every Meta diff did the same to Legal Proceedings sub-sections. Both are sectionizer artifacts (the same text getting sliced into different sections across filings), not real disclosure changes. You learn to discount them, but the change-intensity scoring doesn't currently distinguish "real text changed" from "same text moved sections."

**The HTML report is the wrong artifact for an LLM.** 946KB of inline CSS, evidence links, per-paragraph metadata, built for human scrolling. I read it once and bypassed it after — `edgarpack diff --format full` piped to text was the workable surface. The section packs are the load-bearing primitive; the HTML is chrome.

**Tables are weak.** Income statement and segment tables come through as pipe-delimited duplication (`Cost of revenue / Cost of revenue / 28.9 / 28.9`). 2x token cost and mental normalization. Clean table render would extend the tool meaningfully into financial analysis.

**Counterfactual.** Without edgarpack, four pairwise 10-K diffs across Meta and NVIDIA from raw EDGAR = locating 8 filings, parsing inline-XBRL HTML, normalizing section headings (which shift across years), diffing, and citing across them. 5-10x more tool turns, real risk of misciting paragraphs. With edgarpack, the four diffs in this session ran in parallel and finished in seconds.

**The shape of the value.** Edgarpack converts a context-window problem into a signal-extraction problem. The tool's analytical lift is modest — it doesn't tell you what matters. It clears scaffolding so you can see what matters.

**Two things to fix to make it materially better:**
1. Smarter sectionizer alignment so noise hunks stop shouting (the Item 9A "responsibility_is_to" pattern is recurrent and learnable).
2. Structured table extraction so financial tables are first-class, not pipe-string mush.

**The fascinating findings — H20 charge, 22% customer, NVLink Fusion, Meta's mission rewrite, Zuckerberg combat sports, OpenAI indirect-revenue tell — are not findings edgarpack made.** They are findings the tool made *findable* by getting filings into a size and shape where reading is possible at all.

---

## Thread material — candidate hooks

1. *"NVIDIA's FY26 10-K quietly says one customer is 22% of $215B in revenue. A year ago no customer was over 13%. The risk factors caught up — they added a new top-tier risk called 'counterparty risk' and rolled the old credit-risk bullets into it."*
2. *"The $4.5B H20 inventory charge is the actual dollar cost of China export restrictions, finally booked. Gross margin went 75.0% → 71.1% in one year."*
3. *"NVDA's cumulative R&D since inception went $58.2B → $76.7B in a single year. That's ~$18.5B in FY26 alone, larger than most public tech companies' total revenue."*
4. *"Meta rewrote their mission statement in FY24. Companies almost never do this. 'Give people the power to build community' became 'build the future of human connection.' At the same time, 'metaverse' stopped being called the next evolution in social technology and started being called the next computing platform."*
5. *"Meta disclosed for the first time that Reality Labs reduced 2024 operating profit by $17.73B — and warned 2025 losses will be larger."*
6. *"Mark Zuckerberg's key-person risk factor in the FY24 10-K specifically calls out 'combat sports, extreme sports, and recreational aviation.' This is real."*
7. *"The OpenAI tell: NVDA's FY26 10-K mentions 'one AI research and deployment company' contributing meaningfully to revenue via cloud services bought through NVDA's customers."*
8. *"NVLink Fusion is the most interesting product disclosure in the NVDA filing — it explicitly lets hyperscalers plug their own CPUs and custom ASICs into NVDA's platform. The hedge against custom silicon, written into the 10-K."*
9. *"Two opposite stories. NVIDIA's filing churn is dropping (22% → 13% YoY change intensity) as the company narrows around fewer, larger AI customers. Meta's filing churn is steady at ~28% — driven by external pressure: DMA, DSA, IDPC fines, AI risk, generative AI risk factors."*
10. *"On the tooling: edgarpack converted a context-window problem into a signal-extraction problem. Two 10-Ks of ~150K+ tokens each compressed to <50KB of section markdown for the changed paragraphs. The tool didn't make the findings — it made them findable."*
