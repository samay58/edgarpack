"""Section-aware translation routing.

Routes SSE prospectus sections to different translation strategies based on
section IDs from sectionize_cn.py.
"""

from __future__ import annotations

import asyncio
import re

from ..translate.deepinfra import DeepInfraTranslator
from ..translate.numbers import restore_numbers, tag_numbers
from ..translate.provider import TranslationResult

# Section-specific extra prompt instructions
_SECTION_PROMPTS: dict[str, str] = {
    "ipo_declarations": (
        "This is a standard regulatory declarations section. "
        "Translate formally and precisely. Legal accuracy is paramount."
    ),
    "ipo_s08_financial_info": (
        "This section contains financial statements and tables. "
        "Preserve all table formatting exactly. Use standard English accounting "
        "terminology. Row headers must match the glossary precisely."
    ),
    "ipo_s10_risk_factors": (
        "This section contains legal risk disclosures. "
        "Translate with legal precision. Preserve the cautionary tone. "
        "Do not soften or editorialize risk language."
    ),
    "ipo_s04_core_technology": (
        "This section describes the company's core technology and R&D. "
        "Translate technical terms accurately. Preserve specificity of "
        "technical claims and metrics."
    ),
    "ipo_s05_business_technology": (
        "This section covers business operations and technology details. "
        "Balance technical accuracy with readability for investors."
    ),
    "ipo_s06_industry_overview": (
        "This section provides industry and market context. "
        "Translate market size figures and growth rates precisely. "
        "Keep data source attributions intact."
    ),
}

