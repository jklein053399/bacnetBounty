"""Role maps for the shared model: which point of each point-list device type follows which model value.

point_value() is used by the live devices (devices/model_pointlist.py) and by the history export
(simulator.export), so both give the same value for the same point at the same moment.

    a mapped point             -> the model's value
    an alarm in ALARMS_NORMAL  -> Normal (these start in alarm in the demo profile's lists)
    an analog sensor           -> its starting value plus smooth noise, keyed to the time
    anything else              -> None: leave it as it is (a setpoint keeps what was written to it)
"""
from __future__ import annotations

import math
import re

from .shared_model import SharedState, smooth

# runtime counters climb at this share of real time (hours of run per hour)
RUNTIME_DUTY = {"PCHWP1-RUNTIME": 0.32, "PCHWP2-RUNTIME": 0.04, "SHWP1-RUNTIME": 0.45, "SHWP2-RUNTIME": 0.05}
EPOCH_HOURS_BACK = 26000.0          # runtime counters read as if in service for about 3 years before the epoch


def _occ(u):                        # multistate Occupied (1) / UnOccupied (2)
    return 1 if u["occupied"] else 2


def _onoff(flag):                   # multistate Off (1) / On (2)
    return 2 if flag else 1


ROLES: dict[str, dict] = {
    "VAV": {
        "SA-T": lambda u, st: u["sat"],
        "DA-VP": lambda u, st: u["vp"],
        "ZN-T": lambda u, st: u["zone"],
        "RH-O": lambda u, st: u["reheat"],
        "DPR-O": lambda u, st: u["damper"],
        "SAFLOW-SP": lambda u, st: u["flow_sp"],
        "SA-F": lambda u, st: u["flow"],
        "EFFCLG-SP": lambda u, st: u["eff_clg"],
        "EFFHTG-SP": lambda u, st: u["eff_htg"],
        "OCC-MODE": lambda u, st: _occ(u),
    },
    "RTU": {
        "Control_Temperature": lambda u, st: u["space"],
        "Supply_Air_Temperature": lambda u, st: u["sat"],
        "Supply_Air_Setpoint": lambda u, st: u["sat_sp"],
        "Space_Temperature": lambda u, st: u["space"],
        "Space Humidity": lambda u, st: u["rh"],
        "Return_Air_Temperature": lambda u, st: u["rat"],
        "Outdoor_Air_Temperature": lambda u, st: st.oat_f,
        "Outdoor_Air_Humidity": lambda u, st: st.oa_rh,
        "Outdoor_Air_Wetbulb": lambda u, st: wetbulb_f(st.oat_f, st.oa_rh),
        "Outdoor_Air_Dewpoint": lambda u, st: dewpoint_f(st.oat_f, st.oa_rh),
        "Outdoor_Air_Enthalpy": lambda u, st: enthalpy_btu_lb(st.oat_f, st.oa_rh),
        "Duct_Static_Pressure": lambda u, st: u["static"],
        "Duct_Static_Control_Signal": lambda u, st: u["vfd"],
        "Current_Duct_Static_Setpoint": lambda u, st: u["static_sp"],
        "Building_Pressure": lambda u, st: u["bldg_p"],
        "Building_Pressure_Control_Signal": lambda u, st: 0.6 * u["econ"] if u["fan_on"] else 0.0,
        "Carbon_Dioxide": lambda u, st: u["co2"],
        "Desired_Economizer_Position": lambda u, st: u["econ"],
        "Economizer_Feedback_Position": lambda u, st: max(0.0, u["econ"] - 0.4) if u["econ"] else 0.0,
        "Return_Damper_Position": lambda u, st: u["ret_dpr"],
        "Modulating_Cooling_Position": lambda u, st: u["cooling"],
        "Mod_Gas_Heat_Valve_Position": lambda u, st: u["heating"],
        "A1_Compressor_Signal": lambda u, st: u["cooling"],
        "A1_Condenser_Signal": lambda u, st: 0.8 * u["cooling"],
        "A1_Suction_Pressure": lambda u, st: u["suction"],
        "A1_Head_Pressure": lambda u, st: u["head"],
        "A1_Saturation_Temperature": lambda u, st: u["sst"],
        "A1_Suction_Line_Temperature": lambda u, st: u["slt"],
        "A1_Discharge_Temperature": lambda u, st: u["dlt"],
        "Cooling_Enabled_Status": lambda u, st: st.mode == "cooling",
        "Heating_Enabled_Status": lambda u, st: st.mode == "heating",
        "Economizer_Enabled_Status": lambda u, st: u["econ"] > 15.0,
        "Fan_Proof_of_Airflow_Status": lambda u, st: u["fan_on"],
        "Return_Fan_Proving_Status": lambda u, st: u["fan_on"],
        "A1_Compressor_Enable": lambda u, st: u["cooling"] > 0.0,
        "Exhaust_Hood_On.Off_Status": lambda u, st: u["hood"],
    },
    "AHU": {
        "DA_T": lambda u, st: u["dat"],
        "MA_T": lambda u, st: u["mat"],
        "PH_T": lambda u, st: u["pht"],
        "RA_Q_N": lambda u, st: u["co2"],
        "RA_T": lambda u, st: u["rat"],
        "ZN_H": lambda u, st: u["rh"],
        "ZN_T": lambda u, st: u["zone"],
        "CLG_O": lambda u, st: u["clg"],
        "MOAD_O": lambda u, st: u["moad"],
        "OAD_O": lambda u, st: u["oad"],
        "PHFBD_O": lambda u, st: u["phfbd"],
        "HTG_O": lambda u, st: u["htg"],
        "RAD_O": lambda u, st: u["rad"],
        "OA_H": lambda u, st: st.oa_rh,
        "OA_T": lambda u, st: st.oat_f,
        "EFFDAT_SP": lambda u, st: u["dat_sp"],
        "EFFCLG_SP": lambda u, st: u["eff_clg"],
        "EFFHTG_SP": lambda u, st: u["eff_htg"],
        "SF_C": lambda u, st: u["fan_on"],
        "EF_G1_G2_C": lambda u, st: u["fan_on"],
        "EF_G1_S": lambda u, st: u["fan_on"],
        "EF_G2_S": lambda u, st: u["fan_on"],
        "OCC_SCHEDULE": lambda u, st: _occ(u),
        "EFF_OCC": lambda u, st: _occ(u),
        "AHU_STATE": lambda u, st: u["state"],
        "CLG_AVAILABLE": lambda u, st: st.oat_f > 55.0,
        "ECON_AVAILABLE": lambda u, st: 45.0 < st.oat_f < 62.0,
        "PH_AVAILABLE": lambda u, st: st.oat_f < 40.0,
    },
    "CHWS": {
        "CHWS_T": lambda u, st: u["chws"],
        "CHWR_T": lambda u, st: u["chwr"],
        "CHWTEMP-DIFF": lambda u, st: u["chwr"] - u["chws"],
        "CUH_AUD_T": lambda u, st: u["room"],
        "CHWP1_O": lambda u, st: u["p1"],
        "CHWP2_O": lambda u, st: u["p2"],
        "CP1_C": lambda u, st: u["on"],
        "CP2_C": lambda u, st: u["p2_on"],
        "ACC1_EN": lambda u, st: u["on"],
        "CHWSYS_AVAIL": lambda u, st: st.oat_f > 55.0,
        "OA_T": lambda u, st: st.oat_f,
    },
    "HWS": {
        "HW_DP": lambda u, st: u["dp"],
        "PHWR_T": lambda u, st: u["phwr"],
        "PHWS_T": lambda u, st: u["phws"],
        "CP1_O": lambda u, st: u["p1"],
        "CP2_O": lambda u, st: u["p1"] if u["p2_on"] else 0.0,
        "BLRSP_O": lambda u, st: u["reset"],
        "Effective Setpoint": lambda u, st: u["reset"],
        "OA-T": lambda u, st: st.oat_f,
        "BLR_EN": lambda u, st: u["on"],
        "CP1_C": lambda u, st: u["on"],
        "CP2_C": lambda u, st: u["p2_on"],
        "BLR1-OUTSTATE": lambda u, st: _onoff(u["on"] and u["fire"] > 0.05),
        "SHWP1-OUTSTATE": lambda u, st: _onoff(u["on"]),
        "SHWP2-OUTSTATE": lambda u, st: _onoff(u["p2_on"]),
        "SCHWP 1-Status": lambda u, st: _onoff(u["on"]),
        "SCHWP 2-Status": lambda u, st: _onoff(u["p2_on"]),
    },
    "EF": {
        "EF_C": lambda u, st: u["on"],
        "EF_O": lambda u, st: u["speed"],
    },
    "CUH": {
        "ZN_T": lambda u, st: u["zone"],
        "SF_C": lambda u, st: u["on"],
        "HTG_C": lambda u, st: u["on"],
        "EFFHTG-SP": lambda u, st: u["eff_htg"],
        "EFFCLG-SP": lambda u, st: u["eff_clg"],
        "OCC-SCHEDULE": lambda u, st: _occ(u),
        "OCC_MODE": lambda u, st: _occ(u),
        "EFF-OCC": lambda u, st: _occ(u),
    },
}

