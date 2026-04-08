"""
ALC VAV with Electric Reheat — BAC0 device profile
Source: .live-references/ALC_VAV_Generic.csv (real ALC VAV_ELECTRIC_RH export)

Device type: VAV CTRL/ACT/DP, 3UI, 2CO, 3 BO
Key naming: Hyphens (ZN-T, DA-T, EFFHTG-SP) — Niagara URL-encodes as $2d
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_value,
    binary_value, multistate_value, make_state_text,
)


def create_alc_vav_points():
    """Define all BACnet objects for an ALC VAV with electric reheat.

    Point names use hyphens per ALC convention.
    """
    # --- Temperatures ---
    analog_input(
        name="ZN-T",
        instance=1106,
        description="Zone Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.15,
    )
    analog_input(
        name="DA-T",
        instance=1019,
        description="Discharge Air Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=65.00,
    )
    analog_input(
        name="DA-VP",
        instance=1094,
        description="Discharge Air Velocity Pressure",
        properties={"units": "inchesOfWater"},
        presentValue=0.20,
    )

    # --- Supply Air ---
    analog_value(
        name="SA-T",
        instance=75,
        description="Supply Air Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=61.60,
    )
    analog_value(
        name="SA-F",
        instance=3515,
        description="Supply Air Flow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=981.56,
    )
    analog_value(
        name="SA-KFACTOR",
        instance=3112,
        description="Supply Air K Factor",
        presentValue=2.00,
    )
    analog_value(
        name="SA-AREA",
        instance=3111,
        description="Supply Air Area",
        properties={"units": "squareFeet"},
        presentValue=0.79,
    )

    # --- Zone Setpoints ---
    analog_value(
        name="EFFHTG-SP",
        instance=3473,
        description="Effective Heating Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.00,
    )
    analog_value(
        name="EFFCLG-SP",
        instance=3472,
        description="Effective Cooling Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=74.00,
    )
    analog_value(
        name="HTGOCC-SP",
        instance=3475,
        description="Heating Occupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.00,
    )
    analog_value(
        name="CLGOCC-SP",
        instance=3474,
        description="Cooling Occupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=74.00,
    )
    analog_value(
        name="HTGSTBY-SP",
        instance=3477,
        description="Heating Standby Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=66.00,
    )
    analog_value(
        name="CLGSTBY-SP",
        instance=3476,
        description="Cooling Standby Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=77.00,
    )
    analog_value(
        name="HTGUNOCC-SP",
        instance=3479,
        description="Heating Unoccupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=61.00,
    )
    analog_value(
        name="CLGUNOCC-SP",
        instance=3478,
        description="Cooling Unoccupied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=82.00,
    )
    analog_value(
        name="ZNT-SP",
        instance=12,
        description="Zone Temperature Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.00,
    )

    # --- DAT Setpoints ---
    analog_value(
        name="DATHTGMAX-SP",
        instance=3119,
        description="Discharge Air Temperature Heating Max Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=105.00,
    )
    analog_value(
        name="DATSATISFIED-SP",
        instance=3120,
        description="Discharge Air Temperature Satisfied Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=61.60,
    )

    # --- Outputs (as AV — BAC0 AO objects reject writes from Niagara) ---
    analog_value(
        name="HTG-O",
        instance=2014,
        description="Heating Output",
        properties={"units": "percent"},
        presentValue=12.21,
    )
    analog_value(
        name="DPR-O",
        instance=2131,
        description="Supply Air Damper Output",
        properties={"units": "percent"},
        presentValue=61.64,
    )

    # --- Control Values ---
    analog_value(
        name="CLG-O",
        instance=3615,
        description="Cooling Output",
        properties={"units": "percent"},
        presentValue=0.00,
    )
    analog_value(
        name="CLG-REQ",
        instance=5869,
        description="Cooling Request",
        presentValue=0.00,
    )
    analog_value(
        name="HTG-REQ",
        instance=5870,
        description="Heating Request",
        presentValue=0.00,
    )
    analog_value(
        name="PRESS-REQ",
        instance=5871,
        description="Pressure Request",
        presentValue=0.00,
    )
    analog_value(
        name="SPMAXPOS",
        instance=5715,
        description="Setpoint Max Position",
        presentValue=80.00,
    )
    analog_value(
        name="DPR-POS",
        instance=280939,
        description="Damper Position",
        properties={"units": "percent"},
        presentValue=61.02,
    )

    # --- Airflow Setpoints ---
    analog_value(
        name="SAFLOW-SP",
        instance=3384,
        description="Supply Air Flow Setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=980.00,
    )
    analog_value(
        name="CLG-MAXFLOW",
        instance=3108,
        description="Cooling Max Flow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=980.00,
    )
    analog_value(
        name="HTGOCC-MINFLOW",
        instance=3110,
        description="Heating Occupied Min Flow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=980.00,
    )
    analog_value(
        name="CLGOCC-MINFLOW",
        instance=3109,
        description="Cooling Occupied Min Flow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=980.00,
    )

    # --- Status / Mode ---
    binary_value(
        name="TUNING-RESET",
        instance=769,
        description="Tuning Reset",
        presentValue="inactive",
    )
    binary_value(
        name="HTG-EN",
        instance=7,
        description="Heating Enable",
        presentValue="active",
    )
    binary_value(
        name="PFRESTART-EN",
        instance=3391,
        description="Pre-Functional Restart Enable",
        presentValue="inactive",
    )
    binary_value(
        name="AUTOCAL-C",
        instance=4,
        description="Auto Calibration Command",
        presentValue="inactive",
    )

    # --- Multistate Values ---
    occ_states = make_state_text(["Occupied", "Unoccupied", "Standby"])
    multistate_value(
        name="OCC-SCHEDULE",
        instance=59,
        description="Occupancy Schedule",
        presentValue=1,
        stateText=occ_states,
    )
    multistate_value(
        name="EFF-OCC",
        instance=3290,
        description="Effective Occupancy",
        presentValue=1,
        stateText=occ_states,
    )
    sys_states = make_state_text(["Off", "Warm-Up", "Cool-Down", "Setback", "Setup", "Auto"])
    multistate_value(
        name="SYSTEM-MODE",
        instance=76,
        description="System Mode",
        presentValue=6,
        stateText=sys_states,
    )
    unit_states = make_state_text(["Off", "On"])
    multistate_value(
        name="UNITEN-MODE",
        instance=77,
        description="Unit Enable Mode",
        presentValue=2,
        stateText=unit_states,
    )
    znt_states = make_state_text(["Satisfied", "Heating", "Cooling", "Deadband"])
    return multistate_value(
        name="ZNT-STATE",
        instance=3466,
        description="Zone Temperature State",
        presentValue=4,
        stateText=znt_states,
    )
