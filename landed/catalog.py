"""Catalogue audit: a seller's product list in, a ranked verdict and fix per product out.

No LLM touches this module. Every figure comes from engine.price_check / landed_cost / compare_eu,
row by row, so each row carries the same sourced numbers a single quote would. A row that cannot be
read or priced gets its own error or abstention and never stops the others.

Verdicts, worst first:
  loses_money    profit per unit below zero at the seller's current price
  below_target   profitable, but under the target margin
  not_priced     the engine abstains (EU price above the EUR 150 flat-duty ceiling, a missing rate)
  error          the row could not be read (no cost, a weight of "abc", an unknown market)
  no_price       no current price given: the target price is reported instead
  on_target      at or above the target margin
"""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import replace

from . import data, engine
from .markets import EU_COUNTRIES

MAX_ROWS = 500
AUDIT_PATHS = 2000  # Monte Carlo paths per row; a quote uses 5000, an audit only needs the loss chance
MARGIN_TOLERANCE = 0.005  # 24.6% against a 25% target is "on target": the price was rounded to cents

ORDER = ("loses_money", "below_target", "not_priced", "error", "no_price", "on_target")

# field -> header spellings (compared after _norm). English, Chinese, and the engine's own names.
HEADERS: dict[str, tuple[str, ...]] = {
    "name": ("name", "product", "product name", "title", "sku", "item", "商品", "商品名称", "产品", "产品名称", "名称", "品名"),
    "cogs_cny": ("cogs", "cost", "unit cost", "cost price", "purchase price", "成本", "单件成本", "成本价", "进价",
                 "进货价", "采购价", "采购成本"),
    "weight_kg": ("weight", "shipping weight", "gross weight", "重量", "毛重"),
    "list_price": ("list price", "price", "selling price", "sale price", "current price", "retail price", "售价", "定价",
                   "现价", "销售价"),
    "market": ("market", "country", "destination", "市场", "国家", "目的国"),
    "item_categories": ("item categories", "categories", "kinds", "tariff categories", "品类数", "种类数"),
    "hs_code": ("hs code", "hs", "税号", "hs编码"),
    # Only an explicit target. A bare "margin" / "毛利" column usually holds the seller's current margin,
    # which the audit computes itself; reading it as the target would move every verdict.
    "target_margin": ("target margin", "目标毛利", "目标毛利率"),
    "monthly_units": ("monthly units", "units per month", "monthly sales", "月销量", "月销"),
}
_ENGINE_NAMES = {"cogs_cny": "cogs_cny", "weight_kg": "weight_kg", "weight_g": "weight_g", "list_price": "list_price",
                 "item_categories": "item_categories", "hs_code": "hs_code", "target_margin": "target_margin"}

# Units and currencies written into a header: "Cost (¥)", "Weight(kg)", "重量（克）", "售价(€)", "cost/unit".
_HEADER_UNIT = re.compile(r"\b(?:kg|kgs|g|grams?|cny|rmb|eur|usd|pcs)\b|公斤|千克|克|人民币|欧元|美元|元|[¥￥€$%％]"
                          r"|/\s*(?:unit|pc|pcs|piece|件)\b|\bper (?:unit|piece)\b|每件|单件(?=价)")
_GRAMS_HEADER = re.compile(r"\b(?:g|grams?)\b|(?<!千)克")


def _norm(h: str) -> str:
    return re.sub(r"[\s_\-()（）\[\]【】:：]+", " ", (h or "").strip().lower()).strip()


_LOOKUP = {_norm(s): f for f, spellings in HEADERS.items() for s in spellings}
_LOOKUP.update(_ENGINE_NAMES)


def _field_of(header: str) -> str | None:
    n = _norm(header)
    if n in _LOOKUP:
        return _LOOKUP[n]
    base = _norm(_HEADER_UNIT.sub(" ", n))
    f = _LOOKUP.get(base)
    if f == "weight_kg" and _GRAMS_HEADER.search(n):
        return "weight_g"
    return f

_MARKETS = {"US": "US", "USA": "US", "UNITED STATES": "US", "美国": "US"}
for _code, (_en, _zh, _extra) in EU_COUNTRIES.items():
    _MARKETS.update({_code: _code, _en.upper(): _code, _zh: _code, **{e.upper(): _code for e in _extra}})
_MARKETS["EL"] = "GR"


class RowError(ValueError):
    pass


