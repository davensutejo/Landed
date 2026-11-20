"""Reverse mode (price_check) and the 27-country EU comparison."""
import math

import pytest
from fastapi.testclient import TestClient

from api.main import app
from landed import data, engine
from landed.markets import EU_COUNTRIES

DEMO = dict(market="DE", cogs_cny=38, weight_kg=0.6, target_margin=0.25)
client = TestClient(app, raise_server_exceptions=False)


def test_price_check_at_target_price_hits_target():
    target = engine.landed_cost(engine.Inputs(**DEMO))["waterfall"]["price"]
    r = engine.price_check(engine.Inputs(**DEMO), target)
    assert r["margin_pct"] == pytest.approx(0.25, abs=5e-4)
    # at the target price the seller's own cost is exactly the most they could pay
    assert r["max_cogs_for_target"] == pytest.approx(38, abs=0.05)
    assert r["max_cogs_break_even"] > r["max_cogs_for_target"]


@pytest.mark.parametrize("market", ["DE", "HU", "LU", "US"])
@pytest.mark.parametrize("margin", [0.1, 0.25, 0.4])
def test_max_cogs_round_trips_through_landed_cost(market, margin):
    """Pricing a product that costs max_cogs must give back the list price."""
    kw = dict(DEMO, market=market, target_margin=margin)
    if market == "US":
        kw.update(hs_code="8509.40", indicative=True)
    r = engine.price_check(engine.Inputs(**kw), 29.99)
    cogs = r["max_cogs_for_target"]
    assert cogs and cogs > 0
    back = engine.landed_cost(engine.Inputs(**{**kw, "cogs_cny": cogs}))["waterfall"]["price"]
    assert back == pytest.approx(29.99, abs=0.01)


def test_break_even_cost_gives_zero_profit():
    r = engine.price_check(engine.Inputs(**DEMO), 19.99)
    again = engine.price_check(engine.Inputs(**{**DEMO, "cogs_cny": r["max_cogs_break_even"]}), 19.99)
    assert again["profit_per_unit"] == pytest.approx(0, abs=0.01)


def test_price_check_too_low_has_no_feasible_cost_and_a_loss():
    r = engine.price_check(engine.Inputs(**DEMO), 4.0)  # below freight + EUR 3 duty
    assert r["max_cogs_for_target"] is None and r["max_cogs_break_even"] is None
    assert r["profit_per_unit"] < 0 and r["monte_carlo"]["p_loss"] == 1.0


def test_price_check_abstains_above_eur_150():
    with pytest.raises(data.MissingRate):
        engine.price_check(engine.Inputs(**DEMO), 180.0)


@pytest.mark.parametrize("bad", [0, -5, float("nan"), float("inf")])
def test_price_check_rejects_bad_price(bad):
    with pytest.raises(engine.EngineError):
        engine.price_check(engine.Inputs(**DEMO), bad)


def test_compare_covers_all_27_and_matches_landed_cost():
    c = engine.compare_eu(engine.Inputs(**DEMO))
    assert len(c["rows"]) == 27 and {r["market"] for r in c["rows"]} == set(EU_COUNTRIES)
    for row in c["rows"]:
        own = engine.landed_cost(engine.Inputs(**{**DEMO, "market": row["market"]}))["waterfall"]["price"]
        assert row["target_price"] == pytest.approx(own, abs=0.01)
    de = next(r for r in c["rows"] if r["market"] == "DE")
    # the shared list price defaults to Germany's target price, where the margin is the target
    assert de["margin_at_list"] == pytest.approx(0.25, abs=5e-4)


def test_compare_ranks_by_profit_and_vat_drives_it():
    rows = engine.compare_eu(engine.Inputs(**DEMO), 29.99)["rows"]
    profits = [r["profit_at_list"] for r in rows]
    assert profits == sorted(profits, reverse=True)
    assert rows[0]["market"] == "LU" and rows[-1]["market"] == "HU"  # lowest and highest standard VAT


def test_compare_above_ceiling_gives_no_figure():
    rows = engine.compare_eu(engine.Inputs(**DEMO), 160)["rows"]
    assert all(r["profit_at_list"] is None for r in rows)


def test_compare_needs_eu_market():
    with pytest.raises(engine.EngineError):
        engine.compare_eu(engine.Inputs(**{**DEMO, "market": "US", "hs_code": "8509.40"}))


def test_api_endpoints():
    r = client.post("/api/price-check", json={**DEMO, "list_price": 29.99})
    assert r.status_code == 200 and math.isfinite(r.json()["profit_per_unit"])
    assert client.post("/api/price-check", json=DEMO).status_code == 422
    assert client.post("/api/price-check", json={**DEMO, "list_price": 200}).status_code == 422
    assert client.post("/api/price-check", json={**DEMO, "list_price": -1}).status_code == 422
    r = client.post("/api/compare-eu", json={**DEMO, "platform": "amazon"})
    assert r.status_code == 200 and len(r.json()["rows"]) == 27
    assert client.post("/api/compare-eu", json={**DEMO, "market": "US"}).status_code == 422
