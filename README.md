# 到岸 Landed

Cross-border landed-cost and localization agent (第二届全国人工智能应用创新大赛 · 出海).

The LLM handles language: reading the product description, choosing tools, asking the one clarifying question and writing the listing. **Every number comes from deterministic Python** reading hand-verified tables, and every figure carries a source URL, snapshot date and status.

**Ask only what changes the money.** Below €150 the EU duty is €3 per *kind* of item in a parcel, whatever the HS code, so an EU price (any of the 27 countries, each with its own VAT rate) for any product needs only unit cost, weight, market and target margin. The agent asks for those four and nothing else, and code enforces it: the input form is trimmed to the required fields that are really missing. The HS question appears only where the code changes money (US duty, orders above €150, the declaration itself). Because the duty is per kind, not per unit, the engine also shows when a multipack of the same item would cut the price per unit.

## Layout

| Path | What |
|---|---|
| `data/` | `rates.csv` (duty, VAT, FX, fees, each with `source_url`, `snapshot_date`, `status`), `hs_tree.json` (HS candidates + discriminating attributes), `compliance.json` |
| `landed/engine.py` | Cost waterfall, 5,000-path NumPy Monte Carlo, stress table, GRI 3(b) bundle tip |
| `landed/hs.py` | HS disambiguation; next question chosen by minimum expected entropy |
| `landed/tools.py` | The 4 whitelisted tools the LLM may call |
| `landed/agent.py` | Agent loop (≤ 6 tool rounds), trace log in `logs/trace.jsonl` |
| `landed/guardrail.py` | Flags any money/percentage, product spec (W, ml, mAh…) or certification claim (CE-certified, BPA-free…) in the answer not found in a tool result or the seller's message; the agent gets one rewrite pass before flags reach the UI |
| `api/main.py` | FastAPI: `POST /api/chat` (SSE), `POST /api/calc`, `POST /api/classify`, `GET /api/sources`; serves `dist/` |
| `src/` | Landing page (Vite). `src/lib/engine.js` mirrors the Python engine for the in-page cost card |
| `api/accounts.py` | Sign-in-to-save: users, sessions, seller profile, saved products |
| `landed/profile.py` | The seller profile: niches, what each answer maps to, validation |
| `src/agent/onboarding.js` | The full-screen onboarding and its reveal screen |
| `src/agent/personal.js` | Welcome screen, sign-in dialog, saved products |
| `tests/` | pytest: engine, HS, compliance, guardrail, agent loop (fake LLM), accounts |
| `eval/` | Landed vs. the same LLM without tools: accuracy + Wilson CI, McNemar, Wilcoxon, ask-vs-guess, EMEA |

## Personalisation and accounts

A first visit to `/agent` opens a full-screen onboarding before the workspace: one question per screen with visual cards, a live seller profile that fills in as you answer, and a last screen that prices a typical product from your niche with your answers. Seven questions: category, niche, market and platform, parcel type, typical unit cost, what worries you, target margin and (optionally) your own fee, freight, return rate and FX. Skippable, stored in the browser, no account needed.

Every answer changes something real (`landed/profile.py`):

| Answer | What it changes |
|---|---|
| niche | the compliance checks that run by default (apparel: fibre labels; skincare: cosmetics responsible person and CPNP; toys: toy safety; audio: battery, CE, WEEE; kitchenware: food contact) and the example product |
| market, margin, own fee / freight / returns / FX | applied to the pricing call in code (`agent.apply_profile`); the seller then only gives cost and weight |
| parcel type | how mixed parcels, multipacks and the extra-€3 warning are treated |
| unit cost band | the product the onboarding prices, and an early warning if prices will exceed the €150 flat-duty ceiling |
| worries | which panels and stress rows the workspace puts first (e.g. compliance moves the checklist under the price) |
| platform | the platforms of the chosen country (Amazon, Kaufland, eBay, TikTok Shop, Temu, SHEIN, OTTO, bol.com, Allegro, Cdiscount, Walmart, Etsy, own store) and, where a source was found, that platform's commission (by category) and any per-order fee as the default fee. These are third-party figures marked `secondary` and linked, not the platforms' own pages; where nothing was found the 15% placeholder is used and flagged. A fee the seller types always wins. FBA, ads, subscriptions and payment fees are not modelled (`data/platforms.json`) |

