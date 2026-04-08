#!/usr/bin/env python3
"""Scenario: Multi-vendor demo site for team training.

Launches 8 BACnet/IP devices on the loopback adapter:
  - 2 AAON VCCX-IP RTUs (~38 pts each)
  - 4 Distech ECB VAVs (42 pts each)
  - 1 G36 Chiller Plant (53 pts)
  - 1 JB Unit Ventilator (~35 pts)

Total: ~330 BACnet objects across 8 devices, 3 vendors + G36.

Usage:
    py scenarios/demo_multi_vendor.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from devices.aaon_rtu import create_aaon_rtu_points
from devices.chiller_plant import create_all_plant_points
from devices.distech_ecb_vav import create_distech_vav_points
from devices.jb_unit_vent import create_jb_unit_vent_points

BACNET_PORT = 47808

# Device layout — all on 192.168.100.x loopback adapter
DEVICES = [
    {"name": "AAON_RTU_1",       "ip": "192.168.100.1",  "device_id": 100001, "type": "aaon_rtu"},
    {"name": "AAON_RTU_2",       "ip": "192.168.100.2",  "device_id": 100002, "type": "aaon_rtu"},
    {"name": "Distech_VAV_101",  "ip": "192.168.100.3",  "device_id": 200001, "type": "distech_vav"},
    {"name": "Distech_VAV_102",  "ip": "192.168.100.4",  "device_id": 200002, "type": "distech_vav"},
    {"name": "Distech_VAV_103",  "ip": "192.168.100.5",  "device_id": 200003, "type": "distech_vav"},
    {"name": "Distech_VAV_104",  "ip": "192.168.100.6",  "device_id": 200004, "type": "distech_vav"},
    {"name": "G36_Chiller_Plant","ip": "192.168.100.7",  "device_id": 300001, "type": "chiller"},
    {"name": "JB_Unit_Vent_1",   "ip": "192.168.100.8",  "device_id": 400001, "type": "jb_uv"},
]


def create_points_for_type(device_type):
    """Call the appropriate point factory for a device type."""
    if device_type == "aaon_rtu":
        return create_aaon_rtu_points()
    elif device_type == "distech_vav":
        return create_distech_vav_points()
    elif device_type == "chiller":
        return create_all_plant_points()
    elif device_type == "jb_uv":
        return create_jb_unit_vent_points()
    else:
        raise ValueError(f"Unknown device type: {device_type}")


async def start_device(dev):
    """Start a single BACnet device."""
    import BAC0
    from BAC0.core.devices.local.factory import ObjectFactory

    ip = f"{dev['ip']}/24"
    print(f"  Starting {dev['name']} (ID {dev['device_id']}) on {dev['ip']}...")

    bacnet = BAC0.lite(ip=ip, port=BACNET_PORT, deviceId=dev["device_id"],
                       localObjName=dev["name"])

    ObjectFactory.clear_objects()
    obj = create_points_for_type(dev["type"])
    obj.add_objects_to_application(bacnet)

    return bacnet


async def run_scenario():
    """Launch all devices and keep them running."""
    print(f"\nMulti-Vendor Demo Site — BACnet/IP Simulator")
    print(f"{'=' * 55}")
    print(f"  Devices: {len(DEVICES)}")
    print()
    for dev in DEVICES:
        print(f"  {dev['name']:25s}  {dev['ip']}:{BACNET_PORT}  (ID {dev['device_id']})")
    print()

    instances = []

    for dev in DEVICES:
        bacnet = await start_device(dev)
        instances.append(bacnet)

        print(f"    -> {dev['name']} online")

    print(f"\n{'=' * 55}")
    print(f"  All {len(DEVICES)} devices online")
    print(f"  Discoverable from Workbench on 192.168.100.x subnet")
    print(f"  Press Ctrl+C to stop.")
    print(f"{'=' * 55}\n")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutting down...")
        for inst in instances:
            try:
                inst.disconnect()
            except Exception:
                pass
        print("Done.")


def main():
    asyncio.run(run_scenario())


if __name__ == "__main__":
    main()
