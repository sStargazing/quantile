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


def percentile_band(percentile: float) -> tuple[str, str]:
    """Plain-English reading of a percentile: (key, label).

        below 10    exceptionally weak
        10 – 25     weak
        25 – 75     typical
        75 – 90     strong
        90 and up   exceptionally strong

    "Strong" means your home currency buys more than usual. A pegged currency
    sits at the 50th percentile, so it reads as typical.
    """
    if percentile < 10:
        return "exceptionally_weak", "Exceptionally weak"
    if percentile < 25:
        return "weak", "Weak"
    if percentile <= 75:
        return "typical", "Typical"
    if percentile < 90:
        return "strong", "Strong"
    return "exceptionally_strong", "Exceptionally strong"


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


@dataclass(frozen=True)
class RecordContext:
    """How unusual today's level is within a series: "strongest since …" / "weakest since …".

    `direction` is "high" when today is better for the traveller than on any day
    after `since`, "low" when it is worse. `since` is the most recent earlier day
    that was at least as good (high) or at least as bad (low); None means no
    earlier day in the series was, i.e. today is the best/worst since `span_start`.
    """

    direction: str
    since: date | None
    span_start: date


def record_context(series: FxSeries, min_gap_days: int = 60) -> RecordContext | None:
    """The more striking of "highest since" / "lowest since" for today's rate.

    Returns None when neither is notable: the rate was last at least as good and
    at least as bad within `min_gap_days` (a mid-range or pegged rate).
    """
    if len(series) < 2:
        return None
    today, current = series.latest_date, series.latest_rate
    last_at_least = last_at_most = None
    for d, r in zip(reversed(series.dates[:-1]), reversed(series.rates[:-1])):
        if last_at_least is None and r >= current:
            last_at_least = d
        if last_at_most is None and r <= current:
            last_at_most = d
        if last_at_least and last_at_most:
            break

    def age(d: date | None) -> float:
        return math.inf if d is None else (today - d).days

    if age(last_at_least) >= age(last_at_most):
        direction, since = "high", last_at_least
    else:
        direction, since = "low", last_at_most
    if age(since) < min_gap_days:
        return None
    return RecordContext(direction, since, series.dates[0])


@dataclass(frozen=True)
class RecentExtreme:
    """A notable peak or trough within the recent past, and how far today is from it."""

    on: date
    rate: float
    context: RecordContext  # how notable that day was ("strongest since …" as of `on`)
    today_vs_extreme_pct: float


def recent_extreme(series: FxSeries, lookback_days: int = 92, min_gap_days: int = 182) -> RecentExtreme | None:
    """The more notable of the highest and lowest day in the last `lookback_days`.

    Used when today itself isn't a high or low: "On 28 Aug AUD reached its
    strongest against JPY since July 2024; today is 3.9% below that." A past
    extreme has to be the best/worst in at least `min_gap_days` (half a year by
    default) to be worth mentioning. Returns None if neither was.
    """
    if len(series) < 2:
        return None
    cutoff = series.latest_date - timedelta(days=lookback_days)
    recent = [i for i, d in enumerate(series.dates) if d >= cutoff]
    if len(recent) < 2:
        return None
    candidates = []
    for pick in (max, min):
        i = pick(recent, key=lambda k: series.rates[k])
        if i == len(series) - 1:
            continue  # today is the extreme: record_context already covers it
        upto = FxSeries(series.base, series.quote, series.dates[: i + 1], series.rates[: i + 1])
        ctx = record_context(upto, min_gap_days)
        if ctx is not None and ctx.direction == ("high" if pick is max else "low"):
            candidates.append(RecentExtreme(series.dates[i], series.rates[i], ctx, pct_difference(series.latest_rate, series.rates[i])))
    if not candidates:
        return None

    def notability(c: RecentExtreme) -> float:
        return math.inf if c.context.since is None else (c.on - c.context.since).days

    return max(candidates, key=notability)
