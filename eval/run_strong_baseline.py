"""Landed vs. stronger no-tool baselines: the same model, given the rules (and the formula) in its prompt.

The headline eval (run_eval.py) compares Landed with the same model and no help, which mostly shows
that the model does not know the July 2026 EU rule. This run asks what is left once it does:

  plain          the headline baseline: "helpful assistant", no rules
  rules          + a rule sheet generated from data/rates.csv (the same sourced snapshot the engine
                   reads): EU flat duty and its EUR 150 ceiling, all 27 VAT rates, the US rules and
                   the listed HS duties, plus "answer ASK when a figure you need is missing"
  rules_formula  + the engine's closed-form price formula, so only arithmetic and judgement remain

All three use the same model, temperature and provider settings as Landed, the same 36 cases and the
same scoring as run_eval.py.

Usage:  .venv/Scripts/python -m eval.run_strong_baseline        (needs LLM_API_KEY in .env)
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.run_eval import (  # noqa: E402  (loads .env)
    PRICED_KINDS, SUFFIX, BASELINE_SYSTEM, _retry, lower_bound_ok, margin_at, mcnemar_exact, parse_final,
    run_landed, wilson,
)
from landed import agent, engine  # noqa: E402
from landed.markets import name as market_name  # noqa: E402

# Seller-side assumptions every priced prompt states itself; not rules of the destination.
_NOT_RULES = {"platform_fee", "freight_cny_per_kg", "return_alpha", "return_beta", "return_mean_fashion",
              "return_mean_electronics", "fx_cny_per_eur", "fx_cny_per_usd", "fx_horizon_sd"}


def rule_sheet() -> str:
    rows = list(csv.DictReader(open(ROOT / "data" / "rates.csv", encoding="utf-8", newline="")))
    by = {(r["key"], r["market"]): r for r in rows}
    flat, ceiling = by[("eu_flat_duty_per_category", "EU")], by[("eu_flat_duty_threshold", "EU")]
    vat = sorted((r for r in rows if r["key"] == "vat_standard"), key=lambda r: r["market"])
    eu_duty = [r for r in rows if r["key"].startswith("duty_") and r["market"] == "EU"]
    us_duty = [r for r in rows if r["key"].startswith("duty_") and r["market"] == "US"]
    s301 = by[("us_forced_labor_301_china", "US")]
    used = {"eu_flat_duty_per_category", "eu_flat_duty_threshold", "vat_standard", "us_forced_labor_301_china",
            "us_de_minimis", *(r["key"] for r in eu_duty + us_duty)}
    assert {r["key"] for r in rows} <= used | _NOT_RULES, "rates.csv has rows the sheet does not cover"

    pct = lambda r: f"{float(r['value']) * 100:g}%"  # noqa: E731
    lines = [
        f"RULE SHEET (sourced, snapshot {flat['snapshot_date']}). Goods ship from China. Use these rules; do not "
        "use other duty or VAT figures.",
        "",
        "EU, B2C parcels sold via IOSS:",
        f"- Customs duty for a consignment with intrinsic value <= EUR {float(ceiling['value']):g}: a flat EUR "
        f"{float(flat['value']):g} per tariff category (per distinct kind of item in the parcel, by tariff "
        "classification, not by quantity), whatever the HS code, from 1 Jul 2026. Note: " + flat["note"],
        f"- Above EUR {float(ceiling['value']):g} the flat duty does not apply: the conventional duty of the "
        "product's exact HS code applies. Conventional rates available (secondary source, confirm the 10-digit "
        "line): " + "; ".join(f"HS {r['key'][5:]} {pct(r)}" for r in eu_duty) + ". No other codes are available.",
        "- Import VAT at the destination country's standard rate, included in the consumer price: "
        + ", ".join(f"{market_name(r['market'])} {pct(r)}" for r in vat) + ".",
        "",
        "United States:",
        "- Duty-free de minimis is suspended for all countries: every parcel pays duty. " + by[("us_de_minimis", "US")]["note"],
        f"- China-origin goods pay an extra {pct(s301)} Section 301 duty (HTS 9903.05.31) on the customs value, on top "
        "of the HTS line's base duty. Older Section 301 list duties (7.5% or 25%, by exact HTS line) may also apply "
        "and are not in this sheet.",
        "- Base duty (column 1 general rate) is known only for: " + "; ".join(f"HTS {r['key'][5:]} {pct(r)}" for r in us_duty)
        + ". Without a confirmed HTS code the base duty is unknown.",
        "- US prices exclude sales tax.",
        "",
        "Other destination markets: no rules available.",
        "",
        "If a figure you need is neither given by the seller nor in this sheet (for example the product cost, the "
        "weight, the target margin, or the duty of an HS code that is unconfirmed or not listed), do not estimate it: "
        "answer FINAL_PRICE: ASK and say what is missing.",
    ]
    return "\n".join(lines)


FORMULA = """
PRICE FORMULA (per unit, destination currency):
  goods cost G = (unit cost in CNY + freight per kg in CNY x weight in kg) / FX  +  duty
    EU <= EUR 150:  duty = EUR 3 x number of tariff categories in the parcel
    US:             duty = (unit cost in CNY / FX) x (HTS base rate + 12.5%)
  r = share of units returned and written off; fee = platform fee as a share of the gross price;
  vat = destination VAT rate (0 for the US); m = target margin on revenue excluding VAT.
  Price P = G x (1 + r) / ( 1/(1 + vat) - fee - m/(1 + vat) )
  Check: net revenue N = P/(1 + vat); profit = N - fee x P - G x (1 + r); margin = profit / N = m.
  If P is above EUR 150 for an EU parcel, the flat duty does not apply and this formula is not valid as written.
