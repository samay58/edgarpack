"""Golden-fixture regression gate for Chinese company queries.

Loads tests/eval/china_golden.yaml at collection time and parametrizes
over (ticker, period, metric, currency). Native assertions are exact;
USD assertions use 2% relative tolerance. Known extraction bugs are
carried as xfail rows keyed by bead ID.

See tests/eval/README.md for the schema and the curator workflow.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from edgarpack.fx.convert import convert
from edgarpack.fx.rates import load_rates
from edgarpack.query.financials import financials

GOLDEN_PATH = Path(__file__).parent / "eval" / "china_golden.yaml"
FX_PATH = Path(__file__).parent.parent / "data" / "fx_rates.csv"
USD_REL_TOL = 0.02


@dataclass(frozen=True)
class GoldenCase:
    ticker: str
    company: str
    accounting_standard: str
    reporting_currency: str
    fiscal_year: int
    period: str
    metric: str
    currency: str  # "native" or "usd"
    expected: int | None
    fx_convention: str | None
    source: str
    xfail: str | None
    unit: str | None  # set to "headcount" for non-currency metrics


def _load_cases() -> list[GoldenCase]:
    with GOLDEN_PATH.open() as f:
        doc = yaml.safe_load(f)
    assert doc.get("version") == 1, f"unsupported golden schema version: {doc.get('version')!r}"
    cases: list[GoldenCase] = []
    for company in doc.get("companies", []):
        for metric_name, periods in company["metrics"].items():
            for period_name, block in periods.items():
                unit = block.get("unit")
                if unit == "headcount":
                    # Non-currency metric: only one case, no FX conversion
                    cases.append(
                        GoldenCase(
                            ticker=company["ticker"],
                            company=company["company"],
                            accounting_standard=company["accounting_standard"],
                            reporting_currency=company["reporting_currency"],
                            fiscal_year=company["fiscal_year"],
                            period=period_name,
                            metric=metric_name,
                            currency="native",
                            expected=block.get("native"),
                            fx_convention=None,
                            source=block.get("source", ""),
                            xfail=block.get("xfail"),
                            unit=unit,
                        )
                    )
                else:
                    for currency in ("native", "usd"):
                        cases.append(
                            GoldenCase(
                                ticker=company["ticker"],
                                company=company["company"],
                                accounting_standard=company["accounting_standard"],
                                reporting_currency=company["reporting_currency"],
                                fiscal_year=company["fiscal_year"],
                                period=period_name,
                                metric=metric_name,
                                currency=currency,
                                expected=block.get(currency),
                                fx_convention=block.get("fx_convention"),
                                source=block.get("source", ""),
                                xfail=block.get("xfail"),
                                unit=unit,
                            )
                        )
    return cases


_CASES = _load_cases()


def _case_id(c: GoldenCase) -> str:
    return f"{c.ticker}-{c.period}-{c.metric}-{c.currency}"


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_china_golden(case: GoldenCase, request: pytest.FixtureRequest) -> None:
    if case.xfail:
        request.applymarker(pytest.mark.xfail(strict=True, reason=f"known bug: {case.xfail}"))

    result = asyncio.run(financials(company=case.ticker, metrics=case.metric, period=case.period))
    cited = result.metrics.get(case.metric)
    assert cited is not None, f"{case.metric} not returned by query"
    assert cited.value is not None, f"{case.metric} value is None"

    if case.unit == "headcount":
        # Non-currency metric: compare raw integer value directly, no FX
        actual: float = float(cited.value)
        if actual != case.expected:
            pytest.fail(
                _fail_block(case, actual, rate_used=None),
                pytrace=False,
            )
    elif case.currency == "native":
        actual = float(cited.value)
        if actual != case.expected:
            pytest.fail(
                _fail_block(case, actual, rate_used=None),
                pytrace=False,
            )
    else:
        rates = load_rates(FX_PATH)
        convention = case.fx_convention or "average"
        period_end = cited.period_end
        converted = convert(
            value=Decimal(str(cited.value)),
            from_ccy=cited.reporting_currency,
            to_ccy="USD",
            as_of=period_end,
            convention=convention,  # type: ignore[arg-type]
            rates=rates,
            period_end=period_end,
        )
        actual = converted.converted_value
        if case.expected is None:
            pytest.fail(
                f"{_case_id(case)}: golden USD value is null but xfail was not set",
                pytrace=False,
            )
        if not math.isclose(actual, case.expected, rel_tol=USD_REL_TOL):
            pytest.fail(
                _fail_block(case, actual, rate_used=converted.rate_used),
                pytrace=False,
            )


def _fail_block(case: GoldenCase, actual: float, rate_used: float | None) -> str:
    diff = actual - (case.expected or 0)
    pct = (diff / case.expected * 100.0) if case.expected else float("inf")
    lines = [
        f"GOLDEN MISMATCH: {_case_id(case)}",
        f"  ticker:            {case.ticker} ({case.company})",
        f"  period/metric:     {case.period} / {case.metric}",
        f"  currency:          {case.currency}",
        f"  golden expected:   {case.expected}",
        f"  actual computed:   {actual}",
        f"  abs diff:          {diff}",
        f"  pct diff:          {pct:.4f}%",
    ]
    if rate_used is not None:
        lines.append(f"  fx rate used:      {rate_used}")
    lines.append(f"  source citation:   {case.source}")
    return "\n".join(lines)
