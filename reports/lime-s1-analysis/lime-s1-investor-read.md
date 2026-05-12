# Neutron Holdings / Lime S-1 Investor Read

Source spine: Neutron Holdings, Inc. S-1 filed May 8, 2026, accession `0001628280-26-032523`, CIK `0001699963`. EdgarPack pack: `packs/0001699963/0001628280-26-032523/`.

External search was used only for market context around the proposed IPO and reported valuation. The operating and financial conclusions below come from the S-1 pack unless marked otherwise.

## The Read

Lime is more interesting than the old scooter-company caricature. The S-1 shows a business that has reached real scale, crossed into operating income, and produced positive full-year free cash flow. It also shows a company going public with a balance sheet problem, a weather-shaped cash flow profile, and a relationship with Uber that is part distribution channel, part lender, part shareholder, and part strategic constraint.

The useful way to underwrite Lime is not as software and not as pure transportation hardware. It is a dense local operations business. The core question is whether Lime can keep increasing revenue per vehicle per day, win larger fleet caps in existing cities, and refresh vehicles without letting capex, repairs, insurance, theft, or regulation take back the margin improvement.

On the positive side, the S-1 answers the most basic question investors had after Bird: can shared micromobility work at public-company scale? Lime has a better answer than the category reputation suggests. Revenue grew from $522.0 million in 2023 to $886.7 million in 2025. Operating income moved from a $24.6 million loss to $70.4 million of profit. Adjusted EBITDA reached $218.1 million. Full-year free cash flow reached $103.8 million.

The harder answer is that the IPO is not only a growth event. It is also a refinancing event. The filing says Lime had $261.3 million of unrestricted cash at March 31, 2026 and $845.8 million of convertible note and term-loan principal payments due within twelve months from issuance of the Q1 statements. The filing also says Lime does not currently have enough liquidity to repay them. That is the most important sentence in the prospectus.

## What The Numbers Say

| Metric | 2023 | 2024 | 2025 | Read |
| --- | ---: | ---: | ---: | --- |
| Revenue | $522.0M | $686.6M | $886.7M | 30% two-year CAGR. Scale is no longer hypothetical. |
| Gross profit | $169.2M | $281.1M | $345.4M | Gross margin rose sharply in 2024, then slipped in 2025. |
| Gross margin | 32.4% | 40.9% | 39.0% | Stronger than expected for shared vehicles, but not structurally clean. |
| Operating income | ($24.6M) | $47.0M | $70.4M | The operating model has crossed over. |
| Net income | ($122.4M) | ($33.9M) | ($59.3M) | Below-the-line items still matter. |
| Adjusted EBITDA | $99.8M | $153.4M | $218.1M | 24.6% adjusted EBITDA margin in 2025. |
| Filing-defined free cash flow | $1.1M | $47.3M | $103.8M | The strongest headline metric, but read the capex note. |

Sources: summary financial data and MD&A, especially `s1_itemother_prospectus_summary.md:41-43`, `s1_itemother_summary_consolidated.md:113-125`, and `s1_itemother_managements_discussion.md:368-384`.

The free cash flow line is the cleanest proof that the model changed, but the quality of that proof matters. 2025 free cash flow improved partly because operating cash flow increased by $46 million. Lime also says cash outflow for capex was lower because vehicle supplier payment terms changed. Purchases were secured by letters of credit rather than upfront deposits. That does not invalidate the free cash flow number, but it makes the next diligence question obvious: how much of the improvement is repeatable operating performance versus working capital timing?

EdgarPack's computed free cash flow was not reliable here. The command-line query used $56.9 million of capex for FY2025, which appears to be the Q1 2026 capex number. The filing reconciliation says FY2025 capex was $111.1 million and free cash flow was $103.8 million. I used the filing reconciliation.

## The Operating Formula

Lime's operating story is unusually crisp:

| Operating metric | 2023 | 2024 | 2025 |
| --- | ---: | ---: | ---: |
| Average operational fleet | 229,405 | 275,983 | 325,137 |
| Revenue per vehicle per day | $6.23 | $6.80 | $7.47 |
| Monthly active users | 2.639M | 3.127M | 3.794M |

