# Backtest: price check, 27-country EU comparison, saved-product re-pricing

**Run:** 2026-11-19. Chat cases use the deployed model, `deepseek/deepseek-v4.1-flash` via OpenRouter (thinking disabled). Everything else is deterministic and uses no model.

## What was added

| Feature | Where | What it answers |
|---|---|---|
| Price check (reverse mode) | `engine.price_check`, `/api/price-check`, chat tool `price_check`, result panel | "It sells for €29.99. Do I make money, and how much can I pay the factory?" |
| EU comparison | `engine.compare_eu`, `/api/compare-eu`, chat tool `compare_eu`, result panel | "Which EU country makes the most on this product?" |
| Saved-product re-pricing | `engine.review_saved`, `GET /api/products/review`, `PUT /api/products/{id}`, welcome-screen dashboard | "Rates moved since I saved this. What is my margin now, and what should I charge?" |

As before, the model never computes a figure: every number comes from the engine, and the chat model copies pre-formatted strings.

## Results

| Suite | Cases | Result | Defects found, all fixed |
|---|---|---|---|
| Engine property and fuzz (`tests/test_backtest_new.py`) | 685 | all pass | 3: extreme inputs (fx 1e308, 5e-324, freight × weight overflow) returned `inf` or a 500, and a `NaN`/`Infinity` list price crashed the 422 error response. Fixed with input ceilings in `build_params`; list-price range checks moved from pydantic into the engine. |
| Saved-product review (`tests/test_backtest_saved.py`) | 87 | all pass | 2: a malformed rate entry in a stored baseline, and non-dict `inputs`/`overrides`, made the whole review return 500. Fixed with type guards, and each product is now reviewed in isolation. |
| Unit tests for the new features (`test_reverse_compare.py`, `test_saved_review.py`, `test_agent.py`) | 42 | all pass | – |
| **Full test suite** | **1,292** | **all pass** | |
| Browser end to end (Chrome, scripted) | 7 scenarios | all pass, no page errors | none |
| Simulated sellers, live chat (`eval/run_new_tools.py`) | 60 | **59/60 first run; 60/60 after the fixes** | 1 wrong answer + 1 wording slip: below |
| Headline eval, regression check (`eval/run_eval.py`) | 36 | 26/26 priced, 9/9 asked or declined, u02 1/1 | no regression from this change |

### Simulated sellers (60 cases, Chinese and English, messy units, multi-turn)

| Category | Cases | Pass |
|---|---|---|
| A. Price check: stated price, "can I make money?" | 25 | 25 |
| B. EU comparison: "which country is best", named countries | 15 | 14 → 15 after the fixes |
| C. Must not guess: missing inputs, non-EU/US market, above €150, no price given | 12 | 12 |
| D. Ordinary pricing still uses `landed_cost` | 8 | 8 |

Mean 5.7 s per case. Scoring is programmatic: the right tool, arguments equal to the seller's numbers, quoted figures equal to the tool's display strings, no guardrail warning, and abstaining where required.

**The one miss (B13).** "Compare Sweden, Denmark and Finland." The tool showed the model only the top three, the worst and the seller's own country, so the model gave Finland Sweden's figures and 25% VAT. Finland's VAT is 25.5%. The guardrail could not catch it, because those numbers did appear in the tool output, just for Sweden. **Fix:** the tool now gives every country its own line, and the model is told to use the named countries' own lines. Re-run live: Finland is correctly shown as the weakest of the three, at €4.46 per unit (24.7%). Regression test: `test_compare_eu_display_lists_every_country_with_its_own_vat`.

**A wording slip found with it.** When a seller only listed countries to compare, the answer called the first one "your country" (你的国家). The first fix to the prompt made the model ask which country was the seller's instead of comparing, which was worse, so the rule now says: compare at once, using the first named country as the reference, and never call a named country "theirs" unless the seller said so. Checked live on four comparisons, in Chinese and English.

**The scorer was too lenient, and is now strict.** The subagent that wrote it first reported 60/60, because it only checked that the best country was named correctly. It now also checks that every figure on a line naming one country is that country's own (`misattributed_figures`), and when the seller names countries, it accepts the best of those as well as the best overall. Re-scored, the first run is 59/60 (B13 fails, correctly). A full re-run after the fixes scored 60/60 (`new-tools-20261119-231038.json`); I read the answers to confirm it.

### Headline eval (36 cases)

- **Priced: 26/26 within ±1%**, the same as every earlier run. The baseline (same model, no tools) got 0/26.
- **Asked or declined: 9/9.**
- **u02, US socks with no HTS line loaded: 1/1.** The system prompt has said since before this change to always price the US, as a labelled lower bound. The case still expected a question, so it now has its own kind, `us_lower_bound`: asking passes, and so does the engine's exact lower bound if the answer calls it one. Landed gave $6.27, labelled, with the $6.50 / $7.04 range in case the older tariffs apply. The baseline's unlabelled $5.89 fails. This moves u02 out of the ask cases, so earlier reports' "10 ask cases" are 9 from now on.
- One case (x01) took 889 s because of a slow provider response. Its answer was correct.

## Also fixed after the backtest

- Typing a zero or negative price in the price-check box now shows "Enter a positive price" instead of an empty panel.
- `/api/price-check` no longer accepts `list_price: true` (it was read as €1).

## Caveats

- Each chat suite was run once. The 60 seller cases were written for this backtest, not collected from real sellers.
- Saved-product re-pricing is only as fresh as `data/rates.csv`. FX is refreshed manually (`scripts/refresh_fx.py`), so a seller sees "changed" only after a refresh is deployed.
- Price check uses the same placeholders as the main price (freight ¥45/kg, generic return rate, 15% fee when no platform is chosen) unless the seller enters their own.
