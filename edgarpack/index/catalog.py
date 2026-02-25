"""Hierarchical topic catalog."""

from __future__ import annotations

from pydantic import BaseModel


class TopicCategory(BaseModel):
    """A topic category in the catalog."""

    name: str
    description: str
    topics: list[str]


TOPIC_CATALOG: list[TopicCategory] = [
    TopicCategory(
        name="Risk Factors",
        description="Categories of risk disclosed in SEC filings",
        topics=[
            "risk:export_controls",
            "risk:cybersecurity",
            "risk:intellectual_property",
            "risk:supply_chain",
            "risk:competition",
            "risk:regulatory",
            "risk:china_risk",
            "risk:ai_risk",
            "risk:climate",
        ],
    ),
    TopicCategory(
        name="Financial Concepts",
        description="Accounting and financial reporting topics",
        topics=[
            "financial:revenue_recognition",
            "financial:goodwill",
            "financial:leases",
            "financial:stock_compensation",
            "financial:capex",
            "financial:debt",
        ],
    ),
    TopicCategory(
        name="Regulatory",
        description="Laws, regulations, and compliance frameworks",
        topics=[
            "regulatory:sec_rules",
            "regulatory:antitrust",
            "regulatory:privacy",
            "regulatory:chips_act",
        ],
    ),
    TopicCategory(
        name="Industry",
        description="Industry and technology verticals",
        topics=[
            "industry:datacenter",
            "industry:autonomous_vehicles",
            "industry:gaming",
            "industry:sovereign_ai",
        ],
    ),
]


def get_category_for_topic(topic: str) -> str | None:
    """Get the parent category name for a topic tag."""
    for cat in TOPIC_CATALOG:
        if topic in cat.topics:
            return cat.name
    return None


def list_all_topics() -> list[str]:
    """Return a flat list of all known topic tags."""
    topics: list[str] = []
    for cat in TOPIC_CATALOG:
        topics.extend(cat.topics)
    return topics