In 2025, fleet grew 18%, MAU grew 21%, and RVD grew 10%. That is a strong combination for an asset-heavy consumer service. The company did not grow only by adding more vehicles. It also earned more per vehicle per day.

This is the best evidence that Lime's scale is doing something useful. A larger fleet in the right cities improves availability. Better availability increases rider confidence. More usage improves revenue per vehicle. Higher RVD shortens payback and supports more fleet. If that loop holds, Lime can grow inside existing cities without needing every new geography to work immediately.

The risk is that this loop is local, not universal. RVD depends on weather, density, local regulation, tourist flows, commuting patterns, theft, charging, repair labor, and permit rules. Lime says its top two RVD cities in 2025 generated roughly three times the company average. That is encouraging, but it also means average results hide major city-by-city variance.

Sources: `s1_itemother_managements_discussion.md:123-124`, `s1_itemother_managements_discussion.md:231-250`, and `s1_itemother_managements_discussion.md:256-258`.

## The Vehicle Payback Claim

The most investor-relevant sentence in the operating section is the vehicle payback claim. Lime says its 2025 blended average fully landed vehicle cost was about $1,300, including batteries, shipping, insurance, customs duties, tariffs, and taxes. It also says ROI payback was about twelve months, calculated from annualized RVD multiplied by adjusted gross margin.

That is the difference between a messy scooter fleet and an underwritable fleet asset. If a vehicle pays back in roughly a year and has a multi-year useful life, the economics can work even with real depreciation and replacement needs. But this claim deserves pressure testing:

- What percentage of vehicles actually reach the assumed useful life?
- How much does payback vary by market?
- How sensitive is payback to tariffs and battery costs?
- How much of the RVD improvement came from pricing rather than utilization?
- What loss, theft, and vandalism assumptions are embedded in the fleet math?

The S-1 gives evidence that the company is managing the hard parts better. Maintenance capex averaged 5% of revenue over 2024 and 2025. Lime also says vehicle durability, charging schedules, battery locking, and software changes have improved maintenance capex efficiency. That is more concrete than a generic operating leverage story.

Source: `s1_itemother_managements_discussion.md:123-124`.

## Seasonality Is Not A Footnote

The quarter data changes the tone. Q1 2026 revenue grew 32% year over year to $170.2 million. Gross profit grew 54%. Adjusted EBITDA improved from $2.1 million to $7.5 million. Yet free cash flow was negative $79.2 million.

This is not a contradiction. It is the business model. Lime says rider activity is higher in the second and third quarters and lower in the first and fourth quarters. It also says many costs remain fixed and capex is concentrated in the first part of the year because of manufacturing lead times.

Public investors should not judge this company on one March quarter. They also should not ignore what Q1 reveals. Lime can show revenue growth and still burn cash in cold and wet periods. The annual free cash flow number is real, but the intra-year liquidity need is real too. That matters more when the company is carrying near-term debt maturity pressure.

Sources: `s1_itemother_prospectus_summary.md:42`, `s1_itemother_managements_discussion.md:285-287`, and `s1_itemother_managements_discussion.md:379-384`.

## The IPO Is Also A Balance Sheet Repair

The balance sheet is the clearest risk in the S-1.

At March 31, 2026, Lime disclosed:

- $261.3 million of unrestricted cash and equivalents.
- $82.6 million of restricted cash.
- $821.1 million of outstanding indebtedness principal, including PIK interest.
- $845.8 million of future principal payments on convertible notes and term loan due within twelve months from issuance of the Q1 statements.
- A going-concern warning tied to the IPO or alternative financing.

Use of proceeds confirms the point. Lime intends to use IPO proceeds to repay all outstanding debt under the senior secured term loan. That loan matures in September 2026 and bears 10% interest.

The investment implication is straightforward: the company has earned the right to talk about operating quality, but the stock will be priced through the cleanup of old financing decisions. The 2021 notes convert at the lesser of 80% of the IPO price or a $1.5 billion valuation cap divided by fully diluted shares. The old capital stack matters to new shareholders.

Sources: `s1_itemother_risk_factors.md:566-577`, `s1_itemother_risk_factors.md:659-661`, `s1_itemother_use_of_proceeds.md:12`, `s1_itemother_description_of_securities.md:63-67`, and `s1_itemother_index_to_consolidated.md:1738`.

