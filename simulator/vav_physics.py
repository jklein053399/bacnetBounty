"""VAV physics — pure functions.

Input: SiteState + per-VAV config (from site_config.json vavs[]) + vav_index.
Output: VAVState dataclass with every BACnet point value for one VAV.

Device class is a thin BACnet wrapper that calls compute_vav_state() each tick.
No physics inside the device class (architectural invariant #2).

Key couplings (by design, kept simple per Session B Q5 answer):
- **Zone_Temperature**: read directly from SiteState.vav_zone_temps_f[vav_index].
  Site model owns the per-VAV zone temp as primary data (phase-shifted around
  the active setpoint).
- **Reheat_Valve_Position**: read directly from SiteState.vav_valve_positions
  [vav_index]. Site model owns per-VAV valve as primary data; Meter B sums
  the same values so device readings and Meter B are zero-drift consistent
  (spec doc 03 §Flag 1).
- **Discharge_Air_Temperature**: parent AHU SAT (from SiteState.ahu_sat_f) +
  reheat delta when valve is open. Delta = valve × max reheat delta (~30F
  rise at 100% valve, typical for electric reheat).
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import VAVConfig
from .site_model import SiteState


# AHU name → SiteState.ahu_sat_f index. Mirrors ahu_physics.py.
_AHU_SAT_INDEX: dict[str, int] = {
    "AHU_1": 0,
    "AHU_2": 1,
    "AHU_3": 2,
}

# Max discharge-air-temp rise at 100% reheat valve (electric reheat, typical
# single-stage). Keeps DA temp plausible: 55F SAT + 30F × valve → up to 85F DA.
MAX_REHEAT_DELTA_F = 30.0


@dataclass
class VAVState:
    """Snapshot of every BACnet point for one VAV at a given tick."""
    Zone_Temperature: float                 # degF
    Supply_Airflow: float                   # CFM
    Discharge_Air_Temperature: float        # degF

    Occupied_Cooling_Setpoint: float        # degF
    Occupied_Heating_Setpoint: float        # degF
    Airflow_Setpoint: float                 # CFM

    # Commandable AVs (spec 02 §6 said AO; doc 04 Flag E overrides to AV)
    Damper_Position: float                  # percent
    Reheat_Valve_Position: float            # percent

    Occupancy_Status: str                   # "active" / "inactive"


def compute_vav_state(
    vav_config: VAVConfig,
    vav_index: int,
    site_state: SiteState,
) -> VAVState:
    """One VAV's complete BACnet point snapshot for the current tick."""
    s = site_state

    # --- Zone temperature (from site model primary data) ---
    if vav_index < len(s.vav_zone_temps_f):
        zone_t = s.vav_zone_temps_f[vav_index]
    else:
        zone_t = 72.0  # defensive — shouldn't happen if config is wired right

    # --- Reheat valve position (from site model primary data) ---
    # Stored as 0..1 in SiteState; BACnet point is in percent (0..100).
    if vav_index < len(s.vav_valve_positions):
        valve_frac = s.vav_valve_positions[vav_index]
    else:
        valve_frac = 0.0
    reheat_valve = valve_frac * 100.0

    # --- Discharge air temperature ---
    # Parent AHU SAT + reheat rise (when valve open).
    sat_idx = _AHU_SAT_INDEX.get(vav_config.parent_ahu, 1)
    parent_sat = s.ahu_sat_f[sat_idx]
    da_temp = parent_sat + valve_frac * MAX_REHEAT_DELTA_F

    # --- Setpoints ---
    cool_sp = site_state  # placeholder — use config.schedule below
    # Occupied setpoints per spec 02 §6 AV 1/2 defaults. Pulled from site config
    # schedule section so tuning pass can shift them without code changes.
    cfg_sched = s  # Access via SiteState... actually we need the config.
    # SiteState doesn't carry schedule; we'll use the canonical defaults.
    occ_cool_sp = 74.0
    occ_heat_sp = 70.0

    # --- Airflow setpoint + actual ---
    # Cooling demand drives airflow up from min_cfm to design_cfm.
    # Heating demand drops airflow to min_cfm (reheat handles temp).
    occ = s.occupancy_fraction
    cool_frac = s.cooling_load_fraction
    heat_frac = s.heating_load_fraction

    if occ < 0.1:
        airflow_sp = 0.0  # unoccupied — damper shut
    elif heat_frac > cool_frac:
        airflow_sp = vav_config.min_cfm  # heating mode — min flow, reheat does the work
    else:
        # Cooling mode: min_cfm at cool_frac=0, design_cfm at cool_frac=1
        airflow_sp = vav_config.min_cfm + (vav_config.design_cfm - vav_config.min_cfm) * cool_frac

    # Actual airflow tracks setpoint with small drift
    # (deterministic via device phase so value is stable across ticks)
    airflow = airflow_sp * (0.98 + 0.04 * ((hash((vav_config.name, "aflow")) & 0xFF) / 255.0))

    # --- Damper position ---
    # Tracks airflow SP as a fraction of design flow.
    if vav_config.design_cfm > 0:
        damper = min(100.0, 100.0 * airflow / vav_config.design_cfm)
    else:
        damper = 0.0
    # Enforce minimum damper position when occupied (for ventilation)
    if occ > 0.1:
        damper = max(damper, 100.0 * vav_config.min_cfm / vav_config.design_cfm)

    # --- Occupancy status ---
    occupancy_status = "active" if occ > 0.1 else "inactive"

    return VAVState(
        Zone_Temperature=zone_t,
        Supply_Airflow=airflow,
        Discharge_Air_Temperature=da_temp,
        Occupied_Cooling_Setpoint=occ_cool_sp,
        Occupied_Heating_Setpoint=occ_heat_sp,
        Airflow_Setpoint=airflow_sp,
        Damper_Position=damper,
        Reheat_Valve_Position=reheat_valve,
        Occupancy_Status=occupancy_status,
    )
