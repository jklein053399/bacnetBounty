"""AHU physics — pure functions.

Input: SiteState + per-AHU config (from site_config.json ahus[]).
Output: AHUState dataclass with every BACnet point value for one AHU.

Device class is a thin BACnet wrapper that calls compute_ahu_state() each tick
and ships the resulting fields as presentValues. No physics inside the device
class (architectural invariant #2).

Mode selection is driven off SiteState.cooling_load_fraction vs
heating_load_fraction. SA temp setpoints follow spec 02 §5 AV 1 schedule (55F
cooling / 65F heating). AHU Real Power reads the already-computed per-AHU kW
from SiteState — do NOT re-derive from fan + compressor here, or Meter A will
double-count.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import AHUConfig
from .site_model import SiteState


@dataclass
class AHUState:
    """Snapshot of every BACnet point for one AHU at a given tick.

    Field names track spec 02 §5 point names (underscored) so the device
    wrapper can do a flat dict lookup when writing presentValues.
    """
    # AIs (sensor readings)
    Supply_Air_Temperature: float       # degF
    Return_Air_Temperature: float       # degF
    Mixed_Air_Temperature: float        # degF
    Outside_Air_Temperature: float      # degF (mirror of site OAT)
    Supply_Air_Static_Pressure: float   # inches WC
    Supply_Air_Flow: float              # CFM
    Filter_Differential_Pressure: float # inches WC
    AHU_Real_Power: float               # kW (fan + compressor + aux per doc 03 Flag 1)

    # AVs (setpoints)
    Supply_Air_Temp_Setpoint: float     # degF
    Supply_Static_Pressure_Setpoint: float  # inches WC

    # BIs (status)
    Fan_Status: str                     # "active" / "inactive"
    Filter_Alarm: str                   # "active" / "inactive"

    # BV (command, spec 02 §5 said BO — overridden to BV per doc 04 Flag E)
    Fan_Start_Stop: str                 # "active" / "inactive"

    # AVs (commands, spec 02 §5 said AO — overridden to AV per doc 04 Flag E)
    Fan_VFD_Speed_Command: float        # percent
    OA_Damper_Position: float           # percent
    Heating_Valve_Position: float       # percent
    Cooling_Stage_DX_Status: float      # percent


# Per-AHU kW lookup into SiteState by name. SiteState already owns the per-AHU
# kW contributions (they drive Meter A/B/C nesting), so the device reads them
# instead of re-deriving.
_AHU_KW_FIELDS: dict[str, str] = {
    "AHU_1": "ahu_sz_kw",
    "AHU_2": "ahu_vav_1_kw",
    "AHU_3": "ahu_vav_2_kw",
}


def compute_ahu_state(
    ahu_config: AHUConfig,
    ahu_index: int,          # 0/1/2 — index into SiteState.ahu_sat_f tuple
    site_state: SiteState,
) -> AHUState:
    """One AHU's complete BACnet point snapshot for the current tick."""
    s = site_state
    occ = s.occupancy_fraction
    oat = s.oat_f
    cool_frac = s.cooling_load_fraction
    heat_frac = s.heating_load_fraction

    # --- Mode selection ---
    # Fan runs whenever occupied; off unoccupied (standby for VAV AHUs still
    # reflects a tiny residual kW from SiteState, but fan proper is off).
    fan_on = occ > 0.02

    if heat_frac > cool_frac:
        sat_setpoint = 65.0
        heating_mode = True
        cooling_mode = False
    elif cool_frac > heat_frac:
        sat_setpoint = 55.0
        heating_mode = False
        cooling_mode = True
    else:
        sat_setpoint = 60.0
        heating_mode = False
        cooling_mode = False

    # --- Supply Air Temperature ---
    # Pulled from SiteState so VAV discharge-air-temp can reference the same
    # value via the parent AHU (see vav_physics.py).
    sat = s.ahu_sat_f[ahu_index]

    # --- Return / Mixed Air Temperatures ---
    # RAT tracks a blended zone temp (~72F in cooling, ~70F in heating) with
    # drift. Not physically coupled to individual VAV zone temps — spec is
    # Level-1.
    zone_avg = 72.0 if cooling_mode else 70.0 if heating_mode else 71.0
    rat = zone_avg + (0.5 if cool_frac > 0.5 else -0.3)

    # MAT = blend of OA and RAT by OA damper position
    # Compute damper first so MAT can reference it
    oa_damper_min = 15.0 if fan_on else 0.0  # percent, minimum OA when occupied
    if cooling_mode and 50.0 < oat < 65.0 and fan_on:
        # Economizer — free cooling when OAT favorable
        oa_damper = 100.0
    else:
        oa_damper = oa_damper_min

    oa_frac = oa_damper / 100.0
    mat = oa_frac * oat + (1.0 - oa_frac) * rat

    # --- SA Static Pressure ---
    # Tracks setpoint with small drift. VAV AHUs run ~1.5 in WC; SZ ~0.5 in WC.
    sa_pressure_sp = ahu_config.sa_pressure_setpoint_in_wc
    sa_pressure = sa_pressure_sp * (0.97 + 0.06 * (hash((ahu_config.name, "pdrift"))
                                                   & 0xFF) / 255.0) if fan_on else 0.0

    # --- SA Airflow ---
    # Tracks design_cfm × VFD demand. SZ runs constant-volume so VFD stays near
    # 100% when on. VAV modulates with load — proxy off the larger of cool_frac
    # and heat_frac for airflow demand.
    if not fan_on:
        sa_cfm = 0.0
        vfd_pct = 0.0
    elif ahu_config.kind == "single_zone":
        vfd_pct = 100.0
        sa_cfm = ahu_config.design_cfm
    else:
        # VAV AHU — minimum airflow around 40%, modulates up with load
        load_demand = max(cool_frac, 0.6 * heat_frac)  # heating needs less flow than cooling
        vfd_pct = max(40.0, min(100.0, 40.0 + 60.0 * load_demand))
        sa_cfm = ahu_config.design_cfm * (vfd_pct / 100.0)

    # --- Filter Differential Pressure ---
    # ~0.3 in WC nominal, slow seasonal drift, slightly higher at high flow
    filter_dp = 0.25 + 0.05 * (sa_cfm / ahu_config.design_cfm) if fan_on else 0.0

    # --- AHU Real Power ---
    # Reads already-computed per-AHU kW from SiteState (fan + compressor + aux
    # per doc 03 Flag 1). Do NOT re-derive here or Meter A will double-count.
    kw_field = _AHU_KW_FIELDS.get(ahu_config.name)
    if kw_field is None:
        real_power = 0.0
    else:
        real_power = float(getattr(s, kw_field))

    # --- Heating valve position ---
    # AHU preheat only in heating mode. Tracks SAT error below setpoint — since
    # SAT already tracks setpoint via SiteState, use the mode + load fraction
    # as the proxy.
    if heating_mode and fan_on:
        heating_valve = min(100.0, heat_frac * 100.0)
    else:
        heating_valve = 0.0

    # --- Cooling stage / DX status ---
    # Modulating percentage in cooling mode
    if cooling_mode and fan_on:
        cooling_stage = min(100.0, cool_frac * 100.0)
    else:
        cooling_stage = 0.0

    # --- Status BIs ---
    fan_status = "active" if fan_on else "inactive"
    filter_alarm = "inactive"  # stub — would flip if filter_dp > threshold in a faultier model
    fan_cmd = "active" if fan_on else "inactive"

    return AHUState(
        Supply_Air_Temperature=sat,
        Return_Air_Temperature=rat,
        Mixed_Air_Temperature=mat,
        Outside_Air_Temperature=oat,
        Supply_Air_Static_Pressure=sa_pressure,
        Supply_Air_Flow=sa_cfm,
        Filter_Differential_Pressure=filter_dp,
        AHU_Real_Power=real_power,
        Supply_Air_Temp_Setpoint=sat_setpoint,
        Supply_Static_Pressure_Setpoint=sa_pressure_sp,
        Fan_Status=fan_status,
        Filter_Alarm=filter_alarm,
        Fan_Start_Stop=fan_cmd,
        Fan_VFD_Speed_Command=vfd_pct,
        OA_Damper_Position=oa_damper,
        Heating_Valve_Position=heating_valve,
        Cooling_Stage_DX_Status=cooling_stage,
    )
