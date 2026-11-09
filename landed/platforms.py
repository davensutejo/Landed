"""Sales platforms by market, and what each charges.

Every fee here comes from third-party guides, not from the platform's own fee page, so each
carries status "secondary" (or "assumption") and a source link. Where nothing was found the
platform has no fee entry and the engine says so instead of guessing.
"""
from __future__ import annotations

import json
from functools import lru_cache

from . import data


@lru_cache
def table() -> dict:
    return json.loads((data.DATA_DIR / "platforms.json").read_text(encoding="utf-8"))


def ids() -> tuple[str, ...]:
    return tuple(table()["platforms"])


# Profile category -> the fee group most platforms price by. Anything else uses "default".
FEE_GROUP = {"apparel": "fashion", "electronics": "electronics", "kitchen": "home", "home": "home"}
LEGACY = {"amazon_de": "amazon", "tiktok": "tiktok"}  # ids saved by the first onboarding


def region(market: str) -> str:
    return "US" if market == "US" else "EU"


def available_markets(platform: str) -> list[str]:
    p = table()["platforms"].get(LEGACY.get(platform, platform))
    return list(p["markets"]) if p else []


def available(market: str) -> list[str]:
    return [pid for pid, p in table()["platforms"].items() if market in p["markets"]]


def fee(platform: str, market: str, category: str | None = None) -> dict | None:
    """The fee entry for this platform in this market, or None when no source was found."""
    p = table()["platforms"].get(LEGACY.get(platform, platform))
    if not p:
        return None
    reg = region(market)
    entry = p["fees"].get(reg)
    if not entry:
        return None
    allowed = p.get("fee_markets", {}).get(reg)
    if allowed is not None and market not in allowed:
        return None
    typical = entry["typical"]
    value = typical.get(FEE_GROUP.get(category or "", "default"), typical["default"])
    return {
        "name": p["name"],
        "value": value,
        "low": entry["low"],
        "high": entry["high"],
        "fixed": entry["fixed"],
        "status": entry["status"],
        "source_url": entry["source_url"],
        "note": entry["note"],
        "snapshot_date": table()["snapshot_date"],
    }


def listing(market: str, category: str | None = None) -> list[dict]:
    """What the app shows for a market: each platform with a short fee summary (or none)."""
    out = []
    for pid in available(market):
        f = fee(pid, market, category)
        p = table()["platforms"][pid]
        out.append({
            "id": pid,
            "name": p["name"],
            "fee": None if not f else {
                "typical": f["value"], "low": f["low"], "high": f["high"], "fixed": f["fixed"],
                "status": f["status"], "source_url": f["source_url"],
            },
        })
    return out
