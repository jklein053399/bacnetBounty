"""
JCI FEC-2621 — General Purpose Controller (Misc Equipment).
BACnet MS/TP field controller serving:
  - 2 Exhaust Fans (EF-1, EF-2)
  - 2 Cabinet Unit Heaters (CUH-1, CUH-2)
  - Building pressure monitoring (no control)
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_output, binary_value,
)


def create_misc_controller_points():
    """
    JCI FEC-2621 misc controller point list.
    2 EFs + 2 CUHs + building pressure monitoring.
    """
    base = 0

    # ================================================================
    # Exhaust Fans (EF-1, EF-2)
    # ================================================================
    for ef_id in [1, 2]:
        b = base + (ef_id - 1) * 10

        binary_output(
            name=f"EF{ef_id}-CMD",
            instance=b + 1,
            description=f"Exhaust fan {ef_id} start/stop command",
            presentValue=False,
        )
        binary_input(
            name=f"EF{ef_id}-STS",
            instance=b + 2,
            description=f"Exhaust fan {ef_id} running status (proof)",
            presentValue=False,
        )
        binary_value(
            name=f"EF{ef_id}-FAIL-ALM",
            instance=b + 3,
            description=f"Exhaust fan {ef_id} failure alarm",
            presentValue=False,
        )
        analog_input(
            name=f"EF{ef_id}-AMPS",
            instance=b + 4,
            description=f"Exhaust fan {ef_id} motor amps",
            properties={"units": "amperes"},
            presentValue=0.0,
        )
        analog_value(
            name=f"EF{ef_id}-RUN-HRS",
            instance=b + 5,
            description=f"Exhaust fan {ef_id} runtime hours",
            properties={"units": "hours"},
            presentValue=2500.0 + ef_id * 100,
        )

    # ================================================================
    # Cabinet Unit Heaters (CUH-1, CUH-2)
    # ================================================================
    for cuh_id in [1, 2]:
        b = base + 20 + (cuh_id - 1) * 10

        binary_output(
            name=f"CUH{cuh_id}-CMD",
            instance=b + 1,
            description=f"Cabinet unit heater {cuh_id} enable command",
            presentValue=False,
        )
        binary_input(
            name=f"CUH{cuh_id}-STS",
            instance=b + 2,
            description=f"Cabinet unit heater {cuh_id} status",
            presentValue=False,
        )
        analog_input(
            name=f"CUH{cuh_id}-ZN-T",
            instance=b + 3,
            description=f"CUH {cuh_id} zone temperature",
            properties={"units": "degreesFahrenheit"},
            presentValue=68.0,
        )
        analog_value(
            name=f"CUH{cuh_id}-SP",
            instance=b + 4,
            description=f"CUH {cuh_id} temperature setpoint",
            properties={"units": "degreesFahrenheit"},
            presentValue=65.0,
        )
        analog_output(
            name=f"CUH{cuh_id}-VLV",
            instance=b + 5,
            description=f"CUH {cuh_id} hot water valve output",
            properties={"units": "percent"},
            presentValue=0.0,
        )
        binary_value(
            name=f"CUH{cuh_id}-ZN-T-LO-ALM",
            instance=b + 6,
            description=f"CUH {cuh_id} zone low temperature alarm",
            presentValue=False,
        )

    # ================================================================
    # Building Pressure (Monitoring Only)
    # ================================================================
    analog_input(
        name="BLDG-SP",
        instance=50,
        description="Building static pressure (relative to outdoors)",
        properties={"units": "inchesOfWater"},
        presentValue=0.05,
    )
    analog_value(
        name="BLDG-SP-HI-LIM",
        instance=51,
        description="Building pressure high alarm limit",
        properties={"units": "inchesOfWater"},
        presentValue=0.15,
    )
    analog_value(
        name="BLDG-SP-LO-LIM",
        instance=52,
        description="Building pressure low alarm limit",
        properties={"units": "inchesOfWater"},
        presentValue=-0.02,
    )
    binary_value(
        name="BLDG-SP-HI-ALM",
        instance=53,
        description="Building pressure high alarm",
        presentValue=False,
    )
    return binary_value(
        name="BLDG-SP-LO-ALM",
        instance=54,
        description="Building pressure low alarm",
        presentValue=False,
    )
