# Metric Definition Notes

Primary evidence comes from EdgarPack-built filing sections and `which` outputs. External market sources are intentionally excluded from this task.

Required definitions captured:

- Adobe ARR: Adobe discloses ARR as an annual value of subscription contracts/ETLA-style subscription value, and its framing changed from Digital Media ARR to Total Adobe ARR in fiscal 2025 reporting.
- Salesforce RPO/cRPO: `which` captured RPO/cRPO values and definitions, but the CRM rows still lack chunk IDs even after forced chunk rebuild; section fallback is retained.
- ServiceNow cRPO: filing sections define RPO and cRPO, with cRPO representing RPO expected to be recognized as revenue in the next 12 months.
- Snowflake NRR/RPO caveat: filing sections show consumption timing makes RPO interpretation different from seat-based SaaS backlog.
- MongoDB Atlas ARR: filing sections define ARR using contractual commitments plus Atlas usage annualization windows.
- Datadog FCF: filing sections define free cash flow as operating cash flow less capex and capitalized software development costs.

Comparability rule:

Never compare ARR, RPO/cRPO, NRR, subscription backlog, or FCF across companies without checking the definition row first. The same label often means different inclusion rules, timing windows, or consumption exposure.