## Uber Is The Central Counterparty

Uber is not just a name on the cap table.

The S-1 shows Uber as:

- A go-to-market channel. Uber app revenue was about 14% to 16% of revenue from 2023 through Q1 2026.
- A shareholder with more than 5% ownership.
- Holder of an $85.0 million 2020 note.
- Holder of a $50.0 million 2021 note, excluding PIK interest.
- Guarantor for up to $125.0 million of Lime's senior secured term loan.
- A lock-up counterparty with staggered restrictions over two years, but the lock-up can terminate if the Uber integration agreement terminates.

The good version is that Lime has privileged distribution through a huge mobility app, and Uber has enough economic exposure to care. The bad version is that one company sits across distribution, financing, ownership, governance history, and post-IPO supply. If Uber reduces visibility, changes terms, pushes competing options, or exits after restrictions lift, the effect is not isolated.

The agreement runs through 2028 after a May 2025 renewal, but Uber has unilateral termination rights in some circumstances. That is worth more diligence than a standard "channel partner" footnote.

Sources: `s1_itemother_prospectus_summary.md:28`, `s1_itemother_risk_factors.md:289-295`, and `s1_itemother_certain_relationships.md:19-47`.

## The City-Level Business Is The Real Business

Lime's strongest strategic evidence is not app downloads. It is the operating record with cities.

The company operates in about 230 cities across 29 countries. It says deepening existing cities should be a bigger growth source than entering new ones. In 2025, operational fleet retention was 116%, meaning established cities grew fleet year over year. Lime also disclosed 48 exclusive fleet-cap increases in 2025, with an average increase of 532 vehicles per city.

That is not a normal consumer app growth lever. It means local authorities are allowing Lime to put more vehicles in the places where it already operates. If fleet density drives availability, and availability drives MAU and RVD, then city trust is an input into revenue growth.

This is also why the risk profile is local and political. Permits, fleet caps, operating zones, data sharing rules, parking rules, road infrastructure, public safety, and enforcement shape the business. Lime's advantage is not simply that riders know the brand. It is that cities keep letting Lime expand its physical footprint.

Sources: `s1_itemother_prospectus_summary.md:105`, `s1_itemother_business.md:204`, `s1_itemother_business.md:503`, and `s1_itemother_managements_discussion.md:271`.

## The Pricing Mix Is Quietly Important

Lime is trying to make more revenue come from repeat behavior rather than one-off rides.

Pay-as-you-go fell from 86% of revenue in 2023 to 80% in 2024 and 72% in 2025. LimePass and LimePrime rose from 14% to 20% to 28%. Minute bundle riders took about six times as many trips as pay-as-you-go riders, based on the filing's own definition.

This is not recurring revenue in the software sense. It is still short-duration mobility demand, exposed to weather and local availability. But it does show that Lime has a way to convert casual riders into routine riders. It also gives management a pricing lever that is more subtle than changing unlock fees.

Sources: `s1_itemother_managements_discussion.md:76-86`, `s1_itemother_managements_discussion.md:524`, and `s1_itemother_managements_discussion.md:617-618`.

## Accounting Details That Matter

Vehicle depreciation is not a technical detail here. It is one of the central questions.

In 2024, Lime's annual vehicle asset useful-life reassessment decreased vehicle asset depreciation expense by $27.2 million. In 2025, Lime changed its vehicle depreciation method from usage-based to straight-line, increasing depreciation expense by $14.8 million and net loss by an estimated $11.8 million. Lime estimates useful lives of five years for e-scooters and e-bikes and four years for swappable batteries.

Investors should not treat adjusted EBITDA as the main economic measure without doing this work. The vehicles are the product. Depreciation may be non-cash in a given period, but the fleet still has to be bought, repaired, refreshed, and protected from theft and damage.

Sources: `s1_itemother_managements_discussion.md:1006-1008`, `s1_itemother_index_to_consolidated.md:391-393`, and `s1_itemother_index_to_consolidated.md:711-712`.

## Market Share Is Useful But Not Clean

