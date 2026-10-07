"""Calculations must not depend on how a provider happens to quote a pair."""

import pytest

from app.analytics.fx_metrics import summarise
from app.models.series import FxSeries, cross_rate, normalise_pair
from tests.helpers import fx

AUD_JPY = [95, 100, 105, 98, 102, 97, 101, 99, 103, 96, 104, 100, 98, 101, 97, 99, 102, 100, 96, 103, 108]


def test_inverted_quote_is_normalised_back_to_traveller_direction():
    direct = fx(AUD_JPY, "AUD", "JPY")
    as_provided = FxSeries("JPY", "AUD", direct.dates, tuple(1 / r for r in direct.rates))  # API sent JPY/AUD

    normalised = normalise_pair(as_provided, "AUD", "JPY")
    assert normalised.base == "AUD" and normalised.quote == "JPY"
    assert normalised.rates == pytest.approx(direct.rates)

    a, b = summarise(direct), summarise(normalised)
    assert b.percentile == pytest.approx(a.percentile)
    assert b.vs_mean_pct == pytest.approx(a.vs_mean_pct)


def test_unnormalised_series_would_give_the_opposite_answer():
    # 108 is the best AUD/JPY rate in the window; read as JPY/AUD it is the worst.
    direct = fx(AUD_JPY)
    n = len(AUD_JPY)
    assert summarise(direct).percentile == pytest.approx(100 * (n - 0.5) / n)
    assert summarise(direct.invert()).percentile == pytest.approx(100 * 0.5 / n)


def test_normalise_pair_passes_through_and_rejects_unrelated_pairs():
    s = fx([1.0, 2.0])
    assert normalise_pair(s, "AUD", "JPY") is s
    with pytest.raises(ValueError):
        normalise_pair(s, "GBP", "JPY")


def test_cross_rate_from_common_pivot():
    usd_aud = fx([1.5, 1.6], "USD", "AUD")
    usd_jpy = fx([150.0, 144.0], "USD", "JPY")
    aud_jpy = cross_rate(usd_aud, usd_jpy)
    assert (aud_jpy.base, aud_jpy.quote) == ("AUD", "JPY")
    assert aud_jpy.rates == pytest.approx((100.0, 90.0))


def test_cross_rate_uses_only_dates_present_in_both_series():
    usd_aud = FxSeries("USD", "AUD", fx([1, 1, 1]).dates, (1.5, 1.5, 1.5))
    usd_jpy = FxSeries("USD", "JPY", fx([1, 1, 1]).dates[1:], (150.0, 150.0))
    assert len(cross_rate(usd_aud, usd_jpy)) == 2


def test_cross_rate_is_direction_consistent():
    usd_aud = fx([1.5, 1.6, 1.4], "USD", "AUD")
    usd_jpy = fx([150.0, 144.0, 147.0], "USD", "JPY")
    aud_jpy = cross_rate(usd_aud, usd_jpy)
    jpy_aud = cross_rate(usd_jpy, usd_aud)
    assert normalise_pair(jpy_aud, "AUD", "JPY").rates == pytest.approx(aud_jpy.rates)
