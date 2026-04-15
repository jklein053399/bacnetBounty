"""
G36 Section 5.16 — Virtual Multi-Zone VAV AHU
Creates a BACnet device with standard AHU point list matching the KB.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_output, binary_value,
    multistate_value, make_state_text,
)


def create_ahu_points():
    """
    Define all BACnet objects for a multi-zone VAV AHU.
    Call once before add_objects_to_application().
    """
    # --- Analog Inputs (Sensors) ---
    analog_input(
        name="AHU1_SA_TEMP", instance=1001,
        description="Supply air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=55.0,
    )
    analog_input(
        name="AHU1_RA_TEMP", instance=1002,
        description="Return air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_input(
        name="AHU1_MA_TEMP", instance=1003,
        description="Mixed air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=60.0,
    )
    analog_input(
        name="AHU1_OA_TEMP", instance=1004,
        description="Outdoor air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=85.0,
    )
    analog_input(
        name="AHU1_SA_SP", instance=1005,
        description="Supply duct static pressure",
        properties={"units": "inchesOfWater"},
        presentValue=1.0,
    )
    analog_input(
        name="AHU1_FILT_DP", instance=1006,
        description="Filter differential pressure",
        properties={"units": "inchesOfWater"},
        presentValue=0.5,
    )
    analog_input(
        name="AHU1_OA_RH", instance=1007,
        description="Outdoor air relative humidity",
        properties={"units": "percentRelativeHumidity"},
        presentValue=50.0,
    )
    analog_input(
        name="AHU1_RA_RH", instance=1008,
        description="Return air relative humidity",
        properties={"units": "percentRelativeHumidity"},
        presentValue=50.0,
    )

    # --- Analog Outputs (Commands) ---
    analog_output(
        name="AHU1_CHW_VLV", instance=1010,
        description="Chilled water valve command",
        properties={"units": "percent"},
        presentValue=0.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_output(
        name="AHU1_HW_VLV", instance=1011,
        description="Hot water valve command",
        properties={"units": "percent"},
        presentValue=0.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_output(
        name="AHU1_OA_DMPR", instance=1012,
        description="Outdoor air damper command",
        properties={"units": "percent"},
        presentValue=20.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_output(
        name="AHU1_RA_DMPR", instance=1013,
        description="Return air damper command",
        properties={"units": "percent"},
        presentValue=80.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_output(
        name="AHU1_SF_SPD", instance=1014,
        description="Supply fan VFD speed command",
        properties={"units": "percent"},
        presentValue=0.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )

    # --- Binary Inputs (Status/Proof) ---
    binary_input(
        name="AHU1_SF_STS", instance=1020,
        description="Supply fan proof of airflow",
        presentValue=False,
    )
    binary_input(
        name="AHU1_FREEZE_STAT", instance=1021,
        description="Low limit freeze stat",
        presentValue=False,
    )
    binary_input(
        name="AHU1_SMOKE_SA", instance=1022,
        description="Supply duct smoke detector",
        presentValue=False,
    )
    binary_input(
        name="AHU1_FIRE_ALM", instance=1023,
        description="Fire alarm interface",
        presentValue=False,
    )

    # --- Binary Outputs ---
    binary_output(
        name="AHU1_SF_CMD", instance=1030,
        description="Supply fan start/stop command",
        presentValue=False,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )

    # --- Setpoints and Calculated Values ---
    analog_value(
        name="AHU1_SA_TEMP_SP", instance=1040,
        description="Supply air temperature setpoint (active)",
        properties={"units": "degreesFahrenheit"},
        presentValue=55.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_value(
        name="AHU1_SA_SP_SP", instance=1041,
        description="Duct static pressure setpoint (active)",
        properties={"units": "inchesOfWater"},
        presentValue=1.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_value(
        name="AHU1_SA_TEMP_LOOP", instance=1042,
        description="SAT control loop output 0-100%",
        properties={"units": "percent"},
        presentValue=50.0,
    )

    # --- Mode ---
    modes = make_state_text([
        "Unoccupied", "Setback", "Warmup", "Setup", "Cooldown", "Occupied"
    ])
    multistate_value(
        name="AHU1_OCC_MODE", instance=1050,
        description="Current AHU operating mode",
        presentValue=1,  # Unoccupied
        properties={"stateText": modes},
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )

    # --- Alarms ---
    binary_value(
        name="AHU1_SF_FAIL_ALM", instance=1060,
        description="Supply fan failure alarm",
        presentValue=False,
    )
    binary_value(
        name="AHU1_FREEZE_ALM", instance=1061,
        description="Freeze stat trip alarm",
        presentValue=False,
    )
    binary_value(
        name="AHU1_SMOKE_ALM", instance=1062,
        description="Duct smoke detector alarm",
        presentValue=False,
    )

    # --- FDD ---
    analog_value(
        name="AHU1_FREEZE_STAGE", instance=1070,
        description="Freeze protection stage 0-3",
        presentValue=0.0,
    )
    return analog_value(
        name="AHU1_FAULT_CODE", instance=1071,
        description="FDD fault code (0=none, 1-4 per G36)",
        presentValue=0.0,
    )
