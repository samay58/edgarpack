# NVIDIA 10-K Diff Thread (FY24 → FY26)

*Drafted via Spiral (Tweet elite). Source: edgarpack diff of NVIDIA's last three 10-Ks. CIK 0001045810. Accessions 0001045810-24-000029 (FY24), 0001045810-25-000023 (FY25), 0001045810-26-000021 (FY26).*

---

**1/** I diffed NVIDIA's last three 10-Ks (FY24, FY25, FY26) using edgarpack. Filing-to-filing change intensity: 22.4% (FY24 – FY25), then 13.2% (FY25 – FY26). The story is stabilizing even as financial scale tripled. What changed in the text tells you more than what changed on the income statement.

**2/** Customer concentration nearly doubled. FY24: one customer at 13% of revenue. FY25: three customers at 12%, 11%, 11%. FY26: one direct customer at 22%, a second at 14%. On $215.9B in FY26 revenue, that top customer represents roughly $47B from a single counterparty.

**3/** NVIDIA noticed. FY26 introduced a brand-new top-tier risk factor: counterparty risk. Exact language: "Commercial arrangements expose us to counterparty risks, which may negatively impact our business, financial condition, or results of operations." Old FY25 bullets about customer bankruptcy and credit risk got rolled into one named bucket. They're worried about concentration and they said so.

**4/** The OpenAI tell. FY26 MD&A: "one AI research and deployment company contributed to a meaningful amount of our revenue purchasing cloud services from our customers in fiscal year 2026." Not named. Indirect revenue. NVIDIA disclosed that a company it doesn't even directly sell to moves enough volume through cloud intermediaries to warrant a callout in the filing.

**5/** The $4.5B H20 inventory charge, disclosed in FY26 Q1. Real dollar cost of China export restrictions, finally booked. Gross margin went 75.0% to 71.1% in one year. That's not rounding error. That's policy risk hitting the P&L.

**6/** Cumulative R&D since inception went from $58.2B to $76.7B in one year. Roughly $18.5B in FY26 alone. NVIDIA spends more on R&D annually than most semiconductor companies are worth.

**7/** Self-description shifted. "Full-stack computing infrastructure company" became "data center scale AI infrastructure company." Narrower scope, higher conviction. They stopped pretending to be a general-purpose platform and started saying what they actually are.

**8/** New customer categories appeared in FY26: "AI model makers" and "Neocloud builders." Coreweave and OpenAI described by class, not by name. The old taxonomies couldn't describe who's buying anymore, so NVIDIA invented new ones.

**9/** Dropped from segment descriptions: DGX Cloud, Jetson, GeForce NOW, vGPU, Omniverse Enterprise. Not necessarily discontinued. Just no longer important enough to name in the 10-K. The filing tells you what the company thinks matters. These didn't make the cut.

**10/** Sales pitch reframed. "Performance and power efficiency" became "total cost of ownership." That's a CFO sales motion, not an engineer sales motion. NVIDIA is selling to the person who signs the check now, not the person who racks the server.

**11/** NVLink Fusion introduced in FY26. Lets hyperscalers plug their own CPUs and custom ASICs into NVIDIA's interconnect fabric. This is the hedge against custom silicon, written directly into the 10-K. Can't beat the trend? Absorb it into your platform.

**12/** Rubin announced for H2 FY27, claiming "10x reduction in cost per token compared to Blackwell." If that number holds, it resets inference economics entirely. Big if.

**13/** Geographic methodology completely rewritten. International revenue restated by customer HQ location: FY25 = 41%, FY26 = 31%. The old method had FY25 at 53%. Same underlying sales. Different framing. The restatement alone swung international revenue by 12 points.

**14/** Top500 supercomputer share crept from 75% to 78%. Green500 dominance went from 38-of-top-50 to 9-of-top-10. Apps supported: 3,500 (FY24) → 4,400 (FY25) → 6,000 (FY26). 10-for-1 stock split disclosed in FY25 (June 2024).

**15/** Three-year arc: filings stabilizing as the story matures. Change intensity fell 22.4% to 13.2%. Revenue tripled. Customer concentration spiked. Risk factors got more specific, more honest. NVIDIA's 10-K reads less like a growth story now and more like a franchise narrowing around fewer, larger AI customers. That's not a criticism. It's the most interesting thing in the filing.

---

## How this was made

Built with **edgarpack**, an open-source SEC filing parser that turns 10-Ks, 10-Qs, 8-Ks, and S-1s into deterministic markdown packs and runs section-aligned diffs across them.

Repo: https://github.com/samay58/edgarpack

The two commands that produced this thread:

```bash
# Build NVIDIA's last three 10-Ks
edgarpack build NVDA --form 10-K --last 3 --out ./packs

# Diff FY25 → FY26 in full format
edgarpack diff \
  --before packs/0001045810/0001045810-25-000023 \
  --after  packs/0001045810/0001045810-26-000021 \
  --format full > nvda_25_26.diff
```

A 100K-token 10-K becomes a section-aligned markdown pack in seconds, and the diff narrows the comparison to changed paragraphs only. The H20 charge, the counterparty-risk addition, the OpenAI tell — all single paragraphs you'd never find scrolling raw EDGAR.
