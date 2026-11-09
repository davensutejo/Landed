"""The seller profile: what onboarding learns, and what each answer changes.

Every field here has an effect on the product, not just a label:
- niche / category -> which compliance checks run by default (compliance attrs)
- market, target_margin, fee/freight/return/fx -> applied to pricing in code
- parcel -> how the agent treats the number of kinds of item in a parcel
- cost_band -> the sample the onboarding preview prices, and the EUR 150 warning
- worries -> which panels and stress rows the workspace puts first
- platform + category -> the platform's sourced fee (secondary status) when the seller
  has not typed their own; platforms with no source found fall back to a flagged placeholder
"""
from __future__ import annotations

CATEGORIES = ("apparel", "electronics", "kitchen", "beauty", "toys", "home", "other")

# niche id -> (category, compliance attributes that hold for the whole niche)
NICHES: dict[str, tuple[str, dict]] = {
    "basics": ("apparel", {"textile": True}),
    "tops": ("apparel", {"textile": True}),
    "dresses": ("apparel", {"textile": True}),
    "shoes_bags": ("apparel", {}),
    "accessories": ("apparel", {}),
    "phone_acc": ("electronics", {}),
    "audio": ("electronics", {"electrical": True, "battery_builtin": True}),
    "lighting": ("electronics", {"electrical": True}),
    "gadgets": ("electronics", {"electrical": True}),
    "kitchen_appliance": ("kitchen", {"electrical": True, "food_contact": True}),
    "utensils": ("kitchen", {"food_contact": True}),
    "drinkware": ("kitchen", {"food_contact": True}),
    "food_storage": ("kitchen", {"food_contact": True}),
    "skincare": ("beauty", {"cosmetic": True}),
    "beauty_tools": ("beauty", {}),
    "beauty_devices": ("beauty", {"electrical": True, "battery_builtin": True}),
    "toys_games": ("toys", {"toy": True}),
    "plush": ("toys", {"toy": True}),
    "baby_care": ("toys", {}),
    "home_textiles": ("home", {"textile": True}),
    "decor": ("home", {}),
    "storage": ("home", {}),
    "other_niche": ("other", {}),
}
# Used when the seller picked a category but skipped the niche.
CATEGORY_ATTRS = {
    "apparel": {"textile": True},
    "electronics": {"electrical": True},
    "kitchen": {"food_contact": True},
}
PARCELS = ("single", "multipack", "mixed")
# typical unit cost (CNY) the onboarding preview prices for each band
COST_BANDS = {"lt20": 12.0, "20_60": 38.0, "60_150": 90.0, "gt150": 220.0}
WORRIES = ("duty", "fx", "returns", "freight", "fee", "compliance")
from . import platforms as _platforms

PLATFORMS = _platforms.ids()
from .markets import EU_COUNTRIES

MARKET_NAME = {**{c: v[0] for c, v in EU_COUNTRIES.items()}, "US": "United States"}
OWN_NUMBERS = ("fee_rate", "freight_cny_per_kg", "return_rate", "fx")
_BOUNDS = {"target_margin": (0.01, 0.7), "fee_rate": (0, 0.5), "return_rate": (0, 0.5),
           "freight_cny_per_kg": (0.01, 500), "fx": (0.01, 100)}


def clean(profile: dict | None) -> dict:
    """Keep only values the system understands; anything else is dropped, never trusted."""
    if not isinstance(profile, dict):
        return {}
    out: dict = {}
    if profile.get("market") in MARKET_NAME:
        out["market"] = profile["market"]
    if profile.get("niche") in NICHES:
        out["niche"] = profile["niche"]
        out["category"] = NICHES[profile["niche"]][0]
    elif profile.get("category") in CATEGORIES:
        out["category"] = profile["category"]
    plat = _platforms.LEGACY.get(profile.get("platform"), profile.get("platform"))
    if plat in PLATFORMS:
        out["platform"] = plat
    if profile.get("parcel") in PARCELS:
        out["parcel"] = profile["parcel"]
    if profile.get("cost_band") in COST_BANDS:
        out["cost_band"] = profile["cost_band"]
    worries = profile.get("worries")
    if isinstance(worries, list):
        out["worries"] = [w for w in dict.fromkeys(worries) if w in WORRIES]
        if not out["worries"]:
            del out["worries"]
    for k, (lo, hi) in _BOUNDS.items():
        v = profile.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi:
            out[k] = float(v)
    return out


def compliance_attrs(profile: dict | None) -> dict:
    """Attributes the seller's niche settles for the compliance check."""
    p = clean(profile)
    if p.get("niche"):
        return dict(NICHES[p["niche"]][1])
    return dict(CATEGORY_ATTRS.get(p.get("category"), {}))