# Sections with nearly identical boilerplate across STAR Market IPOs
_TEMPLATE_SECTIONS = frozenset({"ipo_declarations"})
_TABLE_SEPARATOR_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^(?P<prefix>\s{0,3}#{1,6}\s+)(?P<body>.+?)\s*$")
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_CHINESE_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
_ENUM_PREFIX_RE = re.compile(r"^[（(]?[一二三四五六七八九十]+[)）]?[、.]?")
_DATE_CELL_RE = re.compile(r"^(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日$")
_YEAR_MONTH_DATE_CELL_RE = re.compile(r"^(?P<year>\d{4})年(?P<month>\d{1,2})月$")
_YEAR_ONLY_DATE_CELL_RE = re.compile(r"^(?P<year>\d{4})年$")
_REPORTING_PERIOD_RE = re.compile(
    r"^(?P<year>\*{0,2}\d{4}\*{0,2})\s*年\s*(?P<period>\*{0,2}\d{1,2}-\d{1,2}\*{0,2})\s*月$"
)
_PLAIN_YEAR_RE = re.compile(r"^(?P<year>\*{0,2}\d{4}\*{0,2})\s*年$")
_PERIOD_ONLY_RE = re.compile(r"^(?P<period>\*{0,2}\d{1,2}-\d{1,2}\*{0,2})\s*月$")
_YEAR_TOKEN_RE = re.compile(r"^(?P<year>\*{0,2}\d{4}\*{0,2})$")
_FISCAL_YEAR_TOKEN_RE = re.compile(r"^\*{0,2}年度\*{0,2}$")
_FISCAL_YEAR_RE = re.compile(r"^(?P<year>\*{0,2}\d{4}\*{0,2})\s*年度$")
_INLINE_DATE_RE = re.compile(
    r"(?P<year>\*{0,2}\d{4}\*{0,2})\s*年\s*"
    r"(?P<month>\*{0,2}\d{1,2}\*{0,2})\s*月"
    r"(?:\s*(?P<day>\*{0,2}\d{1,2}\*{0,2})\s*日)?"
)
_INLINE_REPORTING_PERIOD_RE = re.compile(
    r"(?P<year>\*{0,2}\d{4}\*{0,2})\s*年\s*"
    r"(?P<period>\*{0,2}\d{1,2}-\d{1,2}\*{0,2})\s*月"
)
_INLINE_FISCAL_YEAR_RE = re.compile(r"(?P<year>\*{0,2}\d{4}\*{0,2})\s*年度")
_PERCENT_LIST_ENTRY_RE = re.compile(
    r"^\s*(?P<label>[^:：;；%]+?)\s*(?:[：:]\s*)?(?P<value>-?\d+(?:\.\d+)?)%\s*$"
)
_KEY_VALUE_LINE_RE = re.compile(r"^[^:：]{1,80}[：:].+$")
_SPLIT_DATE_PREFIX_RE = re.compile(r"^(?P<prefix>.*?\d{4}\s*年)\s*(?P<month_tens>\d)\s*$")
_SPLIT_DATE_SUFFIX_RE = re.compile(r"^(?P<month_ones>\d)\s*月\s*(?P<day>\d{1,2})\s*日(?P<rest>.*)$")
_SOURCE_YEAR_RE = re.compile(r"(?P<year>\d{4})\s*年")
_AGE_RANGE_LABEL_RE = re.compile(
    r"^(?P<start>\d+)-(?P<end>\d+)岁[（(]含(?P=start)岁，不含(?P=end)岁[）)]$"
)
_AGE_UNDER_LABEL_RE = re.compile(r"^(?P<age>\d+)岁以下[（(]不含(?P=age)岁[）)]$")
_AGE_AND_ABOVE_LABEL_RE = re.compile(r"^(?P<age>\d+)岁及以上$")
ROUTER_VERSION = "v16"
_PLACEHOLDER_CELL_TRANSLATIONS: dict[str, str] = {
    "【】年【】月【】日": "[]-[]-[]",
    "【】元": "[] yuan",
    "【】万元": "[] ten thousand yuan",
    "【】股": "[] shares",
}
_SPECIAL_TABLE_LABELS: dict[str, str] = {
    "项目": "Item",
    "单位：万元": "Unit: RMB 10,000",
    "单位:万元": "Unit: RMB 10,000",
    "单位：元": "Unit: RMB",
    "单位:元": "Unit: RMB",
    "是": "Yes",
    "否": "No",
    "不适用": "N/A",
    "合计": "Total",
    "流动资产：": "Current Assets:",
    "非流动资产：": "Non-current Assets:",
    "流动负债：": "Current Liabilities:",
    "非流动负债：": "Non-current Liabilities:",
    "所有者权益：": "Shareholders' Equity:",
    "负债和所有者权益总计": "Total Liabilities and Shareholders' Equity",
    "少数股东损益": "Profit/Loss Attributable to Minority Interest",
    "私募基金名称": "Private Equity Fund Name",
    "投资协议签署时点": "Investment Agreement Signing Date",
    "投资目的": "Investment Purpose",
    "拟投资总额": "Proposed Total Investment",
    "报告期内投资金额": "Investment Amount During the Reporting Period",
    "截至报告期末已投资金额": "Invested Amount as of the End of the Reporting Period",
    "参与身份": "Participation Capacity",
    "报告期末出资比例（%）": "Capital Contribution Ratio at Period End (%)",
    "是否控制该基金或施加重大影响": (
        "Whether the Fund Is Controlled or Subject to Significant Influence"
    ),
    "会计核算科目": "Accounting Account",
    "是否存在关联关系": "Whether a Related-party Relationship Exists",
    "基金底层资产情况": "Underlying Assets of the Fund",
    "报告期利润影响": "Impact on Profit for the Reporting Period",
    "累计利润影响": "Cumulative Impact on Profit",
    "获得投资回报": "Obtain Investment Returns",
    "有限合伙人": "Limited Partner",
    "其他非流动金融资产": "Other Non-current Financial Assets",
}
_PREFIX_TRANSLATIONS: dict[str, str] = {
    "其中：": "Of which: ",
    "其中": "Of which ",
    "加：": "Add: ",
    "减：": "Less: ",
}
_ENTITY_NAME_HINT_RE = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|株式会社|合伙企业|有限合伙|"
    r"私募股权投资基金|股权投资基金|私募基金|投资基金|基金|集团|公司)"
)
_ENTITY_TERM_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("私募股权投资基金", "Private Equity Investment Fund"),
    ("股权投资基金", "Equity Investment Fund"),
    ("投资基金", "Investment Fund"),
    ("私募基金", "Private Fund"),
    ("股份有限公司", "Co., Ltd."),
    ("有限责任公司", "Co., Ltd."),
    ("有限公司", "Co., Ltd."),
    ("株式会社", "Corporation"),
    ("合伙企业", "Partnership"),
    ("有限合伙", "Limited Partnership"),
    ("中金", "CICC"),
    ("新兴", "Emerging"),
    ("青岛", "Qingdao"),
    ("成都", "Chengdu"),
    ("投资", "Investment"),
    ("科技", "Technology"),
    ("证券", "Securities"),
    ("银行", "Bank"),
    ("集团", "Group"),
    ("基金", "Fund"),
    ("公司", "Company"),
)
_FUND_UNDERLYING_ASSETS_RE = re.compile(
    r"^该基金处于投资期，截至报告期末，已投资(?P<invested>\d+)个项目"
    r"(?:，已退出(?P<exited>\d+)个项目)?$"
)


