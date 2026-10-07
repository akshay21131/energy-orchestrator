# 🎥 Demo Video Script (3–4 minutes)

> Recommended: record your screen at 1920×1080 with the browser fullscreen. Start with the app open at http://localhost:8000 on the Welcome overlay.

---

### 0:00–0:20  ·  INTRO (face cam optional)
"Hi, I'm [name] from Team PROTEANZ, and this is our Renewable Energy Orchestrator — an autonomous AI agent that coordinates solar farms, wind farms, batteries, the grid, and industrial demand every 15 minutes, built for the ET × Accenture AI Hackathon. India is targeting 500 GW of renewables by 2030, but today's grid operators can't balance cost, carbon, reliability, and battery life in real time. Our agent does."

[Click **Start Autonomous Run** to dismiss welcome screen.]

---

### 0:20–0:55  ·  THE DASHBOARD
"What you're looking at is our real-time glass dashboard. On the left, the asset portfolio — five solar farms, three wind farms, two battery storage systems, with live outputs and state-of-charge. In the center, the live power flow topology — you can see solar, wind, batteries, and the grid all feeding industrial load, with animated flow lines showing where power is moving. Below that is a rolling 24-hour dispatch chart. On the right are the KPIs, the AI agent's live reasoning showing which objective weights it's prioritizing, forecasts, scenario controls, and a decision audit."

[Point briefly to each column.]

---

### 0:55–1:40  ·  THE AGENT IN ACTION
"Let me press Play."

[Click ▶ Play, set speed to 200×.]

"Watch the time advance. Every tick represents 15 minutes. The agent goes through five stages — Observe, Reason, Optimize, Validate, Act — every single tick. It reads telemetry and forecasts, diagnoses the situation, dynamically sets six objective weights based on forecast confidence and anomalies, then **calls an LP optimizer as a tool** with those weights. That's important — the LP isn't the brain, it's a calculator the agent uses. After solving, the agent validates the plan; if anything fails, it bumps reliability and battery reserve and re-runs the optimizer before dispatching."

[Point to the Observe→Reason→Optimize→Validate→Act pipeline in the header as it lights up. Point to agent reasoning weights changing.]

"You can see the carbon, reliability, battery-life, curtailment, and profit-export weights shifting in real time as conditions change through the day. Look at midday — solar is peaking, batteries are charging on cheap surplus, and we're exporting to the grid. Then as evening hits, the agent discharges batteries and imports only what's needed, avoiding the evening price spike."

[Let it run to ~18:00 so sunset/discharge is visible.]

---

### 1:40–2:20  ·  STRESS TESTS — EVENTS & SCENARIOS
"Let me stress-test it."

[Reset. Click **🌡️ Summer Peak** scenario. Play at 200×.]
"Here's a summer-peak scenario — demand surge plus a price spike. The agent immediately builds battery reserve."

[Pause after a few ticks. Inject ⚡ Price Spike, then 🔋 BESS 1 Fault.]
"I'm injecting a price spike and a battery fault in real time. See that yellow Replan flag? The agent detected the fault, re-weighted objectives, and re-planned — zero critical load dropped."

[Reset. Click **⛈️ Stormy Night**.]
"Stormy night: wind gusts and a line trip. Again the agent replans and routes around it. Across all four scenarios — normal day, summer peak, stormy night, price volatility — we see zero unmet critical load."

---

### 2:20–2:55  ·  NATURAL LANGUAGE COMMANDS
"The operator stays in the loop. I can type natural-language commands."

[Reset, Play at 200× for a few seconds.]
"Type 'go green'."
[Type and send. Point to weights panel.]
"Watch the carbon weight jump up to 0.45 — the agent immediately shifts to minimize grid electricity and maximize renewables."

"Type 'prepare for peak'."
"Now it's holding 25% battery reserve, getting ready for the evening peak. These commands don't hard-code dispatch — they override weights and the agent still reasons over them with the LP."

---

### 2:55–3:25  ·  BUSINESS IMPACT
"Over a full 24-hour day, the agent saves about 71% in operating cost — roughly ₹13.7 lakhs per day for this 100 MW portfolio — avoids about 153 tonnes of CO₂, eliminates 487 MWh of curtailment, and does it all with zero unmet critical load. That compares to a dumb-grid baseline that has no batteries, no demand response, and no export."

[Click ⏩ Day and let it run to completion. When the Day Complete modal appears, point at the numbers.]
"You're seeing the day-summary modal right now: final numbers against baseline."

---

### 3:25–3:50  ·  ARCHITECTURE & CLOSING
[Click 📐 Arch to show the architecture modal — or cut to the architecture slide in the deck.]
"Under the hood it's a FastAPI + WebSocket backend in Python, a React + Recharts frontend, and a PuLP/CBC LP optimizer. The LLM layer is optional — the system runs fully offline with a built-in expert rule brain. That matters for DISCOMs that can't send grid data to external APIs."

"It's genuinely agentic — dynamic weight setting, tool use (the LP), closed-loop reflection on validation failures, uncertainty-aware risk modulation, and natural-language human override. That puts us at the D2/F3 cell of the 9-blocker matrix, which is the highest-reliability agentic position."

"One command to run — `./run.sh` — installs everything, builds the frontend, and starts the server. Thanks for watching."

---

### Quick recording checklist
- [ ] Browser zoom at 100%, hide bookmarks bar for a clean frame
- [ ] Run `./run.sh`, wait for "Server running on port 8000"
- [ ] Reset once before recording so you start fresh at Day 1 06:00 Welcome screen
- [ ] Have speed at 200× so the day visibly progresses but is still readable
- [ ] Talk slowly; pause between actions so the UI catches up
- [ ] End on the Day-Complete modal or the big KPI numbers — visual punch
- [ ] Upload as **Unlisted** YouTube video or public Google Drive link