# alarms the demo profile's point lists start in alarm; the shared site keeps them Normal
ALARMS_NORMAL = {
    "AHU": {"FFILT_S", "LT_A", "SFPLO_A"},
    "HWS": {"CP1_A", "CP2_A"},
    "RTU": {"Bad_Supply_Air_Sensor", "Bad_Return_Air_Sensor", "Bad_Outdoor_Air_Sensor",
            "Bad_Carbon_Dioxide_Sensor", "Bad_Building_Pressure_Sensor"},
}

# setpoints, limits and counters never drift, even when they are read-only analog values
NO_DRIFT = re.compile(r"(SP$|[_-]SP|SP[_-]|Setpoint|SETPOINT|FLOW$|LOCKOUT|Lockout|Limit|RUNTIME|Delay|_SP_)")


def point_value(dtype: str, device: str, point: dict, st: SharedState, ts: float, seed: int):
    """The value of one point at ts, or None to leave it as it is.

    point: {"name", "kind" (AI/AO/AV/BI/BO/BV/MSI/MSO/MSV), "writable", "base"}.
    Binary values come back as bool, multistate as an int (1-based), analog as a float.
    """
    name = point["name"]
    role = ROLES.get(dtype, {}).get(name)
    if role is not None:
        return role(st.units[device], st)
    if name in RUNTIME_DUTY:
        hours = EPOCH_HOURS_BACK + (ts - st.epoch_ts) / 3600.0
        return round(point["base"] + hours * RUNTIME_DUTY[name], 1)
    if name in ALARMS_NORMAL.get(dtype, ()):
        return False
    kind, base = point["kind"], point["base"]
    if (kind == "AI" or (kind == "AV" and not point["writable"])) and base != 0 and not NO_DRIFT.search(name):
        span = 1.5 if abs(base) < 200 else abs(base) * 0.01
        return round(base + 0.5 * span * smooth(seed, f"{device}|{name}", ts, 1800.0), 2)
    return None


# ---------------------------------------------------------------- psychrometrics (sea level, close enough)

def _c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def dewpoint_f(t_f: float, rh: float) -> float:
    t = _c(t_f)
    g = math.log(max(rh, 1.0) / 100.0) + 17.62 * t / (243.12 + t)
    return (243.12 * g / (17.62 - g)) * 9.0 / 5.0 + 32.0


def wetbulb_f(t_f: float, rh: float) -> float:
    """Stull (2011)."""
    t = _c(t_f)
    tw = (t * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + math.atan(t + rh) - math.atan(rh - 1.676331)
          + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)
    return tw * 9.0 / 5.0 + 32.0


def enthalpy_btu_lb(t_f: float, rh: float) -> float:
    t = _c(t_f)
    pws_psia = 0.6112 * math.exp(17.62 * t / (243.12 + t)) * 0.145038
    pw = rh / 100.0 * pws_psia
    w = 0.622 * pw / (14.696 - pw)
    return 0.24 * t_f + w * (1061.0 + 0.444 * t_f)
