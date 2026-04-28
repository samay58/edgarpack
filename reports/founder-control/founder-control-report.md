# Founder Control Across Today's Top Technology Companies

Date: 2026-04-28

## Method

This report uses the current top ten technology companies frozen in `cohort.csv` from CompaniesMarketCap's tech market-cap ranking (`https://companiesmarketcap.com/tech/largest-tech-companies-by-market-cap/`), then tracks each company across 2026, 2016, and 2006 where primary SEC filings are available. The authoritative evidence table is `founder-control-table.csv`; every factual statement below is derived from that table and its cited pack paths, accessions, section IDs, and chunk IDs.

The source priority is DEF 14A, then 20-F for ADR or foreign private issuer cases, then 10-K Part III, then S-1 or F-1 only when the company was not yet public at the anchor year. Samsung Electronics is retained in the cohort but excluded from founder-control extraction because EdgarPack did not resolve SEC or 20-F coverage for the tested Samsung inputs.

## Findings

Founder majority voting control is concentrated in the dual-class companies. Alphabet's co-founders have a combined 52.7% reported voting power in the 2026 row, 52.5% in 2016, and 57.5% in the Google Inc. 2006 predecessor row. Meta is even more explicit: Mark Zuckerberg has 60.8% voting power in 2026, 60.1% including proxy voting power in 2016, and 56.9% including proxy voting power in the 2012 S-1 fallback for the 2006 anchor. Meta's cited filings also state controlled-company status.

Single-class founder influence generally declined. Jeff Bezos remains Amazon's founder executive chair, but the cited ownership rows decline from 24.26% in 2006 to 17.6% in 2016 to 8.8% in 2026. NVIDIA's Jensen Huang remains founder-CEO/director, while cited ownership declines from 6.3% in 2006 to 4.45% in 2016 to 3.77% in the latest proxy row used for 2026. Microsoft's founder-control profile fell from Bill Gates at 9.73% and chair in 2006, to 2.46% and director/technical advisor in 2016, to no founder listed among the current over-5% principal holders in the 2026 anchor row.

Apple is the cleanest founder-control fadeout. The 2006 row shows Steve Jobs as founder-CEO/director with 1.19% common-stock ownership. The 2016 and 2026 rows do not use a founder row; they cite Tim Cook as the relevant management holder under 1%, with no founder-control mechanism cited.

Tesla remains founder-led but not majority founder-controlled in the cited rows. Elon Musk has 26.5% in the 2016 proxy row and 19.8% in the latest proxy row used for 2026. The 2010 S-1 fallback for the 2006 anchor supports Musk as CEO/chairman and a major holder, but the preliminary table does not support a reliable voting-power percentage.

TSM and Broadcom show why founder role, ownership, and control should stay separate. TSM's founder Morris Chang was chairman and held 0.48% in the 2016 row and 0.45% in the 2007 fallback row, while the 2007 row points to Philips and the National Development Fund as possible controlling shareholders. Broadcom's 2026 row shows Henry Samueli as co-founder and board chair with 1.8%; the 2016 predecessor row shows 2.3% voting power after the Broadcom acquisition; the 2008 Avago S-1 fallback is sponsor-controlled, not founder-controlled.

## Company Notes

| Company | 2026 Anchor | 2016 Anchor | 2006 Anchor |
| --- | --- | --- | --- |
| NVIDIA | Huang 3.77%, founder CEO/director | Huang 4.45%, founder CEO/director | Huang 6.3%, founder CEO/director |
| Alphabet / Google | Page + Brin 52.7% voting power | Page + Brin 52.5% voting power | Page + Brin 57.5% voting power under Google Inc. predecessor |
| Apple | no founder row; Cook under 1% | no founder row; Cook under 1% | Jobs 1.19%, founder CEO/director |
| Microsoft | founders not listed among current over-5% holders | Gates 2.46%, director/technical advisor | Gates 9.73%, chairman |
| Amazon | Bezos 8.8%, founder executive chair | Bezos 17.6%, CEO/chair | Bezos 24.26%, CEO/chair |
| TSM | no founder row; C.C. Wei current chair/CEO owns 0.03% | Morris Chang 0.48%, founding chairman | Morris Chang 0.45% in 2007 fallback; Philips/NDF possible control |
| Broadcom | Samueli 1.8%, co-founder and board chair | Samueli 2.3% voting power in predecessor proxy | Avago S-1 fallback is sponsor-controlled, not founder-controlled |
| Meta | Zuckerberg 60.8% voting power; controlled company | Zuckerberg 60.1% including proxy; controlled company | Zuckerberg 56.9% including proxy in S-1 fallback |
| Tesla | Musk 19.8%, founder CEO/director | Musk 26.5%, CEO/chair | S-1 fallback supports major ownership, but no reliable pct |
| Samsung | no SEC-backed row | no SEC-backed row | no SEC-backed row |

## Source Limitations

The 2026 anchor means current as of the 2026-04-28 cohort freeze, not necessarily a filing dated in calendar 2026. NVIDIA, Microsoft, and Tesla use the latest available proxy because their next 2026 proxy had not been filed at the freeze date.

Alphabet and Broadcom require predecessor identity mapping. Alphabet's 2006 row uses Google Inc. CIK 0001288776. Broadcom's 2016 row uses Broadcom Pte. Ltd. CIK 0001649338, and its 2006 anchor uses an Avago Technologies LTD S-1 fallback.

Several 2006 anchor rows are first-public-filing fallbacks rather than exact 2006 disclosures. Meta uses its 2012 S-1, Tesla uses its 2010 S-1, and Broadcom/Avago uses its 2008 S-1. These rows are useful for earliest public founder-control evidence, but they should not be read as direct 2006 public-company snapshots.

TSM is an ADR/FPI case using 20-F filings. The exact 2006 TSM 20-F exists in SEC results but failed EdgarPack table rendering, so the report uses the 2007 20-F pack as the closest comparable filing that EdgarPack could build. TSM rows are medium confidence because 20-F ownership/voting disclosure is less directly comparable to U.S. proxy tables.

Samsung Electronics is in the frozen top-ten cohort, but this run does not use non-SEC sources and EdgarPack did not resolve the tested Samsung inputs to SEC/20-F coverage. The report therefore does not make a founder-control claim for Samsung.

## Evidence Files

- `cohort.csv`
- `filing-selection-notes.md`
- `founder-control-table.csv`
- Local packs under `packs/` with section and chunk evidence paths cited in `founder-control-table.csv`
