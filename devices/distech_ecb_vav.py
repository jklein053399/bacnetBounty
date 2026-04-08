"""
Distech ECB VAV — BAC0 device profile
Source: .live-references/Distech_VAV_Generic.csv (real Distech ECB_VAV export)

Device type: ECB VAV controller
Key naming: CamelCase and underscores (ZN_T, DA_T, OccCoolSP, ActHeatSP, EffectSP)
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_output, binary_value,
    multistate_value, make_state_text,
)


def create_distech_vav_points():
    """Define all BACnet objects for a Distech ECB VAV.

    Point names use Distech CamelCase convention.
    """
    # --- Temperatures ---
    analog_input(
        name="DA_T",
        instance=1,
        description="Discharge Air Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=100.98,
    )
    analog_input(
        name="VAV Differential Pressure",
        instance=5,
        description="VAV Differential Pressure",
        properties={"units": "inchesOfWater"},
        presentValue=0.12,
    )
    analog_input(
        name="DamperPosition",
        instance=6,
        description="Damper Position",
        properties={"units": "percent"},
        presentValue=54.20,
    )
    analog_input(
        name="ComSensor 1 Temp",
        instance=5001,
        description="Communication Sensor 1 Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=71.52,
    )

    # --- Outputs ---
    analog_output(
        name="DamperCommand",
        instance=7,
        description="Damper Command",
        properties={"units": "percent"},
        presentValue=54.33,
    )

    # --- Zone Points ---
    analog_value(
        name="ZN_T",
        instance=5,
        description="Zone Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=71.52,
    )
    analog_value(
        name="EffectSpaceTemp",
        instance=13,
        description="Effective Space Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=71.52,
    )
    analog_value(
        name="EffectSP",
        instance=50,
        description="Effective Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=71.50,
    )
    analog_value(
        name="SensorSetpoint",
        instance=20,
        description="Sensor Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.50,
    )

    # --- Active Setpoints (Distech: "Act" = Active/Effective) ---
    analog_value(
        name="ActCoolSP",
        instance=36,
        description="Active Cooling Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=73.50,
    )
    analog_value(
        name="ActHeatSP",
        instance=37,
        description="Active Heating Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=71.50,
    )

    # --- Occupied Setpoints ---
    analog_value(
        name="OccCoolSP",
        instance=40,
        description="Occupied Cooling Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=74.00,
    )
    analog_value(
        name="OccHeatSP",
        instance=41,
        description="Occupied Heating Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.00,
    )

    # --- Standby / Unoccupied Setpoints ---
    analog_value(
        name="StandbyCoolSP",
        instance=39,
        description="Standby Cooling Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=78.00,
    )
    analog_value(
        name="StandbyHeatSP",
        instance=42,
        description="Standby Heating Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=68.00,
    )
    analog_value(
        name="UnoccCoolSP",
        instance=38,
        description="Unoccupied Cooling Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=79.00,
    )
    analog_value(
        name="UnoccHeatSP",
        instance=43,
        description="Unoccupied Heating Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=67.00,
    )

    # --- DAT Setpoints ---
    analog_value(
        name="DischAirSP",
        instance=12,
        description="Discharge Air Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=150.00,
    )
    analog_value(
        name="MaxDischAirSP",
        instance=56,
        description="Max Discharge Air Setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=150.00,
    )

    # --- Heating Output ---
    analog_value(
        name="HTG_O",
        instance=4,
        description="Heating Output",
        properties={"units": "percent"},
        presentValue=100.00,
    )

    # --- Airflow Points ---
    analog_value(
        name="ActFlow",
        instance=1,
        description="Actual Flow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=318.28,
    )
    analog_value(
        name="ActFlowSP",
        instance=2,
        description="Actual Flow Setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=317.68,
    )
    analog_value(
        name="MinFlowSP",
        instance=26,
        description="Minimum Flow Setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=170.00,
    )
    analog_value(
        name="MaxFlowCoolSP",
        instance=27,
        description="Maximum Flow Cooling Setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=420.00,
    )
    analog_value(
        name="MinFlowHeatSP",
        instance=28,
        description="Minimum Flow Heating Setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=170.00,
    )
    analog_value(
        name="MaxFlowHeatSP",
        instance=29,
        description="Maximum Flow Heating Setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=420.00,
    )

    # --- Configuration ---
    analog_value(
        name="KFactor",
        instance=32,
        description="K Factor",
        presentValue=935.00,
    )
    analog_value(
        name="DamperOvr",
        instance=9,
        description="Damper Override",
        properties={"units": "percent"},
        presentValue=54.33,
    )
    analog_value(
        name="OutdoorTemp",
        instance=8,
        description="Outdoor Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=50.00,
    )
    analog_value(
        name="DuctInTemp",
        instance=6,
        description="Duct Inlet Temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=55.00,
    )
    analog_value(
        name="TempErr",
        instance=51,
        description="Temperature Error",
        properties={"units": "degreesFahrenheit"},
        presentValue=0.00,
    )
    analog_value(
        name="TerminalLoad",
        instance=44,
        description="Terminal Load",
        presentValue=-79.54,
    )

    # --- Binary Points ---
    binary_input(
        name="OCC_S",
        instance=2,
        description="Occupancy Sensor",
        presentValue="active",
    )
    binary_value(
        name="UnitStatus",
        instance=1,
        description="Unit Status",
        presentValue="active",
    )
    binary_value(
        name="RoomOccupancy",
        instance=12,
        description="Room Occupancy",
        presentValue="active",
    )
    binary_value(
        name="HotWaterReheat",
        instance=18,
        description="Hot Water Reheat",
        presentValue="active",
    )

    # --- Multistate Values ---
    occ_states = make_state_text(["Occupied", "Unoccupied", "Standby", "NotSet"])
    multistate_value(
        name="OccupancyCmd",
        instance=1,
        description="Occupancy Command",
        presentValue=1,
        stateText=occ_states,
    )
    multistate_value(
        name="OccupancyStatus",
        instance=15,
        description="Occupancy Status",
        presentValue=1,
        stateText=occ_states,
    )
    hvac_states = make_state_text(["Auto", "Heat", "Cool", "Off"])
    multistate_value(
        name="HVACModeCmd",
        instance=2,
        description="HVAC Mode Command",
        presentValue=1,
        stateText=hvac_states,
    )
    return multistate_value(
        name="HVACModeStatus",
        instance=14,
        description="HVAC Mode Status",
        presentValue=2,
        stateText=hvac_states,
    )
