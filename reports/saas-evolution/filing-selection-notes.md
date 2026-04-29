# Filing Selection Notes

Use this file for exact filing choices, missing baseline periods, S-1 substitutions, annual results-release fallbacks, source URLs, and confidence limits.

## Rules

- Prefer annual 10-K, 20-F, or F-1/S-1 filings built through EdgarPack.
- Use company IR releases only when the latest annual filing is unavailable or a current metric is disclosed only in the release.
- Mark baseline rows as `ipo_or_first_observable` when the company was not public in 2014 or 2015.
- Record every direct SEC or IR source URL used outside EdgarPack.

## Notes

## Initial Filing Availability Pass

EdgarPack identity resolution succeeded for all 11 cohort companies on 2026-04-29. Raw outputs live under `raw/edgarpack/identify-*.txt`.

| ticker | EdgarPack identity | latest annual filing candidate | 2020 anchor candidate | baseline candidate | availability note |
| --- | --- | --- | --- | --- | --- |
| CRM | Salesforce, Inc.; CIK 0001108524 | 10-K filed 2026-03-02; accession 0001108524-26-000060 | 10-K filed 2020-03-05; accession 0001108524-20-000014 | 10-K filed 2015-03-06; accession 0001108524-15-000008, with 2014 also available | Long 10-K history available through EdgarPack. |
| NOW | ServiceNow, Inc.; CIK 0001373715 | 10-K filed 2026-01-29; accession 0001373715-26-000007 | 10-K filed 2020-02-20; accession 0001373715-20-000072 | 10-K filed 2015-02-27; accession 0001373715-15-000067, with 2014 also available | Long 10-K history available through EdgarPack. |
| ADBE | ADOBE INC.; CIK 0000796343 | 10-K filed 2026-01-15; accession 0000796343-26-000003 | 10-K filed 2020-01-21; accession 0000796343-20-000013 | 10-K filed 2015-01-20; accession 0000796343-15-000022, with 2014 also available | Strong fit for subscription-transition baseline using annual reports. |
| TEAM | Atlassian Corp; CIK 0001650372 | 10-K filed 2025-08-15; accession 0001650372-25-000036 | 20-F filed 2020-08-14; accession 0001650372-20-000030 | F-1 filed 2015-11-09; accession 0001047469-15-008450 | Requires form-family switching: F-1 baseline, 20-F history through 2022, 10-K from 2023 onward. |
| SHOP | SHOPIFY INC.; CIK 0001594805 | 10-K filed 2026-02-11; accession 0001594805-26-000007 | 40-F filed 2020-02-12; accession 0001594805-20-000010 | F-1 filed 2015-04-14; accession 0001193125-15-129273 | Requires foreign-issuer form-family switching: F-1 baseline, 40-F through 2024, 10-K from 2025 onward. |
| DDOG | Datadog, Inc.; CIK 0001561550 | 10-K filed 2026-02-18; accession 0001628280-26-008819 | 10-K filed 2020-02-25; accession 0001564590-20-006422 | S-1 filed 2019-08-23; accession 0001193125-19-227783 | No 2014/2015 public-company baseline; mark baseline rows `ipo_or_first_observable`. |
| SNOW | Snowflake Inc.; CIK 0001640147 | 10-K filed 2026-03-20; accession 0001640147-26-000008 | S-1 filed 2020-08-24; accession 0001628280-20-013010 | S-1 filed 2020-08-24; accession 0001628280-20-013010 | No 2014/2015 public-company baseline; 2020 S-1 is both pandemic-era and first observable baseline. |
| MDB | MongoDB, Inc.; CIK 0001441816 | 10-K filed 2026-03-11; accession 0001628280-26-016799 | 10-K filed 2020-03-27; accession 0001441816-20-000067 | S-1 filed 2017-09-21; accession 0001047469-17-006014 | No 2014/2015 public-company baseline; first 10-K begins 2018. |
| ZM | Zoom Communications, Inc.; CIK 0001585521 | 10-K filed 2026-02-27; accession 0001585521-26-000030 | 10-K filed 2020-03-20; accession 0001585521-20-000095 | S-1 filed 2019-03-22; accession 0001193125-19-083351 | No 2014/2015 public-company baseline; pandemic anchor available in first 10-K. |
| HUBS | HUBSPOT INC; CIK 0001404655 | 10-K filed 2026-02-11; accession 0001193125-26-046646 | 10-K filed 2020-02-12; accession 0001564590-20-004381 | 10-K filed 2015-03-05; accession 0001193125-15-079000; S-1 filed 2014-08-25 | Public-company annual baseline exists in 2015; S-1 is useful for IPO-era model framing. |
| WDAY | Workday, Inc.; CIK 0001327811 | 10-K filed 2026-03-06; accession 0001327811-26-000014 | 10-K filed 2020-03-03; accession 0001327811-20-000022 | 10-K filed 2015-03-25; accession 0001327811-15-000006, with 2014 also available | Long 10-K history available through EdgarPack. |

Use `ipo_or_first_observable` for baseline rows where the company had no 2014/2015 annual public-company filing in EdgarPack output.
