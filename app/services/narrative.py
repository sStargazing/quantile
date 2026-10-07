"""Plain-English sentences built from calculated metrics. No numbers are hard-coded here."""

import math
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


def period_phrase(period: Period) -> str:
    return "past year" if period.years == 1 else f"past {period.years} years"


def headline(home: HomeCurrency, dest: Destination, period: Period, below_pct: float, equal_pct: float) -> str:
    """e.g. "1 AUD buys more JPY today than on 87% of days in the past 5 years."

    `below_pct` / `equal_pct` are the shares of earlier days in the window with
    a strictly lower / identical rate. The percentage is rounded *down* so the
    sentence never overstates.
    """
    phrase = period_phrase(period)
    if equal_pct >= 50:
        return (
            f"1 {home.code} buys the same amount of {dest.currency_code} today as on "
            f"{math.floor(equal_pct)}% of days in the {phrase}."
        )
    lead = f"1 {home.code} buys more {dest.currency_code} today than on"
    if below_pct >= 100:
        return f"{lead} any other day in the {phrase}."
    return f"{lead} {math.floor(below_pct)}% of days in the {phrase}."


def explanation(
    home: HomeCurrency,
    dest: Destination,
    period: Period,
    below_pct: float,
    equal_pct: float,
    real_vs_average_pct: float,
    inflation_adjustment_pts: float,
) -> str:
    phrase = period_phrase(period)
    average_name = "1-year" if period.years == 1 else f"{period.years}-year"
    if equal_pct >= 50:
        parts = [f"The exchange rate has been unchanged on {math.floor(equal_pct)}% of days in the {phrase}."]
    else:
        parts = [f"Today's rate is better than on {math.floor(below_pct)}% of days in the {phrase}."]

    if real_vs_average_pct >= 0.05:
        parts.append(f"After inflation, your {home.code} goes {real_vs_average_pct:.1f}% further than its {average_name} average.")
    elif real_vs_average_pct <= -0.05:
        parts.append(f"After inflation, your {home.code} goes {abs(real_vs_average_pct):.1f}% less far than its {average_name} average.")
    else:
        parts.append(f"After inflation, your {home.code} goes about as far as its {average_name} average.")

    if inflation_adjustment_pts <= -2:
        parts.append(
            f"Faster price rises in {place(dest.country)} than in {place(home.country)} take {abs(inflation_adjustment_pts):.1f} points off the currency advantage."
        )
    elif inflation_adjustment_pts >= 2:
        parts.append(
            f"Slower price rises in {place(dest.country)} than in {place(home.country)} add {inflation_adjustment_pts:.1f} points to the currency advantage."
        )
    return " ".join(parts)
