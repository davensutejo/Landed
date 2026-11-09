"""Agent loop mechanics against a scripted fake LLM (no network, no key)."""
import json
from types import SimpleNamespace as NS

from landed import agent


def _call(i, name, args):
    return NS(id=f"call_{i}", type="function", function=NS(name=name, arguments=json.dumps(args)))


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.seen = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        self.seen.append(kw)
        msg = self.script.pop(0)
        return NS(choices=[NS(message=msg)])


def run_with(monkeypatch, script, history):
    fake = FakeLLM(script)
    monkeypatch.setattr(agent, "client", lambda: fake)
    monkeypatch.setattr(agent, "_log", lambda t: None)
    return list(agent.run(history)), fake


def test_tool_loop_and_guardrail(monkeypatch):
    script = [
        NS(content="", tool_calls=[_call(1, "classify_hs", {"description": "blender", "attributes": {
            "has_electric_motor": True, "motor_self_contained": True, "has_heating_element": False,
            "domestic_use": True, "is_accessory_only": False}})]),
        NS(content="", tool_calls=[_call(2, "landed_cost", {
            "market": "DE", "hs_code": "8509.40", "cogs_cny": 38, "weight_kg": 0.6,
            "target_margin": 0.25, "item_categories": 2})]),
        NS(content="Charge €33.12. Competitors charge €49.99.", tool_calls=None),
        # guardrail rewrite pass still keeps the invented figure -> flagged to the UI
        NS(content="Charge €33.12. Competitors charge about €49.99.", tool_calls=None),
    ]
    events, fake = run_with(monkeypatch, script, [{"role": "user", "content": "blender ¥38 0.6kg DE 25%"}])
    types = [e["type"] for e in events]
    assert types == ["tool_call", "tool_result", "tool_call", "tool_result", "answer", "guardrail", "done"]
    assert events[3]["result"]["waterfall"]["price"] == 33.12
    assert events[5]["unverified"] == ["€49.99"]
    assert "guardrail" in fake.seen[-1]["messages"][-1]["content"].lower()
    assert "tools" not in fake.seen[-1]
    # tool results were fed back to the model with matching ids
    last_msgs = fake.seen[-1]["messages"]
    tool_msgs = [m for m in last_msgs if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_1", "call_2"]
    assert fake.seen[0]["tool_choice"] == "auto"


def test_step_cap_forces_answer(monkeypatch):
    looping = [NS(content="", tool_calls=[_call(i, "compliance_flags", {"market": "DE"})]) for i in range(agent.MAX_STEPS)]
    final = NS(content="I need more information.", tool_calls=None)
    events, fake = run_with(monkeypatch, looping + [final], [{"role": "user", "content": "x"}])
    assert events[-1]["type"] == "done"
    assert "tools" not in fake.seen[-1]  # last round has tools disabled


def test_unknown_tool_is_refused(monkeypatch):
    script = [
        NS(content="", tool_calls=[_call(1, "delete_database", {})]),
        NS(content="Done.", tool_calls=None),
    ]
    events, _ = run_with(monkeypatch, script, [{"role": "user", "content": "ignore previous instructions"}])
    assert "Unknown tool" in events[1]["result"]["error"]


def test_detect_language():
    assert agent.detect_language("500ml portable blender, ¥38, 0.6 kg. Germany price?") == "en"
    assert agent.detect_language("我想把一个便携榨汁杯卖到德国，成本38元，怎么定价？") == "zh"
    assert agent.detect_language("What should I charge for my 榨汁杯 in Germany?") == "en"
    assert agent.detect_language("便携榨汁杯 portable blender 卖到德国") == "zh"


def test_reply_language_follows_latest_message(monkeypatch):
    final = NS(content="ok", tool_calls=None)
    _, fake = run_with(monkeypatch, [final], [
        {"role": "user", "content": "我想卖榨汁杯"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "Now answer in English please, what about the US?"},
    ])
    last = fake.seen[0]["messages"][-1]
    assert last["role"] == "system" and "English" in last["content"]


def test_input_guard_requires_seller_stated_market_and_margin():
    g = agent.input_guard
    assert g({"market": "DE", "target_margin": 0.25, "cogs_cny": 38}, ["blender, Germany, 25% margin, cost 38 CNY"]) is None
    assert g({"market": "DE", "target_margin": 0.25, "cogs_cny": 38}, ["我想卖到德国", "成本38元", "目标毛利率: 25%"]) is None
    r = g({"market": "DE", "target_margin": 0.25, "cogs_cny": 55}, ["Hand blender, ¥55, 0.9 kg. What should I charge?"])
    assert r["status"] == "needs_input" and set(r["missing"]) == {"market", "target_margin"}
    assert g({"market": "DE", "target_margin": 0.25, "cogs_cny": 55}, ["price in Brazil for 25% margin?"])["status"] == "out_of_scope"
    assert g({"market": "US", "target_margin": 0.25, "cogs_cny": 38}, ["tell us the price in germany at 25%, cost 38 yuan"])["missing"] == ["market"]


def test_input_guard_rejects_a_cost_the_seller_never_gave():
    # m03: "0.6 kg" was passed as a cost of 0.6 CNY
    g = agent.input_guard
    text = ["Portable blender, HS 8509.40 confirmed, 0.6 kg, Germany, 25% margin. What price?"]
    assert g({"market": "DE", "target_margin": 0.25, "cogs_cny": 0.6}, text)["missing"] == ["cogs_cny"]
    # a cost is stated, but the call uses a different number
    assert g({"market": "DE", "target_margin": 0.25, "cogs_cny": 12}, ["cost 38 CNY, Germany, 25%"])["missing"] == ["cogs_cny"]


def test_guard_blocks_assumed_market_in_loop(monkeypatch):
    script = [
        NS(content="", tool_calls=[_call(1, "landed_cost", {"market": "DE", "hs_code": "8509.40", "cogs_cny": 55, "weight_kg": 0.9, "target_margin": 0.25})]),
        NS(content="Which market and margin?", tool_calls=None),
    ]
    events, _ = run_with(monkeypatch, script, [{"role": "user", "content": "Hand blender, HS 8509.40 confirmed, ¥55, 0.9 kg. What should I charge?"}])
    assert events[1]["result"]["status"] == "needs_input"


def test_guardrail_rewrite_removes_invented_specs(monkeypatch):
    script = [
        NS(content="Leistungsstarker 600W Motor, CE-zertifiziert, BPA-frei.", tool_calls=None),
        NS(content="Motor: [Leistung in W: bitte ergänzen]. CE-Kennzeichnung ist vor dem Verkauf erforderlich.", tool_calls=None),
    ]
    events, fake = run_with(monkeypatch, script, [{"role": "user", "content": "Write a German listing for my portable blender, 500ml."}])
    assert [e["type"] for e in events] == ["answer", "done"]
    assert "bitte ergänzen" in events[0]["text"]
    assert len(fake.seen) == 2


def test_unsupported_market_answered_without_llm(monkeypatch):
    events, fake = run_with(monkeypatch, [], [{"role": "user", "content": "Price for Brazil at 30% margin? HS 8509.40, ¥38"}])
    assert [e["type"] for e in events] == ["answer", "done"]
    assert "Brazil" in events[0]["text"] and "EU" in events[0]["text"]
    assert fake.seen == []
    zh, _ = run_with(monkeypatch, [], [{"role": "user", "content": "卖到巴西应该定价多少？"}])
    assert "巴西" in zh[0]["text"]


def test_mixed_markets_go_to_the_model(monkeypatch):
    events, fake = run_with(monkeypatch, [NS(content="Germany only for now.", tool_calls=None)],
                            [{"role": "user", "content": "Compare Germany and Brazil for my blender"}])
    assert len(fake.seen) == 1


def test_question_card_ends_turn_with_fixed_line(monkeypatch):
    script = [NS(content="", tool_calls=[_call(1, "classify_hs", {"description": "portable blender"})])]
    events, fake = run_with(monkeypatch, script, [{"role": "user", "content": "Portable blender for Germany, price?"}])
    assert events[1]["result"]["status"] == "ambiguous"
    assert events[2] == {"type": "answer", "text": agent.CARD_REPLY["hs"]["en"]}
    assert len(fake.seen) == 1  # no second model call to restate the question


def test_confirmed_hs_in_message_continues_past_card(monkeypatch):
    script = [
        NS(content="", tool_calls=[_call(1, "classify_hs", {"description": "portable blender"})]),
        NS(content="ok", tool_calls=None),
    ]
    _, fake = run_with(monkeypatch, script, [{"role": "user", "content": "Portable blender, confirmed HS 8509.40"}])
    assert len(fake.seen) == 2


def test_us_result_is_marked_lower_bound():
    # The older Section 301 list duty (7.5% or 25%, by list) is NOT loaded: sources disagree on which list
    # 8509.40 is on, so the US price is a floor that includes only MFN + the verified 12.5% China duty.
    from landed import data
    from landed.tools import dispatch
    for_llm, _ = dispatch("landed_cost", {"market": "US", "hs_code": "8509.40", "cogs_cny": 38, "weight_kg": 0.6, "target_margin": 0.25})
    assert for_llm["price_is_lower_bound"] is True
    assert for_llm["display"]["price_label"].startswith("Lower-bound")
    de, _ = dispatch("landed_cost", {"market": "DE", "hs_code": "8509.40", "cogs_cny": 38, "weight_kg": 0.6, "target_margin": 0.25})
    assert "price_is_lower_bound" not in de
    assert any("snapshot 2026-11-08" in s for s in de["display"]["sources"])
    from landed.engine import Inputs, build_params
    p = build_params(Inputs(market="US", hs_code="8509.40", cogs_cny=38, weight_kg=0.6, target_margin=0.25))
    assert abs(p.duty_rate - (0.042 + 0.125)) < 1e-9
    assert p.us_list_known is False
    assert data.rate("us_forced_labor_301_china", "US").status == "verified"


def test_us_with_list_duty_loaded_adds_it(monkeypatch):
    from landed import data, tools
    real = data.rate

    def with_list(key, market):
        if key.startswith("us_section301_list_"):
            return data.Rate(key, "US", 0.075, "ratio", "secondary", "https://example.test", "2026-11-08", "test")
        return real(key, market)

    monkeypatch.setattr(data, "rate", with_list)
    out, _ = tools.dispatch("landed_cost", {"market": "US", "hs_code": "8509.40", "cogs_cny": 38, "weight_kg": 0.6, "target_margin": 0.25})
    assert "price_is_lower_bound" not in out
    from landed.engine import Inputs, build_params
    assert abs(build_params(Inputs(market="US", hs_code="8509.40", cogs_cny=38, weight_kg=0.6, target_margin=0.25)).duty_rate - (0.042 + 0.125 + 0.075)) < 1e-9


def test_every_eu_country_prices_with_its_own_vat():
    from landed import data
    from landed.markets import EU_COUNTRIES
    from landed.tools import dispatch
    seen = {}
    for code in EU_COUNTRIES:
        out, _ = dispatch("landed_cost", {"market": code, "cogs_cny": 38, "weight_kg": 0.6, "target_margin": 0.25})
        assert out.get("status") != "abstain" and "waterfall" in out, code
        vat = data.rate("vat_standard", code)
        assert any(f"{vat.value:.1%}" in w for w in out["warnings"]), code
        seen[code] = out["waterfall"]["price"]
    assert seen["HU"] > seen["DE"] > seen["LU"]  # 27% > 19% > 17%


def test_eu_country_detection_and_compliance():
    from landed.agent import markets_in
    from landed import compliance
    assert markets_in("sell in France at 25%")[0] == ["FR"]
    assert markets_in("卖到西班牙")[0] == ["ES"]
    assert markets_in("Europe, 30% margin")[0] == ["DE"]
    assert markets_in("北爱尔兰")[0] == []
    assert markets_in("Australia")[0] == [] and markets_in("Australia")[1] == ["Australia"]
    ids = {f["id"] for f in compliance.flags("FR", {"electrical": True})["flags"]}
    assert {"ce_eu", "gpsr_eu"} <= ids


def test_platform_fee_is_sourced_and_changes_the_price():
    from landed import data, engine, platforms
    base = engine.landed_cost(engine.Inputs(market="DE", cogs_cny=38, weight_kg=0.6, target_margin=0.25))
    tik = engine.landed_cost(engine.Inputs(market="DE", cogs_cny=38, weight_kg=0.6, target_margin=0.25, platform="tiktok"))
    assert tik["waterfall"]["price"] < base["waterfall"]["price"]  # 9% < the 15% placeholder
    row = next(r for r in tik["provenance"] if r["label"].startswith("Platform fee ("))
    assert row["status"] == "secondary" and row["source_url"] and row["value"] == 0.09
    # a seller's own fee always wins over the platform default
    own = engine.landed_cost(engine.Inputs(market="DE", cogs_cny=38, weight_kg=0.6, target_margin=0.25, platform="tiktok", fee_rate=0.20))
    assert own["waterfall"]["price"] > base["waterfall"]["price"]
    assert not any(r["label"].startswith("Platform fee (") for r in own["provenance"])
    # category-specific rate: electronics on Kaufland is cheaper than the default
    e = platforms.fee("kaufland", "DE", "electronics")["value"]
    assert e < platforms.fee("kaufland", "DE", "apparel")["value"]


def test_fixed_fee_keeps_the_margin_on_target():
    from landed import engine
    r = engine.landed_cost(engine.Inputs(market="DE", cogs_cny=6, weight_kg=0.05, target_margin=0.25, platform="ebay"))
    wf = r["waterfall"]
    assert any(p["label"].startswith("Platform fixed fee") for p in r["provenance"])
    assert abs(wf["margin_pct"] - 0.25) < 0.005  # the per-order fee is inside the price, not on top of it
    assert r["monte_carlo"]["p50_margin"] > 0.2


def test_platform_unknown_fee_falls_back_with_a_warning():
    from landed import engine
    r = engine.landed_cost(engine.Inputs(market="NL", cogs_cny=38, weight_kg=0.6, target_margin=0.25, platform="bol"))
    assert any("No sourced fee for bol.com" in w for w in r["warnings"])
    # a platform that isn't sold in the market is ignored without a warning
    r2 = engine.landed_cost(engine.Inputs(market="NL", cogs_cny=38, weight_kg=0.6, target_margin=0.25, platform="kaufland"))
    assert not any("No sourced fee" in w for w in r2["warnings"])


def test_profile_platform_reaches_the_tool_call_and_legacy_ids_still_load():
    from landed import agent, profile
    args = agent.apply_profile("landed_cost", {"market": "DE", "cogs_cny": 38, "weight_kg": 0.6, "target_margin": 0.25},
                               profile.clean({"platform": "amazon_de", "category": "electronics"}))
    assert args["platform"] == "amazon" and args["fee_category"] == "electronics"
    own = agent.apply_profile("landed_cost", {"market": "DE", "fee_rate": 0.2}, {"platform": "amazon"})
    assert "platform" not in own


def test_fallback_model_used_when_main_is_rate_limited(monkeypatch):
    import httpx
    from openai import RateLimitError

    calls = []

    class Comp:
        def create(self, **kw):
            calls.append(kw["model"])
            if kw["model"] == "main":
                raise RateLimitError("slow down", response=httpx.Response(429, request=httpx.Request("POST", "http://x")), body=None)
            return "ok"

    llm = NS(chat=NS(completions=Comp()))
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "backup")
    assert agent.complete(llm, model="main", messages=[]) == "ok"
    assert calls == ["main", "backup"]
    monkeypatch.delenv("LLM_FALLBACK_MODEL")
    calls.clear()
    try:
        agent.complete(llm, model="main", messages=[])
        raise AssertionError("should have raised")
    except RateLimitError:
        pass


