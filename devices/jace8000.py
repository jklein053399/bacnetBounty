"""
Tridium JACE 8000 — Supervisory controller.
BACnet/IP on building network, routes to MS/TP trunk.
In simulation: exposes its own device with supervisor-level points.
"""
from BAC0.core.devices.local.factory import (
    analog_input, analog_value, binary_value,
    multistate_value, make_state_text,
)


def create_jace_points():
    """
    JACE 8000 supervisor points — system health, trunk status, global setpoints.
    """
    # --- System Health ---
    analog_value(
        name="JACE_CPU_LOAD",
        instance=1,
        description="JACE CPU utilization",
        properties={"units": "percent"},
        presentValue=25.0,
    )
    analog_value(
        name="JACE_MEMORY_USED",
        instance=2,
        description="JACE memory utilization",
        properties={"units": "percent"},
        presentValue=45.0,
    )
    analog_value(
        name="JACE_UPTIME_HRS",
        instance=3,
        description="JACE uptime since last restart",
        properties={"units": "hours"},
        presentValue=720.0,
    )

    # --- MS/TP Trunk Status ---
    binary_value(
        name="MSTP_TRUNK_STS",
        instance=10,
        description="MS/TP trunk communication status",
        presentValue=True,  # True = healthy
    )
    analog_value(
        name="MSTP_DEVICE_COUNT",
        instance=11,
        description="Number of devices on MS/TP trunk",
        presentValue=7.0,
    )
    analog_value(
        name="MSTP_ERROR_RATE",
        instance=12,
        description="MS/TP communication error rate",
        properties={"units": "percent"},
        presentValue=0.1,
    )

    # --- Global Scheduling ---
    modes = make_state_text(["Unoccupied", "Occupied", "Standby", "Override"])
    multistate_value(
        name="BLDG_OCC_MODE",
        instance=20,
        description="Building occupancy mode (from schedule)",
        presentValue=2,  # Occupied
        properties={"stateText": modes},
    )

    # --- Outdoor Conditions (shared sensors) ---
    analog_input(
        name="OAT",
        instance=30,
        description="Outdoor air temperature",
        properties={"units": "degreesFahrenheit"},
        presentValue=85.0,
    )
    analog_input(
        name="OA_RH",
        instance=31,
        description="Outdoor air relative humidity",
        properties={"units": "percentRelativeHumidity"},
        presentValue=50.0,
    )

    # --- Alarm Summary ---
    analog_value(
        name="ACTIVE_ALARM_COUNT",
        instance=40,
        description="Number of active alarms",
        presentValue=0.0,
    )

    return binary_value(
        name="JACE_COMM_FAIL_ALM",
        instance=41,
        description="Any field device communication failure",
        presentValue=False,
    )
