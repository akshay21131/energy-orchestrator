"""Physics/state simulation for solar, wind, battery, demand, prices."""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import numpy as np

from config import Config, SolarFarm, WindFarm, Battery, Consumer, GridConnection


# --- Noise helpers ---
class OUNoise:
    """Ornstein-Uhlenbeck mean-reverting noise for realistic wind/demand fluctuations."""
    def __init__(self, theta=0.15, sigma=0.05, mu=0.0):
        self.theta = theta
        self.sigma = sigma
        self.mu = mu
        self.value = 0.0

    def step(self):
        self.value += self.theta * (self.mu - self.value) + self.sigma * random.gauss(0, 1)
        return self.value


@dataclass
class ForecastPoint:
    lead_minutes: int
    solar_total_kw: float
    wind_total_kw: float
    demand_total_kw: float
    grid_price_inr_per_kwh: float
    confidence: float  # 0..1 (drops with horizon)


@dataclass
class AssetState:
    available_kw: float  # renewable potential / available cap
    output_kw: float  # actually used (after curtailment/action)
    curtailed_kw: float
    soc_kwh: Optional[float] = None
    online: bool = True
    fault_reason: Optional[str] = None


@dataclass
class WorldState:
    sim_time_min: int  # minutes since midnight of sim-day
    day: int
    assets: Dict[str, AssetState] = field(default_factory=dict)
    demand_per_consumer_kw: Dict[str, float] = field(default_factory=dict)
    served_per_consumer_kw: Dict[str, float] = field(default_factory=dict)
    dr_cut_per_consumer_kw: Dict[str, float] = field(default_factory=dict)
    grid_import_kw: float = 0.0
    grid_export_kw: float = 0.0
    grid_price_inr_per_kwh: float = 8.0
    battery_charge_kw: Dict[str, float] = field(default_factory=dict)
    battery_discharge_kw: Dict[str, float] = field(default_factory=dict)
    solar_potential_kw: float = 0.0
    wind_potential_kw: float = 0.0
    total_demand_kw: float = 0.0
    # KPIs (cumulative)
    kpi_cost_inr: float = 0.0
    kpi_co2_kg: float = 0.0
    kpi_curtailed_kwh: float = 0.0
    kpi_renewable_kwh: float = 0.0
    kpi_unmet_critical_kwh: float = 0.0
    kpi_grid_import_kwh: float = 0.0
    kpi_grid_export_kwh: float = 0.0
    # Events / alerts
    active_events: List[Dict[str, Any]] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    forecasts: List[ForecastPoint] = field(default_factory=list)
    # Agent reasoning for this tick
    agent_reasoning: Dict[str, Any] = field(default_factory=dict)
    tick_action_log: List[str] = field(default_factory=list)
    # History
    history: List[Dict[str, Any]] = field(default_factory=list)
    # Day completion summary
    day_summary: Optional[Dict[str, Any]] = None


