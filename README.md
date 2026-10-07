# ⚡ Renewable Energy Orchestrator

> **ET × Accenture AI Hackathon — Agentic Edition**
> Problem 4 · 9-Blocker position **D2 / F3**
> Autonomous AI agent that orchestrates 5 solar farms, 3 wind farms, 2 battery systems, grid imports/exports, and industrial demand — deciding every 15 minutes whether to charge/discharge batteries, buy/sell power, curtail renewables, or trigger demand response — to minimize cost, carbon, curtailment, and battery degradation while maximizing reliability, renewable utilization, and grid stability.

---

## 🎯 What makes this *agentic* (not just an LP with an LLM wrapper)

| Capability | Implementation |
|---|---|
| **LLM in the decision loop** | The agent *reasons* about anomalies, forecast confidence, and operator intent, then *dynamically chooses* 6 objective weights + a battery reserve level per tick. |
| **LP is a called tool**, not the brain | A multi-objective LP (PuLP/CBC, ~20 variables, <50 ms) is invoked **by** the agent with the chosen weights — the solver doesn't decide *what* to optimize. |
| **Closed-loop reflection** | After solving, the agent validates the plan. If critical load is unmet, SOC bounds are violated, or prices are absurd, it bumps reliability/reserve and **re-runs** the optimizer before acting. |
| **Uncertainty-aware** | Forecast confidence (high/medium/low across 5 horizons) modulates the agent's risk posture — low confidence → higher battery reserve. |
| **Natural-language override** | Operators type commands ("go green", "prepare for peak", "discharge") that inject weight overrides blending with the agent's own reasoning. |
| **Structured + textual inputs (D2)** | Telemetry is structured kW/SOC/price; alerts & anomalies are textual — fed to the reasoning layer. |
| **Multi-timestep simulation under varying conditions (F3)** | Continuous 24h tick-by-tick (15-min steps) across 4 scenarios (Normal, Summer Peak, Stormy Night, Price Volatility) + 10 injectable events. |
| **Safety layer that cannot be overridden** | Battery SOC 10–95% hard bounds in LP, ₹50/kWh critical-load penalty, power-balance equality, capacity caps, greedy fallback solver if LP is infeasible, human pause/override. |

---

## 📊 Live Results (24h simulated day vs. dumb-grid baseline)

| KPI | Result |
|---|---|
| **Operating cost saved** | **~71%** (₹13.7 L/day for a ~100 MW portfolio) |
| **CO₂ avoided** | **~153 t CO₂/day** |
| **Curtailment reduced** | **~487 MWh** that would otherwise be wasted |
| **Unmet critical load** | **0 MWh** across all 4 stress scenarios |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  🧑‍💻 Operator Dashboard (React 19 + Vite + Recharts + WS)  │
│   • Live topology • Streaming chart • NL commands • Audit  │
└────────────────────────▲────────────────────────────────────┘
                         │ WebSocket (sub-50 ms broadcasts)
┌────────────────────────┴────────────────────────────────────┐
│  🧠 Agent Brain (observe → reason → optimize → validate → act)│
│   • Rule-based expert (default, zero-dependency)            │
│   • LLM-adaptive (Claude/GPT/Gemini) when API key is set   │
│   • Dynamic weight vector: cost, carbon, reliability,       │
│     battery_life, curtailment, profit_export                │
└────────────────────────▲────────────────────────────────────┘
                         │ tool call (weights + constraints)
┌────────────────────────┴────────────────────────────────────┐
│  ⚙️  LP Optimizer (PuLP/CBC) — ~20 vars, <50 ms per tick    │
│   • Power balance • SOC evolution • capacity caps           │
│   • BESS charge/discharge exclusivity • DR limits           │
└────────────────────────▲────────────────────────────────────┘
                         │ apply dispatch
┌────────────────────────┴────────────────────────────────────┐
│  🌍 Simulation World                                         │
│   • 5 solar farms (93 MW rated, Delhi 28.6°N irradiance)   │
│   • 3 wind farms (75 MW rated, stochastic gusts/lulls)     │
│   • 2 BESS (20 MW / 80 MWh each, 10–95% SOC hard bounds)   │
│   • Grid interconnection with time-of-use tariffs          │
│   • 3 industrial + commercial consumers with DR capacity   │
│   • 5 forecast horizons (15m–4h) with confidence values    │
└─────────────────────────────────────────────────────────────┘
          🛡 Safety layer (cannot be overridden): SOC bounds,
             power-balance, critical-load penalty, greedy fallback
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (tested on 3.13)
- **Node.js 18+** and npm
- No external API keys required for the default experience (LLM is optional).

### One-command run
```bash
git clone <your-repo-url>
cd energy_orchestrator
./run.sh
```

The script will:
1. Install Python deps (fastapi, uvicorn, websockets, pulp<3, numpy, pydantic)
2. Install frontend deps and build the React app
3. Start the server on **http://localhost:8000**

