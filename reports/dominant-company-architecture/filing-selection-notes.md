# Filing Selection Notes

Use this file for judgment calls: missing exact-year filings, predecessor mappings, raw SEC line anchors, companies with no meaningful founder concept, annual-report fallbacks, and table confidence limits.

## Existing Limitation

The founder-control validation pass found that several pre-2000 SEC `.txt` filings build as directory-listing packs. Until `edgarpack-eob` is fixed, use `raw_sec_txt` anchors for those rows and record them in `evidence-ledger.csv`.

## Notes

### Task 2A: 1996 Primary-Cohort Control Rows

- Merck (MRK): selected 1996-03-19 DEF 14A, accession `0000950123-96-001174`, because it is the nearest 1996 proxy and includes the `SECURITY OWNERSHIP` section.
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
