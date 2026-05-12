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

---

## May 11 S-1/A addendum: what the "A" amended

*Source: edgarpack diff between Cerebras Systems Inc. S-1/A filed May 4, 2026 (`0001628280-26-029503`) and S-1/A filed May 11, 2026 (`0001628280-26-033143`). Captured 2026-05-11.*

Commands:

```bash
uv run edgarpack list Cerebras --form S-1/A --limit 10
uv run edgarpack timeline --series registration --cik 0002021728 --format text
uv run edgarpack diff \
  --before packs/0002021728/0001628280-26-029503 \
  --after  packs/0002021728/0001628280-26-033143 \
  --format summary
uv run edgarpack diff \
  --before packs/0002021728/0001628280-26-029503 \
  --after  packs/0002021728/0001628280-26-033143 \
  --format json
uv run edgarpack query Cerebras --period lfy --format json
uv run edgarpack which Cerebras --format json
```

This amendment is much narrower than the original 2024-to-2026 rewrite. EdgarPack shows 6.2% overall change intensity from May 4 to May 11, versus 81.9% from the 2024 S-1 to the April 2026 refile. Nine sections changed, but most of the diff is table-format churn and offering mechanics. The real amendments are pricing, share count, RSU settlement math, ownership percentages, and directed-share distribution plumbing.

### Offering size and implied valuation moved up

- Class A shares offered increased from 28,000,000 to 30,000,000.
- Over-allotment option increased from 4,200,000 to 4,500,000 shares.
- Assumed IPO price moved from $120.00 to $155.00.
- Gross primary proceeds in the dilution table moved from $3.36B to $4.65B before underwriting discounts and expenses.
- Net proceeds estimate moved from $3.2418B to $4.4875B, or from $3.7294B to $5.1620B if the over-allotment is exercised in full.

This is the cleanest thread update: Cerebras did not merely refresh language. It raised the proposed deal size and pricing assumption meaningfully in the amended filing.

### The tax-withholding use of proceeds got much larger

The use-of-proceeds section changed because the assumed IPO price changed and the RSU settlement math updated:

- May 4 S-1/A: about $230.0M of proceeds intended for RSU tax withholding and remittance.
- May 11 S-1/A: about $329.6M of proceeds intended for the same purpose.
- The assumed withholding rate stayed 44.3%.

So roughly $100M more of the IPO cash is earmarked for tax withholding mechanics, not incremental business investment.

### Dilution got harsher even though book value improved

The dilution table changed from:

- $120.00 assumed IPO price
- $20.50 pro forma as-adjusted net tangible book value per share
- $99.50 dilution per share to new investors

to:

- $155.00 assumed IPO price
- $25.61 pro forma as-adjusted net tangible book value per share
- $129.39 dilution per share to new investors

The higher price gives the company more balance-sheet cushion, but public buyers absorb more dollar dilution per share.

### RSU settlement and ownership math were updated

The assumptions block changed from:

- 2,405,513 net Class B shares issued from RSUs after withholding
- 1,916,764 shares withheld for taxes
- May 4, 2026 vesting reference date

to:

- 2,668,673 net Class B shares issued from RSUs after withholding
- 2,126,456 shares withheld for taxes
- May 11, 2026 vesting reference date

Principal stockholders also changed:

- Class B shares used for ownership calculations increased from 185,159,985 to 185,423,145.
- Current executive officers and directors as a group moved from 47,936,708 shares to 47,330,231 shares, with explicit RSU Net Settlement treatment added.
- The filing now gives named RSU settlement share adjustments for Feldman, Lie, Mallick, and the executive/director group.

This is not a change to the founder-control thesis. It is cleanup around what exactly counts as outstanding and beneficially owned once the IPO-triggered RSUs settle.

### New conversion disclosure matters for voting power

The latest amendment adds a paragraph saying that, at IPO completion, approximately:

- 10,819,379 Class B shares,
- 20,225,735 Class B shares issuable on options, and
- 16,687,344 Class B shares issuable on RSUs before the RSU Net Settlement,

will convert into Class A shares or Class A awards for certain current or former employees, consultants, and service providers.

The filing states the important governance implication directly: Class B-to-Class A conversions increase the relative voting power of Class B holders who retain their shares.

That sharpens, rather than weakens, the prior control read. Even as more shares are sold or converted into Class A, the remaining Class B holders become relatively more powerful.

### Directed-share / international selling language got cleaned up

Description of Capital Stock had the highest absolute diff score. The substantive bits were mostly legal-distribution edits:

- Canada language now carves out certain sales under the directed share program from the permitted-client requirement.
- The underwriting-conflicts disclosure now adds an exception for directed-share sales to purchasers who are not permitted clients.
- Israel language was completed around the investor representation for shares issued under the offering.

This points to distribution mechanics getting finalized around the directed share program, not a change in the business.

### What did not change

- Revenue, GAAP net income, non-GAAP loss, gross margin, customer roster framing, OpenAI warrant economics, and the 20-vote Class B structure did not materially change in this amendment.
- Business changed only 0.7% by EdgarPack intensity. Risk Factors changed 0.1%.
- The visually large diff in financial tables is mostly parser/table-format noise. The actual 2025 and 2024 financial statement numbers remain the same in the sections checked.

### Thread update

The April thread remains directionally right. The May 11 amendment adds one useful coda:

> The newest Cerebras S-1/A is not another strategic rewrite. EdgarPack shows only 6.2% change intensity from May 4 to May 11. The "A" is mostly the deal getting priced up: 28M shares became 30M, the assumed IPO price moved from $120 to $155, estimated net proceeds moved from $3.24B to $4.49B, and public-investor dilution moved from $99.50 to $129.39 per share. The control story got one more wrinkle: new disclosure says employee/consultant Class B shares and awards converting into Class A will increase the relative voting power of Class B holders who keep their shares.

The 2024-to-2026 S-1 diff explains why Cerebras became IPO-able again. The May 11 S-1/A shows the book was strong enough, or at least marketed aggressively enough, to push size and price higher while cleaning up IPO mechanics.
