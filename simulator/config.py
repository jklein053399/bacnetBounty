"""Configuration loader and validator for site_config.json.

Fails fast with clear errors on missing/malformed fields.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SiteSection:
    name: str
    square_feet: int
    location: str
    timezone: str


@dataclass
class NetworkSection:
    base_ip: str
    start_octet: int
    subnet_mask_prefix: int
    bacnet_port: int


@dataclass
class SimulationSection:
    tick_interval_seconds: int
    noise_scale: float


@dataclass
class MagnitudesSection:
    building_peak_kw: float
    building_baseline_kw: float
    ahu_vav_peak_kw_each: float
    ahu_sz_peak_kw: float
    vav_reheat_peak_kw_each: float
    lighting_peak_kw: float
    plug_peak_kw: float
    plug_baseline_kw: float
    gas_peak_scfh: float
    gas_baseline_scfh: float
    water_peak_gpm: float
    water_baseline_gpm: float
    voltage_nominal: float
    voltage_phase_nominal: float
    power_factor_nominal: float


@dataclass
class ScheduleSection:
    occupied_weekday_start: str
    occupied_weekday_end: str
    ramp_up_hours: float
    ramp_down_hours: float
    saturday_peak_fraction: float
    sunday_baseline_fraction: float
    cooling_setpoint_occupied: float
    heating_setpoint_occupied: float
    cooling_setpoint_unoccupied: float
    heating_setpoint_unoccupied: float


@dataclass
class WeatherSection:
    location: str
    monthly_high_low_f: list[list[float]]
    diurnal_peak_hour: int
    diurnal_trough_hour: int
    random_walk_bound_f: float


@dataclass
class LoggingSection:
    console_level: str
    file_level: str
    log_dir: str
    rotate_daily: bool
    retention_days: int


@dataclass
class Config:
    site: SiteSection
    network: NetworkSection
    simulation: SimulationSection
    magnitudes: MagnitudesSection
    schedule: ScheduleSection
    weather: WeatherSection
    logging: LoggingSection
    raw: dict = field(default_factory=dict)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"site_config.json not found at {path.resolve()}")

    with path.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: invalid JSON — {e}") from e

    try:
        cfg = Config(
            site=SiteSection(**data["site"]),
            network=NetworkSection(**data["network"]),
            simulation=SimulationSection(**data["simulation"]),
            magnitudes=MagnitudesSection(**data["magnitudes"]),
            schedule=ScheduleSection(**data["schedule"]),
            weather=WeatherSection(**data["weather"]),
            logging=LoggingSection(**data["logging"]),
            raw=data,
        )
    except KeyError as e:
        raise ValueError(f"{path}: missing required section {e}") from e
    except TypeError as e:
        raise ValueError(f"{path}: malformed section — {e}") from e

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if len(cfg.weather.monthly_high_low_f) != 12:
        raise ValueError("weather.monthly_high_low_f must have 12 entries")
    for i, pair in enumerate(cfg.weather.monthly_high_low_f):
        if len(pair) != 2 or pair[0] < pair[1]:
            raise ValueError(f"weather.monthly_high_low_f[{i}]: expected [high, low] with high >= low")
    if not cfg.network.base_ip.endswith("."):
        raise ValueError("network.base_ip must end with a '.' (e.g. '192.168.100.')")
    if cfg.simulation.tick_interval_seconds < 1:
        raise ValueError("simulation.tick_interval_seconds must be >= 1")
    if not 0 < cfg.magnitudes.power_factor_nominal <= 1:
        raise ValueError("magnitudes.power_factor_nominal must be in (0, 1]")
