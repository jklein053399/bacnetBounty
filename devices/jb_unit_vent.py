"""
JB Unit Ventilator — BAC0 device profile
Source: .live-references/.station-surveys/sites/School_ES_01.json (JB_UV_1)

Device type: JCI/JB Unit Ventilator — most common non-RTU/VAV in Metro school stations
Key naming: Standard Metro Controls abbreviations (ZN_T, DA_T, EFFHTG_SP, EFFCLG_SP)
Has OutOfRangeAlarmExt on ZN_T in real stations — ideal for validation.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_output, binary_value,
    multistate_value, make_state_text,
)


def create_jb_unit_vent_points():
    """Define all BACnet objects for a JB Unit Ventilator.

    Point names use standard Metro Controls abbreviations.
    """
    # --- Temperatures ---
    analog_input(
        name="ZN_T",
        instance=1,
        description="Zone Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_input(
        name="DA_T",
        instance=2,
        description="Discharge Air Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=68.0,
    )
    analog_input(
        name="RA_T",
        instance=3,
        description="Return Air Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=71.5,
    )
    analog_input(
        name="OA_T",
        instance=4,
        description="Outdoor Air Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=45.0,
    )
    analog_input(
        name="BLDG_P",
        instance=5,
        description="Building Pressure",
        properties={"units": "inchesOfWater"},
        presentValue=0.02,
    )
    analog_input(
        name="ZN_CO2",
        instance=6,
        description="Zone CO2",
        properties={"units": "partsPerMillion"},
        presentValue=450.0,
    )

    # --- Effective Setpoints (Tier 1) ---
    analog_input(
        name="EFFHTG_SP",
        instance=10,
        description="Effective Heating Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.0,
    )
    analog_input(
        name="EFFCLG_SP",
        instance=11,
        description="Effective Cooling Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=74.0,
    )
    analog_input(
        name="MAD_MINPOS",
        instance=12,
        description="Mixed Air Damper Minimum Position",
        properties={"units": "percent"},
        presentValue=15.0,
    )

    # --- Occupied Setpoints (Tier 2) ---
    analog_value(
        name="HTGOCC_SP",
        instance=20,
        description="Heating Occupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.0,
    )
    analog_value(
        name="CLGOCC_SP",
        instance=21,
        description="Cooling Occupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=74.0,
    )
    analog_value(
        name="HTGUNOCC_SP",
        instance=22,
        description="Heating Unoccupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=60.0,
    )
    analog_value(
        name="CLGUNOCC_SP",
        instance=23,
        description="Cooling Unoccupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=85.0,
    )
    analog_value(
        name="ZN_SP",
        instance=24,
        description="Zone Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )

    # --- DAT / Other Setpoints ---
    analog_value(
        name="DATLL_SP",
        instance=30,
        description="Discharge Air Temperature Low Limit Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=55.0,
    )
    analog_value(
        name="ECONSWO_SP",
        instance=31,
        description="Economizer Switchover Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=65.0,
    )
    analog_value(
        name="HTGOATLOCKOUT_SP",
        instance=32,
        description="Heating OAT Lockout Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=65.0,
    )
    analog_value(
        name="CLGOATLOCKOUT_SP",
        instance=33,
        description="Cooling OAT Lockout Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=50.0,
    )
    analog_value(
        name="OAD_MINPOS",
        instance=34,
        description="Outdoor Air Damper Minimum Position",
        properties={"units": "percent"},
        presentValue=20.0,
    )
    analog_value(
        name="MOA_CO2RSTA",
        instance=35,
        description="Min OA CO2 Reset A",
        presentValue=700.0,
    )
    analog_value(
        name="MOA_CO2RSTB",
        instance=36,
        description="Min OA CO2 Reset B",
        presentValue=1000.0,
    )
    analog_value(
        name="MIN_VALVE_POSITION",
        instance=37,
        description="Minimum Valve Position",
        properties={"units": "percent"},
        presentValue=0.0,
    )

    # --- Outputs ---
    analog_value(
        name="HTG_O",
        instance=40,
        description="Heating Output",
        properties={"units": "percent"},
        presentValue=25.0,
    )
    analog_value(
        name="MAD_O",
        instance=41,
        description="Mixed Air Damper Output",
        properties={"units": "percent"},
        presentValue=20.0,
    )
    analog_value(
        name="RLF_O",
        instance=42,
        description="Relief Output",
        properties={"units": "percent"},
        presentValue=0.0,
    )

    # --- Binary Points ---
    binary_value(
        name="TUNING_RESET",
        instance=50,
        description="Tuning Reset",
        presentValue="inactive",
    )
    binary_value(
        name="SFL_C",
        instance=51,
        description="Supply Fan Low Command",
        presentValue="active",
    )
    binary_value(
        name="SFH_C",
        instance=52,
        description="Supply Fan High Command",
        presentValue="inactive",
    )
    binary_value(
        name="SFM_C",
        instance=53,
        description="Supply Fan Medium Command",
        presentValue="inactive",
    )
    binary_value(
        name="CLG1_C",
        instance=54,
        description="Cooling Stage 1 Command",
        presentValue="inactive",
    )
    binary_input(
        name="LT_A",
        instance=55,
        description="Low Temperature Alarm",
        presentValue="inactive",
    )
    binary_input(
        name="SF_S",
        instance=56,
        description="Supply Fan Status",
        presentValue="active",
    )
    binary_input(
        name="DX_FAN_INPUT",
        instance=57,
        description="DX Fan Input",
        presentValue="inactive",
    )

    # --- Enum Points ---
    occ_states = make_state_text(["Occupied", "Unoccupied", "Standby"])
    multistate_value(
        name="OCC_SCHEDULE",
        instance=60,
        description="Occupancy Schedule",
        presentValue=1,
        stateText=occ_states,
    )
    multistate_value(
        name="EFF_OCC",
        instance=61,
        description="Effective Occupancy",
        presentValue=1,
        stateText=occ_states,
    )
    sys_states = make_state_text(["Off", "Warm-Up", "Cool-Down", "Heating", "Cooling", "Auto"])
    multistate_value(
        name="SYSTEM_MODE",
        instance=62,
        description="System Mode",
        presentValue=6,
        stateText=sys_states,
    )
    unit_states = make_state_text(["Off", "On", "Auto"])
    multistate_value(
        name="UNITEN_MODE",
        instance=63,
        description="Unit Enable Mode",
        presentValue=3,
        stateText=unit_states,
    )
    frz_states = make_state_text(["Normal", "Locked Out", "Reset"])
    return multistate_value(
        name="FRZ_RESET",
        instance=64,
        description="Freeze Reset",
        presentValue=1,
        stateText=frz_states,
    )