**Sign in to save** adds settings that follow the seller across devices and saved products (`api/accounts.py`: SQLite, scrypt password hashes, httpOnly session cookie, consent checkbox, `DELETE /api/me` erases everything). Set `LANDED_DB` to put the database on a persistent volume (the Dockerfile uses `/app/db`). This is a prototype privacy notice, not legal advice: have it reviewed before collecting real users' data in China (PIPL).

## Models

Any OpenAI-compatible provider works; set `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` in `.env`. Evaluated: `glm-4.5-air` (Zhipu), `deepseek/deepseek-v4.1-flash` and `nvidia/nemotron-3.5-super-vl:free` through OpenRouter (see `eval/RESULTS.md`). Recommended: DeepSeek V4.1 Flash with `LLM_FALLBACK_MODEL` set to a second model, which is used automatically if the first is rate-limited, out of credit or down. If a key is rejected or out of quota the chat says so plainly and the calculator keeps working. OpenRouter may not be reachable from mainland China, so test from there before relying on it.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows; use .venv/bin/pip on Linux/macOS
cp .env.example .env                              # add your key (GLM, or OpenRouter + DeepSeek)
npm install && npm run build

.venv/Scripts/python -m uvicorn api.main:app --port 8000
# open http://localhost:8000
```

For front-end work, run `npm run dev` alongside uvicorn; Vite proxies `/api` to port 8000.

## Test and evaluate

```bash
.venv/Scripts/python -m pytest -q tests
.venv/Scripts/python -m eval.run_eval              # calls the model in .env; results in eval/results/
```

## Deploy (one container)

```bash
docker build -t landed .
docker run -d -p 80:8000 --env-file .env -v landed-db:/app/db --restart unless-stopped landed
```

Recommended host: a small Hong Kong-region VPS (no ICP filing needed, reachable from the mainland). Test the link from a mainland network before submitting.

## What is covered, and what is not

- **EU, 27 countries:** each with its own standard VAT rate (all 27 match the European Commission's table, `verified`), the EUR 3 flat duty per kind of item below EUR 150, and EU-wide compliance checks including the packaging producer registration required since 12 Aug 2026 (PPWR, `secondary`). Listings are written in the destination country's language and checked for invented claims in nine languages.
- **United States:** the blender family only, with the verified 12.5% China Section 301 duty. The older Section 301 list duty (7.5% or 25%) is not loaded because sources disagree, so US prices are labelled as a floor.
- **Not covered:** national packaging and electrical registration rules beyond the ones named in the checklist, platform fees for OTTO, bol.com, Allegro and Cdiscount, FBA/ads/subscriptions, products outside the blender family above EUR 150, and every market other than the EU and US.

## Default assumptions

The fields a seller can overwrite start from sourced figures, not made-up ones: FX is the ECB euro reference rate (USD/CNY is the ECB cross rate) with a volatility computed from ECB history; freight is a forwarder-published range, `secondary`; the return rate defaults by category (electronics about 8%, fashion about 25%, `secondary`); the platform fee is that platform's sourced commission. Only the generic 15% fee for an unknown platform is still a flagged placeholder. FX is a snapshot (6 Nov 2026). Refresh it with `python scripts/refresh_fx.py` (add `--dry-run` to preview; then `npm run build`): it reads the ECB reference rates and updates `data/rates.csv` and the copies in `src/`. The tests pin FX, so a refresh does not break them.

## Data status

`verified` = read from the official source on the snapshot date · `secondary` = reputable secondary source, confirm on the primary · `assumption` = a placeholder the seller replaces · `unknown` = not loaded; the engine abstains.

Decision support only, not licensed customs brokerage.
