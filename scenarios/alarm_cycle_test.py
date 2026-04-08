#!/usr/bin/env python3
"""Scenario: Alarm range cycling test.

Launches multi-vendor BACnet devices and ramps key point values through
alarm/normal ranges to validate the full alarm lifecycle:
  NORMAL -> TO_OFFNORMAL (high) -> TO_NORMAL -> TO_OFFNORMAL (low) -> TO_NORMAL

The cycle uses known setpoints and offsets from the device profiles to
compute exact trigger thresholds, then pushes values past them.

Usage:
    py scenarios/alarm_cycle_test.py
    py scenarios/alarm_cycle_test.py --cycle-time 60
    py scenarios/alarm_cycle_test.py --cycles 3

Devices: Same 4 as alarm_test_multi_vendor.py
Cycle targets per device:
    JB_UV_1:     ZN_T (SP=70/74, offset=10 -> high=84, low=60)
    ALC_VAV:     ZN-T (SP=70/74, offset=10 -> high=84, low=60)
    Distech_VAV: ZN_T (SP=70/74, offset=10 -> high=84, low=60)
    AAON_RTU_1:  Space_Temperature (SP varies)
"""

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from devices.aaon_vccx_ip_full import create_aaon_vccx_ip_full_points
from devices.distech_ecb_vav import create_distech_vav_points
from devices.alc_vav_electric_rh import create_alc_vav_points
from devices.jb_unit_vent import create_jb_unit_vent_points

BACNET_PORT = 47808
BASE_IP = "192.168.100"

DEVICES = [
    {"name": "AAON_RTU_1",  "device_id": 100001, "ip_suffix": 1, "create_fn": create_aaon_vccx_ip_full_points},
    {"name": "Distech_VAV", "device_id": 100002, "ip_suffix": 2, "create_fn": create_distech_vav_points},
    {"name": "ALC_VAV",     "device_id": 100003, "ip_suffix": 3, "create_fn": create_alc_vav_points},
    {"name": "JB_UV_1",     "device_id": 100004, "ip_suffix": 4, "create_fn": create_jb_unit_vent_points},
]

# Points to cycle per device, with their normal values and alarm thresholds.
# high_alarm = cooling_sp + offset, low_alarm = heating_sp - offset
# Values are pushed 2 degrees PAST the threshold to ensure trigger.
CYCLE_TARGETS = {
    "JB_UV_1": {
        "point": "ZN_T",
        "normal": 72.0,
        "high_trip": 86.0,    # EFFCLG_SP(74) + offset(10) + 2
        "low_trip": 58.0,     # EFFHTG_SP(70) - offset(10) - 2
    },
    "ALC_VAV": {
        "point": "ZN-T",
        "normal": 72.0,
        "high_trip": 86.0,
        "low_trip": 58.0,
    },
    "Distech_VAV": {
        "point": "ZN_T",
        "normal": 72.0,
        "high_trip": 86.0,
        "low_trip": 58.0,
    },
    "AAON_RTU_1": {
        "point": "Space_Temperature",
        "normal": 72.0,
        "high_trip": 86.0,
        "low_trip": 58.0,
    },
}


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
        _factory = ObjectFactory.__new__(ObjectFactory)
        _factory.add_objects_to_application(bacnet)

    print(f"  {name} online")
    return bacnet


def set_point_value(bacnet, point_name, value):
    """Set a point's presentValue on a running BAC0 device."""
    for obj in bacnet.this_application.objectIdentifier:
        obj_ref = bacnet.this_application.get_object_id(obj)
        if obj_ref and hasattr(obj_ref, "objectName"):
            if obj_ref.objectName == point_name:
                obj_ref.presentValue = value
                return True
    return False


