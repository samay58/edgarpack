# Showcase ideas: marketing EdgarPack by using it

Premise: the product's one unfakeable differentiator is provenance. Every artifact below is designed so a skeptical reader can click through to the exact filing line, which is the marketing. Effort tiers: WEEKEND (one sitting to first artifact), WEEK (real build), ONGOING (compounding engine). Capabilities in parentheses name what each idea proves.

## Recurring engines (compounding distribution)

1. **The Diff**, a weekly drop of the five most meaningful language changes in filings that week across the harvest universe, each as a redline screenshot plus citation links. The mechanical-noise suppression is what makes this signal instead of spam. (diff, insights, harvest) ONGOING
2. **@filing_diffs bot** on X/Bluesky: auto-post significant diffs with redline images the day a filing lands. Bots with taste build large followings; this one has a working taste filter. (diff, harvest) WEEK to build, then ONGOING
3. **IPO Watch**: an automated page that catches every new S-1/F-1 and publishes a day-one cited financial snapshot plus a registration timeline that updates as amendments land. Being first with cited numbers on a hot filing, within the hour, is a repeatable virality event. (s1/f1 shortcuts, timeline, amendment awareness) WEEK
4. **China Lens Weekly**: English, cited digest of HKEX/A-share filing season; one company per issue, bilingual citations, USD and native values side by side. Nobody else publishes cited English A-share coverage at all. (China Lens, translate, FX provenance) ONGOING
5. **Pre-IPO terms tracker**: for each active registration, chart the pro-forma and use-of-proceeds evolution across amendments. IPO desks and fintwit both want this and currently hand-read it. (pro-forma, timeline) WEEK

## Flagship demonstrations (one big swing each)

6. **BYD vs Tesla, fully cited**: an interactive page where every number links to the exact line of the 10-K or the Chinese annual report, USD-normalized with the FX convention shown. This is the zero-knowledge-investor acceptance test turned into the flagship demo. (cross-market comps, China Lens, citations) WEEK, after Phase 3
7. **Ten years of filing drift**: one company's risk factors as a scrollable animated diff timeline (NVDA 2015 to 2025: watch crypto appear and vanish, export controls grow). Data-viz bait for HN and finance Twitter. (diff, corpus) WEEK
8. **IPO time machine**: for now-public companies, diff their S-1 promises against their subsequent 10-K reality. Airbnb, Snowflake, Coinbase. Registration and periodic pipelines in one narrative. (S-1 + diff) WEEK
9. **What the S-1 does not tell you**: teardown series built on distill's gaps.csv, publishing the absences with receipts. Everyone publishes takes on what a filing says; nobody publishes what it omits, verifiably. (distill, gaps discipline) WEEKEND per teardown
10. **The Luckin autopsy**: reconstruct a resolved fraud's filing-visible red flags purely from primary sources, cited. Use only closed, adjudicated cases to stay safe. The China Lens angle writes itself. (China Lens, diff) WEEK
11. **Dual-listing disclosure gap**: diff what Alibaba tells SEC investors (20-F) against what it tells HK investors (annual report). Only possible with cross-market packs; genuinely novel content. (dual-listing, diff) WEEK, after Phase 3

## Developer distribution (the tool inside other people's projects)

12. **edgarpack-mcp**: an MCP server exposing cited query, diff, and which to any MCP client, listed on the directories. Every AI-finance tinkerer becomes a distribution channel, and the None-not-guess contract is exactly what agent builders are burned by. (whole query surface) WEEK
13. **FinCite bench**: a published benchmark scoring frontier models answering 100 financial questions from memory versus EdgarPack-grounded, measuring fabrication rate. Release the harness. AI labs and fintech CTOs share benchmarks. (citation model as ground truth) WEEK
14. **The 100k-token 10-K, read in 3k**: engineering post plus repo comparing agent accuracy and token cost on packs/llms.txt/chunks versus raw EDGAR HTML. Dev-marketing for the pack format itself. (build pipeline, chunks) WEEKEND
15. **Earnings-agent template**: an open-source reference agent that takes a ticker and emits a one-page cited brief (query + which + distill + latest diff). Publish as a Claude Agent SDK / LangChain template; people fork templates. (end-to-end) WEEK
16. **HuggingFace dataset drop**: all current-year S-1/F-1 registration financials as parquet, every row carrying accession and citation columns. Data people redistribute drops; the schema itself advertises the provenance model. (registration extraction) WEEKEND
17. **Notebook gallery**: five reproducible notebooks (LTM math with visible component citations, diff explorer, China comps, KPI discovery, S-1 snapshot). Deterministic rebuilds mean the notebooks never rot. (determinism) WEEKEND each

## Editorial and research (credibility engines)

18. **State of Disclosure annual report**: corpus-wide statistics from 28M tokens: risk-factor inflation by sector, boilerplate growth rates, topic emergence (AI mentions, tariff language). Journalists cite research reports; every citation is a backlink. (index, insights, corpus scale) WEEK, yearly
19. **The quietest sentence**: a recurring editorial finding the single highest-information change of each filing season, with the redline as the image. Small, sharable, prestige format. (language-shift detection) WEEKEND per edition
20. **Read a Chinese annual report in ten minutes**: a screen-recorded walkthrough of translate-sse on Moutai, showing the fail-closed validators and the rule that numbers are never touched by the LLM. Kills the translation-trust objection on camera. (translation pipeline) WEEKEND
21. **Deep-dive engineering series**: byte-identical rebuilds, the LTM citation contract, suppressing 90 percent of diff noise mechanically, the HKEX column-shift guard. Each is HN-front-page-shaped and costs only writing. (internals) WEEKEND each
22. **Verify-the-quote service for journalists**: a guide plus a small workshop deck teaching financial journalists to verify any reported number against filings in 30 seconds. Newsroom adoption seeds "according to filings via EdgarPack" attributions. (query, citations) WEEKEND

## Stunts and formats (attention with a thesis)

23. **Spot the fabrication**: a quiz site showing paired financial claims, one cited real, one model-hallucinated; players guess, then see the receipt. The product thesis as a game loop. (citation model) WEEK
24. **Zero counter**: a public dashboard: filings processed, facts served, and a big fat zero for uncited numbers returned. The zero is the brand. (telemetry over the contract) WEEKEND
25. **Filing-season live threads**: during 10-K season, run same-day cited threads on the five most-watched filers, generated by the pipeline, edited by a human. Timeliness plus receipts beats hot takes. (harvest, diff, query) ONGOING seasonal
26. **The disclosure Wordle**: daily mini-game: one real risk-factor sentence, guess the company and year. Absurdly cheap, weirdly compelling, links back to the corpus. (corpus) WEEKEND

## Where to start (opinion)

Three engines before anything else: **The Diff** (2 then 1: bot first, newsletter wrapping it), because it compounds weekly, exercises the moat, and needs no timing luck; **IPO Watch** (3), because hot filings hand you attention spikes on a schedule you do not control but can always win with speed plus receipts; **edgarpack-mcp** (12), because developer distribution is the only channel where users do the marketing for you. The flagship (6) ships the week Phase 3 makes any-ticker China real. Everything else slots behind those four.
