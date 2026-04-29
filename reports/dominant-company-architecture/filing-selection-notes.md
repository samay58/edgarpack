# Filing Selection Notes

Use this file for judgment calls: missing exact-year filings, predecessor mappings, raw SEC line anchors, companies with no meaningful founder concept, annual-report fallbacks, and table confidence limits.

## Existing Limitation

The founder-control validation pass found that several pre-2000 SEC `.txt` filings build as directory-listing packs. Until `edgarpack-eob` is fixed, use `raw_sec_txt` anchors for those rows and record them in `evidence-ledger.csv`.

## Notes

### Task 2A: 1996 Primary-Cohort Control Rows

- Merck (MRK): selected 1996-03-18 DEF 14A, accession `0000950130-96-000868`, because it is the nearest historical-Merck proxy and includes the `BENEFICIAL OWNERSHIP OF SECURITIES AND VOTING RIGHTS` and `SECURITY OWNERSHIP OF DIRECTORS AND EXECUTIVE OFFICERS` sections.
- IBM (IBM): selected 1996-03-14 DEF 14A, accession `0000950112-96-000792`, because it is the nearest 1996 proxy and includes common-stock voting/investment-power disclosure for directors and officers.
- Procter & Gamble (PG): selected 1996-08-30 DEF 14A, accession `0000080424-96-000015`, because it is the nearest 1996 proxy and includes both common-stock management ownership and ESOP preferred-stock trust ownership.
- Johnson & Johnson (JNJ): selected 1996-03-12 DEF 14A, accession `0000950110-96-000240`, because it is the nearest 1996 proxy and includes the `STOCK OWNERSHIP/CONTROL` section.
- Bristol-Myers Squibb (BMY): selected 1996-03-18 DEF 14A, accession `0000950117-96-000222`, because it is the nearest 1996 proxy and includes voting securities/principal-holder evidence.
- Pfizer (PFE): selected 1996-03-19 DEF 14A, accession `0000912057-96-004748`, because it is the nearest 1996 proxy and includes the `SECURITY OWNERSHIP OF MANAGEMENT` section.
- Walt Disney (DIS): selected 1997-01-09 DEF 14A, accession `0000898430-97-000058`, under predecessor CIK `0001001039` (`TWDC Enterprises 18 Corp.`). EdgarPack's current DIS CIK `0001744489` has only post-2019 filings, so the old CIK is required for 1996-era Disney evidence. The proxy supports limited Roy E. Disney family presence, not founder-family control.
- PepsiCo (PEP): selected 1996-03-26 DEF 14A, accession `0000077476-96-000022`, because it is the nearest 1996 proxy and includes record-date voting stock plus director/officer ownership evidence.
- Chevron (CVX): selected 1996-03-21 DEF 14A, accession `0000950149-96-000255`, because it is the nearest 1996 proxy and includes stock ownership of directors and executive officers.
- AIG (AIG): selected 1996-04-02 DEF 14A, accession `0000950123-96-001545`, because it is the nearest 1996 proxy and includes ownership of AIG plus parent-company securities at Starr and SICO.
- Cisco Systems (CSCO): selected 1996-10-04 DEF 14A, accession `0000950149-96-001536`, because it is the nearest 1996 proxy and includes the ownership table plus a no-5-percent-shareholder statement based on 1996 13G review.
- Eli Lilly (LLY): selected 1996-03-04 DEF 14A, accession `0000950130-96-000714`, because it is the nearest 1996 proxy and includes management ownership plus principal holders of common stock.
- Fannie Mae (FNMA): EdgarPack/SEC lists no 1995-1997 DEF 14A, 10-K, 10-K405, DEF 14C, or PRE 14A for CIK `0000310522`; the first listed SEC 10-K is 2003 and first listed proxy is 2004. Fannie Mae's own 1998 Information Statement (`W21931s.htm`) gives context on statutory board structure, but the control row is marked unresolved because that source is not SEC/EdgarPack/raw SEC evidence.
- JPMorgan Chase (JPM): selected 1996-04-17 DEF 14A, accession `0000950123-96-001749`, for predecessor Chase Manhattan because it is the nearest 1996 proxy and states Old Chase shares were deemed converted under the merger agreement.

### Task 2B: 2026 Current-Cohort Control Rows

