from datetime import date, timedelta

from app.models.series import FxSeries, PriceIndexSeries
from app.providers.imf import parse_period
from app.models.series import PricePeriod


def weekdays(start: date, n: int) -> list[date]:
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def fx(rates: list[float], base="AUD", quote="JPY", start=date(2024, 1, 1)) -> FxSeries:
    return FxSeries(base, quote, tuple(weekdays(start, len(rates))), tuple(float(r) for r in rates))


def cpi(code: str, values: dict[str, float], freq: str = "M", index_type: str = "CPI") -> PriceIndexSeries:
    periods = []
    for label, value in sorted(values.items(), key=lambda kv: parse_period(kv[0])[0]):
        start, end = parse_period(label)
        periods.append(PricePeriod(label, start, end, value))
    return PriceIndexSeries(code, index_type, freq, tuple(periods))
