"""Plain-English sentences built from calculated metrics. No numbers are hard-coded here."""

import math
from dataclasses import dataclass
from datetime import date

from app.config.destinations import Destination, HomeCurrency, Period


_NEEDS_THE = {"United States", "United Kingdom", "United Arab Emirates", "Philippines", "Eurozone"}


def place(name: str) -> str:
    """Country name as it reads mid-sentence: "the United Kingdom", "Japan"."""
    if name == "Eurozone":
        return "the eurozone"
    return f"the {name}" if name in _NEEDS_THE else name


def day(d: date) -> str:
    """7 Oct 2026"""
    return f"{d.day} {d:%b %Y}"


def day_range(start: date, end: date) -> str:
    """1 Jan – 30 Sep 2026, or 1 Dec 2025 – 7 Jan 2026"""
    if start.year == end.year:
        return f"{start.day} {start:%b} – {day(end)}"
    return f"{day(start)} – {day(end)}"


@dataclass(frozen=True)
class PeriodText:
    within: str  # "in the past 5 years" / "since Jan 2010"
    heading: str  # "Past 5 years" / "Since Jan 2010"
    average: str  # "5-year average" / "average since Jan 2010"
    average_short: str  # "5-year avg" / "avg since 2010"


def period_text(period: Period, window_start: date) -> PeriodText:
    """Wording for a comparison window. MAX periods are described by their actual start date."""
    if period.years is None:
        since = f"{window_start:%b %Y}"
        return PeriodText(f"since {since}", f"Since {since}", f"average since {since}", f"avg since {window_start:%Y}")
    if period.years == 1:
        return PeriodText("in the past year", "Past year", "1-year average", "1-year avg")
    n = period.years
    return PeriodText(f"in the past {n} years", f"Past {n} years", f"{n}-year average", f"{n}-year avg")


def headline(home: HomeCurrency, dest: Destination, period: PeriodText, below_pct: float, equal_pct: float) -> str:
    """e.g. "1 AUD buys more JPY today than on 87% of days in the past 5 years."

    `below_pct` / `equal_pct` are the shares of earlier days in the window with
    a strictly lower / identical rate. The percentage is rounded *down* so the
    sentence never overstates.
    """
    within = period.within
    if equal_pct >= 50:
        return (
            f"1 {home.code} buys the same amount of {dest.currency_code} today as on "
            f"{math.floor(equal_pct)}% of days {within}."
        )
    lead = f"1 {home.code} buys more {dest.currency_code} today than on"
    if below_pct >= 100:
        return f"{lead} any other day {within}."
    return f"{lead} {math.floor(below_pct)}% of days {within}."


def explanation(
    home: HomeCurrency,
    dest: Destination,
    period: PeriodText,
    below_pct: float,
    equal_pct: float,
    real_vs_average_pct: float,
    inflation_adjustment_pts: float,
) -> str:
    within, average = period.within, period.average
    if equal_pct >= 50:
        parts = [f"The exchange rate has been unchanged on {math.floor(equal_pct)}% of days {within}."]
    else:
        parts = [f"Today's rate is better than on {math.floor(below_pct)}% of days {within}."]

    if real_vs_average_pct >= 0.05:
        parts.append(f"After inflation, your {home.code} goes {real_vs_average_pct:.1f}% further than its {average}.")
    elif real_vs_average_pct <= -0.05:
        parts.append(f"After inflation, your {home.code} goes {abs(real_vs_average_pct):.1f}% less far than its {average}.")
    else:
        parts.append(f"After inflation, your {home.code} goes about as far as its {average}.")

    if inflation_adjustment_pts <= -2:
        parts.append(
            f"Faster price rises in {place(dest.country)} than in {place(home.country)} take {abs(inflation_adjustment_pts):.1f} points off the currency advantage."
        )
    elif inflation_adjustment_pts >= 2:
        parts.append(
            f"Slower price rises in {place(dest.country)} than in {place(home.country)} add {inflation_adjustment_pts:.1f} points to the currency advantage."
        )
    return " ".join(parts)