def test_platform_not_sold_in_the_country_is_not_applied():
    from landed import engine

    base = dict(market="FR", cogs_cny=38, weight_kg=0.6, target_margin=0.25, hs_code="8509.40")
    kaufland = engine.landed_cost(engine.Inputs(**base, platform="kaufland"))
    plain = engine.landed_cost(engine.Inputs(**base))
    assert kaufland["waterfall"]["price"] == plain["waterfall"]["price"]  # Kaufland's 7-14% is not borrowed for France
    assert any("not sold in" in w for w in kaufland["warnings"])
    cd = engine.landed_cost(engine.Inputs(**base, platform="cdiscount"))
    assert any("No sourced fee" in w for w in cd["warnings"])  # sold in France, but no fee found


def test_platform_list_follows_the_country():
    from landed import platforms

    assert "kaufland" in platforms.available("DE") and "kaufland" not in platforms.available("FR")
    assert "cdiscount" in platforms.available("FR") and "bol" in platforms.available("NL")
    assert "allegro" in platforms.available("PL") and "walmart" in platforms.available("US")


def test_listing_language_follows_the_destination_market():
    from landed import markets

    assert markets.listing_language("FR") == "French" and markets.listing_language("PL") == "Polish"
    assert markets.listing_language("US") == "English" and markets.listing_language("DE") == "German"
    assert set(markets.LISTING_LANGUAGE) == set(markets.EU_COUNTRIES) | {"US"}  # every market has one
    assert "FR French" in agent.SYSTEM_PROMPT and "{LISTING_LANGUAGES}" not in agent.SYSTEM_PROMPT


