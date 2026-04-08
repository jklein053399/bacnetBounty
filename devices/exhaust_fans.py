"""
Misc Controller — 2 Exhaust Fans with Status, Speed, and Command.
BACnet device for Phase 3 Workbench integration testing.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_output, binary_value,
)


def create_exhaust_fan_controller():
    """
    Misc controller with 2 exhaust fans.
    Each fan has: Command (BO), Status (BI), Speed Command (AO), Speed Feedback (AI).
    """
    for ef_id in [1, 2]:
        b = (ef_id - 1) * 10

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
        analog_output(
            name=f"EF{ef_id}-SPD-CMD",
            instance=b + 3,
            description=f"Exhaust fan {ef_id} VFD speed command",
            properties={"units": "percent"},
            presentValue=0.0,
        )
        analog_input(
            name=f"EF{ef_id}-SPD-FBK",
            instance=b + 4,
            description=f"Exhaust fan {ef_id} VFD speed feedback",
            properties={"units": "percent"},
            presentValue=0.0,
        )
        binary_value(
            name=f"EF{ef_id}-FAIL-ALM",
            instance=b + 5,
            description=f"Exhaust fan {ef_id} failure alarm",
            presentValue=False,
        )
        analog_value(
            name=f"EF{ef_id}-RUN-HRS",
            instance=b + 6,
            description=f"Exhaust fan {ef_id} runtime hours",
            properties={"units": "hours"},
            presentValue=2500.0 + ef_id * 100,
        )

    return binary_value(
        name="EF2-FAIL-ALM",
        instance=15,
        description="Exhaust fan 2 failure alarm",
        presentValue=False,
    )
