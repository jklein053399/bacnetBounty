"""
G36 Section 5.6 — Virtual VAV Box with Reheat
Creates a BACnet device with standard VAV point list matching the KB.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_output, binary_value,
    multistate_value, make_state_text,
)


def create_vav_points(box_id: int, design_cfm: float = 800):
    """
    Define all BACnet objects for a single-duct VAV with reheat.
    Call once per VAV box before add_objects_to_application().

    Args:
        box_id: Instance number offset (e.g., 100 for VAV-1, 200 for VAV-2)
        design_cfm: Maximum cooling airflow for this box
    """
    # --- Hardware I/O Points ---
    analog_input(
        name=f"VAV{box_id}_ZN_TEMP",
        instance=box_id + 1,
        description="Zone temperature sensor",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_input(
        name=f"VAV{box_id}_DA_FLOW",
        instance=box_id + 2,
        description="Discharge airflow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=300.0,
    )
    analog_input(
        name=f"VAV{box_id}_DA_TEMP",
        instance=box_id + 3,
        description="Discharge air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=72.0,
    )
    analog_output(
        name=f"VAV{box_id}_DMPR_CMD",
        instance=box_id + 4,
        description="Damper position command",
        properties={"units": "percent"},
        presentValue=50.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_output(
        name=f"VAV{box_id}_HTG_VLV",
        instance=box_id + 5,
        description="Reheat valve command",
        properties={"units": "percent"},
        presentValue=0.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )

    # --- Software / Network Points ---
    analog_value(
        name=f"VAV{box_id}_ZN_TEMP_CLG_SP",
        instance=box_id + 10,
        description="Occupied cooling setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=75.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_value(
        name=f"VAV{box_id}_ZN_TEMP_HTG_SP",
        instance=box_id + 11,
        description="Occupied heating setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=70.0,
        # is_commandable=True,  # Disabled: MRO conflict on Python 3.14
    )
    analog_value(
        name=f"VAV{box_id}_FLOW_SP",
        instance=box_id + 12,
        description="Active airflow setpoint",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=300.0,
    )
    analog_value(
        name=f"VAV{box_id}_FLOW_MAX_CLG",
        instance=box_id + 13,
        description="Maximum cooling airflow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=design_cfm,
    )
    analog_value(
        name=f"VAV{box_id}_FLOW_MIN",
        instance=box_id + 14,
        description="Minimum airflow",
        properties={"units": "cubicFeetPerMinute"},
        presentValue=design_cfm * 0.3,
    )
    analog_value(
        name=f"VAV{box_id}_CLG_LOOP",
        instance=box_id + 15,
        description="Cooling loop output",
        properties={"units": "percent"},
        presentValue=0.0,
    )
    analog_value(
        name=f"VAV{box_id}_HTG_LOOP",
        instance=box_id + 16,
        description="Heating loop output",
        properties={"units": "percent"},
        presentValue=0.0,
    )
    analog_value(
        name=f"VAV{box_id}_DA_TEMP_SP",
        instance=box_id + 17,
        description="Discharge air temperature setpoint",
        properties={"units": "degreesFahrenheit"},
        presentValue=90.0,
    )

    # --- Status ---
    states = make_state_text(["Heating-P1", "Heating-P2", "Deadband", "Cooling"])
    multistate_value(
        name=f"VAV{box_id}_ZONE_STATE",
        instance=box_id + 20,
        description="Current zone state",
        presentValue=3,  # Deadband
        properties={"stateText": states},
    )
    binary_value(
        name=f"VAV{box_id}_OCC_STS",
        instance=box_id + 21,
        description="Zone occupancy status",
        presentValue=True,
    )

    # --- Alarms ---
    binary_value(
        name=f"VAV{box_id}_LOW_FLOW_ALM",
        instance=box_id + 30,
        description="Low airflow alarm",
        presentValue=False,
    )
    binary_value(
        name=f"VAV{box_id}_DA_TEMP_HI_ALM",
        instance=box_id + 31,
        description="DAT high alarm",
        presentValue=False,
    )

    # --- Zone Requests (for AHU T&R) ---
    analog_value(
        name=f"VAV{box_id}_CLG_SAT_REQ",
        instance=box_id + 40,
        description="Cooling SAT reset requests",
        presentValue=0.0,
    )
    analog_value(
        name=f"VAV{box_id}_SP_RESET_REQ",
        instance=box_id + 41,
        description="Static pressure reset requests",
        presentValue=0.0,
    )
    return analog_value(
        name=f"VAV{box_id}_HTG_SAT_REQ",
        instance=box_id + 42,
        description="Heating SAT reset requests",
        presentValue=0.0,
    )
