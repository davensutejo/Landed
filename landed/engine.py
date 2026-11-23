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
    # Costs most sellers carry that the default leaves at 0 (shown as "not included" until the seller enters them):
    ad_rate: float | None = None         # advertising as a share of sales (TACoS: ad spend / total sales incl. VAT)
    payout_rate: float | None = None     # payment provider's payout and currency conversion fee, share of the payout
    fulfilment_fee: float | None = None  # per-order fulfilment / pick-and-pack / last-mile fee, destination currency
    # Box size in cm (length, width, height). Freight is charged on the larger of the actual and the volumetric
    # weight (L x W x H / divisor), as couriers and e-commerce lines do.
    dims_cm: tuple[float, float, float] | list[float] | None = None
    volumetric_divisor: float | None = None
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
    us_list_known: bool = False
    fee_fixed: float = 0.0  # per-order platform fee in the destination currency
    fee_high: float | None = None
    target: float = 0.25
    flat_threshold: float = 150.0
    ad_rate: float = 0.0
    payout_rate: float = 0.0
    fulfil: float = 0.0  # per-order fulfilment fee in the destination currency
    chargeable_kg: float = 0.0
    provenance: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def pct(self) -> float:
        """Costs that scale with the list price P, as a share of P: the platform fee and advertising on the gross
        price, and the payout fee on the payout (approximated by revenue excl. VAT, a slight overstatement)."""
        return self.fee + self.ad_rate + self.payout_rate / (1 + self.vat)

    @property
    def per_order(self) -> float:
        """Costs per order in the destination currency: the platform's fixed fee and the fulfilment fee."""
        return self.fee_fixed + self.fulfil


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
                                   ("freight_cny_per_kg", x.freight_cny_per_kg), ("ad_rate", x.ad_rate),
                                   ("payout_rate", x.payout_rate), ("fulfilment_fee", x.fulfilment_fee),
                                   ("volumetric_divisor", x.volumetric_divisor)) if v is not None})
    if x.dims_cm is not None:
        if not isinstance(x.dims_cm, (list, tuple)) or len(x.dims_cm) != 3:
            raise EngineError("dims_cm must be three numbers: length, width and height in cm")
        nums.update({f"dims_cm[{i}]": v for i, v in enumerate(x.dims_cm)})
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
    if x.ad_rate is not None and not 0 <= x.ad_rate < 0.6:
        raise EngineError("ad_rate must be between 0 and 0.6 (e.g. 0.10 for ads costing 10% of sales)")
    if x.payout_rate is not None and not 0 <= x.payout_rate < 0.1:
        raise EngineError("payout_rate must be between 0 and 0.1 (e.g. 0.01 for a 1% payout and conversion fee)")
    if x.fulfilment_fee is not None and not 0 <= x.fulfilment_fee <= 100:
        raise EngineError("fulfilment_fee must be between 0 and 100 per order, in the destination currency")
    if x.dims_cm is not None and not all(0 < d <= 300 for d in x.dims_cm):
        raise EngineError("each box side (dims_cm) must be above 0 and at most 300 cm")
    if x.volumetric_divisor is not None and not 1000 <= x.volumetric_divisor <= 10000:
        raise EngineError("volumetric_divisor must be between 1000 and 10000 (cm3 per kg; couriers use 5000 or 6000)")
    # Sanity ceilings far beyond any real parcel, so overflow (1e308) can never reach the maths as inf/NaN.
    for name, v, hi in (("cogs_cny", x.cogs_cny, 1e7), ("weight_kg", x.weight_kg, 1000), ("fx", x.fx, 1000),
                        ("freight_cny_per_kg", x.freight_cny_per_kg, 1e5)):
        if v is not None and v > hi:
            raise EngineError(f"{name} must be at most {hi:g}")
    if x.fx is not None and x.fx < 1e-3:
        raise EngineError("fx must be at least 0.001 (CNY per unit of the destination currency)")
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
    # Freight is charged on the larger of the actual and the volumetric weight of the box.
    chargeable = x.weight_kg
    if x.dims_cm is not None:
        dv = data.rate("volumetric_divisor", "ALL")
        _prov(prov, dv, "Volumetric divisor (cm3 per kg)", override=x.volumetric_divisor is not None)
        divisor = x.volumetric_divisor if x.volumetric_divisor is not None else dv.value
        l, w, h = (float(d) for d in x.dims_cm)
        vol_kg = l * w * h / divisor
        chargeable = max(x.weight_kg, vol_kg)
        if vol_kg > x.weight_kg:
            warnings.append(
                f"Freight is charged on the box size: {l:g} x {w:g} x {h:g} cm is {vol_kg:.2f} kg volumetric "
                f"(divided by {divisor:g}) against {x.weight_kg:g} kg actual. A smaller box cuts freight."
            )
    # Advertising, payout and fulfilment: 0 unless the seller enters theirs, and labelled so.
    extra = {}
    for key, given, label, unit in (
        ("ad_rate", x.ad_rate, "Advertising (share of sales)", "ratio"),
        ("payout_rate", x.payout_rate, "Payout and currency conversion fee", "ratio"),
        ("fulfilment_fee", x.fulfilment_fee, "Fulfilment fee per order", m["currency"]),
    ):
        r = data.rate(key, "ALL")
        _prov(prov, replace(r, unit=unit), label, override=given is not None)
        extra[key] = given if given is not None else r.value
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
        freight_cny=(x.freight_cny_per_kg if x.freight_cny_per_kg is not None else fr_r.value) * chargeable,
        cogs_cny=x.cogs_cny,
        ret_alpha=alpha,
        ret_beta=beta,
        duty_mode="ad_valorem",
        target=x.target_margin,
        ad_rate=extra["ad_rate"],
        payout_rate=extra["payout_rate"],
        fulfil=extra["fulfilment_fee"],
        chargeable_kg=chargeable,
        provenance=prov,
        warnings=warnings,
    )

    if region == "EU":
        flat = data.rate("eu_flat_duty_per_category", "EU")
        threshold = data.rate("eu_flat_duty_threshold", "EU")
        _prov(prov, flat, "EU flat duty per tariff category")
        p.duty_mode = "eu_flat"
        p.duty_flat = flat.value * x.item_categories
        # the flat regime only applies to consignments <= EUR 150; above it the engine abstains
        p.flat_threshold = threshold.value
        if not x.hs_code:
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
    d = 1 / (1 + p.vat) - p.pct - p.target / (1 + p.vat)
    if d <= 0:
        raise EngineError("Target margin is unreachable with these fee, advertising and VAT rates")
    return d


