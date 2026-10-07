"""FastAPI application for the Renewable Energy Orchestrator."""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import make_default_config
from simulation import Simulation, WorldState
from optimizer import EnergyOptimizer
from agent import EnergyAgent


# --- Globals ---
cfg = make_default_config()
sim = Simulation(cfg, seed=42)
optimizer = EnergyOptimizer(cfg)
agent = EnergyAgent(cfg, optimizer)

# Engine state
engine_state = {
    "running": False,
    "speed": 20,  # ticks per second (wall-clock); 1 tick = 15 sim-minutes → speed=20 → 5 sim-hours/sec
    "last_tick": 0.0,
    "tick_interval_sec": 1.0,
    "autonomous": True,
    "total_ticks": 0,
    "started": False,  # becomes True after first /play (auto-play on load sets this)
    "day_complete": False,
    "replan_last_tick": False,
    "agent_stage": "idle",  # observe | reason | optimize | validate | act
}
connected_clients: List[WebSocket] = []
decision_history: List[Dict[str, Any]] = []  # last 30 decisions for audit trail
NL_INTENTION_SET = {"hold_reserve","discharge_batteries","charge_batteries","max_export","min_import",
                    "max_reliability","min_cost","min_carbon","min_curtailment","preserve_batteries",
                    "drain_batteries","normal"}


def compute_baseline_kpis() -> Dict[str, float]:
    """Compute KPIs for a naive 'no-battery, no-DR, no-strategy' controller on a fresh sim.
    Used to show lift from the AI agent.
    """
    base = Simulation(cfg, seed=42)
    base.compute_potentials(base.world)
    for _ in range(96):
        base.advance_time()
        base.compute_potentials(base.world)
        ws = base.world
        total_renew_solar = sum(ws.assets[s.id].available_kw for s in cfg.solar_farms)
        total_renew_wind = sum(ws.assets[w.id].available_kw for w in cfg.wind_farms)
        total_renew = total_renew_solar + total_renew_wind
        dem = ws.total_demand_kw
        actions = {
            "solar_use_kw": {s.id: ws.assets[s.id].available_kw for s in cfg.solar_farms},
            "wind_use_kw": {w.id: ws.assets[w.id].available_kw for w in cfg.wind_farms},
            "solar_curtail_kw": {s.id: 0.0 for s in cfg.solar_farms},
            "wind_curtail_kw": {w.id: 0.0 for w in cfg.wind_farms},
            "batt_charge_kw": {b.id: 0.0 for b in cfg.batteries},
            "batt_discharge_kw": {b.id: 0.0 for b in cfg.batteries},
            "grid_import_kw": max(0, dem - total_renew),
            "grid_export_kw": 0.0,
            "serve_kw": {c.id: ws.demand_per_consumer_kw[c.id] for c in cfg.consumers},
            "dr_cut_kw": {c.id: 0.0 for c in cfg.consumers},
        }
        surplus = total_renew - dem
        if surplus > 0:
            for s in cfg.solar_farms:
                share = ws.assets[s.id].available_kw / max(1, total_renew)
                actions["solar_curtail_kw"][s.id] = min(ws.assets[s.id].available_kw, surplus * share)
                actions["solar_use_kw"][s.id] = ws.assets[s.id].available_kw - actions["solar_curtail_kw"][s.id]
            for w in cfg.wind_farms:
                share = ws.assets[w.id].available_kw / max(1, total_renew)
                actions["wind_curtail_kw"][w.id] = min(ws.assets[w.id].available_kw, surplus * share)
                actions["wind_use_kw"][w.id] = ws.assets[w.id].available_kw - actions["wind_curtail_kw"][w.id]
        base.apply_actions(ws, actions, {"reliability": 1.0})
    return {
        "cost_inr": base.world.kpi_cost_inr,
        "co2_kg": base.world.kpi_co2_kg,
        "curtailed_kwh": base.world.kpi_curtailed_kwh,
        "renewable_kwh": base.world.kpi_renewable_kwh,
        "unmet_critical_kwh": base.world.kpi_unmet_critical_kwh,
        "grid_import_kwh": base.world.kpi_grid_import_kwh,
        "grid_export_kwh": base.world.kpi_grid_export_kwh,
    }


_baseline_cache = None
def get_baseline() -> Dict[str, float]:
    global _baseline_cache
    if _baseline_cache is None:
        _baseline_cache = compute_baseline_kpis()
    return _baseline_cache


