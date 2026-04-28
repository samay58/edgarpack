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
- Walt Disney (DIS): selected 1997-01-09 DEF 14A, accession `0000898430-97-000058`, under predecessor CIK `0001001039` (`TWDC Enterprises 18 Corp.`). EdgarPack's current DIS CIK `0001744489` has only post-2019 filings, so the old CIK is required for 1996-era Disney evidence.
- PepsiCo (PEP): selected 1996-03-26 DEF 14A, accession `0000077476-96-000022`, because it is the nearest 1996 proxy and includes record-date voting stock plus director/officer ownership evidence.
- Chevron (CVX): selected 1996-03-21 DEF 14A, accession `0000950149-96-000255`, because it is the nearest 1996 proxy and includes stock ownership of directors and executive officers.
- AIG (AIG): selected 1996-04-02 DEF 14A, accession `0000950123-96-001545`, because it is the nearest 1996 proxy and includes ownership of AIG plus parent-company securities at Starr and SICO.
- Cisco Systems (CSCO): selected 1996-10-04 DEF 14A, accession `0000950149-96-001536`, because it is the nearest 1996 proxy and includes the ownership table plus a no-5-percent-shareholder statement based on 1996 13G review.
- Eli Lilly (LLY): selected 1996-03-04 DEF 14A, accession `0000950130-96-000714`, because it is the nearest 1996 proxy and includes management ownership plus principal holders of common stock.
- Fannie Mae (FNMA): EdgarPack/SEC lists no 1995-1997 DEF 14A or 10-K for CIK `0000310522`; the first listed SEC 10-K is 2003 and first listed proxy is 2004. Used Fannie Mae's own 1998 Information Statement (`W21931s.htm`) as the nearest primary issuer source for statutory board-control structure, with medium confidence and an explicit non-SEC limitation.
- JPMorgan Chase (JPM): selected 1996-04-17 DEF 14A, accession `0000950123-96-001749`, for predecessor Chase Manhattan because it is the nearest 1996 proxy and states Old Chase shares were deemed converted under the merger agreement.
