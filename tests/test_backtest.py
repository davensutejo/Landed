"""Backtest of the deterministic engine, with no LLM.

An independent re-implementation of the pricing formula is compared with the engine over a
large grid of markets, costs, weights, margins, platforms and return rates, then the
engine is checked against properties that must always hold (round trip, accounting identity,
monotonicity, Monte Carlo sanity, regime switch at EUR 150) and fuzzed with random and
extreme inputs. The guardrail is backtested on answers built from real tool results.
"""
import itertools
import math
import random

import pytest

from landed import data, engine, guardrail, platforms
from landed.engine import EngineError, Inputs
from landed.markets import EU_COUNTRIES

EU = sorted(EU_COUNTRIES)
STATUSES = {"verified", "secondary", "assumption", "seller_input", "unknown"}


def ref_price(x: Inputs, hs_rate=0.0) -> float:
    """Closed-form price written from the spec, not from engine.py."""
    eu = x.market != "US"
    fx = x.fx or data.rate("fx_cny_per_eur" if eu else "fx_cny_per_usd", "EU" if eu else "US").value
    vat = data.rate("vat_standard", x.market).value if eu else 0.0
    fee, fixed = data.rate("platform_fee", "ALL").value, 0.0
    if x.fee_rate is not None:
        fee = x.fee_rate
    elif x.platform and x.market in platforms.available_markets(x.platform):
        pf = platforms.fee(x.platform, x.market, x.fee_category)
        if pf:
            fee, fixed = pf["value"], pf["fixed"]
    fr = x.freight_cny_per_kg if x.freight_cny_per_kg is not None else data.rate("freight_cny_per_kg", "ALL").value
    freight = fr * x.weight_kg
    if x.return_rate is not None:
        r = x.return_rate
    else:
        group = platforms.FEE_GROUP.get(x.fee_category or "")
        a = data.rate("return_alpha", "ALL").value
        b = data.rate("return_beta", "ALL").value
        r = data.rate(f"return_mean_{group}", "ALL").value if group else a / (a + b)
    G = (x.cogs_cny + freight) / fx
    G += 3.0 * x.item_categories if eu else (x.cogs_cny / fx) * hs_rate
    d = 1 / (1 + vat) - fee - x.target_margin / (1 + vat)
    return (G * (1 + r) + fixed) / d if d > 0 else math.inf


def run(**kw):
    kw.setdefault("paths", 200)
    return engine.landed_cost(Inputs(**kw))


# ---------- 1. engine == independent formula, over a big grid ----------

PLATS = [None, *platforms.ids()]
GRID = list(itertools.product([5, 38, 120], [0.1, 0.6, 3.0], [0.10, 0.25, 0.40], [1, 2]))