- Amazon (AMZN): selected 2026-04-09 DEF 14A, accession `0001104659-26-041026`, because it was filed before the 2026-04-28 current date and includes founder/director biography plus beneficial ownership.
- Tesla (TSLA): selected 2025-09-17 DEF 14A, accession `0001104659-25-090866`, because no 2026 proxy was filed by 2026-04-28; it includes founder/CEO/director biography, ownership, CEO award, and controlling-stockholder litigation context.
- Berkshire Hathaway (BRK.B): selected 2026-03-13 DEF 14A, accession `0001193125-26-106253`, using EdgarPack input `BRK-B`, because it was filed before the current date and includes Buffett voting/economic ownership plus controlling-shareholder language.
- Walmart (WMT): selected 2026-04-23 DEF 14A, accession `0001193125-26-173673`, because it was filed before the current date and includes Walton Enterprises/Walton Family Holdings Trust ownership and proxy mechanics.
- Eli Lilly (LLY): selected 2026-03-20 DEF 14A, accession `0000059478-26-000029`, because it was filed before the current date and includes common-stock ownership of Lilly Endowment and other 5% holders. The Endowment block is recorded as visible context, not control.
- Exxon Mobil (XOM): selected 2026-04-08 DEF 14A, accession `0001193125-26-147614`, because it was filed before the current date and includes the certain-beneficial-owners section.
- Visa (V): selected 2025-12-08 DEF 14A, accession `0001308179-25-000635`, because no 2026 proxy was filed by 2026-04-28; it includes director/officer ownership and principal Class A holders.
- Micron Technology (MU): selected 2025-11-25 DEF 14A, accession `0000723125-25-000038`, because no 2026 proxy was filed by 2026-04-28; it includes the beneficial ownership table.
- Advanced Micro Devices (AMD): selected 2026-03-27 DEF 14A, accession `0001193125-26-129057`, because it was filed before the current date and includes the security ownership table.
- Johnson & Johnson (JNJ): selected 2026-03-11 DEF 14A, accession `0000200406-26-000063`, because it was filed before the current date and includes security ownership of directors/officers and 5% holders.
- Oracle (ORCL): selected 2025-09-26 DEF 14A, accession `0001193125-25-220801`, because no 2026 proxy was filed by 2026-04-28; it includes Ellison founder/role evidence and beneficial ownership.
- Mastercard (MA): selected 2026-04-27 DEF 14A, accession `0001141391-26-000021`, because it was filed one day before the current date and includes security ownership of 5% Class A holders. It is classified as professional-manager control, not single-class, because the company also has non-voting Class B stock.
- Costco Wholesale (COST): selected 2025-12-04 DEF 14A, accession `0000909832-25-000159`, because no 2026 proxy was filed by 2026-04-28; it includes principal shareholders above 5%.

### Task 3A: 1996 Primary-Cohort Governance Rows

- MSFT, INTC, WMT, XOM, KO, GE, MRK, IBM, PG, JNJ, BMY, PFE, PEP, CVX, AIG, CSCO, and LLY: governance rows use the same 1996 DEF 14A filings selected for the dominance-year control rows, with `raw_sec_txt` line anchors because the local pre-2000 proxy packs render as directory listings.
- DIS: governance uses the same 1997-01-09 DEF 14A predecessor-CIK filing selected for the 1996 control row (`0000898430-97-000058`, CIK `0001001039`), because current Disney CIK `0001744489` does not cover the 1996-era proxy.
- JPM: governance uses the same 1996-04-17 Chase Manhattan DEF 14A selected for the control row (`0000950123-96-001749`) as the nearest 1996 predecessor-continuity proxy for JPMorgan Chase.
- FNMA: no SEC/EdgarPack 1995-1997 governance source was located. The row is marked `unresolved` with `availability_exception` evidence, matching the control-table treatment and avoiding non-SEC issuer material as normal evidence.

### Task 3B: 2026 Current-Cohort Governance Rows

