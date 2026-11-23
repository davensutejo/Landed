"""Product facts for the compliance check are read from the seller's words in code, not left to the model."""
import json
from types import SimpleNamespace as NS

import pytest

from landed import agent
from landed.product_facts import facts_in, stated

from test_agent import _call, run_with


@pytest.mark.parametrize("text, want", [
    ("Portable blender with built-in battery, cost ¥38, 0.6 kg, selling on Amazon Germany, 25% margin",
     {"battery_builtin": True, "food_contact": True, "electrical": True}),
    ("500ml portable blender with battery, ¥38 cost, 0.6kg, shipping to Germany (25% margin)",
     {"battery_builtin": True, "food_contact": True, "electrical": True}),
    ("便携榨汁杯，内置锂电池，成本38元，0.6公斤，卖到德国，毛利25%", {"battery_builtin": True, "food_contact": True, "electrical": True}),
    ("Cotton socks 5-pack, cost ¥12, 0.25 kg, Germany, 25% target margin", {"textile": True}),
    ("纯棉袜子5双装，成本12元，0.25公斤，德国，25%", {"textile": True}),
    ("Phone case, cost ¥6, 0.05 kg, Germany, 25% target margin", {}),
    ("Wireless earbuds ¥45 0.1kg US 30%", {"battery_builtin": True, "electrical": True}),
    ("无线蓝牙耳机，成本45元", {"battery_builtin": True, "electrical": True}),
    ("Face serum 30ml ¥18 0.1 kg Germany 25%", {"cosmetic": True}),
    ("Plush bear toy ¥20 0.3kg DE 25%", {"toy": True}),
    ("Stainless steel water bottle ¥25 0.4kg DE 25%", {"food_contact": True}),
    ("Mini food chopper with built-in motor", {"food_contact": True, "electrical": True}),
    ("我卖便携榨汁杯，成本18元", {"food_contact": True, "electrical": True}),
    ("Electric scooter, ¥900, 14 kg", {"battery_builtin": True, "electrical": True}),
    # negations and look-alikes
    ("Angle grinder ¥80", {}),
    ("Manual citrus juicer, plastic, ¥15, 0.3kg, France 25%", {"food_contact": True, "electrical": False}),
    ("不带电池的手动榨汁器，成本15元", {"battery_builtin": False, "food_contact": True}),
    ("LED desk lamp 5V USB, non-rechargeable, ¥30, 0.5kg", {"battery_builtin": False, "electrical": True}),
    ("Remote control car toy, batteries not included, ¥60", {"toy": True}),
    ("Dog toy squeaky ¥8 0.1kg DE 25%", {}),
    ("Phone holder with suction cups ¥9 0.1kg DE 25%", {}),
    ("Makeup brush set ¥20 0.2kg DE 25%", {}),
    ("Air conditioner cover ¥40, 1kg", {}),
])
def test_facts_in_seller_words(text, want):
    assert facts_in(text) == want


def test_facts_follow_the_product_being_priced_now():
    blender = "blender with battery ¥38 0.6kg DE 25%"
    # a follow-up about another market keeps the product
    assert stated([blender, "what about France?"])["battery_builtin"] is True
    # a new product starts over: the blender's battery does not carry over to socks
    assert stated([blender, "now cotton socks, ¥12, 0.25kg"]) == {"textile": True}
    # the input form's answers belong to the product described before them, and an explicit "no" wins
    form_no = "Unit cost (CNY): ¥38; Shipping weight (kg): 0.6; Target margin: 25%; Built-in lithium battery? no."
    assert stated(["portable blender for Germany", form_no]) == {"food_contact": True, "electrical": True, "battery_builtin": False}
    assert stated(["portable blender for Germany", "单位成本（元）: ¥38；是否内置锂电池？ 是。"])["battery_builtin"] is True


MSG = "Portable blender with built-in battery, cost ¥38, 0.6 kg, selling on Amazon Germany, 25% margin"
PRICE = {"market": "DE", "cogs_cny": 38, "weight_kg": 0.6, "target_margin": 0.25}


def test_seller_facts_win_over_the_model(monkeypatch):
    # the live failure: the model passed no battery and no food contact for a battery blender
    script = [
        NS(content="", tool_calls=[_call(1, "landed_cost", PRICE),
                                   _call(2, "compliance_flags", {"market": "DE", "has_electric_motor": True, "textile": False})]),
        NS(content="ok", tool_calls=None),
    ]
    events, _ = run_with(monkeypatch, script, [{"role": "user", "content": MSG}])
    calls = [e for e in events if e["type"] == "tool_call"]
    assert [c["name"] for c in calls] == ["landed_cost", "compliance_flags"]  # the model's own call: no second run
    assert calls[1]["args"]["battery_builtin"] is True and calls[1]["args"]["food_contact"] is True
    flags = next(e for e in events if e["type"] == "tool_result" and e["name"] == "compliance_flags")["result"]["flags"]
    assert {"un3481", "food_contact_eu", "ce_eu"} <= {f["id"] for f in flags}


def test_flags_ride_along_with_the_price_for_the_model(monkeypatch):
    script = [NS(content="", tool_calls=[_call(1, "landed_cost", PRICE)]), NS(content="ok", tool_calls=None)]
    events, fake = run_with(monkeypatch, script, [{"role": "user", "content": MSG}])
    auto = [e for e in events if e["type"] == "tool_call" and e.get("auto")]
    assert len(auto) == 1 and auto[0]["args"]["battery_builtin"] is True
    tool_msg = next(m for m in fake.seen[-1]["messages"] if m["role"] == "tool")
    body = json.loads(tool_msg["content"])
    assert "un3481" in {f["id"] for f in body["compliance_flags"]["flags"]}


def test_no_auto_check_without_a_price(monkeypatch):
    script = [NS(content="", tool_calls=[_call(1, "ask_seller", {"fields": ["cogs_cny"]})])]
    events, _ = run_with(monkeypatch, script, [{"role": "user", "content": "I sell blenders in Germany"}])
    assert not any(e.get("auto") for e in events)