Open http://localhost:8000 in your browser and click **▶ Play**.

### Manual setup
```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run build     # production build into dist/, served by FastAPI
# or: npm run dev   # dev server with HMR at http://localhost:5173
```

### Optional: enable LLM reasoning
Set an `OPENAI_API_KEY` (or any OpenAI-compatible endpoint via `OPENAI_BASE_URL`) before running. Without it, the built-in rule-based expert brain runs identically — same KPIs, same agentic loop, just shorter textual explanations.

---

## 🎮 Using the dashboard

- **▶ Play / ⏸ Pause / ⏩ Day / ⏭ Step** — control the simulation clock
- **Speed** (5× / 20× / 60× / 200×) — how fast the 15-minute ticks elapse
- **Scenarios** — Normal Day · Summer Peak · Stormy Night · Price Volatility
- **Inject Events** — ☁️ Cloud Cover, 💨 Wind Gust/Lull, ⚡ Price Spike/Crash, 🔋 Battery Fault, 🔌 Line Trip, 🏭 Demand Surge, 🌪️ Storm Warning
- **💬 Operator Commands** (natural language):
  - `"go green"` — maximize renewable use, minimize grid carbon
  - `"prepare for peak"` / `"prepare for storm"` — hold 25–30% battery reserve
  - `"max profit"` — prioritize export arbitrage
  - `"be safe"` — reliability-first mode
  - `"discharge"` — aggressive BESS discharge (no reserve)
  - `"min curtail"` — prioritize absorbing surplus renewables
- **📜 Decision Audit** — click any past tick to see the agent's full reasoning, weights, and validation

---

## 📁 Project structure
```
energy_orchestrator/
├── run.sh                    # One-command launcher
├── backend/
│   ├── main.py               # FastAPI app, WebSocket hub, tick loop, REST endpoints
│   ├── simulation.py         # World model: assets, weather, tariffs, demand, KPIs
│   ├── optimizer.py          # Multi-objective LP (PuLP/CBC)
│   ├── agent.py              # Observe/Reason/Validate/Act loop, rule brain, LLM client
│   ├── llm_client.py         # OpenAI-compatible client (optional)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Main dashboard (dense 16:9 layout)
│   │   ├── index.css         # Glass-morphism dark theme
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── test_all.py               # End-to-end QA: 78 checks across 8 phases
└── submission/
    └── Renewable_Energy_Orchestrator_Pitch.pptx  # 11-slide hackathon deck
```

---

## 🔌 API Reference

All endpoints return JSON. WebSocket at `ws://<host>/ws` pushes `{type: "state", state: {...}, engine: {...}}` messages each tick.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/state` | Current simulation snapshot |
| GET | `/api/config` | Asset portfolio (names, rated capacities) |
| POST | `/api/play` | Start/resume tick loop |
| POST | `/api/pause` | Pause |
| POST | `/api/step` | Single tick |
| POST | `/api/play-day` | Fast-forward to end of day |
| POST | `/api/reset` | Reset to Day 1, 06:00 |
| POST | `/api/control` | Set speed / autonomous mode |
| POST | `/api/load-scenario` | `{"scenario": "normal"|"summer_peak"|"stormy_night"|"price_volatility"}` |
| POST | `/api/inject-event` | Inject a disruption (clouds, gust, fault, price spike, etc.) |
| POST | `/api/nl-command` | `{"command": "go green"}` — natural language operator directive |
| GET | `/api/comparison` | Live savings vs dumb-grid baseline |
| GET | `/api/baseline` | Pre-computed 24h baseline KPIs |
| GET | `/api/safety` | Hard-constraint status (SOC bounds, balance, faults) |
| GET | `/api/decision-history` | Last 40 agent decisions |
| WS | `/ws` | Real-time state/engine/event stream |

---

## 🧪 QA
End-to-end test suite (`test_all.py`) covers 8 phases: server health, WebSocket-driven control flow (same as the browser UI), HTTP step/play/pause, all 4 scenarios, all 10 event types, all 6 NL commands, speed/auto toggle, play-day completion, day-summary correctness, and static asset delivery.

```bash
pip install requests websocket-client
python test_all.py
# → 78 passed, 0 warnings, 0 failures
```

---

## 🛣 Roadmap

- **0–30 days** — pilot at one captive industrial site (5–10 MW), integrate SCADA/inverter APIs, A/B vs human operator.
- **30–90 days** — DISCOM MVP (1–2 GW zone) with zonal coordinator agent, IMD weather API, IEX price feed.
- **6–12 months** — multi-zone coordination for state-level DISCOMs, EV and green-hydrogen flexible loads, carbon-credit arbitrage.

---

## 📜 License
Prototype built for the ET × Accenture AI Hackathon. All rights reserved.
