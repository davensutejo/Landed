# 到岸 Landed — The Landed Price, Sourced.

> **Cross-Border Landed-Cost & Localization Agent**  
> **赛道分类 / Competition Track:** 第二届全国人工智能应用创新大赛 · 出海赛道 (The 2nd National AI Application Innovation Competition — Global Expansion Track)  
> **Core Value Proposition:** Sourced landed-cost calculation, 95% risk-buffered pricing, automated compliance pre-auditing, and localized listing generation for cross-border e-commerce sellers shipping from China to the EU and US.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vite](https://img.shields.io/badge/Frontend-Vite-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-395%20Passing-brightgreen?style=flat-square)](#test-and-evaluate)

---

## 💡 The Thesis: Rule Zero

> **"Numbers never come from the language model."**

Large language models excel at natural language understanding and multilingual generation, but struggle with deterministic customs arithmetic and non-hallucinated figures. On a benchmark of 200 binding U.S. customs rulings, frontier reasoning models identify the exact 10-digit tariff code only ~25% of the time. 

**Landed splits the responsibility cleanly:**
1. **The LLM** handles conversational intent, parses unstructured product descriptions, selects tools, and writes localized listing copy in the destination language.
2. **Deterministic Python Code** computes every rate, fee, VAT, currency conversion, duty waterfall, and Monte Carlo risk distribution from officially verified tables.
3. Every single number displayed carries a **source URL**, a **snapshot date**, and an explicit audit status: `verified`, `secondary`, or `assumption`.

---

## 🏛 Architecture & Data Flow

User requests flow seamlessly from the reactive frontend, through the FastAPI gateway and agent loop, into deterministic calculation engines, with strict anti-hallucination verification before anything reaches the seller.

### Architecture Workflow Diagram

```mermaid
flowchart TD
    classDef ui fill:#FAF6EC,stroke:#C9A24B,stroke-width:1.5px,color:#14110F;
    classDef agent fill:#FFF4E6,stroke:#E8643C,stroke-width:1.5px,color:#14110F;
    classDef engine fill:#E8F5E9,stroke:#2E7D32,stroke-width:1.5px,color:#14110F;
    classDef guard fill:#EDE7F6,stroke:#512DA8,stroke-width:1.5px,color:#14110F;

    User(["👤 Seller / User Input\n(Natural Language or Guided Onboarding)"]):::ui

    subgraph Frontend ["🖥 Frontend Interface (Vite / Vanilla JS)"]
        UI_Chat["Live SSE Chat Console & Dynamic Input Form"]:::ui
        UI_Card["Interactive Cost & Risk Waterfall\n(5,000 Monte Carlo Paths & Sliders)"]:::ui
        UI_Audit["Interactive Sourced Provenance Panel\n& Compliance Checklist"]:::ui
    end

    subgraph Gateway ["⚡ FastAPI Gateway (api/main.py)"]
        API_Route["/api/chat (SSE) · /api/calc · /api/compliance · /api/classify"]:::agent
        RateLimit["Rate Limiting & Scrypt Session Auth (api/accounts.py)"]:::agent
    end

    subgraph AgentLoop ["🤖 Localization & Routing Agent (landed/agent.py)"]
        IntentRouter["Language Detection & Input Guard\n(≤ 6 Bounded Tool Turns)"]:::agent
        LLM["LLM Router (DeepSeek V4.1 Flash / GLM-4.5-Air)\nAuto-Fallback on Rate Limit"]:::agent
        ToolDispatch["Whitelisted Tool Dispatcher (landed/tools.py)"]:::agent
    end

    subgraph DeterministicCore ["⚙️ Deterministic Calculation & Rules Core"]
        Engine["Tariff & Cost Waterfall Engine (landed/engine.py)\n• EU 27 VAT Rates & €3 Flat Duty Regime (≤ €150)\n• US Section 301 China Tariffs (12.5%)\n• 5,000-Path Monte Carlo Simulation (FX ~ N, Returns ~ Beta)"]:::engine
        HSEntropy["HS Code Disambiguation (landed/hs.py)\n• Min-Expected Entropy Question Selection"]:::engine
        ECBSync["Multi-Currency Sync (scripts/refresh_fx.py)\n• Daily ECB Reference Rates & 60-Day Volatility"]:::engine
        ComplianceRules["Compliance Knowledge Base (data/compliance.json)\n• GPSR, PPWR Packaging, WEEE, UN 3481 Batteries"]:::engine
    end

    subgraph PostAudit ["🛡 Anti-Hallucination Guardrail (landed/guardrail.py)"]
        GuardAudit{"Pre-Auditing Scanner\n• Numeric match against tool outputs\n• Spec & cert check (CE, RoHS, BPA-free)"}:::guard
        Rewrite["Automated Single-Pass Rewrite\n(if ungrounded claims detected)"]:::guard
    end

    %% Flow connections
    User --> Frontend
    Frontend -->|HTTP / SSE Stream| Gateway
    Gateway --> AgentLoop
    IntentRouter --> LLM
    LLM -->|Tool Calls| ToolDispatch
    ToolDispatch --> Engine
    ToolDispatch --> HSEntropy
    ToolDispatch --> ComplianceRules
    ECBSync -.->|Daily Updates| Engine

    Engine --> ToolDispatch
    HSEntropy --> ToolDispatch
    ComplianceRules --> ToolDispatch

    ToolDispatch -->|Raw Results| LLM
    LLM -->|Draft Response| GuardAudit
    GuardAudit -- "Pass (Grounded)" --> UI_Chat
    GuardAudit -- "Violation Detected" --> Rewrite
    Rewrite --> UI_Chat

    Engine -->|Direct Calculation| UI_Card
    ComplianceRules -->|Rule Flags| UI_Audit
```

### High-Level ASCII Workflow

```text
+-----------------------------------------------------------------------------------------+
|                                1. SELLER INPUT                                          |
|  "500ml portable blender with battery, ¥38 cost, 0.6kg, shipping to Germany (25% margin)"|
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                         2. AGENT LOOP & ROUTING (FastAPI + LLM)                         |
|  - Language Detection (Chinese/English) & Input Guard (check for cost, weight, market)   |
|  - "Ask only what changes the money": Below €150 EU duty is flat €3/category            |
|    -> Skips irrelevant questions (no need to ask about motor specs before pricing)      |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                     3. DETERMINISTIC ENGINE & PROVENANCE TABLES                         |
|  - Landed Cost Waterfall: COGS + Sourced Freight + Flat EU Duty (€3) + VAT (19% DE)     |
|  - Risk Engine: 5,000 NumPy Monte Carlo paths (ECB FX volatility + Beta returns)        |
|  - Compliance Pre-Audit: UN 3481 Li-ion packing (PI 967), Food contact, PPWR register   |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                  4. POST-GENERATION GUARDRAIL (Zero-Hallucination)                      |
|  - Scans draft answer across 9 languages for unverified numbers or fake specs           |
|  - Rejects unverified claims (e.g. "CE-certified", "BPA-free") -> 1-pass auto rewrite   |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                           5. REACTIVE FRONTEND DELIVERY                                 |
|  - Real-time SSE streaming answer with recommended price & risk-buffered floor price    |
|  - Interactive live SVG waterfall, Monte Carlo margin histogram, and provenance audit   |
+-----------------------------------------------------------------------------------------+
```

---

## ⚡ Quick Start Guide (Under 2 Minutes)

Get the full application running locally with copy-pasteable terminal commands.

### Prerequisites
- **Python 3.11+** installed
- **Node.js 18+** & `npm` installed
- An API key from any OpenAI-compatible provider (e.g., [Zhipu GLM](https://open.bigmodel.cn/) or [OpenRouter](https://openrouter.ai/))

---

### Step-by-Step Setup

#### 1. Clone the repository
```bash
git clone https://github.com/davensutejo/Landed.git
cd Landed
```

#### 2. Configure Python environment & install dependencies
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment:
# On Windows:
.venv\Scripts\activate
# On Linux / macOS:
# source .venv/bin/activate

# Install Python requirements
pip install -r requirements.txt
```

#### 3. Set up environment variables
```bash
# Copy template configuration
cp .env.example .env
```
Open `.env` in your editor and insert your LLM API key. Recommended options:
- **Option A (China Direct - Zhipu GLM):**
  ```env
  LLM_API_KEY=your_glm_api_key_here
  LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
  LLM_MODEL=glm-4.5-air
  LLM_THINKING=disabled
  ```
- **Option B (Global - OpenRouter with DeepSeek & Auto-Fallback):**
  ```env
  LLM_API_KEY=your_openrouter_key_here
  LLM_BASE_URL=https://openrouter.ai/api/v1
  LLM_MODEL=deepseek/deepseek-v4.1-flash
  LLM_FALLBACK_MODEL=nvidia/nemotron-3.5-super-vl:free
  LLM_THINKING=disabled
  ```

#### 4. Install frontend packages & build assets
```bash
npm install
npm run build
```

#### 5. Launch the application
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser!

> 💡 **For Frontend Development with Hot Reload:** Run `npm run dev` in a separate terminal. Vite will serve on `http://localhost:5173` and automatically proxy backend API requests to port `8000`.

---

### Alternative: Run with Docker in 30 Seconds

If you have Docker installed, launch the entire application with persistent volume storage in a single command:

```bash
# Build and run container
docker compose up -d --build

# View logs
docker compose logs -f
```
Open **[http://localhost:8000](http://localhost:8000)**.

---

## 🏰 Competitive Moats

Landed is engineered from first principles as an auditable compliance and pricing copilot, fundamentally different from fragile prompt-wrapper chatbots:

### 1. Automated Compliance Pre-Auditing & Zero-Hallucination Guardrail
- **Proactive Customs Compliance:** Immediately evaluates product attributes against destination regulatory frameworks:
  - **EU GPSR & PPWR:** Flags EU-wide packaging producer registration obligations required since August 2026.
  - **Battery & Safety Regulations:** Flags IATA Packing Instruction 967 / UN 3481 for equipment containing lithium-ion cells.
  - **Food-Contact & WEEE Directives:** Automatically injects declaration requirements for kitchenware and electronics.
- **Anti-Hallucination Regex & Audit Engine (`landed/guardrail.py`):**
  - Scans generated listings and explanations across **9 European destination languages**.
  - Any number, percentage, physical specification (W, mAh, ml), or regulatory certification claim (`CE`, `RoHS`, `BPA-free`, `TÜV`) not present in tool output or user prompt is intercepted.
  - The agent triggers an **automated one-turn internal rewrite** before invalid claims can reach the seller.

### 2. Multi-Currency Real-Time Synchronization & Empirical Volatility
- **Daily ECB Reference Rate Ingestion (`scripts/refresh_fx.py`):**
  - Synchronizes daily reference rates directly from the European Central Bank API for official EUR/CNY and USD/CNY cross-rates.
- **Empirical 60-Day Volatility Modeling:**
  - Calculates true standard deviations of log returns over 42 trading days across 2 years of daily historical data.
  - Feeds a seeded **5,000-path Monte Carlo engine** (NumPy + SciPy) with Gaussian FX distributions and Beta return distributions, computing the exact **95% Margin-at-Risk floor price ($MaR_{95}$)**.

### 3. Ultra-Low Latency & High Fault-Tolerant Availability
- **2–8 Second Conversational Latency:** By turning off token-wasting chain-of-thought overhead (`LLM_THINKING=disabled`) and delegating all math to compiled sub-millisecond Python routines, responses stream with minimal latency.
- **Automated Fallback Model Routing:** If the primary upstream model experiences rate limits (HTTP 429), out-of-quota errors (HTTP 402), or network timeout spikes, `landed/agent.py` automatically retries the turn on `LLM_FALLBACK_MODEL` seamlessly.
- **Graceful Degradation:** If all LLM connectivity fails, the deterministic pricing engine and browser-based calculator remain 100% operational.

### 4. "Ask Only What Changes the Money" (Entropy-Minimized Questioning)
- Standard LLMs inundate sellers with dozens of classification questions. Landed recognizes legal customs thresholds:
  - Under the EU's 1 Jul 2026 customs reform, goods below €150 pay a **flat €3 duty per tariff category**, rendering deep HS disambiguation irrelevant for pricing.
  - Landed asks only for the 4 core economic variables (cost, weight, market, margin) and prices immediately.
  - Where the code alters duty (e.g., US Section 301 tariffs or orders above €150), `landed/hs.py` selects the single next clarifying question that minimizes candidate entropy.
  - **Bundle Optimization (WCO GRI 3(b)):** Automatically identifies opportunities where declaring components as a retail set halves customs category fees.

---

## 📂 Repository Layout

| Directory / File | Description |
|---|---|
| `data/rates.csv` | Hand-verified rates (duty, VAT, FX, platform fees) with `source_url`, `snapshot_date`, and audit `status`. |
| `data/hs_tree.json` | HS classification taxonomy, chapter notes, and discriminating attribute tree. |
| `data/compliance.json` | Multi-jurisdiction compliance flags (GPSR, PPWR, UN 3481, food contact, WEEE, etc.). |
| `data/platforms.json` | Sourced referral commissions for major marketplaces across the EU and US. |
| `landed/engine.py` | Core cost waterfall, 5,000-path Monte Carlo risk simulation, stress tests, and bundle logic. |
| `landed/agent.py` | Bounded agent loop (≤ 6 tool rounds), SSE streaming event generator, and system prompt. |
| `landed/guardrail.py` | Post-generation audit engine verifying numbers, specifications, and certification claims. |
| `landed/hs.py` | Entropy-minimizing HS code classifier and disambiguation dialogue engine. |
| `landed/tools.py` | Strict whitelisted tool definitions and dispatcher for LLM execution. |
| `api/main.py` | FastAPI application serving streaming endpoints (`/api/chat`, `/api/calc`, `/api/compliance`) and static UI. |
| `api/accounts.py` | Persistent session management, SQLite storage, scrypt password hashing, and user profile sync. |
| `src/` | Interactive landing page, cost waterfall visualizer, and onboarding flow (Vite + GSAP). |
| `src/lib/engine.js` | Zero-dependency JavaScript port of the Python engine for instant client-side calculations. |
| `scripts/refresh_fx.py` | Automated ECB daily exchange rate synchronization and historical volatility update script. |
| `tests/` | 395 unit and integration tests covering the engine, agent loop, guardrails, and compliance logic. |
| `eval/` | Benchmark harness testing Landed vs. unassisted LLM baselines across 36+ real-world seller cases. |

---

## 🧪 Test and Evaluate

Run the comprehensive test suite and evaluation benchmarks:

```bash
# Run 395 unit & integration tests
pytest -q tests

# Run offline price formula closed-form backtest (all 27 EU nations)
pytest tests/test_backtest.py tests/test_api_backtest.py

# Run real-world seller evaluation benchmark (calls configured LLM)
python -m eval.run_eval
```

### Benchmark Highlights (`eval/RESULTS.md`):
- **Pricing Accuracy (26 test cases):** Landed achieved **100% (26/26)** within ±1% of ground truth ($p = 3.0 \times 10^{-8}$ vs baseline 0%).
- **Margin Erosion Prevented:** Unassisted LLMs underpriced cases by an average of **€11.57/unit**, which would have forced sellers into negative margins on 19 out of 26 products.
- **Refusal to Hallucinate (10 edge cases):** Correctly declined or requested missing information in 100% of incomplete cases without inventing figures.

---

## 🌐 Coverage & Scope

- **European Union (27 Member States):** Verified individual VAT rates for all 27 EU nations; automated application of the July 2026 €3 flat customs duty regime for parcels ≤ €150; EU-wide PPWR packaging registration, GPSR, and WEEE alerts.
- **United States:** Blender & motor appliance categories with verified 12.5% China Section 301 duties (indicative lower-bound pricing).
- **Listing Localization:** Generates high-converting listings in the official language of the destination market (German, French, Italian, Spanish, Dutch, Polish, Swedish, etc.).

---

## ⚖️ Disclaimer

Landed (到岸) is an AI-powered quantitative decision support tool for cross-border e-commerce planning, not a licensed customs brokerage or legal advisory service. Sellers should verify classifications with customs authorities (e.g., via BTI or CBP CROSS rulings) before shipping commercial consignments.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
