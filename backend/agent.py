"""LLM-based agentic brain for the Energy Orchestrator.

The agent:
  1. Observes current state + forecasts + alerts
  2. Reasons about anomalies, opportunities, uncertainty
  3. Selects objective weights and constraints
  4. Calls the optimizer tool
  5. Validates the plan; if bad, revises & re-optimizes (reflect/replan)
  6. Emits structured action plan + natural-language explanation

If an LLM API key is not configured the agent falls back to a deterministic
rule-based reasoner so the demo always works.
"""
import json
import os
import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import Config
from optimizer import EnergyOptimizer


# --- Optional LLM client ---
class LLMClient:
    def __init__(self):
        self.api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.provider = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.provider = "anthropic"
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            self.provider = "gemini"
            self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        elif os.environ.get("OPENAI_API_KEY"):
            self.provider = "openai"
        self.available = self.provider is not None and self.api_key is not None

    def complete_json(self, system_prompt: str, user_prompt: str, max_retries: int = 2) -> Dict[str, Any]:
        if not self.available:
            raise RuntimeError("No LLM configured")
        try:
            if self.provider == "openai":
                import openai
                client = openai.OpenAI(api_key=self.api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": system_prompt},
                              {"role": "user", "content": user_prompt}],
                    temperature=0.2, response_format={"type": "json_object"},
                )
                return json.loads(resp.choices[0].message.content)
            if self.provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=self.api_key)
                resp = client.messages.create(
                    model="claude-3-5-sonnet-latest",
                    max_tokens=1024, system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.2,
                )
                text = resp.content[0].text
                return self._extract_json(text)
            if self.provider == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"{system_prompt}\n\n{user_prompt}\n\nRespond with JSON only."
                resp = model.generate_content(prompt, generation_config={"response_mime_type": "application/json", "temperature": 0.2})
                return json.loads(resp.text)
        except Exception as e:
            if max_retries > 0:
                return self.complete_json(system_prompt, user_prompt, max_retries - 1)
            raise e
        raise RuntimeError(f"Unknown provider {self.provider}")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        # Try direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try fenced
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        # Try first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise ValueError("No JSON in LLM response")


SYSTEM_PROMPT = """You are the orchestration brain of an AI agent that manages a portfolio of renewable energy assets (5 solar farms, 3 wind farms, 2 battery storage systems, grid interconnection, and industrial/commercial consumers).

Your job is:
1. OBSERVE the current state, forecasts, and alerts.
2. IDENTIFY anomalies, threats, and opportunities.
3. CHOOSE objective weights and any hard constraints for the optimization tool.
4. ASSESS forecast confidence — hold battery reserve when confidence is low or disruption is near.
5. RETURN a strict JSON plan that will be passed to the optimizer.

Competing objectives:
- cost: minimize electricity cost
- carbon: minimize grid fossil electricity
- reliability: serve all load (especially critical), avoid unmet demand
- battery_life: minimize unnecessary battery cycling/degradation
- curtailment: minimize waste of renewable energy
- profit_export: profit from exporting when prices are high

Weights must sum to approximately 1.0 and each be between 0 and 1.

Respond ONLY with JSON of this shape:
{
  "situation_assessment": "<short 1-2 sentence diagnosis of what's happening now>",
  "anomalies": ["<list>"],
  "opportunities": ["<list>"],
  "forecast_confidence": "<high|medium|low>",
  "weights": {"cost": 0..1, "carbon": 0..1, "reliability": 0..1, "battery_life": 0..1, "curtailment": 0..1, "profit_export": 0..1},
  "hold_reserve_kw": <number, battery reserve to hold for uncertainty/forecasted events, in kW>,
  "battery_hold_reserve_frac": <0..0.5, fraction of battery capacity to hold in reserve>,
  "max_grid_import_kw": <number or null>,
  "max_grid_export_kw": <number or null>,
  "intent": "<short statement of strategy this tick>",
  "explanation": "<2-3 sentence operator-friendly explanation of the decision>"
}

Key rules:
- When prices are HIGH (>12 INR/kWh), favor reliability + export profit: discharge batteries and reduce noncritical demand; avoid importing.
- When prices are LOW (<5 INR/kWh), favor cost + battery_life: charge batteries from cheap grid if renewables short, avoid unnecessary cycling.
- When a storm warning or severe uncertainty exists, raise reliability weight and hold_reserve_kw.
- When a battery is offline, increase reliability weight.
- When renewables are abundant, favor curtailment_minimization (use them first) and carbon_minimization.
- At night (no solar), rely on wind + batteries if available, else grid import at off-peak prices.
- Always serve CRITICAL load first — reliability weight should be at least 0.2 in all cases.
- When near morning/evening peaks with high price forecast, hold battery reserve to discharge during peak.
- Be decisive. Do not use equal weights unless the situation is truly uneventful.
"""