class Simulation:
    def __init__(self, cfg: Config, seed: int = 42):
        self.cfg = cfg
        random.seed(seed)
        np.random.seed(seed)
        self.wind_noise = OUNoise(theta=0.2, sigma=0.08)
        self.demand_noise = OUNoise(theta=0.3, sigma=0.03)
        self.world = self._initial_state()
        self._pending_events: List[Dict[str, Any]] = []  # injected future events
        self._active_events: List[Dict[str, Any]] = []  # currently active
        self.baseline_kpis: Dict[str, float] = {"cost_inr": 0.0, "co2_kg": 0.0, "renewable_kwh": 0.0,
                                                "curtailed_kwh": 0.0, "unmet_critical_kwh": 0.0,
                                                "grid_import_kwh": 0.0, "grid_export_kwh": 0.0}
        self._baseline_initialized = False

    def _initial_state(self) -> WorldState:
        ws = WorldState(sim_time_min=6 * 60, day=1)  # start at 6 AM
        for s in self.cfg.solar_farms:
            ws.assets[s.id] = AssetState(available_kw=0, output_kw=0, curtailed_kw=0, online=True)
        for w in self.cfg.wind_farms:
            ws.assets[w.id] = AssetState(available_kw=0, output_kw=0, curtailed_kw=0, online=True)
        for b in self.cfg.batteries:
            ws.assets[b.id] = AssetState(
                available_kw=b.max_discharge_kw, output_kw=0, curtailed_kw=0,
                soc_kwh=b.initial_soc_frac * b.capacity_kwh, online=True,
            )
            ws.battery_charge_kw[b.id] = 0.0
            ws.battery_discharge_kw[b.id] = 0.0
        ws.assets[self.cfg.grid.id] = AssetState(
            available_kw=self.cfg.grid.max_import_kw, output_kw=0, curtailed_kw=0, online=True
        )
        for c in self.cfg.consumers:
            ws.demand_per_consumer_kw[c.id] = 0.0
            ws.served_per_consumer_kw[c.id] = 0.0
            ws.dr_cut_per_consumer_kw[c.id] = 0.0
        # Generate initial forecasts
        self._update_forecasts(ws)
        return ws

    # --- Physics ---
    def _solar_potential(self, sf: SolarFarm, hour: float, cloud_factor: float = 1.0) -> float:
        """Solar output in kW using a sine-curve through daylight hours."""
        if hour < sf.sunrise_hour or hour > sf.sunset_hour:
            return 0.0
        day_angle = (hour - sf.sunrise_hour) / (sf.sunset_hour - sf.sunrise_hour)
        base = max(0.0, math.sin(math.pi * day_angle))
        # small seasonal tilt (fixed here for demo)
        return sf.rated_kw * base * cloud_factor * (0.92 + 0.05 * random.random())

    def _wind_potential(self, wf: WindFarm, wind_speed: float) -> float:
        if wind_speed < wf.cut_in_ms or wind_speed >= wf.cut_out_ms:
            return 0.0
        if wind_speed >= wf.rated_ms:
            return wf.rated_kw
        frac = (wind_speed - wf.cut_in_ms) / (wf.rated_ms - wf.cut_in_ms)
        return wf.rated_kw * (frac ** 3)

    def _demand_profile(self, consumer: Consumer, hour: float, day: int) -> float:
        """Industrial/commercial demand with double hump."""
        is_weekend = ((day - 1) % 7) >= 5  # day starts at 1; days 6,7 = weekend
        scale = 0.55 if is_weekend else 1.0
        # Morning ramp (7-10), lunch dip (12-13), evening ramp (17-20)
        morning = math.exp(-((hour - 9.0) ** 2) / 8.0)
        evening = math.exp(-((hour - 18.5) ** 2) / 10.0)
        lunch_dip = 1.0 - 0.25 * math.exp(-((hour - 12.5) ** 2) / 1.0)
        # night base
        night_base = 0.25 + 0.05 * math.sin(hour / 24 * 2 * math.pi)
        shape = max(night_base, (morning + evening * 0.8)) * lunch_dip
        return consumer.peak_demand_kw * shape * scale

    def _grid_price(self, hour: float, demand_kw: float, total_capacity_kw: float) -> float:
        """Time-varying price with demand correlation and occasional spikes."""
        base = 5.5  # off-peak
        peak_uplift = 4.0 * math.exp(-((hour - 18.5) ** 2) / 6.0)
        morning_uplift = 2.5 * math.exp(-((hour - 9.0) ** 2) / 6.0)
        demand_ratio = demand_kw / max(1, total_capacity_kw)
        price = base + peak_uplift + morning_uplift + 2.0 * max(0, demand_ratio - 0.6)
        # Random spike ~5% of ticks + guaranteed high-price evening peak, low-price pre-dawn window
        if hour >= 18 and hour <= 20:
            price *= random.uniform(1.3, 2.2)  # structurally higher evening peak
        if hour >= 2 and hour <= 5:
            price *= random.uniform(0.4, 0.7)  # off-peak pre-dawn
        if random.random() < 0.05:
            price *= random.uniform(1.8, 3.0)
        return max(2.0, price + random.gauss(0, 0.3))

    # --- Events ---
    def inject_event(self, event_type: str, target: Optional[str] = None,
                     magnitude: float = 1.0, duration_ticks: int = 8,
                     is_forecast: bool = False, lead_ticks: int = 0):
        evt = {
            "type": event_type,
            "target": target,
            "magnitude": magnitude,
            "duration_ticks": duration_ticks,
            "remaining_ticks": duration_ticks,
            "is_forecast": is_forecast,
            "lead_ticks": lead_ticks,
            "start_sim_time": self.world.sim_time_min + lead_ticks * self.cfg.tick_minutes,
            "description": self._describe_event(event_type, target, magnitude),
        }
        self._pending_events.append(evt)
        return evt

    def _describe_event(self, etype: str, target: str, mag: float) -> str:
        if etype == "cloud_surge":
            return f"Cloud cover reduces {target or 'solar farms'} by {int(mag*100)}%"
        if etype == "wind_gust":
            return f"Wind gust increases {target or 'wind farms'} by {int(mag*100)}%"
        if etype == "wind_lull":
            return f"Wind lull reduces {target or 'wind farms'} by {int(mag*100)}%"
        if etype == "price_spike":
            return f"Grid price spikes {mag:.1f}x"
        if etype == "price_crash":
            return f"Grid price crashes (negative pricing event)"
        if etype == "battery_fault":
            return f"Battery {target} goes OFFLINE"
        if etype == "battery_recover":
            return f"Battery {target} returns ONLINE"
        if etype == "line_trip":
            return f"Transmission line trips — capacity reduced by {int(mag*100)}%"
        if etype == "demand_surge":
            return f"Demand surge on {target or 'all loads'} (+{int(mag*100)}%)"
        if etype == "storm_warning":
            return f"Storm warning — wind/solar volatility expected in {mag*60:.0f} min"
        if etype == "maintenance":
            return f"Scheduled maintenance on {target}"
        return f"Event: {etype}"

    def _apply_events(self, ws: WorldState, cloud_factor: Dict[str, float],
                      wind_multiplier: Dict[str, float], demand_multiplier: Dict[str, float],
                      price_multiplier: float, grid_cap_scale: float):
        # Promote pending events that are due to active
        new_active = []
        for evt in list(self._pending_events):
            if evt["lead_ticks"] > 0:
                evt["lead_ticks"] -= 1
                # stay as pending forecast, push to alerts
                continue
            new_active.append(evt)
        self._pending_events = [e for e in self._pending_events if e["lead_ticks"] > 0]
        self._active_events.extend(new_active)

        # Process active events
        remaining = []
        ws.alerts = []
        for evt in self._active_events:
            etype = evt["type"]
            tgt = evt["target"]
            mag = evt["magnitude"]
            if etype == "cloud_surge":
                if tgt:
                    cloud_factor[tgt] = min(cloud_factor.get(tgt, 1.0), 1.0 - mag)
                else:
                    for s in self.cfg.solar_farms:
                        cloud_factor[s.id] = min(cloud_factor[s.id], 1.0 - mag)
            elif etype == "wind_gust":
                if tgt:
                    wind_multiplier[tgt] = wind_multiplier.get(tgt, 1.0) + mag
                else:
                    for w in self.cfg.wind_farms:
                        wind_multiplier[w.id] = wind_multiplier.get(w.id, 1.0) + mag
            elif etype == "wind_lull":
                if tgt:
                    wind_multiplier[tgt] = max(0.0, wind_multiplier.get(tgt, 1.0) - mag)
                else:
                    for w in self.cfg.wind_farms:
                        wind_multiplier[w.id] = max(0.0, wind_multiplier.get(w.id, 1.0) - mag)
            elif etype == "price_spike":
                price_multiplier *= mag
            elif etype == "price_crash":
                price_multiplier = 0.2
            elif etype == "battery_fault" and tgt:
                ws.assets[tgt].online = False
                ws.assets[tgt].fault_reason = "fault"
            elif etype == "battery_recover" and tgt:
                ws.assets[tgt].online = True
                ws.assets[tgt].fault_reason = None
            elif etype == "line_trip":
                grid_cap_scale *= (1.0 - mag)
            elif etype == "demand_surge":
                if tgt and tgt in demand_multiplier:
                    demand_multiplier[tgt] *= (1.0 + mag)
                else:
                    for cid in demand_multiplier:
                        demand_multiplier[cid] *= (1.0 + mag)
            elif etype == "storm_warning":
                ws.alerts.append(evt["description"])
            elif etype == "maintenance" and tgt:
                ws.assets[tgt].online = False
                ws.assets[tgt].fault_reason = "maintenance"

            evt["remaining_ticks"] -= 1
            if evt["remaining_ticks"] > 0:
                remaining.append(evt)
            else:
                # recovery actions
                if etype == "battery_fault" and tgt:
                    ws.assets[tgt].online = True
                    ws.assets[tgt].fault_reason = None
                if etype == "maintenance" and tgt:
                    ws.assets[tgt].online = True
                    ws.assets[tgt].fault_reason = None
                ws.alerts.append(f"Resolved: {evt['description']}")
        self._active_events = remaining
        # Persist active events for visibility
        ws.active_events = [dict(e, tick_messages=[]) for e in self._active_events]
        # Also include forecast events (pending)
        ws.alerts.extend([f"Forecast: {e['description']} (in {e['lead_ticks']} ticks)" for e in self._pending_events])
        return price_multiplier, grid_cap_scale

    def _update_forecasts(self, ws: WorldState, horizons=(1, 4, 8, 16, 32)):
        ws.forecasts = []
        for h in horizons:
            future_min = ws.sim_time_min + h * self.cfg.tick_minutes
            fhour = (future_min % (24 * 60)) / 60.0
            fday = ws.day + (future_min // (24 * 60))
            # approximate solar/wind/demand/price at future hour
            cloud_est = random.uniform(0.7, 1.0)
            solar = sum(self._solar_potential(s, fhour, cloud_est) for s in self.cfg.solar_farms)
            wind_speed = 8.0 + 4.0 * math.sin(fhour / 24 * 2 * math.pi) + random.gauss(0, 2)
            wind = sum(self._wind_potential(w, max(0, wind_speed)) for w in self.cfg.wind_farms)
            dem = sum(self._demand_profile(c, fhour, fday) for c in self.cfg.consumers)
            dem *= (1 + self.demand_noise.sigma * 2 * random.random())
            total_cap = sum(s.rated_kw for s in self.cfg.solar_farms) + sum(w.rated_kw for w in self.cfg.wind_farms)
            price = self._grid_price(fhour, dem, total_cap)
            # confidence decays with horizon — sharper drop further out
            conf = max(0.35, 1.0 - 0.025 * h)
            if h <= 4:
                conf = max(conf, 0.85)
            ws.forecasts.append(ForecastPoint(
                lead_minutes=h * self.cfg.tick_minutes,
                solar_total_kw=solar,
                wind_total_kw=wind,
                demand_total_kw=dem,
                grid_price_inr_per_kwh=price,
                confidence=conf,
            ))

    def compute_potentials(self, ws: WorldState) -> Dict[str, Any]:
        """Compute renewable potentials, demand, and price for the current tick.
        Does NOT apply actions — that's done by apply_actions after optimizer.
        Returns a context dict used by the agent.
        """
        hour = (ws.sim_time_min % (24 * 60)) / 60.0

        cloud_factor = {s.id: 1.0 for s in self.cfg.solar_farms}
        wind_multiplier = {w.id: 1.0 for w in self.cfg.wind_farms}
        demand_multiplier = {c.id: 1.0 for c in self.cfg.consumers}
        price_multiplier = 1.0
        grid_cap_scale = 1.0

        # reset online status check
        for b in self.cfg.batteries:
            if ws.assets[b.id].fault_reason in ("fault", "maintenance"):
                ws.assets[b.id].online = False

        price_multiplier, grid_cap_scale = self._apply_events(
            ws, cloud_factor, wind_multiplier, demand_multiplier, price_multiplier, grid_cap_scale
        )

        # Solar
        solar_pot = 0.0
        for s in self.cfg.solar_farms:
            cf = cloud_factor[s.id] * (0.9 + 0.1 * random.random())
            kw = self._solar_potential(s, hour, cf) if ws.assets[s.id].online else 0.0
            ws.assets[s.id].available_kw = kw
            solar_pot += kw

        # Wind
        wind_pot = 0.0
        for w in self.cfg.wind_farms:
            base_speed = 7.0 + 4.0 * math.sin(hour / 24 * 2 * math.pi + 1.3)
            base_speed += self.wind_noise.step() * 6.0
            base_speed = max(0.0, base_speed) * wind_multiplier[w.id]
            kw = self._wind_potential(w, base_speed) if ws.assets[w.id].online else 0.0
            ws.assets[w.id].available_kw = kw
            wind_pot += kw

        # Demand
        total_demand = 0.0
        for c in self.cfg.consumers:
            d = self._demand_profile(c, hour, ws.day)
            d *= demand_multiplier[c.id] * (1.0 + self.demand_noise.step())
            d = max(0.0, d)
            ws.demand_per_consumer_kw[c.id] = d
            total_demand += d

        # Price
        total_renewable_cap = sum(s.rated_kw for s in self.cfg.solar_farms) + sum(w.rated_kw for w in self.cfg.wind_farms)
        ws.grid_price_inr_per_kwh = self._grid_price(hour, total_demand, total_renewable_cap) * price_multiplier

        # Grid capacity (scaled by line trip events)
        ws.assets[self.cfg.grid.id].available_kw = self.cfg.grid.max_import_kw * grid_cap_scale

        # Update forecasts
        self._update_forecasts(ws)

        ws.solar_potential_kw = solar_pot
        ws.wind_potential_kw = wind_pot
        ws.total_demand_kw = total_demand
        return {
            "hour": hour, "solar_pot": solar_pot, "wind_pot": wind_pot,
            "total_demand": total_demand, "price": ws.grid_price_inr_per_kwh,
            "grid_cap_scale": grid_cap_scale,
        }

    def apply_actions(self, ws: WorldState, actions: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, float]:
        """Apply agent-chosen actions (charge/discharge/import/export/curtail/DR) and update state + KPIs.
        Actions dict expected from optimizer:
          { 'solar_use_kw':{id:kw}, 'wind_use_kw':{id:kw}, 'solar_curtail_kw':{id:kw}, 'wind_curtail_kw':{id:kw},
            'batt_charge_kw':{id:kw}, 'batt_discharge_kw':{id:kw}, 'grid_import_kw':kw, 'grid_export_kw':kw,
            'serve_kw':{id:kw}, 'dr_cut_kw':{id:kw} }
        Returns KPI deltas.
        """
        dt_hours = self.cfg.tick_minutes / 60.0
        deltas = {"cost": 0.0, "co2": 0.0, "curtailed_kwh": 0.0, "renewable_kwh": 0.0,
                  "unmet_critical_kwh": 0.0, "grid_import_kwh": 0.0, "grid_export_kwh": 0.0}
        log = []

        # Renewable use/curtail
        for s in self.cfg.solar_farms:
            use = min(actions.get("solar_use_kw", {}).get(s.id, 0), ws.assets[s.id].available_kw)
            curtail = max(0, ws.assets[s.id].available_kw - use)
            ws.assets[s.id].output_kw = use
            ws.assets[s.id].curtailed_kw = curtail
            deltas["curtailed_kwh"] += curtail * dt_hours
            deltas["renewable_kwh"] += use * dt_hours
        for w in self.cfg.wind_farms:
            use = min(actions.get("wind_use_kw", {}).get(w.id, 0), ws.assets[w.id].available_kw)
            curtail = max(0, ws.assets[w.id].available_kw - use)
            ws.assets[w.id].output_kw = use
            ws.assets[w.id].curtailed_kw = curtail
            deltas["curtailed_kwh"] += curtail * dt_hours
            deltas["renewable_kwh"] += use * dt_hours

        # Batteries
        for b in self.cfg.batteries:
            ast = ws.assets[b.id]
            charge = actions.get("batt_charge_kw", {}).get(b.id, 0.0) if ast.online else 0.0
            discharge = actions.get("batt_discharge_kw", {}).get(b.id, 0.0) if ast.online else 0.0
            charge = min(charge, b.max_charge_kw)
            discharge = min(discharge, b.max_discharge_kw)
            # Update SOC
            new_soc = (ast.soc_kwh or 0) + charge * b.charge_efficiency * dt_hours - discharge / b.discharge_efficiency * dt_hours
            new_soc = max(b.min_soc_frac * b.capacity_kwh, min(b.max_soc_frac * b.capacity_kwh, new_soc))
            ast.soc_kwh = new_soc
            ast.output_kw = discharge - charge
            ws.battery_charge_kw[b.id] = charge
            ws.battery_discharge_kw[b.id] = discharge
            deltas["cost"] += discharge * dt_hours * b.throughput_cost_inr_per_kwh
            if charge > 100 or discharge > 100:
                log.append(f"{b.name}: charge {charge:.0f} kW / discharge {discharge:.0f} kW (SOC {new_soc/b.capacity_kwh*100:.0f}%)")

        # Grid
        imp = max(0.0, actions.get("grid_import_kw", 0.0))
        exp = max(0.0, actions.get("grid_export_kw", 0.0))
        ws.grid_import_kw = imp
        ws.grid_export_kw = exp
        ws.assets[self.cfg.grid.id].output_kw = imp - exp
        import_cost = imp * dt_hours * ws.grid_price_inr_per_kwh
        export_revenue = exp * dt_hours * self.cfg.grid_export_price_inr_per_kwh
        deltas["cost"] += import_cost - export_revenue
        deltas["co2"] += imp * dt_hours * self.cfg.co2_per_kwh_grid_kg
        deltas["grid_import_kwh"] += imp * dt_hours
        deltas["grid_export_kwh"] += exp * dt_hours

        # Demand / DR
        for c in self.cfg.consumers:
            demand = ws.demand_per_consumer_kw[c.id]
            serve = min(demand, max(0, actions.get("serve_kw", {}).get(c.id, demand)))
            dr_cut = max(0, actions.get("dr_cut_kw", {}).get(c.id, 0.0))
            served = min(demand - dr_cut, serve)
            unmet = max(0, demand - served - dr_cut)
            critical_demand = demand * c.critical_fraction
            unmet_critical = max(0, critical_demand - min(critical_demand, served))
            ws.served_per_consumer_kw[c.id] = served
            ws.dr_cut_per_consumer_kw[c.id] = dr_cut
            deltas["unmet_critical_kwh"] += unmet_critical * dt_hours
            deltas["cost"] += unmet_critical * dt_hours * self.cfg.unmet_critical_penalty_inr_per_kwh
            deltas["cost"] += max(0, unmet - unmet_critical) * dt_hours * self.cfg.unmet_noncritical_penalty_inr_per_kwh
            deltas["cost"] -= dr_cut * dt_hours * self.cfg.demand_response_reward_inr_per_kwh

        # Curtailment penalty
        deltas["cost"] += deltas["curtailed_kwh"] * self.cfg.curtailment_penalty_inr_per_kwh

        # Update cumulative KPIs
        ws.kpi_cost_inr += deltas["cost"]
        ws.kpi_co2_kg += deltas["co2"]
        ws.kpi_curtailed_kwh += deltas["curtailed_kwh"]
        ws.kpi_renewable_kwh += deltas["renewable_kwh"]
        ws.kpi_unmet_critical_kwh += deltas["unmet_critical_kwh"]
        ws.kpi_grid_import_kwh += deltas["grid_import_kwh"]
        ws.kpi_grid_export_kwh += deltas["grid_export_kwh"]
        ws.tick_action_log = log
        return deltas

    def advance_time(self):
        self.world.sim_time_min += self.cfg.tick_minutes
        if self.world.sim_time_min >= 24 * 60:
            self.world.sim_time_min -= 24 * 60
            self.world.day += 1

    def snapshot(self) -> Dict[str, Any]:
        """Return JSON-serializable snapshot for frontend."""
        ws = self.world
        assets_out = {}
        for aid, ast in ws.assets.items():
            entry = {
                "available_kw": round(ast.available_kw, 1),
                "output_kw": round(ast.output_kw, 1),
                "curtailed_kw": round(ast.curtailed_kw, 1),
                "online": ast.online,
                "fault_reason": ast.fault_reason,
            }
            if ast.soc_kwh is not None:
                bcfg = next((b for b in self.cfg.batteries if b.id == aid), None)
                if bcfg:
                    entry["soc_kwh"] = round(ast.soc_kwh, 1)
                    entry["soc_frac"] = round(ast.soc_kwh / bcfg.capacity_kwh, 3)
                    entry["capacity_kwh"] = bcfg.capacity_kwh
                    entry["max_charge_kw"] = bcfg.max_charge_kw
                    entry["max_discharge_kw"] = bcfg.max_discharge_kw
            assets_out[aid] = entry
        hour = (ws.sim_time_min % 1440) / 60
        total_gen = sum(a["output_kw"] for a in assets_out.values() if a["output_kw"] > 0)
        return {
            "sim_time_min": ws.sim_time_min,
            "day": ws.day,
            "time_of_day": f"{int(hour):02d}:{int((hour % 1) * 60):02d}",
            "hour": round(hour, 2),
            "assets": assets_out,
            "demand_kw": {cid: round(v, 1) for cid, v in ws.demand_per_consumer_kw.items()},
            "served_kw": {cid: round(v, 1) for cid, v in ws.served_per_consumer_kw.items()},
            "dr_cut_kw": {cid: round(v, 1) for cid, v in ws.dr_cut_per_consumer_kw.items()},
            "grid_import_kw": round(ws.grid_import_kw, 1),
            "grid_export_kw": round(ws.grid_export_kw, 1),
            "batt_charge_kw": {k: round(v, 1) for k, v in ws.battery_charge_kw.items()},
            "batt_discharge_kw": {k: round(v, 1) for k, v in ws.battery_discharge_kw.items()},
            "solar_potential_kw": round(ws.solar_potential_kw, 1),
            "wind_potential_kw": round(ws.wind_potential_kw, 1),
            "total_demand_kw": round(ws.total_demand_kw, 1),
            "grid_price_inr_per_kwh": round(ws.grid_price_inr_per_kwh, 2),
            "kpis": {
                "cost_inr": round(ws.kpi_cost_inr, 0),
                "co2_kg": round(ws.kpi_co2_kg, 0),
                "curtailed_kwh": round(ws.kpi_curtailed_kwh, 0),
                "renewable_kwh": round(ws.kpi_renewable_kwh, 0),
                "unmet_critical_kwh": round(ws.kpi_unmet_critical_kwh, 0),
                "grid_import_kwh": round(ws.kpi_grid_import_kwh, 0),
                "grid_export_kwh": round(ws.kpi_grid_export_kwh, 0),
            },
            "alerts": list(ws.alerts),
            "active_events": ws.active_events,
            "forecasts": [
                {"lead_minutes": f.lead_minutes, "solar_total_kw": round(f.solar_total_kw, 0),
                 "wind_total_kw": round(f.wind_total_kw, 0), "demand_total_kw": round(f.demand_total_kw, 0),
                 "price": round(f.grid_price_inr_per_kwh, 2), "confidence": round(f.confidence, 2)}
                for f in ws.forecasts
            ],
            "agent_reasoning": ws.agent_reasoning,
            "tick_action_log": list(ws.tick_action_log),
            "total_renewable_output_kw": round(sum(
                ws.assets[s.id].output_kw for s in self.cfg.solar_farms
            ) + sum(ws.assets[w.id].output_kw for w in self.cfg.wind_farms), 1),
            "day_summary": ws.day_summary,
        }