- NVDA, MSFT, TSLA, V, MU, ORCL, and COST: governance uses the same latest available 2025 proxy selected for the control row because no 2026 proxy was filed by 2026-04-28.
- GOOGL, META, AAPL, AVGO, JPM, AMZN, BRK.B, WMT, LLY, XOM, AMD, JNJ, and MA: governance uses the same 2026 proxy selected for the current-cohort control row.
- GOOGL is labeled `multi_class_common_with_nonvoting_class` because the proxy discloses Class A/Class B voting shares and non-voting Class C capital stock. META is labeled `dual_class_common` because the proxy discloses Class A one-vote and Class B ten-vote common stock.
- BRK.B is labeled `multi_class_common` because the proxy discloses Class A and Class B voting common stock with different votes per share. MA is labeled `multi_class_common_with_nonvoting_class` because Class A is voting and Class B is non-voting. V is labeled `class_a_voting_only_disclosed` because the reviewed proxy evidence supports Class A voting at the meeting but not a full share-class map.
- TSLA is the main current-cohort governance limitation: the row uses the latest available 2025 proxy, records the classified-board structure and supermajority elimination proposal from the cited chunks, and keeps board-independence wording limited because the reviewed chunks did not provide the same compact full-board independence summary found in most other current proxies.
- AVGO, AMZN, AMD, and COST have one or more governance fields marked `not_disclosed` where the reviewed chunks did not provide a separate committee-independence, full-board-independence, or takeover-defense statement. No search snippets were used as evidence.
### Task 4: Annual Filing Selection For Operating And Capital Rows

