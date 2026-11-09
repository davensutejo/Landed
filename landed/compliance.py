"""Rule-based compliance flags. Each flag carries its source and status."""
from __future__ import annotations

from . import data

from .markets import EU_COUNTRIES

REGION = {**{c: "EU" for c in EU_COUNTRIES}, "US": "US"}


def flags(market: str, attributes: dict) -> dict:
    region = REGION.get(market)
    if region is None:
        return {"market": market, "flags": [], "status": "out_of_scope"}
    attributes = dict(attributes)
    if attributes.get("has_electric_motor"):
        attributes.setdefault("electrical", True)  # the CE / FCC rules are about any electrical product
    rules = data.compliance_rules()
    out = []
    for rule in rules["rules"]:
        if region not in rule["markets"]:
            continue
        ok = True
        for cond, val in rule["when"].items():
            if cond == "item_categories_gt":
                ok &= int(attributes.get("item_categories", 1)) > val
            else:
                ok &= attributes.get(cond) == val
        if ok:
            out.append({k: rule[k] for k in ("id", "flag", "severity", "status", "source_url", "plain", "plain_zh") if k in rule})
    order = {"blocker": 0, "warning": 1, "opportunity": 2}
    out.sort(key=lambda f: order.get(f["severity"], 9))
    return {"market": market, "flags": out, "snapshot_date": rules["snapshot_date"]}
