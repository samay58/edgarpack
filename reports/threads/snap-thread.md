# SNAP 10-K Arc: FY17 → FY21 → FY25

*Drafted via Spiral (Tweet elite). Source: edgarpack diffs of SNAP across 8 years. Citations: 0001564590-18-002721 (FY17), 0001564590-22-003868 (FY21), 0001564408-26-000013 (FY25).*

---

**1/** I diffed Snap's 10-Ks across an 8-year arc. FY17 (filed Feb 2018) vs FY21 (filed Feb 2022) vs FY25 (filed Feb 2026).

Three filings. Three different companies wearing the same ticker.

**2/** FY17 opens with a manifesto. "Snap Inc. is a camera company." 187M DAUs. $824M revenue. $3.4B net loss. $4.7B accumulated deficit. 3,069 employees in Venice, CA.

Spiegel and Murphy held 94.6% of voting power through Class C shares. The 10-K reads like an essay, not a filing.

**3/** FY21 still calls itself a camera company. 319M DAUs (+71%). Revenue hit $4.1B, a 5x in four years. Net loss narrowed to $488M. HQ moved to Santa Monica, headcount grew to 5,661.

Snapchat+ subscription disclosed as launching 2022. First time they bothered mentioning carbon neutrality. Growth was real. The identity hadn't cracked yet.

**4/** FY25 is where it breaks.

474M DAUs, but that's only +5% YoY. Growth flatlined. Revenue $5.93B, just 1.4x over four years after doing 5x the prior four. Net loss narrowed to $460M.

The pitch isn't "reinvent the camera" anymore.

**5/** In their own words: "Snapchat+, Lens+, and Snapchat Platinum, our subscription services." Platinum is the new ad-free tier. Other revenue grew $287.6M YoY in FY25, "predominantly due to higher subscription revenue."

This is a subscription company now. The press hasn't fully clocked it.

**6/** FY25 MD&A references "an agreement with our AI platform partner." Not named. Drove enough revenue to warrant a callout in MD&A.

Snap chose to mask the name in a public SEC filing. The redaction is the disclosure.

**7/** A rare admission for a 10-K: "in January 2023, we made changes to our advertising platform to lay the foundation for future growth, but which have been disruptive to our customers and how some of them utilized our platform."

Companies almost never write that sentence. Snap filed it with the SEC.

**8/** Snap sits on ~$17B in tax assets. $6.5B in U.S. federal NOLs. $4.4B state. $4.9B U.K. $420M Singapore. Plus $1.0B in federal R&D credits and $574.8M state credits. All with indefinite carryforward.

They've never been profitable enough to use any of it.

**9/** Snap wrote the dilution spiral into its own risk factors. FY25: "From January 1, 2024 to December 31, 2025, the trading price of our Class A common stock ranged from $6.90 to $17.75."

Stock declines "have required, and may continue to require, us to issue more equity to incentivize team members." They're telling you dilution is structural.

**10/** What disappeared tells you where they're headed. Spectacles, the IPO-era centerpiece, gets one passing line in FY25 about overlaying AR for creators. The five-tabs-of-Snapchat framing replaced 2017's "the camera screen is the starting point."

Same company, different skeleton.

**11/** The vocabulary shift is the strategy shift. 2024 restructuring language: "drive toward profitability and positive free cash flow."

Compare that to FY17's "we invest heavily and take big risks."

**12/** Run the diff. FY17 – FY21: 71.9% of the filing changed. FY21 – FY25: 94.3%.

The four-year gap from 2021 to 2025 rewrote more of Snap's 10-K than the entire IPO-to-2021 maturation did. Subscription pivot. SOX-era restructuring. New risk factor architecture.

Snap didn't evolve. It molted.

---

## How this was made

Built with **edgarpack**, an open-source SEC filing parser that turns 10-Ks, 10-Qs, 8-Ks, and S-1s into deterministic markdown packs and runs section-aligned diffs across them.

Repo: https://github.com/samay58/edgarpack

The two commands behind this thread:

```bash
# Build the three reference Snap 10-Ks (year-after-IPO, mid-life, today)
edgarpack build Snap --accession 0001564590-18-002721 --out ./packs
edgarpack build Snap --accession 0001564590-22-003868 --out ./packs
edgarpack build Snap --accession 0001564408-26-000013 --out ./packs

# Diff across the arc
edgarpack diff \
  --before packs/0001564408/0001564590-18-002721 \
  --after  packs/0001564408/0001564590-22-003868 \
  --format full > snap_17_21.diff

edgarpack diff \
  --before packs/0001564408/0001564590-22-003868 \
  --after  packs/0001564408/0001564408-26-000013 \
  --format full > snap_21_25.diff
```

Three 10-Ks compressed into section-aligned markdown packs in seconds. The "AI platform partner" line, the dilution-spiral admission, the $17B unused NOL stack — all single paragraphs deep inside hundred-page filings. The diff narrows the comparison to changed text only. The tool didn't make the findings. It made them findable.
