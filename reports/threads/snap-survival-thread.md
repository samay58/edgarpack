# Snap — How They Survived a Decade of GAAP Losses

*Drafted via Spiral (Tweet elite style). Source: edgarpack diffs of SNAP FY17, FY21, FY25 10-Ks. Citations: 0001564590-18-002721, 0001564590-22-003868, 0001564408-26-000013.*

---

**1/** Snap has reported a GAAP loss every year since IPO. Nine years. And the cash pile barely moves: $987M (2016), $2.04B (2017), $3.7B (2021), $3.3B (2024), $2.9B (2025). They've held a $2-3.7B band for nine straight years. This is how.

**2/** Most of the "loss" was never cash. FY17 showed a $3.4B GAAP loss. Looks fatal. But $2.6B of it was stock-based comp, headlined by a $636.6M CEO award (37.4M shares vested at the $17 IPO price, immediately on close). Actual cash burn: $734.7M operating + $84.5M capex = $819M FCF. They paid engineers in equity. Dilutes shareholders, not the bank account.

**3/** That comp expense piled into $17B of net operating losses Snap has never been profitable enough to use. Seventeen billion in paper losses on the books, waiting for a tax bill that hasn't come.

**4/** The IPO kept them alive. $3.4B net at $17/share, March 2017. Without that cash, Snap runs out by year-end.

**5/** Then came the convertible note machine. Stock-linked debt at near-zero coupons, six rounds:

- Aug 2019: $1.265B of 2026 Notes at 0.75%, $1.15B net
- Apr 2020: $1.0B of 2025 Notes at 0.25%, $888.6M net (during COVID)
- Apr 2021: $1.15B of 2027 Notes at 0% (zero-coupon convertible), $1.05B net
- Feb 2022: $1.5B of 2028 Notes at 0.125%, $1.31B net
- May 2024: $750M of 2030 Notes at 0.50%, $671.5M net
- 2025: 2033 + 2034 Notes for $2.0B net (refinancing)

About $6B of net proceeds at sub-1% coupons.

**6/** A company that has never turned a GAAP profit borrowed $6B at basically zero interest. The mechanism is convert-arb. Each issuance paired with a capped call: Snap spends $60-100M buying options to hedge dilution if the stock rallies. Hedge fund desks take the equity option. The coupon is a rounding error. The real product being sold is optionality on the stock.

**7/** Operating cash flow went positive in 2021. $292.9M operating, $223M FCF. The business started paying for itself.

**8/** By FY25, Snap flipped the whole dynamic. In one year: $2.0B of old convertible notes repurchased, $750.9M of stock bought back, matured 2025 Notes retired ($36.2M). Three $500M buyback programs since Oct 2023, all completed. Feb 2026: another $500M authorized. The company that survived on dilution started un-diluting.

**9/** Debt today: $3.5B principal, maturities laddered 2026 through 2034. Short-term interest $149.3M, long-term $967.9M. Easy to carry on $2.9B liquidity plus positive cash flow.

**10/** The full picture: equity holders funded the losses through roughly $2.6B/year of SBC dilution. The debt market funded working capital through convert-arb hedge funds buying near-zero-coupon notes for the equity option. The actual cash needed to run the business, once you strip SBC, was small and shrinking. IPO plus converts covered it.

**11/** Buried in the FY25 10-K risk factors is the admission. Snap wrote the dilution spiral into their own filing: low stock price means more shares to pay the same engineer, more shares dilutes further, price drops more. They see the loop. They disclosed it. They keep issuing.

---

## How this was made

Built with **edgarpack**, an open-source SEC filing parser that turns 10-Ks, 10-Qs, 8-Ks, and S-1s into deterministic markdown packs and runs section-aligned diffs across them.

Repo: https://github.com/samay58/edgarpack

The two commands behind this thread:

```bash
# Build Snap's three reference 10-Ks (FY17 year-after-IPO, FY21 mid, FY25 today)
edgarpack build Snap --accession 0001564590-18-002721 --out ./packs
edgarpack build Snap --accession 0001564590-22-003868 --out ./packs
edgarpack build Snap --accession 0001564408-26-000013 --out ./packs

# Diff across the arc
edgarpack diff \
  --before packs/0001564408/0001564590-18-002721 \
  --after  packs/0001564408/0001564590-22-003868 \
  --format full > snap_17_21.diff
```

Three 100K-token 10-Ks compressed into section-aligned markdown packs in seconds. The convertible-note ladder, the \$17B NOL stack, the dilution-spiral admission, the unnamed AI partner — all paragraphs you'd never spot scrolling raw EDGAR. The tool didn't make the findings. It made them findable.

*Spiral session: https://app.writewithspiral.com/chat/e8182eb7-503e-4f02-8098-247c2db4e0d3*
