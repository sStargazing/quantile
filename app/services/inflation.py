"""Inflation service: cached CPI series for every configured country/area.

The whole dataset (monthly + quarterly, all areas) arrives in a single IMF
request and is cached for a week; CPI is published monthly at most.
"""

from dataclasses import dataclass, field
from datetime import date

from app.models.series import PriceIndexSeries, PricePeriod
from app.providers.imf import ImfCpiProvider
from app.services.cache import FileCache
from app.settings import settings

CPI_START_YEAR = 2000  # covers the MAX window; earlier data is never needed


@dataclass
class CpiDataset:
    series: dict[tuple[str, str, str], PriceIndexSeries]
    stale: bool = False
    warnings: list[str] = field(default_factory=list)

    def best_series(self, code: str, index_type: str, needed_from: date) -> PriceIndexSeries | None:
        """Prefer monthly data; fall back to quarterly if monthly doesn't reach back far enough.

        Australia, for example, has published a full monthly CPI only since
        2024, so a 5-year comparison uses its quarterly CPI instead.
        """
        candidates = [self.series.get((code, index_type, f)) for f in ("M", "Q")]
        candidates = [s for s in candidates if s is not None and s.periods]
        for s in candidates:
            if s.first.start <= needed_from:
                return s
        return candidates[0] if candidates else None


def _encode(series: dict[tuple[str, str, str], PriceIndexSeries]) -> list:
    return [
        {"code": s.code, "index": s.index_type, "freq": s.frequency,
         "periods": [[p.label, p.start.isoformat(), p.end.isoformat(), p.value] for p in s.periods]}
        for s in series.values()
    ]


def _decode(raw: list) -> dict[tuple[str, str, str], PriceIndexSeries]:
    out = {}
    for s in raw:
        periods = tuple(
            PricePeriod(label, date.fromisoformat(start), date.fromisoformat(end), value)
            for label, start, end, value in s["periods"]
        )
        out[(s["code"], s["index"], s["freq"])] = PriceIndexSeries(s["code"], s["index"], s["freq"], periods)
    return out


class InflationService:
    def __init__(self, provider: ImfCpiProvider, cache: FileCache, series: list[tuple[str, str]]):
        self._provider = provider
        self._cache = cache
        self._codes = sorted({c for c, _ in series})
        self._index_types = sorted({i for _, i in series})

    @property
    def provider(self) -> ImfCpiProvider:
        return self._provider

    async def get_dataset(self) -> CpiDataset:
        key = f"cpi:imf:{CPI_START_YEAR}:{'+'.join(self._codes)}:{'+'.join(self._index_types)}"

        async def loader():
            return _encode(await self._provider.fetch(self._codes, self._index_types, CPI_START_YEAR))

        result = await self._cache.fetch(key, settings.cpi_ttl, loader)
        warnings = ["Inflation data could not be refreshed; showing cached data."] if result.stale else []
        return CpiDataset(_decode(result.value), result.stale, warnings)
