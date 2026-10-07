"""Frankfurter v2 exchange-rate provider (https://frankfurter.dev).

Frankfurter blends daily reference rates published by central banks (ECB,
Federal Reserve, RBA and others). It needs no API key and serves bulk date
ranges in one request, so the whole history for every currency arrives in a
handful of calls instead of one call per day.
"""

from datetime import date

import httpx

from app.models.series import FxSeries
from app.providers.base import ProviderError


SOURCE = "Frankfurter exchange-rate service"


class FrankfurterProvider:
    name = "Frankfurter"
    description = "Daily reference rates blended from central-bank publications (ECB, Federal Reserve, RBA and others)"
    url = "https://frankfurter.dev"

    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def fetch_range(self, base: str, quotes: list[str], start: date, end: date) -> dict[str, FxSeries]:
        """Daily base/quote series for every quote currency between start and end (inclusive)."""
        params = {"base": base, "quotes": ",".join(quotes), "from": start.isoformat(), "to": end.isoformat()}
        try:
            response = await self._client.get(f"{self._base_url}/rates", params=params)
            response.raise_for_status()
            records = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Frankfurter request failed for {base} {start}→{end}: {exc}", SOURCE) from exc

        by_quote: dict[str, dict[date, float]] = {q: {} for q in quotes}
        try:
            for rec in records:
                rec_base, rec_quote = rec["base"], rec["quote"]
                if rec_quote not in by_quote:
                    continue
                rate = float(rec["rate"])
                day = date.fromisoformat(rec["date"])
                if rec_base != base:
                    raise ProviderError(f"unexpected base {rec_base!r} in Frankfurter response", SOURCE)
                by_quote[rec_quote][day] = rate  # includes the base/base identity record (rate 1)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"unexpected Frankfurter response shape: {exc}", SOURCE) from exc

        return {q: FxSeries.from_observations(base, q, obs) for q, obs in by_quote.items()}