def test_guardrail_catches_invented_claims_in_other_listing_languages():
    from landed import guardrail

    for text in ("Mixeur certifié CE, sans BPA, lave-vaisselle", "Frullatore impermeabile, certificato CE",
                 "Licuadora certificada, apta para lavavajillas, sin BPA", "Blender waterdicht, BPA-vrij",
                 "Blender wodoodporny, certyfikowany"):
        assert guardrail.check(text, [], []), text
    # a disclaimer is not a claim
    assert not guardrail.check("Nous ne sommes pas certifiés comme courtier.", [], [])


def test_guardrail_units_and_claims():
    from landed import guardrail
    seller = ["portable blender 500ml, 0.6 kg"]
    bad = guardrail.check("600W Motor, 500 ml, 0,6 kg. CE-zertifiziert, BPA-frei, spülmaschinenfest.", [], seller)
    assert bad == ["600W", "BPA-frei", "CE-zertifiziert", "spülmaschinenfest"]
    ok = guardrail.check("CE marking required. Dies ist keine zertifizierte Zollberatung. 需要CE认证。", [], seller)
    assert ok == []


def test_out_of_category_product_gets_no_card(monkeypatch):
    script = [
        NS(content="", tool_calls=[_call(1, "classify_hs", {"description": "electric scooter", "in_category": False})]),
        NS(content="Electric scooters are outside Landed's category.", tool_calls=None),
    ]
    events, fake = run_with(monkeypatch, script, [{"role": "user", "content": "Electric scooter, ¥900, 14 kg, Germany 25%"}])
    assert events[1]["result"]["status"] == "out_of_scope"
    assert events[2]["text"].startswith("Electric scooters")
    assert len(fake.seen) == 2


