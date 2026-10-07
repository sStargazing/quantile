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


def _dated(points):
    return FxSeries("AUD", "JPY", tuple(d for d, _ in points), tuple(float(r) for _, r in points))


def test_record_context_finds_the_last_time_it_was_this_good():
    from app.analytics.fx_metrics import record_context

    s = _dated([(date(2023, 1, 2), 100), (date(2024, 7, 12), 120), (date(2025, 3, 3), 105), (date(2026, 10, 7), 115)])
    ctx = record_context(s)
    assert ctx.direction == "high" and ctx.since == date(2024, 7, 12) and ctx.span_start == date(2023, 1, 2)


def test_record_context_reports_all_time_highs_and_lows():
    from app.analytics.fx_metrics import record_context

    high = record_context(_dated([(date(2020, 1, 1), 100), (date(2022, 1, 3), 110), (date(2026, 10, 7), 130)]))
    assert high.direction == "high" and high.since is None
    low = record_context(_dated([(date(2020, 1, 1), 100), (date(2022, 1, 3), 90), (date(2026, 10, 7), 80)]))
    assert low.direction == "low" and low.since is None


def test_record_context_picks_weakest_since_when_today_is_a_low():
    from app.analytics.fx_metrics import record_context

    s = _dated([(date(2020, 3, 16), 60), (date(2023, 1, 2), 90), (date(2026, 9, 1), 80), (date(2026, 10, 7), 70)])
    ctx = record_context(s)
    assert ctx.direction == "low" and ctx.since == date(2020, 3, 16)


def test_record_context_is_silent_for_unremarkable_or_pegged_rates():
    from app.analytics.fx_metrics import record_context

    # was both higher and lower within the last two months
    assert record_context(_dated([(date(2026, 8, 20), 99), (date(2026, 9, 30), 101), (date(2026, 10, 7), 100)])) is None
    assert record_context(fx([3.6725] * 60)) is None


def test_recent_extreme_reports_a_recent_peak_when_today_is_not_one():
    from app.analytics.fx_metrics import recent_extreme

    s = _dated([(date(2024, 7, 12), 116), (date(2025, 6, 2), 100), (date(2026, 8, 28), 114.7),
                (date(2026, 9, 15), 112), (date(2026, 10, 7), 110.2)])
    ext = recent_extreme(s)
    assert ext.on == date(2026, 8, 28) and ext.context.direction == "high" and ext.context.since == date(2024, 7, 12)
    assert ext.today_vs_extreme_pct == pytest.approx((110.2 / 114.7 - 1) * 100)


def test_recent_extreme_ignores_unremarkable_swings():
    from app.analytics.fx_metrics import recent_extreme

    s = _dated([(date(2026, 4, 1), 115), (date(2026, 5, 1), 85), (date(2026, 7, 20), 110),
                (date(2026, 8, 20), 90), (date(2026, 10, 7), 100)])
    assert recent_extreme(s) is None  # both recent extremes were beaten within the previous half-year
