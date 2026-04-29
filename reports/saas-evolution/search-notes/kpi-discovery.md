# KPI Discovery Notes

Primary evidence is `raw/edgarpack/which-*.json`, after building recent annual packs with `--with-chunks`.

Target KPIs by company:

- CRM: attrition, RPO, cRPO, employees.
- NOW: customers and employees were found; RPO/cRPO and AI ACV were not found by `which`.
- ADBE: `which` found a PDF-search metric, but it was not useful for this SaaS-evolution report; Total Adobe ARR and Digital Media ARR were added from filing-section fallback evidence.
- TEAM: customer count and Marketplace gross purchases were found.
- SHOP: Shopify Payments GMV, payments penetration, App Store breadth, and employees were found; MRR/GMV/subscription-vs-merchant-solution rows require Task 5/6 filing or release work.
- DDOG: total customers were found; net retention and large-customer thresholds require Task 5/6 filing or release work.
- SNOW: NRR, customers above $1M product revenue, total customers, Global 2000 revenue contribution, and daily-query scale were found.
- MDB: customers, net ARR expansion rate, and employees were found.
- ZM: App Marketplace breadth, employees, and Zoom Phone country breadth were found; net dollar expansion and enterprise revenue mix require Task 5/6 filing or release work.
- HUBS: default `which` stalled on filing 1/7, and catalog-only fallback returned zero KPIs; customer count and Average Subscription Revenue per Customer were added from filing-section fallback evidence.
- WDAY: catalog-only fallback returned zero KPIs; total and 12-month subscription revenue backlog were added from filing-section fallback evidence.

Execution notes:

- Default `which` was not reliable as an unattended full-cohort batch. It completed for most companies, stalled around SNOW/HUBS, and required process termination plus targeted fallbacks.
- CRM `which` rows still lacked `chunk_id` even after a forced rebuild with `--with-chunks`; the table keeps `section:<section_id>` in `chunk_id` as a fallback and records the limitation in row notes.
- Rows in `kpi-disclosure-table.csv` are restricted to operationally useful KPIs for the SaaS-evolution report, not every discovered number.
- Raw `which-*.json` files were normalized after capture so each artifact is parseable JSON. The progress lines emitted before JSON are documented as friction rather than preserved inside the JSON artifact.
