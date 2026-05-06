# Cerebras S-1 Diff: 2024 IPO vs 2026 Refile

*Drafted via Spiral (Tweet elite). Source: edgarpack diff between Cerebras Systems S-1 filings — original Sept 30, 2024 (`0001628280-24-041596`) vs April 17, 2026 refile (`0001628280-26-025762`).*

---

**1/** I diffed Cerebras's two S-1 filings. Original Sept 30, 2024 (0001628280-24-041596) vs April 17, 2026 refile (0001628280-26-025762).

81.9% change intensity. Normal 10-K diffs run 13-28%. This is a new prospectus wearing the same skeleton.

**2/** Revenue: $24.6M (FY22) → $78.7M (FY23) → $290.3M (FY24) → $510M (FY25).

6.5x in two years. The growth story got real while they sat on the sidelines.

**3/** The customer story flipped completely.

2024 S-1: "a significant majority of our revenue is generated from one customer headquartered in the United Arab Emirates."

That's G42. That's the CFIUS overhang that killed the original IPO.

**4/** 2026 S-1 names four customers for the first time: OpenAI, G42, MBZUAI, AWS. Top 10 customers grew aggregate spend ~80% within 12 months of initial purchase.

Single-customer risk became a real roster.

**5/** FY25 GAAP net income: +$237.8M (vs -$481.6M FY24). Looks incredible until you read the footnotes.

$363.3M positive "change in fair value (extinguishment) of forward contract liability," likely tied to the original G42 deal. Non-GAAP net loss: $75.7M. Still losing money.

**6/** The smoking gun sits at line 3017 of the diff.

December 2025: Cerebras issued the OpenAI Warrant. Right to buy 33,445,026 shares of Class N common stock at $0.00001 per share. Effectively free.

**7/** 4,459,337 shares vested January 2026 when Cerebras took a Working Capital Loan from OpenAI. 5,574,171 shares vest at the earlier of $40B market cap (30-day VWAP) or fee milestones. The rest ties to Master Reseller Agreement milestones.

**8/** Sit with that. OpenAI is simultaneously a named customer, an equity holder, and a creditor. The 2024 S-1 doesn't mention OpenAI once.

**9/** Class structure changed. 2024: two classes (Class A 1-vote, Class N non-voting). 2026: three classes. Class A 1-vote sold in the IPO. Class B with 20 votes per share for founders and insiders. Class N non-voting.

Existing Class A got reclassified into Class B before the IPO.

**10/** 20:1 supervoting is more aggressive than Meta or Google. They built it specifically for the public-market entry. Founders want the capital without the governance.

**11/** Mission rewrite tells you everything.

2024: "Our mission is to accelerate AI by making it faster, easier to use, and more energy efficient."

2026: "We are building the fastest AI infrastructure in the world. In AI, speed is critical to win."

From hedge-against-NVIDIA to beat-NVIDIA-head-on.

**12/** Hardware comparisons got specific. 2026 S-1: "The WSE-3 is 58 times larger than NVIDIA's B200 chip. The WSE has 19 times more transistors, 250 times more on-chip memory, and 2,625 times more memory bandwidth than NVIDIA's B200 package."

Exact-figure NVIDIA comparisons in an S-1 are unusual. They are leaning in.

**13/** Buyer thesis pivot: inference-time compute and AI coding agents.

The 2026 S-1 names competitor models: "OpenAI's GPT-5.4, Anthropic's Claude Opus 4.7, and Google's Gemini 3.1 Pro."

Names buyer apps: "Cursor, Claude Code, Codex, Windsurf, and GitHub Copilot."

**14/** "AI-native coding products barely existed in 2023. Yet they collectively generated billions in ARR in 2025."

That's the market Cerebras is underwriting now. Not training. Inference.

**15/** Material weakness disclosure carries forward unremediated. Selling stockholders disappeared. 2024 was secondary-friendly. 2026 is primary-only. Trading symbol CBRS on Nasdaq Global Select.

**16/** The thesis: Cerebras walked away from 2024 because of CFIUS pressure on G42 dependency. They waited until a different anchor showed up. OpenAI became that anchor. Customer, creditor, and equity holder all at once.

**17/** The S-1 diff makes the timeline visible. What changed, when, and at what cost. 81.9% of the filing is new text. At that point you're not amending a prospectus. You're confessing to a pivot.

---

## How this was made

Built with **edgarpack**, an open-source SEC filing parser that turns 10-Ks, 10-Qs, 8-Ks, and S-1s into deterministic markdown packs and runs section-aligned diffs across them.

Repo: https://github.com/samay58/edgarpack

The exact two commands behind this thread:

```bash
# Build the two prospectuses into structured packs
edgarpack build Cerebras --accession 0001628280-24-041596 --out ./packs
edgarpack build Cerebras --accession 0001628280-26-025762 --out ./packs

# Run the diff in full format
edgarpack diff \
  --before packs/0002021728/0001628280-24-041596 \
  --after  packs/0002021728/0001628280-26-025762 \
  --format full > crbs_s1.diff
```

The whole pipeline took about 90 seconds. Two prospectuses, hundreds of pages of EDGAR HTML, compressed into a single 3,047-line text diff with section-aligned change intensity. The OpenAI Warrant hides on line 3017.
