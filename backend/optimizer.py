"""Multi-objective optimizer (MILP/LP) for renewable energy orchestration.

The optimizer is called by the agent with dynamically chosen weights
(cost, carbon, reliability, battery_life, curtailment) and returns
physically feasible MW/kW flows across all assets.
"""
from typing import Dict, Any, Optional, Tuple

import pulp

from config import Config


class EnergyOptimizer:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def solve(self, state_snapshot: Dict[str, Any], weights: Dict[str, float],
              extra_constraints: Optional[Dict[str, Any]] = None,
              must_hold_reserve_kw: float = 0.0) -> Dict[str, Any]:
        """Run one LP optimization.

        Args:
            state_snapshot: current potentials/demand/SOC/etc. (from simulation.compute_potentials output)
            weights: objective weights summing ~1 (cost, carbon, reliability, battery_life, curtailment, profit_export)
            extra_constraints: optional hard constraints (e.g., max_grid_import_kw, battery_hold_reserve_frac)
            must_hold_reserve_kw: reserve capacity the agent wants to preserve
        Returns:
            actions dict + diagnostics
        """
        cfg = self.cfg
        dt_hours = cfg.tick_minutes / 60.0

        # Pull values from state
        solar_avail = {s.id: state_snapshot["assets"][s.id]["available_kw"] for s in cfg.solar_farms}
        wind_avail = {w.id: state_snapshot["assets"][w.id]["available_kw"] for w in cfg.wind_farms}
        demand_kw = state_snapshot["demand_kw"]
        price = state_snapshot["grid_price_inr_per_kwh"]
        # Battery state
        batt_soc = {}
        batt_online = {}
        for b in cfg.batteries:
            ast = state_snapshot["assets"][b.id]
            batt_soc[b.id] = ast.get("soc_kwh", b.initial_soc_frac * b.capacity_kwh)
            batt_online[b.id] = ast.get("online", True)
        # Grid
        grid_avail_imp = state_snapshot["assets"][cfg.grid.id].get("available_kw", cfg.grid.max_import_kw)
        grid_avail_exp = cfg.grid.max_export_kw

        extra_constraints = extra_constraints or {}
        max_grid_import = min(grid_avail_imp, extra_constraints.get("max_grid_import_kw", grid_avail_imp))
        max_grid_export = min(grid_avail_exp, extra_constraints.get("max_grid_export_kw", grid_avail_exp))
        battery_hold_reserve_frac = extra_constraints.get("battery_hold_reserve_frac", 0.0)

        w = {
            "cost": weights.get("cost", 0.25),
            "carbon": weights.get("carbon", 0.20),
            "reliability": weights.get("reliability", 0.25),
            "battery_life": weights.get("battery_life", 0.15),
            "curtailment": weights.get("curtailment", 0.10),
            "profit_export": weights.get("profit_export", 0.05),
        }

        prob = pulp.LpProblem("energy_orchestrator", pulp.LpMinimize)

        # --- Variables ---
        solar_use = {s.id: pulp.LpVariable(f"s_use_{s.id}", 0, solar_avail[s.id]) for s in cfg.solar_farms}
        wind_use = {wf.id: pulp.LpVariable(f"w_use_{wf.id}", 0, wind_avail[wf.id]) for wf in cfg.wind_farms}
        solar_curtail = {s.id: pulp.LpVariable(f"s_cur_{s.id}", 0, solar_avail[s.id]) for s in cfg.solar_farms}
        wind_curtail = {wf.id: pulp.LpVariable(f"w_cur_{wf.id}", 0, wind_avail[wf.id]) for wf in cfg.wind_farms}

        batt_charge = {}
        batt_discharge = {}
        for b in cfg.batteries:
            max_chg = b.max_charge_kw if batt_online[b.id] else 0
            max_dis = b.max_discharge_kw if batt_online[b.id] else 0
            batt_charge[b.id] = pulp.LpVariable(f"b_chg_{b.id}", 0, max_chg)
            batt_discharge[b.id] = pulp.LpVariable(f"b_dis_{b.id}", 0, max_dis)

        grid_import = pulp.LpVariable("g_imp", 0, max_grid_import)
        grid_export = pulp.LpVariable("g_exp", 0, max_grid_export)

        serve = {c.id: pulp.LpVariable(f"sv_{c.id}", 0, demand_kw[c.id]) for c in cfg.consumers}
        dr_cut = {c.id: pulp.LpVariable(f"dr_{c.id}", 0, demand_kw[c.id] * 0.15) for c in cfg.consumers}  # max 15% DR
        unmet = {c.id: pulp.LpVariable(f"um_{c.id}", 0, demand_kw[c.id]) for c in cfg.consumers}
        unmet_critical = {c.id: pulp.LpVariable(f"umc_{c.id}", 0, demand_kw[c.id] * c.critical_fraction) for c in cfg.consumers}

        # Power balance
        total_gen = (
            pulp.lpSum(solar_use.values()) + pulp.lpSum(wind_use.values())
            + pulp.lpSum(batt_discharge.values()) + grid_import
        )
        total_consume = (
            pulp.lpSum(serve.values()) + pulp.lpSum(batt_charge.values())
            + pulp.lpSum(dr_cut.values()) + grid_export
        )
        prob += total_gen == total_consume, "power_balance"

        # Curtail = avail - use
        for s in cfg.solar_farms:
            prob += solar_use[s.id] + solar_curtail[s.id] == solar_avail[s.id], f"solar_bal_{s.id}"
        for wf in cfg.wind_farms:
            prob += wind_use[wf.id] + wind_curtail[wf.id] == wind_avail[wf.id], f"wind_bal_{wf.id}"

        # Demand balance
        for c in cfg.consumers:
            prob += serve[c.id] + unmet[c.id] + dr_cut[c.id] == demand_kw[c.id], f"dem_bal_{c.id}"
            prob += unmet_critical[c.id] <= unmet[c.id], f"umc_bound_{c.id}"
            critical_demand = demand_kw[c.id] * c.critical_fraction
            # unmet_critical is that portion of unmet that cuts into critical load
            prob += unmet_critical[c.id] >= critical_demand - serve[c.id], f"umc_def_{c.id}"

        # Battery SOC constraints
        for b in cfg.batteries:
            if not batt_online[b.id]:
                continue
            new_soc = (
                batt_soc[b.id]
                + batt_charge[b.id] * b.charge_efficiency * dt_hours
                - batt_discharge[b.id] * (1.0 / b.discharge_efficiency) * dt_hours
            )
            min_soc = max(b.min_soc_frac * b.capacity_kwh,
                          b.min_soc_frac * b.capacity_kwh + must_hold_reserve_kw * dt_hours)
            # Reserve: keep SOC above hold_reserve_frac * capacity if requested
            min_soc = max(min_soc, battery_hold_reserve_frac * b.capacity_kwh)
            prob += new_soc >= min_soc, f"batt_min_soc_{b.id}"
            prob += new_soc <= b.max_soc_frac * b.capacity_kwh, f"batt_max_soc_{b.id}"

        # Prevent simultaneous charge and discharge from the same battery (mild penalty instead of binary;
        # objective structure naturally separates, but add soft penalty for robustness)
        # (Using continuous vars; objective cost weights dis-incentivize simultaneous charge+discharge.)

        # --- Objective ---
        # Cost (grid import cost - export revenue + throughput cost + penalties)
        cost_term = (
            grid_import * dt_hours * price
            - grid_export * dt_hours * cfg.grid_export_price_inr_per_kwh
            + pulp.lpSum(batt_discharge[b.id] * dt_hours * b.throughput_cost_inr_per_kwh for b in cfg.batteries)
            + pulp.lpSum(solar_curtail[s.id] * dt_hours * cfg.curtailment_penalty_inr_per_kwh for s in cfg.solar_farms)
            + pulp.lpSum(wind_curtail[wf.id] * dt_hours * cfg.curtailment_penalty_inr_per_kwh for wf in cfg.wind_farms)
            + pulp.lpSum(unmet_critical[c.id] * dt_hours * cfg.unmet_critical_penalty_inr_per_kwh for c in cfg.consumers)
            + pulp.lpSum((unmet[c.id] - unmet_critical[c.id]) * dt_hours * cfg.unmet_noncritical_penalty_inr_per_kwh for c in cfg.consumers)
            - pulp.lpSum(dr_cut[c.id] * dt_hours * cfg.demand_response_reward_inr_per_kwh for c in cfg.consumers)
        )
        carbon_term = grid_import * dt_hours * cfg.co2_per_kwh_grid_kg
        reliability_term = (
            pulp.lpSum(unmet_critical[c.id] for c in cfg.consumers) * 100
            + pulp.lpSum(unmet[c.id] - unmet_critical[c.id] for c in cfg.consumers) * 10
        )
        battery_life_term = pulp.lpSum(
            (batt_charge[b.id] + batt_discharge[b.id]) for b in cfg.batteries
        ) * dt_hours
        curtailment_term = (
            pulp.lpSum(solar_curtail[s.id] for s in cfg.solar_farms)
            + pulp.lpSum(wind_curtail[wf.id] for wf in cfg.wind_farms)
        ) * dt_hours
        profit_export_term = -grid_export * dt_hours * price * 0.5  # reward exporting at high price

        # Normalize to roughly comparable scales
        # These scale factors make each term order-of-magnitude comparable before applying weights
        norm_cost = 1.0 / max(1.0, sum(demand_kw.values()) * dt_hours * 10.0)
        norm_carbon = 1.0 / max(1.0, sum(demand_kw.values()) * dt_hours * cfg.co2_per_kwh_grid_kg)
        norm_rel = 1.0 / max(1.0, sum(demand_kw.values()) * 100)
        norm_batt = 1.0 / max(1.0, sum(b.max_discharge_kw for b in cfg.batteries) * dt_hours * 5)
        norm_curt = 1.0 / max(1.0, (sum(s.rated_kw for s in cfg.solar_farms) + sum(wf.rated_kw for wf in cfg.wind_farms)) * dt_hours)
        norm_profit = norm_cost

        objective = (
            w["cost"] * norm_cost * cost_term
            + w["carbon"] * norm_carbon * carbon_term
            + w["reliability"] * norm_rel * reliability_term
            + w["battery_life"] * norm_batt * battery_life_term
            + w["curtailment"] * norm_curt * curtailment_term
            + w["profit_export"] * norm_profit * profit_export_term
        )
        prob += objective

        # Solve
        solver = pulp.PULP_CBC_CMD(msg=False)
        prob.solve(solver)
        status = pulp.LpStatus[prob.status]

        if status != "Optimal":
            # Fallback: reliability-only solve
            return self._fallback_solution(state_snapshot, solar_avail, wind_avail, demand_kw, batt_soc, batt_online,
                                           grid_avail_imp, dt_hours)

        # Extract solution
        actions = {
            "solar_use_kw": {s.id: solar_use[s.id].value() for s in cfg.solar_farms},
            "wind_use_kw": {wf.id: wind_use[wf.id].value() for wf in cfg.wind_farms},
            "solar_curtail_kw": {s.id: solar_curtail[s.id].value() for s in cfg.solar_farms},
            "wind_curtail_kw": {wf.id: wind_curtail[wf.id].value() for wf in cfg.wind_farms},
            "batt_charge_kw": {b.id: batt_charge[b.id].value() for b in cfg.batteries},
            "batt_discharge_kw": {b.id: batt_discharge[b.id].value() for b in cfg.batteries},
            "grid_import_kw": grid_import.value(),
            "grid_export_kw": grid_export.value(),
            "serve_kw": {c.id: serve[c.id].value() for c in cfg.consumers},
            "dr_cut_kw": {c.id: dr_cut[c.id].value() for c in cfg.consumers},
        }
        diagnostics = {
            "status": status,
            "objective_value": pulp.value(prob.objective),
            "weights_used": w,
            "must_hold_reserve_kw": must_hold_reserve_kw,
            "price_inr_per_kwh": price,
        }
        return {"actions": actions, "diagnostics": diagnostics}

    def _fallback_solution(self, state_snapshot, solar_avail, wind_avail, demand_kw,
                           batt_soc, batt_online, grid_avail_imp, dt_hours):
        """Greedy reliability-first fallback if LP fails."""
        actions = {
            "solar_use_kw": dict(solar_avail),
            "wind_use_kw": dict(wind_avail),
            "solar_curtail_kw": {k: 0.0 for k in solar_avail},
            "wind_curtail_kw": {k: 0.0 for k in wind_avail},
            "batt_charge_kw": {b.id: 0.0 for b in self.cfg.batteries},
            "batt_discharge_kw": {b.id: 0.0 for b in self.cfg.batteries},
            "grid_import_kw": 0.0,
            "grid_export_kw": 0.0,
            "serve_kw": {},
            "dr_cut_kw": {c.id: 0.0 for c in self.cfg.consumers},
        }
        total_renew = sum(solar_avail.values()) + sum(wind_avail.values())
        total_demand = sum(demand_kw.values())
        surplus = total_renew - total_demand
        # serve all demand with renewables first
        for c in self.cfg.consumers:
            actions["serve_kw"][c.id] = demand_kw[c.id]
        if surplus < 0:
            # Discharge batteries, then import
            deficit = -surplus
            for b in self.cfg.batteries:
                if not batt_online[b.id]:
                    continue
                available_energy = max(0, batt_soc[b.id] - b.min_soc_frac * b.capacity_kwh)
                available_kw = min(b.max_discharge_kw, available_energy / dt_hours)
                use = min(deficit, available_kw)
                actions["batt_discharge_kw"][b.id] = use
                deficit -= use
                if deficit <= 0:
                    break
            actions["grid_import_kw"] = min(grid_avail_imp, max(0, deficit))
        else:
            # Charge batteries with surplus, then export
            for b in self.cfg.batteries:
                if not batt_online[b.id]:
                    continue
                headroom_kwh = b.max_soc_frac * b.capacity_kwh - batt_soc[b.id]
                headroom_kw = min(b.max_charge_kw, headroom_kwh / dt_hours / b.charge_efficiency)
                use = min(surplus, headroom_kw)
                actions["batt_charge_kw"][b.id] = use
                surplus -= use
                if surplus <= 0:
                    break
            actions["grid_export_kw"] = min(self.cfg.grid.max_export_kw, max(0, surplus))
        return {"actions": actions, "diagnostics": {"status": "FallbackGreedy", "weights_used": {"reliability": 1.0}}}
