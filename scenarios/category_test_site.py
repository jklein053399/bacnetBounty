"""
Category Test Site — 1 AAON RTU + 2 ALC VAVs on Loopback

Uses device models with AV/BV for commands (no AO/BO — BAC0 rejects writes):
  192.168.100.2  AAON_RTU_1   Device 100001  (AAON VCCX-IP, 37 points)
  192.168.100.3  ALC_VAV_1    Device 200001  (ALC VAV Electric RH, ~37 points)
  192.168.100.4  ALC_VAV_2    Device 200002  (ALC VAV Electric RH, ~37 points)
  192.168.100.5  Reserved for Workbench

Setup (admin PowerShell — paste directly):
    foreach ($i in 2..5) { netsh interface ipv4 add address "Ethernet 11" "192.168.100.$i" 255.255.255.0 }

Run:
    cd tools/simulator
    py scenarios/category_test_site.py
"""
import asyncio
import sys
import os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from devices.aaon_rtu import create_aaon_rtu_points
from devices.alc_vav_electric_rh import create_alc_vav_points

# --- Device layout ---
SUBNET = 24
PORT = 47808

DEVICES = [
    {"name": "AAON_RTU_1", "id": 100001, "ip": "192.168.100.2", "type": "rtu"},
    {"name": "ALC_VAV_1",  "id": 200001, "ip": "192.168.100.3", "type": "vav"},
    {"name": "ALC_VAV_2",  "id": 200002, "ip": "192.168.100.4", "type": "vav"},
]


async def start_device(cfg, point_creator):
    """Start a BACnet device on its own loopback IP."""
    import BAC0
    from BAC0.core.devices.local.factory import ObjectFactory

    print(f"  Starting {cfg['name']} (Device {cfg['id']}) on {cfg['ip']}...")
    dev = BAC0.lite(
        ip=f"{cfg['ip']}/{SUBNET}",
        deviceId=cfg["id"],
        localObjName=cfg["name"],
        port=PORT,
    )

    ObjectFactory.clear_objects()
    obj = point_creator()
    obj.add_objects_to_application(dev)
    return dev


async def run_scenario():
    import BAC0
    BAC0.log_level("error")

    print("=" * 64)
    print("  Category Test Site — 1 AAON RTU + 2 ALC VAVs")
    print("=" * 64)
    print()

    devices = []

    try:
        # --- AAON RTU ---
        rtu = await start_device(DEVICES[0], create_aaon_rtu_points)
        devices.append(rtu)
        print(f"    RTU online — {rtu.localIPAddr}")

        # --- ALC VAV 1 ---
        vav1 = await start_device(DEVICES[1], create_alc_vav_points)
        devices.append(vav1)
        print(f"    VAV-1 online — {vav1.localIPAddr}")

        # --- ALC VAV 2 ---
        vav2 = await start_device(DEVICES[2], create_alc_vav_points)
        devices.append(vav2)
        print(f"    VAV-2 online — {vav2.localIPAddr}")

        # --- Summary ---
        print()
        print("All 3 devices online:")
        for cfg in DEVICES:
            print(f"  {cfg['ip']}:{PORT}  Device {cfg['id']:6d}  {cfg['name']}")
        print(f"  192.168.100.5  (reserved for Workbench)")
        print()
        print("Discover from Workbench: Drivers > BacnetNetwork > Discover")
        print("Press Ctrl+C to stop.")
        print("-" * 64)

        # Keep alive
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for dev in reversed(devices):
            try:
                dev.disconnect()
            except Exception:
                pass
        print("All devices stopped.")


def main():
    asyncio.run(run_scenario())


if __name__ == "__main__":
    main()
