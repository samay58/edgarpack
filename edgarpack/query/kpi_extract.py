"""Layer B of the self-heal stack: extract industry KPIs from pack prose.

Layer A (self_heal.py) handles GAAP concept drift within XBRL. Layer B
handles metrics that exist only in management prose and segment tables:
ARR, NRR, RPO, DAU, GMV, same-store sales, and so on.

See docs/superpowers/specs/2026-04-11-self-heal-v2-layer-b-design.md for
the full design rationale.

Entry point: try_extract_kpi(metric, cik, company, period, ...).

Resolution order inside this module:
    1. KPI_CATALOG lookup (fail fast if metric isn't a known KPI)
    2. _resolve_filing_for_period: find the pack that represents the period
    3. _select_sections: read manifest, filter to MD&A + key-metrics
    4. _read_section_text: concat markdown from disk
    5. _trim_to_budget: stay under the LLM token budget
    6. _build_extraction_prompt: tight prompt with KPI phrases + text
    7. _extract_via_llm: subprocess to codex/claude, parse JSON
    8. _verify_excerpt_in_text: anti-hallucination substring check
    9. _build_cited_from_extraction: CitedValue with excerpt_text and badge
    10. _verify_against_prior_filing: recursive order-of-magnitude check
    11. Persist to learned_concepts with accession key
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KpiDef:
    """Metadata about a hand-curated KPI the extractor knows how to look for.

    phrases: the forms the LLM should search for in prose. Multiple forms
        are useful because companies use different phrasings (e.g. 'ARR' in
        one filing and 'annual recurring revenue' in another).
    unit_hint: the expected unit type. The LLM is told this so it can
        normalize or reject mismatched units.
    industry: SIC prefix tuple. Empty tuple means 'all industries'. Not
        used by the v2 selector but recorded for a future industry-aware
        suggester.
    description: human-readable description for `edgarpack learned show`.
    """

    phrases: tuple[str, ...]
    unit_hint: str
    industry: tuple[str, ...] = field(default=())
    description: str = ""


KPI_CATALOG: dict[str, KpiDef] = {
    # SaaS / subscription
    "arr": KpiDef(
        phrases=("annual recurring revenue", "ARR", "ending ARR",
                 "ARR of approximately"),
        unit_hint="USD",
        description="Annualized subscription revenue at period end.",
    ),
    "nrr": KpiDef(
        phrases=("net revenue retention", "dollar-based net retention",
                 "net dollar retention", "NRR", "NDR"),
        unit_hint="percent",
        description="Cohort-based revenue retention, typically >100% for healthy SaaS.",
    ),
    "grr": KpiDef(
        phrases=("gross revenue retention", "GRR", "gross dollar retention"),
        unit_hint="percent",
    ),
    "rpo": KpiDef(
        phrases=("remaining performance obligations", "RPO"),
        unit_hint="USD",
    ),
    "crpo": KpiDef(
        phrases=("current remaining performance obligations", "cRPO",
                 "current RPO"),
        unit_hint="USD",
    ),
    "billings": KpiDef(
        phrases=("calculated billings", "total billings", "non-GAAP billings"),
        unit_hint="USD",
    ),
    "subscription_rev": KpiDef(
        phrases=("subscription revenue",),
        unit_hint="USD",
    ),
    "customer_count": KpiDef(
        phrases=("total customers", "number of customers",
                 "customers with ARR over"),
        unit_hint="count",
    ),
    # Consumer / internet
    "dau": KpiDef(
        phrases=("daily active users", "DAU"),
        unit_hint="count",
    ),
    "mau": KpiDef(
        phrases=("monthly active users", "MAU"),
        unit_hint="count",
    ),
    "qau": KpiDef(
        phrases=("quarterly active users", "QAU"),
        unit_hint="count",
    ),
    "arpu": KpiDef(
        phrases=("average revenue per user", "ARPU"),
        unit_hint="USD",
    ),
    "arppu": KpiDef(
        phrases=("average revenue per paying user", "ARPPU"),
        unit_hint="USD",
    ),
    "paying_users": KpiDef(
        phrases=("paying users", "paid users", "paying subscribers"),
        unit_hint="count",
    ),

    # Marketplace / platform
    "gmv": KpiDef(
        phrases=("gross merchandise volume", "GMV", "gross transaction value",
                 "gross booking value"),
        unit_hint="USD",
    ),
    "gross_bookings": KpiDef(
        phrases=("gross bookings",),
        unit_hint="USD",
    ),
    "take_rate": KpiDef(
        phrases=("take rate", "net take rate", "effective take rate"),
        unit_hint="percent",
    ),
    "transactions": KpiDef(
        phrases=("number of transactions", "total transactions",
                 "transactions processed"),
        unit_hint="count",
    ),

    # Retail / consumer goods
    "same_store_sales": KpiDef(
        phrases=("same-store sales", "comparable store sales",
                 "comparable sales"),
        unit_hint="percent",
    ),
    "store_count": KpiDef(
        phrases=("number of stores", "total stores", "store count"),
        unit_hint="count",
    ),
    "avg_ticket": KpiDef(
        phrases=("average ticket", "average transaction value", "average check"),
        unit_hint="USD",
    ),

    # Fintech / payments
    "tpv": KpiDef(
        phrases=("total payment volume", "TPV", "payment volume"),
        unit_hint="USD",
    ),
    "active_accounts": KpiDef(
        phrases=("active accounts", "active customer accounts"),
        unit_hint="count",
    ),
    "aum": KpiDef(
        phrases=("assets under management", "AUM"),
        unit_hint="USD",
    ),
    "aua": KpiDef(
        phrases=("assets under administration", "AUA"),
        unit_hint="USD",
    ),
}
