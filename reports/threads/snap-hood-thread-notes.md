# SNAP + HOOD 10-K Diff Findings — Thread Draft Notes

*Source: edgarpack diffs of two post-IPO survivors. SNAP across 8 years (year-after-IPO → mid-life → today). HOOD across 3 years (year-after-IPO → today). Captured 2026-05-05.*

Underlying artifacts:
- `/tmp/diffs/snap_17_21.txt` (SNAP FY17 → FY21, intensity 71.9%)
- `/tmp/diffs/snap_21_25.txt` (SNAP FY21 → FY25, intensity 94.3%)
- `/tmp/diffs/hood_22_25.txt` (HOOD FY22 → FY25, intensity 43.3%)
- Pack roots: `packs/0001564408/`, `packs/0001783879/`
- Anchors: SNAP IPO Mar 2017, HOOD IPO Jul 2021

---

## SNAP — three filings, three companies

The thing the diff makes obvious: SNAP didn't slow down — it reincarnated.

**FY17 (post-IPO, 0001564590-18-002721).** "Snap Inc. is a camera company." 187M DAUs, $824.9M revenue, net loss $3.4B, accumulated deficit $4.7B, 3,069 employees, HQ in Venice, founders Spiegel + Murphy holding 94.6% voting through Class C. Pitch: reinvent the camera. The 10-K reads like a manifesto. Risk factors are itemized prose ("Our two co-founders have control..."), 376 lines deleted by FY21.

**FY21 (0001564590-22-003868).** Still a camera company. 319M DAUs Q4'21 (1.7x), revenue $4.1B (5x), net loss $488M, Adj EBITDA $616.7M, 5,661 employees, HQ moved to Santa Monica. New disclosure: cumulative carbon offsets purchased to make Snap "historically carbon neutral" since 2011. Spectacles still mentioned. Snapchat+ subscription disclosed as launching 2022. Risk-factor structure rewritten (98.6% intensity in that section alone) — moved to "summary of risk factors" preface plus categorized prose.