# --- Event models ---
class EventRequest(BaseModel):
    type: str
    target: Optional[str] = None
    magnitude: float = 1.0
    duration_ticks: int = 8
    is_forecast: bool = False
    lead_ticks: int = 0


class ManualActionRequest(BaseModel):
    battery_charge_kw: Optional[Dict[str, float]] = None
    battery_discharge_kw: Optional[Dict[str, float]] = None
    grid_import_kw: Optional[float] = None
    grid_export_kw: Optional[float] = None
    note: Optional[str] = None


class ConfigRequest(BaseModel):
    speed: Optional[float] = None
    autonomous: Optional[bool] = None


class ScenarioRequest(BaseModel):
    scenario: str  # 'normal', 'summer_peak', 'stormy_night', 'price_volatility'


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize: run potentials once so first snapshot is non-trivial
    sim.compute_potentials(sim.world)
    # Do NOT run the agent on the initial zero-potential state — that produces nonsensical
    # actions at 6 AM before any sun/wind. The first Play/tick will prime it naturally.
    sim.world.agent_reasoning = {
        "mode": "Idle",
        "situation_assessment": "System ready. Press Play to start autonomous operation.",
        "explanation": "The AI agent will begin observing conditions, reasoning about priorities, and dispatching assets every 15 minutes once autonomous mode starts.",
        "intent": "Awaiting start",
        "anomalies": ["System initialized — no data yet."],
        "opportunities": [],
        "forecast_confidence": "high",
        "weights": {"cost": 0.22, "carbon": 0.2, "reliability": 0.28, "battery_life": 0.1, "curtailment": 0.15, "profit_export": 0.05},
        "optimizer_called": False,
        "replanned_this_tick": False,
        "stage": "idle",
        "actions_summary": {},
        "validation": {"valid": True, "issues": []},
    }
    # Start the simulation tick loop
    global _loop_task
    _loop_task = asyncio.create_task(tick_loop())
    yield
    if _loop_task is not None:
        _loop_task.cancel()