async def run_cycle(instances, device_map, cycle_num, hold_secs):
    """Run one alarm cycle: normal -> high alarm -> normal -> low alarm -> normal."""
    print(f"\n{'='*60}")
    print(f"  CYCLE {cycle_num}")
    print(f"{'='*60}")

    # Phase 1: Confirm normal
    print(f"\n  Phase 1: NORMAL (hold {hold_secs}s)")
    for name, bacnet in device_map.items():
        target = CYCLE_TARGETS.get(name)
        if not target:
            continue
        set_point_value(bacnet, target["point"], target["normal"])
        print(f"    {name}/{target['point']} = {target['normal']}")
    await asyncio.sleep(hold_secs)

    # Phase 2: Ramp HIGH (above high limit)
    print(f"\n  Phase 2: HIGH ALARM (hold {hold_secs}s)")
    for name, bacnet in device_map.items():
        target = CYCLE_TARGETS.get(name)
        if not target:
            continue
        set_point_value(bacnet, target["point"], target["high_trip"])
        print(f"    {name}/{target['point']} = {target['high_trip']}  (above high limit)")
    await asyncio.sleep(hold_secs)

    # Phase 3: Return to normal
    print(f"\n  Phase 3: RETURN TO NORMAL (hold {hold_secs}s)")
    for name, bacnet in device_map.items():
        target = CYCLE_TARGETS.get(name)
        if not target:
            continue
        set_point_value(bacnet, target["point"], target["normal"])
        print(f"    {name}/{target['point']} = {target['normal']}")
    await asyncio.sleep(hold_secs)

    # Phase 4: Ramp LOW (below low limit)
    print(f"\n  Phase 4: LOW ALARM (hold {hold_secs}s)")
    for name, bacnet in device_map.items():
        target = CYCLE_TARGETS.get(name)
        if not target:
            continue
        set_point_value(bacnet, target["point"], target["low_trip"])
        print(f"    {name}/{target['point']} = {target['low_trip']}  (below low limit)")
    await asyncio.sleep(hold_secs)

    # Phase 5: Return to normal
    print(f"\n  Phase 5: RETURN TO NORMAL (hold {hold_secs}s)")
    for name, bacnet in device_map.items():
        target = CYCLE_TARGETS.get(name)
        if not target:
            continue
        set_point_value(bacnet, target["point"], target["normal"])
        print(f"    {name}/{target['point']} = {target['normal']}")
    await asyncio.sleep(hold_secs)

    print(f"\n  Cycle {cycle_num} complete.")


async def run_scenario(base_ip, cycle_time, num_cycles):
    """Launch devices and run alarm cycles."""
    hold_secs = cycle_time // 5  # 5 phases per cycle

    print(f"\nAlarm Range Cycling Test — BACnet/IP Simulator")
    print(f"{'='*55}")
    print(f"  Cycles: {num_cycles}  |  Cycle time: {cycle_time}s  |  Phase hold: {hold_secs}s")
    print()
    for d in DEVICES:
        ip = f"{base_ip}.{d['ip_suffix']}"
        target = CYCLE_TARGETS.get(d["name"], {})
        point = target.get("point", "—")
        print(f"  {d['name']:15s} Device {d['device_id']} on {ip}  cycling: {point}")
    print()

    # Start all devices
    instances = []
    device_map = {}
    for d in DEVICES:
        ip = f"{base_ip}.{d['ip_suffix']}"
        bacnet = await start_device(d["device_id"], d["name"], ip, d["create_fn"])
        instances.append(bacnet)
        device_map[d["name"]] = bacnet

    print(f"\nAll {len(DEVICES)} devices online. Starting cycles...\n")

    try:
        for cycle in range(1, num_cycles + 1):
            await run_cycle(instances, device_map, cycle, hold_secs)

        print(f"\n{'='*60}")
        print(f"  ALL {num_cycles} CYCLES COMPLETE")
        print(f"{'='*60}")
        print(f"\nDevices still running. Press Ctrl+C to stop.")

        while True:
            await asyncio.sleep(1)

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutting down...")
        for bacnet in instances:
            bacnet.disconnect()
        print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Alarm range cycling test")
    parser.add_argument("--base-ip", default=BASE_IP,
                        help=f"Base IP for loopback adapter (default: {BASE_IP})")
    parser.add_argument("--cycle-time", type=int, default=300,
                        help="Total time per cycle in seconds (default: 300 = 5 min)")
    parser.add_argument("--cycles", type=int, default=3,
                        help="Number of cycles to run (default: 3)")
    args = parser.parse_args()

    asyncio.run(run_scenario(args.base_ip, args.cycle_time, args.cycles))


if __name__ == "__main__":
    main()
