"""Price-index helpers: aligning CPI series and measuring cumulative inflation.

CPI is published monthly or quarterly, while FX is daily. Quantile never
invents daily CPI values. Instead every day is assigned the index value of
the month/quarter it falls in (a step function), and every day after the
latest CPI release is treated as having that latest price level.
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date

from app.models.series import DataQualityError, PriceIndexSeries, PricePeriod


def period_on(series: PriceIndexSeries, day: date) -> PricePeriod | None:
    """The CPI period in force on `day`: the latest period starting on or before it.

    If a period is missing from the source data, the previous period stays in
    force (see `count_gaps`). Returns None if `day` precedes the series.
    """
    i = bisect_right(series.starts, day)
    return series.periods[i - 1] if i else None


def count_gaps(series: PriceIndexSeries, start: date, end: date) -> int:
    """Number of missing months/quarters between the periods covering [start, end]."""
    step = 1 if series.frequency == "M" else 3
    relevant = [p for p in series.periods if p.end >= start and p.start <= end]
    gaps = 0
    for prev, nxt in zip(relevant, relevant[1:]):
        months = (nxt.start.year - prev.start.year) * 12 + (nxt.start.month - prev.start.month)
        gaps += max(0, months // step - 1)
    return gaps


def common_cutoff(a: PriceIndexSeries, b: PriceIndexSeries) -> date:
    """Last day covered by *both* series' latest releases.

    Comparing a country whose CPI runs to August against one that only runs to
    June would count two extra months of inflation for the first, so both are
    cut at the earlier of the two.
    """
    return min(a.last.end, b.last.end)


def truncate(series: PriceIndexSeries, cutoff: date) -> PriceIndexSeries:
    """Drop periods ending after `cutoff`."""
    periods = tuple(p for p in series.periods if p.end <= cutoff)
    if not periods:
        raise DataQualityError(f"{series.code}: no CPI observations on or before {cutoff}")
    return PriceIndexSeries(series.code, series.index_type, series.frequency, periods)


@dataclass(frozen=True)
class CumulativeInflation:
    start_period: str
    end_period: str
    change_pct: float  # total price-level change over the window
    annualised_pct: float


def cumulative_inflation(series: PriceIndexSeries, start: date) -> CumulativeInflation:
    """Price-level change from the period containing `start` to the series' last period."""
    first = period_on(series, start)
    if first is None:
        raise DataQualityError(f"{series.code}: CPI data starts in {series.first.label}, after {start}")
    last = series.last
    change = last.value / first.value - 1.0
    years = (last.start - first.start).days / 365.25
    annualised = ((1.0 + change) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    return CumulativeInflation(first.label, last.label, change * 100.0, annualised * 100.0)
