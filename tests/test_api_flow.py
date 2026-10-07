"""End-to-end flow through the FastAPI app with both external APIs replaced by synthetic data."""

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


def test_full_user_flow(make_client):
    client = make_client()

    page = client.get("/")
    assert page.status_code == 200 and "Leaderboard" in page.text

    options = client.get("/api/options").json()
    assert options["default_base"] == "AUD" and options["default_period"] == "5y"

    board = client.get("/api/leaderboard", params={"base": "AUD", "period": "5y"}).json()
    entries = board["entries"]
    expected = [d for d in enabled_destinations() if d.currency_code != "AUD"]
    assert len(entries) == len(expected)
    assert all(e["status"] == "ranked" for e in entries)
    assert [e["rank"] for e in entries] == list(range(1, len(entries) + 1))
    scores = [e["quantile_score"] for e in entries]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)
    assert all(2 <= len(e["sparkline"]) <= 62 and e["historical_average"] > 0 for e in entries)
    france = next(e for e in entries if e["destination"]["id"] == "france")
    assert "Italy" in france["shares_currency_with"]

    # click through to a destination, keeping base & period
    top = entries[0]["destination"]["id"]
    assert client.get(f"/country/{top}", params={"base": "AUD", "period": "5y"}).status_code == 200
    detail = client.get(f"/api/country/{top}", params={"base": "AUD", "period": "5y"}).json()
    assert detail["rank"] == 1
    assert detail["headline"].startswith("1 AUD buys")
    assert detail["fx"]["observations"] > 1000
    assert len(detail["chart"]["points"]) <= 610 and detail["chart"]["downsampled"]
    assert detail["inflation"]["home"]["country"] == "Australia"
    assert detail["score"]["quantile_score"] == pytest.approx(entries[0]["quantile_score"])
    assert detail["data_quality"]["complete"] is True
    assert {s["used_for"] for s in detail["sources"]} == {"Daily exchange rates", "Consumer price indices (inflation)"}

    history = client.get("/api/history/AUD-JPY", params={"period": "1y", "max_points": 100}).json()
    assert history["base"] == "AUD" and len(history["points"]) <= 102

    converted = client.get("/api/convert", params={"to": "JPY", "amount": 100}).json()
    assert converted["result"] == pytest.approx(round(100 * converted["rate"], 2))


def test_switching_home_currency_changes_the_set(make_client):
    client = make_client()
    board = client.get("/api/leaderboard", params={"base": "EUR", "period": "1y"}).json()
    ids = {e["destination"]["id"] for e in board["entries"]}
    assert "australia" in ids and "france" not in ids


def test_missing_cpi_for_one_country_does_not_fail_the_leaderboard(make_client):
    client = make_client(cpi_handler=fake_cpi(skip={"EGY"}))
    board = client.get("/api/leaderboard").json()
    egypt = next(e for e in board["entries"] if e["destination"]["id"] == "egypt")
    assert egypt["status"] == "unavailable" and egypt["rank"] is None
    assert "Egypt" in egypt["unavailable_reason"]
    assert egypt["fx_percentile"] is not None  # nominal data still shown
    assert sum(e["status"] == "ranked" for e in board["entries"]) == len(board["entries"]) - 1
    assert board["entries"][-1]["destination"]["id"] == "egypt"  # unranked rows come last


def test_provider_outage_returns_friendly_503(make_client):
    client = make_client(fx_handler=lambda request: httpx.Response(503, json={"detail": "down"}))
    response = client.get("/api/leaderboard")
    assert response.status_code == 503
    assert "Frankfurter exchange-rate service isn't responding" in response.json()["detail"]


def test_validation_errors_are_readable(make_client):
    client = make_client()
    assert client.get("/api/leaderboard", params={"base": "XYZ"}).status_code == 400
    assert client.get("/api/leaderboard", params={"period": "7y"}).status_code == 400
    assert client.get("/api/country/atlantis").status_code == 404
    same = client.get("/api/country/australia", params={"base": "AUD"})
    assert same.status_code == 404 and "home currency" in same.json()["detail"]
