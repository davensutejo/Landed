"""The full cost stack (advertising, payout fee, fulfilment fee) and freight on the box size (volumetric weight)."""
import json
from types import SimpleNamespace as NS

import pytest

from landed import agent, engine, tools
from landed.engine import Inputs

from test_agent import _call, run_with

BEAR = dict(market="DE", cogs_cny=20, weight_kg=0.3, target_margin=0.25)
FULL = dict(ad_rate=0.12, payout_rate=0.01, fulfilment_fee=3.2)


def price(**kw):
    return engine.landed_cost(Inputs(**{**BEAR, **kw}))


def test_defaults_add_nothing_and_say_so():
    r = price()
    assert {s["key"] for s in r["waterfall"]["steps"]}.isdisjoint({"ads", "payout", "fulfilment"})
    rows = {p["key"]: p for p in r["provenance"]}
    for k in ("ad_rate", "payout_rate", "fulfilment_fee"):
        assert rows[k]["value"] == 0 and rows[k]["status"] == "assumption"
    d = tools._compact_cost(r)["display"]
    assert d["not_included"] == ["advertising", "payout and currency conversion fee", "fulfilment fee per order"]
    assert not any("Advertising" in a or "Fulfilment" in a for a in d["assumptions_to_replace"])  # never "0%"


@pytest.mark.parametrize("market", ["DE", "FR", "HU", "US"])
@pytest.mark.parametrize("extra", [{"ad_rate": 0.12}, {"payout_rate": 0.015}, {"fulfilment_fee": 3.2}, FULL])
def test_closed_form_still_hits_the_target(market, extra):
    r = engine.landed_cost(Inputs(**{**BEAR, "market": market, **extra, "indicative": market == "US"}))
    wf = r["waterfall"]
    assert sum(s["value"] for s in wf["steps"]) == pytest.approx(wf["price"], abs=0.03)
    assert wf["margin_pct"] == pytest.approx(0.25, abs=1e-4)
    assert r["monte_carlo"]["p50_margin"] == pytest.approx(0.25, abs=0.01)
    # each cost the seller pays raises the price
    assert wf["price"] > engine.landed_cost(Inputs(**{**BEAR, "market": market, "indicative": market == "US"}))["waterfall"]["price"]


def test_each_line_is_what_it_says():
    r = price(**FULL)
    wf = r["waterfall"]
    steps = {s["key"]: s["value"] for s in wf["steps"]}
    assert steps["ads"] == pytest.approx(0.12 * wf["price"], abs=0.01)
    assert steps["fulfilment"] == pytest.approx(3.2)
    assert steps["payout"] == pytest.approx(0.01 * wf["net_revenue"], abs=0.01)
    for k in FULL:
        assert next(p for p in r["provenance"] if p["key"] == k)["status"] == "seller_input"
    assert tools._compact_cost(r)["display"]["not_included"] == []


def test_reverse_questions_invert_the_same_formula():
    x = Inputs(**{**BEAR, **FULL})
    target = engine.landed_cost(x)["waterfall"]["price"]
    chk = engine.price_check(x, target)
    assert chk["margin_pct"] == pytest.approx(0.25, abs=1e-3)
    # paying exactly the max unit cost at that price earns exactly the target
    again = engine.price_check(Inputs(**{**BEAR, **FULL, "cogs_cny": chk["max_cogs_for_target"]}), target)
    assert again["margin_pct"] == pytest.approx(0.25, abs=1e-3)
    assert engine.sweep(x)["target_price"] == pytest.approx(target, abs=0.01)
    de = next(row for row in engine.compare_eu(x)["rows"] if row["market"] == "DE")
    assert de["target_price"] == pytest.approx(target, abs=0.01)


def test_ads_can_make_a_margin_unreachable():
    with pytest.raises(engine.EngineError, match="unreachable"):
        price(ad_rate=0.5, target_margin=0.4)


def test_ad_stress_row_only_when_the_seller_advertises():
    assert not any("Advertising" in s["scenario"] for s in price()["stress"])
    row = next(s for s in price(ad_rate=0.12)["stress"] if "Advertising" in s["scenario"])
    assert row["margin_pct"] < 0.25 and "17%" in row["scenario"]


# ------------------------------------------------------------------ volumetric weight
def test_freight_on_the_box_when_it_is_bulky():
    r = price(dims_cm=[30, 25, 20])
    assert r["inputs"]["chargeable_weight_kg"] == pytest.approx(2.5)  # 15000 / 6000
    plain = price()
    f = lambda res: next(s["value"] for s in res["waterfall"]["steps"] if s["key"] == "freight")  # noqa: E731
    assert f(r) == pytest.approx(f(plain) * 2.5 / 0.3, abs=0.02)
    assert any("box size" in w for w in r["warnings"])
    assert tools._compact_cost(r)["display"]["chargeable_weight"].startswith("2.5 kg")
    row = next(p for p in r["provenance"] if p["key"] == "volumetric_divisor")
    assert row["value"] == 6000 and row["status"] == "secondary" and row["source_url"]


