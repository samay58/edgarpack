from edgarpack.hk.extract import extract_with_regex

_SYNTHETIC_INCOME = """Year ended 31 December
2022 2023 2024
in thousands
Revenue 1,000 2,000 3,000
"""


def test_extracts_three_years_of_revenue():
    facts = extract_with_regex(_SYNTHETIC_INCOME, "hkex_income_statement", "HKFRS")
    revenues = [f for f in facts if f.metric == "revenue"]
    years = sorted(f.fiscal_year for f in revenues)
    assert years == [2022, 2023, 2024]
    by_year = {f.fiscal_year: f.value for f in revenues}
    assert by_year[2022] == 1_000_000
    assert by_year[2023] == 2_000_000
    assert by_year[2024] == 3_000_000


def test_two_year_disclosure_is_handled():
    text = "Year ended 31 December\n2023 2024\nin thousands\nRevenue 2,000 3,000\n"
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS")
    revenues = [f for f in facts if f.metric == "revenue"]
    years = sorted(f.fiscal_year for f in revenues)
    assert years == [2023, 2024]


def test_duplicate_year_is_deduped():
    # MiniMax/Zhipu style: annual columns then interim reusing same year.
    text = (
        "For the year ended 31 December\n"
        "For the nine months ended 30 September\n"
        "2022 2023 2024 2024 2025\n"
        "in thousands\n"
        "Revenue 1,000 2,000 3,000 2,000 4,000\n"
    )
    facts = extract_with_regex(text, "hkex_income_statement", "HKFRS", max_fy=2024)
    revenues = [f for f in facts if f.metric == "revenue"]
    years = sorted(f.fiscal_year for f in revenues)
    # Duplicate 2024 (interim) and >max_fy 2025 both dropped.
    assert years == [2022, 2023, 2024]
    by_year = {f.fiscal_year: f.value for f in revenues}
    assert by_year[2024] == 3_000_000
