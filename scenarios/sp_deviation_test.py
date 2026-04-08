#!/usr/bin/env python3
"""Scenario: Small building simulation for commissioning testing.

2 RTUs + 8 VAVs on loopback adapter. Realistic point sets for testing
MetroAutoCommissioner (unified program) and all individual generators.

Usage:
    py scenarios/sp_deviation_test.py
    py scenarios/sp_deviation_test.py --base-ip 192.168.100

Devices (each on its own loopback IP, port 47808):
    RTU_1  — AAON-style RTU (20 pts: temps, SPs, outputs, alarms, occ)
    RTU_2  — AAON-style RTU (20 pts: same structure, different values)
    VAV_1  — ALC hyphen style (8 pts: ZN-T, DA-T, SPs, flow, damper, heating)
    VAV_2  — ALC underscore style (8 pts)
    VAV_3  — AMBIGUOUS: 2 zone temp candidates (ZN_T + Space_Temperature)
    VAV_4  — AMBIGUOUS: 2 heat SP + 2 cool SP candidates
    VAV_5  — Metro verbose naming (8 pts)
    VAV_6  — Verbose underscores (7 pts)
    VAV_7  — Short form naming (6 pts)
    VAV_8  — Room temp style + alarm point (8 pts)

Requires Ethernet 11 (KM-TEST Loopback) with IPs .1-.10 + .11 for Workbench.
"""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from BAC0.core.devices.local.factory import (
    ObjectFactory,
    analog_input,
    analog_value,
    binary_value,
    multistate_value,
    make_state_text,
)

BACNET_PORT = 47808
BASE_DEVICE_ID = 200001


