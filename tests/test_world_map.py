"""World Map: every destination must be findable in the map geometry by ISO id, and the
map must be fed by the same leaderboard data (no separate scoring)."""

import json
from pathlib import Path

from app.config.destinations import enabled_destinations

GEOMETRY = Path(__file__).resolve().parent.parent / "static" / "vendor" / "countries-110m.json"


def test_destination_iso_ids_are_unique_and_well_formed():
    ids = [d.iso_numeric for d in enabled_destinations()]
    assert len(ids) == len(set(ids))
    assert all(len(i) == 3 and i.isdigit() for i in ids)


def test_every_destination_has_a_shape_or_a_marker():
    topology = json.loads(GEOMETRY.read_text())
    shape_ids = {g.get("id") for g in topology["objects"]["countries"]["geometries"]}
    for d in enabled_destinations():
        assert d.iso_numeric in shape_ids or d.map_point is not None, f"{d.country} can't be drawn"
        if d.map_point is not None:
            lon, lat = d.map_point
            assert -180 <= lon <= 180 and -90 <= lat <= 90


def test_map_page_and_shared_data(make_client):
    client = make_client()
    page = client.get("/map")
    assert page.status_code == 200
    assert 'aria-current="page"' in page.text and "World Map" in page.text

    destinations = client.get("/api/destinations").json()
    assert all("iso_numeric" in d for d in destinations)

    # The map consumes /api/leaderboard directly; entries carry the ids it needs.
    board = client.get("/api/leaderboard", params={"base": "AUD", "period": "5y"}).json()
    ids = [e["destination"]["iso_numeric"] for e in board["entries"]]
    assert len(ids) == len(set(ids))  # keyed by country, not currency (France ≠ Italy)
    euro = {e["destination"]["id"]: e["quantile_score"] for e in board["entries"] if e["destination"]["currency_code"] == "EUR"}
    assert len(euro) == 4
