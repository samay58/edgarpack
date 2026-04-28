# Validation Evidence Notes

This note records the evidence anchors used for the validation slice in `founder-control-era-table.csv`.

## Raw SEC Evidence

Some pre-2000 filings currently build in EdgarPack as SEC directory-listing packs rather than parsed filing text. For those rows, the evidence IDs use `raw:<company-year>:Lx-Ly` anchors from the SEC `.txt` filing retrieved with the configured EdgarPack user agent.

- `raw:MSFT-1996:L250-L364`: Microsoft 1996 DEF 14A identifies Gates and Allen as founders and lists Gates at 23.7% and Allen at 9.0%.
- `raw:MSFT-1996:L376`: Microsoft 1996 directors/officers group ownership was 38.7%.
- `raw:INTC-1996:L430-L431`: Intel 1996 DEF 14A identifies Gordon Moore as co-founder and chairman.
- `raw:INTC-1996:L1195`: Intel 1996 ownership table lists Moore at 45,996,726 shares, or 5.6%.
- `raw:WMT-1996:L808-L819`: Walmart 1996 DEF 14A lists Walton family ownership rows and Walton Enterprises-linked holdings around 38%.
- `raw:XOM-1996:L1005-L1044`: Exxon 1996 DEF 14A lists directors/nominees and directors/officers group ownership below founder-control levels.
- `raw:KO-1996:L555-L591` and `raw:KO-1996:L678-L691`: Coca-Cola 1996 DEF 14A lists Buffett/Berkshire as a non-founder 7.98% holder.
- `raw:GE-1996:L545-L572`: GE 1996 DEF 14A states no director/officer exceeds 0.1% and the group is below 1%.
- `raw:NVDA-S1-1998:L3238-L3257` and `raw:NVDA-S1-1998:L3839-L3878`: Nvidia 1998 S-1 identifies Huang as co-founder, president, CEO and director and lists him at 12.8%.

## EdgarPack Chunk Evidence

Current filings and post-2000 S-1 packs have usable EdgarPack chunks. The CSV records the relevant `chunk_id` values in `evidence_chunk_ids`; `evidence_section_id` is descriptive context only.
