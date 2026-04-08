"""
AAON VCCX-IP — Rooftop Unit Controller.
BACnet MS/TP field device. Based on VCCX-IP Controller Technical Guide Rev K
and KB point list from ahu-sequences.md.

Supports: VAV operation, economizer, staged DX cooling, modulating gas heat,
dehumidification mode.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_value,
    binary_input, binary_value,
    multistate_value, make_state_text,
)


def create_aaon_rtu_points():
    """
    AAON VCCX-IP RTU BACnet point list.
    Based on real VCCX-IP controller with BACnet interface.
    """
    # ================================================================
    # Analog Inputs (Sensors)
    # ================================================================
    analog_input(
        name="SA-T",
        instance=1,
        description="Supply air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=55.0,
    )
    analog_input(
        name="RA-T",
        instance=2,
        description="Return air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_input(
        name="MA-T",
        instance=3,
        description="Mixed air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=65.0,
    )
    analog_input(
        name="OA-T",
        instance=4,
        description="Outdoor air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=85.0,
    )
    analog_input(
        name="SA-SP",
        instance=5,
        description="Supply duct static pressure",
        properties={"units": "inchesOfWater"},
        presentValue=1.0,
    )
    analog_input(
        name="RA-RH",
        instance=6,
        description="Return air relative humidity",
        properties={"units": "percentRelativeHumidity"},
        presentValue=50.0,
    )
    analog_input(
        name="FILT-DP",
        instance=7,
        description="Filter differential pressure",
        properties={"units": "inchesOfWater"},
        presentValue=0.6,
    )
    analog_input(
        name="SUCT-T",
        instance=8,
        description="Suction saturation temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=40.0,
    )
    analog_input(
        name="SUCT-P",
        instance=9,
        description="Suction pressure",
        properties={"units": "poundsForcePerSquareInch"},
        presentValue=68.0,
    )
    analog_input(
        name="COND-P",
        instance=10,
        description="Condensing pressure",
        properties={"units": "poundsForcePerSquareInch"},
        presentValue=280.0,
    )

    # ================================================================
    # Analog Commands (as AV — BAC0 AO objects reject writes from Niagara)
    # ================================================================
    analog_value(
        name="SF-SPD",
        instance=50,
        description="Supply fan VFD speed command",
        properties={"units": "percent"},
        presentValue=0.0,
    )
    analog_value(
        name="OA-DPR",
        instance=51,
        description="Outdoor air/economizer damper command",
        properties={"units": "percent"},
        presentValue=15.0,
    )
    analog_value(
        name="HTG-O",
        instance=52,
        description="Modulating gas heat output",
        properties={"units": "percent"},
        presentValue=0.0,
    )

    # ================================================================
    # Binary Inputs (Status/Proof)
    # ================================================================
    binary_input(
        name="SF-STS",
        instance=1,
        description="Supply fan proof of airflow",
        presentValue=False,
    )
    binary_input(
        name="COMP1-STS",
        instance=2,
        description="Compressor circuit 1 status",
        presentValue=False,
    )
    binary_input(
        name="COMP2-STS",
        instance=3,
        description="Compressor circuit 2 status",
        presentValue=False,
    )
    binary_input(
        name="HP-LOCKOUT",
        instance=4,
        description="High pressure safety lockout",
        presentValue=False,
    )
    binary_input(
        name="LP-LOCKOUT",
        instance=5,
        description="Low pressure safety lockout",
        presentValue=False,
    )
    binary_input(
        name="SMOKE-DET",
        instance=6,
        description="Duct smoke detector",
        presentValue=False,
    )
    binary_input(
        name="FREEZE-STAT",
        instance=7,
        description="Low limit freeze thermostat",
        presentValue=False,
    )
    binary_input(
        name="GAS-VLV-STS",
        instance=8,
        description="Gas valve proving status",
        presentValue=False,
    )

    # ================================================================
    # Binary Commands (as BV — BAC0 BO objects reject writes from Niagara)
    # ================================================================
    binary_value(
        name="SF-CMD",
        instance=50,
        description="Supply fan start/stop command",
        presentValue=False,
    )
    binary_value(
        name="COMP1-CMD",
        instance=51,
        description="Compressor circuit 1 enable",
        presentValue=False,
    )
    binary_value(
        name="COMP2-CMD",
        instance=52,
        description="Compressor circuit 2 enable",
        presentValue=False,
    )
    binary_value(
        name="HTG-STG1",
        instance=53,
        description="Heat stage 1 (backup staged heat)",
        presentValue=False,
    )

    # ================================================================
    # Setpoints and Status
    # ================================================================
    analog_value(
        name="SA-T-SP",
        instance=1,
        description="Supply air temperature setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=55.0,
    )
    analog_value(
        name="SA-SP-SP",
        instance=2,
        description="Duct static pressure setpoint",
        properties={"units": "inchesOfWater"},
        presentValue=1.5,
    )
    analog_value(
        name="ECON-ENABLE-SP",
        instance=3,
        description="Economizer enable OAT setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=75.0,
    )
    analog_value(
        name="CLG-LOCKOUT-SP",
        instance=4,
        description="Mechanical cooling lockout OAT",
        properties={"units": "degreesFahrenheit"},
        presentValue=45.0,
    )
    analog_value(
        name="OCC-CLG-SP",
        instance=5,
        description="Occupied cooling setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=75.0,
    )
    analog_value(
        name="OCC-HTG-SP",
        instance=6,
        description="Occupied heating setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.0,
    )
    analog_value(
        name="MIN-OA-POS",
        instance=7,
        description="Minimum OA damper position",
        properties={"units": "percent"},
        presentValue=15.0,
    )

    # --- Operating Mode ---
    modes = make_state_text([
        "Off", "Vent", "Economizer", "Mech-Clg-1", "Mech-Clg-2",
        "Heat", "Dehum", "Morning-WU"
    ])
    multistate_value(
        name="UNIT-MODE",
        instance=1,
        description="Current unit operating mode",
        presentValue=1,  # Off
        properties={"stateText": modes},
    )

    # --- Alarms ---
    binary_value(
        name="SF-FAIL-ALM",
        instance=1,
        description="Supply fan failure alarm",
        presentValue=False,
    )
    binary_value(
        name="FILT-DP-ALM",
        instance=2,
        description="Filter high DP alarm (dirty filter)",
        presentValue=False,
    )
    binary_value(
        name="FREEZE-ALM",
        instance=3,
        description="Freeze stat trip alarm",
        presentValue=False,
    )
    binary_value(
        name="HP-ALM",
        instance=4,
        description="High pressure lockout alarm",
        presentValue=False,
    )
    binary_value(
        name="LP-ALM",
        instance=5,
        description="Low pressure lockout alarm",
        presentValue=False,
    )
    return binary_value(
        name="SMOKE-ALM",
        instance=6,
        description="Duct smoke detector alarm",
        presentValue=False,
    )