@pytest.mark.parametrize("market", EU)
def test_eu_grid_matches_reference(market):
    checked = 0
    for (cogs, kg, margin, cats), plat, ret in itertools.product(GRID, PLATS[:: max(1, len(PLATS) // 5)], [None, 0.05, 0.30]):
        x = Inputs(market=market, cogs_cny=cogs, weight_kg=kg, target_margin=margin, item_categories=cats,
                   platform=plat, fee_category="electronics", return_rate=ret, paths=100)
        want = ref_price(x)
        if want > 150:  # above the flat regime with no HS code: the engine must refuse, not guess
            with pytest.raises(data.MissingRate):
                engine.landed_cost(x)
            continue
        got = engine.landed_cost(x)["waterfall"]["price"]
        assert got == pytest.approx(want, abs=0.006), (market, x)
        checked += 1
    assert checked > 100


@pytest.mark.parametrize("cogs,kg,margin", list(itertools.product([20, 60, 200, 800], [0.3, 1.5, 6], [0.15, 0.3])))
def test_us_matches_reference(cogs, kg, margin):
    x = Inputs(market="US", cogs_cny=cogs, weight_kg=kg, hs_code="8509.40", target_margin=margin, paths=100)
    rate = data.rate("duty_8509.40", "US").value + data.rate("us_forced_labor_301_china", "US").value
    got = engine.landed_cost(x)["waterfall"]["price"]
    assert got == pytest.approx(ref_price(x, hs_rate=rate), abs=0.006)


# ---------- 2. properties ----------

CASES = [(m, c, k, g) for m in ("DE", "FR", "NL", "PL", "SE") for c in (12, 45, 150) for k in (0.2, 0.8, 2.5) for g in (0.1, 0.3)]


@pytest.mark.parametrize("m,c,k,g", CASES)
def test_round_trip_and_accounting(m, c, k, g):
    out = run(market=m, cogs_cny=c, weight_kg=k, target_margin=g, platform="amazon", fee_category="electronics")
    wf = out["waterfall"]
    assert wf["margin_pct"] == pytest.approx(g, abs=0.0006)          # selling at the price earns the target
    total = sum(s["value"] for s in wf["steps"])
    assert total == pytest.approx(wf["price"], abs=0.04)              # the waterfall adds up to the price
    assert all(s["value"] >= 0 for s in wf["steps"] if s["key"] != "margin")
    assert wf["net_revenue"] == pytest.approx(wf["price"] / (1 + data.rate("vat_standard", m).value), abs=0.01)


def _p(**kw):
    base = dict(market="DE", cogs_cny=40, weight_kg=0.6, target_margin=0.25)
    base.update(kw)
    return run(**base)["waterfall"]["price"]


@pytest.mark.parametrize("field,lo,hi", [
    ("cogs_cny", 20, 80), ("weight_kg", 0.3, 2.0), ("target_margin", 0.1, 0.4), ("fee_rate", 0.05, 0.25),
    ("return_rate", 0.02, 0.3), ("freight_cny_per_kg", 20, 80), ("item_categories", 1, 3),
])
def test_price_increases_with(field, lo, hi):
    assert _p(**{field: lo}) < _p(**{field: hi})


def test_price_falls_when_yuan_is_stronger():
    assert _p(fx=8.5) < _p(fx=7.5)


def test_higher_vat_country_costs_more():
    assert _p(market="HU") > _p(market="LU")  # 27% vs 17%


def test_flat_duty_does_not_scale_with_goods():
    a = _p(cogs_cny=40, weight_kg=0.6)
    b = _p(cogs_cny=80, weight_kg=1.2)
    assert 1.5 * a < b < 2 * a


def test_regime_switch_at_150():
    cheap = run(market="DE", cogs_cny=100, weight_kg=1)
    assert cheap["waterfall"]["price"] < 150
    # above 150 the engine refuses, with or without an HS code, in calc and in the risk sweep
    for hs in (None, "8509.40"):
        with pytest.raises(data.MissingRate):
            run(market="DE", cogs_cny=900, weight_kg=2, hs_code=hs)
        with pytest.raises(data.MissingRate):
            engine.sweep(Inputs(market="DE", cogs_cny=900, weight_kg=2, hs_code=hs, paths=200))


def test_unreachable_margin_is_an_error_not_a_number():
    with pytest.raises(EngineError):
        run(market="DE", cogs_cny=40, weight_kg=0.6, target_margin=0.6, fee_rate=0.5)


@pytest.mark.parametrize("bad", [dict(cogs_cny=0), dict(cogs_cny=-5), dict(weight_kg=0), dict(target_margin=0),
                                 dict(target_margin=0.8), dict(market="JP")])
def test_invalid_inputs_rejected(bad):
    kw = dict(market="DE", cogs_cny=40, weight_kg=0.6, target_margin=0.25)
    kw.update(bad)
    with pytest.raises(EngineError):
        run(**kw)


# ---------- 3. Monte Carlo ----------

@pytest.mark.parametrize("m,c,k", [("DE", 30, 0.5), ("FR", 90, 1.5), ("IT", 15, 0.2), ("SE", 60, 1.0), ("US", 50, 0.6)])
def test_monte_carlo_sanity(m, c, k):
    mk = lambda: engine.landed_cost(Inputs(market=m, cogs_cny=c, weight_kg=k, hs_code="8509.40", paths=4000))
    out = mk()
    mc, price = out["monte_carlo"], out["waterfall"]["price"]
    assert 0.15 < mc["p_below_target"] < 0.85         # priced at the expected cost: near a coin flip
    assert mc["p_loss"] < mc["p_below_target"]
    assert mc["p5_margin"] < mc["p50_margin"]
    assert mc["floor_price_95"] > price                # a safer price costs more
    assert mc["p50_margin"] == pytest.approx(0.25, abs=0.05)
    assert sum(mc["histogram"]["counts"]) == 4000
    assert mk()["monte_carlo"] == mc                   # seeded: reproducible


@pytest.mark.parametrize("m", ["DE", "ES", "US"])
def test_sweep_is_monotone(m):
    sw = engine.sweep(Inputs(market=m, cogs_cny=40, weight_kg=0.6, hs_code="8509.40", paths=2000))
    for key in ("p_hit_target", "mean_margin", "p5_margin"):
        v = sw[key]
        assert all(b >= a - 1e-9 for a, b in zip(v, v[1:])), key
    assert all(b <= a + 1e-9 for a, b in zip(sw["p_loss"], sw["p_loss"][1:]))
    assert sw["p_hit_target"][0] < sw["p_hit_target"][-1]
    assert sw["prices"] == sorted(sw["prices"])


# ---------- 4. every number is sourced ----------

@pytest.mark.parametrize("m", ["DE", "FR", "NL", "ES", "PL", "US"])
@pytest.mark.parametrize("plat", [None, "amazon", "temu", "tiktok", "own_site", "walmart", "etsy"])
def test_provenance_complete(m, plat):
    out = run(market=m, cogs_cny=40, weight_kg=0.6, hs_code="8509.40", platform=plat, fee_category="apparel")
    assert out["provenance"]
    for row in out["provenance"]:
        assert row["status"] in STATUSES, row
        assert row["snapshot_date"], row
        if row["status"] in ("verified", "secondary"):
            assert str(row["source_url"]).startswith("http"), row
    labels = " ".join(r["label"] for r in out["provenance"]).lower()
    assert "fx" in labels and "freight" in labels


def test_us_is_always_labelled_a_lower_bound():
    out = run(market="US", cogs_cny=40, weight_kg=0.6, hs_code="8509.40")
    assert any("LOWER BOUND" in w for w in out["warnings"])


def test_unknown_us_hs_abstains():
    with pytest.raises(data.MissingRate):
        run(market="US", cogs_cny=40, weight_kg=0.6, hs_code="1234.56")
    with pytest.raises(data.MissingRate):
        run(market="US", cogs_cny=40, weight_kg=0.6)


# ---------- 5. fuzz: random and extreme inputs never produce garbage ----------

def test_fuzz_engine_never_returns_garbage():
    rnd = random.Random(20261109)
    ok = refused = 0
    for _ in range(600):
        kw = dict(
            market=rnd.choice([*EU, "US"]),
            cogs_cny=10 ** rnd.uniform(-1, 4),
            weight_kg=10 ** rnd.uniform(-2, 2),
            target_margin=rnd.uniform(0.001, 0.79),
            item_categories=rnd.randint(1, 5),
            hs_code=rnd.choice([None, "8509.40", "8516.79", "3924.10", "9999.99"]),
            platform=rnd.choice(PLATS),
            fee_category=rnd.choice([None, "apparel", "electronics", "home"]),
            fee_rate=rnd.choice([None, rnd.uniform(0, 0.4)]),
            return_rate=rnd.choice([None, rnd.uniform(0, 0.6)]),
            fx=rnd.choice([None, rnd.uniform(5, 12)]),
            freight_cny_per_kg=rnd.choice([None, rnd.uniform(0, 200)]),
            paths=100,
        )
        try:
            out = engine.landed_cost(Inputs(**kw))
        except (EngineError, data.MissingRate):
            refused += 1
            continue
        ok += 1
        wf = out["waterfall"]
        assert math.isfinite(wf["price"]) and wf["price"] > 0, kw
        assert abs(wf["margin_pct"] - kw["target_margin"]) < 0.001, kw
        assert sum(s["value"] for s in wf["steps"]) == pytest.approx(wf["price"], abs=0.05), kw
        mc = out["monte_carlo"]
        assert 0 <= mc["p_loss"] <= mc["p_below_target"] + 1e-9
        assert mc["p_below_target"] <= 1.0
    assert ok > 100 and refused > 20


# ---------- 6. guardrail backtest on answers built from real tool results ----------

def _answer(out):
    wf = out["waterfall"]
    return f"Sell at €{wf['price']:.2f} for a {wf['margin_pct']:.0%} margin. Net revenue is €{wf['net_revenue']:.2f}."


def test_guardrail_passes_true_answers_and_flags_invented_ones():
    rnd = random.Random(7)
    false_alarms = misses = trials = 0
    for _ in range(300):
        out = run(market=rnd.choice(EU), cogs_cny=rnd.uniform(8, 120), weight_kg=rnd.uniform(0.1, 2.5),
                  target_margin=rnd.choice([0.1, 0.15, 0.2, 0.25, 0.3]))
        if guardrail.check(_answer(out), [out], []):
            false_alarms += 1
        wf = out["waterfall"]
        invented = wf["price"] + rnd.choice([-7.31, 4.13, 9.77, -3.29])
        if invented <= 0:
            continue
        trials += 1
        if not guardrail.check(f"Sell at €{invented:.2f}.", [out], []):
            misses += 1
    assert false_alarms == 0
    assert misses <= trials * 0.02  # an invented price can coincide with another sourced figure


@pytest.mark.parametrize("claim", ["CE-certified", "BPA-free", "waterproof", "dishwasher-safe", "TÜV"])
def test_guardrail_flags_unsourced_certifications(claim):
    assert guardrail.check(f"This blender is {claim}.", [], ["I sell a blender"])
    assert not guardrail.check(f"This blender is {claim}.", [], [f"my product is {claim}"])


# ---------- 7. the platform a seller names in chat ----------

@pytest.mark.parametrize("text,want", [
    ("selling on Amazon.de", "amazon"), ("我在亚马逊卖", "amazon"), ("Temu seller here", "temu"),
    ("bol.com in NL", "bol"), ("on eBay", "ebay"), ("TikTok Shop FR", "tiktok"), ("Kaufland", "kaufland"),
    ("my own Shopify store", "own_site"), ("独立站", "own_site"),
    ("on Amazon and eBay", None),            # two platforms: ambiguous, so none
    ("a bottle for my hotel lobby", None), ("the otters like it", None), ("I sell bolts", None),
])
def test_platform_in_text(text, want):
    from landed.agent import platform_in
    assert platform_in(text) == want


# ---------- 8. how sellers actually phrase the cost ----------

@pytest.mark.parametrize("text", [
    "cost ¥38", "cost is 70", "my cost was 45", "it costs me 30 yuan", "costs 12", "unit cost: 25", "I pay 18 per piece",
    "38 RMB each", "38元", "进价30", "成本是70", "成本为 45", "采购价¥20", "拿货25块", "supplier quote is 40", "purchase price 33",
])
def test_cost_phrasings_are_recognised(text):
    from landed.agent import COST_RX
    assert COST_RX.search(text), text


@pytest.mark.parametrize("text", ["0.6 kg to Germany", "25% margin", "weighs 600g", "ship 2 units"])
def test_non_cost_numbers_are_not_costs(text):
    from landed.agent import COST_RX
    assert not COST_RX.search(text), text


# ---------- 9. guardrail: nouns and placeholders are not claims ----------

@pytest.mark.parametrize("text", [
    "Checklist: certification may be required for this product.",
    "Dichiarazione: la certificazione CE è richiesta.",
    "[Lavabile in lavastoviglie: da confermare]",
    "[Spülmaschinenfest: bitte bestätigen]",
    "Bring a declaration and a certificate of conformity.",
])
def test_guardrail_ignores_nouns_and_placeholders(text):
    assert not guardrail.check(text, [], [])


@pytest.mark.parametrize("text", ["Tazza certificata CE.", "Produit certifié.", "Taza certificada.", "Lavabile in lavastoviglie."])
def test_guardrail_still_flags_real_claims(text):
    assert guardrail.check(text, [], [])


# ---------- 10. US without a known HTS line: a labelled lower bound, never a refusal ----------

def test_us_indicative_price_is_a_labelled_lower_bound():
    out = run(market="US", cogs_cny=76, weight_kg=0.8, indicative=True)
    assert out["waterfall"]["price"] > 0
    assert any("not loaded" in w for w in out["warnings"])
    row = next(r for r in out["provenance"] if r["key"] == "us_base_duty_unknown")
    assert row["status"] == "unknown"
    with_code = run(market="US", cogs_cny=76, weight_kg=0.8, hs_code="6109.10")["waterfall"]["price"]
    assert with_code > out["waterfall"]["price"]          # a known 16.5% base duty costs more than the unknown (0) one


def test_us_unknown_code_still_abstains_unless_indicative():
    with pytest.raises(data.MissingRate):
        run(market="US", cogs_cny=40, weight_kg=0.6, hs_code="1234.56")
    assert run(market="US", cogs_cny=40, weight_kg=0.6, hs_code="1234.56", indicative=True)["waterfall"]["price"] > 0


@pytest.mark.parametrize("code,rate", [("3406.00", 0), ("6109.10", 0.165), ("9506.91", 0.046), ("8518.30", 0), ("9503.00", 0),
                                       ("3304.99", 0), ("7323.93", 0.02), ("3923.30", 0.03), ("8509.40", 0.042)])
def test_us_base_duties_are_verified_from_usitc(code, rate):
    r = data.rate(f"duty_{code}", "US")
    assert r.value == rate and r.status == "verified" and "hts.usitc.gov" in r.source_url


@pytest.mark.parametrize("text,code", [
    ("Scented candle 2-pack", "3406.00"), ("soy candles", "3406.00"), ("cotton t-shirt", "6109.10"), ("纯棉T恤", "6109.10"),
    ("yoga mat", "9506.91"), ("bluetooth earbuds", "8518.30"), ("wooden puzzle", "9503.00"), ("face serum", "3304.99"),
    ("polyester t-shirt", None), ("t-shirt", None), ("phone case", None), ("candle and a yoga mat", None),
])
def test_us_hs_guess(text, code):
    from landed import hs
    got = hs.suggest_us(text)
    assert (got[0] if got else None) == code


# ---------- 11. typos, plain wording, US range (from the naive-user test) ----------

@pytest.mark.parametrize("text,want", [
    ("chnage to germny pls", ["DE"]), ("frnace", ["FR"]), ("itally", ["IT"]), ("poalnd", ["PL"]), ("Spain", ["ES"]),
    ("austrlia", []), ("Iceland", []), ("England", []), ("norwy", []), ("a candle stand", []), ("I need lots of Spin", []),
])
def test_country_typos(text, want):
    from landed.agent import markets_in
    assert markets_in(text)[0] == want


def test_every_compliance_rule_has_plain_wording():
    from landed import compliance
    for r in data.compliance_rules()["rules"]:
        assert r.get("plain") and r.get("plain_zh"), r["id"]
    fl = compliance.flags("DE", {"electrical": True})["flags"]
    assert fl and all(f.get("plain") for f in fl)


def test_us_scenarios_bracket_the_floor():
    out = run(market="US", cogs_cny=76, weight_kg=0.8, hs_code="3406.00")
    s = out["us_scenarios"]
    assert out["waterfall"]["price"] < s["list_duty_7_5"] < s["list_duty_25"]
    assert "us_scenarios" not in run(market="DE", cogs_cny=76, weight_kg=0.8)