Lime says it had 27% share across docked and dockless shared micromobility operators in countries where it operated in 2025, 37% share in the United States, 35% share among dockless operators globally, and 48% dockless share in the United States.

Those claims matter because the city-level model benefits from scale and reliability. But the method is not a perfect third-party market share table. Lime calculates share primarily using Sensor Tower monthly active app user data, supplemented by public and internal data. That is directionally useful, not dispositive.

The right investor use is to treat the share claims as support for the density thesis, not as a precise basis for valuation.

Sources: `s1_itemother_prospectus_summary.md:40`, `s1_itemother_business.md:43`, and `s1_itemother_market_industry_data.md:10-19`.

## Valuation Context

The S-1 did not include price range or share count. External reports said the company was aiming around a $2 billion valuation, but that is not in the filing and should be treated as reported context.

If the $2 billion press figure is directionally right, the rough math is:

- 2.3x 2025 revenue.
- 9.2x 2025 adjusted EBITDA.
- 19.3x 2025 filing-defined free cash flow.

Those multiples are not enough by themselves because the offering mechanics are still blank. The old notes, conversion terms, term-loan repayment, Uber ownership, and post-IPO share count will decide what new buyers actually own. But the headline is clear: at roughly $2 billion, investors would not be paying software multiples. They would be paying for a category survivor with proven scale, positive full-year free cash flow, and material financing cleanup still attached.

External sources used for context: Business Wire release syndicated by Yahoo Finance, Financial Times report on approximate valuation, and MarketWatch article on debt concerns.

## What EdgarPack Helped With

The gain versus ordinary agentic search was not that EdgarPack "found the answer" by itself. The gain was that it turned a 250k-token filing into a local, queryable evidence set and made the analysis faster to check.

What worked:

- `identify`, `list`, `build`, and `doctor` quickly established the exact filer, accession, filing date, and pack health.
- `query` produced a clean first financial table for revenue, gross profit, operating income, net income, adjusted EBITDA, and operating cash flow.
- `search` jumped directly to the relevant S-1 sections for Uber, going concern, LimePass, fleet retention, and ROI payback.
- The section markdown made it easy to read MD&A, risk factors, related-party transactions, use of proceeds, and financial-statement notes side by side.
- The pack exposed operating KPIs that generic web coverage mostly compressed away: average operational fleet, RVD, MAU, fleet retention, fleet-cap increases, supplier payment terms, depreciation-method changes, and LimePass mix.

What still needed human review:

- `query` mis-bound FY2025 capex and therefore overstated computed free cash flow. The filing's own reconciliation was the right source.
- `which "Neutron Holdings" --format json --max-periods 8` ran too long and was stopped. The operating KPIs were still recoverable from `search` and the generated sections.
- Table rendering in the S-1 markdown duplicates headers and cells. The data is usable, but it requires careful reading.
- EdgarPack can surface the sections; it does not decide which disclosures are load-bearing. The memo still came from reading the filing.

Against traditional agentic search, this mattered most in three places. First, the debt and going-concern issue is easy to underweight if you read only news summaries. Second, the 2025 free cash flow number looks clean until you read the capex and supplier payment-term note. Third, the best operating story is not "micromobility is back." It is the much narrower and more useful fact that fleet, MAU, and revenue per vehicle per day all grew at the same time while existing-city fleet retention stayed above 100%.

## Commands And Process Log

Repository setup:

```bash
bd prime
bd ready
git status --short --branch
```

Memory and prior work check:

```bash
rg -n "Lime|Neutron|S-1|Neutron Holdings|edgarpack" /Users/samaydhawan/.codex/memories/MEMORY.md
sed -n '1,220p' reports/threads/lime-s1-thread.md
rg -n "Neutron|Lime|Uber|free cash flow|Adjusted EBITDA|gross bookings|revenue|fleet|season" packs reports docs edgarpack universe.toml
```

Core EdgarPack commands:

```bash
uv run edgarpack identify "Neutron Holdings"
uv run edgarpack list "Neutron Holdings" --form S-1 --limit 10
uv run edgarpack doctor packs/0001699963/0001628280-26-032523 --format json
uv run edgarpack query "Neutron Holdings" revenue,gross_profit,operating_income,net_income,adjusted_ebitda,operating_cash_flow,capex,free_cash_flow,cash_and_equivalents --period lfy,lfy-1,lfy-2 --show-links primary
uv run edgarpack which "Neutron Holdings" --format json --max-periods 8
```

