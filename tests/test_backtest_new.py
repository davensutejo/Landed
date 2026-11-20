"""Backtest of price_check and compare_eu against an independent re-implementation.

The reference below is written from the formula only (no engine internals):
  N = P/(1+vat), F = fee*P + fixed, G = (COGS+freight)/fx + duty, r = mean return rate
  profit = N - F - G(1+r),  margin = profit/N
  max COGS for margin m: solve margin = m for COGS.
It also checks properties (round trip, monotonicity, bounds), compare_eu invariants, the
regime/abstain rules, and hostile API inputs through FastAPI's TestClient.
"""
import itertools
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from landed import data, engine, platforms
from landed.engine import EngineError, Inputs
from landed.markets import EU_COUNTRIES

EU = sorted(EU_COUNTRIES)
ALL_MARKETS = [*EU, "US"]
PLATFORMS_JSON = json.loads((Path(__file__).resolve().parent.parent / "data" / "platforms.json").read_text(encoding="utf-8"))
US_HS = "8509.40"
GROUP = {"apparel": "fashion", "electronics": "electronics", "kitchen": "home", "home": "home"}


# ---------- independent reference ----------

def ref_fee(x: Inputs, market: str) -> tuple[float, float]:
    """(percent fee, fixed fee per order) from the spec: seller override, else the platform's sourced
    typical fee if the platform is sold there, else the generic placeholder."""
    if x.fee_rate is not None:
        return x.fee_rate, 0.0
    region = "US" if market == "US" else "EU"
    p = PLATFORMS_JSON["platforms"].get(x.platform) if x.platform else None
    if p and market in p["markets"]:
        entry = p["fees"].get(region)
        allowed = p.get("fee_markets", {}).get(region)
        if entry and (allowed is None or market in allowed):
            typical = entry["typical"]
            return typical.get(GROUP.get(x.fee_category or "", "default"), typical["default"]), entry["fixed"]
    return data.rate("platform_fee", "ALL").value, 0.0


def ref_terms(x: Inputs, market: str) -> dict:
    eu = market != "US"
    region = "EU" if eu else "US"
    fx = x.fx if x.fx is not None else data.rate("fx_cny_per_eur" if eu else "fx_cny_per_usd", region).value
    vat = data.rate("vat_standard", market).value if eu else 0.0
    fee, fixed = ref_fee(x, market)
    fr = x.freight_cny_per_kg if x.freight_cny_per_kg is not None else data.rate("freight_cny_per_kg", "ALL").value
    freight = fr * x.weight_kg
    if x.return_rate is not None:
        r = x.return_rate
    else:
        a, b = data.rate("return_alpha", "ALL").value, data.rate("return_beta", "ALL").value
        r = a / (a + b)
        group = GROUP.get(x.fee_category or "")
        if group:
            try:
                r = data.rate(f"return_mean_{group}", "ALL").value
            except data.MissingRate:
                pass
    if eu:
        duty_per_unit = data.rate("eu_flat_duty_per_category", "EU").value * x.item_categories
        duty_rate = 0.0
    else:
        duty_rate = data.rate(f"duty_{US_HS}", "US").value + data.rate("us_forced_labor_301_china", "US").value
        duty_per_unit = 0.0
    return dict(fx=fx, vat=vat, fee=fee, fixed=fixed, freight=freight, r=r, eu=eu,
                duty_per_unit=duty_per_unit, duty_rate=duty_rate)


def ref_profit_margin(x: Inputs, market: str, price: float) -> tuple[float, float]:
    t = ref_terms(x, market)
    if t["eu"]:
        G = (x.cogs_cny + t["freight"]) / t["fx"] + t["duty_per_unit"]
    else:
        G = (x.cogs_cny + t["freight"]) / t["fx"] + (x.cogs_cny / t["fx"]) * t["duty_rate"]
    net = price / (1 + t["vat"])
    profit = net - (t["fee"] * price + t["fixed"]) - G * (1 + t["r"])
    return profit, profit / net


