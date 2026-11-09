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
                "properties": {
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
        "biggest_risk": next(
            (f"{s['scenario']}: margin {s['margin_pct'] * 100:.1f}%"
             for s in sorted(out["stress"], key=lambda s: s["margin_pct"])
             if any(k in s["scenario"] for k in ("CNY", "Return", "Freight"))),
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
            allowed = {
                "market", "hs_code", "cogs_cny", "weight_kg", "target_margin",
                "item_categories", "fee_rate", "freight_cny_per_kg", "return_rate", "fx", "platform", "fee_category", "indicative", "hs_assumed",
            }
            kwargs = {k: v for k, v in args.items() if k in allowed and v is not None}
            res = engine.landed_cost(engine.Inputs(**kwargs))
            return _compact_cost(res), res
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
