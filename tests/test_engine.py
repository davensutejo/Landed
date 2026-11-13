import pytest

from landed import data, engine, hs, compliance, guardrail
from landed.tools import dispatch

DEMO = dict(market="DE", hs_code="8509.40", cogs_cny=38, weight_kg=0.6, target_margin=0.25)


def test_waterfall_matches_browser_engine():
    # Same figures as src/lib/engine.js renders on the landing page.
    two = engine.landed_cost(engine.Inputs(**DEMO, item_categories=2))
    one = engine.landed_cost(engine.Inputs(**DEMO, item_categories=1))
    assert two["waterfall"]["price"] == pytest.approx(33.12, abs=0.01)
    assert one["waterfall"]["price"] == pytest.approx(26.37, abs=0.01)
    assert two["bundle_tip"]["price_reduction"] == pytest.approx(6.75, abs=0.01)


def test_waterfall_sums_to_price_and_hits_target():
    r = engine.landed_cost(engine.Inputs(**DEMO, item_categories=2))
    wf = r["waterfall"]
    assert sum(s["value"] for s in wf["steps"]) == pytest.approx(wf["price"], abs=0.02)
    assert wf["margin_pct"] == pytest.approx(0.25, abs=1e-4)


def test_monte_carlo_is_reproducible_and_coherent():
    a = engine.landed_cost(engine.Inputs(**DEMO))
    b = engine.landed_cost(engine.Inputs(**DEMO))
    assert a["monte_carlo"] == b["monte_carlo"]
    mc = a["monte_carlo"]
    assert mc["p5_margin"] < 0.25 < mc["floor_price_95"]  # floor price is in EUR, well above 0.25
    assert mc["floor_price_95"] > a["waterfall"]["price"]
    assert 0.3 < mc["p_below_target"] < 0.7  # priced at the mean, roughly half the paths miss


def test_every_figure_has_provenance():
    r = engine.landed_cost(engine.Inputs(**DEMO))
    for p in r["provenance"]:
        assert p["status"] in {"verified", "secondary", "assumption", "seller_input"}
        assert p["snapshot_date"]


def test_seller_override_marks_provenance():
    r = engine.landed_cost(engine.Inputs(**DEMO, fee_rate=0.08))
    fee = [p for p in r["provenance"] if p["label"] == "Platform fee"][0]
    assert fee["status"] == "seller_input"
    assert r["waterfall"]["price"] < engine.landed_cost(engine.Inputs(**DEMO))["waterfall"]["price"]


def test_us_abstains_on_unknown_hs_and_warns_on_china_tariffs():
    with pytest.raises(data.MissingRate):
        engine.landed_cost(engine.Inputs(market="US", hs_code="9999.99", cogs_cny=38, weight_kg=0.6))
    r = engine.landed_cost(engine.Inputs(market="US", hs_code="8509.40", cogs_cny=38, weight_kg=0.6))
    assert any("Section 301" in w for w in r["warnings"])


def test_unreachable_margin_raises():
    with pytest.raises(engine.EngineError):
        engine.landed_cost(engine.Inputs(**{**DEMO, "target_margin": 0.5}, fee_rate=0.5))


def test_tool_dispatch_abstains_instead_of_guessing():
    for_llm, _ = dispatch("landed_cost", {"market": "US", "hs_code": "0000.00", "cogs_cny": 10, "weight_kg": 1})
    assert for_llm["status"] == "abstain"
    for_llm, _ = dispatch("rm_rf", {})
    assert "Unknown tool" in for_llm["error"]


def test_hs_asks_when_ambiguous_and_resolves_when_specified():
    r = hs.classify("portable blender")
    assert r["status"] == "ambiguous" and r["next_question"]["attribute"]
    full = {
        "has_electric_motor": True,
        "motor_self_contained": True,
        "has_heating_element": False,
        "domestic_use": True,
        "is_accessory_only": False,
    }
    r = hs.classify("portable blender", full)
    assert r["status"] == "resolved" and r["candidates"][0]["hs"] == "8509.40"
    r = hs.classify("tritan cup", {"has_electric_motor": False, "is_accessory_only": True})
    assert r["candidates"][0]["hs"] == "3924.10"


def test_hs_question_sequence_converges():
    known: dict = {}
    for _ in range(6):
        r = hs.classify("portable blender with battery", known)
        if r["status"] == "resolved":
            break
        attr = r["next_question"]["attribute"]
        known[attr] = {
            "has_electric_motor": True,
            "motor_self_contained": True,
            "has_heating_element": False,
            "domestic_use": True,
            "is_accessory_only": False,
        }[attr]
    assert r["status"] == "resolved" and r["candidates"][0]["hs"] == "8509.40"


