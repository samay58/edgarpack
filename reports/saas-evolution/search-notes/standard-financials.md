# Standard Financials Extraction Notes

Primary evidence is the EdgarPack annual-series component JSON under `raw/edgarpack/query-*-annual-series.json`. The scalar selector outputs under `raw/edgarpack/query-*-annual-core.json` were kept as raw evidence but not used for final table population because sparse `lfy-10` fallbacks were too easy to misread as true baseline periods.

Rules used:

- Queried `revenue,gross_profit,operating_income,operating_cash_flow,capex,rd_expense,sm_expense,stock_based_compensation` for `annual:12`.
- Preserved EdgarPack `company`, `cik`, `fiscal_year`, `form_type`, `filed`, `accession`, `primary_link`, and `citation_ids`.
- Mapped the latest available annual revenue year to `current`, fiscal 2020 to `midpoint` when available, and the filing-selection baseline target year when available.
- If the baseline target year was unavailable through `query`, used the earliest/closest annual-series query year and marked the row note so it cannot be mistaken for a true 2014/2015 or IPO baseline.
- Kept missing metric fields blank and documented missing coverage in row notes.
- Computed margins, intensities, and free cash flow only from EdgarPack-sourced component values in the same fiscal year.

Coverage notes:

- Query coverage still falls short of the filing availability pass for several companies. Example: EdgarPack `list` finds older 10-Ks/20-Fs/F-1s, while `query annual:12` may only return a shorter XBRL-backed series.
- TEAM has current 10-K query coverage but no useful query-series history before fiscal 2023; use Task 4/5 filing packs and 20-F/F-1 evidence before making any historical Atlassian claim.
- SHOP annual-series query output only covers fiscal 2024-2025 even though EdgarPack `list` finds F-1/40-F history. Do not use the standard-financials table alone for Shopify history.
