"""Backtest of saved products re-pricing themselves (engine.review_saved and /api/products/review)."""
import json
import math
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from api import accounts
from landed import data, engine, platforms

DE = dict(market="DE", cogs_cny=38, weight_kg=0.6, target_margin=0.25)
US = dict(market="US", cogs_cny=38, weight_kg=0.6, target_margin=0.25, hs_code="8509.40", indicative=True)
CRED = {"email": "seller@example.com", "password": "correct horse", "consent": True}
EU_MARKETS = sorted(m for m in engine.MARKETS if m != "US")


def _baseline(calc):
    return engine.baseline_of(engine.landed_cost(engine.Inputs(**calc)))


def move(monkeypatch, **factors):
    """Scale sourced rates: move(vat_standard=1.1). Values may be a factor (float) or an absolute value (tuple)."""
    real = data.rate

    def rate(key, market):
        r = real(key, market)
        if key not in factors:
            return r
        f = factors[key]
        value = f[0] if isinstance(f, tuple) else r.value * f
        return replace(r, value=value)

    monkeypatch.setattr(data, "rate", rate)


def _change(r, key):
    return next((c for c in r["changes"] if c["key"] == key), None)


# ------------------------------------------------------------------ 1. rate shocks
@pytest.mark.parametrize("factor", [0.98, 0.95, 0.90, 1.02, 1.05, 1.10])
def test_eur_cny_shock_is_reported_with_correct_before_after(monkeypatch, factor):
    base = _baseline(DE)
    move(monkeypatch, fx_cny_per_eur=factor)
    r = engine.review_saved(DE, base)
    assert r["status"] == "changed"
    c = _change(r, "fx_cny_per_eur")
    assert c is not None
    assert c["before"] == pytest.approx(base["rates"]["fx_cny_per_eur"]["value"])
    assert c["after"] == pytest.approx(c["before"] * factor)
    # yuan strengthens (fewer CNY per EUR) -> the same listing earns less
    if factor < 1:
        assert r["at_saved_price"]["margin_pct"] < base["margin_pct"]
    else:
        assert r["at_saved_price"]["margin_pct"] > base["margin_pct"]
    assert engine.review_saved(DE, r["current_baseline"])["status"] == "unchanged"


@pytest.mark.parametrize("factor", [0.98, 1.02, 0.95, 1.05, 0.90, 1.10])
def test_usd_cny_shock_for_us_product(monkeypatch, factor):
    base = _baseline(US)
    move(monkeypatch, fx_cny_per_usd=factor)
    r = engine.review_saved(US, base)
    assert r["status"] == "changed"
    assert _change(r, "fx_cny_per_usd") is not None
    assert engine.review_saved(US, r["current_baseline"])["status"] == "unchanged"


@pytest.mark.parametrize("country", ["DE", "FR", "IT", "NL", "SE"])
def test_vat_change_per_country(monkeypatch, country):
    calc = {**DE, "market": country}
    base = _baseline(calc)
    key = f"vat_standard"
    move(monkeypatch, **{key: 1.02})
    r = engine.review_saved(calc, base)
    assert r["status"] == "changed"
    c = _change(r, key)
    assert c is not None and c["after"] == pytest.approx(c["before"] * 1.02)


def test_platform_fee_change_is_reported(monkeypatch):
    base = _baseline(DE)
    move(monkeypatch, platform_fee=1.5)
    r = engine.review_saved(DE, base)
    assert r["status"] == "changed" and _change(r, "platform_fee") is not None
    assert r["at_saved_price"]["margin_pct"] < base["margin_pct"]


def test_flat_duty_change_3_to_2(monkeypatch):
    base = _baseline(DE)
    assert base["rates"]["eu_flat_duty_per_category"]["value"] == pytest.approx(3)
    move(monkeypatch, eu_flat_duty_per_category=(2.0,))
    r = engine.review_saved(DE, base)
    c = _change(r, "eu_flat_duty_per_category")
    assert c is not None and c["before"] == pytest.approx(3) and c["after"] == pytest.approx(2)
    assert r["target_price"] < base["price"]  # cheaper duty, cheaper target price
    assert r["at_saved_price"]["margin_pct"] > base["margin_pct"]


