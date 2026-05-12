# Lime S-1 Thread: The Micromobility Business Finally Has Numbers

*Source: EdgarPack analysis of Neutron Holdings, Inc. S-1 filed May 8, 2026, accession `0001628280-26-032523`, CIK `0001699963`. Web search was used only to sanity-check news context. The claims below come from the filing pack.*

---

1/ Lime filed its S-1 under Neutron Holdings. Proposed Nasdaq ticker: `LIME`.

This is not just a scooter-company comeback story. It is a city-permit, fleet-utilization, working-capital, and Uber-dependency story in one filing.

2/ The business is larger than the category reputation suggests.

As of Dec. 31, 2025: approximately 230 cities, 29 countries, 19 million riders, and the company calls itself the largest global shared micromobility business.

3/ Revenue grew from $522.0M in 2023 to $686.6M in 2024 to $886.7M in 2025.

Gross profit went $169.2M to $281.1M to $345.4M. Operating income went from a $24.6M loss in 2023 to $47.0M profit in 2024 and $70.4M profit in 2025.

The operating business is no longer obviously broken.

4/ GAAP net income still does not clear.

Net loss was $122.4M in 2023, $33.9M in 2024, and $59.3M in 2025. The company crossed into operating profit, then lost money below the line through interest expense and other expense.

The business improved before the capital structure did.

5/ Adjusted EBITDA looks strong: $99.8M in 2023, $153.4M in 2024, $218.1M in 2025.

But this is not software. Depreciation is not a rounding error when the product is a fleet of vehicles sitting outside in cities. The right follow-up is capex, useful life, repairs, and vehicle payback.

6/ The filing's own free cash flow reconciliation is the cleaner source: $1.1M in 2023, $47.3M in 2024, $103.8M in 2025.

That is the strongest number in the S-1. The company is not just adjusting itself into EBITDA. Full-year free cash flow is positive.

7/ Q1 tells the other half of the story.

Q1 2026 revenue was $170.2M, up 32% year over year. Adjusted EBITDA was $7.5M, up from $2.1M. But free cash flow was negative $79.2M because bad weather hits demand while many costs stay fixed and vehicle capex is front-loaded.

The business has real seasonality. Annual numbers are easier to like than March-quarter cash flow.

8/ The operating formula is simple and useful:

Average operational fleet up 18% in 2025. MAU up 21%. Revenue per vehicle per day up 10%.

More vehicles, more riders, more revenue per vehicle. That is the whole operating thesis.

9/ Lime claims each vehicle is an underwritable asset now.

2025 blended average fully landed vehicle cost was about $1,300, including batteries, shipping, insurance, customs duties, tariffs, and taxes. ROI payback period was about twelve months.

If true, this is the difference between "shared scooters are vandalized hardware" and "shared scooters are a short-payback fleet asset."

10/ The mix is also shifting.

LimePass and LimePrime were 14% of revenue in 2023, 20% in 2024, and 28% in 2025. Pay-as-you-go fell from 86% to 72% over the same period.

The scooter business is trying to become a repeat-use pricing business.

11/ Uber is the most important non-financial financial statement item.

Uber channel revenue was 14.1% of revenue in 2023, 15.8% in 2024, 14.3% in 2025, and 14.0% in Q1 2026. Lime vehicles show up inside Uber's app in nearly all shared markets.

Uber is distribution. It is also much more than distribution.

12/ Uber holds more than 5% of Lime, has an $85.0M 2020 note, has a $50.0M 2021 note, and guarantees up to $125.0M of Lime's senior secured term loan.

There is also a staged two-year Uber lock-up tied to the integration agreement.

This is a platform partnership, an investor relationship, a creditor relationship, and a backstop.

13/ The balance sheet is the urgency.

As of March 31, 2026, Lime had $261.3M of cash and equivalents and negative $529.0M of working capital. The filing says principal payments on convertible notes and the term loan of approximately $845.8M are due within twelve months, and that Lime does not currently have sufficient liquidity to repay them.

That is the loudest sentence in the S-1.

14/ Use of proceeds makes the point.

The company says net proceeds will repay all outstanding indebtedness under the senior secured term loan. That loan matures in September 2026 and carries a 10% fixed rate.

This IPO is not just growth capital. It is a balance-sheet event.