def ref_max_cogs(x: Inputs, market: str, price: float, margin: float) -> float | None:
    """Solve margin(price, cogs) = margin for cogs (None if the answer is <= 0)."""
    t = ref_terms(x, market)
    d = 1 / (1 + t["vat"]) - t["fee"] - margin / (1 + t["vat"])
    if d <= 0:
        return None
    G = (price * d - t["fixed"]) / (1 + t["r"])
    if t["eu"]:
        cogs = (G - t["duty_per_unit"]) * t["fx"] - t["freight"]
    else:
        cogs = (G * t["fx"] - t["freight"]) / (1 + t["duty_rate"])
    return cogs if cogs > 0 else None


def mk(market, **kw):
    if market == "US":
        kw.setdefault("hs_code", US_HS)
        kw.setdefault("indicative", True)
    kw.setdefault("paths", 20)
    return Inputs(market=market, **kw)


def pc(x, price):
    return engine.price_check(x, price)


# ---------- 1. engine == independent re-implementation over a grid ----------

COGS = [8.0, 30.0, 90.0]
WEIGHTS = [0.2, 1.2]
MARGINS = [0.10, 0.30, 0.45]
PRICES = [9.5, 60.0]
PLATS = [None, "amazon", "temu", "ebay"]
FEE_CATS = ["electronics", "apparel", "kitchen"]
OVERRIDES = [
    {},
    {"fee_rate": 0.12},
    {"return_rate": 0.07},
    {"freight_cny_per_kg": 35.0, "fx": 7.9},
]
SCENARIOS = [(ov, cats) for ov in OVERRIDES for cats in (1, 2, 3)]


@pytest.mark.parametrize("market", ALL_MARKETS)
@pytest.mark.parametrize("ov,cats", SCENARIOS, ids=lambda v: str(v))
def test_price_check_matches_reference(market, ov, cats):
    n = 0
    for j, (cogs, kg, m, price) in enumerate(itertools.product(COGS, WEIGHTS, MARGINS, PRICES)):
        plat = PLATS[j % len(PLATS)]
        if market == "US":
            plat = plat if plat in (None, "amazon", "ebay") else None  # keep US platforms sold there
        x = mk(market, cogs_cny=cogs, weight_kg=kg, target_margin=m, item_categories=cats, platform=plat,
               fee_category=FEE_CATS[j % 3], **ov)
        got = pc(x, price)
        profit, margin = ref_profit_margin(x, market, price)
        assert got["profit_per_unit"] == pytest.approx(profit, abs=0.006), (x, price)
        assert got["margin_pct"] == pytest.approx(margin, abs=0.0006), (x, price)
        for key, target in (("max_cogs_for_target", m), ("max_cogs_break_even", 0.0)):
            want = ref_max_cogs(x, market, price, target)
            have = got[key]
            if want is None:
                assert have is None, (key, x, price, have)
            else:
                assert have is not None and have == pytest.approx(want, abs=0.011), (key, x, price, want, have)
        n += 1
    assert n == len(COGS) * len(WEIGHTS) * len(MARGINS) * len(PRICES)


# ---------- 2. properties ----------

@pytest.mark.parametrize("market", ALL_MARKETS)
def test_round_trip_max_cogs_gives_back_list_price(market):
    for cogs, m, price in itertools.product([10.0, 45.0], [0.15, 0.35], [14.0, 55.0]):
        x = mk(market, cogs_cny=cogs, weight_kg=0.5, target_margin=m, platform=None)
        mc = pc(x, price)["max_cogs_for_target"]
        if mc is None:
            continue
        back = engine.landed_cost(replace(x, cogs_cny=mc))["waterfall"]["price"]
        assert back == pytest.approx(price, abs=0.01), (market, cogs, m, price, mc)


