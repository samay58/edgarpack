"""Extract topics from filing text using domain-specific patterns (no LLM)."""

from __future__ import annotations

import re

# Risk category patterns (matched against section headings and content)
_RISK_PATTERNS: dict[str, list[re.Pattern]] = {
    "export_controls": [
        re.compile(r"export\s+control", re.I),
        re.compile(r"export\s+restriction", re.I),
        re.compile(r"trade\s+sanction", re.I),
        re.compile(r"export\s+licen[sc]e", re.I),
        # EAR/ITAR as whole words only to avoid false matches
        re.compile(r"\bEAR\b(?!\s+(?:of|for|to)\b)", re.I),
        re.compile(r"\bITAR\b", re.I),
    ],
    "cybersecurity": [
        re.compile(r"cyber\s*security", re.I),
        re.compile(r"data\s+breach", re.I),
        re.compile(r"ransomware", re.I),
        re.compile(r"cyber\s*attack", re.I),
        re.compile(r"information\s+security", re.I),
    ],
    "intellectual_property": [
        re.compile(r"intellectual\s+property", re.I),
        re.compile(r"patent\s+(infringement|litigation|portfolio)", re.I),
        re.compile(r"trade\s+secret", re.I),
        re.compile(r"proprietary\s+technology", re.I),
    ],
    "supply_chain": [
        re.compile(r"supply\s+chain", re.I),
        re.compile(r"single\s+source", re.I),
        re.compile(r"sole\s+supplier", re.I),
        re.compile(r"component\s+shortage", re.I),
        re.compile(r"manufacturing\s+(capacity|constraint)", re.I),
    ],
    "competition": [
        # Require risk/threat context to avoid "competitive advantage" positives
        re.compile(r"competit(ive|ion)\s+(risk|threat|pressure|challenge)", re.I),
        re.compile(r"(intense|significant|increasing)\s+competit", re.I),
        re.compile(r"market\s+share\s+(loss|declin|erosion)", re.I),
        re.compile(r"pricing\s+pressure", re.I),
    ],
    "regulatory": [
        # Require enough context to distinguish from passing mentions
        re.compile(r"regulatory\s+(risk|burden|change|requirement|compliance|uncertainty)", re.I),
        re.compile(r"new\s+regulat(ory|ion)", re.I),
        re.compile(r"compliance\s+requirement", re.I),
        re.compile(r"government\s+regulation", re.I),
    ],
    "china_risk": [
        # Require risk/restriction context; avoid matching "China revenue grew"
        re.compile(r"China\s+(risk|restriction|regulation|sanction|ban)", re.I),
        re.compile(r"Chinese\s+government", re.I),
        re.compile(r"\bPRC\s+(regulat|restrict|government)", re.I),
        re.compile(r"geopolit", re.I),
        re.compile(r"U\.S\.\s*-\s*China", re.I),
    ],
    "ai_risk": [
        re.compile(r"artificial\s+intelligence", re.I),
        re.compile(r"\bAI\s+(regulat|govern|ethic|bias|safety)", re.I),
        re.compile(r"machine\s+learning\s+risk", re.I),
    ],
    "climate": [
        re.compile(r"climate\s+(change|risk|related)", re.I),
        re.compile(r"greenhouse\s+gas", re.I),
        re.compile(r"carbon\s+(emission|footprint|neutral)", re.I),
        re.compile(r"sustainability", re.I),
    ],
}

# Financial concept patterns (GAAP terminology)
_FINANCIAL_PATTERNS: dict[str, list[re.Pattern]] = {
    "revenue_recognition": [
        re.compile(r"revenue\s+recognition", re.I),
        re.compile(r"ASC\s+606", re.I),
        re.compile(r"performance\s+obligation", re.I),
    ],
    "goodwill": [
        re.compile(r"goodwill\s+(impairment|assessment|test)", re.I),
        re.compile(r"intangible\s+asset", re.I),
    ],
    "leases": [
        re.compile(r"operating\s+lease", re.I),
        re.compile(r"ASC\s+842", re.I),
        re.compile(r"right-of-use\s+asset", re.I),
    ],
    "stock_compensation": [
        re.compile(r"stock-based\s+compensation", re.I),
        re.compile(r"share-based\s+(compensation|payment)", re.I),
        re.compile(r"RSU|restricted\s+stock\s+unit", re.I),
    ],
    "capex": [
        re.compile(r"capital\s+expenditure", re.I),
        re.compile(r"property.{1,20}equipment", re.I),
        re.compile(r"infrastructure\s+investment", re.I),
    ],
    "debt": [
        re.compile(r"(long|short).term\s+debt", re.I),
        re.compile(r"credit\s+facility", re.I),
        re.compile(r"convertible\s+note", re.I),
        re.compile(r"revolving\s+(credit|loan)", re.I),
    ],
}

# Regulatory reference patterns
_REGULATORY_PATTERNS: dict[str, list[re.Pattern]] = {
    "sec_rules": [
        re.compile(r"SEC\s+Rule", re.I),
        re.compile(r"Regulation\s+S-[KX]", re.I),
        re.compile(r"Sarbanes-Oxley|SOX", re.I),
        re.compile(r"Dodd-Frank", re.I),
    ],
    "antitrust": [
        re.compile(r"antitrust", re.I),
        re.compile(r"FTC|Federal\s+Trade\s+Commission", re.I),
        re.compile(r"Sherman\s+Act|Clayton\s+Act", re.I),
    ],
    "privacy": [
        re.compile(r"GDPR", re.I),
        re.compile(r"CCPA|California\s+Consumer\s+Privacy", re.I),
        re.compile(r"data\s+privacy|data\s+protection", re.I),
    ],
    "chips_act": [
        re.compile(r"CHIPS\s+(and\s+Science\s+)?Act", re.I),
        re.compile(r"semiconductor\s+subsid", re.I),
    ],
}

# Industry terms from headings / bold text
_INDUSTRY_PATTERNS: dict[str, list[re.Pattern]] = {
    "datacenter": [
        re.compile(r"data\s*center", re.I),
        re.compile(r"cloud\s+(computing|infrastructure)", re.I),
        re.compile(r"hyperscale", re.I),
    ],
    "autonomous_vehicles": [
        re.compile(r"autonomous\s+(vehicle|driving)", re.I),
        re.compile(r"self-driving", re.I),
        re.compile(r"ADAS|advanced\s+driver", re.I),
    ],
    "gaming": [
        re.compile(r"gaming\s+(GPU|graphics|market|revenue)", re.I),
        re.compile(r"GeForce|Radeon|console", re.I),
    ],
    "sovereign_ai": [
        re.compile(r"sovereign\s+AI", re.I),
        re.compile(r"national\s+AI\s+(strategy|initiative)", re.I),
    ],
}


def extract_topics(text: str) -> list[str]:
    """Extract topic tags from a text chunk using pattern matching.

    Args:
        text: Filing text (section or chunk level)

    Returns:
        Sorted list of unique topic tags
    """
    topics: set[str] = set()

    all_patterns = {
        **{f"risk:{k}": v for k, v in _RISK_PATTERNS.items()},
        **{f"financial:{k}": v for k, v in _FINANCIAL_PATTERNS.items()},
        **{f"regulatory:{k}": v for k, v in _REGULATORY_PATTERNS.items()},
        **{f"industry:{k}": v for k, v in _INDUSTRY_PATTERNS.items()},
    }

    for topic, patterns in all_patterns.items():
        for pattern in patterns:
            if pattern.search(text):
                topics.add(topic)
                break

    return sorted(topics)
