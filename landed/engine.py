"""Deterministic landed-cost engine + vectorised Monte Carlo.

No LLM touches this module. Mirrors src/lib/engine.js (the in-browser card).

Notation (per unit, destination currency):
  P  gross list price (VAT-inclusive for EU B2C; excl. sales tax for US)
  N  net revenue = P / (1 + vat)
  G  goods cost  = (COGS + freight) / fx + duty
  R  returns     = r * G          (returned unit written off)
  F  platform fee = fee * P
  profit = N - F - G(1 + r);  margin = profit / N

profit is linear in P, so the price that hits target margin m is closed form:
  P* = G(1 + r) / (1/(1+vat) - fee - m/(1+vat))
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from . import data, platforms
from .markets import EU_COUNTRIES, name as market_name

MARKETS = {
    # market -> region, currency, fx key, VAT key (None = sales tax added at checkout)
    **{c: {"region": "EU", "currency": "EUR", "fx": "fx_cny_per_eur", "vat": ("vat_standard", c)} for c in EU_COUNTRIES},
    "US": {"region": "US", "currency": "USD", "fx": "fx_cny_per_usd", "vat": None},
}


class EngineError(ValueError):
    pass


@dataclass
class Inputs:
    market: str
    cogs_cny: float
    weight_kg: float
    # Optional for EU countries: under the EU flat regime (<= EUR 150) the duty is EUR 3 per tariff
    # category whatever the code. Required for the US and for EU consignments above EUR 150.
    hs_code: str | None = None
    target_margin: float = 0.25
    item_categories: int = 1
    # optional seller overrides (replace demo assumptions)
    fee_rate: float | None = None
    platform: str | None = None      # sourced default fee for this platform when fee_rate is not given
    fee_category: str | None = None  # the seller's category, for platforms that price by category
    freight_cny_per_kg: float | None = None
    return_rate: float | None = None
    fx: float | None = None
    paths: int = 5000
    seed: int = 20261108
    # US only. With no usable HS code, price anyway: the 12.5% China Section 301 duty is included, the base
    # duty of the unknown HTS line is not, and the result is labelled a lower bound.
    indicative: bool = False
    hs_assumed: bool = False  # the code came from the product description, not from the seller


@dataclass
class Params:
    currency: str
    vat: float
    fee: float
    fx_mean: float
    fx_sd: float
    freight_cny: float
    cogs_cny: float
    ret_alpha: float
    ret_beta: float
    duty_mode: str  # "eu_flat" | "ad_valorem"
    duty_flat: float = 0.0
    duty_rate: float = 0.0
    duty_rate_known: bool = False
    us_list_known: bool = False
    fee_fixed: float = 0.0  # per-order platform fee in the destination currency
    fee_high: float | None = None
    target: float = 0.25
    flat_threshold: float = 150.0
    provenance: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _prov(rows: list[dict], r: data.Rate, label: str, override: bool = False) -> None:
    p = r.provenance()
    p["label"] = label
    if override:
        p["status"] = "seller_input"
        p["source_url"] = None
    rows.append(p)


def build_params(x: Inputs) -> Params:
    if x.market not in MARKETS:
        raise EngineError(f"Market {x.market!r} not supported. Supported: {sorted(MARKETS)}")
    nums = {"target_margin": x.target_margin, "cogs_cny": x.cogs_cny, "weight_kg": x.weight_kg}
    nums.update({k: v for k, v in (("fee_rate", x.fee_rate), ("return_rate", x.return_rate), ("fx", x.fx),
                                   ("freight_cny_per_kg", x.freight_cny_per_kg)) if v is not None})
    for name, v in nums.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise EngineError(f"{name} must be a finite number")
    if not 0 < x.target_margin < 0.8:
        raise EngineError("target_margin must be between 0 and 0.8")
    if x.cogs_cny <= 0 or x.weight_kg <= 0:
        raise EngineError("cogs_cny and weight_kg must be positive")
    if x.fee_rate is not None and not 0 <= x.fee_rate < 1:
        raise EngineError("fee_rate must be between 0 and 1 (e.g. 0.15 for 15%)")
    if x.return_rate is not None and not 0 <= x.return_rate < 1:
        raise EngineError("return_rate must be between 0 and 1 (e.g. 0.08 for 8%)")
    if x.fx is not None and x.fx <= 0:
        raise EngineError("fx must be positive (CNY per unit of the destination currency)")
    if x.freight_cny_per_kg is not None and x.freight_cny_per_kg < 0:
        raise EngineError("freight_cny_per_kg cannot be negative")
    if not isinstance(x.item_categories, int) or not 1 <= x.item_categories <= 50:
        raise EngineError("item_categories must be a whole number from 1 to 50")
    m = MARKETS[x.market]
    region = m["region"]
    prov: list[dict] = []
    warnings: list[str] = []

    fx_r = data.rate(m["fx"], region)
    _prov(prov, fx_r, f"FX CNY per {m['currency']}", override=x.fx is not None)
    fx_sd = data.rate("fx_horizon_sd", "ALL")
    _prov(prov, fx_sd, "FX volatility (horizon)")

    fee_r = data.rate("platform_fee", "ALL")
    _prov(prov, fee_r, "Platform fee", override=x.fee_rate is not None)
    fee_value, fee_fixed, fee_high = fee_r.value, 0.0, None
    if x.fee_rate is None and x.platform and x.platform != "other":
        name = platforms.table()["platforms"].get(platforms.LEGACY.get(x.platform, x.platform), {}).get("name", x.platform)
        sold_here = x.market in platforms.available_markets(x.platform)
        pf = platforms.fee(x.platform, x.market, x.fee_category) if sold_here else None
        if not sold_here:
            warnings.append(
                f"{name} is not sold in {market_name(x.market)}, so its fee is not used and the generic "
                f"{fee_r.value:.0%} placeholder applies. Pick a platform sold there or enter your own fee."
            )
        elif pf:
            prov.pop()  # replace the generic row with the platform's own
            _prov(prov, data.Rate("platform_fee", x.market, pf["value"], "ratio", pf["status"], pf["source_url"],
                                  pf["snapshot_date"], pf["note"]), f"Platform fee ({pf['name']})")
            fee_value, fee_fixed, fee_high = pf["value"], pf["fixed"], pf["high"]
            if pf["fixed"]:
                _prov(prov, data.Rate("platform_fee_fixed", x.market, pf["fixed"], m["currency"], pf["status"],
                                      pf["source_url"], pf["snapshot_date"], "Fixed fee per order"),
                      f"Platform fixed fee per order ({pf['name']})")
        elif x.market in platforms.available_markets(x.platform):
            warnings.append(
                f"No sourced fee for {name} in this market, so the generic {fee_r.value:.0%} placeholder is used. "
                "Enter the fee from your seller panel."
            )
    fr_r = data.rate("freight_cny_per_kg", "ALL")
    _prov(prov, fr_r, "Freight CNY/kg", override=x.freight_cny_per_kg is not None)
    ra = data.rate("return_alpha", "ALL")
    rb = data.rate("return_beta", "ALL")
    _prov(prov, ra, "Return-rate prior", override=x.return_rate is not None)

    if x.return_rate is not None:
        # keep prior strength (100) but move the mean to the seller's figure
        alpha, beta = 100 * x.return_rate, 100 * (1 - x.return_rate)
    else:
        alpha, beta = ra.value, rb.value
        group = platforms.FEE_GROUP.get(x.fee_category or "")
        if group:  # fashion returns far more than electronics: use the category's own mean
            try:
                cm = data.rate(f"return_mean_{group}", "ALL")
            except data.MissingRate:
                cm = None
            if cm:
                _prov(prov, cm, f"Return rate, {group}")
                alpha, beta = 100 * cm.value, 100 * (1 - cm.value)

    vat = 0.0
    if m["vat"]:
        v = data.rate(*m["vat"])
        _prov(prov, v, "VAT")
        vat = v.value

    p = Params(
        currency=m["currency"],
        vat=vat,
        fee=x.fee_rate if x.fee_rate is not None else fee_value,
        fee_fixed=fee_fixed if x.fee_rate is None else 0.0,
        fee_high=fee_high if x.fee_rate is None else None,
        fx_mean=x.fx if x.fx is not None else fx_r.value,
        fx_sd=fx_sd.value,
        freight_cny=(x.freight_cny_per_kg if x.freight_cny_per_kg is not None else fr_r.value) * x.weight_kg,
        cogs_cny=x.cogs_cny,
        ret_alpha=alpha,
        ret_beta=beta,
        duty_mode="ad_valorem",
        target=x.target_margin,
        provenance=prov,
        warnings=warnings,
    )

    if region == "EU":
        flat = data.rate("eu_flat_duty_per_category", "EU")
        threshold = data.rate("eu_flat_duty_threshold", "EU")
        _prov(prov, flat, "EU flat duty per tariff category")
        p.duty_mode = "eu_flat"
        p.duty_flat = flat.value * x.item_categories
        # sanity: the flat regime only applies to consignments <= EUR 150
        p.flat_threshold = threshold.value
        # ad-valorem rate kept for the > EUR 150 fallback
        if x.hs_code:
            try:
                dr = data.rate(f"duty_{x.hs_code}", "EU")
                p.duty_rate = dr.value
                p.duty_rate_known = True
                _prov(prov, dr, f"EU conventional duty {x.hs_code} (above EUR 150 only)")
            except data.MissingRate:
                pass
        else:
            warnings.append(
                "No HS code given. That does not change this price: under the EU flat regime the duty is EUR 3 per "
                "tariff category whatever the code. The customs declaration still needs a 6-digit HS code."
            )
        warnings.append(
            f"VAT uses {EU_COUNTRIES[x.market][0]}'s standard {vat:.1%} rate; some goods (e.g. food, books) use a reduced rate."
        )
    else:  # US
        dr = None
        if x.hs_code:
            try:
                dr = data.rate(f"duty_{x.hs_code}", "US")
            except data.MissingRate:
                if not x.indicative:
                    raise
        elif not x.indicative:
            raise data.MissingRate(
                "US duty depends on the exact HTS line, so a US price needs a confirmed HS code."
            )
        if dr is not None:
            _prov(prov, dr, f"US HTSUS duty {x.hs_code}" + (" (assumed code)" if x.hs_assumed else ""))
            p.duty_rate = dr.value
            if x.hs_assumed:
                warnings.append(
                    f"HS {x.hs_code} was assumed from the product description, not confirmed. Check it with a customs broker; "
                    "a different line can carry a different duty."
                )
        else:
            _prov(prov, data.Rate("us_base_duty_unknown", "US", 0.0, "ratio", "unknown", "https://hts.usitc.gov/",
                                  "2026-11-09", "Base duty of this product's HTS line is not loaded, so 0% is used here"),
                  "US base duty (HTS line not loaded)")
            p.duty_rate = 0.0
            warnings.append(
                "The base duty for this product's HTS line is not loaded, so only the 12.5% China Section 301 duty is "
                "included. Real landed cost is higher by that line's base duty (often 0-17%). Ask a customs broker for the HTS line."
            )
        dm = data.rate("us_de_minimis", "US")
        _prov(prov, dm, "US de minimis")
        fl = data.rate("us_forced_labor_301_china", "US")
        _prov(prov, fl, "US Section 301 forced-labor duty (China, 9903.05.31)")
        p.duty_rate += fl.value
        try:
            lr = data.rate(f"us_section301_list_{x.hs_code}", "US")
        except data.MissingRate:
            warnings.append(
                "US figure is a LOWER BOUND: the older Section 301 list duty (7.5% or 25%) for this exact HTS line is not loaded."
            )
        else:
            _prov(prov, lr, f"US Section 301 list duty {x.hs_code}")
            p.duty_rate += lr.value
            p.us_list_known = True
            warnings.append(
                "US duty assumes the Section 301 list duty stacks with the 12.5% forced-labor duty and that this line is on that list; "
                "both are from secondary sources. Confirm with a customs broker."
            )
    return p


def _goods_cost(p: Params, fx):
    base = (p.cogs_cny + p.freight_cny) / fx
    if p.duty_mode == "eu_flat":
        return base + p.duty_flat
    # US: duty on customs value (FOB, approximated by COGS converted at fx)
    return base + (p.cogs_cny / fx) * p.duty_rate


def _denom(p: Params) -> float:
    d = 1 / (1 + p.vat) - p.fee - p.target / (1 + p.vat)
    if d <= 0:
        raise EngineError("Target margin is unreachable with these fee and VAT rates")
    return d


def waterfall(p: Params) -> dict:
    fx = p.fx_mean
    r = p.ret_alpha / (p.ret_alpha + p.ret_beta)
    cogs = p.cogs_cny / fx
    freight = p.freight_cny / fx
    G = _goods_cost(p, fx)
    duty = G - cogs - freight
    returns = r * G
    price = (G * (1 + r) + p.fee_fixed) / _denom(p)
    net = price / (1 + p.vat)
    vat = price - net
    fee = p.fee * price + p.fee_fixed
    margin = net - fee - G - returns
    steps = [
        ("cogs", "COGS", cogs),
        ("freight", "Freight", freight),
        ("duty", "Duty", duty),
        ("returns", "Returns", returns),
        ("fee", "Platform fee", fee),
        ("vat", "VAT", vat),
        ("margin", "Margin", margin),
    ]
    return {
        "currency": p.currency,
        "price": round(price, 2),
        "net_revenue": round(net, 2),
        "margin_pct": round(margin / net, 4),
        "steps": [{"key": k, "label": lbl, "value": round(v, 2)} for k, lbl, v in steps if abs(v) > 1e-9],
        "_price_exact": price,
    }


def simulate(p: Params, price: float, paths: int = 5000, seed: int = 20261108) -> dict:
    rng = np.random.default_rng(seed)
    fx = p.fx_mean * (1 + p.fx_sd * rng.standard_normal(paths))
    r = rng.beta(p.ret_alpha, p.ret_beta, paths)
    G = _goods_cost(p, fx)
    net = price / (1 + p.vat)
    profit = net - p.fee * price - p.fee_fixed - G * (1 + r)
    margins = profit / net
    required = (G * (1 + r) + p.fee_fixed) / _denom(p)
    hist, edges = np.histogram(margins, bins=40)
    return {
        "paths": paths,
        "seed": seed,
        "p5_margin": round(float(np.quantile(margins, 0.05)), 4),
        "p50_margin": round(float(np.quantile(margins, 0.5)), 4),
        "p_below_target": round(float(np.mean(margins < p.target)), 4),
        "p_loss": round(float(np.mean(profit < 0)), 4),
        "floor_price_95": round(float(np.quantile(required, 0.95)), 2),
        "histogram": {"counts": hist.tolist(), "edges": [round(float(e), 4) for e in edges]},
    }


def stress(p: Params, price: float) -> list[dict]:
    def margin(q: Params) -> float:
        net = price / (1 + q.vat)
        r = q.ret_alpha / (q.ret_alpha + q.ret_beta)
        G = _goods_cost(q, q.fx_mean)
        return (net - q.fee * price - q.fee_fixed - G * (1 + r)) / net

    from dataclasses import replace

    base_ret = p.ret_alpha / (p.ret_alpha + p.ret_beta)
    rows = [
        ("Base case", p),
        ("CNY +5% vs destination currency", replace(p, fx_mean=p.fx_mean * 0.95)),
        (f"Return rate {max(0.15, base_ret + 0.10):.0%}", replace(p, ret_alpha=100 * max(0.15, base_ret + 0.10), ret_beta=100 * (1 - max(0.15, base_ret + 0.10)))),
        ("Freight +30% (peak season)", replace(p, freight_cny=p.freight_cny * 1.3)),
    ]
    if p.fee_high is not None and p.fee_high > p.fee + 1e-9:
        rows.append((f"Platform fee at the high end ({p.fee_high:.0%})", replace(p, fee=p.fee_high)))
    if p.duty_mode == "ad_valorem":
        rows.append(("Duty +10 percentage points", replace(p, duty_rate=p.duty_rate + 0.10)))
    else:
        rows.append(("Add a different kind of item, e.g. a free gift (+EUR 3 duty)", replace(p, duty_flat=p.duty_flat + 3)))
    return [{"scenario": s, "margin_pct": round(margin(q), 4)} for s, q in rows]


def landed_cost(x: Inputs) -> dict:
    """Full result for one SKU. Raises MissingRate/EngineError instead of guessing."""
    p = build_params(x)
    wf = waterfall(p)
    price = wf.pop("_price_exact")
    if p.duty_mode == "eu_flat" and price > p.flat_threshold:
        # Above EUR 150 the flat regime does not apply: the conventional rate of the exact code does.
        if not p.duty_rate_known:
            raise data.MissingRate(
                f"The price would be about EUR {price:.0f}, above the EUR {p.flat_threshold:.0f} ceiling of the flat "
                "EUR 3 duty, so the conventional duty of the exact tariff code applies and it is not in the "
                "verified tables" + (f" for {x.hs_code}" if x.hs_code else " (no HS code given)") + "."
            )
        p.duty_mode = "ad_valorem"
        wf = waterfall(p)
        price = wf.pop("_price_exact")
        p.warnings.append(
            f"Above the EUR {p.flat_threshold:.0f} flat-duty ceiling, so the conventional {p.duty_rate:.1%} duty for "
            f"{x.hs_code} applies instead of EUR 3 per category (customs value approximated by the goods cost)."
        )
    us_scen = None
    if x.market == "US" and not p.us_list_known:
        # the list duty of this line is not loaded: show the price under each rate it could carry
        us_scen = {f"list_duty_{r}": round(waterfall(replace(p, duty_rate=p.duty_rate + v))["price"], 2)
                   for r, v in (("7_5", 0.075), ("25", 0.25))}
    sim = simulate(p, price, x.paths, x.seed)
    out = {
        "inputs": {
            "market": x.market,
            "hs_code": x.hs_code,
            "cogs_cny": x.cogs_cny,
            "weight_kg": x.weight_kg,
            "target_margin": x.target_margin,
            "item_categories": x.item_categories,
            "platform": x.platform,
        },
        "waterfall": wf,
        "monte_carlo": sim,
        "stress": stress(p, price),
        "provenance": p.provenance,
        "warnings": p.warnings,
    }
    if us_scen:
        out["us_scenarios"] = us_scen
    out_tip = None
    if p.duty_mode == "eu_flat" and x.item_categories == 1:
        # The flat duty is per tariff category, not per unit: a multipack of the SAME item
        # still pays EUR 3 once, so the duty per unit falls. Only worth showing when the
        # duty is a large share of the price.
        duty_share = p.duty_flat / price
        if duty_share >= 0.10:
            options = []
            for n in (2, 3):
                q = build_params(Inputs(**{**x.__dict__, "cogs_cny": x.cogs_cny * n, "weight_kg": x.weight_kg * n}))
                if q.duty_mode != "eu_flat":
                    break
                pack = waterfall(q)["price"]
                if pack > q.flat_threshold:
                    break
                options.append({"units": n, "pack_price": pack, "price_per_unit": round(pack / n, 2),
                                "saving_per_unit": round(wf["price"] - pack / n, 2)})
            if options:
                out_tip = {
                    "duty_share_of_price": round(duty_share, 4),
                    "rule": "EU flat duty is EUR 3 per tariff category per parcel, not per unit",
                    "options": options,
                    "caveat": "Only identical items count as one category. A multipack changes the offer; check demand and the platform's variation rules.",
                }
                p.warnings.append(
                    f"The EUR 3 duty is {duty_share:.0%} of this price. A multipack of the same item pays it once: "
                    f"see multipack_tip."
                )
    if out_tip:
        out["multipack_tip"] = out_tip
    if p.duty_mode == "eu_flat" and x.item_categories > 1:
        alt = build_params(Inputs(**{**x.__dict__, "item_categories": 1}))
        alt_price = waterfall(alt)["price"]
        out["bundle_tip"] = {
            "rule": "WCO GRI 3(b) goods put up in sets for retail sale",
            "categories_now": x.item_categories,
            "price_if_one_set": alt_price,
            "price_reduction": round(wf["price"] - alt_price, 2),
            "caveat": "Set classification is a judgment call; confirm with a customs broker or BTI ruling before shipping.",
        }
    return out


def sweep(x: Inputs, n: int = 61, lo: float = 0.9, hi: float = 1.15) -> dict:
    """Risk curve: for a grid of list prices, P(margin >= target), P5 margin and
    expected margin, using one shared set of Monte Carlo draws (common random numbers)."""
    p = build_params(x)
    base = waterfall(p)["_price_exact"]
    prices = np.linspace(base * lo, base * hi, n)
    rng = np.random.default_rng(x.seed)
    fx = p.fx_mean * (1 + p.fx_sd * rng.standard_normal(x.paths))
    r = rng.beta(p.ret_alpha, p.ret_beta, x.paths)
    cost = _goods_cost(p, fx) * (1 + r)                       # (paths,)
    net = prices[:, None] / (1 + p.vat)                        # (n, 1)
    profit = net - p.fee * prices[:, None] - p.fee_fixed - cost[None, :]     # (n, paths)
    margins = profit / net
    return {
        "currency": p.currency,
        "target_margin": p.target,
        "target_price": round(base, 2),
        "prices": [round(float(v), 2) for v in prices],
        "p_hit_target": [round(float(v), 4) for v in (margins >= p.target).mean(axis=1)],
        "p5_margin": [round(float(v), 4) for v in np.quantile(margins, 0.05, axis=1)],
        "mean_margin": [round(float(v), 4) for v in margins.mean(axis=1)],
        "p_loss": [round(float(v), 4) for v in (profit < 0).mean(axis=1)],
    }