def test_form_refused_when_all_inputs_given(monkeypatch):
    script = [
        NS(content="", tool_calls=[_call(1, "ask_seller", {"fields": ["cogs_cny", "item_categories"]})]),
        NS(content="", tool_calls=[_call(2, "landed_cost", {"market": "DE", "cogs_cny": 12, "weight_kg": 0.25, "target_margin": 0.3})]),
        NS(content="Recommended price €15.09", tool_calls=None),
    ]
    events, _ = run_with(monkeypatch, script, [{"role": "user", "content": "棉袜5双一包，成本12元，0.25公斤，卖到德国，毛利30%"}])
    assert events[1]["result"]["status"] == "not_needed"
    assert events[3]["result"]["waterfall"]["price"] == 15.09
    assert events[-1]["type"] == "done"


def test_form_trimmed_to_missing_required_fields(monkeypatch):
    script = [NS(content="", tool_calls=[_call(1, "ask_seller", {"fields": ["target_margin", "item_categories", "battery_builtin"]})])]
    events, _ = run_with(monkeypatch, script, [{"role": "user", "content": "Phone case, cost ¥6, 0.05 kg, Germany. Price?"}])
    assert events[0]["args"]["fields"] == ["target_margin"]
    assert events[2]["text"] == agent.CARD_REPLY["ask"]["en"]