@pytest.mark.parametrize("market", ALL_MARKETS)
def test_profit_strictly_increases_with_list_price(market):
    x = mk(market, cogs_cny=30, weight_kg=0.5, platform="amazon", fee_category="electronics")
    prices = [5.0, 10.0, 20.0, 40.0, 80.0]
    profits = [pc(x, p)["profit_per_unit"] for p in prices]
    assert all(b > a for a, b in zip(profits, profits[1:]))


@pytest.mark.parametrize("market", ALL_MARKETS)
def test_max_cogs_monotone_in_price_and_margin(market):
    x = mk(market, cogs_cny=30, weight_kg=0.5)
    prices = [25.0, 40.0, 70.0, 120.0]
    mc = [pc(x, p)["max_cogs_for_target"] for p in prices]
    assert all(b > a for a, b in zip(mc, mc[1:]))
    by_margin = [pc(replace(x, target_margin=m), 40.0)["max_cogs_for_target"] for m in (0.1, 0.2, 0.3, 0.4)]
    assert all(b < a for a, b in zip(by_margin, by_margin[1:]))


@pytest.mark.parametrize("market", ALL_MARKETS)
def test_break_even_cogs_at_least_target_cogs(market):
    for price in (25.0, 40.0):
        r = pc(mk(market, cogs_cny=30, weight_kg=0.5, target_margin=0.2), price)
        assert r["max_cogs_break_even"] is not None
        assert r["max_cogs_break_even"] >= r["max_cogs_for_target"]


@pytest.mark.parametrize("market", ALL_MARKETS)
def test_margin_at_target_price_equals_target(market):
    x = mk(market, cogs_cny=40, weight_kg=0.6, target_margin=0.27, platform="ebay", fee_category="home")
    tp = pc(x, 20.0)["target_price"]
    r = pc(x, tp)
    assert r["margin_pct"] == pytest.approx(0.27, abs=0.002)
    assert r["profit_per_unit"] >= -0.01


@pytest.mark.parametrize("market", ALL_MARKETS)
def test_p_loss_and_p_below_target_are_probabilities_and_monotone(market):
    x = mk(market, cogs_cny=35, weight_kg=0.7, target_margin=0.25, platform="amazon", paths=3000)
    prices = [8.0, 14.0, 22.0, 35.0, 60.0]
    rs = [pc(x, p)["monte_carlo"] for p in prices]
    for mc in rs:
        assert 0.0 <= mc["p_loss"] <= 1.0 and 0.0 <= mc["p_below_target"] <= 1.0
        assert mc["p_loss"] <= mc["p_below_target"] + 1e-9
    for key in ("p_loss", "p_below_target"):
        v = [mc[key] for mc in rs]
        assert all(b <= a + 1e-9 for a, b in zip(v, v[1:])), key


@pytest.mark.parametrize("market", ALL_MARKETS)
def test_sim_results_are_seeded(market):
    x = mk(market, cogs_cny=35, weight_kg=0.7, paths=400)
    assert pc(x, 25.0)["monte_carlo"] == pc(x, 25.0)["monte_carlo"]


# ---------- 3. compare_eu ----------

@pytest.mark.parametrize("list_price", [None, 9.5, 40.0, 150.0])
@pytest.mark.parametrize("platform", [None, "allegro", "kaufland", "amazon"])
def test_compare_eu_invariants(list_price, platform):
    x = Inputs(market="FR", cogs_cny=35, weight_kg=0.6, target_margin=0.25, platform=platform, paths=20,
               fee_category="electronics")
    out = engine.compare_eu(x, list_price)
    rows = out["rows"]
    assert len(rows) == 27
    assert sorted(r["market"] for r in rows) == EU
    profits = [r["profit_at_list"] for r in rows]
    finite = [p for p in profits if p is not None]
    assert finite == sorted(finite, reverse=True)
    assert profits[len(finite):] == [None] * (27 - len(finite))
    lp = out["list_price"]
    for r in rows:
        q = replace(x, market=r["market"])
        # target price in each country equals landed_cost there
        tp = engine.landed_cost(q)["waterfall"]["price"]
        assert r["target_price"] == (round(tp, 2) if tp <= 150 else None)
        if lp <= 150:
            chk = pc(q, lp)
            assert r["profit_at_list"] == pytest.approx(chk["profit_per_unit"], abs=0.011), r["market"]
            assert r["margin_at_list"] == pytest.approx(chk["margin_pct"], abs=0.0006), r["market"]
        else:
            assert r["profit_at_list"] is None and r["margin_at_list"] is None
        assert r["vat"] == pytest.approx(data.rate("vat_standard", r["market"]).value)


