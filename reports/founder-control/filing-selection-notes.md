# Filing Selection Notes

Use this file only for judgment calls: missing exact-year filings, ambiguous share classes, ADR/20-F treatment, S-1/F-1 fallback, or companies where the nearest available filing changes the interpretation.

## Notes

### NVDA 2026

- Candidate forms checked: DEF 14A, 10-K
- Selected filing: DEF 14A filed 2025-05-13 accession 0001045810-25-000095
- Reason: latest available proxy as of the 2026-04-28 cohort freeze; the next proxy had not been filed.
- Limitation: current anchor uses latest available proxy rather than a 2026 filing.

### GOOG 2006

- Candidate forms checked: DEF 14A
- Selected filing: DEF 14A filed 2006-03-31 accession 0001193125-06-070406
- Reason: the current Alphabet CIK has no 2006 filings; Google Inc. predecessor CIK 0001288776 has the 2006 proxy.
- Limitation: predecessor identity mapping is required.

### MSFT 2026

- Candidate forms checked: DEF 14A, 10-K
- Selected filing: DEF 14A filed 2025-10-21 accession 0001193125-25-245150
- Reason: latest available proxy as of the 2026-04-28 cohort freeze; Microsoft's 2026 proxy cycle had not yet occurred.
- Limitation: current anchor uses latest available proxy rather than a 2026 filing.

### TSM 2026, 2016, 2006

- Candidate forms checked: 20-F, DEF 14A, 10-K, S-1, F-1
- Selected filings:
  - 2026: 20-F filed 2026-04-16 accession 0001628280-26-025362
  - 2016: 20-F filed 2016-04-11 accession 0001193125-16-536225
  - 2006: 20-F filed 2007-04-20 accession 0001145549-07-000571
- Reason: TSM is an ADR/FPI case; 20-F is the SEC-backed annual source.
- Limitation: governance disclosure format differs from U.S. proxy statements. The exact 2006 20-F accession 0001145549-06-000500 fails in EdgarPack table rendering with `IndexError: list assignment index out of range`, so the 2007 20-F pack is used as the closest comparable filing that EdgarPack can build.

### AVGO 2016

- Candidate forms checked: DEF 14A, 10-K
- Selected filing: DEF 14A filed 2016-02-23 accession 0001193125-16-472407
- Reason: Broadcom Inc. CIK 0001730168 starts later; the 2016 anchor uses predecessor Broadcom Pte. Ltd. CIK 0001649338.
- Limitation: predecessor identity mapping is required.

### AVGO 2006

- Candidate forms checked: DEF 14A, 10-K, S-1
- Selected filing: S-1 filed 2008-08-21 accession 0001193125-08-182335
- Reason: the company was not public at the 2006 anchor; earliest relevant SEC registration filing under Avago Technologies LTD CIK 0001441634 is used as a fallback.
- Limitation: this is a post-anchor first-public-filing fallback, not a 2006 disclosure.

### META 2006

- Candidate forms checked: DEF 14A, 10-K, S-1
- Selected filing: S-1 filed 2012-02-01 accession 0001193125-12-034517
- Reason: Facebook was not public at the 2006 anchor; earliest relevant SEC registration filing is used as a fallback.
- Limitation: this is a post-anchor first-public-filing fallback, not a 2006 disclosure.

### TSLA 2026

- Candidate forms checked: DEF 14A, 10-K
- Selected filing: DEF 14A filed 2025-09-17 accession 0001104659-25-090866
- Reason: latest available proxy as of the 2026-04-28 cohort freeze; a 2026 proxy had not been filed.
- Limitation: current anchor uses latest available proxy rather than a 2026 filing.

### TSLA 2006

- Candidate forms checked: DEF 14A, 10-K, S-1
- Selected filing: S-1 filed 2010-01-29 accession 0001193125-10-017054
- Reason: Tesla was not public at the 2006 anchor; earliest relevant SEC registration filing is used as a fallback.
- Limitation: this is a post-anchor first-public-filing fallback, not a 2006 disclosure.

### Samsung Electronics 2026, 2016, 2006

- Candidate forms checked: 20-F, DEF 14A, 10-K, S-1, F-1
- Selected filing: none
- Reason: EdgarPack did not resolve `Samsung Electronics`, `005930.KS`, or tested Samsung Electronics name variants to SEC/20-F coverage.
- Limitation: retained in the frozen cohort but excluded from founder-control extraction because this run does not use non-SEC sources.