@dataclass
class AgentDecision:
    weights: Dict[str, float]
    extra_constraints: Dict[str, Any]
    hold_reserve_kw: float
    reasoning: Dict[str, Any]
    used_llm: bool
    validation: Dict[str, Any] = field(default_factory=dict)
    actions: Optional[Dict[str, Any]] = None


class EnergyAgent:
    def __init__(self, cfg: Config, optimizer: EnergyOptimizer):
        self.cfg = cfg
        self.optimizer = optimizer
        self.llm = LLMClient()
        self.tick_count = 0
        self.override: Dict[str, Any] = {}  # nl-command overrides (cleared after consumption)

    def observe_and_act(self, snapshot: Dict[str, Any]) -> AgentDecision:
        self.tick_count += 1
        if self.llm.available and random.random() < 1.0:  # use LLM whenever available
            try:
                decision = self._llm_reason(snapshot)
            except Exception as e:
                decision = self._rule_reason(snapshot, error=str(e))
        else:
            decision = self._rule_reason(snapshot)

        # Apply NL-command overrides (sticky for one or more ticks)
        if self.override:
            if "weights" in self.override:
                decision.weights = dict(self.override["weights"])
                total = sum(decision.weights.values())
                if total > 0:
                    decision.weights = {k: v / total for k, v in decision.weights.items()}
            if "hold_reserve_kw" in self.override:
                decision.hold_reserve_kw = max(decision.hold_reserve_kw, self.override["hold_reserve_kw"])
            if "battery_hold_reserve_frac" in self.override:
                decision.extra_constraints["battery_hold_reserve_frac"] = max(
                    decision.extra_constraints.get("battery_hold_reserve_frac", 0.0),
                    self.override["battery_hold_reserve_frac"],
                )
            decision.reasoning["operator_command_applied"] = True
            decision.reasoning["mode"] = decision.reasoning.get("mode", "") + " + operator directive"
            # Clear override after it takes effect (one-shot)
            self.override = {}

        # Validate: call optimizer, check result, possibly replan
        opt_result = self.optimizer.solve(
            snapshot, decision.weights,
            extra_constraints=decision.extra_constraints,
            must_hold_reserve_kw=decision.hold_reserve_kw,
        )
        decision.actions = opt_result["actions"]
        diag = opt_result["diagnostics"]

        # Validation: check critical load served, battery reserve, extreme export/import
        validation = self._validate(snapshot, opt_result)
        decision.validation = validation

        # If validation fails badly AND we have budget to replan, adjust weights and retry once
        if not validation["valid"] and validation["replan_reason"]:
            revised_weights = dict(decision.weights)
            revised_constraints = dict(decision.extra_constraints)
            # Bump reliability and reserve
            revised_weights["reliability"] = min(1.0, revised_weights.get("reliability", 0.25) + 0.25)
            revised_weights["cost"] = max(0.05, revised_weights.get("cost", 0.25) - 0.1)
            revised_constraints["battery_hold_reserve_frac"] = max(
                revised_constraints.get("battery_hold_reserve_frac", 0.0), 0.15
            )
            new_reserve = decision.hold_reserve_kw * 1.5 + 2000
            opt_result2 = self.optimizer.solve(
                snapshot, revised_weights,
                extra_constraints=revised_constraints,
                must_hold_reserve_kw=new_reserve,
            )
            validation2 = self._validate(snapshot, opt_result2)
            if validation2["valid"] or validation2["unmet_critical_kw"] < validation["unmet_critical_kw"]:
                decision.weights = revised_weights
                decision.extra_constraints = revised_constraints
                decision.hold_reserve_kw = new_reserve
                decision.actions = opt_result2["actions"]
                decision.validation = validation2
                decision.reasoning["replan"] = {
                    "original_issue": validation["replan_reason"],
                    "action_taken": "Increased reliability weight and battery reserve; re-optimized.",
                }
                diag = opt_result2["diagnostics"]

        decision.reasoning["optimizer_status"] = diag.get("status")
        decision.reasoning["weights_applied"] = decision.weights
        return decision

    def _validate(self, snapshot: Dict[str, Any], opt_result: Dict[str, Any]) -> Dict[str, Any]:
        actions = opt_result["actions"]
        issues = []
        total_unmet_critical = 0.0
        demand = snapshot["demand_kw"]
        serve = actions["serve_kw"]
        dr = actions["dr_cut_kw"]
        for c in self.cfg.consumers:
            cid = c.id
            c_dem = demand[cid]
            c_serv = serve.get(cid, c_dem)
            c_dr = dr.get(cid, 0)
            crit = c_dem * c.critical_fraction
            unmet_crit = max(0, crit - min(crit, c_serv))
            if unmet_crit > 1.0:
                issues.append(f"Unmet critical load on {c.name}: {unmet_crit:.0f} kW")
                total_unmet_critical += unmet_crit

        # Check battery SOC violations
        # (optimizer enforces SOC bounds, so this is a double-check)

        price = snapshot["grid_price_inr_per_kwh"]
        if price > 12 and actions["grid_import_kw"] > 10000:
            issues.append(f"Importing heavily at high price ({price:.1f} INR/kWh): {actions['grid_import_kw']:.0f} kW")

        valid = len(issues) == 0
        return {
            "valid": valid,
            "issues": issues,
            "unmet_critical_kw": total_unmet_critical,
            "replan_reason": issues[0] if issues else None,
        }

    def _llm_reason(self, snapshot: Dict[str, Any]) -> AgentDecision:
        # Build compact state summary
        state_summary = self._summarize_state(snapshot)
        user_prompt = f"Current state:\n{json.dumps(state_summary, indent=2)}"
        raw = self.llm.complete_json(SYSTEM_PROMPT, user_prompt)
        # Clamp weights
        weights = raw.get("weights", {})
        weights = {k: max(0.0, min(1.0, float(v))) for k, v in weights.items()}
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        else:
            weights = {"cost": 0.25, "carbon": 0.2, "reliability": 0.3, "battery_life": 0.1, "curtailment": 0.1, "profit_export": 0.05}
        hold_reserve_kw = max(0.0, float(raw.get("hold_reserve_kw", 0)))
        battery_reserve_frac = max(0.0, min(0.5, float(raw.get("battery_hold_reserve_frac", 0.0))))
        extra_constraints = {
            "battery_hold_reserve_frac": battery_reserve_frac,
        }
        if raw.get("max_grid_import_kw"):
            extra_constraints["max_grid_import_kw"] = float(raw["max_grid_import_kw"])
        if raw.get("max_grid_export_kw"):
            extra_constraints["max_grid_export_kw"] = float(raw["max_grid_export_kw"])
        reasoning = {
            "mode": "LLM agent",
            "situation_assessment": raw.get("situation_assessment", ""),
            "anomalies": raw.get("anomalies", []),
            "opportunities": raw.get("opportunities", []),
            "forecast_confidence": raw.get("forecast_confidence", "medium"),
            "intent": raw.get("intent", ""),
            "explanation": raw.get("explanation", ""),
        }
        return AgentDecision(
            weights=weights, extra_constraints=extra_constraints,
            hold_reserve_kw=hold_reserve_kw, reasoning=reasoning, used_llm=True,
        )

    def _rule_reason(self, snapshot: Dict[str, Any], error: Optional[str] = None) -> AgentDecision:
        """Deterministic rule-based reasoning — always works, demonstrates situation awareness."""
        price = snapshot["grid_price_inr_per_kwh"]
        hour = snapshot["hour"]
        solar_pot = snapshot["solar_potential_kw"]
        wind_pot = snapshot["wind_potential_kw"]
        demand = snapshot["total_demand_kw"]
        alerts = snapshot["alerts"]
        forecasts = snapshot["forecasts"]

        # Default weights
        weights = {"cost": 0.22, "carbon": 0.20, "reliability": 0.28, "battery_life": 0.15, "curtailment": 0.10, "profit_export": 0.05}
        anomalies = []
        opportunities = []
        hold_reserve_kw = 0.0
        battery_reserve_frac = 0.05
        intent_parts = []
        explanation_parts = []
        # Near-term confidence (next 2 hours) drives reserve decisions; far-term is always uncertain.
        near_forecasts = [f for f in forecasts if f["lead_minutes"] <= 120]
        far_forecasts = [f for f in forecasts if f["lead_minutes"] > 120]
        min_conf = min((f["confidence"] for f in near_forecasts), default=1.0)
        min_far_conf = min((f["confidence"] for f in far_forecasts), default=1.0)

        # Offline batteries
        offline_batts = [bid for bid, a in snapshot["assets"].items() if bid.startswith("b") and not a.get("online", True)]
        if offline_batts:
            anomalies.append(f"{len(offline_batts)} battery(ies) offline — reliability risk")
            weights["reliability"] += 0.15
            weights["battery_life"] = 0.0
            weights["cost"] = max(0.05, weights["cost"] - 0.05)
            intent_parts.append("defensive mode due to battery fault")
            explanation_parts.append("One or more batteries are offline, so I'm prioritizing reliability and importing grid as needed.")

        # Price regimes
        if price > 12:
            anomalies.append(f"Grid price is HIGH ({price:.1f} INR/kWh)")
            weights["cost"] += 0.10
            weights["profit_export"] += 0.10
            weights["battery_life"] = max(0.0, weights["battery_life"] - 0.05)
            hold_reserve_kw = 0  # discharge now if profitable
            battery_reserve_frac = 0.0
            opportunities.append("Discharge batteries to offset expensive imports; export excess.")
            intent_parts.append("exploit high prices")
            explanation_parts.append(f"Prices are spiking at {price:.1f} INR/kWh — discharging batteries and minimizing imports.")
        elif price < 5:
            opportunities.append(f"Low grid prices ({price:.1f} INR/kWh) — opportunity to charge batteries.")
            weights["cost"] += 0.10
            weights["battery_life"] += 0.05
            intent_parts.append("charge on cheap grid")
            explanation_parts.append(f"Off-peak pricing ({price:.1f} INR/kWh) — topping up batteries from grid when economical.")
        else:
            intent_parts.append("balanced operation")
            explanation_parts.append("Operating in balanced mode across cost/carbon/reliability.")

        # Time-of-day strategy
        # Look ahead to see if price peak is coming (evening peak around 18-20)
        upcoming_high_price = any(f["price"] > price * 1.4 for f in forecasts[:4])
        if hour < 17 and upcoming_high_price:
            opportunities.append("Evening peak approaching — preserving battery capacity for peak discharge.")
            hold_reserve_kw = max(hold_reserve_kw, 10000)
            battery_reserve_frac = max(battery_reserve_frac, 0.20)
            weights["profit_export"] += 0.05
            intent_parts.append("reserving BESS for evening peak")
            explanation_parts.append("Forecast shows evening price peak — holding battery reserve to discharge at peak prices.")

        # Renewable abundance
        ren_total = solar_pot + wind_pot
        if ren_total > demand * 1.05:
            opportunities.append("Renewable surplus — maximize self-consumption, charge batteries, export excess.")
            weights["curtailment"] += 0.10
            weights["carbon"] += 0.05
            weights["battery_life"] = max(0.05, weights["battery_life"] - 0.05)
            battery_reserve_frac = 0.0  # use available capacity
            intent_parts.append("absorb renewable surplus")
        elif ren_total < demand * 0.4 and hour >= 18:
            anomalies.append("Evening peak with low renewable output — drawing on batteries + grid.")
            weights["reliability"] += 0.05
            battery_reserve_frac = 0.0  # use batteries

        # Storm warning / near-term low confidence (only trigger reserve on immediate uncertainty)
        if any("storm" in a.lower() for a in alerts) or min_conf < 0.55:
            anomalies.append("Low forecast confidence / storm warning — holding reserve.")
            weights["reliability"] += 0.10
            hold_reserve_kw = max(hold_reserve_kw, 8000)
            battery_reserve_frac = max(battery_reserve_frac, 0.20)
            intent_parts.append("conservative posture due to uncertainty")
            explanation_parts.append("Forecast confidence is low or storm is forecast — holding safety reserve and prioritizing reliability.")

        # Demand surge / DR opportunity
        if any("surge" in a.lower() or "spike" in a.lower() for a in alerts):
            anomalies.append("Demand spike/alert detected.")
            weights["reliability"] += 0.10
            explanation_parts.append("Demand event in progress — prepared to call demand response if needed.")

        # Night (no solar)
        if solar_pot < 100:
            weights["battery_life"] = max(weights["battery_life"], 0.15)
            # rely on wind + battery carefully

        # Re-normalize weights
        total_w = sum(weights.values())
        weights = {k: v / total_w for k, v in weights.items()}
        # Guarantee reliability floor
        if weights["reliability"] < 0.20:
            weights["reliability"] = 0.20

        # Confidence label
        if min_conf < 0.5:
            conf_label = "low"
        elif min_conf < 0.75:
            conf_label = "medium"
        else:
            conf_label = "high"

        situation = f"Hour {hour:.1f}, solar {solar_pot:.0f} kW, wind {wind_pot:.0f} kW, demand {demand:.0f} kW, price {price:.1f} INR/kWh."
        if not anomalies:
            anomalies = ["Nominal conditions."]
        if not opportunities:
            opportunities = ["Routine dispatch."]
        if error:
            explanation_parts.append(f"(Rule-based fallback due to LLM issue: {error[:80]})")

        reasoning = {
            "mode": "Rule-based agent" + (" (LLM fallback)" if error else ""),
            "situation_assessment": situation,
            "anomalies": anomalies,
            "opportunities": opportunities,
            "forecast_confidence": conf_label,
            "intent": "; ".join(intent_parts) if intent_parts else "balanced operation",
            "explanation": " ".join(explanation_parts),
        }
        return AgentDecision(
            weights=weights,
            extra_constraints={"battery_hold_reserve_frac": battery_reserve_frac},
            hold_reserve_kw=hold_reserve_kw,
            reasoning=reasoning,
            used_llm=False,
        )

    def _summarize_state(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        assets = {}
        for aid, a in snapshot["assets"].items():
            entry = {
                "online": a["online"],
                "available_kw": a["available_kw"],
            }
            if "soc_frac" in a:
                entry["soc_frac"] = a["soc_frac"]
                entry["soc_kwh"] = a["soc_kwh"]
            assets[aid] = entry
        return {
            "time_of_day": snapshot["time_of_day"],
            "day": snapshot["day"],
            "solar_total_potential_kw": snapshot["solar_potential_kw"],
            "wind_total_potential_kw": snapshot["wind_potential_kw"],
            "total_demand_kw": snapshot["total_demand_kw"],
            "grid_price_inr_per_kwh": snapshot["grid_price_inr_per_kwh"],
            "demand_kw_per_consumer": snapshot["demand_kw"],
            "assets": assets,
            "alerts": snapshot["alerts"],
            "active_events": snapshot["active_events"],
            "forecasts": snapshot["forecasts"],
            "kpis_to_date": snapshot["kpis"],
        }
