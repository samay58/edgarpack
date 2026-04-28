# Dominant Company Architecture Research Spec

Date: 2026-04-28
Status: Approved direction, ready for writing plan
Scope: Research workflow and report design, not product implementation

## Purpose

Use EdgarPack to build a sharper historical comparison of dominant public companies across eras. Founder control is the opening wedge, not the whole report.

The report should ask what changed in the structure of market dominance: who controls the company, how the company scales, what governance bargain public investors accept, what operating profile sits underneath the market cap, and which disclosed KPIs explain the business.

The output should read like an investor research memo. The evidence should still behave like a filing-backed data product.

## Main Question

How did the architecture of dominant public companies change between the earlier market era and today?

The report should answer five linked questions:

- Control: who could influence or control shareholder outcomes at the time of dominance?
- Governance bargain: did public investors buy single-class institutional governance, founder voting control, family ownership, or professional-manager control?
- Operating machine: was the company asset-heavy, asset-light, R&D-heavy, capex-heavy, services-led, advertising-led, financial, retail, industrial, or commodity-exposed?
- Capital allocation: did dominance come with dividends, buybacks, acquisition scale, cash accumulation, debt, or reinvestment intensity?
- Disclosure model: what KPIs did the company ask investors to track, and how did those KPIs differ across eras?

## Recommended Frame

The report should be called:

```text
Dominant Company Architecture: Then vs Now
```

The current founder-control validation slice becomes the first evidence module. It should not be treated as the final report.

The better final product is not a row-by-row founder-control recap. It is a classification of dominant company types, backed by tables.

## Primary Cohorts

Use the already frozen cohort frame:

- Earlier era: S&P 500 top 20 by market cap in 1996.
- Current era: S&P 500 top 20 by market cap in 2026.
- Historical context: S&P 500 top 20 by market cap in 1989, used only for backdrop unless primary filings support a claim.

Do not make global technology companies the main sample yet. ADR and 20-F companies can be a later extension after the U.S. SEC-first version is strong.

## Output Bundle

Create a new bundle:

```text
reports/dominant-company-architecture/
```

Expected files:

```text
README.md
cohorts.csv
filing-selection-notes.md
company-life-arc.csv
control-table.csv
governance-table.csv
operating-profile-table.csv
capital-allocation-table.csv
kpi-disclosure-table.csv
architecture-archetypes.csv
evidence-ledger.csv
dominant-company-architecture-report.md
```

The existing `reports/founder-control-era/` bundle remains the validation slice and source material for the control module. New work can copy or regenerate its cohort and life-arc files, but the new report should live under the new bundle name.

## Core Tables

### Control Table

Start from `founder-control-era-table.csv`, then complete the full 1996 and 2026 top-20 cohorts.

Required fields:

```text
company
ticker
cik
cohort_name
cohort_year
comparison_point
filing_form
filing_date
accession
source_path
control_type
founder_or_family_names
founder_executive_role
founder_board_role
economic_ownership_pct
voting_power_pct
control_mechanism
controlled_company_status
control_signal
evidence_chunk_ids
evidence_excerpt
confidence
notes
```

`control_type` should use this controlled vocabulary:

```text
founder_voting_control
founder_operator_influence
founder_family_control
predecessor_founder_continuity
professional_manager_control
institutional_single_class
state_or_other_control
unresolved
```

### Governance Table

Extract only governance fields that can be compared across eras without turning the project into a legal treatise.

Required fields:

```text
company
ticker
cohort_name
cohort_year
filing_form
filing_date
accession
share_classes
director_election_structure
board_independence_signal
committee_independence_signal
classified_board_or_staggered_terms
proxy_access_or_shareholder_nomination_rights
takeover_defense_signal
auditor
evidence_chunk_ids
evidence_excerpt
confidence
notes
```

Do not overfit this table to modern proxy language. If a 1996 filing does not disclose a modern governance concept, mark it as `not_disclosed`, not `absent`.

### Operating Profile Table

Use 10-Ks, 20-Fs where applicable, annual reports, or annual-report sections attached to the proxy package when available.

Required fields:

```text
company
ticker
cohort_name
cohort_year
filing_form
filing_date
accession
revenue
operating_income
net_income
gross_margin
operating_margin
r_and_d_expense
r_and_d_intensity
capex
capex_intensity
employees
segment_mix_summary
geographic_mix_summary
evidence_chunk_ids
evidence_excerpt
confidence
notes
```

The table should use disclosed values first. Derived margins or intensities are allowed only when numerator and denominator both come from the same filing period and the calculation is recorded in `notes`.

### Capital Allocation Table

Required fields:

```text
company
ticker
cohort_name
cohort_year
filing_form
filing_date
accession
dividends
share_repurchases
cash_and_equivalents
marketable_securities
total_debt
major_acquisition_signal
capital_allocation_summary
evidence_chunk_ids
evidence_excerpt
confidence
notes
```

