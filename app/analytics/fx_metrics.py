"""Nominal exchange-rate metrics.

All functions take an `FxSeries` already restricted to the comparison window
and expressed as home/destination ("destination currency per 1 unit of home
currency"), so a higher rate is always better for the traveller.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.models.series import DataQualityError, FxSeries

MIN_OBSERVATIONS = 20
TRADING_DAYS_PER_YEAR = 260  # weekdays; weekends are excluded upstream


def percentile_rank(values: Sequence[float], current: float) -> float:
    """Percentage of observations below `current`, counting ties as half (0–100).

    This is the "FX percentile": with the window's observations as `values`
    (today's included), a result of 84 means today's rate beats 84% of
    observed days. Counting ties as half (the standard mid-rank convention)
    rather than as "at or below" matters for pegged currencies: a rate that
    never moves sits at the 50th percentile instead of claiming the 100th.
    For freely floating currencies the two definitions differ by at most
    one observation.
    """
    if not values:
        raise DataQualityError("cannot rank against an empty history")
    below = sum(1 for v in values if v < current)
    equal = sum(1 for v in values if v == current)
    return 100.0 * (below + 0.5 * equal) / len(values)


def share_below_and_equal(history: Sequence[float], current: float) -> tuple[float, float]:
    """(% of `history` strictly below `current`, % exactly equal). Used for plain-English statements."""
    if not history:
        raise DataQualityError("cannot compare against an empty history")
    below = sum(1 for v in history if v < current)
    equal = sum(1 for v in history if v == current)
    return 100.0 * below / len(history), 100.0 * equal / len(history)


def pct_difference(current: float, reference: float) -> float:
    """(current / reference − 1) × 100."""
    if reference <= 0:
        raise DataQualityError("reference value must be positive")
    return (current / reference - 1.0) * 100.0


@dataclass(frozen=True)
class FxSummary:
    current: float
    current_date: date
    first_date: date
    observations: int
    mean: float
    median: float
    high: float
    high_date: date
    low: float
    low_date: date
    percentile: float
    vs_mean_pct: float
    vs_median_pct: float


def summarise(series: FxSeries) -> FxSummary:
    """Headline statistics of the window. The latest observation is "today"."""
    if len(series) < MIN_OBSERVATIONS:
        raise DataQualityError(
            f"only {len(series)} exchange-rate observations for {series.pair}; at least {MIN_OBSERVATIONS} are needed"
        )
    rates = series.rates
    current = series.latest_rate
    mean = statistics.fmean(rates)
    median = statistics.median(rates)
    hi = max(range(len(rates)), key=lambda i: rates[i])
    lo = min(range(len(rates)), key=lambda i: rates[i])
    return FxSummary(
        current=current,
        current_date=series.latest_date,
        first_date=series.dates[0],
        observations=len(rates),
        mean=mean,
        median=median,
        high=rates[hi],
        high_date=series.dates[hi],
        low=rates[lo],
        low_date=series.dates[lo],
        percentile=percentile_rank(rates, current),
        vs_mean_pct=pct_difference(current, mean),
        vs_median_pct=pct_difference(current, median),
    )


def change_over_days(series: FxSeries, days: int) -> float | None:
    """% change from the last observation on/before (latest − days) to the latest. None if no such observation."""
    if not series.rates:
        return None
    then = series.rate_on_or_before(series.latest_date - timedelta(days=days))
    if then is None:
        return None
    return pct_difference(series.latest_rate, then[1])


def annualised_volatility(series: FxSeries) -> float | None:
    """Standard deviation of daily log returns, annualised, as a percentage."""
    if len(series) < MIN_OBSERVATIONS:
        return None
    returns = [math.log(b / a) for a, b in zip(series.rates, series.rates[1:])]
    return statistics.stdev(returns) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0