class SectionRouter:
    """Routes section content to appropriate translation strategies.

    Wraps a DeepInfraTranslator and selects per-section system prompts
    based on section IDs from the Chinese sectionizer.
    """

    def __init__(self, translator: DeepInfraTranslator) -> None:
        self._translator = translator
        self._template_cache: dict[str, TranslationResult] = {}
        self._table_cell_cache: dict[tuple[str, bool], str] = {}

    @property
    def provider(self) -> str:
        return self._translator.provider

    async def translate_section(
        self,
        section_id: str,
        paragraphs: list[str],
        strict: bool = False,
    ) -> list[TranslationResult]:
        """Translate all paragraphs in a section using the appropriate strategy."""
        extra = _SECTION_PROMPTS.get(section_id, "")
        if strict:
            extra = (
                extra + " Strict mode: do not leave Chinese text in the English output. "
                "Never summarize, fabricate, or normalize data. Preserve literal tokens exactly."
            )
        system_prompt = self._translator.build_system_prompt(extra)
        results: list[TranslationResult | None] = [None] * len(paragraphs)
        llm_indices: list[int] = []
        llm_paragraphs: list[str] = []

        for index, paragraph in enumerate(paragraphs):
            if self._is_markdown_heading(paragraph):
                results[index] = await self._translate_heading_paragraph(paragraph, strict=strict)
            elif self._is_flattened_catalog_paragraph(paragraph):
                results[index] = await self._translate_flattened_catalog_paragraph(
                    paragraph,
                    strict=strict,
                )
            elif self._is_markdown_table(paragraph):
                results[index] = await self._translate_table_paragraph(paragraph, strict=strict)
            else:
                llm_indices.append(index)
                llm_paragraphs.append(paragraph)

        if llm_paragraphs:
            llm_results = await self._translator.translate_batch(
                llm_paragraphs,
                system_prompt=system_prompt,
            )
            for index, result in zip(llm_indices, llm_results):
                results[index] = result

        return [result for result in results if result is not None]

    def get_strategy_name(self, section_id: str) -> str:
        """Return the translation strategy name for a section."""
        if section_id in _TEMPLATE_SECTIONS:
            return "template_cache"
        if section_id in _SECTION_PROMPTS:
            return "specialized"
        return "standard"

    def _is_numeric_heavy_markdown_table(self, paragraph: str) -> bool:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        rows = [line for line in lines if line.startswith("|") and line.endswith("|")]
        if len(rows) < 2:
            return False

        total_cells = 0
        structured_cells = 0
        for row in rows:
            cells = row.split("|")[1:-1]
            if not cells:
                continue
            if all(
                not cell.strip() or _TABLE_SEPARATOR_RE.fullmatch(cell.strip()) for cell in cells
            ):
                continue
            for cell in cells[1:]:
                total_cells += 1
                if self._is_structured_table_value(cell):
                    structured_cells += 1

        return total_cells > 0 and structured_cells / total_cells >= 0.7

    def _is_markdown_table(self, paragraph: str) -> bool:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        rows = [line for line in lines if line.startswith("|") and line.endswith("|")]
        return len(rows) >= 2

    def _is_markdown_heading(self, paragraph: str) -> bool:
        return _MARKDOWN_HEADING_RE.fullmatch(paragraph.strip()) is not None

    def _is_flattened_catalog_paragraph(self, paragraph: str) -> bool:
        normalized = re.sub(r"\s+", "", paragraph)
        return "型号产品图片主要参数核心特点" in normalized

    async def _translate_heading_paragraph(
        self,
        paragraph: str,
        strict: bool = False,
    ) -> TranslationResult:
        match = _MARKDOWN_HEADING_RE.fullmatch(paragraph.strip())
        if match is None:
            return TranslationResult(
                text_zh=paragraph,
                text_en=paragraph,
                provider=self.provider,
            )

        translated_body = await self._translate_table_label(match.group("body"), strict=strict)
        return TranslationResult(
            text_zh=paragraph,
            text_en=f"{match.group('prefix')}{translated_body}",
            provider=self.provider,
        )

    async def _translate_flattened_catalog_paragraph(
        self,
        paragraph: str,
        strict: bool = False,
    ) -> TranslationResult:
        extra = (
            "The source is a flattened OCR extract of a Chinese product comparison card or "
            "table. Reconstruct it as a clean English markdown table with these columns: "
            "Model | Key Parameters | Core Features. Do not invent image URLs, markdown "
            "image syntax, or an image column. Preserve all product names, numbers, units, "
            "and technical specifications exactly. Remove obvious OCR garbage such as "
            "~~...~~ fragments. If a field cannot be assigned confidently, leave it blank "
            "instead of inventing content."
        )
        if strict:
            extra += " Strict mode: do not leave Chinese text in the output."
        prompt = self._translator.build_system_prompt(extra)
        result = await self._translator.translate_async(
            paragraph,
            system_prompt=prompt,
            allow_markdown_artifacts=True,
        )
        return TranslationResult(
            text_zh=paragraph,
            text_en=result.text_en,
            provider=self.provider,
        )

    async def _translate_table_paragraph(
        self,
        paragraph: str,
        strict: bool = False,
    ) -> TranslationResult:
        rendered_lines: list[str | None] = []
        row_specs: list[tuple[int, list[str]]] = []
        for line in paragraph.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                rendered_lines.append(line)
                continue

            cells = stripped.split("|")[1:-1]
            cells = self._repair_split_date_row_cells(cells)
            if all(
                not cell.strip() or _TABLE_SEPARATOR_RE.fullmatch(cell.strip()) for cell in cells
            ):
                rendered_lines.append(stripped)
                continue

            rendered_lines.append(None)
            row_specs.append((len(rendered_lines) - 1, cells))

        translated_rows = await asyncio.gather(
            *(
                asyncio.gather(
                    *(
                        self._translate_table_cell(
                            cell,
                            strict=strict,
                        )
                        for cell in cells
                    )
                )
                for _, cells in row_specs
            )
        )

        for (line_index, _), translated_cells in zip(row_specs, translated_rows, strict=False):
            rendered_lines[line_index] = "|" + "|".join(translated_cells) + "|"

        return TranslationResult(
            text_zh=paragraph,
            text_en="\n".join(line for line in rendered_lines if line is not None),
            provider=self.provider,
        )

    def _repair_split_date_row_cells(self, cells: list[str]) -> list[str]:
        if len(cells) < 2:
            return cells

        stripped_cells = [cell.strip() for cell in cells]
        first_match = _SPLIT_DATE_PREFIX_RE.fullmatch(stripped_cells[0])
        second_match = _SPLIT_DATE_SUFFIX_RE.fullmatch(stripped_cells[1])
        if first_match is None or second_match is None:
            return cells

        month = int(first_match.group("month_tens") + second_match.group("month_ones"))
        day = int(second_match.group("day"))
        if month < 1 or month > 12 or day < 1 or day > 31:
            return cells

        rebuilt = f"{first_match.group('prefix')}{month}月{day}日{second_match.group('rest')}"
        repaired = cells.copy()
        repaired[0] = cells[0].replace(stripped_cells[0], rebuilt, 1)

        for index in range(1, len(cells)):
            match = _SPLIT_DATE_SUFFIX_RE.fullmatch(stripped_cells[index])
            if match is None:
                continue
            if (
                match.group("month_ones") != second_match.group("month_ones")
                or match.group("day") != second_match.group("day")
                or match.group("rest") != second_match.group("rest")
            ):
                continue
            repaired[index] = cells[index].replace(stripped_cells[index], rebuilt, 1)

        return repaired

    async def _translate_table_cell(
        self,
        cell: str,
        strict: bool = False,
    ) -> str:
        stripped = cell.strip()
        converted_period = self._convert_reporting_period_cell(stripped)
        if converted_period is not None:
            return cell.replace(stripped, converted_period, 1)
        placeholder_translation = self._translate_placeholder_cell(stripped)
        if placeholder_translation is not None:
            return cell.replace(stripped, placeholder_translation, 1)
        converted_date = self._convert_date_cell(stripped)
        if converted_date is not None:
            return cell.replace(stripped, converted_date, 1)
        converted_amount = self._convert_numeric_amount_cell(stripped)
        if converted_amount is not None:
            return cell.replace(stripped, converted_amount, 1)
        if self._should_convert_inline_period_markers(stripped):
            converted_inline = self._convert_inline_period_markers(stripped)
            if converted_inline is not None:
                cell = cell.replace(stripped, converted_inline, 1)
                stripped = converted_inline
        converted_multiline_period = self._convert_multiline_period_cell(stripped)
        if converted_multiline_period is not None:
            return cell.replace(stripped, converted_multiline_period, 1)
        percent_list_translation = await self._translate_percentage_list_cell(
            stripped,
            strict=strict,
        )
        if percent_list_translation is not None:
            return cell.replace(stripped, percent_list_translation, 1)
        multiline_translation = await self._translate_multiline_structured_cell(
            stripped,
            strict=strict,
        )
        if multiline_translation is not None:
            return cell.replace(stripped, multiline_translation, 1)
        if not stripped or self._is_structured_table_value(stripped):
            return cell
        if not _CHINESE_RE.search(stripped):
            return cell

        inner = stripped
        prefix = ""
        suffix = ""
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) >= 4:
            inner = stripped[2:-2]
            prefix = "**"
            suffix = "**"

        translated = await self._translate_table_label(inner, strict=strict)
        if translated == inner:
            return cell

        replacement = f"{prefix}{translated}{suffix}"
        return cell.replace(stripped, replacement, 1)

    def _convert_numeric_amount_cell(self, value: str) -> str | None:
        normalized = value.strip()
        if normalized.startswith("人民币"):
            normalized = normalized.removeprefix("人民币").strip()
        if normalized.endswith("人民币"):
            normalized = normalized.removesuffix("人民币").strip()

        tagged, number_tags = tag_numbers(normalized)
        if not number_tags or tagged != "<<NUM_001>>":
            return None
        return restore_numbers(tagged, number_tags)

    def _convert_date_cell(self, value: str) -> str | None:
        normalized = value.replace("<br>", "")
        match = _DATE_CELL_RE.fullmatch(normalized)
        if match is not None:
            return (
                f"{match.group('year')}-"
                f"{int(match.group('month')):02d}-"
                f"{int(match.group('day')):02d}"
            )
        year_month_match = _YEAR_MONTH_DATE_CELL_RE.fullmatch(normalized)
        if year_month_match is None:
            year_only_match = _YEAR_ONLY_DATE_CELL_RE.fullmatch(normalized)
            if year_only_match is None:
                return None
            return year_only_match.group("year")
        return f"{year_month_match.group('year')}-{int(year_month_match.group('month')):02d}"

    def _convert_reporting_period_cell(self, value: str) -> str | None:
        period_match = _REPORTING_PERIOD_RE.fullmatch(value)
        if period_match is not None:
            return f"{period_match.group('year')} {period_match.group('period')}M"

        plain_year_match = _PLAIN_YEAR_RE.fullmatch(value)
        if plain_year_match is not None:
            return plain_year_match.group("year")

        fiscal_year_match = _FISCAL_YEAR_RE.fullmatch(value)
        if fiscal_year_match is not None:
            return f"FY {fiscal_year_match.group('year')}"

        return None

    def _convert_multiline_period_cell(self, value: str) -> str | None:
        if "<br>" not in value:
            return None

        parts = [part.strip() for part in value.split("<br>")]
        if len(parts) != 2 or not all(parts):
            return None

        year = self._convert_reporting_period_cell(parts[0]) or self._convert_date_cell(parts[0])
        period_match = _PERIOD_ONLY_RE.fullmatch(parts[1])
        if year is not None and period_match is not None:
            return f"{year}<br>{period_match.group('period')}M"

        year_token_match = _YEAR_TOKEN_RE.fullmatch(parts[0])
        if year_token_match is not None and _FISCAL_YEAR_TOKEN_RE.fullmatch(parts[1]):
            return f"FY {year_token_match.group('year')}"
        return None

    def _convert_inline_period_markers(self, value: str) -> str | None:
        converted = _INLINE_DATE_RE.sub(self._replace_inline_date, value)
        converted = _INLINE_REPORTING_PERIOD_RE.sub(
            lambda match: f"{match.group('year')} {match.group('period')}M",
            converted,
        )
        converted = _INLINE_FISCAL_YEAR_RE.sub(
            lambda match: f"FY {match.group('year')}",
            converted,
        )
        if converted == value:
            return None
        return converted

    def _should_convert_inline_period_markers(self, value: str) -> bool:
        reduced = value.replace("<br>", "")
        reduced = _INLINE_DATE_RE.sub("", reduced)
        reduced = _INLINE_REPORTING_PERIOD_RE.sub("", reduced)
        reduced = _INLINE_FISCAL_YEAR_RE.sub("", reduced)
        reduced = re.sub(r"[*_/\s().:\-]+", "", reduced)
        return not _CHINESE_RE.search(reduced)

    def _replace_inline_date(self, match: re.Match[str]) -> str:
        month = _zero_pad_marked_numeric_token(match.group("month"), width=2)
        day = match.group("day")
        if day is None:
            return f"{match.group('year')}-{month}"
        return f"{match.group('year')}-{month}-{_zero_pad_marked_numeric_token(day, width=2)}"

    async def _translate_percentage_list_cell(self, value: str, strict: bool = False) -> str | None:
        lines = value.split("<br>")
        translated_lines: list[str] = []
        entry_count = 0

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            if re.fullmatch(r"[!！]+", stripped_line):
                continue

            entries = [part.strip() for part in re.split(r"[；;]", stripped_line) if part.strip()]
            if not entries:
                translated_lines.append(line)
                continue

            translated_entries: list[str] = []
            for entry in entries:
                match = _PERCENT_LIST_ENTRY_RE.fullmatch(entry)
                if match is None:
                    return None
                label = match.group("label").strip()
                translated_label = label
                if _CHINESE_RE.search(label):
                    translated_label = await self._translate_table_label(label, strict=strict)
                translated_entries.append(f"{translated_label}: {match.group('value')}%")
                entry_count += 1
            translated_lines.append("; ".join(translated_entries))

        if entry_count < 2:
            return None
        return "<br>".join(translated_lines)

    def _translate_placeholder_cell(self, value: str) -> str | None:
        return _PLACEHOLDER_CELL_TRANSLATIONS.get(value)

    async def _translate_multiline_structured_cell(
        self,
        value: str,
        strict: bool = False,
    ) -> str | None:
        if "<br>" not in value or not _CHINESE_RE.search(value):
            return None

        lines = [line.strip() for line in value.split("<br>") if line.strip()]
        if len(lines) < 2:
            return None

        structured_lines = [line for line in lines if _KEY_VALUE_LINE_RE.fullmatch(line)]
        if len(structured_lines) < 2 or len(structured_lines) * 2 < len(lines):
            return None

        translated_lines: list[str] = []
        for line in lines:
            translated_line = await self._translate_table_label(line, strict=strict)
            translated_lines.append(translated_line)
        return "<br>".join(translated_lines)

    async def _translate_table_label(
        self,
        label: str,
        strict: bool = False,
    ) -> str:
        normalized = self._normalize_table_label(label)
        if not normalized:
            return label

        translated = self._lookup_table_label(normalized)
        if translated is None and _CHINESE_RE.search(normalized):
            translated = await self._translate_table_label_via_llm(normalized, strict=strict)

        if translated is None:
            translated = self._fallback_table_label(normalized)

        if translated is None:
            return label
        return self._restore_line_breaks(label, normalized, translated)

    def _fallback_table_label(
        self,
        label: str,
    ) -> str | None:
        if not _CHINESE_RE.search(label):
            return None

        if _ENTITY_NAME_HINT_RE.search(label):
            return _translate_entity_name_fallback(label)

        return None

    async def _translate_table_label_via_llm(self, label: str, strict: bool = False) -> str | None:
        cache_key = (label, strict)
        if cache_key in self._table_cell_cache:
            return self._table_cell_cache[cache_key]

        prompt = self._translator.build_table_cell_prompt(strict=strict)
        result = await self._translator.translate_async(label, system_prompt=prompt)
        translated = result.text_en.strip()
        if not translated:
            return None

        translated = translated.splitlines()[0].strip()
        translated = translated.replace("|", "/")
        translated = _restore_missing_year_literals(label, translated)
        if _CHINESE_RE.search(translated):
            return None
        self._table_cell_cache[cache_key] = translated
        return translated

    def _lookup_table_label(self, label: str) -> str | None:
        if age_range := _AGE_RANGE_LABEL_RE.fullmatch(label):
            start = age_range.group("start")
            end = age_range.group("end")
            return f"{start}-{end} years old (including {start}, excluding {end})"

        if age_under := _AGE_UNDER_LABEL_RE.fullmatch(label):
            age = age_under.group("age")
            return f"Under {age} years old (excluding {age})"

        if age_above := _AGE_AND_ABOVE_LABEL_RE.fullmatch(label):
            age = age_above.group("age")
            return f"{age} years old and above"

        if label in _SPECIAL_TABLE_LABELS:
            return _SPECIAL_TABLE_LABELS[label]

        if underlying_assets_match := _FUND_UNDERLYING_ASSETS_RE.fullmatch(label):
            invested = underlying_assets_match.group("invested")
            exited = underlying_assets_match.group("exited")
            invested_label = "project" if invested == "1" else "projects"
            if exited is None:
                return (
                    "The fund is in the investment period; as of the end of the "
                    f"Reporting Period, it had invested in {invested} {invested_label}"
                )
            exited_label = "project" if exited == "1" else "projects"
            return (
                "The fund is in the investment period; as of the end of the "
                f"Reporting Period, it had invested in {invested} {invested_label} "
                f"and exited {exited} {exited_label}"
            )

        if glossary_match := self._translator.glossary.lookup(label):
            return glossary_match

        if label.endswith("：") or label.endswith(":"):
            base = label[:-1]
            translated_base = self._lookup_table_label(base)
            if translated_base:
                return f"{translated_base}:"

        if label.endswith("合计"):
            base = label[:-2]
            translated_base = self._lookup_table_label(base)
            if translated_base:
                return f"Total {translated_base}"

        if label.endswith("小计"):
            base = label[:-2]
            translated_base = self._lookup_table_label(base)
            if translated_base:
                return f"Subtotal of {translated_base}"

        enum_match = _ENUM_PREFIX_RE.match(label)
        if enum_match:
            translated_base = self._lookup_table_label(label[enum_match.end() :])
            if translated_base:
                return translated_base

        for prefix, translated_prefix in _PREFIX_TRANSLATIONS.items():
            if label.startswith(prefix):
                translated_base = self._lookup_table_label(label[len(prefix) :])
                if translated_base:
                    return f"{translated_prefix}{translated_base}"

        return None

    def _normalize_table_label(self, label: str) -> str:
        normalized = label.replace("<br>", "")
        normalized = normalized.replace("**", "")
        normalized = normalized.replace("__", "")
        normalized = re.sub(r"\s+", "", normalized)
        return normalized

    def _restore_line_breaks(self, original: str, normalized: str, translated: str) -> str:
        if "<br>" not in original or " " not in translated:
            return translated

        parts = original.split("<br>")
        if len(parts) != 2:
            return translated

        words = translated.split()
        if len(words) < 2:
            return translated

        ratio = len(self._normalize_table_label(parts[0])) / max(len(normalized), 1)
        running = 0
        best_index = 1
        best_distance = float("inf")
        for index in range(1, len(words)):
            running += len(words[index - 1]) + (1 if index > 1 else 0)
            distance = abs((running / max(len(translated), 1)) - ratio)
            if distance < best_distance:
                best_distance = distance
                best_index = index

        return " ".join(words[:best_index]) + "<br>" + " ".join(words[best_index:])

    def _romanize_label(self, label: str) -> str | None:
        try:
            from pypinyin import lazy_pinyin
        except ImportError:
            return None

        romanized = "_".join(lazy_pinyin(label))
        romanized = re.sub(r"[^a-z0-9_]", "", romanized.lower())
        romanized = re.sub(r"_+", "_", romanized).strip("_")
        return romanized or None

    def _is_structured_table_value(self, cell: str) -> bool:
        cleaned = cell.replace("**", "").replace("__", "").replace("<br>", "")
        cleaned = re.sub(r"\s+", "", cleaned)
        if not cleaned:
            return True

        if cleaned in {"-", "--", "---", "—", "——"}:
            return True

        structured = cleaned
        for token in (
            "人民币",
            "美元",
            "港元",
            "欧元",
            "日元",
            "万元",
            "亿元",
            "万股",
            "股",
            "元",
            "年",
            "月",
            "日",
            "度",
            "季度",
            "期",
        ):
            structured = structured.replace(token, "")

        if _CHINESE_RE.search(structured):
            return False

        return bool(re.fullmatch(r"[\d,.\-/%（）()【】\[\]/]+", structured))