def map_headers(headers: list[str]) -> dict[str, int]:
    """Column index per field. Unknown columns are ignored; a field named twice keeps the first column."""
    out: dict[str, int] = {}
    for i, h in enumerate(headers):
        f = _field_of(h)
        if f and f not in out:
            out[f] = i
    return out


_CURRENCY = {
    "EUR": re.compile(r"€|eur|euro|欧元"),
    "USD": re.compile(r"\$|usd|美元"),
    "CNY": re.compile(r"[¥￥元块]|cny|rmb|人民币"),
}
MAX_MONTHLY_UNITS = 10_000_000
UNITLESS_KG_LIMIT = 50  # "250" under a plain weight header is almost always grams


def currency_of(raw: str) -> str | None:
    low = (raw or "").lower()
    found = [c for c, rx in _CURRENCY.items() if rx.search(low)]
    return found[0] if len(found) == 1 else None


def parse_number(raw: str, field: str) -> float:
    """'¥38', '38元', '1,299.00', '1.299,00', '12,5', '0.6kg', '600 g', '25%' -> a float in the field's unit."""
    s = (raw or "").strip()
    if not s:
        raise RowError(f"{field} is empty")
    low = re.sub(r"[\s  ]", "", s.lower())
    grams = bool(re.search(r"\d(g|克|gram|grams)$", low))
    kilos = bool(re.search(r"\d(kg|kgs|公斤|千克)$", low))
    pct = low.endswith(("%", "％"))
    num = re.sub(r"(cny|rmb|eur|euro|usd|us|kgs|kg|公斤|千克|grams?|人民币|克|元|块|欧元|美元|[¥￥€$%％g])", "", low)
    if not re.fullmatch(r"[+-]?(\d+([.,]\d+)*|[.,]\d+)", num):
        raise RowError(f"{field} is not a number: {raw!r}")
    if "." in num and "," in num:
        dec = "." if num.rfind(".") > num.rfind(",") else ","
        num = num.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "," in num:
        # "1,299" / "12,000,000" are thousands. "12,5", "0,250" (a group never starts with 0) and any weight
        # (no parcel weighs 1,000 kg) are decimal commas.
        thousands = re.fullmatch(r"[+-]?[1-9]\d{0,2}(,\d{3})+", num) and not field.startswith("weight")
        num = num.replace(",", "") if thousands else num.replace(",", ".")
    elif num.count(".") > 1 or (field == "monthly_units" and re.fullmatch(r"[+-]?[1-9]\d{0,2}(\.\d{3})+", num)):
        num = num.replace(".", "")  # "1.299.000"; "1.200" units a month is 1200, not 1.2
    try:
        v = float(num)
    except ValueError:
        raise RowError(f"{field} is not a number: {raw!r}") from None
    if not math.isfinite(v):
        raise RowError(f"{field} is not a finite number: {raw!r}")
    if field.startswith("weight"):
        if kilos:
            pass
        elif grams or field == "weight_g":
            v /= 1000
        elif v >= UNITLESS_KG_LIMIT:
            raise RowError(f"weight {raw!r} has no unit: write {raw}g for grams or {raw}kg for kilograms")
    if field == "target_margin" and (pct or v >= 1):
        v /= 100
    if field == "monthly_units":
        if v != int(v) or v < 0:
            raise RowError(f"monthly units must be a whole number: {raw!r}")
        if v > MAX_MONTHLY_UNITS:
            raise RowError(f"monthly units must be at most {MAX_MONTHLY_UNITS:,}")
    return v


def parse_market(raw: str) -> str:
    code = _MARKETS.get((raw or "").strip().upper()) or _MARKETS.get((raw or "").strip())
    if not code:
        raise RowError(f"market {raw!r} is not covered: Landed prices the 27 EU countries and the US")
    return code


def _cell(row: list[str], cols: dict[str, int], field: str) -> str:
    i = cols.get(field)
    return row[i].strip() if i is not None and i < len(row) and row[i] is not None else ""