def test_two_refusals_turn_tools_off_and_markup_is_stripped(monkeypatch):
    script = [
        NS(content="", tool_calls=[_call(1, "landed_cost", {"market": "DE", "cogs_cny": 12, "weight_kg": 0.25, "target_margin": 0.3})]),
        NS(content="", tool_calls=[_call(2, "ask_seller", {"fields": ["market"]})]),
        NS(content="No US duty for socks yet. <tool_call>ask_seller<arg_key>x</arg_key></tool_call>", tool_calls=None),
    ]
    events, fake = run_with(monkeypatch, script, [{"role": "user", "content": "Socks ¥12, 0.25 kg, US, 30% margin"}])
    assert "tools" not in fake.seen[-1]
    assert events[-2]["text"] == "No US duty for socks yet."


def test_de_prices_without_hs_and_us_needs_it():
    from landed import data, engine
    r = engine.landed_cost(engine.Inputs(market="DE", cogs_cny=12, weight_kg=0.25, target_margin=0.3))
    assert r["waterfall"]["price"] == 15.09 and r["inputs"]["hs_code"] is None
    assert r["multipack_tip"]["options"][0]["units"] == 2
    import pytest
    with pytest.raises(data.MissingRate):
        engine.landed_cost(engine.Inputs(market="US", cogs_cny=12, weight_kg=0.25, target_margin=0.3))
    with pytest.raises(data.MissingRate):  # above EUR 150 with no conventional rate loaded
        engine.landed_cost(engine.Inputs(market="DE", cogs_cny=900, weight_kg=14, target_margin=0.25))


