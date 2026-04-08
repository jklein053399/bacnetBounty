#!/usr/bin/env python3
"""Scenario: Multi-vendor alarm extension testing.

Launches 4 BACnet/IP devices on the loopback adapter for testing
alarm extension generators against real vendor naming patterns.

Usage:
    py scenarios/alarm_test_multi_vendor.py
    py scenarios/alarm_test_multi_vendor.py --base-ip 192.168.100

Devices:
    AAON_RTU_1:  Device 100001 on .1 — AAON VCCX-IP verbose naming
    Distech_VAV: Device 100002 on .2 — Distech ECB CamelCase naming
    ALC_VAV:     Device 100003 on .3 — ALC hyphen naming (ZN-T, EFFHTG-SP)
    JB_UV_1:     Device 100004 on .4 — JB Unit Vent standard Metro naming

Expected alarm matching results:
    AAON_RTU_1:  ZN_T=Space_Temperature, HTG_SP=Mode_Heating_Setpoint (T4)
    Distech_VAV: ZN_T=ZN_T, HTG_SP=ActHeatSP (T1), CLG_SP=ActCoolSP (T1)
    ALC_VAV:     ZN_T=ZN-T, HTG_SP=EFFHTG-SP (T1), CLG_SP=EFFCLG-SP (T1)
    JB_UV_1:     ZN_T=ZN_T, HTG_SP=EFFHTG_SP (T1), CLG_SP=EFFCLG_SP (T1)
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from devices.aaon_vccx_ip_full import create_aaon_vccx_ip_full_points
from devices.distech_ecb_vav import create_distech_vav_points
from devices.alc_vav_electric_rh import create_alc_vav_points
from devices.jb_unit_vent import create_jb_unit_vent_points

BACNET_PORT = 47808
BASE_IP = "192.168.100"
# RESERVED: 192.168.100.250 — Workbench/local machine BACnet binding. Never assign to BAC0 devices.

DEVICES = [
    {"name": "AAON_RTU_1",  "device_id": 100001, "ip_suffix": 1, "create_fn": create_aaon_vccx_ip_full_points},
    {"name": "Distech_VAV", "device_id": 100002, "ip_suffix": 2, "create_fn": create_distech_vav_points},
    {"name": "ALC_VAV",     "device_id": 100003, "ip_suffix": 3, "create_fn": create_alc_vav_points},
    {"name": "JB_UV_1",     "device_id": 100004, "ip_suffix": 4, "create_fn": create_jb_unit_vent_points},
]


async def start_device(device_id, name, ip, create_fn):
    """Start a single BACnet device."""
    import BAC0
    from BAC0.core.devices.local.factory import ObjectFactory

    print(f"  Starting {name} (device {device_id}) on {ip}:{BACNET_PORT}...")
    bacnet = BAC0.lite(ip=ip, port=BACNET_PORT, deviceId=device_id, localObjName=name)

    ObjectFactory.clear_objects()
    last_obj = create_fn()
    if last_obj is not None:
        last_obj.add_objects_to_application(bacnet)
    else:
        # Fallback: use class-level objects dict directly
        _factory = ObjectFactory.__new__(ObjectFactory)
        _factory.add_objects_to_application(bacnet)

    print(f"  {name} online")
    return bacnet


async def run_scenario(base_ip):
    """Launch all 4 devices."""
    print(f"\nMulti-Vendor Alarm Test — BACnet/IP Simulator")
    print(f"=" * 55)
    for d in DEVICES:
        ip = f"{base_ip}.{d['ip_suffix']}"
        print(f"  {d['name']:15s} Device {d['device_id']} on {ip}:{BACNET_PORT}")
    print()

    instances = []
    for d in DEVICES:
        ip = f"{base_ip}.{d['ip_suffix']}"
        bacnet = await start_device(d["device_id"], d["name"], ip, d["create_fn"])
        instances.append(bacnet)

    print(f"\nAll {len(DEVICES)} devices online. Discoverable from Workbench.")
    print(f"Press Ctrl+C to stop.\n")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutting down...")
        for bacnet in instances:
            bacnet.disconnect()
        print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Multi-vendor alarm test simulator")
    parser.add_argument("--base-ip", default=BASE_IP,
                        help=f"Base IP for loopback adapter (default: {BASE_IP})")
    args = parser.parse_args()

    asyncio.run(run_scenario(args.base_ip))


if __name__ == "__main__":
    main()
