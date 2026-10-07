"""Normalised internal data structures.

Providers convert whatever their APIs return into these types, and the
analytics layer only ever sees these types. Two conventions are fixed here so
the rest of the code never has to think about them:

* An `FxSeries` with base B and quote Q holds rates expressed as
  "units of Q per 1 unit of B". For a traveller with home currency B visiting a
  country that uses Q, a *higher* rate is *better*.
* A `PriceIndexSeries` is a sequence of non-overlapping periods (months or
  quarters), each with one index value. Missing periods are simply absent;
  nothing is ever filled with zero.
"""

import math
from dataclasses import dataclass
from functools import cached_property
from datetime import date


class DataQualityError(ValueError):
    """Raised when data is too incomplete to calculate a metric honestly."""


@dataclass(frozen=True)
class FxSeries:
    base: str
    quote: str
    dates: tuple[date, ...]
    rates: tuple[float, ...]

    def __post_init__(self):
        if len(self.dates) != len(self.rates):
            raise DataQualityError("dates and rates differ in length")
        for prev, nxt in zip(self.dates, self.dates[1:]):
            if nxt <= prev:
                raise DataQualityError(f"{self.pair}: dates must be strictly increasing ({prev} → {nxt})")
        for r in self.rates:
            if not (math.isfinite(r) and r > 0):
                raise DataQualityError(f"{self.pair}: invalid rate {r!r}")

    @property
    def pair(self) -> str:
        return f"{self.base}/{self.quote}"

    def __len__(self) -> int:
        return len(self.rates)

    @property
    def latest_date(self) -> date:
        if not self.dates:
            raise DataQualityError(f"{self.pair}: no observations")
        return self.dates[-1]

    @property
    def latest_rate(self) -> float:
        if not self.rates:
            raise DataQualityError(f"{self.pair}: no observations")
        return self.rates[-1]

    def invert(self) -> "FxSeries":
        """B/Q → Q/B. 1 / (Q per B) = B per Q."""
        return FxSeries(self.quote, self.base, self.dates, tuple(1.0 / r for r in self.rates))

    def window(self, start: date, end: date | None = None) -> "FxSeries":
        """Observations with start <= date <= end."""
        pairs = [(d, r) for d, r in zip(self.dates, self.rates) if d >= start and (end is None or d <= end)]
        return FxSeries(self.base, self.quote, tuple(d for d, _ in pairs), tuple(r for _, r in pairs))

    def rate_on_or_before(self, day: date) -> tuple[date, float] | None:
        found = None
        for d, r in zip(self.dates, self.rates):
            if d > day:
                break
            found = (d, r)
        return found

    @classmethod
    def from_observations(cls, base: str, quote: str, observations: dict[date, float]) -> "FxSeries":
        items = sorted(observations.items())
        return cls(base, quote, tuple(d for d, _ in items), tuple(r for _, r in items))


def normalise_pair(series: FxSeries, base: str, quote: str) -> FxSeries:
    """Return `series` expressed as base/quote, inverting it if it arrived the other way round."""
    if series.base == base and series.quote == quote:
        return series
    if series.base == quote and series.quote == base:
        return series.invert()
    raise ValueError(f"cannot express {series.pair} as {base}/{quote}")


def cross_rate(pivot_to_base: FxSeries, pivot_to_quote: FxSeries) -> FxSeries:
    """Derive base/quote from two series quoted against a common pivot currency.

    If 1 USD = 1.45 AUD and 1 USD = 150 JPY then 1 AUD = 150 / 1.45 JPY.
    Only dates present in both series are used; gaps are never filled.
    """
    if pivot_to_base.base != pivot_to_quote.base:
        raise ValueError("both series must share the same base (pivot) currency")
    base_rates = dict(zip(pivot_to_base.dates, pivot_to_base.rates))
    combined = {
        d: q / base_rates[d]
        for d, q in zip(pivot_to_quote.dates, pivot_to_quote.rates)
        if d in base_rates
    }
    return FxSeries.from_observations(pivot_to_base.quote, pivot_to_quote.quote, combined)


@dataclass(frozen=True)
class PricePeriod:
    label: str  # e.g. "2025-M03" or "2025-Q1"
    start: date
    end: date
    value: float


@dataclass(frozen=True)
class PriceIndexSeries:
    code: str  # IMF country/area code, e.g. "JPN"
    index_type: str  # "CPI" or "HICP"
    frequency: str  # "M" or "Q"
    periods: tuple[PricePeriod, ...]

    def __post_init__(self):
        for prev, nxt in zip(self.periods, self.periods[1:]):
            if nxt.start <= prev.end:
                raise DataQualityError(f"{self.code}: CPI periods overlap or are unsorted")
        for p in self.periods:
            if not (math.isfinite(p.value) and p.value > 0):
                raise DataQualityError(f"{self.code}: invalid CPI value {p.value!r} in {p.label}")

    @cached_property
    def starts(self) -> tuple[date, ...]:
        return tuple(p.start for p in self.periods)

    @property
    def first(self) -> PricePeriod:
        if not self.periods:
            raise DataQualityError(f"{self.code}: no CPI observations")
        return self.periods[0]

    @property
    def last(self) -> PricePeriod:
        if not self.periods:
            raise DataQualityError(f"{self.code}: no CPI observations")
        return self.periods[-1]
