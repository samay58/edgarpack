"""Chinese SSE filing section detection.

The first China Lens slice supported STAR Market prospectuses. Listed-company
annual reports use the same ``第X节`` heading pattern but a different canonical
section vocabulary, so keep the tokenizer shared and swap the slug map by
document type.
"""

import re

from ..parse.sectionize import Section

# Chinese numeral mapping for section numbers
_CN_NUMERALS: dict[str, int] = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
    "十三": 13,
    "十四": 14,
    "十五": 15,
    "十六": 16,
    "十七": 17,
    "十八": 18,
    "十九": 19,
    "二十": 20,
}

# Canonical prospectus section map: Chinese title keyword -> (english slug, english title)
_PROSPECTUS_SECTIONS: dict[str, tuple[str, str]] = {
    "重要声明": ("ipo_declarations", "Important Declarations"),
    "概览": ("ipo_s01_overview", "Overview"),
    "本次发行概况": ("ipo_s02_offering_summary", "Offering Summary"),
    "发行人基本情况": ("ipo_s03_issuer_info", "Issuer Info"),
    "核心技术": ("ipo_s04_core_technology", "Core Technology"),
    "业务与技术": ("ipo_s05_business_technology", "Business & Technology"),
    "行业概况": ("ipo_s06_industry_overview", "Industry Overview"),
    "公司治理": ("ipo_s07_corporate_governance", "Corporate Governance"),
    "财务会计信息": ("ipo_s08_financial_info", "Financial Information"),
    "募集资金运用": ("ipo_s09_use_of_proceeds", "Use of Proceeds"),
    "风险因素": ("ipo_s10_risk_factors", "Risk Factors"),
    "其他重要事项": ("ipo_s11_other_matters", "Other Matters"),
    "备查文件": ("ipo_s12_reference_docs", "Reference Documents"),
}

_ANNUAL_REPORT_SECTIONS: dict[str, tuple[str, str]] = {
    "重要提示": ("annual_important_notice", "Important Notice"),
    "公司简介和主要财务指标": (
        "annual_s02_company_profile_key_financials",
        "Company Profile and Key Financials",
    ),
    "管理层讨论与分析": ("annual_s03_mda", "Management Discussion and Analysis"),
    "公司治理": ("annual_s04_corporate_governance", "Corporate Governance"),
    "环境与社会责任": ("annual_s05_esg", "Environmental and Social Responsibility"),
    "重要事项": ("annual_s06_important_matters", "Important Matters"),
    "股份变动及股东情况": (
        "annual_s07_share_changes_shareholders",
        "Share Changes and Shareholders",
    ),
    "优先股相关情况": ("annual_s08_preferred_shares", "Preferred Shares"),
    "债券相关情况": ("annual_s09_bonds", "Bonds"),
    "财务报告": ("annual_s10_financial_report", "Financial Report"),
}

# Backward-compatible name used by older tests/importers.
_CANONICAL_SECTIONS = _PROSPECTUS_SECTIONS

# Pattern: 第X节 Title (with optional markdown heading prefix)
_SECTION_PATTERN = re.compile(
    r"^(?:#+\s*)?第(?P<num>[一二三四五六七八九十百零]+)节\s*(?P<title>.+)$",
    re.MULTILINE,
)

# Pattern: 重要声明 (standalone heading, often before the numbered sections)
_DECLARATIONS_PATTERN = re.compile(
    r"^(?:#+\s*)?(?:\*\*)?重要声明(?:\*\*)?\s*$",
    re.MULTILINE,
)


def _cn_num_to_int(cn: str) -> int:
    """Convert Chinese numeral string to integer."""
    if cn in _CN_NUMERALS:
        return _CN_NUMERALS[cn]
    # Handle compound: e.g. 二十一 = 21
    if cn.startswith("二十"):
        rest = cn[2:]
        if not rest:
            return 20
        return 20 + _CN_NUMERALS.get(rest, 0)
    if cn.startswith("十"):
        rest = cn[1:]
        if not rest:
            return 10
        return 10 + _CN_NUMERALS.get(rest, 0)
    return 0