This table should explain the cash-flow posture of dominance. It should not try to reconstruct every acquisition or payout event.

### KPI Disclosure Table

Use EdgarPack `which` and targeted section review to discover recurring company-specific metrics.

Required fields:

```text
company
ticker
cohort_name
cohort_year
filing_form
filing_date
accession
kpi_name
kpi_value
kpi_unit
kpi_section
kpi_category
evidence_chunk_ids
evidence_excerpt
confidence
notes
```

KPI categories:

```text
user_or_customer_scale
unit_volume
store_or_location_count
production_or_capacity
advertising_or_platform_metric
financial_services_metric
segment_metric
none_disclosed
unresolved
```

## Archetype Layer

The report should classify companies after evidence extraction, not before.

Likely archetypes to test:

- Founder-controlled platforms: companies where founders retain formal voting control through high-vote shares or voting agreements.
- Founder-led but not founder-controlled: companies where a founder remains the central operator but does not hold majority voting control.
- Founder-origin institutional tech: companies with founder mythology but current single-class institutional governance.
- Founder or family controlled non-tech dominance: companies where founder-family ownership remains a control or influence block.
- Manager-controlled old-line incumbents: mature companies with dispersed ownership and professional management.
- Predecessor-founder continuity: current companies where founder influence comes through a predecessor entity or major acquired business.

The final `architecture-archetypes.csv` should include:

```text
company
ticker
cohort_name
cohort_year
assigned_archetype
control_rationale
governance_rationale
operating_rationale
capital_allocation_rationale
kpi_rationale
evidence_row_refs
confidence
notes
```

## Narrative Report Shape

The narrative should make an argument. It should not simply summarize every table.

Recommended structure:

```text
Opening thesis
What changed in who controls dominance
What changed in the governance bargain
What changed in the operating machine
What changed in capital allocation
What changed in what investors are asked to track
Company archetypes
Cases that break the simple story
Limits and next work
```

The opening thesis should be willing to take a position if the evidence supports it. A likely version to test:

```text
The shift from 1996 to 2026 is not just a shift from old economy to technology. It is a shift from mature, manager-controlled institutions toward a mixed regime: institutionally governed mega-cap technology on one side, and founder-controlled or founder-led platforms on the other. The public investor bargain changed from owning dispersed claims on mature corporate machines to owning claims on companies where control, reinvestment, and disclosed KPIs vary much more sharply by business model.
```

Do not force this thesis if the full evidence table contradicts it.

## Evidence Policy

Every factual claim in the report must trace to one of:

- an evidence row with chunk IDs,
- a raw SEC line anchor for old filings where EdgarPack cannot yet build parsed chunks,
- a cohort source citation used only for membership or market-cap rank.

Interpretive claims must name their evidence base. Avoid uncited claims about culture, strategy, or investor expectations unless the filing says it.

Search may locate sections. Search is not evidence by itself.

## Execution Workflow

Start with the already built founder-control validation slice.

Then proceed in this order:

- Complete the control table for all 40 primary cohort rows.
- Fill governance fields for the same 40 rows from proxies or annual governance disclosures.
- Fill operating-profile fields from the nearest annual filing for each cohort year.
- Fill capital-allocation fields from the same annual filing period where possible.
- Run KPI discovery with `which`, then manually validate the recurring metrics.
- Assign archetypes only after the core tables are populated.
- Write the narrative from the archetype layer and cite back to rows.

This order matters. If archetypes are assigned too early, the report will start cherry-picking.

## Handling Old Filings

The existing validation pass found that some pre-2000 SEC filings build as directory-listing packs even when raw SEC text exists.

Until `edgarpack-eob` is fixed, use `raw_sec_txt` anchors for those filings. Label them clearly in `evidence-ledger.csv`. Do not pretend raw line anchors are normal chunk evidence.

## Success Criteria

The research pass succeeds when:

- the new bundle contains the full 1996 and 2026 primary cohorts;
- every table row has accession-level evidence or a documented exclusion reason;
- control, governance, operating profile, capital allocation, and KPI evidence are separated;
- archetypes are assigned from evidence rows, not intuition;
- the report makes a real argument and names cases that complicate it;
- the report can be read without opening the CSVs, but every important claim can be audited through the CSVs;
- limitations are specific enough to drive follow-up work.

## Not Building

- No new EdgarPack command.
- No dashboard.
- No non-SEC global-company acquisition.
- No attempt to exhaust every governance provision.
- No ranking of companies by "quality" or investment attractiveness.

## Minimal Version

If the full operating and KPI extraction becomes too large, ship a strong version with:

- full control table,
- full governance table,
- operating profile for revenue, operating margin, R&D intensity, capex intensity, and employees,
- capital allocation for dividends, buybacks, cash, and debt,
- KPI table only for companies where the annual filing clearly foregrounds recurring operating metrics.

That still produces a much better report than founder control alone.