def _restore_missing_year_literals(source: str, translated: str) -> str:
    source_years = [match.group("year") for match in _SOURCE_YEAR_RE.finditer(source)]
    missing_years = [year for year in source_years if year not in translated]
    if not missing_years:
        return translated
    prefix = " ".join(dict.fromkeys(missing_years))
    return f"{prefix} {translated}".strip()


def _zero_pad_marked_numeric_token(token: str, width: int) -> str:
    match = re.fullmatch(r"(?P<mark>\*{0,2})(?P<digits>\d+)(?P=mark)", token)
    if match is None:
        return token
    mark = match.group("mark")
    padded = f"{int(match.group('digits')):0{width}d}"
    return f"{mark}{padded}{mark}"


def _translate_entity_name_fallback(label: str) -> str | None:
    normalized = label.replace("（", "(").replace("）", ")")
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized:
        return None

    translated = normalized
    for zh_term, en_term in _ENTITY_TERM_TRANSLATIONS:
        translated = translated.replace(zh_term, f" {en_term} ")

    translated = _romanize_chinese_runs(translated)
    if translated is None or _CHINESE_RE.search(translated):
        return None

    return _normalize_fallback_label_spacing(translated)


def _romanize_chinese_runs(text: str) -> str | None:
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return None

    def _replace(match: re.Match[str]) -> str:
        words = [word.capitalize() for word in lazy_pinyin(match.group(0)) if word]
        return " ".join(words)

    return _CHINESE_RUN_RE.sub(_replace, text)


def _normalize_fallback_label_spacing(label: str) -> str:
    normalized = re.sub(r"\s+", " ", label)
    normalized = re.sub(r"\s*\(\s*", " (", normalized)
    normalized = re.sub(r"\s*\)\s*", ") ", normalized)
    normalized = re.sub(r"\s+([,.;:%])", r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