**FY25 (0001564408-26-000013).** Different company. 474M DAUs Q4'25 (5% YoY — growth flatlining), revenue $5.93B (just 1.4x in 4 years; the slowdown is the story), net loss $460.5M (improving), Adj EBITDA $689.5M. The pivot is real:
- **Subscription-led pivot.** "Snapchat+, Lens+, and Snapchat Platinum, our subscription services" — Platinum is the new ad-free tier. Other revenue grew $287.6M YoY, "predominantly due to higher subscription revenue." This is a company that admitted advertising-only didn't work.
- **AI platform partner agreement disclosed.** Buried in MD&A: "an agreement with our AI platform partner." Not named in the filing. New revenue line.
- **My AI** (chatbot) launched 2023; called out as a major product surface.
- **Sponsored Snaps** introduced — ad inventory inside primary friend feed. The wall came down.
- **2024 restructuring** explicitly framed as "drive toward profitability and positive free cash flow." (Different language than 2017's "take big risks.")
- **Stock price disclosure.** "From January 1, 2024 to December 31, 2025, the trading price of our Class A common stock ranged from $6.90 to $17.75." Then this admission: declines "have required, and may continue to require, us to issue more equity to incentivize team members which is likely to dilute stockholders." Spiral risk written in plain text.
- **NOL stack.** $6.5B US federal NOL + $4.4B US state + $4.9B UK + $420M Singapore + $1.0B US federal R&D credit + $574.8M state R&D credit. **They have never been profitable enough to use any of it.**
- **Australia ban for under-16s.** Disclosed Dec 2025 implementation as a teen-safety risk factor.
- **2023 ad-platform change disclosed as a customer-disrupting failure.** "In January 2023, we made changes to our advertising platform to lay the foundation for future growth, but which have been disruptive to our customers." A rare 10-K admission of a self-inflicted product wound.

What got cut: Spectacles is gone from product positioning (still mentioned, no longer central). "We are a camera company" survives in spirit but the pitch shifted to "reinventing communication." The five-tabs-of-Snapchat list (Camera, Communication, Snap Map, Stories, Spotlight) replaced 2017's "Snap is the camera screen" framing.

**Diff intensity arc**: 71.9% (FY17→FY21) → 94.3% (FY21→FY25). The four-year FY21→FY25 gap is more disruptive than the entire IPO-to-2021 maturation. That's because the 10-K structure was rewritten when SOX/Reg S-K updates kicked in and because Snap's product model fundamentally changed.

---

## HOOD — same primitive, different scale

**FY22 (0001783879-23-000045, year after IPO).** Trough year. Two restructurings:
- April 2022: 9% layoff (~330 employees).
- August 2022: 23% layoff (~780). Five more office closures.
- Net: ~32% of headcount cut in eight months.

Revenue $1.36B (-25% YoY). Net loss $1.03B. Adj EBITDA -$94M. NCFA flat at 23.0M. **MAU collapsed from 17.3M to 11.4M (-34%).** AUC $62.2B (down from $98B). Gold subscribers 1.3M → 1.1M. The Q4 2022 processing error ate $57M (1-for-25 reverse split of Cosmos Health was mishandled). Brand was in crisis, mentioned by name: "Early 2021 Trading Restrictions, the November 2021 Data Security Incident, the Q4 2022 Processing Error, and uncertainty related to the status of the Emergent Shares."

**FY25 (0001783879-26-000023, today).** Different company entirely.
- **Funded Customers 27.0M (+7%); Investment Accounts 28.4M.** They added a new metric — "Investment Accounts" (multiple accounts per customer). NCFA was renamed Funded Customers. AUC was renamed Total Platform Assets ($322.1B, +67% YoY).
- **Net Deposits $68.1B in 2025.** That's a 35% growth rate against year-end 2024 platform assets. They are aggregating money at scale.
- **ARPU $171** (up 40% YoY from $122). For comparison: SNAP ARPU is ~$3-4 per quarter.
- **Robinhood Gold 4.18M subscribers** (+58% YoY from 2.64M). Reversal of FY22's churn.
- **Adj EBITDA $2.52B** (+76%). They went from -$94M to +$2.52B in three years.
- **DTA valuation allowance released in Q4 2024.** "Provision for income taxes increased by $572 million primarily due to the benefits from the valuation release of the U.S. federal and certain state deferred tax assets." The auditors agreed they'll be reliably profitable. The accountant's tell.
- **$152M of stablecoin on the balance sheet.** Listed as a liquidity source alongside cash. First time. New language: "cash flows generated from operations, and our cash, cash equivalents, investments, **and stablecoin**."

The product surface explosion is the part raw stats hide. The diff makes the long list of new business lines visible:
- **Robinhood Banking** — BaaS partnership with Coastal Bank, invite-only launch. RHY runs risk and compliance.
- **Robinhood Credit** — credit card facilitator/servicer (Coastal Bank is the issuer). Subject to CFPB authority.
- **Robinhood Strategies** — managed wealth, 0.25% management fee, capped at $250/yr for Gold.
- **TradePMR acquisition** — RIA custodial and portfolio management platform. Robinhood now serves financial advisors.
- **Bitstamp acquisition** — operating crypto exchange in EU.
- **RHEU (Lithuania)** — holds MiCA license + MiFID; stock tokens trading in EU; multi-currency accounts.
- **Robinhood Chain** disclosed as "a permissionless Layer 2 blockchain optimized for real-world assets, from public to private to global." They aren't using crypto; they're operating one.
- **24-hour market** — first U.S. broker.
- **Short selling launched Q4 2025.**
- **Index option trading** rolled out 2025 (S&P 500, VIX).
- **Robinhood Legend** — browser-based desktop trading platform for active traders, free, all major asset classes.
- **Singapore APAC office.** UK ISAs (stocks-and-shares).
- **58 supported cryptocurrencies.**
- **Mortgage rates** offered exclusively to Gold subscribers.
- **Strategic priority: tokenization of real-world assets** ("public to private to global").

Five new regulated subsidiaries — RHC, RHY, RHEU, RAM, RHV, RHD, plus TradePMR. The 10-K's regulation section nearly doubled in scope (broker-dealer, money transmitter, BaaS, MiCA, MiFID, FDCPA, ECOA, TILA, banking partnership oversight by Federal Reserve Board).

**Diff intensity 43.3%.** Lower than either SNAP comparison even though HOOD changed more aggressively in absolute product terms. Why: HOOD's 10-K structure was already mature post-IPO; the changes are mostly *additions*, not rewrites.

---

## Side-by-side framing

| Theme | SNAP (FY17 → FY21 → FY25) | HOOD (FY22 → FY25) |
|-------|-----------------------------|---------------------|
| Post-IPO survival | Stock $6.90–$17.75 in 2024–25, equity dilution spiral risk admitted | Two restructurings cutting ~32% staff; MAU -34%; brand-incident name-checking |
| Recovery shape | Subscription pivot (Snapchat+/Lens+/Platinum) + AI partnership | Financial supermarket: bank, credit card, wealth mgmt, RIA platform, crypto exchange, L2 blockchain |
| The accountant's tell | $11.8B+ NOL stack, never used | DTA valuation allowance released Q4 2024 ($572M tax provision swing) |
| New asset on balance sheet | None novel | $152M stablecoin |
| Capital structure | Class C still ~94% voting | Operating Robinhood Chain (own L2 blockchain) |
| Filing intensity | 94.3% (FY21→FY25 — pivot in flight) | 43.3% (additive expansion) |
| Pitch in own words | "reinventing the camera" → "next computing platform" | "democratize finance" → "global financial ecosystem" with "tokenization efforts" |

The mirror: SNAP went from a manifesto company to a margin company. HOOD went from a meme-trade casualty to running its own blockchain. Both were declared dead at IPO+1 to IPO+5; both come out the other side as something the prospectus didn't predict.

---

## Genuinely interesting tells

1. **HOOD's stablecoin disclosure** as a liquidity source is the single most underappreciated line in either filing. They're now a stablecoin holder of record at scale. Not a custodian for users — corporate treasury.

2. **HOOD's DTA valuation release** is a stronger profitability signal than any earnings release. Auditors require *more-likely-than-not* future profitability before they let you book the asset. They got the green light Q4 2024.

3. **SNAP's NOL stack ($6.5B US federal alone)** is the inverse signal. They've never been profitable enough to use any of it, and the indefinite carryforward means they don't lose it — but it's a permanent reminder of how deep the hole is.

4. **SNAP's "AI platform partner" agreement** is an unnamed counterparty that drove revenue growth in 2025. The redaction is the disclosure. (Likely OpenAI, Google, or Perplexity, given My AI's product positioning — but it's not named in the 10-K.)

5. **SNAP admitted in plain text that the 2023 ad-platform change broke customers.** "Disruptive to our customers and how some of them utilized our platform." 10-Ks rarely concede their own product errors.

6. **Robinhood Chain** is buried in growth strategy, but it's the sleeper. "Permissionless Layer 2 blockchain optimized for real-world assets, from public to private to global." A US retail broker operating its own L2 to tokenize private equity and global assets is a 2030 pitch in a 2025 filing.

7. **HOOD made up two metrics this cycle**: NCFA → Funded Customers, AUC → Total Platform Assets, and added "Investment Accounts" (because customers now have multiple accounts: brokerage, crypto, IRA, mortgage). The metric drift hides scale: the same customer is now ~6 accounts at HOOD.

8. **SNAP's Spectacles**, mentioned as "one of the best ways to create Memories" in FY17, is gone from primary product positioning by FY25. AR Spectacles for creators got one passing line. They never gave up on hardware, but they stopped selling it as the future.

9. **HOOD's two restructurings in FY22** are textbook private-tech-bust dynamics on a public company filing — the kind of disclosure most companies bury but Robinhood named: "April 2022 Restructuring," "August 2022 Restructuring," with exact percentages.

10. **The reverse-stock-split processing error** in Q4 2022 ($57M cost) is a beautifully boring kind of disclosure. Cosmos Health 1-for-25 reverse split, mishandled by Robinhood's brokerage system, $57M expense. It captures how operational fragility, not market direction, defined HOOD's near-death year.

---

## Edgarpack — usefulness, refresher

This third pass on the tool reinforces what was already true:

**Worked**: SNAP FY17 vs FY21 vs FY25 spans 8 years, three regulatory regimes (pre-Reg S-K modernization, post-DSA, post-AI), and two business model pivots. Reading three full 10-Ks would be ~400K tokens of inline-XBRL HTML soup. The packed sections + diff narrowed it to the changed paragraphs. SNAP's "AI platform partner" line, the $11.8B NOL stack, and the equity-dilution spiral admission are findings nobody hears in earnings calls — they live in the filing only.

**Worked again**: HOOD's three-year diff (43.3% intensity) lit up the new product surface immediately. Robinhood Chain, stablecoin balance, DTA release — all visible inside the changed-paragraphs view in <30 seconds of reading.

**Sectionizer drift, again, in two new flavors**:
- SNAP FY21 introduced a "summary of risk factors" preface that the sectionizer split into a separate `_1` ID. Result: Risk Factors looked like 98.6% rewritten + a brand-new section. Reality: same content, restructured.
- SNAP FY25 added Part-I/Part-II reorganizations that fragmented MD&A across `partii_item7_managements_discussion`, `partii_item7_managements_discussion_1`, and `partii_item7_item_7_managements_discussion`. The "real" MD&A is in the `_1` variant. Cost: ~3 minutes of mental normalization to figure out which file is canonical.

**Reaffirmed gap**: financial table rendering still mush. The HOOD revenue table comes through as `Transaction-based revenues / Transaction-based revenues / $ / 720 / $ / 1,402 / $ / 814` — nine repetitions of the row header per cell, no proper column alignment. Acceptable for narrative diff; useless for cross-year financial analysis without manual reconstruction.

**Surprise cost**: SNAP FY25 had ~50 added sections (94.3% intensity). Many were sectionizer artifacts. The intensity number overstates the actual disclosure change — should probably be deflated by an "alignment penalty" for how much new content is just relabeled old content.

**Surprise win**: harvesting an 8-year-old filing (SNAP FY17, accession 0001564590-18-002721) and getting it diff-ready in one command (`edgarpack build Snap --accession 0001564590-18-002721`) was clean. No friction, no manual EDGAR scraping.

---

## Thread material — candidate hooks

1. *"Robinhood quietly disclosed in their FY25 10-K that they hold $152M of stablecoin on their corporate balance sheet, listed as a liquidity source alongside cash and investments. First time. The language: 'cash flows generated from operations, and our cash, cash equivalents, investments, and stablecoin.'"*
2. *"In Q4 2024, Robinhood released the valuation allowance on their U.S. federal and state deferred tax assets — which means their auditors agreed it's more-likely-than-not that they'll be profitable enough to use them. The provision-for-income-taxes line moved by $572M. That's a stronger 'we're a real company now' signal than any earnings release."*
3. *"In their FY25 10-K, Robinhood disclosed Robinhood Chain: 'a permissionless Layer 2 blockchain optimized for real-world assets, from public to private to global.' They are no longer using crypto. They're operating one. Tokenization of real-world assets is now their #1 international growth strategy, in their own words."*
4. *"Three years ago, Robinhood ran two layoffs in eight months cutting 32% of staff, MAU fell 34%, and a single reverse-stock-split processing error cost $57M. Today they have $322B in platform assets, 4.18M Gold subscribers, and 2.5B in adjusted EBITDA. The 10-K diff between FY22 and FY25 shows you what survival actually looks like."*
5. *"Robinhood's product surface in FY25 has more new lines than the original FY22 filing had products. New regulated subsidiaries: RHEU (Lithuania, MiCA + MiFID licensed), TradePMR (RIA custodian, $40B+ AUM), Bitstamp (EU crypto exchange). New product lines: 24-hour market, short selling, index options, banking, credit card, wealth management, mortgage. They IPO'd as a stock app."*
6. *"Snap's FY25 10-K admits in plain text that their stock decline 'has required, and may continue to require, us to issue more equity to incentivize team members which is likely to dilute stockholders.' The dilution spiral, written into the risk factors. SNAP traded $6.90–$17.75 across 2024–2025."*
7. *"Snap has accumulated $6.5B in U.S. federal net operating losses, $4.4B in state, $4.9B in U.K., $420M in Singapore — plus $1B in U.S. federal R&D credits. Total ~$17B in tax assets. They've been operating long enough that the carryforwards are indefinite under post-2017 rules. They've never been profitable enough to use any of it."*
8. *"Snap's FY25 10-K mentions an 'AI platform partner' as a revenue source — but doesn't name them. The redaction is the disclosure. Whoever it is contributed materially enough to write into MD&A."*
9. *"Snap's FY17 10-K opened with 'Snap Inc. is a camera company.' Their FY25 10-K still says it, but the lead product description is a five-tab application stack. Spectacles, the centerpiece of the IPO, gets one passing line in FY25 — about overlaying AR onto the world for creators. The IPO pitch and the current product are different companies in the same skin."*
10. *"Both Snap and Robinhood IPO'd into chaos and were declared dead a year later. The 10-K diff across their post-IPO arc shows two recovery shapes: Snap reincarnated as a subscription company with an unnamed AI partner. Robinhood reincarnated as a global financial supermarket running its own blockchain. Neither prospectus predicted these."*
11. *"On the tooling: edgarpack let me diff three Snap 10-Ks across 8 years and two Robinhood 10-Ks across 3 years in roughly 90 seconds of compute. The findings — stablecoin on Robinhood's balance sheet, Snap's $17B unused tax asset stack, the unnamed AI partner, Robinhood Chain — are all single paragraphs in 100K-token filings. Without the diff, you don't see them. With it, they jump."*
