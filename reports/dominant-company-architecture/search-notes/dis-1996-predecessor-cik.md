# Walt Disney 1996 Predecessor CIK Note

Task 2A uses CIK `0001001039` (`TWDC Enterprises 18 Corp.`) for the 1996-era Walt Disney row.

EdgarPack resolves current ticker `DIS` to CIK `0001744489`, whose listed filings begin after the later Disney reorganization and do not cover the 1996 dominance-year proxy. Running `uv run edgarpack identify 1001039` resolves the old public filer, and `uv run edgarpack list 1001039 --form "DEF 14A" --limit 60` returns the 1997-01-09 DEF 14A accession `0000898430-97-000058`.

The selected filing is inside the 1995-1997 Task 2A window and contains the stock-ownership section used for the control row.
