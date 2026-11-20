"""Saved products re-priced against today's rates (engine.review_saved and /api/products/review)."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from api import accounts
from landed import data, engine

CALC = dict(market="DE", cogs_cny=38, weight_kg=0.6, target_margin=0.25)
CRED = {"email": "seller@example.com", "password": "correct horse", "consent": True}


def _baseline(calc=CALC):
    return engine.baseline_of(engine.landed_cost(engine.Inputs(**calc)))


def shift(monkeypatch, **moves):
    """Move sourced rates by a factor, e.g. shift(fx_cny_per_eur=0.95)."""
    real = data.rate

    def rate(key, market):
        r = real(key, market)
        return replace(r, value=r.value * moves[key]) if key in moves else r

    monkeypatch.setattr(data, "rate", rate)


def test_unchanged_when_rates_have_not_moved():
    r = engine.review_saved(CALC, _baseline())
    assert r["status"] == "unchanged" and r["changes"] == []
    assert r["at_saved_price"]["margin_pct"] == pytest.approx(0.25, abs=5e-4)


def test_fx_move_is_reported_with_the_margin_it_costs(monkeypatch):
    base = _baseline()
    shift(monkeypatch, fx_cny_per_eur=0.95)  # yuan strengthens 5%
    r = engine.review_saved(CALC, base)
    assert r["status"] == "changed"
    fx = next(c for c in r["changes"] if c["key"] == "fx_cny_per_eur")
    assert fx["after"] == pytest.approx(fx["before"] * 0.95)
    assert r["at_saved_price"]["margin_pct"] < 0.25  # same listing earns less
    assert r["target_price"] > base["price"]  # price to get the margin back is higher
    # re-baselining makes it unchanged again
    assert engine.review_saved(CALC, r["current_baseline"])["status"] == "unchanged"


def test_vat_change_is_reported(monkeypatch):
    base = _baseline()
    shift(monkeypatch, vat_standard=21 / 19)
    r = engine.review_saved(CALC, base)
    assert any(c["key"] == "vat_standard" for c in r["changes"]) and r["status"] == "changed"


def test_seller_overrides_are_not_reported_as_rate_changes(monkeypatch):
    calc = {**CALC, "fx": 7.2, "fee_rate": 0.1}
    base = _baseline(calc)
    shift(monkeypatch, fx_cny_per_eur=0.9, platform_fee=1.5)
    r = engine.review_saved(calc, base)
    assert r["status"] == "unchanged" and not r["changes"]


def test_no_baseline_and_bad_inputs():
    assert engine.review_saved(CALC, None)["status"] == "no_baseline"
    assert engine.review_saved(CALC, {"price": "x"})["status"] == "no_baseline"
    assert engine.review_saved({**CALC, "cogs_cny": -1}, None)["status"] == "error"
    assert engine.review_saved({"market": "DE"}, None)["status"] == "error"
    assert engine.review_saved({**CALC, "bogus": 1}, None)["status"] == "no_baseline"  # unknown keys ignored


def test_abstains_above_eur_150():
    assert engine.review_saved({**CALC, "cogs_cny": 900}, None)["status"] == "abstain"


def test_check_price_is_re_evaluated():
    r = engine.review_saved(CALC, _baseline(), 29.99)
    assert r["at_check_price"]["price"] == 29.99
    assert r["at_check_price"]["max_cogs_for_target"] == pytest.approx(
        engine.price_check(engine.Inputs(**CALC), 29.99)["max_cogs_for_target"])


# ------------------------------------------------------------------ API
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "DB_PATH", tmp_path / "t.sqlite3")
    accounts._attempts.clear()
    accounts.init()
    from api.main import app
    return TestClient(app)


def test_review_endpoint_and_legacy_products(client):
    assert client.get("/api/products/review").status_code == 401
    client.post("/api/auth/register", json=CRED)
    client.put("/api/profile", json={"platform": "amazon", "market": "DE"})
    new = {"calc": CALC, "baseline": _baseline(), "check": {"price": 29.99}, "priceText": "€26.37"}
    legacy = {"inputs": {**CALC, "hs_code": None, "item_categories": 1}, "overrides": {}, "priceText": "€26.37"}
    a = client.post("/api/products", json={"name": "new", "data": new}).json()["id"]
    b = client.post("/api/products", json={"name": "legacy", "data": legacy}).json()["id"]
    reviews = {r["id"]: r for r in client.get("/api/products/review").json()["reviews"]}
    assert reviews[a]["status"] == "unchanged" and reviews[a]["at_check_price"]
    assert reviews[b]["status"] == "no_baseline"
    # the legacy product picks up the seller's saved platform, as the page would
    assert any("Platform fee (" in v["label"] for v in reviews[b]["current_baseline"]["rates"].values())


def test_update_rebaselines_and_is_owner_only(client):
    client.post("/api/auth/register", json=CRED)
    pid = client.post("/api/products", json={"name": "p", "data": {"calc": CALC}}).json()["id"]
    rev = client.get("/api/products/review").json()["reviews"][0]
    assert client.put(f"/api/products/{pid}", json={"data": {"calc": CALC, "baseline": rev["current_baseline"]}}).status_code == 200
    assert client.get("/api/products/review").json()["reviews"][0]["status"] == "unchanged"
    client.post("/api/auth/logout")
    assert client.put(f"/api/products/{pid}", json={"data": {}}).status_code == 401
    client.post("/api/auth/register", json={**CRED, "email": "other@example.com"})
    assert client.put(f"/api/products/{pid}", json={"data": {"calc": {}}}).status_code == 404
    assert client.get("/api/products/review").json()["reviews"] == []
    assert client.put(f"/api/products/{pid}", json={"data": {"x": "y" * 30000}}).status_code == 413


def test_corrupted_product_does_not_break_the_review(client):
    client.post("/api/auth/register", json=CRED)
    client.post("/api/products", json={"name": "ok", "data": {"calc": CALC}})
    client.post("/api/products", json={"name": "junk", "data": {"calc": "nope", "baseline": [1], "check": 5}})
    reviews = client.get("/api/products/review").json()["reviews"]
    assert {r["name"]: r["status"] for r in reviews} == {"ok": "no_baseline", "junk": "error"}
