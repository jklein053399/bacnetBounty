"""
G36 Section 5.20 — Virtual Chiller Plant
Creates BACnet objects for a 2-chiller plant with pumps and cooling tower.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_output, binary_value,
    multistate_value, make_state_text,
)


def create_chiller_points(chiller_id: int):
    """Per-chiller BACnet points. chiller_id: 1 or 2."""
    base = 2000 + (chiller_id - 1) * 50

    binary_output(
        name=f"CH{chiller_id}_CMD", instance=base + 1,
        description=f"Chiller {chiller_id} start/stop",
        presentValue=False, # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    binary_input(
        name=f"CH{chiller_id}_STS", instance=base + 2,
        description=f"Chiller {chiller_id} running status",
        presentValue=False,
    )
    binary_value(
        name=f"CH{chiller_id}_ALM", instance=base + 3,
        description=f"Chiller {chiller_id} alarm",
        presentValue=False,
    )
    analog_input(
        name=f"CH{chiller_id}_CHWST", instance=base + 4,
        description=f"Chiller {chiller_id} leaving CHW temp",
        properties={"units": "degreesFahrenheit"},
        presentValue=44.0,
    )
    analog_input(
        name=f"CH{chiller_id}_CHWRT", instance=base + 5,
        description=f"Chiller {chiller_id} entering CHW temp",
        properties={"units": "degreesFahrenheit"},
        presentValue=56.0,
    )
    analog_input(
        name=f"CH{chiller_id}_LOAD", instance=base + 6,
        description=f"Chiller {chiller_id} percent load",
        properties={"units": "percent"},
        presentValue=0.0,
    )
    analog_input(
        name=f"CH{chiller_id}_KW", instance=base + 7,
        description=f"Chiller {chiller_id} power",
        properties={"units": "kilowatts"},
        presentValue=0.0,
    )
    analog_value(
        name=f"CH{chiller_id}_CHWST_SP", instance=base + 8,
        description=f"Chiller {chiller_id} CHWST setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=44.0, # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )


def create_pump_points(pump_type: str, pump_id: int):
    """Per-pump points. pump_type: 'CHWP' or 'CWP'. pump_id: 1 or 2."""
    base = 2200 + (pump_id - 1) * 20
    if pump_type == "CWP":
        base += 100

    binary_output(
        name=f"{pump_type}{pump_id}_CMD", instance=base + 1,
        description=f"{pump_type} {pump_id} start/stop",
        presentValue=False, # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    binary_input(
        name=f"{pump_type}{pump_id}_STS", instance=base + 2,
        description=f"{pump_type} {pump_id} running status",
        presentValue=False,
    )
    analog_output(
        name=f"{pump_type}{pump_id}_SPD", instance=base + 3,
        description=f"{pump_type} {pump_id} VFD speed",
        properties={"units": "percent"},
        presentValue=0.0, # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    binary_value(
        name=f"{pump_type}{pump_id}_FAIL_ALM", instance=base + 4,
        description=f"{pump_type} {pump_id} failure alarm",
        presentValue=False,
    )


def create_cooling_tower_points():
    """Cooling tower cell points."""
    base = 2500

    analog_output(
        name="CT1_FAN_SPD", instance=base + 1,
        description="Cooling tower fan VFD speed",
        properties={"units": "percent"},
        presentValue=0.0, # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    binary_input(
        name="CT1_FAN_STS", instance=base + 2,
        description="Cooling tower fan status",
        presentValue=False,
    )
    analog_input(
        name="CT1_BASIN_TEMP", instance=base + 3,
        description="Basin water temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=80.0,
    )


def create_plant_system_points():
    """Plant-level system points."""
    base = 2600

    analog_input(
        name="CHW_SUPPLY_TEMP", instance=base + 1,
        description="CHW supply header temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=44.0,
    )
    analog_input(
        name="CHW_RETURN_TEMP", instance=base + 2,
        description="CHW return header temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=56.0,
    )
    analog_input(
        name="CHW_DP", instance=base + 3,
        description="CHW differential pressure (remote)",
        properties={"units": "poundsForcePerSquareInch"},
        presentValue=10.0,
    )
    analog_input(
        name="CHW_FLOW", instance=base + 4,
        description="CHW plant flow",
        properties={"units": "usGallonsPerMinute"},
        presentValue=0.0,
    )
    analog_value(
        name="CHW_SUPPLY_TEMP_SP", instance=base + 5,
        description="Plant CHWST setpoint (active)",
        properties={"units": "degreesFahrenheit"},
        presentValue=44.0, # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_value(
        name="CHW_DP_SP", instance=base + 6,
        description="CHW DP setpoint (active)",
        properties={"units": "poundsForcePerSquareInch"},
        presentValue=12.0, # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_input(
        name="CW_SUPPLY_TEMP", instance=base + 7,
        description="CW supply temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=75.0,
    )
    analog_input(
        name="CW_RETURN_TEMP", instance=base + 8,
        description="CW return temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=85.0,
    )
    analog_input(
        name="OA_WB_TEMP", instance=base + 9,
        description="Outdoor wet bulb temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )

    # Plant status
    plant_modes = make_state_text(["Off", "Enabling", "Running", "Disabling"])
    multistate_value(
        name="CHW_PLANT_MODE", instance=base + 20,
        description="Plant operating mode",
        presentValue=1,
        properties={"stateText": plant_modes},
    )
    analog_value(
        name="NUM_CH_ON", instance=base + 21,
        description="Number of chillers running",
        presentValue=0.0,
    )
    analog_value(
        name="CHW_PLANT_LOAD", instance=base + 22,
        description="Plant cooling load (tons)",
        presentValue=0.0,
    )
    return analog_value(
        name="CHW_PLANT_KW_TON", instance=base + 23,
        description="Plant efficiency (kW/ton)",
        presentValue=0.0,
    )


def create_all_plant_points():
    """Create complete chiller plant point set."""
    create_chiller_points(1)
    create_chiller_points(2)
    create_pump_points("CHWP", 1)
    create_pump_points("CHWP", 2)
    create_pump_points("CWP", 1)
    create_pump_points("CWP", 2)
    create_cooling_tower_points()
    return create_plant_system_points()