`which` was stopped after it ran longer than the rest of the workflow without returning output.

Targeted EdgarPack search:

```bash
uv run edgarpack search "Uber Integration Agreement" --limit 5
uv run edgarpack search "going concern substantial doubt" --limit 5
uv run edgarpack search "LimePass LimePrime" --limit 5
uv run edgarpack search "operational fleet retention rate" --limit 5
uv run edgarpack search "ROI Payback Period" --limit 5
```

Direct section inspection:

```bash
find packs/0001699963/0001628280-26-032523/sections -maxdepth 1 -type f | sort
rg -n "Free Cash Flow|free cash flow|capital expenditures|Adjusted EBITDA|reconciliation|operating activities|purchases of property|property and equipment" packs/0001699963/0001628280-26-032523/sections
rg -n "Uber|Integration Agreement|lock-up|guarantee|Note|term loan|going concern|substantial doubt|liquidity|working capital|Use of Proceeds|proceeds" packs/0001699963/0001628280-26-032523/sections
rg -n "RVD|revenue per vehicle|average operational fleet|MAU|monthly active|LimePass|LimePrime|market share|Sensor Tower|operational fleet retention|exclusive fleet|ROI Payback|fully landed vehicle cost|Useful Life|weather|seasonality" packs/0001699963/0001628280-26-032523/sections
sed -n '220,390p' packs/0001699963/0001628280-26-032523/sections/s1_itemother_managements_discussion.md
sed -n '650,690p' packs/0001699963/0001628280-26-032523/sections/s1_itemother_risk_factors.md
sed -n '1,80p' packs/0001699963/0001628280-26-032523/sections/s1_itemother_use_of_proceeds.md
sed -n '250,310p' packs/0001699963/0001628280-26-032523/sections/s1_itemother_risk_factors.md
sed -n '560,582p' packs/0001699963/0001628280-26-032523/sections/s1_itemother_risk_factors.md
sed -n '1,120p' packs/0001699963/0001628280-26-032523/sections/s1_itemother_principal.md
rg -n "Senior Secured Term Loan|Uber Guaranty|Uber Integration Agreement|Uber Note|2021 Notes|2020 Uber Note|more than 5|greater than 5|beneficial" packs/0001699963/0001628280-26-032523/sections/s1_itemother_certain_relationships.md packs/0001699963/0001628280-26-032523/sections/s1_itemother_principal.md packs/0001699963/0001628280-26-032523/sections/s1_itemother_description_of_securities.md
rg -n "Average Operational Fleet|RVD|MAU|LimePass|Pay-As-You-Go|fully landed vehicle cost|maintenance capital expenditures|useful life|depreciation methodology|vehicle asset useful life|working capital|cash and cash equivalents|principal payments" packs/0001699963/0001628280-26-032523/sections/s1_itemother_managements_discussion.md packs/0001699963/0001628280-26-032523/sections/s1_itemother_index_to_consolidated.md
```

External search:

```text
Neutron Holdings Lime S-1 filed May 2026 IPO LIME
SEC Neutron Holdings S-1 0001628280-26-032523
Lime IPO Neutron Holdings S-1 Uber debt 2026
Business Wire Lime Files Registration Statement Proposed Initial Public Offering May 8 2026 Neutron Holdings
```

External links referenced:

- SEC filing URL from pack manifest: https://www.sec.gov/Archives/edgar/data/0001699963/000162828026032523/neutronholdingsinc-sx1.htm
- Business Wire release syndicated by Yahoo Finance: https://finance.yahoo.com/markets/stocks/articles/lime-files-registration-statement-proposed-101700340.html
- Financial Times valuation context, access-restricted in link check: https://www.ft.com/content/6622a3fa-5dbf-4790-90c3-618a70f7f11c
- MarketWatch debt context, access-restricted in link check: https://www.marketwatch.com/story/uber-backed-lime-plans-ipo-as-debt-concerns-mount-for-the-e-scooter-maker-62f4f09a
