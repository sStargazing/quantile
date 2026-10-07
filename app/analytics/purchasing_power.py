"""Inflation-adjusted ("real") purchasing power.

Method
------
For each historical day t in the window, restate that day's exchange rate in
today's prices:

    R_adj(t) = R_t × (P_dest_now / P_dest(t)) ÷ (P_home_now / P_home(t))

where P(t) is the CPI level in force on day t and "now" is the latest CPI
period available for *both* countries. R_adj(t) answers: "how many units of
destination currency would I need today to have the same real buying power as
1 unit of home currency bought on day t?". High destination inflation raises
it (the old rate is "worth" more local currency today); high home inflation
lowers it.

Comparing today's actual rate with R_adj(t) is equivalent to comparing the
real exchange rate Q = R × P_home / P_dest today against day t, the standard
measure of relative purchasing power.

From the adjusted series we compute exactly the same statistics as for the
nominal series, so the two are directly comparable:

* real vs average  = (R_today / mean(R_adj) − 1) × 100
* real percentile  = % of days with R_adj(t) ≤ R_today
* inflation adjustment (percentage points) = real vs average − nominal vs average
"""

import statistics
from dataclasses import dataclass
from datetime import date

from app.analytics.fx_metrics import pct_difference, percentile_rank
from app.analytics.inflation import (
    CumulativeInflation,
    common_cutoff,
    count_gaps,
    cumulative_inflation,
    period_on,
    truncate,
)
from app.models.series import DataQualityError, FxSeries, PriceIndexSeries


def inflation_adjusted_rates(fx: FxSeries, home_cpi: PriceIndexSeries, dest_cpi: PriceIndexSeries) -> tuple[FxSeries, date]:
    """Return (R_adj series, CPI cutoff date). See module docstring."""
    cutoff = common_cutoff(home_cpi, dest_cpi)
    home = truncate(home_cpi, cutoff)
    dest = truncate(dest_cpi, cutoff)
    home_now, dest_now = home.last.value, dest.last.value

    adjusted = []
    for day, rate in zip(fx.dates, fx.rates):
        ref = min(day, cutoff)
        ph, pd = period_on(home, ref), period_on(dest, ref)
        if ph is None or pd is None:
            missing = home if ph is None else dest
            raise DataQualityError(
                f"{missing.code} CPI starts in {missing.first.label}, after the comparison window begins ({fx.dates[0]})"
            )
        adjusted.append(rate * (dest_now / pd.value) / (home_now / ph.value))
    return FxSeries(fx.base, fx.quote, fx.dates, tuple(adjusted)), cutoff


@dataclass(frozen=True)
class RealSummary:
    cpi_cutoff: date
    home_inflation: CumulativeInflation
    dest_inflation: CumulativeInflation
    relative_inflation_factor: float  # (1 + destination inflation) / (1 + home inflation)
    adjusted: FxSeries
    real_mean: float
    real_percentile: float
    real_vs_mean_pct: float
    inflation_adjustment_pts: float
    home_cpi_gaps: int
    dest_cpi_gaps: int


def real_summary(fx: FxSeries, home_cpi: PriceIndexSeries, dest_cpi: PriceIndexSeries) -> RealSummary:
    if not fx.rates:
        raise DataQualityError(f"no exchange-rate observations for {fx.pair}")
    adjusted, cutoff = inflation_adjusted_rates(fx, home_cpi, dest_cpi)
    home, dest = truncate(home_cpi, cutoff), truncate(dest_cpi, cutoff)
    start = fx.dates[0]
    home_infl = cumulative_inflation(home, start)
    dest_infl = cumulative_inflation(dest, start)

    current = fx.latest_rate
    nominal_mean = statistics.fmean(fx.rates)
    real_mean = statistics.fmean(adjusted.rates)
    real_vs_mean = pct_difference(current, real_mean)
    return RealSummary(
        cpi_cutoff=cutoff,
        home_inflation=home_infl,
        dest_inflation=dest_infl,
        relative_inflation_factor=(1 + dest_infl.change_pct / 100) / (1 + home_infl.change_pct / 100),
        adjusted=adjusted,
        real_mean=real_mean,
        real_percentile=percentile_rank(adjusted.rates, current),
        real_vs_mean_pct=real_vs_mean,
        inflation_adjustment_pts=real_vs_mean - pct_difference(current, nominal_mean),
        home_cpi_gaps=count_gaps(home, start, cutoff),
        dest_cpi_gaps=count_gaps(dest, start, cutoff),
    )
