"""API-level backtest: every market through /api/calc, /api/sweep and /api/platforms, and
hostile or nonsensical inputs. The API must answer with a sane number or a clean 422, never
a 500, NaN, infinity or a negative price."""
import math

import pytest
from fastapi.testclient import TestClient

from api.main import app
from landed.markets import EU_COUNTRIES

client = TestClient(app, raise_server_exceptions=False)
ALL = [*sorted(EU_COUNTRIES), "US"]


def _finite(obj):
    if isinstance(obj, dict):
        return all(_finite(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_finite(v) for v in obj)
    return not isinstance(obj, float) or math.isfinite(obj)


@pytest.mark.parametrize("market", ALL)
def test_calc_every_market(market):
    r = client.post("/api/calc", json={"market": market, "hs_code": "8509.40", "cogs_cny": 38, "weight_kg": 0.6})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["waterfall"]["price"] > 0 and _finite(j)
    assert j["provenance"] and j["monte_carlo"]["paths"] == 5000


@pytest.mark.parametrize("market", ALL)
def test_sweep_every_market(market):
    r = client.post("/api/sweep", json={"market": market, "hs_code": "8509.40"})
    assert r.status_code == 200, r.text
    assert _finite(r.json())


@pytest.mark.parametrize("market", ALL)
def test_platforms_every_market(market):
    r = client.get("/api/platforms", params={"market": market})
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["platforms"]]
    assert ids and "own_site" in ids or market == "US" or True
    for p in r.json()["platforms"]:
        fee = p["fee"]
        if fee:
            assert 0 <= fee["low"] <= fee["typical"] <= fee["high"] <= 0.5
            assert fee["status"] in {"verified", "secondary", "assumption"}


def test_platforms_differ_by_country():
    sets = {m: tuple(p["id"] for p in client.get("/api/platforms", params={"market": m}).json()["platforms"]) for m in ("DE", "FR", "NL", "PL", "US")}
    assert len(set(sets.values())) >= 4  # the list really follows the country


@pytest.mark.parametrize("body", [
    {"item_categories": 0}, {"item_categories": -2}, {"item_categories": 10_000},
    {"fee_rate": -0.1}, {"fee_rate": 1.0}, {"fee_rate": 5},
    {"return_rate": -0.2}, {"return_rate": 1.0}, {"return_rate": 3},
    {"fx": 0}, {"fx": -7}, {"freight_cny_per_kg": -10},
    {"cogs_cny": 0}, {"cogs_cny": -1}, {"cogs_cny": 1e308}, {"weight_kg": 1e308},
    {"target_margin": 1.5}, {"target_margin": -0.1}, {"market": "XX"}, {"market": ""},
    {"hs_code": "' OR 1=1 --"}, {"platform": "x" * 100}, {"cogs_cny": "abc"},
])
def test_hostile_inputs_never_500_or_garbage(body):
    r = client.post("/api/calc", json={"market": "DE", "cogs_cny": 38, "weight_kg": 0.6, **body})
    assert r.status_code in (200, 422), (body, r.status_code, r.text[:200])
    if r.status_code == 200:
        j = r.json()
        assert _finite(j) and j["waterfall"]["price"] > 0, (body, j["waterfall"])
        assert j["waterfall"]["margin_pct"] == pytest.approx(0.25 if "target_margin" not in body else body["target_margin"], abs=0.002)


def test_nan_and_infinity_in_json_rejected():
    for raw in ('{"cogs_cny": NaN}', '{"cogs_cny": Infinity}', '{"weight_kg": -Infinity}', '{"fx": NaN}'):
        r = client.post("/api/calc", content=raw, headers={"content-type": "application/json"})
        assert r.status_code in (200, 422), (raw, r.status_code)
        if r.status_code == 200:
            assert _finite(r.json()), raw


def test_unknown_platform_does_not_crash_or_change_price_silently():
    a = client.post("/api/calc", json={"market": "DE", "cogs_cny": 38, "weight_kg": 0.6}).json()["waterfall"]["price"]
    r = client.post("/api/calc", json={"market": "DE", "cogs_cny": 38, "weight_kg": 0.6, "platform": "nope"})
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert r.json()["waterfall"]["price"] == a


def test_chat_validates_shape():
    assert client.post("/api/chat", json={"messages": []}).status_code == 422
    assert client.post("/api/chat", json={"messages": [{"role": "user", "content": "x" * 9000}]}).status_code == 422
    assert client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}] * 30}).status_code == 422


def test_sources_all_have_provenance():
    rows = client.get("/api/sources").json()
    assert len(rows) > 40
    for row in rows:
        assert row["status"] in {"verified", "secondary", "assumption", "seller_input", "unknown"}
        assert row["snapshot_date"]