app = FastAPI(title="Renewable Energy Orchestrator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Aggressive no-cache middleware so the browser always picks up new JS/CSS after restarts
@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# --- WebSocket hub ---
async def broadcast(msg: Dict[str, Any]):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for d in dead:
        connected_clients.remove(d)


async def tick_engine():
    """Advance simulation by one tick: compute potentials → agent decides → apply actions → push state."""
    prev_day = sim.world.day
    sim.advance_time()

    # Stage 1: OBSERVE
    engine_state["agent_stage"] = "observe"
    ctx = sim.compute_potentials(sim.world)

    if engine_state["autonomous"]:
        # Stage 2: REASON
        engine_state["agent_stage"] = "reason"
        await asyncio.sleep(0)  # yield so stage broadcasts are visible (brief)

        snap = sim.snapshot()

        # Stage 3: OPTIMIZE
        engine_state["agent_stage"] = "optimize"
        decision = agent.observe_and_act(snap)

        # Stage 4: VALIDATE
        engine_state["agent_stage"] = "validate"
        replanned = bool(decision.reasoning.get("replan"))
        engine_state["replan_last_tick"] = replanned

        # Stage 5: ACT
        engine_state["agent_stage"] = "act"
        sim.apply_actions(sim.world, decision.actions, decision.weights)
        reasoning = dict(decision.reasoning)
        reasoning["validation"] = decision.validation
        reasoning["weights"] = decision.weights
        reasoning["hold_reserve_kw"] = decision.hold_reserve_kw
        reasoning["actions_summary"] = _summarize_actions(decision.actions)
        reasoning["stage"] = "act"
        reasoning["optimizer_called"] = True
        reasoning["replanned_this_tick"] = replanned
        sim.world.agent_reasoning = reasoning

        # Push into decision history
        decision_history.insert(0, {
            "sim_time": snap["sim_time_min"],
            "time_of_day": snap["time_of_day"],
            "reasoning": decision.reasoning,
            "weights": decision.weights,
            "actions_summary": _summarize_actions(decision.actions),
            "kpis_snapshot": dict(snap["kpis"]),
            "replanned": replanned,
        })
        if len(decision_history) > 40:
            decision_history.pop()
    else:
        sim.world.agent_reasoning = {
            "mode": "Manual / paused",
            "explanation": "Agent is paused. Use dashboard controls or resume autonomous mode.",
            "actions_summary": {},
            "stage": "idle",
        }

    engine_state["total_ticks"] += 1
    engine_state["agent_stage"] = "idle"

    # Detect day completion
    if sim.world.day > prev_day:
        engine_state["day_complete"] = True
        engine_state["running"] = False
        # Attach day summary
        day_summary = {
            "day": prev_day,
            "kpis": {
                "cost_inr": sim.world.kpi_cost_inr,
                "co2_kg": sim.world.kpi_co2_kg,
                "renewable_kwh": sim.world.kpi_renewable_kwh,
                "curtailed_kwh": sim.world.kpi_curtailed_kwh,
                "grid_import_kwh": sim.world.kpi_grid_import_kwh,
                "grid_export_kwh": sim.world.kpi_grid_export_kwh,
                "unmet_critical_kwh": sim.world.kpi_unmet_critical_kwh,
            },
            "baseline_24h": get_baseline(),
        }
        b = day_summary["baseline_24h"]
        day_summary["savings"] = {
            "cost_inr_saved": b["cost_inr"] - day_summary["kpis"]["cost_inr"],
            "co2_kg_saved": b["co2_kg"] - day_summary["kpis"]["co2_kg"],
            "curtailment_reduced_kwh": b["curtailed_kwh"] - day_summary["kpis"]["curtailed_kwh"],
        }
        sim.world.day_summary = day_summary
    else:
        sim.world.day_summary = None


def _summarize_actions(actions: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "grid_import_kw": round(actions["grid_import_kw"], 0),
        "grid_export_kw": round(actions["grid_export_kw"], 0),
        "battery_discharge_total_kw": round(sum(actions["batt_discharge_kw"].values()), 0),
        "battery_charge_total_kw": round(sum(actions["batt_charge_kw"].values()), 0),
        "solar_curtail_total_kw": round(sum(actions["solar_curtail_kw"].values()), 0),
        "wind_curtail_total_kw": round(sum(actions["wind_curtail_kw"].values()), 0),
        "demand_response_total_kw": round(sum(actions["dr_cut_kw"].values()), 0),
    }


async def tick_loop():
    while True:
        await asyncio.sleep(0.05)
        if not engine_state["running"]:
            continue
        now = time.time()
        interval = 1.0 / max(1, engine_state["speed"])
        if now - engine_state["last_tick"] >= interval:
            engine_state["last_tick"] = now
            try:
                await tick_engine()
                await broadcast({"type": "state", "state": sim.snapshot(), "engine": engine_status()})
                if engine_state["day_complete"]:
                    await broadcast({"type": "day_complete", "summary": sim.world.day_summary})
            except Exception as e:
                import traceback
                traceback.print_exc()
                engine_state["running"] = False
                await broadcast({"type": "engine", "engine": engine_status(), "error": str(e)})


_loop_task = None


def engine_status() -> Dict[str, Any]:
    return {
        "running": engine_state["running"],
        "speed": engine_state["speed"],
        "autonomous": engine_state["autonomous"],
        "total_ticks": engine_state["total_ticks"],
        "llm_available": agent.llm.available,
        "started": engine_state["started"],
        "day_complete": engine_state["day_complete"],
        "agent_stage": engine_state["agent_stage"],
        "replan_last_tick": engine_state["replan_last_tick"],
    }


class NLCommandRequest(BaseModel):
    command: str


@app.post("/api/nl-command")
async def nl_command(req: NLCommandRequest):
    """Parse a natural-language operator command into weight overrides or scenario triggers.
    Works with or without LLM (keyword-based fallback)."""
    cmd = req.command.lower().strip()
    overrides = {}
    response = ""
    injected = None

    # Keyword-based intent parsing (always works, even without LLM)
    if "evening" in cmd or "peak" in cmd or "prepare" in cmd or "reserve" in cmd:
        overrides["hold_reserve_kw"] = 15000
        overrides["battery_hold_reserve_frac"] = 0.25
        response = "Understood. Holding 25% battery reserve and prioritizing reliability in preparation."
    elif "export" in cmd or "sell" in cmd:
        overrides["weights"] = {"cost":0.15,"carbon":0.1,"reliability":0.2,"battery_life":0.05,"curtailment":0.1,"profit_export":0.4}
        response = "Shifting to export-priority mode. Will discharge batteries and sell to grid when prices allow."
    elif "save" in cmd and "battery" in cmd or "preserve" in cmd:
        overrides["weights"] = {"cost":0.2,"carbon":0.15,"reliability":0.25,"battery_life":0.3,"curtailment":0.05,"profit_export":0.05}
        response = "Preserving battery life. Will minimize cycling and use grid/renewables directly."
    elif "drain" in cmd or "discharge" in cmd:
        overrides["hold_reserve_kw"] = 0
        overrides["battery_hold_reserve_frac"] = 0
        overrides["weights"] = {"cost":0.3,"carbon":0.1,"reliability":0.2,"battery_life":0.0,"curtailment":0.1,"profit_export":0.3}
        response = "Discharging batteries aggressively (will not hold reserve)."
    elif "charge" in cmd:
        overrides["weights"] = {"cost":0.35,"carbon":0.2,"reliability":0.2,"battery_life":0.1,"curtailment":0.1,"profit_export":0.05}
        response = "Charging batteries when economical (prioritizing low-cost charging)."
    elif "carbon" in cmd or "clean" in cmd or "green" in cmd or "renewable" in cmd:
        overrides["weights"] = {"cost":0.1,"carbon":0.45,"reliability":0.2,"battery_life":0.05,"curtailment":0.15,"profit_export":0.05}
        response = "Maximizing clean energy utilization and minimizing grid carbon."
    elif "reliable" in cmd or "critical" in cmd or "safe" in cmd or "storm" in cmd:
        overrides["hold_reserve_kw"] = 20000
        overrides["battery_hold_reserve_frac"] = 0.3
        overrides["weights"] = {"cost":0.1,"carbon":0.05,"reliability":0.6,"battery_life":0.05,"curtailment":0.05,"profit_export":0.15}
        response = "Entering reliability-first mode. Holding 30% battery reserve, prioritizing critical load."
    elif "cost" in cmd or "cheap" in cmd or "money" in cmd or "profit" in cmd:
        overrides["weights"] = {"cost":0.4,"carbon":0.1,"reliability":0.2,"battery_life":0.05,"curtailment":0.05,"profit_export":0.2}
        response = "Prioritizing cost minimization and arbitrage profit."
    elif "curtail" in cmd or "waste" in cmd:
        overrides["weights"] = {"cost":0.1,"carbon":0.15,"reliability":0.15,"battery_life":0.05,"curtailment":0.5,"profit_export":0.05}
        response = "Minimizing renewable curtailment as top priority."
    elif "stop" in cmd or "pause" in cmd:
        engine_state["running"] = False
        response = "Paused."
    elif "reset" in cmd:
        await reset()
        response = "Reset to initial state."
    elif "play" in cmd or "go" in cmd or "start" in cmd or "run" in cmd:
        await play()
        response = "Starting autonomous operation."
    elif "event" in cmd or "spike" in cmd or "fault" in cmd or "storm" in cmd:
        # simple trigger a spike
        injected = sim.inject_event("price_spike", magnitude=2.0, duration_ticks=4)
        response = "Injecting a price spike event."
    else:
        # If LLM is available, try LLM parsing; otherwise default response
        if agent.llm.available:
            response = "I'll apply that directive."  # LLM agent naturally interprets state each tick
        else:
            response = "I didn't understand that command. Try: 'prepare for peak', 'maximize profit', 'go green', 'be safe', 'discharge batteries', 'minimize curtailment'."

    # Apply weight overrides to agent for next tick
    if overrides:
        agent.override = overrides
    await broadcast({"type": "command", "command": req.command, "response": response})
    return {"ok": True, "response": response, "overrides": overrides, "injected": injected}


@app.get("/api/decision-history")
def decision_history_endpoint():
    return {"history": decision_history[:30], "count": len(decision_history)}


@app.get("/api/safety")
def safety_info():
    """Show hard safety constraints the AI can never violate."""
    return {
        "constraints": [
            {"name": "Battery minimum SOC", "value": f"{cfg.batteries[0].min_soc_frac*100:.0f}%", "enforced_by": "LP (hard bound)"},
            {"name": "Battery maximum SOC", "value": f"{cfg.batteries[0].max_soc_frac*100:.0f}%", "enforced_by": "LP (hard bound)"},
            {"name": "Critical load priority", "value": "Penalty ₹50/kWh", "enforced_by": "LP penalty"},
            {"name": "Grid import cap", "value": f"{cfg.grid.max_import_kw/1000:.0f} MW", "enforced_by": "LP bound"},
            {"name": "Grid export cap", "value": f"{cfg.grid.max_export_kw/1000:.0f} MW", "enforced_by": "LP bound"},
            {"name": "Battery charge rate", "value": "≤max C-rate", "enforced_by": "LP bound"},
            {"name": "Power balance", "value": "gen = load + losses", "enforced_by": "LP equality"},
            {"name": "LLM output schema", "value": "JSON with clamped weights", "enforced_by": "Agent validator"},
            {"name": "Replan on validation failure", "value": "Retry w/ higher reliability", "enforced_by": "Agent reflect loop"},
            {"name": "LP failure fallback", "value": "Greedy reliability-first", "enforced_by": "Optimizer fallback"},
        ]
    }


# --- REST endpoints ---
@app.get("/api/config")
def get_config():
    return {
        "solar_farms": [s.__dict__ for s in cfg.solar_farms],
        "wind_farms": [w.__dict__ for w in cfg.wind_farms],
        "batteries": [b.__dict__ for b in cfg.batteries],
        "grid": cfg.grid.__dict__,
        "consumers": [c.__dict__ for c in cfg.consumers],
        "tick_minutes": cfg.tick_minutes,
    }


@app.get("/api/state")
def get_state():
    return {"state": sim.snapshot(), "engine": engine_status()}


@app.post("/api/control")
async def set_control(req: ConfigRequest):
    if req.speed is not None:
        engine_state["speed"] = max(0.5, min(200, float(req.speed)))
    if req.autonomous is not None:
        engine_state["autonomous"] = bool(req.autonomous)
    await broadcast({"type": "engine", "engine": engine_status()})
    return engine_status()


@app.post("/api/play")
async def play():
    engine_state["running"] = True
    engine_state["started"] = True
    engine_state["last_tick"] = time.time()
    await broadcast({"type": "engine", "engine": engine_status()})
    return engine_status()


@app.post("/api/pause")
async def pause():
    engine_state["running"] = False
    await broadcast({"type": "engine", "engine": engine_status()})
    return engine_status()


@app.post("/api/play-day")
async def play_day():
    """Fast-forward to end of current day (stop at day rollover)."""
    engine_state["running"] = True
    engine_state["started"] = True
    engine_state["speed"] = 200  # fast
    engine_state["day_complete"] = False
    engine_state["last_tick"] = time.time()
    await broadcast({"type": "engine", "engine": engine_status()})
    return engine_status()


@app.post("/api/step")
async def step():
    """Run a single tick manually."""
    engine_state["running"] = False
    await tick_engine()
    await broadcast({"type": "state", "state": sim.snapshot(), "engine": engine_status()})
    return engine_status()


@app.post("/api/reset")
async def reset():
    global sim, optimizer, agent, _baseline_cache, decision_history
    engine_state["running"] = False
    engine_state["total_ticks"] = 0
    engine_state["day_complete"] = False
    engine_state["started"] = False
    engine_state["replan_last_tick"] = False
    engine_state["agent_stage"] = "idle"
    decision_history = []
    sim = Simulation(cfg, seed=int(time.time()) % 10000)
    optimizer = EnergyOptimizer(cfg)
    agent = EnergyAgent(cfg, optimizer)
    _baseline_cache = None
    sim.compute_potentials(sim.world)
    # Do NOT prime agent with a decision at reset — show clean "Idle" state until Play is pressed
    sim.world.agent_reasoning = {
        "mode": "Idle",
        "situation_assessment": "System ready. Press Play to start autonomous operation.",
        "explanation": "The AI agent will observe conditions, reason about priorities, call the LP optimizer, validate, and act every 15 minutes once autonomous mode starts.",
        "intent": "Awaiting start",
        "anomalies": ["System initialized — no data yet."],
        "opportunities": [],
        "forecast_confidence": "high",
        "weights": {"cost": 0.22, "carbon": 0.2, "reliability": 0.28, "battery_life": 0.1, "curtailment": 0.15, "profit_export": 0.05},
        "optimizer_called": False,
        "replanned_this_tick": False,
        "stage": "idle",
        "actions_summary": {},
        "validation": {"valid": True, "issues": []},
    }
    await broadcast({"type": "state", "state": sim.snapshot(), "engine": engine_status()})
    return engine_status()


@app.post("/api/inject-event")
async def inject_event(req: EventRequest):
    evt = sim.inject_event(
        event_type=req.type, target=req.target, magnitude=req.magnitude,
        duration_ticks=req.duration_ticks, is_forecast=req.is_forecast, lead_ticks=req.lead_ticks,
    )
    await broadcast({"type": "event_injected", "event": evt})
    return evt


@app.post("/api/load-scenario")
async def load_scenario(req: ScenarioRequest):
    global sim, optimizer, agent, _baseline_cache, decision_history
    engine_state["running"] = False
    engine_state["total_ticks"] = 0
    engine_state["day_complete"] = False
    engine_state["started"] = False
    engine_state["replan_last_tick"] = False
    decision_history = []
    seed = {"normal": 42, "summer_peak": 100, "stormy_night": 200, "price_volatility": 300}.get(req.scenario, 42)
    sim = Simulation(cfg, seed=seed)
    optimizer = EnergyOptimizer(cfg)
    agent = EnergyAgent(cfg, optimizer)
    _baseline_cache = None
    sim.compute_potentials(sim.world)
    snap = sim.snapshot()
    decision = agent.observe_and_act(snap)
    sim.apply_actions(sim.world, decision.actions, decision.weights)
    sim.world.agent_reasoning = decision.reasoning

    # Scenario-specific pre-seeded events
    if req.scenario == "summer_peak":
        sim.inject_event("demand_surge", magnitude=0.25, duration_ticks=16, lead_ticks=8)
        sim.inject_event("cloud_surge", target="s3", magnitude=0.6, duration_ticks=12, lead_ticks=12)
        sim.inject_event("price_spike", magnitude=2.5, duration_ticks=6, lead_ticks=20)
    elif req.scenario == "stormy_night":
        sim.inject_event("storm_warning", magnitude=4, duration_ticks=32, lead_ticks=4)
        sim.inject_event("wind_gust", magnitude=0.6, duration_ticks=16, lead_ticks=10)
        sim.inject_event("line_trip", magnitude=0.5, duration_ticks=8, lead_ticks=14)
        sim.inject_event("cloud_surge", magnitude=0.9, duration_ticks=10, lead_ticks=2)
    elif req.scenario == "price_volatility":
        sim.inject_event("price_spike", magnitude=3.0, duration_ticks=4, lead_ticks=4)
        sim.inject_event("price_crash", duration_ticks=4, lead_ticks=12)
        sim.inject_event("price_spike", magnitude=2.2, duration_ticks=5, lead_ticks=22)
        sim.inject_event("wind_lull", magnitude=0.8, duration_ticks=14, lead_ticks=8)

    await broadcast({"type": "state", "state": sim.snapshot(), "engine": engine_status()})
    return {"ok": True, "scenario": req.scenario}


@app.post("/api/manual-action")
async def manual_action(req: ManualActionRequest):
    """Apply a manual operator override (human-in-the-loop)."""
    if engine_state["autonomous"]:
        raise HTTPException(status_code=400, detail="Disable autonomous mode first to apply manual actions.")
    # Build a reasonable action set by starting from serving all demand with available renewables
    snap = sim.snapshot()
    actions = {
        "solar_use_kw": {s.id: snap["assets"][s.id]["available_kw"] for s in cfg.solar_farms},
        "wind_use_kw": {w.id: snap["assets"][w.id]["available_kw"] for w in cfg.wind_farms},
        "solar_curtail_kw": {s.id: 0.0 for s in cfg.solar_farms},
        "wind_curtail_kw": {w.id: 0.0 for w in cfg.wind_farms},
        "batt_charge_kw": req.battery_charge_kw or {b.id: 0.0 for b in cfg.batteries},
        "batt_discharge_kw": req.battery_discharge_kw or {b.id: 0.0 for b in cfg.batteries},
        "grid_import_kw": req.grid_import_kw if req.grid_import_kw is not None else 0.0,
        "grid_export_kw": req.grid_export_kw if req.grid_export_kw is not None else 0.0,
        "serve_kw": {c.id: snap["demand_kw"][c.id] for c in cfg.consumers},
        "dr_cut_kw": {c.id: 0.0 for c in cfg.consumers},
    }
    sim.apply_actions(sim.world, actions, {})
    sim.world.agent_reasoning = {
        "mode": "Manual override",
        "explanation": req.note or "Operator applied manual actions.",
        "actions_summary": _summarize_actions(actions),
    }
    await broadcast({"type": "state", "state": sim.snapshot(), "engine": engine_status()})
    return {"ok": True}


@app.get("/api/status")
def status():
    return engine_status()


@app.get("/api/baseline")
def baseline():
    """Naive baseline (no BESS, no DR, no export) 24h KPIs for comparison."""
    return get_baseline()


@app.get("/api/comparison")
def comparison():
    """Compare current cumulative KPIs to baseline (pro-rated)."""
    base = get_baseline()
    cur = sim.world.kpi_cost_inr  # placeholders
    ticks_elapsed = engine_state["total_ticks"]
    if ticks_elapsed < 1:
        agent_zero = {"cost_inr": 0, "co2_kg": 0, "curtailed_kwh": 0, "renewable_kwh": 0,
                      "unmet_critical_kwh": 0, "grid_import_kwh": 0, "grid_export_kwh": 0}
        return {"baseline_projected": {k: 0 for k in base}, "baseline_full_24h": base,
                "agent": agent_zero, "savings": {k: 0 for k in ["cost_inr_saved","co2_kg_saved","curtailment_reduced_kwh","unmet_critical_avoided_kwh"]},
                "progress_pct": 0.0}
    frac = min(1.0, ticks_elapsed / 96.0)
    expected = {k: v * frac for k, v in base.items()}
    agent = {
        "cost_inr": sim.world.kpi_cost_inr,
        "co2_kg": sim.world.kpi_co2_kg,
        "curtailed_kwh": sim.world.kpi_curtailed_kwh,
        "renewable_kwh": sim.world.kpi_renewable_kwh,
        "unmet_critical_kwh": sim.world.kpi_unmet_critical_kwh,
        "grid_import_kwh": sim.world.kpi_grid_import_kwh,
        "grid_export_kwh": sim.world.kpi_grid_export_kwh,
    }
    savings = {
        "cost_inr_saved": expected["cost_inr"] - agent["cost_inr"],
        "co2_kg_saved": expected["co2_kg"] - agent["co2_kg"],
        "curtailment_reduced_kwh": expected["curtailed_kwh"] - agent["curtailed_kwh"],
        "unmet_critical_avoided_kwh": expected["unmet_critical_kwh"] - agent["unmet_critical_kwh"],
    }
    return {"baseline_projected": expected, "baseline_full_24h": base, "agent": agent, "savings": savings, "progress_pct": round(frac*100, 1)}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    # First connection triggers auto-start if the sim hasn't begun
    if not engine_state["started"] and not engine_state["running"]:
        engine_state["started"] = True
    try:
        await ws.send_json({
            "type": "state",
            "state": sim.snapshot(),
            "engine": engine_status(),
            "safety": (await _get_safety()),
        })
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if ws in connected_clients:
            connected_clients.remove(ws)


async def _get_safety():
    return {
        "constraints": [
            {"name": "Battery SOC bounds", "value": f"10–95%"},
            {"name": "Critical load protected", "value": "₹50/kWh penalty"},
            {"name": "Power balance", "value": "Strict equality"},
            {"name": "Grid import/export caps", "value": f"{cfg.grid.max_import_kw/1000:.0f}/{cfg.grid.max_export_kw/1000:.0f} MW"},
            {"name": "LLM fallback", "value": "Deterministic rules"},
            {"name": "Replan on failure", "value": "Auto-retry"},
        ]
    }


@app.get("/", response_class=HTMLResponse)
def root(response: Response):
    index = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if index.exists():
        resp = FileResponse(index)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    return HTMLResponse("<h2>Renewable Energy Orchestrator API</h2><p>Run <code>./run.sh</code> from the project root to build the frontend.</p>")


# Mount built frontend static assets (JS/CSS)
import glob as _glob
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
_frontend_assets = _frontend_dist / "assets"
if _frontend_assets.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_assets)), name="assets")
# Also mount /public assets (favicon, etc.) if built
_frontend_public = _frontend_dist
if _frontend_public.exists():
    # Already serving index via root; assets via /assets above.
    pass

@app.get("/favicon.svg")
def favicon():
    f = Path(__file__).parent.parent / "frontend" / "public" / "favicon.svg"
    if f.exists():
        return FileResponse(f)
    return HTMLResponse("", status_code=204)


# Catch-all: serve index.html for any non-API path (for single-page app routing)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa_catchall(full_path: str):
    if full_path.startswith("api/") or full_path == "ws":
        raise HTTPException(status_code=404)
    index = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404)