def _section_map_for(document_type: str) -> dict[str, tuple[str, str]]:
    normalized = document_type.upper().replace("_", "-")
    if normalized in {"ANNUAL-REPORT", "ANNUAL"}:
        return _ANNUAL_REPORT_SECTIONS
    return _PROSPECTUS_SECTIONS


def _slug_prefix_for(document_type: str, section_num: int | None) -> str:
    normalized = document_type.upper().replace("_", "-")
    if normalized in {"ANNUAL-REPORT", "ANNUAL"}:
        return f"annual_s{section_num:02d}" if section_num else "annual_other"
    return f"ipo_s{section_num:02d}" if section_num else "ipo_other"


def _slug_for_title(
    title: str,
    section_num: int | None,
    document_type: str = "IPO-PROSPECTUS",
) -> tuple[str, str]:
    """Return (slug, english_title) for a Chinese section title.

    First checks canonical map, then falls back to pypinyin transliteration.
    """
    title_clean = title.strip()

    # Check canonical map
    for keyword, (slug, en_title) in _section_map_for(document_type).items():
        if keyword in title_clean:
            return slug, en_title

    # Fallback: use pypinyin for romanization
    prefix = _slug_prefix_for(document_type, section_num)
    try:
        from pypinyin import lazy_pinyin

        pinyin = "_".join(lazy_pinyin(title_clean))
        # Clean slug
        pinyin = re.sub(r"[^a-z0-9_]", "", pinyin.lower())
        pinyin = re.sub(r"_+", "_", pinyin).strip("_")
        if pinyin:
            return f"{prefix}_{pinyin[:30]}", title_clean
    except ImportError:
        pass

    return prefix, title_clean


def find_sections_cn(markdown: str, document_type: str = "IPO-PROSPECTUS") -> list[Section]:
    """Find sections in a Chinese SSE filing.

    Args:
        markdown: Full markdown text of the filing.
        document_type: ``IPO-PROSPECTUS`` or ``ANNUAL-REPORT``.

    Returns:
        List of Section objects with Chinese content preserved.
    """
    matches: list[tuple[int, int, str, str]] = []  # (char_pos, num, slug, title)

    # Find 重要声明 (Important Declarations) - often before numbered sections
    for m in _DECLARATIONS_PATTERN.finditer(markdown):
        slug, en_title = _section_map_for(document_type).get(
            "重要声明", ("ipo_declarations", "Important Declarations")
        )
        matches.append((m.start(), 0, slug, en_title))

    # Find 第X节 sections
    for m in _SECTION_PATTERN.finditer(markdown):
        cn_num = m.group("num")
        title = m.group("title").strip()
        section_num = _cn_num_to_int(cn_num)
        slug, en_title = _slug_for_title(title, section_num, document_type=document_type)
        matches.append((m.start(), section_num, slug, en_title))

    # Sort by position
    matches.sort(key=lambda x: x[0])

    if not matches:
        return [
            Section(
                id="unknown_01",
                title="Unknown Section",
                content=markdown,
                char_start=0,
                char_end=len(markdown),
                warnings=["No section headings detected in Chinese filing"],
            )
        ]

    sections: list[Section] = []
    total_len = len(markdown)

    # Preamble before first section
    first_pos = matches[0][0]
    if first_pos > 0:
        preamble = markdown[:first_pos].strip()
        if preamble and len(preamble) > 100:
            sections.append(
                Section(
                    id="unknown_00",
                    title="Preamble",
                    content=preamble,
                    char_start=0,
                    char_end=first_pos,
                    warnings=["Content before first detected section"],
                )
            )

    # Create sections from matches
    for i, (char_pos, _num, slug, en_title) in enumerate(matches):
        char_end = matches[i + 1][0] if i + 1 < len(matches) else total_len
        content = markdown[char_pos:char_end].strip()

        sections.append(
            Section(
                id=slug,
                title=en_title,
                content=content,
                char_start=char_pos,
                char_end=char_end,
                warnings=[],
            )
        )

    # Deduplicate IDs
    seen_ids: dict[str, int] = {}
    for section in sections:
        if section.id in seen_ids:
            seen_ids[section.id] += 1
            section.id = f"{section.id}_{seen_ids[section.id]}"
        else:
            seen_ids[section.id] = 0

    return sections