"""

SYSTEMS = {
    "plain": BASELINE_SYSTEM,
    "rules": BASELINE_SYSTEM + "\n\n" + rule_sheet(),
    "rules_formula": BASELINE_SYSTEM + "\n\n" + rule_sheet() + "\n" + FORMULA,
}


def run_prompted(system: str, prompt: str) -> str:
    llm = agent.client()
    r = llm.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "glm-4.5-air"),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt + SUFFIX}],
        temperature=0.2,
        **agent.provider_extras(),
    )
    return r.choices[0].message.content or ""


def run_case(c: dict) -> dict:
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=1 + len(SYSTEMS)) as ex:
        landed = ex.submit(_retry, run_landed, c["prompt"])
        others = {k: ex.submit(_retry, run_prompted, s, c["prompt"]) for k, s in SYSTEMS.items()}
        texts = {"landed": landed.result()[0], **{k: f.result() for k, f in others.items()}}
    row = {"id": c["id"], "kind": c["kind"], "secs": round(time.time() - t0, 1)}
    row.update({k: parse_final(t) for k, t in texts.items()})
    if c.get("truth"):
        truth = engine.landed_cost(engine.Inputs(**c["truth"]))["waterfall"]
        row["truth"] = truth["price"]
        if c["kind"] in PRICED_KINDS:
            row["truth_margin"] = c["truth"]["target_margin"]
            for who in texts:
                if isinstance(row[who], float):
                    row[f"{who}_realised_margin"] = round(margin_at(c["truth"], row[who]), 4)
    row["errors"] = [k for k, t in texts.items() if str(t).startswith("error:")]
    print(json.dumps(row, ensure_ascii=False), flush=True)
    row["texts"] = {k: t[-1500:] for k, t in texts.items()}
    return row


def score(rows: list[dict], who: str) -> dict:
    def correct(v, truth):
        return isinstance(v, float) and abs(v - truth) / truth <= 0.01

    priced = [r for r in rows if r["kind"] in PRICED_KINDS]
    # A failed API call is neither a guess nor an abstention: leave it out of must-not-guess.
    asky = [r for r in rows if r["kind"] not in PRICED_KINDS and r["kind"] != "us_lower_bound" and who not in r["errors"]]
    ok = [correct(r[who], r["truth"]) for r in priced]
    ape = sorted(abs(r[who] - r["truth"]) / r["truth"] if isinstance(r[who], float) else 1.0 for r in priced)
    under = [r for r in priced if isinstance(r[who], float) and r[who] < r["truth"] * 0.99]
    out = {
        "priced_ok": f"{sum(ok)}/{len(priced)}",
        "priced_ci95": wilson(sum(ok), len(priced)),
        "median_ape": round(ape[len(ape) // 2], 4) if ape else None,
        "asked_instead_of_guessing": f"{sum(not isinstance(r[who], float) for r in asky)}/{len(asky)}",
        "guessed_on": [r["id"] for r in asky if isinstance(r[who], float)],
        "underpriced": len(under),
        "sold_at_a_loss": sum(1 for r in priced if r.get(f"{who}_realised_margin", 1) < 0),
        "priced_misses": [r["id"] for r, k in zip(priced, ok) if not k],
        "api_errors": [r["id"] for r in rows if who in r["errors"]],
    }
    if who != "landed":
        l_ok = [correct(r["landed"], r["truth"]) for r in priced]
        out["mcnemar_p_vs_landed"] = mcnemar_exact(sum(a and not b for a, b in zip(l_ok, ok)),
                                                   sum(b and not a for a, b in zip(l_ok, ok)))
        l_err = [abs(r["landed"] - r["truth"]) / r["truth"] if isinstance(r["landed"], float) else 1.0 for r in priced]
        b_err = [abs(r[who] - r["truth"]) / r["truth"] if isinstance(r[who], float) else 1.0 for r in priced]
        try:
            out["wilcoxon_p_vs_landed"] = float(stats.wilcoxon(l_err, b_err).pvalue)
        except ValueError:
            out["wilcoxon_p_vs_landed"] = None
    return out


def main():
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))["cases"]
    rows = [run_case(c) for c in cases]
    report = {
        "model": os.environ.get("LLM_MODEL"), "thinking": os.environ.get("LLM_THINKING"), "n_cases": len(rows),
        **{who: score(rows, who) for who in ("landed", *SYSTEMS)},
    }
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"strong-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"report": report, "systems": SYSTEMS, "rows": rows}, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    print("\nREPORT", path.name, "\n" + json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
