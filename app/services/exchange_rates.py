"""Exchange-rate service: cached, chunked historical FX for every configured currency.

Design:

* All currencies are fetched once against a single pivot (USD) and every
  home/destination pair is derived as a cross rate. One dataset therefore
  serves every home currency, and switching home currency costs no API calls.
* History is fetched in calendar-year chunks, concurrently. Completed years
  never change, so they are cached for a long time; only the current month is
  refreshed frequently.
* Weekend observations are dropped. FX markets are closed at weekends; the
  handful of central banks that publish weekend rates would otherwise make
  weekday and weekend "days" mean different things across currencies.
"""

import asyncio
import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.models.series import DataQualityError, FxSeries, cross_rate
from app.providers.base import ProviderError
from app.providers.frankfurter import SOURCE as FX_SOURCE, FrankfurterProvider
from app.services.cache import FileCache
from app.services.narrative import day_range
from app.settings import settings

log = logging.getLogger(__name__)

PIVOT = "USD"
MAX_CONCURRENT_REQUESTS = 8  # be polite to the provider when fetching many years at once


@dataclass(frozen=True)
class Chunk:
    start: date
    end: date
    ttl: int


@dataclass
class FxTable:
    """Pivot-quoted daily series for all currencies, plus provenance."""

    pivot_series: dict[str, FxSeries]
    warnings: list[str] = field(default_factory=list)

    def pair(self, base: str, quote: str) -> FxSeries:
        if base not in self.pivot_series or quote not in self.pivot_series:
            missing = base if base not in self.pivot_series else quote
            raise DataQualityError(f"no exchange-rate data for {missing}")
        if base == quote:
            raise ValueError("base and quote are the same currency")
        return cross_rate(self.pivot_series[base], self.pivot_series[quote])


def plan_chunks(start: date, end: date) -> list[Chunk]:
    """Split [start, end] into cacheable chunks with TTLs that reflect how often each can change."""
    chunks: list[Chunk] = []
    for year in range(start.year, end.year + 1):
        if year < end.year:
            chunks.append(Chunk(date(year, 1, 1), date(year, 12, 31), settings.fx_history_ttl))
            continue
        month_start = end.replace(day=1)
        if month_start > date(year, 1, 1):
            prev_month_end = month_start - timedelta(days=1)
            chunks.append(Chunk(date(year, 1, 1), prev_month_end, settings.fx_recent_ttl))
        chunks.append(Chunk(month_start, end, settings.fx_current_ttl))
    return chunks


def _encode(series: dict[str, FxSeries]) -> dict:
    return {q: [[d.isoformat(), r] for d, r in zip(s.dates, s.rates)] for q, s in series.items()}


def _decode(base: str, raw: dict) -> dict[str, FxSeries]:
    return {
        q: FxSeries.from_observations(base, q, {date.fromisoformat(d): r for d, r in rows})
        for q, rows in raw.items()
    }


class ExchangeRateService:
    def __init__(self, provider: FrankfurterProvider, cache: FileCache, currencies: list[str]):
        self._provider = provider
        self._cache = cache
        self._currencies = sorted(set(currencies) | {PIVOT})
        self._limit = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    @property
    def provider(self) -> FrankfurterProvider:
        return self._provider

    async def _load_chunk(self, chunk: Chunk) -> tuple[dict, bool]:
        key = f"fx:{self._provider.name}:{PIVOT}:{chunk.start}:{chunk.end}:{','.join(self._currencies)}"

        async def loader():
            async with self._limit:
                series = await self._provider.fetch_range(PIVOT, self._currencies, chunk.start, chunk.end)
            return _encode(series)

        result = await self._cache.fetch(key, chunk.ttl, loader)
        return result.value, result.stale

    async def get_table(self, start: date, end: date | None = None) -> FxTable:
        """Daily pivot-quoted series (weekdays only) covering [start, end]."""
        end = end or date.today()
        chunks = plan_chunks(start, end)
        results = await asyncio.gather(*(self._load_chunk(c) for c in chunks), return_exceptions=True)

        merged: dict[str, dict[date, float]] = {c: {} for c in self._currencies}
        warnings: list[str] = []
        loaded = 0
        for chunk, res in zip(chunks, results):
            if isinstance(res, BaseException):
                if not isinstance(res, (ProviderError, DataQualityError)):
                    raise res
                log.warning("FX chunk %s–%s unavailable: %s", chunk.start, chunk.end, res)
                warnings.append(f"Exchange rates for {day_range(chunk.start, chunk.end)} are unavailable from the provider.")
                continue
            raw, stale = res
            loaded += 1
            if stale:
                warnings.append(
                    f"Exchange rates for {day_range(chunk.start, chunk.end)} couldn't be refreshed; showing the copy cached earlier."
                )
            for quote, series in _decode(PIVOT, raw).items():
                if quote in merged:
                    merged[quote].update(
                        (d, r) for d, r in zip(series.dates, series.rates) if d.weekday() < 5 and start <= d <= end
                    )
        if loaded == 0:
            raise ProviderError("no FX chunk could be loaded and none is cached", FX_SOURCE)

        table = {q: FxSeries.from_observations(PIVOT, q, obs) for q, obs in merged.items() if obs}
        return FxTable(table, warnings)


def years_before(day: date, years: int) -> date:
    """The same calendar day `years` earlier (29 Feb → 28 Feb when needed)."""
    year = day.year - years
    return day.replace(year=year, day=min(day.day, calendar.monthrange(year, day.month)[1]))
