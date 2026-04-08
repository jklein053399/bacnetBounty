"""
JCI FEC-2611 — VAV Terminal Unit Controller.
BACnet MS/TP field controller for single-duct VAV with reheat.
Each instance is a separate BACnet device on the trunk.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_value,
    multistate_value, make_state_text,
)


def create_fec_vav_points(zone_name: str, design_cfm: float = 800):
    """
    JCI FEC-2611 VAV controller point list.
    Matches standard JCI VAV BACnet object naming conventions.

    Args:
        zone_name: Zone identifier (e.g., "Interior-1")
        design_cfm: Maximum cooling airflow for this box
    """
    # --- Hardware Inputs ---
    analog_input(
        name="ZN-T",
        instance=1,
        description=f"Zone temperature — {zone_name}",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_input(
        name="DA-T",
        instance=2,
        description="Discharge air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_input(
        name="DA-CFM",
        instance=3,
        description="Discharge airflow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=design_cfm * 0.3,
    )

    # --- Hardware Outputs ---
    analog_output(
        name="DPR-O",
        instance=1,
        description="Damper actuator output",
        properties={"units": "percent"},
        presentValue=50.0,
    )
    analog_output(
        name="HTG-O",
        instance=2,
        description="Reheat valve output",
        properties={"units": "percent"},
        presentValue=0.0,
    )

    # --- Setpoints ---
    analog_value(
        name="ZN-SP",
        instance=1,
        description="Active zone temperature setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_value(
        name="OCC-COOL-SP",
        instance=2,
        description="Occupied cooling setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=75.0,
    )
    analog_value(
        name="OCC-HEAT-SP",
        instance=3,
        description="Occupied heating setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.0,
    )
    analog_value(
        name="UNOCC-COOL-SP",
        instance=4,
        description="Unoccupied cooling setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=85.0,
    )
    analog_value(
        name="UNOCC-HEAT-SP",
        instance=5,
        description="Unoccupied heating setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=60.0,
    )
    analog_value(
        name="CFM-MAX",
        instance=6,
        description="Maximum airflow setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=design_cfm,
    )
    analog_value(
        name="CFM-MIN",
        instance=7,
        description="Minimum airflow setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=design_cfm * 0.3,
    )
    analog_value(
        name="CFM-SP",
        instance=8,
        description="Active airflow setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=design_cfm * 0.3,
    )
    analog_value(
        name="DA-T-MAX",
        instance=9,
        description="Maximum discharge air temperature limit",
        properties={"units": "degreesFahrenheit"},
        presentValue=90.0,
    )

    # --- Control Status ---
    analog_value(
        name="CLG-O",
        instance=10,
        description="Cooling loop output",
        properties={"units": "percent"},
        presentValue=0.0,
    )
    analog_value(
        name="HTG-LOOP",
        instance=11,
        description="Heating loop output",
        properties={"units": "percent"},
        presentValue=0.0,
    )

    states = make_state_text(["Heating", "Deadband", "Cooling", "Unocc-Htg", "Unocc-Clg"])
    multistate_value(
        name="ZN-STATE",
        instance=1,
        description="Zone operating state",
        presentValue=2,  # Deadband
        properties={"stateText": states},
    )

    binary_value(
        name="OCC-STS",
        instance=1,
        description="Zone occupancy status",
        presentValue=True,
    )

    # --- Alarms ---
    binary_value(
        name="ZN-T-HI-ALM",
        instance=10,
        description="Zone temperature high alarm",
        presentValue=False,
    )
    binary_value(
        name="ZN-T-LO-ALM",
        instance=11,
        description="Zone temperature low alarm",
        presentValue=False,
    )
    binary_value(
        name="LO-FLOW-ALM",
        instance=12,
        description="Low airflow alarm",
        presentValue=False,
    )
    return binary_value(
        name="DA-T-HI-ALM",
        instance=13,
        description="Discharge air temperature high alarm",
        presentValue=False,
    )