@pytest.mark.parametrize("factor", [0.8, 1.25])
def test_freight_change(monkeypatch, factor):
    base = _baseline(DE)
    move(monkeypatch, freight_cny_per_kg=factor)
    r = engine.review_saved(DE, base)
    assert r["status"] == "changed" and _change(r, "freight_cny_per_kg") is not None


@pytest.mark.parametrize("factor", [0.5, 2.0])
def test_volatility_change(monkeypatch, factor):
    base = _baseline(DE)
    move(monkeypatch, fx_horizon_sd=factor)
    r = engine.review_saved(DE, base)
    assert r["status"] == "changed" and _change(r, "fx_horizon_sd") is not None


def test_target_price_equals_landed_cost_under_new_rates(monkeypatch):
    base = _baseline(DE)
    move(monkeypatch, fx_cny_per_eur=0.92)
    r = engine.review_saved(DE, base)
    assert r["target_price"] == engine.baseline_of(engine.landed_cost(engine.Inputs(**DE)))["price"]


# ------------------------------------------------------------------ 2. no false alarms
@pytest.mark.parametrize("market", EU_MARKETS)
def test_identical_rates_are_unchanged_in_every_eu_market(market):
    calc = {**DE, "market": market}
    assert engine.review_saved(calc, _baseline(calc))["status"] == "unchanged"


def test_identical_rates_unchanged_us_and_platform_variants():
    assert engine.review_saved(US, _baseline(US))["status"] == "unchanged"
    for market in EU_MARKETS:
        pids = platforms.available(market)
        if pids:
            calc = {**DE, "market": market, "platform": pids[0], "fee_category": "electronics"}
            assert engine.review_saved(calc, _baseline(calc))["status"] == "unchanged", market


@pytest.mark.parametrize("override, key, factor", [
    ({"fx": 7.2}, "fx_cny_per_eur", 0.9),
    ({"fee_rate": 0.1}, "platform_fee", 1.5),
    ({"freight_cny_per_kg": 20}, "freight_cny_per_kg", 1.3),
    ({"return_rate": 0.08}, "return_alpha", 1.2),
    ({"return_rate": 0.08}, "return_beta", 0.8),
])
def test_seller_override_hides_its_rate_from_changes(monkeypatch, override, key, factor):
    calc = {**DE, **override}
    base = _baseline(calc)
    move(monkeypatch, **{key: factor})  # only the table rate under the override moves
    r = engine.review_saved(calc, base)
    assert r["status"] == "unchanged" and not r["changes"]


# ------------------------------------------------------------------ 3. legacy and corrupted data (API)
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "DB_PATH", tmp_path / "t.sqlite3")
    accounts._attempts.clear()
    accounts.init()
    from api.main import app
    return TestClient(app)


def _register(client, email="seller@example.com"):
    r = client.post("/api/auth/register", json={**CRED, "email": email})
    assert r.status_code == 200, r.text


def _reviews(client):
    r = client.get("/api/products/review")
    assert r.status_code == 200, r.text
    return {x["name"]: x for x in r.json()["reviews"]}


def _put_profile(client, **profile):
    r = client.put("/api/profile", json=profile)
    assert r.status_code == 200, r.text


def _save(client, name, data):
    r = client.post("/api/products", json={"name": name, "data": data})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_legacy_inputs_only_product_is_reviewed(client):
    _register(client)
    _save(client, "legacy", {"inputs": {**DE, "hs_code": None, "item_categories": 1}, "overrides": {}})
    rev = _reviews(client)["legacy"]
    assert rev["status"] == "no_baseline" and rev["current_baseline"]["price"] > 0


def test_legacy_overrides_are_applied(client):
    _register(client)
    _save(client, "legacy", {"inputs": DE, "overrides": {"fx": 7.2}})
    rev = _reviews(client)["legacy"]
    assert rev["status"] == "no_baseline"
    assert rev["calc"]["fx"] == 7.2


