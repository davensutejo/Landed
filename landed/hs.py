"""HS disambiguation over a hand-built candidate set.

Given the attributes the seller has stated, keep every candidate consistent with
them. If more than one survives, ask about the attribute whose answer minimises
the expected entropy of the remaining candidate set (uniform prior). Never pick
a code by guessing; the seller confirms.
"""
from __future__ import annotations

import math
import re

from . import data

# Facts the product type makes certain, read from the seller's own description so the
# seller is never asked "does your blender have a motor?". Explicit answers override these.
_APPLIANCE = re.compile(r"blend|smoothie|mixer|juicer|chopper|food processor|smoothie maker|榨汁|搅拌|料理机|破壁机|果汁机", re.I)
_PART = re.compile(r"\bjar\b|\bcup\b|\blid\b|\bblades?\b|spare|replacement|杯身|杯子|刀头|刀片|配件|盖子", re.I)
_SELF_CONTAINED = re.compile(r"portable|rechargeable|cordless|battery|usb|handheld|hand blender|immersion|stick|便携|充电|无线|电池|手持", re.I)
_DOMESTIC = re.compile(r"household|home|personal|portable|家用|便携|个人", re.I)
_COMMERCIAL = re.compile(r"commercial|industrial|cafe|café|restaurant|bar\b|商用|工业|餐厅|咖啡", re.I)
_HEATING = re.compile(r"heat|cook|soup|warm|加热|煮|汤", re.I)


def infer_attributes(description: str) -> dict:
    d = description or ""
    out: dict = {}
    if _APPLIANCE.search(d) and not _PART.search(d):
        out["has_electric_motor"] = True
        out["is_accessory_only"] = False
        if _SELF_CONTAINED.search(d):
            out["motor_self_contained"] = True
    if _COMMERCIAL.search(d):
        out["domestic_use"] = False
    elif _DOMESTIC.search(d):
        out["domestic_use"] = True
    if _HEATING.search(d):
        out["has_heating_element"] = True
    return out


def _consistent(cand: dict, known: dict) -> bool:
    for attr, required in cand["requires"].items():
        if attr in known and known[attr] is not None and bool(known[attr]) != required:
            return False
    return True


def _entropy(n: int) -> float:
    return math.log2(n) if n > 0 else 0.0


def _best_question(cands: list[dict], known: dict, attrs: dict) -> dict | None:
    best = None
    h0 = _entropy(len(cands))
    for attr, question in attrs.items():
        if attr in known and known[attr] is not None:
            continue
        # candidates that don't constrain the attribute survive either answer
        yes = [c for c in cands if c["requires"].get(attr, True) is True]
        no = [c for c in cands if c["requires"].get(attr, False) is False]
        if len(yes) == len(cands) and len(no) == len(cands):
            continue  # answer would not split anything
        # Uniform prior over candidates. A candidate that requires the attribute
        # answers deterministically; an unconstrained one answers yes/no 50:50.
        n = len(cands)
        n_true = sum(1 for c in cands if c["requires"].get(attr) is True)
        n_free = sum(1 for c in cands if attr not in c["requires"])
        p_yes = (n_true + 0.5 * n_free) / n
        p_no = 1 - p_yes
        expected = p_yes * _entropy(len(yes)) + p_no * _entropy(len(no))
        gain = h0 - expected
        if best is None or gain > best["information_gain_bits"]:
            best = {"attribute": attr, "question": question, "information_gain_bits": round(gain, 3)}
    return best


def classify(description: str, attributes: dict | None = None) -> dict:
    """Return surviving HS candidates, the next question to ask (if any) and a status.

    `attributes` keys must come from hs_tree.json `attributes`; unknown keys are ignored.
    """
    tree = data.hs_tree()
    attrs = tree["attributes"]
    stated = {k: v for k, v in (attributes or {}).items() if k in attrs and v is not None}
    known = {**infer_attributes(description), **stated}
    survivors = [c for c in tree["candidates"] if _consistent(c, known)]

    result = {
        "description": description,
        "known_attributes": known,
        "candidates": [
            {
                "hs": c["hs"],
                "title": c["title"],
                "reasoning": c["reasoning"],
                "legal_refs": c["legal_refs"],
                "source_url": c["source_url"],
            }
            for c in survivors
        ][:3],
        "snapshot_date": tree["snapshot_date"],
    }
    if not survivors:
        result["status"] = "out_of_scope"
        result["message"] = (
            "No candidate in Landed's verified category matches these attributes. "
            "Abstain: recommend a customs broker or a binding ruling."
        )
        return result
    if len(survivors) == 1:
        missing = [a for a in survivors[0]["requires"] if a not in known]
        if not missing:
            result["status"] = "resolved"
            result["message"] = "Single candidate. Ask the seller to confirm before pricing."
            return result
        # one candidate left but some of its conditions are unverified: ask about them
        attr = missing[0]
        result["status"] = "needs_confirmation"
        result["next_question"] = {"attribute": attr, "question": attrs[attr], "information_gain_bits": 0.0}
        return result
    q = _best_question(survivors, known, attrs)
    result["status"] = "ambiguous"
    result["next_question"] = q
    return result


# Likely US HTS heading by product wording. Used only to price indicatively when the seller gave no code; the
# result is labelled "assumed". Only headings whose general rate is the same on every line are listed.
US_GUESS = [
    (r"candle|蜡烛|香薰蜡", "3406.00", "candles"),
    (r"(?:cotton|纯棉|全棉)[^.\n]{0,30}(?:t-?shirt|tee|t恤)|(?:t-?shirt|tee|t恤)[^.\n]{0,30}(?:cotton|纯棉|全棉)", "6109.10", "cotton T-shirts"),
    (r"yoga mat|瑜伽垫|exercise mat|fitness mat|resistance band|弹力带|dumbbell|哑铃", "9506.91", "exercise equipment"),
    (r"earbuds?|earphones?|headphones?|耳机|耳塞", "8518.30", "headphones and earphones"),
    (r"\btoys?\b|puzzle|拼图|玩具|\bdolls?\b|building blocks?|积木", "9503.00", "toys"),
    (r"skin ?care|serum|face cream|moisturi[sz]er|lotion|精华|面霜|乳液|护肤", "3304.99", "skin-care preparations"),
]


def suggest_us(text: str) -> tuple[str, str] | None:
    """(hs_code, what it is) when the wording points to exactly one heading, else None."""
    import re

    hits = {(code, label) for rx, code, label in US_GUESS if re.search(rx, text, re.I)}
    return next(iter(hits)) if len(hits) == 1 else None