def waterfall(p: Params) -> dict:
    fx = p.fx_mean
    r = p.ret_alpha / (p.ret_alpha + p.ret_beta)
    cogs = p.cogs_cny / fx
    freight = p.freight_cny / fx
    G = _goods_cost(p, fx)
    duty = G - cogs - freight
    returns = r * G
    price = (G * (1 + r) + p.per_order) / _denom(p)
    net = price / (1 + p.vat)
    vat = price - net
    fee = p.fee * price + p.fee_fixed
    ads = p.ad_rate * price
    payout = p.payout_rate * net
    fulfil = p.fulfil
    margin = net - fee - ads - payout - fulfil - G - returns
    steps = [
        ("cogs", "COGS", cogs),
        ("freight", "Freight", freight),
        ("duty", "Duty", duty),
        ("returns", "Returns", returns),
        ("fee", "Platform fee", fee),
        ("ads", "Advertising", ads),
        ("fulfilment", "Fulfilment", fulfil),
        ("payout", "Payout fee", payout),
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
    profit = net - p.pct * price - p.per_order - G * (1 + r)
    margins = profit / net
    required = (G * (1 + r) + p.per_order) / _denom(p)
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
        return (net - q.pct * price - q.per_order - G * (1 + r)) / net

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
    if p.ad_rate > 0:  # ad costs rise when a competitor bids up the same keywords
        rows.append((f"Advertising +5 points ({p.ad_rate + 0.05:.0%} of sales)", replace(p, ad_rate=p.ad_rate + 0.05)))
    if p.duty_mode == "ad_valorem":
        rows.append(("Duty +10 percentage points", replace(p, duty_rate=p.duty_rate + 0.10)))
    else:
        rows.append(("Add a different kind of item, e.g. a free gift (+EUR 3 duty)", replace(p, duty_flat=p.duty_flat + 3)))
    return [{"scenario": s, "margin_pct": round(margin(q), 4)} for s, q in rows]


def _check_flat_ceiling(p: Params, price: float) -> None:
    """EU prices are given only under the flat EUR 3 regime. Above EUR 150 the conventional duty of
    the exact tariff code applies instead, which is not loaded for every line, so abstain."""
    if p.duty_mode == "eu_flat" and price > p.flat_threshold:
        raise data.MissingRate(
            f"The price would be about EUR {price:.0f}, above the EUR {p.flat_threshold:.0f} ceiling of the flat "
            "EUR 3 duty. Above it the conventional duty of the exact tariff code applies, which Landed does not "
            "price. Ask a customs broker for the duty of the exact code."
        )


def landed_cost(x: Inputs) -> dict:
    """Full result for one SKU. Raises MissingRate/EngineError instead of guessing."""
    p = build_params(x)
    wf = waterfall(p)
    price = wf.pop("_price_exact")
    _check_flat_ceiling(p, price)
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
            "dims_cm": list(x.dims_cm) if x.dims_cm is not None else None,
            "chargeable_weight_kg": round(p.chargeable_kg, 3),
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
                # n boxes in one parcel weigh n times the chargeable weight of one (box size included)
                q = build_params(Inputs(**{**x.__dict__, "cogs_cny": x.cogs_cny * n, "weight_kg": p.chargeable_kg * n,
                                           "dims_cm": None}))
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


def _mean_return(p: Params) -> float:
    return p.ret_alpha / (p.ret_alpha + p.ret_beta)


def _profit_at(p: Params, price: float) -> tuple[float, float]:
    """Expected profit and margin per unit at a given list price (FX and returns at their means)."""
    net = price / (1 + p.vat)
    profit = net - p.pct * price - p.per_order - _goods_cost(p, p.fx_mean) * (1 + _mean_return(p))
    return profit, profit / net


def _max_cogs(p: Params, price: float, margin: float) -> float | None:
    """Highest unit cost in CNY that still earns `margin` at list price `price`, everything else unchanged.
    Inverts price = (G(1 + r) + per_order) / denom for G, then G for COGS. None if no cost is low enough."""
    denom = 1 / (1 + p.vat) - p.pct - margin / (1 + p.vat)
    G = (price * denom - p.per_order) / (1 + _mean_return(p))
    if p.duty_mode == "eu_flat":
        cogs = (G - p.duty_flat) * p.fx_mean - p.freight_cny
    else:  # G = (cogs + freight) / fx + cogs / fx * duty
        cogs = (G * p.fx_mean - p.freight_cny) / (1 + p.duty_rate)
    return round(cogs, 2) if cogs > 0 else None


def price_check(x: Inputs, list_price: float) -> dict:
    """The reverse question: "it sells for list_price, can I make money?". Margin and risk at that price
    for the seller's unit cost, and the highest unit cost that still hits the target margin or breaks even."""
    if not isinstance(list_price, (int, float)) or isinstance(list_price, bool) or not math.isfinite(list_price) or list_price <= 0:
        raise EngineError("list_price must be a positive number")
    p = build_params(x)
    _check_flat_ceiling(p, list_price)
    profit, margin = _profit_at(p, list_price)
    sim = simulate(p, list_price, x.paths, x.seed)
    sim.pop("histogram", None)
    sim.pop("floor_price_95", None)  # that is the price for the target, not a property of this price
    return {
        "currency": p.currency,
        "market": x.market,
        "list_price": round(list_price, 2),
        "target_margin": x.target_margin,
        "cogs_cny": x.cogs_cny,
        "profit_per_unit": round(profit, 2),
        "margin_pct": round(margin, 4),
        "monte_carlo": sim,
        "max_cogs_for_target": _max_cogs(p, list_price, x.target_margin),
        "max_cogs_break_even": _max_cogs(p, list_price, 0.0),
        "target_price": round(waterfall(p)["price"], 2),
        "warnings": [w for w in p.warnings if not w.startswith("No HS code given")],
    }


def compare_eu(x: Inputs, list_price: float | None = None) -> dict:
    """Same product, every EU country: the price that hits the target margin there and, at one shared
    list price (the seller's, or the target price in x.market), the profit per unit. Countries differ by
    VAT and by whether the seller's platform is sold there."""
    if x.market not in EU_COUNTRIES:
        raise EngineError("The EU comparison needs an EU market")
    base = build_params(x)
    if list_price is None:
        list_price = waterfall(base)["_price_exact"]
    if not isinstance(list_price, (int, float)) or isinstance(list_price, bool) or not math.isfinite(list_price) or list_price <= 0:
        raise EngineError("list_price must be a positive number")
    rows = []
    for c in EU_COUNTRIES:
        q = build_params(replace(x, market=c))
        row = {"market": c, "vat": q.vat, "fee": round(q.fee, 4),
               "platform_sold": not any("is not sold in" in w for w in q.warnings)}
        price = waterfall(q)["_price_exact"]
        row["target_price"] = round(price, 2) if price <= q.flat_threshold else None
        if list_price <= q.flat_threshold:
            profit, margin = _profit_at(q, list_price)
            row.update(profit_at_list=round(profit, 2), margin_at_list=round(margin, 4))
        else:
            row.update(profit_at_list=None, margin_at_list=None)
        rows.append(row)
    rows.sort(key=lambda r: (r["profit_at_list"] is None, -(r["profit_at_list"] or 0), r["market"]))
    return {"currency": "EUR", "list_price": round(list_price, 2), "target_margin": x.target_margin,
            "market": x.market, "rows": rows}


INPUT_FIELDS = {f for f in Inputs.__dataclass_fields__ if f not in ("paths", "seed")}
# Relative moves a saved product shrugs off: daily FX noise and a small re-estimate of FX volatility.
# Any other rate that changes at all is a real change (a VAT, duty or fee is not noise).
NOISE = {"fx_cny_per_eur": 0.005, "fx_cny_per_usd": 0.005, "fx_horizon_sd": 0.10}
PRICE_NOISE = 0.005  # the target price moved by half a percent or more


def baseline_of(res: dict) -> dict:
    """What a saved product remembers about its price: the result and every sourced rate behind it."""
    wf, mc = res["waterfall"], res["monte_carlo"]
    return {
        "price": wf["price"],
        "currency": wf["currency"],
        "margin_pct": wf["margin_pct"],
        "p_loss": mc["p_loss"],
        "floor_price_95": mc["floor_price_95"],
        # the seller's own figures are not rates that can move under them
        "rates": {p["key"]: {"value": p["value"], "snapshot_date": p["snapshot_date"], "label": p["label"], "unit": p.get("unit")}
                  for p in res["provenance"] if p.get("key") and p.get("status") != "seller_input"},
    }


def _check_summary(x: Inputs, price: float) -> dict | None:
    try:
        r = price_check(x, price)
    except (data.MissingRate, EngineError):
        return None
    return {"price": r["list_price"], "profit_per_unit": r["profit_per_unit"], "margin_pct": r["margin_pct"],
            "p_loss": r["monte_carlo"]["p_loss"], "max_cogs_for_target": r["max_cogs_for_target"]}


def review_saved(calc: dict, baseline: dict | None = None, check_price: float | None = None) -> dict:
    """Re-price a saved product against today's rates and say what moved since it was saved.

    status: unchanged | changed | no_baseline | abstain | error. The margin at the saved price is what the
    seller earns now if they keep their listing as it is; the target price is what to charge to get the
    margin back."""
    try:
        x = Inputs(**{k: v for k, v in (calc or {}).items() if k in INPUT_FIELDS})
        res = landed_cost(x)
    except data.MissingRate as e:
        return {"status": "abstain", "error": str(e)}
    except (EngineError, TypeError, ValueError) as e:
        return {"status": "error", "error": str(e)}
    now = baseline_of(res)
    out = {"status": "no_baseline", "market": x.market, "currency": now["currency"], "target_margin": x.target_margin,
           "target_price": now["price"], "p_loss": now["p_loss"], "current_baseline": now, "changes": []}
    old_price = (baseline or {}).get("price")
    if isinstance(old_price, (int, float)) and not isinstance(old_price, bool) and math.isfinite(old_price) and old_price > 0 \
            and baseline.get("currency") == now["currency"]:
        old_rates = baseline.get("rates") if isinstance(baseline.get("rates"), dict) else {}
        for key, r in now["rates"].items():
            old = old_rates.get(key)
            before = old.get("value") if isinstance(old, dict) else None
            if isinstance(before, (int, float)) and r["value"] is not None and abs(before - r["value"]) > 1e-9:
                out["changes"].append({"key": key, "label": r["label"], "unit": r["unit"], "before": before, "after": r["value"],
                                       "snapshot_date": r["snapshot_date"]})
        out["saved"] = {"price": round(old_price, 2), "margin_pct": baseline.get("margin_pct")}
        out["at_saved_price"] = _check_summary(x, old_price)
        # FX now refreshes daily (landed.fx), so it always drifts a little. Every change stays in `changes`,
        # but a drift below the noise floor does not flag the product: only a real move does.
        moved = abs(now["price"] - old_price) / old_price >= PRICE_NOISE
        material = [c for c in out["changes"] if abs(c["after"] - c["before"]) > NOISE.get(c["key"], 0) * abs(c["before"])]
        out["status"] = "changed" if material or moved else "unchanged"
    if isinstance(check_price, (int, float)) and not isinstance(check_price, bool) and math.isfinite(check_price) and check_price > 0:
        out["at_check_price"] = _check_summary(x, check_price)
    return out


def sweep(x: Inputs, n: int = 61, lo: float = 0.9, hi: float = 1.15) -> dict:
    """Risk curve: for a grid of list prices, P(margin >= target), P5 margin and
    expected margin, using one shared set of Monte Carlo draws (common random numbers)."""
    p = build_params(x)
    base = waterfall(p)["_price_exact"]
    _check_flat_ceiling(p, base)
    prices = np.linspace(base * lo, base * hi, n)
    rng = np.random.default_rng(x.seed)
    fx = p.fx_mean * (1 + p.fx_sd * rng.standard_normal(x.paths))
    r = rng.beta(p.ret_alpha, p.ret_beta, x.paths)
    cost = _goods_cost(p, fx) * (1 + r)                       # (paths,)
    net = prices[:, None] / (1 + p.vat)                        # (n, 1)
    profit = net - p.pct * prices[:, None] - p.per_order - cost[None, :]     # (n, paths)
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
