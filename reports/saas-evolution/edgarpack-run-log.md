# EdgarPack Run Log

Record every EdgarPack command that contributes evidence to the bundle.

| timestamp_et | command | output_path | result | notes |
| --- | --- | --- | --- | --- |
| 2026-04-29 | `for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do uv run edgarpack identify "$ticker"; done` | `raw/edgarpack/identify-*.txt` | success after escalated rerun | Identity pass for full cohort; all 11 resolved as public SEC filers with CIKs. Initial sandboxed run failed before EdgarPack started because uv cache access was denied. |
| 2026-04-29 | `for ticker in CRM NOW ADBE TEAM SHOP DDOG SNOW MDB ZM HUBS WDAY; do uv run edgarpack list "$ticker" --form 10-K --limit 15; done` | `raw/edgarpack/list-*-10k.txt` | success after escalated rerun | 10-K availability pass. Long histories for CRM/NOW/ADBE/HUBS/MDB/WDAY; IPO-era or foreign-issuer gaps for TEAM/SHOP/DDOG/SNOW/ZM. |
| 2026-04-29 | `for form in S-1 F-1 20-F; do for ticker in TEAM SHOP DDOG SNOW MDB ZM HUBS; do uv run edgarpack list "$ticker" --form "$form" --limit 10; done; done` | `raw/edgarpack/list-*-S-1.txt`, `raw/edgarpack/list-*-F-1.txt`, `raw/edgarpack/list-*-20-F.txt` | success | Targeted baseline-form sweep found DDOG/SNOW/MDB/ZM/HUBS S-1s, SHOP/TEAM F-1s, and TEAM 20-F history. |
| 2026-04-29 | `for ticker in SHOP TEAM; do uv run edgarpack list "$ticker" --form 40-F --limit 12; done` | `raw/edgarpack/list-*-40-F.txt` | success | Foreign-issuer annual-form check found Shopify 40-F history from 2017-2024; TEAM has no 40-F filings. |