def test_hs_infers_obvious_attributes():
    from landed import hs
    r = hs.classify("Portable blender")
    assert r["known_attributes"]["has_electric_motor"] is True
    assert r["next_question"]["attribute"] == "has_heating_element"
    assert hs.classify("Smoothie machine for cafes")["status"] == "resolved"


def test_tool_call_written_as_text_is_retried_not_shown(monkeypatch):
    """DeepSeek sometimes emits its tool call as text (DSML). The seller must never see it."""
    from types import SimpleNamespace as NS
    from landed import agent

    replies = iter([
        NS(choices=[NS(message=NS(content='<｜DSML｜function_calls><｜DSML｜invoke name="landed_cost">', tool_calls=None))]),
        NS(choices=[NS(message=NS(content="Here is a normal answer.", tool_calls=None))]),
    ])
    monkeypatch.setattr(agent, "complete", lambda llm, **kw: next(replies))
    monkeypatch.setattr(agent, "client", lambda: object())
    ev = list(agent.run([{"role": "user", "content": "hello there"}]))
    answers = [e["text"] for e in ev if e["type"] == "answer"]
    assert answers == ["Here is a normal answer."]


def test_tool_call_text_every_time_gives_a_plain_apology(monkeypatch):
    from types import SimpleNamespace as NS
    from landed import agent

    bad = NS(choices=[NS(message=NS(content="<｜DSML｜invoke name=landed_cost>", tool_calls=None))])
    monkeypatch.setattr(agent, "complete", lambda llm, **kw: bad)
    monkeypatch.setattr(agent, "client", lambda: object())
    ev = list(agent.run([{"role": "user", "content": "hello there"}]))
    answers = [e["text"] for e in ev if e["type"] == "answer"]
    assert len(answers) == 1 and "DSML" not in answers[0] and "again" in answers[0].lower()