def test_compliance_flags_battery_and_bundle():
    f = compliance.flags("DE", {"battery_builtin": True, "food_contact": True, "has_electric_motor": True, "item_categories": 2})
    ids = {x["id"] for x in f["flags"]}
    assert {"un3481", "food_contact_eu", "ce_eu", "eu_flat_duty_set"} <= ids
    assert f["flags"][0]["severity"] == "blocker"


def test_guardrail_flags_invented_numbers():
    tool = engine.landed_cost(engine.Inputs(**DEMO, item_categories=2))
    ok = guardrail.check("Charge €33.12 for a 25% margin.", [tool], ["¥38, 0.6 kg"])
    assert ok == []
    bad = guardrail.check("Duty is 17.3% so charge €44.90.", [tool], [])
    assert set(bad) == {"17.3%", "€44.90"}


def test_sweep_risk_curve_is_monotone_and_centered():
    s = engine.sweep(engine.Inputs(**DEMO, item_categories=2))
    hit = s["p_hit_target"]
    assert all(b >= a for a, b in zip(hit, hit[1:]))          # higher price -> more likely to hit target
    i = min(range(len(s["prices"])), key=lambda k: abs(s["prices"][k] - s["target_price"]))
    assert 0.35 < hit[i] < 0.65                                  # at the mean-target price, ~half the paths hit
    assert s["target_price"] == pytest.approx(33.12, abs=0.01)


def test_guardrail_accepts_rounding_but_not_invention():
    tool = engine.landed_cost(engine.Inputs(**DEMO, item_categories=1))
    p_below = tool["monte_carlo"]["p_below_target"]  # e.g. 0.4712
    rounded = f"{round(p_below * 100)}%"
    assert guardrail.check(f"About {rounded} of paths miss the target.", [tool], []) == []
    assert guardrail.check("Charge about €26.4 or €26.", [tool], []) == []
    assert guardrail.check("Charge €19.99.", [tool], []) == ["€19.99"]


def test_guardrail_reads_european_number_formats():
    tool = {"price_eur": 26.37, "vat_rate": 0.19, "big": 1299.0}
    # symbol after the number, comma decimals, percent as a word: sourced -> pass
    assert guardrail.check("Verkaufspreis: 26,37 € inkl. 19 % MwSt.", [tool], []) == []
    assert guardrail.check("Preis 26,37 EUR, davon 19 Prozent MwSt.", [tool], []) == []
    assert guardrail.check("Prix : 1.299,00 € TTC", [tool], []) == []
    assert guardrail.check("售价 26.37 欧元", [tool], []) == []
    # the same formats with invented numbers -> flagged
    assert guardrail.check("Verkaufspreis: 29,99 €", [tool], []) == ["29,99 €"]
    assert guardrail.check("Zoll 17 Prozent", [tool], []) == ["17 Prozent"]
    assert guardrail.check("Prix 1.499,00 €", [tool], []) == ["1.499,00 €"]
    assert guardrail.check("售价 31.50 欧元", [tool], []) == ["31.50 欧元"]
    # "3 €26" is a count followed by a price, not "3 €"
    assert guardrail.check("Buy 3 €26.37 items", [tool], []) == []


def test_fx_and_volatility_are_sourced_not_demo():
    from landed import data
    for key, market in (("fx_cny_per_eur", "EU"), ("fx_cny_per_usd", "US"), ("fx_horizon_sd", "ALL")):
        r = data.rate(key, market)
        assert r.status == "verified" and "ecb.europa.eu" in r.source_url, key
    assert 7.0 < data.rate("fx_cny_per_eur", "EU").value < 8.0  # guards against a typo, not the market


def test_fashion_defaults_to_a_higher_return_rate_than_electronics():
    base = dict(market="DE", cogs_cny=38, weight_kg=0.6, target_margin=0.25)
    fashion = engine.landed_cost(engine.Inputs(**base, fee_category="apparel"))
    electronics = engine.landed_cost(engine.Inputs(**base, fee_category="electronics"))
    plain = engine.landed_cost(engine.Inputs(**base))
    assert fashion["waterfall"]["price"] > plain["waterfall"]["price"] >= electronics["waterfall"]["price"] - 0.01
    assert any(r["label"] == "Return rate, fashion" for r in fashion["provenance"])
    assert any(s["scenario"].startswith("Return rate 35%") for s in fashion["stress"])  # base + 10 points
    own = engine.landed_cost(engine.Inputs(**base, fee_category="apparel", return_rate=0.08))
    assert own["waterfall"]["price"] == pytest.approx(plain["waterfall"]["price"], abs=0.01)  # the seller's figure wins
