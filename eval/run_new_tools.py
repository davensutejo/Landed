"""Evaluation of the two new pricing tools (price_check, compare_eu) plus a landed_cost regression check.

Usage:
  .venv/Scripts/python -X utf8 -m eval.run_new_tools                 # run all categories
  .venv/Scripts/python -X utf8 -m eval.run_new_tools --cats A,C      # run a batch
  .venv/Scripts/python -X utf8 -m eval.run_new_tools --rescore eval/results/new-tools-X.json

Cases are a fixed literal list (CASES below), so every run uses the same messages. The agent is
called in-process through agent.run (the same path as the server), one run per case, sequentially.

Scoring is programmatic: no model grades another model.
- A (price_check expected): the last price_check call matches the seller's numbers (cost and weight within
  0.5%, margin exact, list_price exact); the answer contains the display profit_per_unit string and the
  display max_unit_cost_for_target string (or a no-cost phrase when it is null); no guardrail or error event.
- B (compare_eu expected): compare_eu was called; the answer names the country in rows[0] (best) and does
  not name a different country in a sentence that calls something best; no guardrail or error event.
- C (must not guess): no successful pricing result (landed_cost / price_check / compare_eu) has a figure
  quoted in the final answer. For the above-EUR-150 cases, the answer must not contain any money or percent
  figure that the seller did not write (150 and 3 are excluded: they are the ceiling and the duty).
- D (regression): landed_cost was called with the seller's numbers and produced a result; neither
  price_check nor compare_eu was called.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from landed import agent  # noqa: E402
from landed.markets import EU_COUNTRIES  # noqa: E402
from landed.tools import _compact_check, _compact_compare, _compact_cost  # noqa: E402

# ------------------------------------------------------------------ cases
# truth keys: m market, c cost CNY, w weight kg, g target margin, p selling price (list_price)
def A(cid, turns, m, c, w, g, p):
    return {"id": cid, "cat": "A", "turns": turns, "truth": {"m": m, "c": c, "w": w, "g": g, "p": p}}


def B(cid, turns, c, w, g, p=None, m=None):
    return {"id": cid, "cat": "B", "turns": turns, "truth": {"c": c, "w": w, "g": g, "p": p, "m": m}}


def C(cid, turns, gt150=False):
    return {"id": cid, "cat": "C", "turns": turns, "truth": {"gt150": gt150}}


def D(cid, turns, m, c, w, g):
    return {"id": cid, "cat": "D", "turns": turns, "truth": {"m": m, "c": c, "w": w, "g": g}}


CASES = [
    # A. price_check expected
    A("A01", ["我的成本是38元，重量300g，卖到德国，目标利润率25%。我在亚马逊上卖29.99欧，能赚钱吗？最多能给工厂多少钱？"], "DE", 38, 0.3, 0.25, 29.99),
    A("A02", ["silicone phone case cost 12 RMB, 0.08kg, Germany, I want 30% margin. Listed at €19.90 on Amazon DE. Does it make money?"], "DE", 12, 0.08, 0.30, 19.90),
    A("A03", ["拿货价45块，净重1.2kg，发法国，利润率20%，法国站售价59,90€，还能赚吗"], "FR", 45, 1.2, 0.20, 59.90),
    A("A04", ["cotton tee, cost ¥32, 250 g, Italy, margin 25%, selling at 24.99 euro on eBay, can I make money?"], "IT", 32, 0.25, 0.25, 24.99),
    A("A05", ["卖家你好，成本价 88 元，重量 1.5 公斤，西班牙，目标毛利率 35%，我们在 Temu 上定价 49.9 欧，算一下利润"], "ES", 88, 1.5, 0.35, 49.9),
    A("A06", ["Desk lamp: my cost is 65 CNY, 0.9 kg, Netherlands, 30% margin, I plan to sell at €34.50 on Bol. Profitable?"], "NL", 65, 0.9, 0.30, 34.50),
    A("A07", ["成本 22 元 重 180克 卖到奥地利 利润率 20% 现在标价 19.99€ 能不能做"], "AT", 22, 0.18, 0.20, 19.99),
    A("A08", ["Hair dryer cost 110 yuan, weight 1.1 kg, sell in Germany for €69,99 target 25%, what's the max I can pay per unit?"], "DE", 110, 1.1, 0.25, 69.99),
    A("A09", ["进价 15块，500g，法国，利润率 30%，亚马逊卖 25.99 欧，还剩多少利润？"], "FR", 15, 0.5, 0.30, 25.99),
    A("A10", ["My Kaufland listing is €42.00. Unit cost is 58 RMB, shipping weight 2.3kg, going to Belgium. Want 25% margin. Do I profit?"], "BE", 58, 2.3, 0.25, 42.00),
    A("A11", ["我们卖 Temu，售价 12.9 欧，成本 9 元，重 60g，目标利润 20%，德国。这个价格能做吗"], "DE", 9, 0.06, 0.20, 12.9),
    A("A12", ["cost 140 RMB, 3kg, Poland, 28% margin, selling at €139.00 on Allegro. profit?"], "PL", 140, 3, 0.28, 139.00),
    A("A13", ["USD market: cost 40 yuan, 0.5 kg, US, target 25%, listing at $59.99 on Amazon US, does it make money"], "US", 40, 0.5, 0.25, 59.99),
    A("A14", ["same product sells at $49.95 on eBay US, my cost 40 元, weight 500g, want 25% margin. Still profitable?"], "US", 40, 0.5, 0.25, 49.95),
    A("A15", ["我的成本 65 元，1.4kg，发美国，目标利润率 20%，亚马逊标价 $89.00，这价格能赚钱吗"], "US", 65, 1.4, 0.20, 89.00),
    A("A16", ["Bike bell: 8 RMB cost, 45 grams, Sweden, 20% margin, sell at €11.90 on Otto. profit?"], "SE", 8, 0.045, 0.20, 11.90),
    A("A17", ["成本 27.5 元 重 0.4kg 卖去意大利 25% 利润率 标价 39.90欧"], "IT", 27.5, 0.4, 0.25, 39.90),
    A("A18", ["Two-pack socks cost ¥18, weight 0.15 kg, Germany, margin 30%. My listing is €14.90, does it make money? Max I can pay?"], "DE", 18, 0.15, 0.30, 14.90),
    A("A19", ["我想卖一款蓝牙音箱，到德国，利润率 25%，进价 120 元，重 1.8 公斤", "亚马逊标价 99.99 欧，还能赚吗？"], "DE", 120, 1.8, 0.25, 99.99),
    A("A20", ["cost is 33 RMB, 0.7kg, France, 30% margin", "I'm listing it at 44,90 € on Amazon FR, makes money?"], "FR", 33, 0.7, 0.30, 44.90),
    A("A21", ["Plant pot. 进价 6 块，重量 800 克，西班牙，目标利润 25%。竞争对手卖 17.99 欧，我能赚吗？"], "ES", 6, 0.8, 0.25, 17.99),
    A("A22", ["我这款充电宝成本 75 元，1.1kg，德国，利润率 22%，TikTok 售价 49.99 欧。赚不赚钱"], "DE", 75, 1.1, 0.22, 49.99),
    A("A23", ["cost 19 cny weight 0.35kg ireland 25% margin, competitor sells at 29.99 eur, what's my max unit cost?"], "IE", 19, 0.35, 0.25, 29.99),
    A("A24", ["Yoga mat cost 52 RMB, 1.6kg, Austria, margin 28%, listed at 46,00 € on Amazon. Profitable?"], "AT", 52, 1.6, 0.28, 46.00),
    A("A25", ["Bluetooth earbuds cost 58元 weight 120g Germany 35% margin they sell at 79€ on Amazon. Is it worth it?"], "DE", 58, 0.12, 0.35, 79),
    # B. compare_eu expected
    B("B01", ["Which EU country should I sell in? cost 38 RMB, 0.3kg, my home is Germany, 25% margin"], 38, 0.3, 0.25, m="DE"),
    B("B02", ["compare France vs Germany vs Italy for my kettle: cost 85 yuan, 1.2 kg, 25% target margin"], 85, 1.2, 0.25),
    B("B03", ["我该在哪个欧盟国家卖？成本 22 元，0.25 公斤，利润率 30%"], 22, 0.25, 0.30),
    B("B04", ["哪个欧盟国家最赚钱？进价 60 块，重 800g，目标 25%，我在西班牙"], 60, 0.8, 0.25, m="ES"),
    B("B05", ["Which EU country is cheapest to sell in for a yoga mat? cost 52 RMB 1.5kg 25%"], 52, 1.5, 0.25),
    B("B06", ["Best EU market for my LED lamp? 成本 35 元 重 0.45 kg 利润率 25%。我现在在意大利"], 35, 0.45, 0.25, m="IT"),
    B("B07", ["compare EU countries please: cost 19 yuan, 300 grams, target 20%, list price €24.90"], 19, 0.3, 0.20, p=24.90),
    B("B08", ["欧盟哪个国家卖最划算？成本 48 元，1.1kg，目标利润率 25%，法国卖 39.90 欧"], 48, 1.1, 0.25, p=39.90),
    B("B09", ["Where should I sell EU-wide? cost is 60 RMB, 0.9kg, 30% margin, I'm based in Netherlands"], 60, 0.9, 0.30, m="NL"),
    B("B10", ["I ship from Poland. Which EU country pays best? cost 14 yuan 0.2kg 25% margin"], 14, 0.2, 0.25, m="PL"),
    B("B11", ["for a steel water bottle, cost 27 RMB, 0.55kg, 25% target, which EU country gives highest profit per unit?"], 27, 0.55, 0.25),
    B("B12", ["欧洲哪里卖最赚？成本 26元，420克，利润率 25%"], 26, 0.42, 0.25),
    B("B13", ["Compare Sweden, Denmark and Finland for a wooden toy: cost 30 RMB, 0.4kg, 25% margin."], 30, 0.4, 0.25),
    B("B14", ["我想比较一下德国和荷兰，哪个赚得多？成本 41 元，重 0.7kg，利润率 25%"], 41, 0.7, 0.25),
    B("B15", ["Which EU country is best for my ceramic mug? I am in Italy, cost 16 RMB, weight 0.35kg, want 30% margin, selling price 14,90 €"], 16, 0.35, 0.30, p=14.90, m="IT"),
    # C. must not guess
    C("C01", ["成本 40 元 重 0.5kg 德国 卖 29.99 欧能赚钱吗"]),
    C("C02", ["I sell in Germany, weight 0.4 kg, selling price €35, 25% margin. How much can I pay for the unit?"]),
    C("C03", ["卖到英国，成本 30 元，0.5kg，利润率 25%，售价 £24.99，能赚钱吗"]),
    C("C04", ["日本市场，进价 45 块，重 400g，目标利润 25%，标价 ¥3980 能不能赚？"]),
    C("C05", ["cost 25 RMB 0.3kg Germany, selling at €189 on Amazon, 25% margin. profit?"], gt150=True),
    C("C06", ["Can you tell me if this makes money? I'm selling at 29.99 euro"]),
    C("C07", ["我想知道这个价格合不合适：成本 22 元，0.25 公斤，德国，售价 19.9 欧"]),
    C("C08", ["Does this make money at my selling price? cost 30 RMB, 0.4kg, Germany, 25% margin"]),
    C("C09", ["卖到法国，成本 60 元，1.2kg，利润率 30%，售价 ¥350，能赚吗"], gt150=True),
    C("C10", ["Australia market, cost 20 RMB, 0.3kg, 25%, sell at AUD 39.99 → profit?"]),
    C("C11", ["卖加拿大，进价 33 元，0.6 kg，利润率 25%，标价 C$44.99，能赚钱吗"]),
    C("C12", ["Sell in Germany: cost 50 RMB, 1kg, 25%. I'm selling at €160 on Amazon. What's the profit?"], gt150=True),
    # D. regression: plain "what should I charge", no selling price
    D("D01", ["成本 38 元，重 0.3 公斤，卖到德国，利润率 25%，我应该定价多少？"], "DE", 38, 0.3, 0.25),
    D("D02", ["What should I charge for a phone case? cost 12 RMB, 80 g, Germany, 30% margin"], "DE", 12, 0.08, 0.30),
    D("D03", ["帮我定个价。进价 25 块，500 克，法国，目标利润 20%"], "FR", 25, 0.5, 0.20),
    D("D04", ["Cost 60 yuan, 1.1kg, Italy, 25% margin. What price should I list at?"], "IT", 60, 1.1, 0.25),
    D("D05", ["我的成本 15 元，0.2kg，西班牙，利润率 30%，建议售价是多少"], "ES", 15, 0.2, 0.30),
    D("D06", ["what's the right price for my yoga mat? cost 52 RMB, 1.6 kg, Netherlands, 25% target margin"], "NL", 52, 1.6, 0.25),
    D("D07", ["成本 90 元，2kg，美国，利润率 25%，该卖多少钱？"], "US", 90, 2, 0.25),
    D("D08", ["pricing help: cost 33 RMB, 0.7kg, Belgium, margin 30%, what should my price be?"], "BE", 33, 0.7, 0.30),
]

# ------------------------------------------------------------------ helpers

NO_COST = re.compile(
    r"没有|无法|不可能|都不赚|任何成本|任何进价|no unit cost|no cost|any cost|at any|cannot|can't|not possible|no price", re.I)
SUP = re.compile(r"best|cheapest|most profitable|highest|\btop\b|more profit|最好|最划算|最赚|最多|最高|最优|第一|首选|推荐|最值得|利润最", re.I)
NEGATED = re.compile(r"not|n't|不是|不算|并非|没有", re.I)  # "X is not the top" names X as NOT best
WORST = re.compile(r"worst|lowest|least|最差|最低|最少|垫底|最末|最不", re.I)
SELLER_NUM = re.compile(r"\d+(?:[.,]\d+)?")
MONEY = re.compile(r"(?:€|EUR|\$|USD|¥|￥|元|欧|块|%|％)\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(?:%|％|€|EUR|元|欧|块|USD|\$)")


def calls(evs, name):
    return [e for e in evs if e.get("type") == "tool_call" and e.get("name") == name]


def results(evs, name):
    return [e.get("result") for e in evs if e.get("type") == "tool_result" and e.get("name") == name]


def seller_numbers(turns):
    nums = set()
    for t in turns:
        for x in SELLER_NUM.findall(t):
            nums.add(round(float(x.replace(",", ".")), 2))
    return nums


def num_tokens(text):
    return {round(float(x), 2) for x in re.findall(r"\d+(?:\.\d+)?", text.replace(",", "."))}


def display_strings(name, r):
    """The display values the LLM was told to quote, computed from the UI result the way tools.py does."""
    if name == "price_check":
        return [v for v in _compact_check(r)["display"].values() if isinstance(v, str)]
    if name == "landed_cost":
        return [v for v in _compact_cost(r)["display"].values() if isinstance(v, str)]
    if name == "compare_eu":
        c = _compact_compare(r)
        return [x for x in [*c["best"], c["worst"], c["reference_country"]] if isinstance(x, str)]
    return []


def successful_pricing(evs):
    out = []
    for name, key in (("landed_cost", "waterfall"), ("price_check", "max_cogs_for_target"), ("compare_eu", "rows")):
        for r in results(evs, name):
            if isinstance(r, dict) and key in r:
                out.append((name, r))
    return out


def final_answer(evs):
    return next((e["text"] for e in reversed(evs) if e.get("type") == "answer"), "")


def score_A(case, evs, answer):
    t = case["truth"]
    notes = []
    pcs = calls(evs, "price_check")
    if not pcs:
        return False, [f"no price_check call (tools: {[e['name'] for e in evs if e.get('type') == 'tool_call']})"]
    a = pcs[-1]["args"]
    if a.get("market") != t["m"]:
        notes.append(f"market {a.get('market')} != {t['m']}")
    for k, tv in (("cogs_cny", t["c"]), ("weight_kg", t["w"])):
        v = a.get(k)
        if not isinstance(v, (int, float)) or abs(v - tv) > 0.005 * tv:
            notes.append(f"{k} {v} != {tv}")
    if a.get("target_margin") is None or abs(a["target_margin"] - t["g"]) > 1e-6:
        notes.append(f"target_margin {a.get('target_margin')} != {t['g']}")
    if a.get("list_price") is None or abs(a["list_price"] - t["p"]) > 0.005:
        notes.append(f"list_price {a.get('list_price')} != {t['p']}")
    res = results(evs, "price_check")
    r = res[-1] if res else None
    if not isinstance(r, dict) or "max_cogs_for_target" not in r:
        notes.append(f"price_check did not return a price: {str(r)[:120]}")
        return False, notes
    d = _compact_check(r)["display"]
    if d["profit_per_unit"] not in answer:
        notes.append(f"profit_per_unit '{d['profit_per_unit']}' not in answer")
    if d["max_unit_cost_for_target"] is not None:
        if d["max_unit_cost_for_target"] not in answer:
            notes.append(f"max_unit_cost_for_target '{d['max_unit_cost_for_target']}' not in answer")
    elif not NO_COST.search(answer):
        notes.append("max_unit_cost_for_target is null but answer does not say no cost works")
    if any(e.get("type") == "guardrail" for e in evs):
        notes.append("guardrail event")
    if any(e.get("type") == "error" for e in evs):
        notes.append("error event")
    return not notes, notes


EN_WORD = {}


def name_in(sentence, code):
    en, zh, _ = EU_COUNTRIES[code]
    return bool(re.search(rf"\b{re.escape(en)}\b", sentence, re.I)) or zh in sentence


def score_B(case, evs, answer):
    t = case["truth"]
    notes = []
    cs = calls(evs, "compare_eu")
    if not cs:
        return False, [f"no compare_eu call (tools: {[e['name'] for e in evs if e.get('type') == 'tool_call']})"]
    a = cs[-1]["args"]
    if t.get("p") is not None and (a.get("list_price") is None or abs(a["list_price"] - t["p"]) > 0.005):
        notes.append(f"list_price {a.get('list_price')} != stated {t['p']}")
    res = results(evs, "compare_eu")
    r = res[-1] if res else None
    if not isinstance(r, dict) or "rows" not in r:
        notes.append(f"compare_eu returned no rows: {str(r)[:120]}")
        return False, notes
    best = r["rows"][0]["market"]
    best_en, best_zh, _ = EU_COUNTRIES[best]
    # "Compare France vs Germany vs Italy" asks for the best of THOSE: the top-ranked named country is a right answer too.
    seller = " ".join(case["turns"])
    named = [x["market"] for x in r["rows"] if name_in(seller, x["market"])]  # rows are ranked, so named[0] is best of them
    allowed = {best} | ({named[0]} if len(named) >= 2 else set())
    if not any(name_in(answer, c) for c in allowed):
        notes.append(f"best country {best_en} not named in answer")
    for s in re.split(r"[.!?。！？\n;；]", answer):
        if not SUP.search(s) or WORST.search(s):
            continue
        if any(name_in(s, c) for c in allowed):
            continue
        others = [c for c in EU_COUNTRIES if c not in allowed and name_in(s, c)]
        if others:
            notes.append(f"sentence calls another country best: {s.strip()[:80]} (best is {best_en})")
    notes += misattributed_figures(answer, r)
    if any(e.get("type") == "guardrail" for e in evs):
        notes.append("guardrail event")
    if any(e.get("type") == "error" for e in evs):
        notes.append("error event")
    return not notes, notes


def misattributed_figures(answer: str, r: dict) -> list[str]:
    """Every €/% figure on a line that names exactly one country must be that country's own figure.

    Catches the B13 failure: the model gave Finland Sweden's profit and VAT. The guardrail cannot see this,
    because the numbers do appear in the tool output, just for another country."""
    rows = {x["market"]: x for x in r["rows"]}
    shared = {round(r["list_price"], 2), 3.0, 150.0, round(r["target_margin"] * 100, 1)}
    notes = []
    for line in re.split(r"[\n。]", answer):
        named = [c for c in rows if name_in(line, c)]
        if len(named) != 1:
            continue
        x = rows[named[0]]
        own = set(shared)
        for v in (x["profit_at_list"], x["target_price"]):
            if v is not None:
                own.add(round(v, 2))
        for v in (x["margin_at_list"], x["vat"]):
            if v is not None:
                own.add(round(v * 100, 1))
        for m in MONEY.finditer(line):
            raw = (m.group(1) or m.group(2)).replace(",", ".")
            v = float(raw)
            if not any(abs(v - o) < 0.051 if "%" in m.group(0) or "％" in m.group(0) else abs(v - o) < 0.006 for o in own):
                notes.append(f"{EU_COUNTRIES[named[0]][0]} given figure {m.group(0).strip()} that is not its own")
    return notes


def score_C(case, evs, answer, seller_text):
    notes = []
    # Spec: a price_check / compare_eu result must not be quoted. A landed_cost target price is not in that rule.
    produced = [(n, r) for n, r in successful_pricing(evs) if n in ("price_check", "compare_eu")]
    seller_nums = seller_numbers([seller_text])
    for name, r in produced:
        for s in display_strings(name, r):
            for tok in re.findall(r"\d+\.\d+|\d{3,}", s):
                v = round(float(tok), 2)
                if v in seller_nums or v in (150.0, 3.0):
                    continue
                if str(tok) in answer or f"{v:.2f}" in answer:
                    notes.append(f"quotes {name} figure {tok} from '{s}'")
                    break
    if case["truth"]["gt150"]:
        for m in MONEY.finditer(answer):
            raw = next(g for g in m.groups() if g)
            v = round(float(raw.replace(",", ".")), 2)
            if v in seller_nums or v in (150.0, 3.0):
                continue
            notes.append(f"money/percent figure {raw} above EUR 150 (not the seller's)")
            break
    if produced and not notes:
        notes.append(f"(info) a pricing result was produced: {[n for n, _ in produced]}; no figure quoted")
    fails = [n for n in notes if not n.startswith("(info)")]
    return not fails, notes


def score_D(case, evs, answer):
    t = case["truth"]
    notes = []
    if calls(evs, "price_check") or calls(evs, "compare_eu"):
        notes.append("price_check or compare_eu called on a no-selling-price request")
    ls = calls(evs, "landed_cost")
    if not ls:
        notes.append(f"no landed_cost call (tools: {[e['name'] for e in evs if e.get('type') == 'tool_call']})")
        return False, notes
    a = ls[-1]["args"]
    if a.get("market") != t["m"]:
        notes.append(f"market {a.get('market')} != {t['m']}")
    if a.get("cogs_cny") is None or abs(a["cogs_cny"] - t["c"]) > 0.005 * t["c"]:
        notes.append(f"cogs {a.get('cogs_cny')} != {t['c']}")
    if a.get("weight_kg") is None or abs(a["weight_kg"] - t["w"]) > 0.005 * t["w"]:
        notes.append(f"weight {a.get('weight_kg')} != {t['w']}")
    if a.get("target_margin") is None or abs(a["target_margin"] - t["g"]) > 1e-6:
        notes.append(f"margin {a.get('target_margin')} != {t['g']}")
    if not any(isinstance(r, dict) and "waterfall" in r for r in results(evs, "landed_cost")):
        notes.append("landed_cost produced no price (blocked by guard?)")
    return not notes, notes


def score(rec):
    case_id = rec["id"]
    case = next(c for c in CASES if c["id"] == case_id)
    evs = rec["all_events"][-1] if rec.get("all_events") else []
    answer = final_answer(evs)
    if rec.get("error"):
        return False, [f"run error: {rec['error']}"]
    if case["cat"] == "A":
        ok, notes = score_A(case, evs, answer)
    elif case["cat"] == "B":
        ok, notes = score_B(case, evs, answer)
    elif case["cat"] == "C":
        ok, notes = score_C(case, evs, answer, " ".join(case["turns"]))
    else:
        ok, notes = score_D(case, evs, answer)
    return ok, notes


def run_case(case):
    rec = {"id": case["id"], "cat": case["cat"], "turns": case["turns"], "truth": case["truth"],
           "all_events": [], "error": None, "attempts": 0}
    t0 = time.time()
    for attempt in (1, 2):
        rec["attempts"] = attempt
        try:
            history, all_events = [], []
            for msg in case["turns"]:
                history.append({"role": "user", "content": msg})
                evs = list(agent.run(history))
                all_events.append(evs)
                text = next((e["text"] for e in evs if e["type"] == "answer"), "") or "(no answer)"
                history.append({"role": "assistant", "content": text})
            rec["all_events"] = all_events
            rec["error"] = None
            break
        except Exception as e:  # noqa: BLE001 - recorded, one retry
            rec["error"] = f"{type(e).__name__}: {e}"
            if attempt == 1:
                time.sleep(3)
    rec["secs"] = round(time.time() - t0, 2)
    rec["answer"] = final_answer(rec["all_events"][-1]) if rec["all_events"] else ""
    rec["pass"], rec["notes"] = score(rec)
    return rec


def summary(recs):
    lines = []
    total_pass = 0
    for cat in "ABCD":
        rs = [r for r in recs if r["cat"] == cat]
        if not rs:
            continue
        p = sum(r["pass"] for r in rs)
        total_pass += p
        lines.append(f"{cat}: {p}/{len(rs)} ({100 * p / len(rs):.0f}%)")
    secs = [r["secs"] for r in recs if r.get("secs") is not None]
    lines.append(f"TOTAL: {total_pass}/{len(recs)} ({100 * total_pass / max(1, len(recs)):.0f}%)")
    if secs:
        lines.append(f"mean latency: {sum(secs) / len(secs):.1f}s over {len(secs)} cases")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cats", default="A,B,C,D")
    ap.add_argument("--rescore", nargs="+", help="re-score saved result files without calling the LLM")
    a = ap.parse_args()
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    if a.rescore:
        recs = []
        for f in a.rescore:
            recs += json.loads(Path(f).read_text(encoding="utf-8"))["records"]
        for r in recs:
            r["pass"], r["notes"] = score(r)
        out = out_dir / f"new-tools-rescored-{stamp}.json"
        out.write_text(json.dumps({"records": recs}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        for r in recs:
            print(json.dumps({"id": r["id"], "pass": r["pass"], "notes": r["notes"][:2]}, ensure_ascii=False))
        print("\n" + summary(recs))
        print(f"saved {out}")
        return

    cats = set(a.cats.split(","))
    recs = []
    out = out_dir / f"new-tools-{stamp}.json"
    model = __import__("os").environ.get("LLM_MODEL")
    for case in [c for c in CASES if c["cat"] in cats]:
        rec = run_case(case)
        recs.append(rec)
        print(json.dumps({"id": rec["id"], "cat": rec["cat"], "pass": rec["pass"], "secs": rec["secs"],
                          "error": rec["error"], "notes": rec["notes"][:2]}, ensure_ascii=False), flush=True)
        # saved after every case, so a stopped run keeps its finished cases
        out.write_text(json.dumps({"model": model, "records": recs}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        time.sleep(0.5)
    print("\nSUMMARY\n" + summary(recs))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
