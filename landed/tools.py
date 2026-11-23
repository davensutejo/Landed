"""Whitelisted tools exposed to the LLM. The dispatcher only runs these four."""
from __future__ import annotations

import json

from . import compliance, data, engine, hs

ATTR_PROPS = {
    "has_electric_motor": {"type": "boolean"},
    "motor_self_contained": {"type": "boolean"},
    "has_heating_element": {"type": "boolean"},
    "domestic_use": {"type": "boolean"},
    "is_accessory_only": {"type": "boolean"},
}

ASK_FIELDS = ["cogs_cny", "weight_kg", "market", "target_margin", "item_categories", "battery_builtin", "food_contact"]

# Inputs shared by every pricing tool.
_COST_PROPS = {
    "market": {"type": "string", "enum": sorted(engine.MARKETS)},
    "hs_code": {"type": "string", "description": "6-digit HS code like 8509.40, only if the seller gave or confirmed it. Required for US."},
    "cogs_cny": {"type": "number", "description": "Unit cost in CNY"},
    "weight_kg": {"type": "number"},
    "target_margin": {"type": "number", "description": "e.g. 0.25 for 25%"},
    "item_categories": {
        "type": "integer",
        "description": (
            "Number of DIFFERENT kinds of goods in one parcel (5 pairs of the same socks = 1; "
            "blender + spare cup = 2). Default 1 for a single product."
        ),
    },
    "fee_rate": {"type": "number", "description": "Seller's own platform fee rate, if given"},
    "freight_cny_per_kg": {"type": "number", "description": "Seller's own freight quote, if given"},
    "return_rate": {"type": "number", "description": "Seller's own return rate, if given"},
    "fx": {"type": "number", "description": "Seller's own FX rate (CNY per unit of destination currency), if given"},
    "ad_rate": {"type": "number", "description": "Seller's advertising spend as a share of total sales, e.g. 0.10, if given"},
    "payout_rate": {"type": "number", "description": "Seller's payout / currency conversion fee, e.g. 0.01, if given"},
    "fulfilment_fee": {"type": "number", "description": "Seller's fulfilment or pick-and-pack fee per order, in the destination currency, if given"},
    "dims_cm": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "description": "Box size in cm [length, width, height], only if the seller gave it"},
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "classify_hs",
            "description": (
                "Find HS code candidates for a product from Landed's verified category table (blenders, mixers, "
                "juicers and their parts). Call it ONLY when the code changes money or the seller asks for it: the "
                "market is the US, landed_cost abstained because the price is above EUR 150, or the seller asks which "
                "HS code to declare. Never call it just to price a German order. "
                "Pass attributes the seller stated, plus those the product type makes certain: a blender, mixer or "
                "juicer that blends has an electric motor driving the blade; a product that heats or cooks has a "
                "heating element; 'for home use' / 'household' means domestic_use. Never infer motor_self_contained "
                "or is_accessory_only unless the seller said it; omit anything uncertain. "
                "Returns candidates, a status (resolved | ambiguous | needs_confirmation | out_of_scope) "
                "and, when ambiguous, the single most informative question to ask the seller."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Product description in the seller's words"},
                    "in_category": {
                        "type": "boolean",
                        "description": (
                            "true only if the product is a blender, mixer, juicer, food processor or a cup/jar/blade "
                            "part for one. false for anything else (scooters, phones, clothing, other appliances)."
                        ),
                    },
                    "attributes": {"type": "object", "properties": ATTR_PROPS},
                },
                "required": ["description", "in_category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "landed_cost",
            "description": (
                "Deterministic landed cost, target price, 5,000-path Monte Carlo margin risk and stress table, for ANY "
                "product. For DE, hs_code is optional: below EUR 150 the duty is EUR 3 per tariff category whatever "
                "the code, so price as soon as cost, weight, market and margin are known. For the US, pass a confirmed "
                "hs_code (the duty depends on it). Never compute prices yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": _COST_PROPS,
                "required": ["market", "cogs_cny", "weight_kg"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "price_check",
            "description": (
                "The reverse question: the seller names a selling price (their listing, a competitor's, or what the "
                "product sells for on a platform) and asks if it makes money. Returns profit and margin at that price, "
                "the chance of hitting the target margin and of a loss (5,000-path Monte Carlo), and the most the "
                "seller can pay per unit (CNY) to keep the target margin or to break even. Needs the same four inputs "
                "as landed_cost plus list_price. Never compute these yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "list_price": {"type": "number", "description": "The selling price the seller stated, in the destination currency (VAT included for EU)"},
                    **_COST_PROPS,
                },
                "required": ["market", "cogs_cny", "weight_kg", "list_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_eu",
            "description": (
                "Same product in all 27 EU countries: the price that hits the target margin in each, and the profit "
                "per unit in each at one shared list price (the seller's stated price if given, otherwise the target "
                "price in `market`), ranked best first. Use when the seller asks which EU country to sell in or to "
                "compare EU countries. `market` is the seller's own EU country (Germany if they said only EU)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "list_price": {"type": "number", "description": "Optional: one selling price in EUR the seller stated"},
                    **_COST_PROPS,
                },
                "required": ["market", "cogs_cny", "weight_kg"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_seller",
            "description": (
                "Show the seller an interactive form for missing inputs (unit cost, weight, market, target margin, "
                "number of tariff categories, battery, food contact). Use this instead of asking for these in prose. "
                "Pass values you already know in `prefill`. After calling it, reply with one short sentence and stop."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fields": {"type": "array", "items": {"type": "string", "enum": ASK_FIELDS}},
                    "prefill": {"type": "object", "description": "Known values, e.g. {\"cogs_cny\": 38, \"market\": \"DE\"}"},
                    "note": {"type": "string", "description": "One short line explaining why these are needed"},
                },
                "required": ["fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compliance_flags",
            "description": (
                "Shipping, customs and product-safety requirements with sources, for any product. Call it whenever you "
                "give a price, passing only the attributes the seller stated or the product type makes certain."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "market": {"type": "string", "enum": sorted(engine.MARKETS)},
                    "battery_builtin": {"type": "boolean"},
                    "food_contact": {"type": "boolean"},
                    "has_electric_motor": {"type": "boolean"},
                    "electrical": {"type": "boolean", "description": "Any mains- or battery-powered electrical product"},
                    "cosmetic": {"type": "boolean", "description": "Skincare, makeup, haircare or other cosmetic product"},
                    "toy": {"type": "boolean", "description": "A toy or product designed for play by children"},
                    "textile": {"type": "boolean", "description": "Clothing, socks, fabric or other textile product"},
                    "item_categories": {"type": "integer"},
                },
                "required": ["market"],
            },
        },
    },
]


# rates.csv keys that default to 0 and are "not included" until the seller enters theirs
NOT_INCLUDED = {"ad_rate": "advertising", "payout_rate": "payout and currency conversion fee",
                "fulfilment_fee": "fulfilment fee per order"}


def _compact_cost(res: dict) -> dict:
    """Drop the histogram from what the LLM sees (the UI gets the full result)."""
    out = json.loads(json.dumps(res))
    mc = out["monte_carlo"]
    mc.pop("histogram", None)
    # Pre-formatted figures: the model copies these strings instead of converting
    # ratios itself (models truncate 0.2096 to "20.9%"; the engine rounds to 21.0%).
    pc = lambda v: f"{v * 100:.1f}%"  # noqa: E731
    cur = {"EUR": "€", "USD": "$"}.get(out["waterfall"]["currency"], "")
    lower_bound = out["inputs"]["market"] == "US" and not any("list duty" in (r.get("label") or "") for r in out.get("provenance", []))
    if lower_bound:
        out["price_is_lower_bound"] = True

    assumed = next((r for r in out.get("provenance", []) if "(assumed code)" in (r.get("label") or "")), None)
    base_unknown = any(r.get("key") == "us_base_duty_unknown" for r in out.get("provenance", []))

    def src(p: dict) -> str:
        if p.get("status") == "seller_input":
            return f"{p['label']}: seller's own figure"
        link = f"[{p['label']}]({p['source_url']})" if p.get("source_url") else p["label"]
        return f"{link} · {p.get('status')} · snapshot {p.get('snapshot_date')}"

    out["display"] = {
        "price_label": "Lower-bound price (older Section 301 list duty not loaded)" if lower_bound else ("Target price (US duty to confirm)" if out["inputs"]["market"] == "US" else "Target price"),
        "target_price": f"{cur}{out['waterfall']['price']:.2f}",
        "floor_price_95": f"{cur}{mc['floor_price_95']:.2f}",
        "p5_margin": pc(mc["p5_margin"]),
        "p50_margin": pc(mc["p50_margin"]),
        "p_below_target": pc(mc["p_below_target"]),
        "p_loss": pc(mc["p_loss"]),
        "target_margin": pc(out["inputs"]["target_margin"]),
        "waterfall": {s["label"]: f"{cur}{s['value']:.2f}" for s in out["waterfall"]["steps"]},
        "stress": {s["scenario"]: pc(s["margin_pct"]) for s in out["stress"]},
        "sources": [src(p) for p in out["provenance"]],
        "assumptions_to_replace": [
            f"{p['label']}: " + (f"{p['value'] * 100:g}%" if p.get("unit") == "ratio" else f"{p['value']:g} {p.get('unit') or ''}".strip())
            for p in out["provenance"]
            if p.get("status") == "assumption" and p.get("unit") != "param" and "volatility" not in p["label"].lower()
            and p.get("key") not in NOT_INCLUDED
        ] + [
            # Beta(alpha, 100 - alpha) prior: alpha is the mean return rate in percent
            f"Return rate: {p['value']:g}%" for p in out["provenance"] if p.get("key") == "return_alpha" and p.get("status") == "assumption"
        ],
        "multipack": [
            f"{o['units']}-pack of the same item: {cur}{o['pack_price']:.2f} ({cur}{o['price_per_unit']:.2f} per unit, "
            f"{cur}{o['saving_per_unit']:.2f} less per unit)"
            for o in (out.get("multipack_tip") or {}).get("options", [])
        ],
        "multipack_zh": [
            f"{o['units']} 件装（同款）：整包 {cur}{o['pack_price']:.2f}，折合每件 {cur}{o['price_per_unit']:.2f}，每件便宜 {cur}{o['saving_per_unit']:.2f}"
            for o in (out.get("multipack_tip") or {}).get("options", [])
        ],
        # costs left at 0 because the seller has not entered them: named, never quoted as "0%"
        "not_included": [
            NOT_INCLUDED[p["key"]] for p in out["provenance"]
            if p.get("key") in NOT_INCLUDED and p.get("status") == "assumption" and not p.get("value")
        ],
        "chargeable_weight": (
            f"{out['inputs']['chargeable_weight_kg']:g} kg (box size; actual {out['inputs']['weight_kg']:g} kg)"
            if out["inputs"].get("dims_cm") and out["inputs"]["chargeable_weight_kg"] > out["inputs"]["weight_kg"] else None
        ),
        "biggest_risk": next(
            (f"{s['scenario']}: margin {s['margin_pct'] * 100:.1f}%"
             for s in sorted(out["stress"], key=lambda s: s["margin_pct"])
             if any(k in s["scenario"] for k in ("CNY", "Return", "Freight", "Advertising"))),
            None,
        ),
        "profit_per_unit": next((f"{cur}{s['value']:.2f}" for s in out["waterfall"]["steps"] if s["key"] == "margin"), None),
        "us_range": (
            f"If an older Section 301 list duty applies on top: about {cur}{out['us_scenarios']['list_duty_7_5']:.2f} at 7.5%, "
            f"or {cur}{out['us_scenarios']['list_duty_25']:.2f} at 25%. Which one (if any) depends on the exact product line."
            if out.get("us_scenarios") else None
        ),
        "us_duty_note": (
            "The base duty of this product's HTS line is not loaded, so only the 12.5% China Section 301 duty is included; "
            "the real price is higher by that line's base duty. Ask a customs broker for the HTS line." if base_unknown else
            (f"Assumed HS {assumed['label'].split()[3]} from the product description, base duty {assumed['value'] * 100:g}% "
             "(USITC, verified); confirm the code with a customs broker." if assumed else None)
        ),
        "instruction": "Quote figures exactly as written in this display block. Use price_label as the headline label.",
    }
    return out


_SYM = {"EUR": "€", "USD": "$"}
_pc = lambda v: f"{v * 100:.1f}%"  # noqa: E731


def _signed(v: float, cur: str) -> str:
    return f"-{_SYM.get(cur, '')}{-v:.2f}" if v < 0 else f"{_SYM.get(cur, '')}{v:.2f}"


def _compact_check(r: dict) -> dict:
    """price_check result with pre-formatted strings the model copies (see _compact_cost)."""
    out = json.loads(json.dumps(r))
    mc, cur = out["monte_carlo"], out["currency"]
    tgt, brk = out["max_cogs_for_target"], out["max_cogs_break_even"]
    if brk is None:
        verdict = "loss_at_any_cost"
    elif out["margin_pct"] >= out["target_margin"]:
        verdict = "meets_target"
    elif out["profit_per_unit"] > 0:
        verdict = "profitable_below_target"
    else:
        verdict = "loss"
    out["display"] = {
        "list_price": _signed(out["list_price"], cur),
        "profit_per_unit": _signed(out["profit_per_unit"], cur),
        "margin": _pc(out["margin_pct"]),
        "target_margin": _pc(out["target_margin"]),
        "chance_hit_target": _pc(1 - mc["p_below_target"]),
        "chance_of_loss": "< 0.1%" if mc["p_loss"] < 0.0005 else _pc(mc["p_loss"]),
        "seller_unit_cost": f"¥{out['cogs_cny']:.2f}",
        "max_unit_cost_for_target": f"¥{tgt:.2f}" if tgt is not None else None,
        "max_unit_cost_break_even": f"¥{brk:.2f}" if brk is not None else None,
        "target_price": _signed(out["target_price"], cur),
        "verdict": verdict,
        "us_profit_is_upper_bound": out["market"] == "US" and any(
            "LOWER BOUND" in w or "base duty" in w for w in out.get("warnings", [])),
        "instruction": (
            "Quote figures exactly as written here. Lead with the verdict in plain words, then the most the seller can "
            "pay per unit, then target_price as the price that hits their margin. If us_profit_is_upper_bound, say the "
            "real profit is lower because part of the US duty is not loaded."
        ),
    }
    return out


def _compact_compare(r: dict) -> dict:
    """compare_eu result for the model: the best three, the worst, and the reference country (`market`), pre-formatted."""
    from .markets import EU_COUNTRIES

    rows = r["rows"]

    def line(row: dict) -> str:
        en, zh, _ = EU_COUNTRIES[row["market"]]
        if row["profit_at_list"] is None:
            return f"{en} ({zh}): above the EUR 150 flat-duty ceiling, not priced"
        return (f"{en} ({zh}): profit {_signed(row['profit_at_list'], 'EUR')} per unit ({_pc(row['margin_at_list'])}), "
                f"VAT {row['vat'] * 100:g}%, target price {_signed(row['target_price'], 'EUR') if row['target_price'] else 'n/a'}")

    own = next((x for x in rows if x["market"] == r["market"]), None)
    return {
        "list_price": f"€{r['list_price']:.2f}",
        "target_margin": _pc(r["target_margin"]),
        "countries": len(rows),
        "best": [line(x) for x in rows[:3]],
        "worst": line(rows[-1]),
        "reference_country": line(own) if own else None,  # `market`: the seller's country only if they said so
        # every country, ranked: a seller who names three countries gets each one's own figures, never a copy
        "all_countries_ranked": [f"{i}. {line(x)}" for i, x in enumerate(rows, 1)],
        "platform_not_sold_in": [EU_COUNTRIES[x["market"]][0] for x in rows if not x["platform_sold"]],
        "why_they_differ": "Only VAT (and the platform fee where the platform is not sold) differs; the EUR 3 duty and freight are EU-wide.",
        "instruction": (
            "Quote figures exactly as written. If the seller named specific countries, compare exactly those, each "
            "with its own line from all_countries_ranked (never assume two countries are the same). Otherwise say the "
            "best country and how much more it makes per unit than reference_country, and mention the worst. "
            "Point to the full 27-country table in the workspace."
        ),
    }


_PRICING_ARGS = {
    "market", "hs_code", "cogs_cny", "weight_kg", "target_margin", "item_categories", "fee_rate", "freight_cny_per_kg",
    "return_rate", "fx", "platform", "fee_category", "indicative", "hs_assumed",
    "ad_rate", "payout_rate", "fulfilment_fee", "dims_cm", "volumetric_divisor",
}


def dispatch(name: str, args: dict) -> tuple[dict, dict]:
    """Run a whitelisted tool. Returns (result_for_llm, result_for_ui)."""
    try:
        if name == "classify_hs":
            if args.get("in_category") is False:
                r = {
                    "status": "out_of_scope",
                    "candidates": [],
                    "message": (
                        "This product is outside Landed's HS table (blenders, mixers, juicers and their parts), so "
                        "Landed cannot suggest its HS code or its US duty. Germany can still be priced without the code "
                        "(EUR 3 per tariff category below EUR 150): offer that. For the code itself, recommend the "
                        "destination's tariff database or a customs broker."
                    ),
                }
                return r, r
            r = hs.classify(args.get("description", ""), args.get("attributes") or {})
            return r, r
        if name == "landed_cost":
            kwargs = {k: v for k, v in args.items() if k in _PRICING_ARGS and v is not None}
            res = engine.landed_cost(engine.Inputs(**kwargs))
            return _compact_cost(res), res
        if name in ("price_check", "compare_eu"):
            kwargs = {k: v for k, v in args.items() if k in _PRICING_ARGS and v is not None}
            lp = args.get("list_price")
            if name == "price_check":
                if lp is None:
                    raise engine.EngineError("price_check needs the selling price the seller stated (list_price)")
                res = engine.price_check(engine.Inputs(**kwargs), lp)
                return _compact_check(res), res
            res = engine.compare_eu(engine.Inputs(**kwargs), lp)
            return _compact_compare(res), res
        if name == "ask_seller":
            fields = [f for f in (args.get("fields") or []) if f in ASK_FIELDS]
            prefill = {k: v for k, v in (args.get("prefill") or {}).items() if k in ASK_FIELDS}
            r = {
                "status": "awaiting_seller",
                "fields": fields or ["cogs_cny", "weight_kg", "market", "target_margin"],
                "prefill": prefill,
                "note": str(args.get("note", ""))[:200],
                "instruction": "A form is now shown to the seller. Reply with one short sentence and stop; do not ask in prose.",
            }
            return r, r
        if name == "compliance_flags":
            market = args.get("market", "")
            r = compliance.flags(market, {k: v for k, v in args.items() if k != "market"})
            return r, r
        r = {"error": f"Unknown tool {name!r}. Only whitelisted tools may run."}
        return r, r
    except data.MissingRate as e:
        r = {"status": "abstain", "error": str(e), "instruction": "Say this figure is not in the verified tables. Do not estimate it."}
        return r, r
    except (engine.EngineError, TypeError, ValueError) as e:
        r = {"status": "error", "error": str(e)}
        return r, r
