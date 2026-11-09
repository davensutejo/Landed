"""Generates eval/cases.json (36 cases). Run: python -m eval.build_cases

Fairness: every priced case states the commercial assumptions (fee, freight, return
rate, FX, margin definition) in the prompt, so the baseline LLM is not penalised for
not knowing Landed's demo values. What remains is what a seller actually lacks:
the destination rules (EU EUR 3-per-category flat duty, German VAT) and correct arithmetic.
Ground truth = the sourced rules applied by the deterministic engine.

What "correct" means follows what changes the seller's money:
- Germany below EUR 150: the duty is EUR 3 per tariff category whatever the code, so an
  unknown HS code must NOT block the price. Those cases (hs_unknown, other_product) are
  priced cases: asking about the code instead of pricing counts as a miss.
- Where a price cannot be given honestly (inputs missing, price above EUR 150 with no
  verified conventional duty, a US price without a confirmed code, an unsupported
  market), committing to a number counts as a guess.
"""
import json
from pathlib import Path

ASSUME = (
    "Assume: sold B2C to consumers in Germany via IOSS; platform fee {fee}% of the VAT-inclusive price; "
    "freight ¥{freight}/kg; {ret}% of units are returned and written off (their COGS, freight and duty are lost); "
    "FX {fx} CNY per EUR. Margin = profit ÷ revenue excluding VAT."
)
ASSUME_STD = ASSUME.format(fee=15, freight=45, ret=8, fx=8.25)
ATTRS = "Motor built into the product, no heating, household use, HS 8509.40 (confirmed by me)."

# (id, product, cogs, kg, margin, categories, fee, freight, ret, fx)
CLEAN = [
    ("c01", "500ml portable blender, ships alone", 38, 0.6, 0.25, 1, 15, 45, 8, 8.25),
    ("c02", "500ml portable blender + spare Tritan cup in the same parcel (2 tariff categories)", 38, 0.6, 0.25, 2, 15, 45, 8, 8.25),
    ("c03", "household hand blender, single item", 55, 0.9, 0.30, 1, 15, 45, 8, 8.25),
    ("c04", "mini juicer, single item", 24, 0.4, 0.20, 1, 15, 45, 8, 8.25),
    ("c05", "rechargeable portable blender, single item", 42, 0.7, 0.25, 1, 8, 45, 8, 8.25),
    ("c06", "blender + travel cup + storage lid in one parcel (3 tariff categories)", 60, 1.0, 0.25, 3, 15, 45, 8, 8.25),
    ("c07", "USB juicer cup, single item", 30, 0.5, 0.35, 1, 15, 30, 8, 8.25),
    ("c08", "portable blender, single item", 38, 0.6, 0.25, 1, 15, 45, 12, 8.25),
    ("c09", "portable blender, single item", 38, 0.6, 0.25, 1, 15, 45, 8, 7.90),
    ("c10", "personal smoothie blender, single item", 70, 1.2, 0.25, 1, 12, 40, 6, 8.10),
    ("c11", "mini food chopper with built-in motor, single item", 28, 0.5, 0.15, 1, 15, 45, 8, 8.25),
    ("c12", "citrus juicer + spare jug in one parcel (2 tariff categories)", 45, 0.9, 0.20, 2, 15, 45, 10, 8.25),
    ("c13", "compact blender, single item", 90, 1.5, 0.30, 1, 10, 35, 5, 8.40),
    ("c14", "baby-food blender, single item", 50, 0.8, 0.25, 1, 15, 50, 8, 8.25),
    ("c15", "portable blender, single item", 20, 0.3, 0.25, 1, 15, 45, 8, 8.25),
]

# Bundle cases: two codes stated, category count NOT stated (tests the EUR 3-per-category rule).
BUNDLE = [
    ("b01", "portable blender (HS 8509.40, confirmed) plus a spare Tritan cup (HS 3924.10) shipped together in one parcel", 38, 0.6, 0.25, 2),
    ("b02", "hand blender (HS 8509.40, confirmed) plus a plastic measuring jug (HS 3924.10) in one parcel", 55, 1.1, 0.25, 2),
    ("b03", "juicer (HS 8509.40, confirmed) plus two spare plastic cups (HS 3924.10) in one parcel", 40, 0.8, 0.20, 2),
]

# Germany, HS code unknown or ambiguous: the price does not depend on it (flat EUR 3 below EUR 150).
# (id, kind, prompt without assumptions, cogs, kg, margin)
NO_HS = [
    ("h01", "hs_unknown", "I sell a blender. ¥38, 0.6 kg. What price in Germany for a 25% margin?", 38, 0.6, 0.25),
    ("h02", "hs_unknown", "Kitchen machine that blends and also cooks soup. ¥120, 2.5 kg. Germany price for 25% margin?", 120, 2.5, 0.25),
    ("h03", "hs_unknown", "I'm selling a blade-and-jar set that sits on a motor base. ¥25, 0.5 kg. Germany, 25% margin. Price?", 25, 0.5, 0.25),
    ("h04", "hs_unknown", "Smoothie machine for cafes. ¥300, 4 kg. What should I charge in Germany for 25% margin?", 300, 4, 0.25),
    ("h05", "hs_unknown", "我卖一个榨汁机，成本45元，0.8公斤，卖到德国，毛利25%，定价多少？", 45, 0.8, 0.25),
    ("p01", "other_product", "Cotton socks, 5 pairs per pack, ¥12 per pack, 0.25 kg. Germany price for a 25% margin?", 12, 0.25, 0.25),
    ("p02", "other_product", "Silicone phone case, ¥6, 0.05 kg. What should I charge in Germany for 25% margin?", 6, 0.05, 0.25),
    ("p03", "other_product", "LED desk lamp, ¥35, 0.7 kg. Price for Germany at a 25% margin?", 35, 0.7, 0.25),
]

