#!/usr/bin/env python3
"""Scenario: Two AAON VCCX-IP RTUs on loopback adapter.

Launches two full 535-point BACnet/IP devices on the loopback adapter
IPs for Workbench discovery and integration testing.

Usage:
    py scenarios/aaon_rtu_pair.py
    py scenarios/aaon_rtu_pair.py --ip1 192.168.100.1 --ip2 192.168.100.2

Devices:
    RTU_1: Device ID 100001 on 192.168.100.1:47808
    RTU_2: Device ID 100002 on 192.168.100.2:47808

Both devices expose the full AAON VCCX-IP PIC point list (286 AI + 99 AV + 150 BI).
"""

import argparse
import asyncio
import os
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from devices.aaon_vccx_ip_full import create_aaon_vccx_ip_full_points, get_point_count


# Default loopback adapter IPs
DEFAULT_IP1 = "192.168.100.1"
DEFAULT_IP2 = "192.168.100.2"
BACNET_PORT = 47808

# Device IDs (unique per device on the network)
RTU1_DEVICE_ID = 100001
RTU2_DEVICE_ID = 100002


async def start_rtu(device_id: int, name: str, ip: str, port: int = BACNET_PORT):
    """Start a single AAON VCCX-IP BACnet device."""
    import BAC0

    from BAC0.core.devices.local.factory import ObjectFactory

    print(f"  Starting {name} (device {device_id}) on {ip}:{port}...")
    bacnet = BAC0.lite(ip=ip, port=port, deviceId=device_id, localObjName=name)

    ObjectFactory.clear_objects()
    obj = create_aaon_vccx_ip_full_points()
    obj.add_objects_to_application(bacnet)

    print(f"  {name} online — {get_point_count()} BACnet objects registered")
    return bacnet


async def run_scenario(ip1: str, ip2: str):
    """Launch both RTUs and keep them running."""
    print(f"\nAAON VCCX-IP RTU Pair — BACnet/IP Simulator")
    print(f"=" * 50)
    print(f"  RTU_1: {ip1}:{BACNET_PORT} (device {RTU1_DEVICE_ID})")
    print(f"  RTU_2: {ip2}:{BACNET_PORT} (device {RTU2_DEVICE_ID})")
    print(f"  Points per device: {get_point_count()}")
    print()

    rtu1 = await start_rtu(RTU1_DEVICE_ID, "AAON_RTU_1", ip1)
    rtu2 = await start_rtu(RTU2_DEVICE_ID, "AAON_RTU_2", ip2)

    print(f"\nBoth RTUs online. Discoverable from Workbench.")
    print(f"Press Ctrl+C to stop.\n")

    # Keep alive — devices respond to BACnet requests in background
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutting down...")
        rtu1.disconnect()
        rtu2.disconnect()
        print("Done.")


def main():
    parser = argparse.ArgumentParser(description="AAON VCCX-IP RTU pair simulator")
    parser.add_argument("--ip1", default=DEFAULT_IP1, help=f"RTU_1 IP (default: {DEFAULT_IP1})")
    parser.add_argument("--ip2", default=DEFAULT_IP2, help=f"RTU_2 IP (default: {DEFAULT_IP2})")
    args = parser.parse_args()

    asyncio.run(run_scenario(args.ip1, args.ip2))


if __name__ == "__main__":
    main()