def read_csv(text: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Header, then (file line number, cells) for every non-blank row."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        raise engine.EngineError("The file is empty")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows: list[tuple[int, list[str]]] = []
    try:
        for r in reader:
            if any(c.strip() for c in r):
                rows.append((reader.line_num, r))
    except csv.Error as e:
        raise engine.EngineError(f"The file could not be read near line {reader.line_num}: {e}") from None
    if not rows:
        raise engine.EngineError("The file is empty")
    return rows[0][1], rows[1:]


def _row_inputs(row: list[str], cols: dict[str, int], defaults: dict) -> tuple[engine.Inputs, float | None, float | None]:
    market = parse_market(_cell(row, cols, "market")) if _cell(row, cols, "market") else defaults.get("market", "DE")
    if not _cell(row, cols, "cogs_cny"):
        raise RowError("no unit cost (CNY)")
    cogs = parse_number(_cell(row, cols, "cogs_cny"), "cogs_cny")
    if _cell(row, cols, "weight_kg"):
        weight = parse_number(_cell(row, cols, "weight_kg"), "weight_kg")
    elif _cell(row, cols, "weight_g"):
        weight = parse_number(_cell(row, cols, "weight_g"), "weight_g")
    else:
        raise RowError("no weight")
    kw = {k: defaults[k] for k in ("fee_rate", "platform", "fee_category", "freight_cny_per_kg", "return_rate", "fx")
          if defaults.get(k) is not None}
    margin = parse_number(_cell(row, cols, "target_margin"), "target_margin") if _cell(row, cols, "target_margin") \
        else defaults.get("target_margin", 0.25)
    cats = 1
    if _cell(row, cols, "item_categories"):
        c = parse_number(_cell(row, cols, "item_categories"), "item_categories")
        if c != int(c) or not 1 <= c <= 20:
            raise RowError("item categories must be a whole number from 1 to 20")
        cats = int(c)
    hs_code = _cell(row, cols, "hs_code") or None
    x = engine.Inputs(market=market, cogs_cny=cogs, weight_kg=weight, target_margin=margin, item_categories=cats,
                      hs_code=hs_code, paths=AUDIT_PATHS, **kw)
    if market == "US" and not hs_code:
        x = replace(x, indicative=True)
    raw_price = _cell(row, cols, "list_price")
    price = parse_number(raw_price, "list_price") if raw_price else None
    if price is not None:
        want = "USD" if market == "US" else "EUR"
        got = currency_of(raw_price)
        if got is None and re.search(r"[¥￥€$元块]|eur|usd|cny|rmb|人民币|欧元|美元", raw_price.lower()):
            raise RowError(f"the selling price {raw_price!r} names more than one currency")
        if got not in (None, want):
            raise RowError(f"the selling price {raw_price!r} is in {got}; for {market} it must be in {want}")
    units = parse_number(_cell(row, cols, "monthly_units"), "monthly_units") if _cell(row, cols, "monthly_units") else None
    return x, price, units


def _actions(x: engine.Inputs, price: float | None, check: dict | None, quote: dict | None) -> list[dict]:
    acts: list[dict] = []
    short = check is not None and check["margin_pct"] < x.target_margin - MARGIN_TOLERANCE
    if short and quote is not None:
        acts.append({"kind": "raise_price", "to": quote["waterfall"]["price"]})
    if short and check.get("max_cogs_for_target") and check["max_cogs_for_target"] > 0:
        acts.append({"kind": "cut_cost", "to_cny": check["max_cogs_for_target"]})
    if quote is not None and quote.get("multipack_tip"):
        best = max(quote["multipack_tip"]["options"], key=lambda o: o["saving_per_unit"])
        acts.append({"kind": "multipack", **best})
    if quote is not None and quote.get("bundle_tip") and quote["bundle_tip"]["price_reduction"] > 0:
        acts.append({"kind": "one_set", "price_if_one_set": quote["bundle_tip"]["price_if_one_set"],
                     "price_reduction": quote["bundle_tip"]["price_reduction"]})
    if price is not None and check is not None and x.market in EU_COUNTRIES:
        try:
            cmp = engine.compare_eu(x, price)
        except (engine.EngineError, data.MissingRate):
            cmp = None
        ok = [r for r in (cmp or {}).get("rows", []) if r["platform_sold"] and r["profit_at_list"] is not None]
        if ok:
            best = max(ok, key=lambda r: r["profit_at_list"])
            gain = best["profit_at_list"] - check["profit_per_unit"]
            if best["market"] != x.market and gain >= max(0.10, 0.05 * abs(check["profit_per_unit"])):
                acts.append({"kind": "better_market", "market": best["market"], "profit_per_unit": best["profit_at_list"],
                             "gain_per_unit": round(gain, 2)})
    return acts


def audit_row(row: list[str], cols: dict[str, int], defaults: dict, width: int | None = None) -> dict:
    out: dict = {"name": _cell(row, cols, "name") or None}
    if width is not None and len(row) > width and any(c.strip() for c in row[width:]):
        # An unquoted comma in a name ("Pack, 2") shifts every later column: never read it.
        return {**out, "verdict": "error", "actions": [],
                "error": f"this row has {len(row)} cells but the header has {width}; put a name that contains "
                         f"a comma in double quotes"}
    try:
        x, price, units = _row_inputs(row, cols, defaults)
    except (ValueError, TypeError) as e:  # RowError and EngineError are ValueErrors
        return {**out, "verdict": "error", "error": str(e), "actions": []}
    out.update(market=x.market, currency="USD" if x.market == "US" else "EUR", cogs_cny=x.cogs_cny,
               weight_kg=x.weight_kg, target_margin=x.target_margin, list_price=price, monthly_units=units,
               us_lower_bound=x.indicative)
    check = quote = None
    try:
        quote = engine.landed_cost(x)
        out["target_price"] = quote["waterfall"]["price"]
        # A US line whose older Section 301 list duty is not loaded is a floor too (the engine shows us_scenarios).
        out["us_lower_bound"] = x.indicative or bool(quote.get("us_scenarios"))
    except data.MissingRate as e:
        out["target_price"] = None
        out["note"] = str(e)
    except engine.EngineError as e:
        return {**out, "verdict": "error", "error": str(e), "actions": []}
    if price is not None:
        try:
            check = engine.price_check(x, price)
        except data.MissingRate as e:
            return {**out, "verdict": "not_priced", "note": str(e), "actions": []}
        except engine.EngineError as e:
            return {**out, "verdict": "error", "error": str(e), "actions": []}
        out.update(profit_per_unit=check["profit_per_unit"], margin=check["margin_pct"],
                   chance_of_loss=check["monte_carlo"]["p_loss"])
        if units is not None:
            out["monthly_profit"] = round(check["profit_per_unit"] * units, 2)
        if check["profit_per_unit"] < 0:
            out["verdict"] = "loses_money"
        elif check["margin_pct"] < x.target_margin - MARGIN_TOLERANCE:
            out["verdict"] = "below_target"
        else:
            out["verdict"] = "on_target"
    else:
        out["verdict"] = "no_price" if quote is not None else "not_priced"
    out["actions"] = _actions(x, price, check, quote)
    return out


def audit(text: str, defaults: dict | None = None) -> dict:
    """Audit a CSV catalogue. Raises EngineError only for a file that cannot be read at all."""
    defaults = dict(defaults or {})
    if defaults.get("market"):
        defaults["market"] = parse_market(str(defaults["market"]))
    headers, rows = read_csv(text)
    cols = map_headers(headers)
    if "cogs_cny" not in cols:
        raise engine.EngineError("No unit-cost column found. Name one column 'cost' or '成本' (unit cost in CNY).")
    if "weight_kg" not in cols and "weight_g" not in cols:
        raise engine.EngineError("No weight column found. Name one column 'weight' (kg) or '重量'.")
    if len(rows) > MAX_ROWS:
        raise engine.EngineError(f"At most {MAX_ROWS} products per audit; this file has {len(rows)}.")
    results = []
    for line, row in rows:  # the file's own line numbers, blank lines included
        r = audit_row(row, cols, defaults, width=len(headers))
        r["line"] = line
        results.append(r)
    rank = {v: k for k, v in enumerate(ORDER)}
    results.sort(key=lambda r: (rank[r["verdict"]], r.get("profit_per_unit") if r.get("profit_per_unit") is not None
                                else math.inf, r["line"]))

    def by_currency(rs: list[dict]) -> dict[str, float] | None:
        out: dict[str, float] = {}
        for r in rs:
            if r.get("monthly_profit") is not None:
                out[r["currency"]] = round(out.get(r["currency"], 0.0) + r["monthly_profit"], 2)
        return out or None  # EUR and USD are never added together

    summary = {
        "products": len(results),
        "by_verdict": {v: sum(1 for r in results if r["verdict"] == v) for v in ORDER},
        "monthly_profit": by_currency(results),
        "monthly_loss_from_losing_products": by_currency([r for r in results if r["verdict"] == "loses_money"]),
        "columns_used": {f: headers[i] for f, i in sorted(cols.items(), key=lambda kv: kv[1])},
        "columns_ignored": [h for i, h in enumerate(headers) if i not in cols.values() and h.strip()],
    }
    return {"summary": summary, "rows": results, "snapshot_date": data.rate("eu_flat_duty_per_category", "EU").snapshot_date}
