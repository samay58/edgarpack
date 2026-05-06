# Robinhood FY22 vs FY25 10-K

*Drafted via Spiral (Tweet elite). Source: edgarpack diff of HOOD FY22 (year after IPO) and FY25 10-Ks. Citations: 0001783879-23-000045 (FY22), 0001783879-26-000023 (FY25).*

---

**1/** I diffed Robinhood's FY22 10-K (year after IPO) against their FY25 10-K (filed Feb 2026). The gap between these two filings is one of the cleanest "what survival looks like" documents in public markets.

**2/** FY22 was the trough. Revenue $1.36B, down 25% YoY. Net loss $1.03B. Adj EBITDA negative $94M. MAU collapsed from 17.3M to 11.4M in a single year. AUC dropped from $98B to $62.2B. Gold subscribers slipped from 1.3M to 1.1M. Funded customers flat at 23.0M.

**3/** Two restructurings named explicitly in the filing. April 2022: 9% of staff, roughly 330 people. August 2022: 23%, roughly 780. Five additional office closures. The 10-K prints exact percentages and headcounts. Most companies hide layoffs behind "organizational realignment" language. Robinhood filed the receipts.

**4/** Then the $57M processing error. Cosmos Health did a 1-for-25 reverse stock split in Q4 2022. Robinhood's brokerage system mishandled it. The problem was not the market or a competitor. Their own plumbing almost sank the year. Operational fragility defined HOOD's near-death period more than any macro headwind.

**5/** FY25 reads like a different company. Funded Customers: 27.0M (+7%). Total Platform Assets: $322.1B (+67%). Net Deposits: $68.1B in FY25 alone. ARPU jumped to $171, up 40% from $122. Robinhood Gold: 4.18M subscribers, up 58% and nearly 4x the 1.1M trough. Adj EBITDA: $2.52B (+76%).

**6/** The accountant's tell is the most underrated line in the filing. Q4 2024, Robinhood released the valuation allowance on U.S. federal and state deferred tax assets. The provision-for-income-taxes line shifted $572M. That means auditors agree it's now more-likely-than-not Robinhood will generate enough profit to use those assets. Stronger signal than any earnings call.

**7/** First time: stablecoin on the corporate balance sheet. The FY25 10-K liquidity section reads "cash flows generated from operations, and our cash, cash equivalents, investments, and stablecoin." $152M held as corporate treasury. Not user custody. Their own balance sheet. A U.S. broker holding stablecoin as a corporate asset is new.

**8/** The sleeper. Robinhood Chain, described in the filing as "a permissionless Layer 2 blockchain optimized for real-world assets, from public to private to global." A U.S. retail brokerage operating its own L2. That sentence sits in a 10-K filed with the SEC.

**9/** Product line built since IPO: Robinhood Banking (BaaS, partner Coastal Bank). Credit card (Coastal Bank issuer). Robinhood Strategies (managed wealth, 0.25% fee, $250/yr cap for Gold). TradePMR acquisition for RIA custodial. Bitstamp acquisition for EU crypto. 24-hour market trading, first U.S. broker to do it. Short selling launched Q4 2025. Index options 2025. Legend desktop platform. Mortgage rates exclusive to Gold.

**10/** International footprint built from zero. RHEU in Lithuania holds MiCA + MiFID licenses. Stock tokens trading and multi-currency accounts across the EU. UK ISAs. Singapore APAC office. 58 supported cryptocurrencies. Three years from U.S.-only stock app to multi-continent financial platform.

**11/** The metric drift tells its own story. NCFA became Funded Customers. AUC became Total Platform Assets. A new metric appeared: Investment Accounts (28.4M). One person now holds brokerage, crypto, IRA, mortgage, and banking accounts. Same customer, roughly six accounts. When companies rename their KPIs, they're telling you the business model changed.

**12/** Overall diff intensity between filings: 43.3%. Lower than you'd expect given the scale of transformation. The 10-K skeleton was already mature by FY22. Change came through additions, not rewrites. Robinhood didn't rebuild the company. They bolted a new one onto the old frame. The frame held.

---

## How this was made

Built with **edgarpack**, an open-source SEC filing parser that turns 10-Ks, 10-Qs, 8-Ks, and S-1s into deterministic markdown packs and runs section-aligned diffs across them.

Repo: https://github.com/samay58/edgarpack

The two commands behind this thread:

```bash
# Build Robinhood's FY22 (year-after-IPO) and FY25 (today) 10-Ks
edgarpack build 0001783879 --accession 0001783879-23-000045 --out ./packs
edgarpack build 0001783879 --accession 0001783879-26-000023 --out ./packs

# Diff across the arc
edgarpack diff \
  --before packs/0001783879/0001783879-23-000045 \
  --after  packs/0001783879/0001783879-26-000023 \
  --format full > hood_22_25.diff
```

Two 10-Ks compressed into section-aligned markdown packs in seconds. The DTA valuation release, the $152M stablecoin treasury, Robinhood Chain — all single paragraphs deep inside the filing. The tool didn't make the findings. It made them findable.
