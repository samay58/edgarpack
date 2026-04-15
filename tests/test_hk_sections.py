from edgarpack.hk import load_section_map


def test_common_hk_headings_map_to_canonical_sections():
    m = load_section_map()
    assert m["CHAIRMAN'S STATEMENT"] == "hkex_chairman_statement"
    assert m["MANAGEMENT DISCUSSION AND ANALYSIS"] == "hkex_mdna"
    assert m["CONSOLIDATED STATEMENT OF PROFIT OR LOSS"] == "hkex_income_statement"
    assert m["CONSOLIDATED STATEMENT OF FINANCIAL POSITION"] == "hkex_balance_sheet"
    assert m["CONSOLIDATED STATEMENT OF CASH FLOWS"] == "hkex_cash_flow"


def test_heading_lookup_is_normalized():
    m = load_section_map()
    def normalize(s: str) -> str:
        return s.strip().upper().rstrip(".")
    assert m[normalize("Chairman's Statement")] == "hkex_chairman_statement"
