# Filing Selection Notes

Use this file for judgment calls: missing exact-year filings, predecessor mappings, raw SEC line anchors, companies with no meaningful founder concept, annual-report fallbacks, and table confidence limits.

## Existing Limitation

The founder-control validation pass found that several pre-2000 SEC `.txt` filings build as directory-listing packs. Until `edgarpack-eob` is fixed, use `raw_sec_txt` anchors for those rows and record them in `evidence-ledger.csv`.

## Notes