def test_compare_eu_default_list_price_is_target_price_in_market():
    x = Inputs(market="NL", cogs_cny=28, weight_kg=0.4, target_margin=0.3, paths=20)
    out = engine.compare_eu(x)
    assert out["list_price"] == pytest.approx(engine.landed_cost(x)["waterfall"]["price"], abs=0.005)


def test_compare_eu_above_150_all_profits_none():
    out = engine.compare_eu(Inputs(market="DE", cogs_cny=38, weight_kg=0.6, paths=20), 150.01)
    assert len(out["rows"]) == 27
    assert all(r["profit_at_list"] is None and r["margin_at_list"] is None for r in out["rows"])


@pytest.mark.parametrize("platform", ["allegro", "kaufland", "bol"])
def test_compare_eu_platform_sold_flag(platform):
    x = Inputs(market="DE", cogs_cny=38, weight_kg=0.6, platform=platform, paths=20)
    rows = {r["market"]: r for r in engine.compare_eu(x, 20.0)["rows"]}
    sold = set(platforms.available_markets(platform)) & set(EU)
    for c, r in rows.items():
        assert r["platform_sold"] is (c in sold), (platform, c)
        if c not in sold:
            assert r["fee"] == pytest.approx(data.rate("platform_fee", "ALL").value)


def test_compare_eu_rejects_us_and_bad_prices():
    with pytest.raises(EngineError):
        engine.compare_eu(mk("US", cogs_cny=38, weight_kg=0.6))
    for bad in (0, -3, float("nan"), float("inf"), True, "12"):
        with pytest.raises(EngineError):
            engine.compare_eu(Inputs(market="DE", cogs_cny=38, weight_kg=0.6, paths=20), bad)


# ---------- 4. regime and abstain ----------

def test_eu_price_above_150_raises_missing_rate():
    x = Inputs(market="DE", cogs_cny=38, weight_kg=0.6, paths=20)
    with pytest.raises(data.MissingRate):
        pc(x, 150.01)
    assert pc(x, 150.0)["list_price"] == 150.0


@pytest.mark.parametrize("bad", [0, 0.0, -1, -0.01, float("nan"), float("inf"), float("-inf"), True, False, "12", None])
def test_bad_list_prices_raise_engine_error(bad):
    x = Inputs(market="DE", cogs_cny=38, weight_kg=0.6, paths=20)
    with pytest.raises(EngineError):
        pc(x, bad)


@pytest.mark.parametrize("hs", [US_HS, "9999.99"])
def test_us_price_check_works_with_indicative(hs):
    r = engine.price_check(Inputs(market="US", cogs_cny=76, weight_kg=0.8, hs_code=hs, indicative=True, paths=50), 40.0)
    assert r["currency"] == "USD" and r["market"] == "US"
    assert math.isfinite(r["profit_per_unit"]) and r["max_cogs_for_target"] is not None


def test_us_price_check_without_hs_abstains():
    with pytest.raises(data.MissingRate):
        engine.price_check(Inputs(market="US", cogs_cny=76, weight_kg=0.8, paths=20), 40.0)


def test_us_price_check_above_150_is_not_refused_by_flat_ceiling():
    r = engine.price_check(mk("US", cogs_cny=300, weight_kg=0.8), 400.0)
    assert r["list_price"] == 400.0