def test_a_dense_box_is_charged_on_its_actual_weight():
    r = price(dims_cm=[10, 10, 5], weight_kg=0.6)  # 0.083 kg volumetric
    assert r["inputs"]["chargeable_weight_kg"] == pytest.approx(0.6)
    assert not any("box size" in w for w in r["warnings"])
    assert tools._compact_cost(r)["display"]["chargeable_weight"] is None
    assert r["waterfall"]["price"] == price(weight_kg=0.6)["waterfall"]["price"]


def test_the_sellers_divisor_wins():
    r = price(dims_cm=[30, 25, 20], volumetric_divisor=5000)
    assert r["inputs"]["chargeable_weight_kg"] == pytest.approx(3.0)
    assert next(p for p in r["provenance"] if p["key"] == "volumetric_divisor")["status"] == "seller_input"


def test_multipack_counts_the_box():
    # two boxed bears weigh twice the chargeable weight of one, not twice the bare 0.3 kg
    r = price(dims_cm=[20, 15, 10], weight_kg=0.2)  # 0.5 kg volumetric
    pack = next(o for o in r["multipack_tip"]["options"] if o["units"] == 2)
    two = engine.landed_cost(Inputs(**{**BEAR, "weight_kg": 1.0, "cogs_cny": 40}))["waterfall"]["price"]
    assert pack["pack_price"] == pytest.approx(two, abs=0.01)


@pytest.mark.parametrize("bad", [[30, 25], [30, 25, 0], [30, 25, 400], "30x25x20"])
def test_bad_box_sizes_are_refused(bad):
    with pytest.raises(engine.EngineError):
        price(dims_cm=bad)


# ------------------------------------------------------------------ the seller's words reach the engine
def test_stated_costs_and_box_reach_the_engine(monkeypatch):
    msg = "Plush bear, cost ¥20, 0.3 kg, box 30x25x20 cm, Germany, 25% margin, ads 12% of sales, FBA fee €3.20, payout fee 1%"
    script = [NS(content="", tool_calls=[_call(1, "landed_cost", BEAR)]), NS(content="ok", tool_calls=None)]
    events, _ = run_with(monkeypatch, script, [{"role": "user", "content": msg}])
    args = next(e for e in events if e["type"] == "tool_call" and e["name"] == "landed_cost")["args"]
    assert args["ad_rate"] == 0.12 and args["fulfilment_fee"] == 3.2 and args["payout_rate"] == 0.01
    assert args["dims_cm"] == [30.0, 25.0, 20.0]
    res = next(e for e in events if e["type"] == "tool_result" and e["name"] == "landed_cost")["result"]
    assert res["inputs"]["chargeable_weight_kg"] == pytest.approx(2.5)


@pytest.mark.parametrize("text, want", [
    ("Germany 25% ads 12%", {"ad_rate": 0.12}),
    ("I spend 9% on ads, Germany 25% margin", {"ad_rate": 0.09}),
    ("14% TACoS, 25% margin", {"ad_rate": 0.14}),
    ("毛绒熊 成本20元 箱规 300*250*200 毫米 德国 25% 广告费 12% 提现费 1%",
     {"ad_rate": 0.12, "payout_rate": 0.01, "dims_cm": [30.0, 25.0, 20.0]}),
    ("10% on ads and fulfilment 2.5 EUR per order", {"ad_rate": 0.1, "fulfilment_fee": 2.5}),
    ("Compare a 10% and 15% ad spend", {}),
    ("Blender ¥38 0.6kg DE 25% margin, 5x2x3", {}),  # no unit, no box
])
def test_stated_cost_phrasings(text, want):
    assert agent.stated_overrides([text], "DE") == want


def test_saved_amounts_in_a_currency_follow_the_currency():
    prof = {"market": "DE", "fulfilment_fee": 3.0, "fx": 7.5, "ad_rate": 0.1}
    fr = agent.apply_profile("landed_cost", {"market": "FR", "cogs_cny": 20, "weight_kg": 0.3}, prof)
    us = agent.apply_profile("landed_cost", {"market": "US", "cogs_cny": 20, "weight_kg": 0.3}, prof)
    assert fr["fulfilment_fee"] == 3.0 and fr["fx"] == 7.5 and fr["ad_rate"] == 0.1  # EUR is EUR in France too
    assert "fulfilment_fee" not in us and "fx" not in us and us["ad_rate"] == 0.1  # a € fee is not a $ fee


def test_api_accepts_the_new_inputs():
    from fastapi.testclient import TestClient

    from api.main import app

    c = TestClient(app)
    r = c.post("/api/calc", json={**BEAR, **FULL, "dims_cm": [30, 25, 20]})
    assert r.status_code == 200 and r.json()["inputs"]["chargeable_weight_kg"] == pytest.approx(2.5)
    assert c.post("/api/calc", json={**BEAR, "dims_cm": [30, 25]}).status_code == 422
    assert c.post("/api/calc", json={**BEAR, "ad_rate": 0.7}).status_code == 422
    json.dumps(r.json())  # plain JSON all the way down
