# Fannie Mae 1996 SEC Availability Note

Task 2A could not locate a 1995-1997 SEC proxy or 10-K for Fannie Mae CIK `0000310522`.

Commands checked:

```bash
uv run edgarpack list FNMA --form "DEF 14A" --limit 60
uv run edgarpack list FNMA --form "10-K" --limit 60
uv run edgarpack list FNMA --form "10-K405" --limit 60
uv run edgarpack list FNMA --form "DEF 14C" --limit 60
uv run edgarpack list FNMA --form "PRE 14A" --limit 60
```

EdgarPack returned no 1995-1997 proxy or annual-report filing for this CIK; the first listed SEC 10-K was 2003 and the first listed DEF 14A was 2004. SEC full-text search for 1995-1997 `Federal National Mortgage Association` 10-K filings also returned no hits.

The control row therefore uses Fannie Mae's 1998 primary issuer Information Statement at `https://www.fanniemae.com/syndicated/documents/mbs/debtmarketing/DEBENTUR/W21931s.htm`, which describes the charter-based board structure and incorporates the 1997 proxy for stock-ownership details. This is recorded as medium confidence and not as a SEC accession.
