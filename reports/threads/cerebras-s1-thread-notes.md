# Cerebras S-1 → S-1 Diff: 2024 IPO Attempt vs 2026 Refile

*Source: edgarpack diff between Cerebras Systems Inc. (CIK 0002021728) S-1 filings. Captured 2026-05-05.*

Underlying artifacts:
- `0001628280-24-041596` (S-1 filed Sept 30, 2024 — original IPO attempt)
- `0001628280-26-025762` (S-1 filed Apr 17, 2026 — refile)
- Diff: `/tmp/diffs/crbs_s1.txt`
- Pack root: `packs/0002021728/`

**Headline meta-stat: 81.9% change intensity.** Annual 10-K cycles run ~13–28%. 82% means this is essentially a brand-new prospectus. Same skeleton, almost every substantive paragraph rewritten.

8 sections modified, 1 added (Principal Stockholders), 1 removed (Underwriting).

---

## The numbers — financial scale changed completely

Pulled from Risk Factors openings and Prospectus Summary tables, both filings.

- **2024 S-1**: revenue $24.6M (FY2022) → $78.7M (FY2023).
- **2026 S-1**: revenue $290.3M (FY2024) → **$510.0M (FY2025)**.
- 6.5x in two years. FY24 → FY25 alone is +76%.

GAAP net income / loss (Prospectus Summary table):
- FY2024 = **$(481.6M) loss**.
- FY2025 = **+$237.8M GAAP profit.**
- Driver: "Change in fair value (extinguishment) of forward contract liability" = **+$363.3M positive in 2025** vs. **$401.3M negative in 2024**. The forward contract was likely tied to the original G42 deal; extinguishing it in 2025 produced a large paper gain.

Non-GAAP (operating-economics) view:
- FY2024 non-GAAP net loss: $(21.8M).
- FY2025 non-GAAP net loss: **$(75.7M)** — loss got bigger as inference scale ramp continued.

Stock-based comp: $58.6M (FY24) → $49.8M (FY25). R&D heavy at $32.2M of that.

Balance sheet (Dec 31, 2025):
- $701.7M cash and equivalents
- $824.1M working capital
- $2.33B total assets
- $971.3M total liabilities
- **$1.93B redeemable convertible preferred stock**
- **$(578.7)M stockholders' deficit**

---

## The customer story — completely rewritten

The single most consequential change.

- **2024 S-1**: *"a substantial portion of our current business is supported by one primary customer"* + *"a significant majority of our revenue is generated from one customer headquartered in the United Arab Emirates"*. That customer is G42. G42 was both the concentration risk and the CFIUS / export-control risk.
- **2026 S-1 forward-looking statements** name customers explicitly for the first time: *"our ability to successfully retain existing customers, including **OpenAI, G42, MBZUAI, AWS**, and other significant customers."*
- New 2026 disclosure (Prospectus Summary): *"our top ten customers by year-to-date revenue through December 31, 2025 increased their aggregate spend with us by approximately 80% within 12 months of their initial purchase, often including contracts for co-development."*

The story flipped from "we are dependent on G42" to "we have a top-10 cohort with OpenAI / G42 / MBZUAI / AWS as named anchors, growing 80% YoY."

---

## The OpenAI Warrant — the smoking gun

Buried at line 3017 of the diff, in Capitalization footnotes. Not in the 2024 S-1 at all.

*"In December 2025, we issued the OpenAI Warrant to OpenAI in connection with the execution of the MRA. Pursuant to the OpenAI Warrant, OpenAI has the right to purchase up to **33,445,026 shares of our Class N common stock at an exercise price of $0.00001 per share.**"*

Effectively a free-share grant. Vesting tied to:
- 4,459,337 shares vested January 2026 upon Cerebras' receipt of a **"Working Capital Loan" from OpenAI**.
- 5,574,171 shares vest at the earlier of (a) Cerebras market cap exceeding **$40 billion** (30-day VWAP) or (b) certain fee milestones.
- Additional tranches tied to MRA (Master Reseller Agreement) milestones.

Translation: OpenAI loaned Cerebras working capital, signed a Master Reseller Agreement, and took 33.4M shares in exchange — a Coreweave-style supplier-equity arrangement. This is the structural reason the 2026 S-1 looks different. OpenAI is simultaneously a named significant customer, a substantial equity holder, and a creditor.