# Each device definition: (name, device_id, points)
# Points are (factory_func, name, instance, value, units)
DEVICES = [
    # === 2 RTUs (AAON-style, spaces/hyphens — needs normalization) ===
    {
        "name": "RTU_1",
        "note": "AAON-style RTU — spaces and hyphens in point names",
        "points": [
            ("ai", "Space Temperature", 1, 72.1, "degreesFahrenheit"),
            ("ai", "Discharge Air Temp", 2, 55.3, "degreesFahrenheit"),
            ("ai", "Return Air Temp", 3, 72.0, "degreesFahrenheit"),
            ("ai", "Mixed Air Temp", 4, 62.5, "degreesFahrenheit"),
            ("ai", "Outside Air Temp", 5, 48.2, "degreesFahrenheit"),
            ("ai", "Outside Air Humidity", 6, 45.0, "percentRelativeHumidity"),
            ("av", "EFFHTG-SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFFCLG-SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "HTG OCC-SP", 12, 70.0, "degreesFahrenheit"),
            ("av", "CLG OCC-SP", 13, 74.0, "degreesFahrenheit"),
            ("av", "Supply Fan CMD", 20, 75.0, "percent"),
            ("av", "Cooling Stage", 21, 1.0, "noUnits"),
            ("av", "Heating Stage", 22, 0.0, "noUnits"),
            ("av", "OA Damper", 23, 20.0, "percent"),
            ("bv", "SF-S", 30, "active"),
            ("bv", "CLG-EN", 31, "active"),
            ("bv", "HTG-EN", 32, "active"),
            ("bv", "Low Temp Alarm", 33, "inactive"),
            ("bv", "Freeze Stat", 34, "inactive"),
            ("mv", "OCC CMD", 40, 1),
        ],
    },
    {
        "name": "RTU_2",
        "note": "AAON-style RTU — spaces and hyphens, different values",
        "points": [
            ("ai", "Space Temperature", 1, 73.5, "degreesFahrenheit"),
            ("ai", "Discharge Air Temp", 2, 56.1, "degreesFahrenheit"),
            ("ai", "Return Air Temp", 3, 73.2, "degreesFahrenheit"),
            ("ai", "Mixed Air Temp", 4, 63.0, "degreesFahrenheit"),
            ("ai", "Outside Air Temp", 5, 48.2, "degreesFahrenheit"),
            ("ai", "Outside Air Humidity", 6, 45.0, "percentRelativeHumidity"),
            ("av", "EFFHTG-SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFFCLG-SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "HTG OCC-SP", 12, 70.0, "degreesFahrenheit"),
            ("av", "CLG OCC-SP", 13, 74.0, "degreesFahrenheit"),
            ("av", "Supply Fan CMD", 20, 80.0, "percent"),
            ("av", "Cooling Stage", 21, 2.0, "noUnits"),
            ("av", "Heating Stage", 22, 0.0, "noUnits"),
            ("av", "OA Damper", 23, 25.0, "percent"),
            ("bv", "SF-S", 30, "active"),
            ("bv", "CLG-EN", 31, "active"),
            ("bv", "HTG-EN", 32, "inactive"),
            ("bv", "Low Temp Alarm", 33, "inactive"),
            ("bv", "Dirty Filter", 34, "inactive"),
            ("mv", "OCC CMD", 40, 1),
        ],
    },
    # === 8 VAVs (varied naming with spaces/hyphens — needs normalization) ===
    {
        "name": "VAV_1",
        "note": "ALC hyphen style — needs normalize",
        "points": [
            ("ai", "ZN-T", 1, 71.5, "degreesFahrenheit"),
            ("ai", "DA-T", 2, 58.0, "degreesFahrenheit"),
            ("av", "EFFHTG-SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFFCLG-SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "SA-F", 20, 450.0, "cubicFeetPerMinute"),
            ("av", "DPR-O", 21, 55.0, "percent"),
            ("av", "HTG-O", 22, 0.0, "percent"),
            ("bv", "HTG-EN", 30, "active"),
        ],
    },
    {
        "name": "VAV_2",
        "note": "ALC with spaces — needs normalize",
        "points": [
            ("ai", "ZN T", 1, 72.0, "degreesFahrenheit"),
            ("ai", "DA T", 2, 57.5, "degreesFahrenheit"),
            ("av", "EFF HTG SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFF CLG SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "SA Flow", 20, 380.0, "cubicFeetPerMinute"),
            ("av", "Damper Out", 21, 48.0, "percent"),
            ("av", "HTG Out", 22, 12.0, "percent"),
            ("bv", "HTG Enable", 30, "active"),
        ],
    },
    {
        "name": "VAV_3",
        "note": "AMBIGUOUS — 2 zone temp candidates + hyphens",
        "points": [
            ("ai", "ZN-T", 1, 71.0, "degreesFahrenheit"),
            ("av", "Space Temperature", 2, 71.2, "degreesFahrenheit"),
            ("ai", "DA-T", 3, 59.0, "degreesFahrenheit"),
            ("av", "EFFHTG-SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFFCLG-SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "SA Flow", 20, 520.0, "cubicFeetPerMinute"),
            ("av", "Damper Output", 21, 62.0, "percent"),
            ("av", "HTG Output", 22, 5.0, "percent"),
        ],
    },
    {
        "name": "VAV_4",
        "note": "AMBIGUOUS — 2 eff heat + 2 eff cool, hyphens and spaces",
        "points": [
            ("ai", "ZN-T", 1, 72.5, "degreesFahrenheit"),
            ("ai", "DA-T", 2, 56.8, "degreesFahrenheit"),
            ("av", "EFFHTG-SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFF HTG SP", 11, 69.5, "degreesFahrenheit"),
            ("av", "EFFCLG-SP", 12, 75.0, "degreesFahrenheit"),
            ("av", "EFF CLG SP", 13, 74.5, "degreesFahrenheit"),
            ("av", "SA-F", 20, 400.0, "cubicFeetPerMinute"),
            ("av", "DPR-O", 21, 50.0, "percent"),
        ],
    },
    {
        "name": "VAV_5",
        "note": "Metro verbose with spaces",
        "points": [
            ("ai", "Space Temperature", 1, 73.0, "degreesFahrenheit"),
            ("ai", "Discharge Air Temp", 2, 55.8, "degreesFahrenheit"),
            ("av", "EFFHTG SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFFCLG SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "Supply Air Flow", 20, 600.0, "cubicFeetPerMinute"),
            ("av", "Damper Position", 21, 70.0, "percent"),
            ("av", "Heating Output", 22, 0.0, "percent"),
            ("bv", "HTG Enable", 30, "active"),
        ],
    },
    {
        "name": "VAV_6",
        "note": "Verbose with spaces everywhere",
        "points": [
            ("ai", "Zone Temperature", 1, 71.8, "degreesFahrenheit"),
            ("ai", "Discharge Air Temperature", 2, 57.2, "degreesFahrenheit"),
            ("av", "Eff Heat SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "Eff Cool SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "Supply Air Flow", 20, 350.0, "cubicFeetPerMinute"),
            ("av", "Damper Position", 21, 42.0, "percent"),
            ("av", "Heating Output", 22, 8.0, "percent"),
        ],
    },
    {
        "name": "VAV_7",
        "note": "Short form with hyphens",
        "points": [
            ("av", "ZN-T", 1, 70.5, "degreesFahrenheit"),
            ("ai", "DA-T", 2, 58.5, "degreesFahrenheit"),
            ("av", "EFFHTG", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFFCLG", 11, 74.0, "degreesFahrenheit"),
            ("av", "SA-F", 20, 280.0, "cubicFeetPerMinute"),
            ("av", "DPR", 21, 35.0, "percent"),
        ],
    },
    {
        "name": "VAV_8",
        "note": "Room temp style with spaces + alarm point",
        "points": [
            ("ai", "Room Temp", 1, 72.2, "degreesFahrenheit"),
            ("ai", "Discharge Air Temp", 2, 56.0, "degreesFahrenheit"),
            ("av", "EFF HTG SP", 10, 70.0, "degreesFahrenheit"),
            ("av", "EFF CLG SP", 11, 74.0, "degreesFahrenheit"),
            ("av", "Supply Air Flow", 20, 410.0, "cubicFeetPerMinute"),
            ("av", "Damper Output", 21, 52.0, "percent"),
            ("av", "Heating Output", 22, 15.0, "percent"),
            ("bv", "Low Flow Alarm", 30, "inactive"),
        ],
    },
]


def create_device_points(device_def):
    """Create BAC0 points for a single device definition."""
    for pt_type, name, instance, value, units in device_def["points"]:
        factory = analog_input if pt_type == "ai" else analog_value
        factory(
            name=name,
            instance=instance,
            description=name,
            properties={"units": units},
            presentValue=value,
        )


async def start_device(device_def, ip, port=BACNET_PORT):
    """Start a single BAC0 device."""
    import BAC0

    idx = DEVICES.index(device_def)
    device_id = BASE_DEVICE_ID + idx
    name = device_def["name"]

    print(f"  Starting {name} (ID {device_id}) on {ip}:{port} — {device_def['note']}")
    bacnet = BAC0.lite(ip=ip, port=port, deviceId=device_id, localObjName=name)

    occ_states = make_state_text(["Occupied", "Unoccupied", "Standby"])

    ObjectFactory.clear_objects()
    last_obj = None
    for pt in device_def["points"]:
        pt_type, pt_name, instance, value = pt[0], pt[1], pt[2], pt[3]
        units = pt[4] if len(pt) > 4 else "noUnits"

        if pt_type == "ai":
            last_obj = analog_input(name=pt_name, instance=instance, description=pt_name,
                properties={"units": units}, presentValue=value)
        elif pt_type == "av":
            last_obj = analog_value(name=pt_name, instance=instance, description=pt_name,
                properties={"units": units}, presentValue=value)
        elif pt_type == "bv":
            last_obj = binary_value(name=pt_name, instance=instance, description=pt_name,
                presentValue=value)
        elif pt_type == "mv":
            last_obj = multistate_value(name=pt_name, instance=instance, description=pt_name,
                presentValue=value, stateText=occ_states)

    if last_obj is not None:
        last_obj.add_objects_to_application(bacnet)

    pt_count = len(device_def["points"])
    print(f"    {name} online — {pt_count} points")
    return bacnet


async def run_scenario(base_ip):
    """Launch all 10 VAV devices."""
    print(f"\nSmall Building Sim — 2 RTUs + 8 VAVs")
    print(f"=" * 55)
    print(f"  Base IP: {base_ip}.1 through {base_ip}.10")
    print(f"  Port: {BACNET_PORT}")
    print()

    # Expected results summary
    print("Expected MetroAutoCommissioner results:")
    print("  RTU_1, RTU_2:          Full commissioning (history, alarms, PxView, SP deviation)")
    print("  VAV_1, VAV_2:          SP deviation match (ALC eff style)")
    print("  VAV_3:                 AMBIGUOUS zone temp (HMI flag)")
    print("  VAV_4:                 AMBIGUOUS setpoints (HMI flag)")
    print("  VAV_5 through VAV_8:   SP deviation match (various naming)")
    print(f"  Total: 2 RTUs + 8 VAVs = 10 devices, ~110 points")
    print()

    devices = []
    for i, device_def in enumerate(DEVICES):
        ip = f"{base_ip}.{i + 1}"
        dev = await start_device(device_def, ip)
        devices.append(dev)

    print(f"\nAll 10 VAVs online. Discoverable from Workbench on {base_ip}.1-10:{BACNET_PORT}")
    print(f"Press Ctrl+C to stop.\n")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutting down...")
        for dev in devices:
            dev.disconnect()
        print("Done.")


def main():
    parser = argparse.ArgumentParser(description="SP Deviation test — 10 VAV devices")
    parser.add_argument(
        "--base-ip", default="192.168.100",
        help="First 3 octets of loopback IPs (default: 192.168.100)",
    )
    args = parser.parse_args()
    asyncio.run(run_scenario(args.base_ip))


if __name__ == "__main__":
    main()