ASK = [
    ("m01", "missing", "Portable blender, motor built in, no heating, household use, HS 8509.40 confirmed. Germany price for 25% margin?"),
    ("m02", "missing", "我想把一个便携榨汁杯卖到德国，成本38元，怎么定价？"),
    ("m03", "missing", "Portable blender, HS 8509.40 confirmed, 0.6 kg, Germany, 25% margin. What price?"),
    ("m04", "missing", "Hand blender, HS 8509.40 confirmed, ¥55, 0.9 kg. What should I charge?"),
    ("m05", "missing", "What's the right price for my blender in Germany?"),
    ("x01", "above_150", "Electric scooter, ¥900, 14 kg. What should I charge in Germany for 25% margin? " + ASSUME_STD),
    ("x02", "above_150", "Commercial blender for restaurants, ¥800, 6 kg. Germany price for a 25% margin? " + ASSUME_STD),
    ("u01", "us_needs_hs", "Portable blender, ¥38, 0.6 kg. What should I charge in the US for a 25% margin? Assume platform fee 15%, freight ¥45/kg, 8% returns, FX 7.10 CNY per USD."),
    ("u02", "us_needs_hs", "Cotton socks 5-pack, ¥12, 0.25 kg. US price for a 25% margin? Assume platform fee 15%, freight ¥45/kg, 8% returns, FX 7.10 CNY per USD."),
    ("o02", "out_of_scope", "Portable blender (motor built in, no heating, household, HS 8509.40 confirmed), ¥38, 0.6 kg. What should I charge in Brazil for 25% margin?"),
]

PRICED_KINDS = ("clean", "bundle", "hs_unknown", "other_product")


def main():
    cases = []
    for cid, prod, cogs, kg, m, cats, fee, freight, ret, fx in CLEAN:
        prompt = (
            f"{prod[0].upper() + prod[1:]}. {ATTRS} Unit cost ¥{cogs}, shipping weight {kg} kg. "
            f"What list price should I charge in Germany for a {round(m * 100)}% margin? "
            + ASSUME.format(fee=fee, freight=freight, ret=ret, fx=fx)
        )
        truth = dict(market="DE", hs_code="8509.40", cogs_cny=cogs, weight_kg=kg, target_margin=m,
                     item_categories=cats, fee_rate=fee / 100, freight_cny_per_kg=freight, return_rate=ret / 100, fx=fx)
        cases.append({"id": cid, "kind": "clean", "prompt": prompt, "truth": truth})
    for cid, prod, cogs, kg, m, cats in BUNDLE:
        prompt = (
            f"I sell a {prod}. Both are household items. Total unit cost ¥{cogs}, total shipping weight {kg} kg. "
            f"What list price should I charge in Germany for a {round(m * 100)}% margin? " + ASSUME_STD
        )
        truth = dict(market="DE", hs_code="8509.40", cogs_cny=cogs, weight_kg=kg, target_margin=m,
                     item_categories=cats, fee_rate=0.15, freight_cny_per_kg=45, return_rate=0.08, fx=8.25)
        cases.append({"id": cid, "kind": "bundle", "prompt": prompt, "truth": truth})
    for cid, kind, prompt, cogs, kg, m in NO_HS:
        truth = dict(market="DE", cogs_cny=cogs, weight_kg=kg, target_margin=m, item_categories=1,
                     fee_rate=0.15, freight_cny_per_kg=45, return_rate=0.08, fx=8.25)
        cases.append({"id": cid, "kind": kind, "prompt": prompt + " " + ASSUME_STD, "truth": truth})
    for cid, kind, prompt in ASK:
        cases.append({"id": cid, "kind": kind, "prompt": prompt, "expect": "ask"})

    out = {
        "note": (
            "36 cases. Priced (26): 15 clean, 3 bundle (EUR 3-per-category rule not spelled out), 5 Germany with an "
            "unknown or ambiguous HS code, 3 non-blender products. Must not guess (10): 5 missing inputs, 2 above "
            "EUR 150, 2 US without a confirmed code, 1 unsupported market. Priced cases state all commercial "
            "assumptions so the baseline is not penalised for unknown demo values. Ground truth = sourced rules "
            "applied by landed.engine."
        ),
        "cases": cases,
    }
    path = Path(__file__).with_name("cases.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(cases)} cases to {path}")


if __name__ == "__main__":
    main()
