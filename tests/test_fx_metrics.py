from datetime import date

import pytest

from app.analytics.fx_metrics import (
    annualised_volatility,
    change_over_days,
    pct_difference,
    percentile_rank,
    share_below_and_equal,
    summarise,
)
from app.models.series import DataQualityError, FxSeries
from tests.helpers import fx


def test_percentile_counts_observations_below_current():
    # history excludes today: no ties, so this is simply "share below"
    assert percentile_rank([1, 2, 3, 4, 5], 4.5) == pytest.approx(80.0)
    assert percentile_rank([1, 2, 3, 4, 5], 6) == pytest.approx(100.0)
    assert percentile_rank([1, 2, 3, 4, 5], 0.5) == pytest.approx(0.0)


def test_percentile_counts_ties_as_half():
    # window includes today's own observation (4): 3 below + ½ × 1 tie
    assert percentile_rank([1, 2, 3, 4, 5], 4) == pytest.approx(70.0)
    assert percentile_rank([1, 2, 2, 3], 2) == pytest.approx(50.0)


def test_pegged_currency_sits_at_the_median_not_the_top():
    assert percentile_rank([3.6725] * 250, 3.6725) == pytest.approx(50.0)


def test_share_below_and_equal():
    assert share_below_and_equal([1, 2, 2, 3], 2) == (pytest.approx(25.0), pytest.approx(50.0))


def test_percentile_rejects_empty_history():
    with pytest.raises(DataQualityError):
        percentile_rank([], 1.0)


def test_pct_difference():
    assert pct_difference(110, 100) == pytest.approx(10.0)
    assert pct_difference(90, 100) == pytest.approx(-10.0)
    assert pct_difference(100, 100) == pytest.approx(0.0)


def test_summarise_known_series():
    # 10, 11, ..., 29 then today = 20 → 21 observations.
    rates = list(range(10, 30)) + [20]
    s = summarise(fx(rates))
    assert s.observations == 21
    assert s.current == 20
    assert s.mean == pytest.approx(410 / 21)
    assert s.median == pytest.approx(20)  # sorted middle (11th of 21) value
    assert s.high == 29 and s.low == 10
    assert s.high_date == fx(rates).dates[19]
    assert s.low_date == fx(rates).dates[0]
    # below 20: 10..19 (10 values); ties: the historical 20 and today's 20 count half each → 11 of 21
    assert s.percentile == pytest.approx(100 * 11 / 21)
    assert s.vs_mean_pct == pytest.approx((20 / (410 / 21) - 1) * 100)
    assert s.vs_median_pct == pytest.approx(0.0)


def test_mean_and_median_differ_for_skewed_history():
    rates = [1.0] * 15 + [10.0] * 5 + [1.0]
    s = summarise(fx(rates))
    assert s.median == pytest.approx(1.0)
    assert s.mean == pytest.approx((16 * 1.0 + 5 * 10.0) / 21)


def test_summarise_requires_enough_observations():
    with pytest.raises(DataQualityError):
        summarise(fx([1.0] * 5))


def test_change_over_days_uses_last_observation_on_or_before_target():
    series = FxSeries("AUD", "JPY", (date(2024, 1, 1), date(2024, 6, 3), date(2025, 1, 1)), (100.0, 105.0, 110.0))
    assert change_over_days(series, 365) == pytest.approx(10.0)  # 2025-01-01 − 365d = 2024-01-02 → 2024-01-01 obs
    assert change_over_days(series, 3650) is None


def test_volatility_is_zero_for_flat_series_and_positive_otherwise():
    assert annualised_volatility(fx([100.0] * 30)) == pytest.approx(0.0)
    assert annualised_volatility(fx([100.0, 101.0] * 15)) > 0