BAD_DATA = {
    "calc_wrong_types": {"calc": {**DE, "cogs_cny": "38", "weight_kg": None}},
    "calc_strings": {"calc": {"market": "DE", "cogs_cny": "x", "weight_kg": "y"}},
    "calc_nulls": {"calc": None, "baseline": None, "check": None},
    "calc_nested_junk": {"calc": {**DE, "fee_rate": {"a": [1, 2]}}},
    "baseline_list": {"calc": DE, "baseline": [1, 2, 3]},
    "baseline_string": {"calc": DE, "baseline": "price"},
    "baseline_negative": {"calc": DE, "baseline": {"price": -5, "currency": "EUR", "rates": {}}},
    "baseline_nan_like": {"calc": DE, "baseline": {"price": "NaN", "currency": "EUR"}},
    "check_string": {"calc": DE, "check": {"price": "29.99"}},
    "check_negative": {"calc": DE, "check": {"price": -10}},
    "check_huge": {"calc": DE, "check": {"price": 1e300}},
    "missing_market": {"calc": {"cogs_cny": 38, "weight_kg": 0.6}},
    "unsupported_market_BR": {"calc": {**DE, "market": "BR"}},
    "eur_baseline_on_us_calc": {"calc": US, "baseline": {"price": 20, "currency": "EUR", "rates": {}}},
    "data_is_list": None,
}


@pytest.mark.parametrize("name", [k for k in BAD_DATA if BAD_DATA[k] is not None])
def test_bad_product_returns_a_status_not_a_500(client, name):
    _register(client)
    _save(client, "ok", {"calc": DE})
    _save(client, "bad", BAD_DATA[name])
    revs = _reviews(client)  # _reviews asserts 200
    assert "status" in revs["bad"]
    assert revs["ok"]["status"] in {"no_baseline", "unchanged"}


def test_data_that_is_not_an_object_is_reviewed_not_500(client):
    _register(client)
    r = client.post("/api/products", json={"name": "list", "data": {"x": 1}})
    assert r.status_code == 200
    # a JSON array stored directly is not representable through the API; simulate the row
    with accounts.db() as con:
        con.execute("UPDATE products SET data = ? WHERE name = 'list'", (json.dumps([1, 2]),))
    assert _reviews(client)["list"]["status"] in {"no_baseline", "error", "abstain"}


@pytest.mark.parametrize("bad", [{"inputs": [1, 2]}, {"inputs": DE, "overrides": "fx=7"}])
def test_non_dict_inputs_or_overrides_do_not_break_the_whole_review(client, bad):
    _register(client)
    _save(client, "ok", {"calc": DE})
    _save(client, "bad", bad)
    revs = _reviews(client)
    assert revs["ok"]["status"] in {"no_baseline", "unchanged"}


def test_string_calc_is_error_status(client):
    _register(client)
    _save(client, "junk", {"calc": "nope"})
    assert _reviews(client)["junk"]["status"] == "error"


def test_non_dict_rate_entry_in_baseline_does_not_500(client):
    _register(client)
    _save(client, "ok", {"calc": DE})
    _save(client, "bad", {"calc": DE, "baseline": {"price": 20, "currency": "EUR", "rates": {"fx_cny_per_eur": "x"}}})
    assert _reviews(client)["bad"]["status"] in {"changed", "unchanged", "no_baseline"}


def test_eur_baseline_on_us_calc_is_no_baseline_not_changed(client):
    _register(client)
    _save(client, "mismatch", {"calc": US, "baseline": {"price": 20, "currency": "EUR", "rates": {}}})
    rev = _reviews(client)["mismatch"]
    assert rev["status"] == "no_baseline" and rev["changes"] == []


def test_missing_market_and_unsupported_market_are_errors_or_abstain(client):
    _register(client)
    _save(client, "nomarket", {"calc": {"cogs_cny": 38, "weight_kg": 0.6}})
    _save(client, "br", {"calc": {**DE, "market": "BR"}})
    revs = _reviews(client)
    assert revs["nomarket"]["status"] == "error"
    assert revs["br"]["status"] == "error"