---

## Class structure changed dramatically

- **2024 S-1**: two classes — Class A (1 vote) + Class N (non-voting, convertible).
- **2026 S-1**: three classes —
  - Class A (1 vote, sold in IPO)
  - **Class B (20 votes per share, founder/insider supervoting)**
  - Class N (non-voting)
  - Existing Class A reclassified into Class B prior to IPO ("Common Stock Reclassification").

20:1 supervoting is more aggressive than Meta's or Google's. Cerebras decided, between 2024 and 2026, to give Andrew Feldman and the founder group hard supervoting control before going public.

Other capitalization details:
- Preferred stock conversion: 82.9M Class A in 2024 → **124.7M Class B** in 2026 (supervoting goes to existing preferred holders).
- Outstanding stock options as of Dec 31, 2025: 28.4M Class B options at **$4.97 weighted-average exercise**.
- Trading symbol: **"CBRS"** on Nasdaq Global Select Market.

---

## Mission and pitch were rewritten

- **2024 mission**: *"Our mission is to accelerate AI by making it faster, easier to use, and more energy efficient, making AI accessible around the world."*
- **2026 opening**: *"We are building the **fastest** AI infrastructure in the world. **In AI, speed is critical to win.**"*

From accessibility-and-energy-efficiency (a hedge-against-NVDA pitch) to raw speed dominance (a we-beat-NVDA-on-our-axis pitch).

The new buyer thesis is explicitly inference-time compute and AI coding agents:
- *"Today, AI has entered a new era centered on inference… these models effectively 'think through' the problem… These additional steps use substantially more compute during inference, while producing more accurate answers."*
- Names competitor models: *"OpenAI's GPT-5.4, Anthropic's Claude Opus 4.7, and Google's Gemini 3.1 Pro."*
- Names buyer apps: *"Products such as Cursor, Claude Code, Codex, Windsurf, and GitHub Copilot act as autonomous collaborators… AI-native coding products barely existed in 2023. Yet they collectively generated billions in ARR in 2025."*

---

## Hardware comparison got specific (and aggressive)

The 2024 S-1 described WSE in general terms. The 2026 S-1 stacks it directly against NVIDIA:

*"The WSE-3 is **58 times larger** than NVIDIA's B200 chip. The WSE has **19 times more transistors**, **250 times more on-chip memory**, and **2,625 times more memory bandwidth** than NVIDIA's B200 package, which contains two individual chips."*

Exact-figure NVDA comparisons in an S-1 are unusual. Cerebras is leaning in.

New technical disclosure:
- Three generations at **16, 7, and 5 nm nodes**.
- *"a single massive processor… deliver a wafer that communicated across the entire **46,225 mm of silicon**."*
- WSE-3 spec: 900,000 cores, 44GB on-chip memory, 21PB/s memory bandwidth.

---

## TAM reframing

- **2024 S-1**: *"$131 billion in 2024, growing to $453 billion in 2027, a 51% CAGR."*
- **2026 S-1**: *"The combined market for AI training infrastructure and our addressable market within AI inference is estimated to be **$251 billion in 2025**"* + *"investments in AI solutions and services are projected to yield a global cumulative impact of **$22.3 trillion by 2030**."*

Methodology shifted from training-led to inference-led. Absolute numbers larger.

---

## What got dropped

- **G42 dependency risk softened.** Still in the filing (Class N share reservations for G42 Primary Purchase remain), but no longer the singular customer.
- **Underwriting section removed** — 2026 S-1 left it blank. Underwriting syndicate gets named in the May 2026 S-1/A.
- **Selling stockholders disappeared.** 2024 S-1 contemplated insider secondary sales; 2026 is primary-only. Clean offering.
- **2023 AI Executive Order** mentions streamlined; **EU AI Act (2024)** added.
- **Material weakness disclosure carries forward** — still unremediated.

---

## What this tells us

