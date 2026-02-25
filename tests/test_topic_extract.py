"""Tests for topic extraction."""

from edgarpack.index.topic_extract import extract_topics


def test_export_controls():
    text = "The company is subject to U.S. export control regulations."
    topics = extract_topics(text)
    assert "risk:export_controls" in topics


def test_cybersecurity():
    text = "We face cybersecurity risks including data breaches and ransomware attacks."
    topics = extract_topics(text)
    assert "risk:cybersecurity" in topics


def test_supply_chain():
    text = "Our supply chain is dependent on a single source supplier for key components."
    topics = extract_topics(text)
    assert "risk:supply_chain" in topics


def test_china_risk():
    text = "U.S.-China trade tensions and PRC government policies affect our operations."
    topics = extract_topics(text)
    assert "risk:china_risk" in topics


def test_revenue_recognition():
    text = "We recognize revenue in accordance with ASC 606 and performance obligations."
    topics = extract_topics(text)
    assert "financial:revenue_recognition" in topics


def test_chips_act():
    text = "The CHIPS and Science Act provides semiconductor subsidies."
    topics = extract_topics(text)
    assert "regulatory:chips_act" in topics


def test_datacenter():
    text = "Revenue from data center and cloud computing infrastructure grew significantly."
    topics = extract_topics(text)
    assert "industry:datacenter" in topics


def test_multiple_topics():
    text = (
        "Our data center business grew significantly. "
        "We face export control restrictions on AI chips to China. "
        "Cybersecurity remains a key risk. "
        "Revenue recognition under ASC 606 applies."
    )
    topics = extract_topics(text)
    assert len(topics) >= 4
    assert "industry:datacenter" in topics
    assert "risk:export_controls" in topics
    assert "risk:cybersecurity" in topics
    assert "financial:revenue_recognition" in topics


def test_no_topics():
    text = "The weather was nice today."
    topics = extract_topics(text)
    assert len(topics) == 0


def test_ai_risk():
    text = "Artificial intelligence regulation and AI governance pose emerging risks."
    topics = extract_topics(text)
    assert "risk:ai_risk" in topics


def test_climate():
    text = "Climate change risks and greenhouse gas emission reduction targets."
    topics = extract_topics(text)
    assert "risk:climate" in topics


def test_privacy():
    text = "We comply with GDPR, CCPA, and other data privacy regulations."
    topics = extract_topics(text)
    assert "regulatory:privacy" in topics