# ---------- 5. hostile API inputs ----------

@pytest.fixture(scope="module")
def client():
    from api.main import app
    return TestClient(app, raise_server_exceptions=False)


def _assert_clean(resp):
    assert resp.status_code == 200 or 400 <= resp.status_code < 500, (resp.status_code, resp.text[:200])
    # Python's json accepts NaN/Infinity by default; forbid them so the body is strict JSON
    json.loads(resp.text, parse_constant=lambda c: pytest.fail(f"non-finite token {c} in response"))
    if resp.status_code == 200:
        def walk(v):
            if isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
            elif isinstance(v, float):
                assert math.isfinite(v), v
        walk(resp.json())


BASE = {"market": "DE", "cogs_cny": 38, "weight_kg": 0.6, "list_price": 20}


@pytest.mark.parametrize("path", ["/api/price-check", "/api/compare-eu"])
@pytest.mark.parametrize("body", [
    {**BASE, "list_price": 0}, {**BASE, "list_price": -5}, {**BASE, "list_price": 1e9}, {**BASE, "list_price": 1e300},
    {**BASE, "list_price": 1e-300}, {**BASE, "list_price": "abc"}, {**BASE, "list_price": [1]}, {**BASE, "list_price": {}},
    {**BASE, "list_price": True}, {**BASE, "list_price": "NaN"}, {**BASE, "list_price": None},
    {**BASE, "cogs_cny": 0}, {**BASE, "cogs_cny": -1}, {**BASE, "cogs_cny": 1e308}, {**BASE, "cogs_cny": "x"},
    {**BASE, "cogs_cny": 1e300, "weight_kg": 1e300}, {**BASE, "weight_kg": 0}, {**BASE, "weight_kg": -2},
    {**BASE, "fx": 0}, {**BASE, "fx": -1}, {**BASE, "fx": 1e-300},
    {**BASE, "fee_rate": 1.0}, {**BASE, "fee_rate": -0.1}, {**BASE, "return_rate": 1.0}, {**BASE, "freight_cny_per_kg": -3},
    {**BASE, "target_margin": 0}, {**BASE, "target_margin": 0.99}, {**BASE, "target_margin": 1e308},
    {**BASE, "item_categories": 0}, {**BASE, "item_categories": 51}, {**BASE, "item_categories": 10**30},
    {**BASE, "item_categories": 2.5}, {**BASE, "item_categories": "2"},
    {**BASE, "market": "XX"}, {**BASE, "market": "de"}, {**BASE, "market": ""}, {**BASE, "market": None},
    {**BASE, "market": "US"}, {**BASE, "market": "US", "hs_code": None},
    {**BASE, "platform": "x" * 100}, {**BASE, "platform": "not-a-platform"}, {**BASE, "fee_category": "y" * 50},
    {**BASE, "foo": 1, "__proto__": {"x": 1}, "paths": 10**9, "seed": "z"},
    {"market": "DE", "cogs_cny": 38}, {}, [1, 2], None,
])
def test_hostile_api_input_is_200_finite_or_clean_4xx(client, path, body):
    _assert_clean(client.post(path, json=body) if not isinstance(body, list) and body is not None
                  else client.post(path, content=json.dumps(body), headers={"content-type": "application/json"}))


@pytest.mark.parametrize("path", ["/api/price-check", "/api/compare-eu"])
@pytest.mark.parametrize("raw", [
    '{"market":"DE","cogs_cny":NaN,"list_price":20}',
    '{"market":"DE","cogs_cny":-Infinity,"list_price":20}',
    '{"market":"DE","cogs_cny":38,"list_price":20,"fx":NaN}',
])
def test_raw_nonfinite_tokens_are_rejected_cleanly(client, path, raw):
    _assert_clean(client.post(path, content=raw, headers={"content-type": "application/json"}))


