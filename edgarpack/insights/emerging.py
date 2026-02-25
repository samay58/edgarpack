"""Emerging topic detection: topics appearing in more filings this period vs. last."""

from __future__ import annotations

import json

from pydantic import BaseModel

from ..index.inverted import SearchIndex


class EmergingTopic(BaseModel):
    """A topic gaining prevalence across filings."""

    topic: str
    current_count: int
    prior_count: int
    growth_ratio: float
    example_companies: list[str]


def detect_emerging_topics(
    index: SearchIndex,
    current_cutoff: str,
    prior_cutoff: str,
    min_current_count: int = 3,
) -> list[EmergingTopic]:
    """Find topics that appear in more filings in the current period than the prior.

    Args:
        index: SearchIndex instance
        current_cutoff: ISO date string dividing current/prior periods (e.g. "2024-06-01")
        prior_cutoff: ISO date string for start of prior period (e.g. "2023-06-01")
        min_current_count: Minimum appearances in current period to report

    Returns:
        List of EmergingTopic sorted by growth ratio (descending)
    """
    conn = index._get_conn()

    # Count topic occurrences in current period
    current_rows = conn.execute(
        "SELECT topics_json, ticker FROM chunks WHERE filing_date >= ?",
        (current_cutoff,),
    ).fetchall()

    # Count topic occurrences in prior period
    prior_rows = conn.execute(
        "SELECT topics_json, ticker FROM chunks WHERE filing_date >= ? AND filing_date < ?",
        (prior_cutoff, current_cutoff),
    ).fetchall()

    def _count_topics(rows: list) -> tuple[dict[str, int], dict[str, set[str]]]:
        counts: dict[str, int] = {}
        companies: dict[str, set[str]] = {}
        for row in rows:
            topics = json.loads(row["topics_json"]) if row["topics_json"] else []
            ticker = row["ticker"] or ""
            for t in topics:
                counts[t] = counts.get(t, 0) + 1
                if t not in companies:
                    companies[t] = set()
                companies[t].add(ticker)
        return counts, companies

    current_counts, current_companies = _count_topics(current_rows)
    prior_counts, _ = _count_topics(prior_rows)

    emerging: list[EmergingTopic] = []
    for topic, current_n in current_counts.items():
        if current_n < min_current_count:
            continue

        prior_n = prior_counts.get(topic, 0)
        if prior_n == 0:
            growth = float(current_n)
        else:
            growth = current_n / prior_n

        if growth > 1.0:
            example = sorted(current_companies.get(topic, set()))[:5]
            emerging.append(
                EmergingTopic(
                    topic=topic,
                    current_count=current_n,
                    prior_count=prior_n,
                    growth_ratio=growth,
                    example_companies=example,
                )
            )

    emerging.sort(key=lambda e: e.growth_ratio, reverse=True)
    return emerging
