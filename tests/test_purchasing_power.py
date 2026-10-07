from datetime import date

import pytest

from app.analytics.purchasing_power import inflation_adjusted_rates, real_summary
from app.models.series import DataQualityError, FxSeries
from tests.helpers import cpi

DAYS = (date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15))
FLAT_FX = FxSeries("AUD", "JPY", DAYS, (100.0, 100.0, 100.0))
FLAT_CPI = {"2024-M01": 100.0, "2024-M02": 100.0, "2024-M03": 100.0}


def test_destination_inflation_erodes_a_flat_exchange_rate():
    dest = cpi("JPN", {"2024-M01": 100.0, "2024-M02": 105.0, "2024-M03": 110.0})
    home = cpi("AUS", FLAT_CPI)
    adjusted, cutoff = inflation_adjusted_rates(FLAT_FX, home, dest)
    assert cutoff == date(2024, 3, 31)
    # Jan: 100 × 110/100; Feb: 100 × 110/105; Mar: 100 × 110/110
    assert adjusted.rates == pytest.approx((110.0, 100 * 110 / 105, 100.0))

    r = real_summary(FLAT_FX, home, dest)
    real_mean = (110.0 + 100 * 110 / 105 + 100.0) / 3
    assert r.real_mean == pytest.approx(real_mean)
    assert r.real_vs_mean_pct == pytest.approx((100 / real_mean - 1) * 100)  # ≈ −4.69%
    assert r.inflation_adjustment_pts == pytest.approx(r.real_vs_mean_pct)  # nominal vs mean is 0
    assert r.real_percentile == pytest.approx(100 * 0.5 / 3)  # only today's own (tied) value
    assert r.dest_inflation.change_pct == pytest.approx(10.0)
    assert r.home_inflation.change_pct == pytest.approx(0.0)
    assert r.relative_inflation_factor == pytest.approx(1.10)


def test_home_inflation_makes_todays_rate_relatively_better():
    home = cpi("AUS", {"2024-M01": 100.0, "2024-M02": 105.0, "2024-M03": 110.0})
    dest = cpi("JPN", FLAT_CPI)
    r = real_summary(FLAT_FX, home, dest)
    assert r.adjusted.rates == pytest.approx((100 / 1.10, 100 / (110 / 105), 100.0))
    assert r.real_vs_mean_pct > 0
    assert r.real_percentile == pytest.approx(100 * 2.5 / 3)  # beats both earlier days
    assert r.relative_inflation_factor == pytest.approx(1 / 1.10)


def test_equal_inflation_leaves_the_nominal_picture_unchanged():
    both = {"2024-M01": 100.0, "2024-M02": 103.0, "2024-M03": 106.0}
    fx = FxSeries("AUD", "JPY", DAYS, (95.0, 100.0, 105.0))
    r = real_summary(fx, cpi("AUS", both), cpi("JPN", both))
    assert r.adjusted.rates == pytest.approx(fx.rates)
    assert r.inflation_adjustment_pts == pytest.approx(0.0)


def test_depreciation_matched_by_inflation_is_not_a_bargain():
    # The lira halves while Turkish prices double: nominal looks great, real is flat.
    fx = FxSeries("AUD", "TRY", DAYS, (10.0, 15.0, 20.0))
    dest = cpi("TUR", {"2024-M01": 100.0, "2024-M02": 150.0, "2024-M03": 200.0})
    home = cpi("AUS", FLAT_CPI)
    r = real_summary(fx, home, dest)
    assert r.adjusted.rates == pytest.approx((20.0, 20.0, 20.0))
    assert r.real_vs_mean_pct == pytest.approx(0.0)
    assert r.inflation_adjustment_pts == pytest.approx(-(20 / 15 - 1) * 100)


def test_days_after_latest_cpi_use_latest_price_level():
    fx = FxSeries("AUD", "JPY", DAYS + (date(2024, 5, 10),), (100.0, 100.0, 100.0, 120.0))
    dest = cpi("JPN", {"2024-M01": 100.0, "2024-M02": 105.0, "2024-M03": 110.0})
    adjusted, _ = inflation_adjusted_rates(fx, cpi("AUS", FLAT_CPI), dest)
    assert adjusted.rates[-1] == pytest.approx(120.0)


def test_cpi_releases_are_cut_to_the_common_latest_period():
    home = cpi("AUS", {"2024-Q1": 100.0}, freq="Q")
    dest = cpi("JPN", {"2024-M01": 100.0, "2024-M02": 100.0, "2024-M03": 100.0, "2024-M04": 150.0})
    r = real_summary(FLAT_FX, home, dest)
    assert r.cpi_cutoff == date(2024, 3, 31)
    assert r.dest_inflation.change_pct == pytest.approx(0.0)  # April's jump is not counted


def test_missing_cpi_history_is_a_data_quality_error():
    dest = cpi("JPN", {"2024-M02": 100.0, "2024-M03": 100.0})
    with pytest.raises(DataQualityError):
        real_summary(FLAT_FX, cpi("AUS", FLAT_CPI), dest)
