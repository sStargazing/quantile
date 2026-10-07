"""Providers, cache and services, with external HTTP replaced by fakes."""

import asyncio
import json
from datetime import date

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.frankfurter import FrankfurterProvider
from app.providers.imf import parse_cpi_xml
from app.services.cache import FileCache
from app.services.exchange_rates import ExchangeRateService, plan_chunks

CPI_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<message:StructureSpecificData xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
 <message:DataSet>
  <Series COUNTRY="JPN" INDEX_TYPE="CPI" COICOP_1999="_T" TYPE_OF_TRANSFORMATION="IX" FREQUENCY="M">
   <Obs TIME_PERIOD="2024-M02" OBS_VALUE="101.0"/>
   <Obs TIME_PERIOD="2024-M01" OBS_VALUE="100.0"/>
   <Obs TIME_PERIOD="2024-M03" OBS_VALUE="NaN"/>
   <Obs TIME_PERIOD="2024-M04" OBS_VALUE="102.5"/>
  </Series>
  <Series COUNTRY="NZL" INDEX_TYPE="CPI" COICOP_1999="_T" TYPE_OF_TRANSFORMATION="IX" FREQUENCY="Q">
   <Obs TIME_PERIOD="2024-Q1" OBS_VALUE="130.0"/>
  </Series>
 </message:DataSet>
</message:StructureSpecificData>"""


def test_parse_cpi_xml_sorts_and_skips_missing_values():
    data = parse_cpi_xml(CPI_XML)
    jpn = data[("JPN", "CPI", "M")]
    assert [p.label for p in jpn.periods] == ["2024-M01", "2024-M02", "2024-M04"]  # NaN dropped, not zeroed
    assert data[("NZL", "CPI", "Q")].last.end == date(2024, 3, 31)


def _frankfurter(records, status=200):
    def handler(request: httpx.Request):
        return httpx.Response(status, json=records)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FrankfurterProvider(client, "https://fx.test/v2")


def test_frankfurter_normalises_records_per_quote():
    provider = _frankfurter([
        {"date": "2024-01-02", "base": "USD", "quote": "USD", "rate": 1},
        {"date": "2024-01-02", "base": "USD", "quote": "JPY", "rate": 140.5},
        {"date": "2024-01-03", "base": "USD", "quote": "JPY", "rate": 141.0},
    ])
    out = asyncio.run(provider.fetch_range("USD", ["USD", "JPY"], date(2024, 1, 1), date(2024, 1, 3)))
    assert out["JPY"].rates == (140.5, 141.0)
    assert out["USD"].rates == (1.0,)


def test_frankfurter_errors_become_provider_errors():
    provider = _frankfurter({"detail": "down"}, status=503)
    provider._retry_delay = 0
    with pytest.raises(ProviderError):
        asyncio.run(provider.fetch_range("USD", ["JPY"], date(2024, 1, 1), date(2024, 1, 2)))


def test_frankfurter_retries_transient_failures():
    calls = []

    def handler(request: httpx.Request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow", request=request)
        if len(calls) == 2:
            return httpx.Response(429, json={"detail": "slow down"})
        return httpx.Response(200, json=[{"date": "2024-01-02", "base": "USD", "quote": "JPY", "rate": 140.5}])

    provider = FrankfurterProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://fx.test/v2", retry_delay=0)
    out = asyncio.run(provider.fetch_range("USD", ["JPY"], date(2024, 1, 1), date(2024, 1, 2)))
    assert out["JPY"].rates == (140.5,) and len(calls) == 3


def test_frankfurter_does_not_retry_client_errors():
    calls = []

    def handler(request: httpx.Request):
        calls.append(1)
        return httpx.Response(422, json={"detail": "bad currency"})

    provider = FrankfurterProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://fx.test/v2", retry_delay=0)
    with pytest.raises(ProviderError):
        asyncio.run(provider.fetch_range("USD", ["XXX"], date(2024, 1, 1), date(2024, 1, 2)))
    assert len(calls) == 1


def test_cache_serves_stale_value_when_refresh_fails(tmp_path):
    cache = FileCache(tmp_path)

    async def ok():
        return {"v": 1}

    async def boom():
        raise ProviderError("offline")

    async def run():
        first = await cache.fetch("k", -1, ok)  # stored already expired
        second = await cache.fetch("k", 60, boom)
        return first, second

    first, second = asyncio.run(run())
    assert first.value == {"v": 1} and not first.stale
    assert second.value == {"v": 1} and second.stale
    assert FileCache(tmp_path).get("k").value == {"v": 1}  # persisted to disk


def test_cache_without_stale_value_propagates_errors(tmp_path):
    async def boom():
        raise ProviderError("offline")

    with pytest.raises(ProviderError):
        asyncio.run(FileCache(tmp_path).fetch("k", 60, boom))


def test_plan_chunks_splits_by_year_and_current_month():
    chunks = plan_chunks(date(2024, 3, 1), date(2026, 10, 7))
    assert [(c.start, c.end) for c in chunks] == [
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 9, 30)),
        (date(2026, 10, 1), date(2026, 10, 7)),
    ]
    assert chunks[0].ttl > chunks[2].ttl > chunks[3].ttl


def test_exchange_rate_service_drops_weekends_and_builds_crosses(tmp_path):
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.params["from"])
        rows = []
        for day in ("2024-01-05", "2024-01-06", "2024-01-08"):  # Fri, Sat, Mon
            rows += [
                {"date": day, "base": "USD", "quote": "USD", "rate": 1},
                {"date": day, "base": "USD", "quote": "AUD", "rate": 1.5},
                {"date": day, "base": "USD", "quote": "JPY", "rate": 150},
            ]
        return httpx.Response(200, json=rows)

    provider = FrankfurterProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://fx.test/v2")
    service = ExchangeRateService(provider, FileCache(tmp_path), ["AUD", "JPY"])
    table = asyncio.run(service.get_table(date(2024, 1, 1), date(2024, 1, 31)))
    aud_jpy = table.pair("AUD", "JPY")
    assert aud_jpy.dates == (date(2024, 1, 5), date(2024, 1, 8))
    assert aud_jpy.rates == pytest.approx((100.0, 100.0))
    assert table.pair("USD", "AUD").rates == pytest.approx((1.5, 1.5))
    assert len(calls) == 1  # a January-only range is a single current-month chunk
    asyncio.run(service.get_table(date(2024, 1, 1), date(2024, 1, 31)))
    assert len(calls) == 1  # served from cache
