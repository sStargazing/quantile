"""End-to-end flow through the FastAPI app with both external APIs replaced by synthetic data."""

import httpx
import pytest

from app.config.destinations import enabled_destinations
from tests.conftest import fake_cpi


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


def test_max_period_uses_one_common_window(make_client):
    client = make_client()
    board = client.get("/api/leaderboard", params={"base": "AUD", "period": "max"}).json()
    period = board["period"]
    # Synthetic CPI starts in Jan 2014 for every area, so MAX starts there.
    assert period["key"] == "max" and period["years"] is None
    assert board["window_start"] == period["start"] == "2014-01-01"
    assert period["within"] == "since Jan 2014" and period["average"] == "average since Jan 2014"
    assert all(e["status"] == "ranked" for e in board["entries"])
    top = board["entries"][0]["destination"]["id"]
    detail = client.get(f"/api/country/{top}", params={"base": "AUD", "period": "max"}).json()
    assert detail["headline"].endswith("since Jan 2014.")
    assert detail["fx"]["first_date"] >= "2014-01-01"


def test_static_assets_are_versioned_by_content(make_client):
    import re

    client = make_client()
    for page in ("/", "/map", "/country/japan"):
        html = client.get(page).text
        urls = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
        assert urls and all(re.search(r"\?v=[0-9a-f]{10}$", u) for u in urls), urls
        for u in urls:
            assert client.get(u).status_code == 200


def test_page_titles_name_the_page(make_client):
    import re

    client = make_client()
    title = lambda path: re.search(r"<title>(.*?)</title>", client.get(path).text).group(1)
    assert title("/") == "Travel Value Leaderboard — Quantile"
    assert title("/map") == "World Map — Quantile"
    assert title("/country/japan") == "Japan (JPY) — Quantile"
    assert title("/country/indonesia") == "Indonesia (IDR) — Quantile"
    assert title("/country/turkey") == "Türkiye (TRY) — Quantile"
