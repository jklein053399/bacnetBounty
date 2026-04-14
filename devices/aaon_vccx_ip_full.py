"""
AAON VCCX-IP — Full BACnet device model from live RTU export.

437 points matching a real AAON VCCX-IP RTU (device 3600005):
  197 Analog Inputs, 99 Analog Values, 141 Binary Inputs.

Uses the live CSV export as ground truth, supplemented by PIC data.
The live unit has FAC (fan array) and power metering points not in the
base PIC, and omits RSMZ compressor module points not installed.

Sources:
  - device-data/aaon_vccx_ip_live_export.json (primary — from real RTU)
  - device-data/aaon_vccx_ip_full_pic.json (supplemental — full PIC)
"""

import json
import os
import re

from BAC0.core.devices.local.factory import (
    analog_input,
    analog_value,
    binary_input,
    multistate_value,
    make_state_text,
)

# Path to the live export JSON (ground truth)
_LIVE_JSON = os.path.join(
    os.path.dirname(__file__), "..", "device-data", "aaon_vccx_ip_live_export.json"
)

# Fallback to PIC if live export not available
_PIC_JSON = os.path.join(
    os.path.dirname(__file__), "..", "device-data", "aaon_vccx_ip_full_pic.json"
)


def _sanitize_name(name: str) -> str:
    """Convert PIC parameter name to BACnet-safe object name.

    Rules: replace spaces with underscores, strip special chars,
    collapse multiple underscores.
    """
    s = name.replace("/", "_").replace("#", "").replace("(", "").replace(")", "")
    s = re.sub(r"[^A-Za-z0-9_ ]", "", s)
    s = s.strip().replace(" ", "_")
    s = re.sub(r"_+", "_", s)
    return s


def _load_points() -> dict:
    """Load point data — prefer live export, fall back to PIC."""
    if os.path.exists(_LIVE_JSON):
        with open(_LIVE_JSON) as f:
            return json.load(f)
    with open(_PIC_JSON) as f:
        return json.load(f)


def _default_value(bacnet_type: str, instance: int, name: str) -> float | bool:
    """Assign a reasonable default presentValue based on point type and name."""
    name_lower = name.lower()

    if bacnet_type == "binaryInput":
        # Alarms default to False, status default to False
        return False

    if bacnet_type == "analogValue":
        # Setpoints get reasonable defaults
        if "cooling" in name_lower and "setpoint" in name_lower:
            return 75.0
        if "heating" in name_lower and "setpoint" in name_lower:
            return 70.0
        if "supply" in name_lower and "setpoint" in name_lower:
            return 55.0
        if "humidity" in name_lower and "setpoint" in name_lower:
            return 50.0
        if "economizer" in name_lower and "setpoint" in name_lower:
            return 75.0
        if "lockout" in name_lower:
            return 45.0
        if "minimum" in name_lower and ("position" in name_lower or "economizer" in name_lower):
            return 15.0
        if "offset" in name_lower:
            return 5.0
        if "deadband" in name_lower:
            return 2.0
        if "override" in name_lower:
            return 0.0
        return 0.0

    # analogInput defaults based on sensor type
    if "temperature" in name_lower or "temp" in name_lower:
        if "outdoor" in name_lower:
            return 85.0
        if "supply" in name_lower:
            return 55.0
        if "return" in name_lower:
            return 72.0
        if "space" in name_lower:
            return 72.0
        if "saturation" in name_lower or "suction" in name_lower:
            return 40.0
        return 70.0
    if "humidity" in name_lower:
        return 50.0
    if "pressure" in name_lower:
        if "building" in name_lower:
            return 0.05
        if "suction" in name_lower:
            return 68.0
        return 0.0
    if "position" in name_lower or "signal" in name_lower:
        return 0.0
    if "setpoint" in name_lower:
        return 72.0
    if "mode" in name_lower or "status" in name_lower:
        return 0.0
    if "version" in name_lower:
        return 11.0  # Software version
    if "co2" in name_lower or "carbon" in name_lower:
        return 400.0
    if "enthalpy" in name_lower:
        return 30.0

    return 0.0


def _unit_for_point(name: str) -> str | None:
    """Infer BACnet engineering units from point name."""
    name_lower = name.lower()

    if "temperature" in name_lower or "temp" in name_lower:
        if "dew" in name_lower or "wetbulb" in name_lower:
            return "degreesFahrenheit"
        return "degreesFahrenheit"
    if "humidity" in name_lower:
        return "percentRelativeHumidity"
    if "pressure" in name_lower:
        if "building" in name_lower:
            return "inchesOfWater"
        if "suction" in name_lower or "discharge" in name_lower or "liquid" in name_lower:
            return "poundsForcePerSquareInch"
        return "inchesOfWater"
    if "position" in name_lower or "signal" in name_lower or "percent" in name_lower:
        return "percent"
    if "setpoint" in name_lower:
        if "humidity" in name_lower:
            return "percentRelativeHumidity"
        return "degreesFahrenheit"
    if "offset" in name_lower or "deadband" in name_lower:
        return "degreesFahrenheit"
    if "co2" in name_lower or "carbon" in name_lower:
        return "partsPerMillion"
    if "enthalpy" in name_lower:
        return "btusPerPound"
    if "cfm" in name_lower or "airflow" in name_lower or "flow" in name_lower:
        return "cubicFeetPerMinute"

    return None


def create_aaon_vccx_ip_full_points():
    """Create all BACnet objects from the AAON VCCX-IP live export.

    Returns the last created object (BAC0 pattern for add_objects_to_application).
    """
    data = _load_points()
    points = data["points"]
    last_obj = None

    seen_names = set()
    for pt in points:
        name = pt["name"]
        # Disambiguate duplicate names (e.g., "Not_used") by appending instance
        if name in seen_names:
            _type_abbr = {"analogInput": "AI", "analogValue": "AV", "binaryInput": "BI", "multistateValue": "MV"}
            name = f"{name} {_type_abbr.get(pt['bacnet_type'], 'OBJ')}{pt['instance']}"
        seen_names.add(name)
        instance = pt["instance"]
        desc = pt.get("description", pt["name"])
        btype = pt["bacnet_type"]

        # Use live value if available, otherwise infer default
        live_val = pt.get("value", "")
        if btype == "binaryInput":
            if live_val in ("Active", "active"):
                default = True
            elif live_val in ("Inactive", "inactive"):
                default = False
            else:
                default = _default_value(btype, instance, pt["name"])
        else:
            try:
                default = float(live_val)
            except (ValueError, TypeError):
                default = _default_value(btype, instance, pt["name"])

        units = _unit_for_point(pt["name"])
        props = {}
        if units:
            props["units"] = units
        else:
            # Override BAC0's default of "percent" — leave units blank
            props["units"] = "noUnits"

        if btype == "analogInput":
            last_obj = analog_input(
                name=name, instance=instance,
                description=desc, properties=props,
                presentValue=float(default),
            )
        elif btype == "analogValue":
            last_obj = analog_value(
                name=name, instance=instance,
                description=desc, properties=props,
                presentValue=float(default),
            )
        elif btype == "binaryInput":
            last_obj = binary_input(
                name=name, instance=instance,
                description=desc,
                presentValue=bool(default),
            )

    return last_obj


def get_point_count() -> int:
    """Return total point count."""
    data = _load_points()
    return len(data["points"])