15/ The market-share claim is good, with a caveat.

For 2025, Lime says it had 27% share across docked and dockless operators in countries where it operated, 37% in the U.S., 35% share among dockless operators globally, and 48% dockless share in the U.S.

The caveat: Lime calculates this primarily using Sensor Tower monthly active app users, supplemented with public and internal data. Directionally useful, but not a clean third-party market-share table.

16/ The city moat matters more than the app.

Lime disclosed 116% operational fleet retention in 2025 and 48 exclusive fleet-cap increases that year, averaging 532 more vehicles per city.

For this business, the moat is not only consumer UX. It is permits, fleet caps, local operations, and city trust.

17/ The read:

Lime is not Bird. It has real revenue scale, positive operating income, positive full-year free cash flow, high adjusted gross margins, and a credible operating KPI stack.

It is also not a clean software IPO. Weather, permits, vehicles, insurance, tariffs, debt maturity, and Uber all matter.

18/ The S-1 reads like a company that finally made micromobility work at scale, but only after becoming a fleet-finance, city-government, and Uber-platform hybrid.

The IPO looks less like "we need money to prove the model" and more like "the model finally works, but the balance sheet needs the public market."

---

## How this was made

Built with EdgarPack from the primary S-1, then checked against the generated section markdown.

Core commands:

```bash
uv run edgarpack identify "Neutron Holdings"
uv run edgarpack list "Neutron Holdings" --form S-1 --limit 10
uv run edgarpack build "Neutron Holdings" \
  --accession 0001628280-26-032523 \
  --with-chunks \
  --out ./packs
uv run edgarpack doctor packs/0001699963/0001628280-26-032523 --format json
```

Financial extraction:

```bash
uv run edgarpack query "Neutron Holdings" \
  revenue,gross_profit,operating_income,net_income,adjusted_ebitda \
  --period lfy,lfy-1,lfy-2 \
  --show-links primary

uv run edgarpack query "Neutron Holdings" \
  capex,free_cash_flow,operating_cash_flow \
  --period lfy,lfy-1,lfy-2 \
  --format json-full \
  --audit
```

KPI discovery and filing search:

```bash
uv run edgarpack which "Neutron Holdings" --format json --max-periods 8
uv run edgarpack search "Uber Integration Agreement" --limit 5
uv run edgarpack search "going concern substantial doubt" --limit 5
uv run edgarpack search "LimePass LimePrime" --limit 5
uv run edgarpack search "operational fleet retention rate" --limit 5
uv run edgarpack search "ROI Payback Period" --limit 5
```

Section files that carried the thread:

```text
packs/0001699963/0001628280-26-032523/sections/s1_itemother_prospectus_summary.md
packs/0001699963/0001628280-26-032523/sections/s1_itemother_summary_consolidated.md
packs/0001699963/0001628280-26-032523/sections/s1_itemother_managements_discussion.md
packs/0001699963/0001628280-26-032523/sections/s1_itemother_certain_relationships.md
packs/0001699963/0001628280-26-032523/sections/s1_itemother_use_of_proceeds.md
packs/0001699963/0001628280-26-032523/sections/s1_itemother_business.md
```

Tooling notes:

- `identify`, `list`, `build`, and `doctor` worked cleanly for the fresh S-1.
- `query` worked well for revenue, gross profit, operating income, net loss, adjusted EBITDA, operating cash flow, and many margin calculations.
- I did not use the `query` free-cash-flow value in the thread. EdgarPack pulled FY2025 capex as $56.9M, which appears to be the Q1 2026 capex value. The filing's own reconciliation says FY2025 capex was $111.1M and free cash flow was $103.8M. I used the filing reconciliation.
- The `mrq` period selector returned `N/A` for Q1 financials, so Q1 revenue, adjusted EBITDA, and free cash flow were pulled from the S-1 summary and MD&A sections.
- `which --format json` was useful for extracting operating KPIs: cities, countries, riders, MAU growth, RVD growth, fleet growth, market share, Uber revenue share, and LimePass/LimePrime mix.
- `edgarpack search` was useful for jumping to Uber, going-concern, LimePass, operational fleet retention, and ROI payback sections. One search query on vehicle depreciation hit an index-schema error, so I validated that topic directly from the generated section markdown.
