"""Landed vs. the same LLM zero-shot without tools.

Usage:  .venv/Scripts/python -m eval.run_eval            (needs LLM_API_KEY in .env)

Both systems get the same suffix asking for a machine-readable last line, so the
comparison is fair. Reports: price accuracy within ±1% (Wilson 95% CI), McNemar
exact test on paired correctness, Wilcoxon signed-rank on absolute % error,
ask-vs-guess rate on ambiguous/missing cases, and Expected Margin Erosion Avoided.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from landed import agent, engine  # noqa: E402

SUFFIX = (
    "\n\nEnd your reply with exactly one final line: `FINAL_PRICE: <number>` (gross price in the destination "
    "currency, VAT included) or `FINAL_PRICE: ASK` if you need more information or cannot answer reliably."
)
BASELINE_SYSTEM = "You are a helpful assistant for cross-border e-commerce sellers."


def parse_final(text: str):
    m = re.search(r"FINAL_PRICE:\s*`?\s*(ASK|[\d.,]+)", text or "", re.I)
    if not m:
        return None
    v = m.group(1)
    if v.upper() == "ASK":
        return "ASK"
    try:
        return float(v.replace(",", ""))
    except ValueError:
        return None


PRICED_KINDS = ("clean", "bundle", "hs_unknown", "other_product")


def _retry(fn, *a):
    for attempt in range(2):
        try:
            return fn(*a)
        except Exception as e:  # network / rate limit: one retry, then record the failure
            if attempt:
                return ("", [f"error: {e}"]) if fn is run_landed else f"error: {e}"
            time.sleep(3)


def margin_at(truth_inputs: dict, price: float) -> float:
    """Margin the seller would actually earn at `price`, under the true rules."""
    p = engine.build_params(engine.Inputs(**truth_inputs))
    r = p.ret_alpha / (p.ret_alpha + p.ret_beta)
    net = price / (1 + p.vat)
    G = engine._goods_cost(p, p.fx_mean)
    return (net - p.fee * price - G * (1 + r)) / net


def run_landed(prompt: str) -> tuple[str, list]:
    events = list(agent.run([{"role": "user", "content": prompt + SUFFIX}]))
    answer = next((e["text"] for e in events if e["type"] == "answer"), "")
    calls = [e["name"] for e in events if e["type"] == "tool_call"]
    return answer, calls


def run_baseline(prompt: str) -> str:
    import os

    llm = agent.client()
    kw = agent.provider_extras()  # same setting as Landed: fair comparison
    r = llm.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "glm-4.5-air"),
        messages=[{"role": "system", "content": BASELINE_SYSTEM}, {"role": "user", "content": prompt + SUFFIX}],
        temperature=0.2,
        **kw,
    )
    return r.choices[0].message.content or ""


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def mcnemar_exact(b: int, c: int) -> float:
    """b = Landed right & baseline wrong, c = the reverse. Two-sided exact binomial."""
    n = b + c
    if n == 0:
        return 1.0
    return float(min(1.0, 2 * stats.binom.cdf(min(b, c), n, 0.5)))


def main():
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))["cases"]
    rows = []
    for c in cases:
        t0 = time.time()
        landed_text, calls = _retry(run_landed, c["prompt"])
        base_text = _retry(run_baseline, c["prompt"])
        row = {"id": c["id"], "kind": c["kind"], "landed": parse_final(landed_text), "baseline": parse_final(base_text),
               "landed_calls": calls, "secs": round(time.time() - t0, 1)}
        if c["kind"] in PRICED_KINDS:
            truth = engine.landed_cost(engine.Inputs(**c["truth"]))["waterfall"]
            row["truth"] = truth["price"]
            row["truth_margin"] = c["truth"]["target_margin"]
            for who in ("landed", "baseline"):
                if isinstance(row[who], float):
                    row[f"{who}_realised_margin"] = round(margin_at(c["truth"], row[who]), 4)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        row["landed_text"] = landed_text[-1500:]
        row["baseline_text"] = base_text[-1500:]
        rows.append(row)

    def correct(v, truth):
        return isinstance(v, float) and abs(v - truth) / truth <= 0.01

    clean = [r for r in rows if r["kind"] in PRICED_KINDS]
    asky = [r for r in rows if r["kind"] not in PRICED_KINDS]
    l_ok = [correct(r["landed"], r["truth"]) for r in clean]
    b_ok = [correct(r["baseline"], r["truth"]) for r in clean]
    b = sum(1 for x, y in zip(l_ok, b_ok) if x and not y)
    cc = sum(1 for x, y in zip(l_ok, b_ok) if y and not x)

    def ape(v, truth):
        return abs(v - truth) / truth if isinstance(v, float) else 1.0  # no price = 100% error

    l_err = [ape(r["landed"], r["truth"]) for r in clean]
    b_err = [ape(r["baseline"], r["truth"]) for r in clean]
    try:
        wil_p = float(stats.wilcoxon(l_err, b_err).pvalue)
    except ValueError:
        wil_p = None

    # Expected Margin Erosion Avoided: margin points lost per unit if the seller used
    # the baseline price instead of the rule-correct price (price below truth erodes margin).
    erosion = []        # EUR per unit left on the table / lost by underpricing
    margin_gap = []     # target margin minus margin actually earned at the baseline price (pp)
    for r in clean:
        if isinstance(r["baseline"], float) and r["baseline"] < r["truth"]:
            erosion.append(r["truth"] - r["baseline"])
            margin_gap.append((r["truth_margin"] - r["baseline_realised_margin"]) * 100)

    # Ask-vs-guess, scored identically for both systems: a "guess" means committing to a
    # numeric FINAL_PRICE. Asking in prose, showing a question card, or declining all count
    # as not guessing (Landed's cards often end the turn without the FINAL_PRICE line).
    l_ask = [not isinstance(r["landed"], float) for r in asky]
    b_ask = [not isinstance(r["baseline"], float) for r in asky]
    report = {
        "n_clean": len(clean),
        "landed_accuracy": sum(l_ok) / max(1, len(clean)),
        "landed_accuracy_ci95": wilson(sum(l_ok), len(clean)),
        "baseline_accuracy": sum(b_ok) / max(1, len(clean)),
        "baseline_accuracy_ci95": wilson(sum(b_ok), len(clean)),
        "mcnemar_p": mcnemar_exact(b, cc),
        "wilcoxon_p_abs_pct_error": wil_p,
        "landed_median_ape": sorted(l_err)[len(l_err) // 2] if l_err else None,
        "baseline_median_ape": sorted(b_err)[len(b_err) // 2] if b_err else None,
        "n_ask_cases": len(asky),
        "landed_ask_rate": sum(l_ask) / max(1, len(asky)),
        "baseline_ask_rate": sum(b_ask) / max(1, len(asky)),
        "ask_mcnemar_p": mcnemar_exact(
            sum(1 for x, y in zip(l_ask, b_ask) if x and not y), sum(1 for x, y in zip(l_ask, b_ask) if y and not x)
        ),
        "emea_mean_eur_per_unit": round(sum(erosion) / len(erosion), 2) if erosion else 0.0,
        "emea_cases_underpriced": len(erosion),
        "emea_mean_margin_points_lost": round(sum(margin_gap) / len(margin_gap), 1) if margin_gap else 0.0,
        "baseline_cases_with_negative_margin": sum(1 for r in clean if r.get("baseline_realised_margin", 1) < 0),
        "by_kind": {
            k: {
                "n": sum(1 for r in rows if r["kind"] == k),
                "landed_ok": sum(1 for r in rows if r["kind"] == k and (
                    correct(r["landed"], r["truth"]) if k in PRICED_KINDS else not isinstance(r["landed"], float))),
                "baseline_ok": sum(1 for r in rows if r["kind"] == k and (
                    correct(r["baseline"], r["truth"]) if k in PRICED_KINDS else not isinstance(r["baseline"], float))),
            }
            for k in ("clean", "bundle", "hs_unknown", "other_product", "missing", "above_150", "us_needs_hs", "out_of_scope")
        },
        "model": os.environ.get("LLM_MODEL"),
        "thinking": os.environ.get("LLM_THINKING"),
    }
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"run-{stamp}.json").write_text(json.dumps({"report": report, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nREPORT\n" + json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