1. **Cerebras walked away from the 2024 IPO because of the CFIUS overhang on G42.** The 2024 filing made the G42 scrutiny explicit; the 2026 filing has decoupled the company narrative from G42. They had to wait for a different demand profile to be IPO-able.
2. **OpenAI is the new anchor**, both as customer and equity holder. The OpenAI deal is the commercial substance that made this S-1 viable.
3. **Founder supervoting before IPO.** Cerebras was not previously dual-class. They built the structure specifically for the public-market entry.
4. **Pitch pivoted from energy-efficiency to inference speed** — the more defensible angle in 2026, given how much of the AI infrastructure narrative now rides on test-time compute.
5. **The GAAP profit is an accounting event, not operating economics.** Sophisticated readers will look at non-GAAP net loss ($75.7M) and FCF, not headline net income.

---

## Edgarpack notes for this run

- **One-shot diff in seconds.** `edgarpack diff --before <pack> --after <pack> --form S-1 --format full` — two prospectuses, hundreds of pages of EDGAR HTML each, compressed into a single 3,047-line text diff.
- **81.9% intensity was real signal here**, not noise. The high-intensity sections (Risk Factors 98%, Dilution 100%, Prospectus Summary 86%, Business 81%, Capitalization 64%) all carried substantive change. The S-1 sectionizer aligned cleanly across the two filings — same section IDs both times. (Better behavior than what we saw on the 10-K diffs.)
- **Same recurring weakness on tables** — pipe-delimited duplication on the financial summary tables. Workable; dollar figures came through readable.
- **Cross-filing-event use case is a real edge**. S-1 prospectuses don't have year-over-year iteration. They're event filings. Edgarpack's section-aligned diff handles the comparison between a withdrawn IPO and its refile natively — a use case a 10-K-style change-tracking workflow wouldn't attempt.

---

## Thread material — candidate hooks

1. *"Cerebras filed an S-1 in September 2024. They withdrew it. They refiled this April. Running edgarpack across the two filings: 81.9% change intensity. For comparison, year-over-year 10-K diffs run 13–28%. Same skeleton, almost every substantive paragraph rewritten."*

2. *"The headline number: revenue went from $79M (FY23) in the 2024 S-1 to **$510M (FY25)** in the 2026 S-1. 6.5x in two years."*

3. *"FY2025 looks GAAP profitable ($237.8M net income) but it's a one-time accounting event — extinguishment of a forward-contract liability worth $363M. Non-GAAP, they lost $75.7M. Real economics: still loss-making, sitting on $700M cash, going to market."*

4. *"The 2024 S-1: 'a significant majority of our revenue is generated from one customer headquartered in the United Arab Emirates.' That's G42. The 2026 S-1 names four customers by name in the forward-looking statements: **OpenAI, G42, MBZUAI, AWS**. Different company."*

5. *"The smoking gun is at line 3017 of the diff. In December 2025, Cerebras issued OpenAI a warrant for **33,445,026 shares of Class N common stock at $0.00001 per share** — basically free. Vesting tied to a working-capital loan from OpenAI and a $40B market-cap milestone. Coreweave-style supplier-equity deal."*

6. *"OpenAI is simultaneously a named significant customer, a substantial equity holder, and a creditor of Cerebras. The 2024 S-1 didn't mention OpenAI at all. The relationship was built between filings."*

7. *"Cerebras went from a two-class structure (1-vote A + non-voting N) to a three-class structure with **Class B at 20 votes per share** going to founders/insiders. They built supervoting specifically for the public-market entry. 20:1 is more aggressive than Meta or Google."*

8. *"Mission rewrite. 2024: 'accelerate AI by making it faster, easier to use, and more energy efficient.' 2026: 'We are building the fastest AI infrastructure in the world. In AI, speed is critical to win.' From hedge-against-NVDA pitch to we-beat-NVDA-on-our-axis pitch."*

9. *"The 2026 S-1 stacks WSE-3 directly against NVIDIA's B200: 58x larger, 19x more transistors, 250x more on-chip memory, **2,625x more memory bandwidth**. Exact-figure NVDA comparisons in S-1s are unusual. Cerebras is leaning in."*

10. *"Why it matters: the 2024 IPO was killed by the CFIUS overhang on the G42 dependency. They had to wait until a different anchor customer (OpenAI) showed up before they could come back to market. The S-1 diff makes the timeline visible — what changed, when, and at what cost."*

11. *"On the tooling: edgarpack converted the comparison between a withdrawn IPO attempt and its refile into a single text diff. S-1s don't have annual cycles, so cross-filing-event diffing is genuinely a new analytical surface — not just a faster version of something humans already do."*
