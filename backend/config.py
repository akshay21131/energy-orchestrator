"""Asset configuration for the Renewable Energy Orchestrator."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class SolarFarm:
    id: str
    name: str
    rated_kw: float
    sunrise_hour: float = 6.0
    sunset_hour: float = 18.5


@dataclass
class WindFarm:
    id: str
    name: str
    rated_kw: float
    cut_in_ms: float = 3.0
    rated_ms: float = 12.0
    cut_out_ms: float = 25.0


@dataclass
class Battery:
    id: str
    name: str
    capacity_kwh: float
    max_charge_kw: float
    max_discharge_kw: float
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    initial_soc_frac: float = 0.60
    min_soc_frac: float = 0.10
    max_soc_frac: float = 0.95
    throughput_cost_inr_per_kwh: float = 3.0


@dataclass
class GridConnection:
    id: str
    name: str
    max_import_kw: float
    max_export_kw: float
    line_capacity_kw: float


@dataclass
class Consumer:
    id: str
    name: str
    peak_demand_kw: float
    critical_fraction: float = 0.40  # critical load that must be served


@dataclass
class Config:
    tick_minutes: int = 15
    solar_farms: List[SolarFarm] = field(default_factory=list)
    wind_farms: List[WindFarm] = field(default_factory=list)
    batteries: List[Battery] = field(default_factory=list)
    grid: GridConnection = None
    consumers: List[Consumer] = field(default_factory=list)
    # Baseline cost/CO2 params
    grid_import_price_inr_per_kwh: float = 8.0
    grid_export_price_inr_per_kwh: float = 4.0
    co2_per_kwh_grid_kg: float = 0.82  # India grid average
    curtailment_penalty_inr_per_kwh: float = 0.5
    unmet_critical_penalty_inr_per_kwh: float = 50.0
    unmet_noncritical_penalty_inr_per_kwh: float = 10.0
    demand_response_reward_inr_per_kwh: float = 2.0
    # Location (Delhi 28.6N)
    latitude: float = 28.6


def make_default_config() -> Config:
    cfg = Config(tick_minutes=15)
    cfg.solar_farms = [
        SolarFarm("s1", "Solar Farm 1 — Rohtak", rated_kw=20000),
        SolarFarm("s2", "Solar Farm 2 — Gurugram", rated_kw=25000),
        SolarFarm("s3", "Solar Farm 3 — Noida", rated_kw=15000),
        SolarFarm("s4", "Solar Farm 4 — Sonipat", rated_kw=18000),
        SolarFarm("s5", "Solar Farm 5 — Faridabad", rated_kw=22000),
    ]
    cfg.wind_farms = [
        WindFarm("w1", "Wind Farm 1 — Jaisalmer Link", rated_kw=30000),
        WindFarm("w2", "Wind Farm 2 — Coastal Link", rated_kw=25000),
        WindFarm("w3", "Wind Farm 3 — Hillside", rated_kw=20000),
    ]
    cfg.batteries = [
        Battery("b1", "BESS 1 — North Hub", capacity_kwh=40000,
                max_charge_kw=20000, max_discharge_kw=20000, initial_soc_frac=0.60),
        Battery("b2", "BESS 2 — South Hub", capacity_kwh=30000,
                max_charge_kw=15000, max_discharge_kw=15000, initial_soc_frac=0.55),
    ]
    cfg.grid = GridConnection(
        "g1", "State Grid Interconnect",
        max_import_kw=80000, max_export_kw=50000, line_capacity_kw=100000,
    )
    cfg.consumers = [
        Consumer("c1", "Industrial Park A", peak_demand_kw=35000, critical_fraction=0.45),
        Consumer("c2", "Industrial Park B", peak_demand_kw=28000, critical_fraction=0.50),
        Consumer("c3", "Commercial District", peak_demand_kw=15000, critical_fraction=0.30),
    ]
    return cfg
