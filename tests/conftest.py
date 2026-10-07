"""Shared fixtures: the FastAPI app wired to synthetic exchange-rate and CPI providers."""

import math
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config.destinations import all_cpi_series, all_currency_codes, enabled_destinations
from app.main import app
from app.providers.frankfurter import FrankfurterProvider
from app.providers.imf import ImfCpiProvider
from app.services.analysis import AnalysisService
from app.services.cache import FileCache
from app.services.exchange_rates import ExchangeRateService
from app.services.inflation import InflationService
from app.settings import settings


def fake_fx(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    quotes = params["quotes"].split(",")
    day, end = date.fromisoformat(params["from"]), date.fromisoformat(params["to"])
    rows = []
    while day <= end:
        t = day.toordinal()
        for i, q in enumerate(quotes):
            rate = 1.0 if q == "USD" else (1 + i) * (1 + 0.1 * math.sin(t / (90 + 7 * i)))
            rows.append({"date": day.isoformat(), "base": "USD", "quote": q, "rate": round(rate, 6)})
        day += timedelta(days=1)
    return httpx.Response(200, json=rows)


def fake_cpi(skip: set[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path.rsplit("/", 1)[-1]
        codes, index_types = key.split(".")[0].split("+"), key.split(".")[1].split("+")
        today = date.today()
        series = []
        for code in codes:
            if code in skip:
                continue
            obs = []
            months = (today.year - 2014) * 12 + today.month - 2
            growth = 1.002 + 0.0005 * (len(code) % 3)
            for m in range(months):
                y, mo = 2014 + m // 12, m % 12 + 1
                obs.append(f'<Obs TIME_PERIOD="{y}-M{mo:02d}" OBS_VALUE="{100 * growth ** m:.4f}"/>')
            for idx in index_types:
                series.append(f'<Series COUNTRY="{code}" INDEX_TYPE="{idx}" FREQUENCY="M">{"".join(obs)}</Series>')
        xml = f'<?xml version="1.0"?><m:Data xmlns:m="x"><m:DataSet>{"".join(series)}</m:DataSet></m:Data>'
        return httpx.Response(200, content=xml.encode(), headers={"content-type": "application/xml"})

    return handler


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "prewarm_on_startup", False)
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "boot")
    clients = []

    def build(fx_handler=fake_fx, cpi_handler=None):
        cache = FileCache(tmp_path / f"cache{len(clients)}")
        fx = ExchangeRateService(
            FrankfurterProvider(httpx.AsyncClient(transport=httpx.MockTransport(fx_handler)), "https://fx.test/v2"),
            cache,
            all_currency_codes(),
        )
        cpi = InflationService(
            ImfCpiProvider(httpx.AsyncClient(transport=httpx.MockTransport(cpi_handler or fake_cpi(set()))), "https://imf.test"),
            cache,
            all_cpi_series(),
        )
        client = TestClient(app)
        client.__enter__()
        app.state.analysis = AnalysisService(fx, cpi)
        clients.append(client)
        return client

    yield build
    for c in clients:
        c.__exit__(None, None, None)