- Coca-Cola (KO, 1996): selected 10-K405 filed 1997-03-11, accession `0000021344-97-000014`; evidence locator `raw:KO-1996:L7683-L7701`.
- Exxon Mobil (XOM, 1996): selected 10-K filed 1996-03-08, accession `0000930661-96-000138`; evidence locator `raw:XOM-1996:L4210-L4228; raw:XOM-1996:L1759-L1787`.
- Intel (INTC, 1996): selected 10-K filed 1997-03-28, accession `0000050863-97-000020`; evidence locator `raw:INTC-1996:L4368-L4386; raw:INTC-1996:L520-L524`.
- Microsoft (MSFT, 1996): selected 10-K filed 1996-09-27, accession `0000891020-96-001130`; evidence locator `raw:MSFT-1996:L2982-L3000; raw:MSFT-1996:L678-L680; raw:MSFT-1996:L1036-L1044`.
- General Electric (GE, 1996): selected 10-K405 filed 1997-03-21, accession `0000040545-97-000005`; evidence locator `raw:GE-1996:L6347-L6365; raw:GE-1996:L873-L885; raw:GE-1996:L3160-L3160`.
- Merck (MRK, 1996): selected 10-K filed 1997-03-19, accession `0000950130-97-001093`; evidence locator `raw:MRK-1996:L139-L141; raw:MRK-1996:L721-L723; raw:MRK-1996:L2848-L2855; raw:MRK-1996:L4156-L4200`.
- IBM (IBM, 1996): selected 10-K filed 1997-03-27, accession `0000912057-97-010483`; evidence locator `raw:IBM-1996:L5525-L5543; raw:IBM-1996:L2943-L2954`.
- Procter & Gamble (PG, 1996): selected 10-K filed 1996-09-11, accession `0000080424-96-000017`; evidence locator `raw:PG-1996:L5301-L5319; raw:PG-1996:L234-L234`.
- Johnson & Johnson (JNJ, 1996): selected 10-K405 filed 1997-03-31, accession `0000950123-97-002843`; evidence locator `raw:JNJ-1996:L5770-L5788`.
- Walmart (WMT, 1996): selected 10-K filed 1997-04-21, accession `0000104169-97-000003`; evidence locator `raw:WMT-1996:L2468-L2486; raw:WMT-1996:L1701-L1724`.
- Bristol-Myers Squibb (BMY, 1996): selected 10-K filed 1997-03-31, accession `0000014272-97-000008`; evidence locator `raw:BMY-1996:L8543-L8561; raw:BMY-1996:L1312-L1317`.
- Pfizer (PFE, 1996): selected 10-K filed 1997-03-28, accession `0000950116-97-000605`; evidence locator `raw:PFE-1996:L14829-L14847; raw:PFE-1996:L337-L340; raw:PFE-1996:L907-L911`.
- Walt Disney (DIS, 1996): selected 10-K405 filed 1996-12-19, accession `0000898430-96-005815`; evidence locator `raw:DIS-1996:L10471-L10489; raw:DIS-1996:L1356-L1359`.
- PepsiCo (PEP, 1996): selected 10-K filed 1997-03-25, accession `0000077476-97-000007`; evidence locator `raw:PEP-1996:L10591-L10609; raw:PEP-1996:L326-L328; raw:PEP-1996:L2443-L2444`.
- Chevron (CVX, 1996): selected 10-K filed 1996-03-27, accession `0000093410-96-000003`; evidence locator `raw:CVX-1996:L8392-L8410; raw:CVX-1996:L3917-L3931; raw:CVX-1996:L240-L240`.
- AIG (AIG, 1996): selected 10-K filed 1997-03-28, accession `0000950123-97-002720`; evidence locator `raw:AIG-1996:L9306-L9306; raw:AIG-1996:L2556-L2557; raw:AIG-1996:L4149-L4149`.
- Cisco Systems (CSCO, 1996): selected 10-K filed 1996-10-25, accession `0000950149-96-001640`; evidence locator `raw:CSCO-1996:L3963-L3981; raw:CSCO-1996:L604-L607; raw:CSCO-1996:L864-L870`.
- Eli Lilly (LLY, 1996): selected 10-K filed 1996-03-25, accession `0000059478-96-000001`; evidence locator `raw:LLY-1996:L5042-L5060; raw:LLY-1996:L607-L609; raw:LLY-1996:L2791-L2794`.
- Fannie Mae (FNMA, 1996): selected availability_exception filed no-1995-1997-sec-annual, accession `no-1995-1997-sec-annual`; evidence locator `availability_exception:FNMA-1996:no-sec-annual-filing`.
- JPMorgan Chase (JPM, 1996): selected 10-K filed 1997-03-25, accession `0000950123-97-002412`; evidence locator `raw:JPM-1996:L11303-L11303`.
- NVIDIA (NVDA, 2026): selected 10-K filed 2026-02-25, accession `0001045810-26-000021`; evidence locator `76db4f64fb7c0f8c; 8e43a2ddda32c7ed; 924de81c8bd11bdd; faca9441d16bf926; 317640d522f84336; 6d818794f80ce674; 5528577b40a2bd2a`.
- Alphabet (GOOGL, 2026): selected 10-K filed 2026-02-05, accession `0001652044-26-000018`; evidence locator `2944603f9d6253ce; 299663073aeeae1c; 754218e0c456f4e1; 66e919ea6a89c5c9; 38630a332cfb2bcd; 7c2c95e2c66d9aac; ffaa7169415628b4; 230b816365022b67`.
- Apple (AAPL, 2026): selected 10-K filed 2025-10-31, accession `0000320193-25-000079`; evidence locator `fa7828d9fce42172; ec069b7dcbf393a0; aabda7a3b9a62566; 0b7b125fee38ef7d; be2a735a6acbdc71`.
- Microsoft (MSFT, 2026): selected 10-K filed 2025-07-30, accession `0000950170-25-100235`; evidence locator `8f5a9a653fd87359; effcee5a391032d3; d5335e6b9eb843f8; 63ab2ab6f45f7d24; 8b8e8c43682746e4; 12d2b6ebe61c3703`.
- Amazon (AMZN, 2026): selected 10-K filed 2026-02-06, accession `0001018724-26-000004`; evidence locator `3912c859e32d4efc; ed3bd5a069aef122; a7ca4c3305e5c3c5; 9181e4fd1d644adc; 58be82cb75582d90; 82ea41785db77f3d; ed6c560457d7bf0e`.
- Broadcom (AVGO, 2026): selected 10-K filed 2025-12-18, accession `0001730168-25-000121`; evidence locator `4f47760ca73e32bb; 4645d17e6a4723d9; d23b6bd8ee80da71; 316ae7852c169ec2; f66ea888c413bbae; ef0cf4f47de422d5; 5c5ad1014756413d`.
- Meta Platforms (META, 2026): selected 10-K filed 2026-01-29, accession `0001628280-26-003942`; evidence locator `73f51c843cd4097e; 1b4862134809d2ae; 88f5824f9e70b2ca; 1a3f6b42414fe151; 632d63d89afa425b; 43c8f1756f863d69; 3f85be798c2d364d`.
- Tesla (TSLA, 2026): selected 10-K filed 2026-01-29, accession `0001628280-26-003952`; evidence locator `2bdeaf78d75e4dd5; efdbe9003d9ead54; 58a74a803da5cc84; fe7e8a28c2dc108a; d878b7d206cd0edc; d218b9d3eccca91a; cfa0f2315d3973e2`.
- Berkshire Hathaway (BRK.B, 2026): selected 10-K filed 2026-03-02, accession `0001193125-26-083899`; evidence locator `2958c0e07eacaaa1; d3e52f4b477cbd15; d226e48e5c6461f4; c795cb1f17118dd2; b0d0cda15f40f436; ab3a5694d4f7abe8`.
- Walmart (WMT, 2026): selected 10-K filed 2026-03-13, accession `0000104169-26-000055`; evidence locator `8643ff20c037d17e; 74d3d427af9a5321; d5dac99b25c812b4; 9e0e94351b929ffb; fac6095fe42200dc; f50e97c42ff582ad; c29d608ae93a7e65`.
- JPMorgan Chase (JPM, 2026): selected 10-K filed 2026-02-13, accession `0001628280-26-008131`; evidence locator `d0e7aadfe0820527; c9f7823e98a90319; e5bd3bd1329391bc; db35c25aba99aed0; d931262f93831f99; a3decff3a0e517a7; f5f33aeac5934736`.
- Eli Lilly (LLY, 2026): selected 10-K filed 2026-02-12, accession `0000059478-26-000013`; evidence locator `cc99294f464388fa; 9f933cf8a3152410; 03d7de98f092489a; d4890c51547508a8; b5764e2c79f9a1b3; 973c82e9daced9db; fd487982c7c35928; bfaf0f98dd738c60`.
- Exxon Mobil (XOM, 2026): selected 10-K filed 2026-02-18, accession `0000034088-26-000045`; evidence locator `d69376907ed8777a; fcdf22cb91490105; e18a8a28adfcf588; 2951de14f973d74a; 0a13d3fde1620b3c; e8e8bee6522ab133; a035df9359904dd4`.
- Visa (V, 2026): selected 10-K filed 2025-11-06, accession `0001403161-25-000089`; evidence locator `ecad61173b7d4527; 69abefc6acca05b1; 605be01d59209a5d; 91c77b82959e3ba8; ecc8d6b393c6ad31; a97cf3682f292770; 9ce61fd35ea23157; 30dd6bf1a34b9f93`.
- Micron Technology (MU, 2026): selected 10-K filed 2025-10-03, accession `0000723125-25-000028`; evidence locator `386867fcdf159431; e0edc2ae5ba05323; 0986712ab1f8f432; b61e71e8dc066664; feb0388a5793b0ac; 6786d3c397b3a178; 933d9e667d20a207`.
- Advanced Micro Devices (AMD, 2026): selected 10-K filed 2026-02-04, accession `0000002488-26-000018`; evidence locator `34939d242a49c7a2; b794e110d9b3769a; 49f10deba779caad; d288ac3ab828c684; 8c9ea306ff08a701; 22dd6da45ef04921; ed2ab5f61012ad5e`.
- Johnson & Johnson (JNJ, 2026): selected 10-K filed 2026-02-11, accession `0000200406-26-000016`; evidence locator `cada017cefbc5fa1; ddf0b35bfe20f720; 90a70f54551b403d; d5bc65dca3fe6214; ef97604b9d72b187; d606985e75bb6d8e; c7a417233e29ca22; 0ae26be4f92554b6`.
- Oracle (ORCL, 2026): selected 10-K filed 2025-06-18, accession `0000950170-25-087926`; evidence locator `f3ede522013cf9e5; 8ce3c6c1a3073dd1; 594fd9c9d7012424; 0cae6e344bcf87c1; d327f577a68e949f; b8144882db68f212; 7f21fa2851c8bb36`.
- Mastercard (MA, 2026): selected 10-K filed 2026-02-11, accession `0001141391-26-000013`; evidence locator `c6ab47a3be08dc78; e0e0ef75933df8ad; 2ceef30bdbfe9d2b; 956f8914092ddb3c; 0db20a4717e4b86d; e230b65570892e82`.
- Costco Wholesale (COST, 2026): selected 10-K filed 2025-10-08, accession `0000909832-25-000101`; evidence locator `a0e37c097fccca33; 498b96b34c471de9; 58d394300bbcfca4; d4e8abe9fab8bb05; b3d1f9d10d6ff5ab; feac4d56b61b42ea; cac19c5e3428150b`.

Lower-confidence/unresolved extraction rows in this pass: Fannie Mae 1996 availability exception; AIG 1996 and JPMorgan Chase 1996 financial-taxonomy limitations; Berkshire Hathaway 2026 and JPMorgan Chase 2026 use lower confidence because conglomerate/banking operating-income and margin fields are not directly comparable to industrial issuers.

## KPI-specific limitations
- KPI correction (MRK, 1996): the research pass corrected Merck from current-MRK lineage CIK `0000310158` to historical Merck CIK `0000064978`. The corrected annual filing is accession `0000950130-97-001093`; the corrected proxy is accession `0000950130-96-000868`.
