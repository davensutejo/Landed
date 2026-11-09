# Evaluation results: Landed vs. the same LLM without tools

**Run:** 2026-11-08 · `eval/results/run-20261108-165227.json` · model `glm-4.5-air` (thinking disabled) for **both** systems · 36 cases, one run each. This run uses the submitted code (see "Development history" for earlier runs and how the case set changed).

## What the eval checks

A seller needs two things from a pricing agent: a correct price whenever one can be given, and no made-up price when it cannot. Under the EU's €3 regime (from 1 Jul 2026) the duty on a parcel below €150 is €3 per *kind* of item, whatever the HS code. So:

- **Priced cases (26):** the agent must return the rule-correct price within ±1%. This includes 5 German cases where the HS code is unknown or ambiguous and 3 products outside the blender family (socks, a phone case, a desk lamp). Asking about the HS code instead of pricing counts as a miss here, because the code does not change the price.
- **Must-not-guess cases (10):** a price cannot honestly be given (inputs missing, a price above €150 where the exact code's conventional duty is not verified, a US price without a confirmed code, an unsupported market). Committing to a number counts as a guess.

| | Landed | Baseline |
|---|---|---|
| Model | glm-4.5-air | glm-4.5-air (same) |
| Tools | landed_cost, compliance_flags, classify_hs, ask_seller + market scope check + input guard + form gate + numeric/claim guardrail | none |
| Prompt | Landed system prompt | "helpful assistant for cross-border sellers" |

Both receive the identical user prompt plus the same instruction to end with `FINAL_PRICE: <number>` or `FINAL_PRICE: ASK`.

**Fairness:** every priced case states the commercial assumptions in the prompt (platform fee, freight per kg, return rate, FX, margin definition), so the baseline is not penalised for not knowing Landed's demo values. What the baseline still has to supply is what a seller lacks: the destination rules (€3 per tariff category below €150, German VAT 19%) and correct arithmetic.

**Ground truth** = those sourced rules applied by `landed/engine.py`, the same engine Landed calls. On priced cases the eval therefore measures whether a seller gets the rule-correct price, not whether the engine itself is right; the engine is checked separately by unit tests (`tests/`).

## Results

### Pricing (26 cases)

| Metric | Landed | Baseline |
|---|---|---|
| Price within ±1% of rule-correct price | **26/26 (100%)**, 95% Wilson CI [87.1%, 100%] | **0/26 (0%)**, CI [0%, 12.9%] |
| … blender family, HS confirmed (15 clean + 3 bundles) | 18/18 | 0/18 |
| … Germany, HS code unknown or ambiguous | 5/5 | 0/5 |
| … other products (socks, phone case, desk lamp) | 3/3 | 0/3 |
| Median absolute % price error | 0.0% | 43.8% |
| McNemar exact test (paired correctness) | p = 3.0 × 10⁻⁸ | |
| Wilcoxon signed-rank (absolute % error) | p = 3.0 × 10⁻⁸ | |

### Margin erosion avoided (what the baseline's price would cost a seller)

- The baseline under-priced **26/26** cases, by **€11.57 per unit** on average.
- At the baseline's price, the seller would earn on average **41.0 margin points below target**.
- **19/26** baseline prices would sell **at a loss**.

Examples on products outside the blender family: cotton socks 5-pack, rule-correct €13.08, baseline €6.33; phone case, €9.00 vs €3.39.

### Must not guess (10 cases; 8 scored for both)

The GLM account ran out of credit during the last two cases (HTTP 429 "余额不足"). Case u02 (socks, US) failed for both systems, and the baseline's o02 (Brazil) failed. The runner counts a failed call as "did not guess", which would flatter both, so those are excluded from the paired comparison below. Landed's o02 answer is valid: unsupported markets get a fixed reply without calling the model.

| | Landed | Baseline |
|---|---|---|
| Did not guess (8 paired cases: m01–m05, x01, x02, u01) | **8/8** | 5/8 |
| Also valid for Landed only | o02 Brazil: declined | (API error) |
| McNemar exact | p = 0.25 (**not significant** at n = 8) | |

Baseline guesses: a portable blender with no weight or margin given (it invented ¥15 shipping and a 30% margin and answered 80, a yuan figure), an electric scooter whose price is above €150 (€440.64), and a restaurant blender above €150 (€202.66). Landed showed an input form for the five missing-input cases, explained the €150 ceiling and abstained on x01/x02, and showed the HS question card for the US blender.

### Why the baseline misprices (pattern counts over its 26 priced answers)

- Mentions German VAT at 19%: 21/26. So it is not an uninformed model.
- Mentions the EU €3-per-category flat duty: **0/26**. It does not know the July 2026 rule. Most answers leave duty out entirely; 3 set it to 0% and 4 apply a percentage rate.

## Other models (OpenRouter, run after the headline run)

The headline run above used GLM directly. The GLM account later ran out of credit, so the same 36 cases were run through OpenRouter on two other models. Same cases, same runner, one run each; the model-free baseline is the same model without tools in each run.

| | Nemotron 3.5 super (free) | DeepSeek V4.1 Flash |
|---|---|---|
| Result file | `run-20261108-220806` | `run-20261108-232236` |
| Reasoning | off | off |
| Price within ±1% (26 priced cases) | **26/26** | **26/26** |
| Baseline, same model without tools | 0/26 | 0/26 |
| Asked instead of guessing (10 cases) | 9/10 | **10/10** |
| Mean seconds per case | 12.0 | 9.0 |

- **Pricing is model-independent**, as designed: the price comes from `landed/engine.py`, and the model only has to call the tool with the seller's inputs.
- **Nemotron's one miss (m03)** is a real defect that this run exposed: the model passed "0.6 kg" as a unit cost of 0.6 CNY and priced a blender at €15.02. It was fixed afterwards by checking that the cost the agent passes is a cost the seller stated (`input_guard`, with a test). The Nemotron run predates that fix, DeepSeek's run followed it. DeepSeek asked correctly on its own in a manual check before the fix.
- **These runs include u02 and o02**, which the GLM run lost to its empty balance, so caveat 4 below no longer blocks them.
- `z-ai/glm-5.3-flash` was also started. It requires reasoning, which made single cases take 1 to 5 minutes, so it was not used and its run is not reported.
- The deployed default is `deepseek/deepseek-v4.1-flash`, with the free Nemotron model as an automatic fallback when the main model is rate-limited or unavailable.

*Note on later changes:* after these runs the FX default moved from a rounded 7.5 to the ECB reference rate 7.4485 and fashion gained its own return-rate default, so today's rule-correct prices differ from the stored ones by about 0.4% (e.g. the 38 CNY blender in Germany: 26.24 then, 26.37 now). Pricing accuracy is scored against the engine of the same moment, so the result files stay internally consistent.

## Caveats (say these before a judge does)

1. **Small n, one run.** 36 cases, one sample each at temperature 0.2. The pricing gap is decisive (p < 10⁻⁷). The must-not-guess difference is directionally favourable but not significant, and the baseline's rate varies between runs.
2. **Ground truth comes from Landed's own rules.** Appropriate, since the rules are sourced and a broker would apply the same ones, but the eval does not test whether the rules are right. The source table and unit tests cover that.
3. **One destination for pricing** (Germany, below €150). US prices need a confirmed code in the blender family and now include the 12.5% China Section 301 duty (CBP notice, verified) only; the older Section 301 list duty (7.5% or 25%, by list) is not loaded because sources disagree on which list this HTS line is on, so US prices are labelled as a floor. They are not in the priced set.
4. **Two cases lost to the API balance** in the GLM run (see above). Both were scored in the OpenRouter runs.
5. **Development history, disclosed.** Every run is kept in `eval/results/`.
   - `run-20261108-132140`, `132905`: the first version required a confirmed HS code before any price and scored "asking about the code" as correct. The first run exposed an assumed market/margin (m04) and a German price for a Brazil request (o02); fixed with a code-level input guard.
   - `154455`, `155457`, `161318`: after live testing fixed invented listing claims, the market bypass and US labelling. These runs exposed an out-of-category product receiving the blender question card and the floor price reported as the final answer; both fixed. Pricing 18/18 vs 0/18 in four of the five runs on the old case set, 17/18 in one.
   - **Then the case set changed, deliberately.** Testing as a seller showed the agent asking about motors and heating before pricing products whose German price does not depend on the answer (and declining socks entirely). The €3 rule is per kind of item, not per code, so the agent now prices any German order below €150 without asking about the code, and the five "ambiguous HS" cases became priced cases (with the commercial assumptions added to their prompts so the baseline is treated fairly). Three non-blender products, two above-€150 cases and two US cases were added. `run-20261108-165227` (this report) is the first run on the new set.
6. Same base model for both systems, so the comparison isolates what the system design adds. A frontier model without tools, or the same model given the rules in its prompt, would be useful further baselines.

Reproduce: `python -m eval.build_cases && python -m eval.run_eval`

## Wide backtest (9 Nov 2026)

**Offline, no LLM** (`tests/test_backtest.py`, `tests/test_api_backtest.py`; 395 tests in total). An independent
closed-form re-implementation of the price formula is compared with the engine over all 27 EU countries x costs x
weights x margins x platforms x return rates (every price within EUR 0.006), plus the US. Properties checked: selling at the
price earns exactly the target margin, the waterfall sums to the price, price rises with cost/weight/margin/fee/returns,
the EUR 150 regime switch refuses instead of guessing, Monte Carlo is seeded and sane, the risk curve is monotone, every
number carries a status, a snapshot date and (when verified or secondary) a source URL, 600 random and extreme inputs never
give NaN, infinity or a negative price, and 23 hostile API inputs never give a 500. The backtest found real gaps (return
rate above 100%, zero or negative FX, NaN, zero or negative category counts were accepted) and they are now rejected.

**Agent, live** (`python -m eval.run_wide`, deepseek/deepseek-v4.1-flash, 99 generated cases, one run): 99/99. Priced
cases within 1% of the engine: 54 EU (27 countries x English and Chinese), 6 bundles, 6 US, 3 prompt-injection,
10 messy phrasings (grams, 块, typos, comma decimals). Must not guess: 8 missing inputs, 4 above EUR 150, 2 US without a
code, 6 unsupported markets. One run per case; the model is stochastic, so rerun before quoting a rate.

## Realistic-seller backtest (9 Nov 2026)

`python -m eval.run_real` (deepseek/deepseek-v4.1-flash): 171 cases written the way sellers type, with no stated fee, freight,
FX or return assumptions. Single-turn pricing in English and Chinese across 20 EU markets (90 cases, plus two more random
seeds of 90, 270 in all: 270/270 priced correctly), 12 two-turn conversations, 10 follow-up what-ifs, 12 compliance questions
scored against the exact rules returned, 9 listing requests, 10 platform-named prompts (10/10), and 30 messy or hostile
inputs (injection, missing data, units, bundles, multiple SKUs). Scoring is programmatic: the agent must call the engine with
exactly the seller's numbers and show the engine's price.

Real defects found and fixed: "cost is 70" was not recognised as a cost, so the agent asked again; a named platform was ignored
and the generic fee used; "certification" and a bracketed placeholder were flagged as unsourced claims; and a US price with no
HS code was refused outright. A US price is now an indicative lower bound: a likely HS line is assumed from the product wording
(base duties read from the USITC schedule, verified), the 12.5% China Section 301 duty is added, and the result is labelled.
Where no line can be assumed, the base duty is shown as not loaded.

## Naive-user rounds (9 Nov 2026)

Three fresh agents with no knowledge of the code used the site in a real browser as first-time sellers (Chinese and English UI,
desktop and phone, with and without onboarding). They found, and these were fixed and re-checked: the chat and the side panel
showing different prices for one product, a typo'd country ("germny") breaking a follow-up, tool-call text leaking into the chat,
a misleading "AI unavailable" message on rate limiting, a niche's compliance rules applied to a different product, VAT/legal
questions answered with a pricing form, silent rejection of invalid numbers, the US button disabled while the chat priced the
US, the result lost on reload, and unexplained compliance jargon. Not fixed: onboarding length, landing-page tone, and the
platform-fee sources that are still secondary. Regression run after the fixes: 171/174 on the realistic suite; the misses were two scorer artifacts (a correct refusal that quotes the
words it refuses to use) and one listing where the guardrail correctly caught an invented "antibacterial" claim.