# ------------------------------------------------------------------ 4. isolation and auth
def test_user_b_cannot_see_or_change_user_a_products(client):
    _register(client, "a@example.com")
    pid = _save(client, "a-product", {"calc": DE})
    client.post("/api/auth/logout")
    _register(client, "b@example.com")
    assert _reviews(client) == {}
    assert client.get("/api/products").json()["products"] == []
    assert client.put(f"/api/products/{pid}", json={"data": {"calc": {}}}).status_code == 404
    assert client.delete(f"/api/products/{pid}").json() == {"ok": True}  # no-op, not an error
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={**CRED, "email": "a@example.com"}).status_code == 200
    assert _reviews(client)["a-product"]["status"] == "no_baseline"  # still there, untouched


def test_logged_out_requests_are_401(client):
    assert client.get("/api/products/review").status_code == 401
    assert client.get("/api/products").status_code == 401
    assert client.put("/api/products/1", json={"data": {}}).status_code == 401


def test_oversized_put_is_413(client):
    _register(client)
    pid = _save(client, "p", {"calc": DE})
    assert client.put(f"/api/products/{pid}", json={"data": {"x": "y" * 30000}}).status_code == 413
    assert client.post("/api/products", json={"name": "big", "data": {"x": "y" * 30000}}).status_code == 413


def test_put_renames_only_when_name_given(client):
    _register(client)
    pid = _save(client, "old", {"calc": DE})
    assert client.put(f"/api/products/{pid}", json={"data": {"calc": DE}}).status_code == 200
    assert client.get("/api/products").json()["products"][0]["name"] == "old"
    assert client.put(f"/api/products/{pid}", json={"name": "new", "data": {"calc": DE}}).status_code == 200
    assert client.get("/api/products").json()["products"][0]["name"] == "new"


# ------------------------------------------------------------------ 5. scale
def test_fifty_products_review_is_fast(client):
    _register(client)
    _put_profile(client, platform="amazon", market="DE")
    for i in range(accounts.MAX_PRODUCTS):
        market = EU_MARKETS[i % len(EU_MARKETS)] if i % 5 else "US"
        calc = {**(US if market == "US" else DE), "market": market, "cogs_cny": 20 + i}
        _save(client, f"p{i}", {"calc": calc, "baseline": _baseline(calc), "check": {"price": 29.99}})
    assert client.post("/api/products", json={"name": "51st", "data": {}}).status_code == 422
    t0 = time.perf_counter()
    revs = _reviews(client)
    elapsed = time.perf_counter() - t0
    print(f"\n50-product review: {elapsed:.2f} s")
    assert len(revs) == accounts.MAX_PRODUCTS
    assert all(v["status"] == "unchanged" for v in revs.values())
    assert elapsed < 5.0


# ------------------------------------------------------------------ 6. profile-dependent legacy rebuild
def test_profile_platform_applied_only_where_sold(client):
    _register(client)
    _put_profile(client, platform="kaufland", category="electronics", market="DE")
    _save(client, "de", {"inputs": DE, "overrides": {}})
    _save(client, "fr", {"inputs": {**DE, "market": "FR"}, "overrides": {}})
    revs = _reviews(client)
    de_labels = [v["label"] for v in revs["de"]["current_baseline"]["rates"].values()]
    fr_labels = [v["label"] for v in revs["fr"]["current_baseline"]["rates"].values()]
    assert any(label.startswith("Platform fee (") for label in de_labels)
    assert not any(label.startswith("Platform fee (") for label in fr_labels)
    assert revs["de"]["calc"]["platform"] == "kaufland"
    assert "platform" not in revs["fr"]["calc"]
    assert revs["de"]["calc"]["fee_category"] == "electronics"
    assert "fee_category" in revs["fr"]["calc"]


def test_profile_platform_skipped_when_seller_set_fee_rate(client):
    _register(client)
    _put_profile(client, platform="amazon", market="DE")
    _save(client, "override", {"inputs": {**DE, "fee_rate": 0.12}, "overrides": {}})
    assert "platform" not in _reviews(client)["override"]["calc"]
