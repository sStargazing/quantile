from datetime import date

import pytest

from app.analytics.inflation import common_cutoff, count_gaps, cumulative_inflation, period_on, truncate
from app.models.series import DataQualityError
from app.providers.imf import parse_period
from tests.helpers import cpi


def test_parse_period():
    assert parse_period("2025-M03") == (date(2025, 3, 1), date(2025, 3, 31))
    assert parse_period("2024-M02") == (date(2024, 2, 1), date(2024, 2, 29))
    assert parse_period("2025-Q4") == (date(2025, 10, 1), date(2025, 12, 31))
    with pytest.raises(ValueError):
        parse_period("2025")


def test_period_on_is_a_step_function():
    s = cpi("X", {"2024-M01": 100, "2024-M02": 101})
    assert period_on(s, date(2023, 12, 31)) is None
    assert period_on(s, date(2024, 1, 31)).value == 100
    assert period_on(s, date(2024, 2, 1)).value == 101
    assert period_on(s, date(2024, 5, 1)).value == 101  # after the series: latest level stays in force


def test_cumulative_inflation_manual_example():
    s = cpi("X", {f"2024-M{m:02d}": 100 + m - 1 for m in range(1, 13)} | {"2025-M01": 112.0})
    infl = cumulative_inflation(s, date(2024, 1, 10))
    assert infl.start_period == "2024-M01" and infl.end_period == "2025-M01"
    assert infl.change_pct == pytest.approx(12.0)
    years = (date(2025, 1, 1) - date(2024, 1, 1)).days / 365.25
    assert infl.annualised_pct == pytest.approx((1.12 ** (1 / years) - 1) * 100)


def test_cumulative_inflation_fails_when_cpi_starts_too_late():
    s = cpi("X", {"2024-M06": 100, "2024-M07": 101})
    with pytest.raises(DataQualityError):
        cumulative_inflation(s, date(2024, 1, 1))


def test_common_cutoff_aligns_monthly_and_quarterly_releases():
    home = cpi("AUS", {"2024-Q1": 100, "2024-Q2": 101}, freq="Q")
    dest = cpi("JPN", {f"2024-M{m:02d}": 100 + m for m in range(1, 9)})
    cutoff = common_cutoff(home, dest)
    assert cutoff == date(2024, 6, 30)
    assert truncate(dest, cutoff).last.label == "2024-M06"


def test_count_gaps_reports_missing_periods():
    s = cpi("X", {"2024-M01": 100, "2024-M02": 101, "2024-M05": 103})
    assert count_gaps(s, date(2024, 1, 1), date(2024, 5, 31)) == 2
    q = cpi("Y", {"2024-Q1": 100, "2024-Q3": 102}, freq="Q")
    assert count_gaps(q, date(2024, 1, 1), date(2024, 9, 30)) == 1