def test_api_price_check_missing_list_price_is_422(client):
    r = client.post("/api/price-check", json={"market": "DE", "cogs_cny": 38})
    assert r.status_code == 422


def test_api_compare_eu_us_is_4xx(client):
    r = client.post("/api/compare-eu", json={**BASE, "market": "US"})
    assert 400 <= r.status_code < 500


def test_api_compare_eu_defaults_list_price_when_missing(client):
    r = client.post("/api/compare-eu", json={"market": "DE", "cogs_cny": 38, "weight_kg": 0.6})
    assert r.status_code == 200 and len(r.json()["rows"]) == 27


def test_api_price_check_huge_but_finite_inputs_stay_finite(client):
    _assert_clean(client.post("/api/price-check", json={**BASE, "cogs_cny": 1e308}))
    _assert_clean(client.post("/api/price-check", json={**BASE, "cogs_cny": 1e300, "weight_kg": 1e300}))


# ---------- 6. overflow and non-finite inputs (found by this backtest, fixed by input ceilings in build_params) ----------

OVERFLOW_REASON = ("ENGINE BUG? numpy overflow: a tiny fx or huge freight makes an inf goods cost and "
                   "simulate()'s histogram raises a bare ValueError (not EngineError) instead of a clean refusal")


def test_engine_overflow_is_clean_refusal_not_valueerror():
    x = Inputs(market="DE", cogs_cny=38, weight_kg=0.6, fx=5e-324, paths=20)
    try:
        out = engine.price_check(x, 20.0)
    except (EngineError, data.MissingRate):
        return
    except ValueError as e:  # pragma: no cover - documents the current failure
        raise AssertionError(f"bare ValueError escaped: {e}") from e
    assert all(math.isfinite(v) for v in (out["profit_per_unit"], out["margin_pct"]))


def test_engine_huge_fx_gives_finite_max_cogs():
    try:
        out = engine.price_check(Inputs(market="DE", cogs_cny=38, weight_kg=0.6, fx=1e308, paths=20), 20.0)
    except EngineError:
        return  # refused by the input ceiling: the clean outcome
    assert out["max_cogs_for_target"] is None or math.isfinite(out["max_cogs_for_target"])
    assert out["max_cogs_break_even"] is None or math.isfinite(out["max_cogs_break_even"])


def test_engine_freight_overflow_is_clean_refusal():
    x = Inputs(market="DE", cogs_cny=38, weight_kg=1e308, freight_cny_per_kg=1e308, paths=20)
    try:
        out = engine.price_check(x, 20.0)
    except (EngineError, data.MissingRate):
        return
    except ValueError as e:
        raise AssertionError(f"bare ValueError escaped: {e}") from e
    assert math.isfinite(out["profit_per_unit"])


@pytest.mark.parametrize("path,body", [
    ("/api/price-check", {**BASE, "fx": 5e-324}),
    ("/api/compare-eu", {**BASE, "fx": 5e-324}),
    ("/api/price-check", {**BASE, "weight_kg": 1e308, "freight_cny_per_kg": 1e308}),
    ("/api/price-check", {**BASE, "fx": 1e308}),
    ("/api/price-check", '{"market":"DE","cogs_cny":38,"list_price":NaN}'),
    ("/api/price-check", '{"market":"DE","cogs_cny":38,"list_price":-Infinity}'),
    ("/api/compare-eu", '{"market":"DE","cogs_cny":38,"list_price":NaN}'),
    ("/api/compare-eu", '{"market":"DE","cogs_cny":38,"list_price":-Infinity}'),
])
def test_api_overflow_is_never_500(client, path, body):
    if isinstance(body, str):  # raw JSON text with a bare NaN / Infinity token
        r = client.post(path, content=body, headers={"content-type": "application/json"})
    else:
        r = client.post(path, json=body)
    assert r.status_code != 500, (path, body, r.text[:120])
    _assert_clean(r)
