"""
Small Office Scenario — Realistic BACnet Topology

Network:
  Building Ethernet (BACnet/IP)
  └── JACE 8000 (Device 1001, port 47808) — Supervisor + trunk router
      └── MS/TP Trunk (simulated as separate BACnet/IP devices)
          ├── MAC 1:  JCI FEC-2611 VAV-1 (Device 2001, port 47809)
          ├── MAC 2:  JCI FEC-2611 VAV-2 (Device 2002, port 47810)
          ├── MAC 3:  JCI FEC-2611 VAV-3 (Device 2003, port 47811)
          ├── MAC 4:  JCI FEC-2611 VAV-4 (Device 2004, port 47812)
          ├── MAC 5:  JCI FEC-2611 VAV-5 (Device 2005, port 47813)
          ├── MAC 10: AAON VCCX-IP RTU  (Device 3001, port 47814)
          └── MAC 20: JCI FEC-2621 Misc (Device 4001, port 47815)

Each controller is a separate BACnet device with its own instance ID,
just like a real building. Yabe or Niagara will discover 8 devices.

Run: python run_simulator.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from devices.jace8000 import create_jace_points
from devices.jci_fec_vav import create_fec_vav_points
from devices.aaon_rtu import create_aaon_rtu_points
from devices.jci_fec_misc import create_misc_controller_points
from simulation.zone_model import ZoneModel
from simulation.ahu_model import AhuModel


# VAV zone configurations: (zone_name, design_cfm, internal_load_btu)
VAV_ZONES = [
    ("Interior-Office-1", 600,  2500),
    ("Interior-Office-2", 600,  2000),
    ("Perimeter-South",   900,  4000),
    ("Perimeter-North",   800,  1500),
    ("Conference-Room",   1200, 6000),
]

# Device instance IDs and ports
JACE_DEVICE_ID = 1001
JACE_PORT = 47808
VAV_BASE_DEVICE_ID = 2001
VAV_BASE_PORT = 47809
RTU_DEVICE_ID = 3001
RTU_PORT = 47814
MISC_DEVICE_ID = 4001
MISC_PORT = 47815

SIM_INTERVAL = 2.0  # seconds


async def start_device(device_id, name, port, point_creator, *args):
    """Start a single BACnet device and register its points."""
    import BAC0
    bacnet = await BAC0.lite(deviceId=device_id, localObjName=name, port=port).__aenter__()
    obj = point_creator(*args)
    obj.add_objects_to_application(bacnet)
    return bacnet


async def run_scenario():
    """Run the small office scenario with realistic multi-device topology."""
    import BAC0
    BAC0.log_level("error")

    print("=" * 60)
    print("  Small Office BACnet Simulator")
    print("  Realistic Multi-Device Topology")
    print("=" * 60)
    print()

    devices = []

    try:
        # --- Start JACE 8000 (Supervisor) ---
        print(f"Starting JACE 8000 (Device {JACE_DEVICE_ID}, port {JACE_PORT})...")
        jace = await start_device(JACE_DEVICE_ID, "JACE-8000", JACE_PORT, create_jace_points)
        devices.append(jace)
        print(f"  JACE online at {jace.localIPAddr}")

        # --- Start VAV Controllers ---
        vav_devices = []
        for i, (zone_name, cfm, load) in enumerate(VAV_ZONES):
            dev_id = VAV_BASE_DEVICE_ID + i
            port = VAV_BASE_PORT + i
            name = f"FEC-2611-VAV{i+1}"
            print(f"Starting {name} ({zone_name}, Device {dev_id}, port {port})...")
            dev = await start_device(dev_id, name, port, create_fec_vav_points, zone_name, cfm)
            vav_devices.append(dev)
            devices.append(dev)

        # --- Start AAON RTU ---
        print(f"Starting AAON VCCX-IP RTU (Device {RTU_DEVICE_ID}, port {RTU_PORT})...")
        rtu = await start_device(RTU_DEVICE_ID, "AAON-RTU-1", RTU_PORT, create_aaon_rtu_points)
        devices.append(rtu)

        # --- Start Misc Controller ---
        print(f"Starting JCI FEC-2621 Misc (Device {MISC_DEVICE_ID}, port {MISC_PORT})...")
        misc = await start_device(MISC_DEVICE_ID, "FEC-2621-MISC", MISC_PORT, create_misc_controller_points)
        devices.append(misc)

        print()
        print(f"All {len(devices)} devices online!")
        print(f"  JACE 8000:      port {JACE_PORT}")
        for i in range(len(VAV_ZONES)):
            print(f"  FEC-2611 VAV-{i+1}: port {VAV_BASE_PORT + i}")
        print(f"  AAON RTU:       port {RTU_PORT}")
        print(f"  FEC-2621 Misc:  port {MISC_PORT}")
        print()
        print("Open Yabe -> Add Device -> scan each port, or use Who-Is broadcast.")
        print("Press Ctrl+C to stop.")
        print("-" * 60)

        # --- Initialize simulation models ---
        zones = []
        for zone_name, cfm, load in VAV_ZONES:
            z = ZoneModel(zone_name, area_sqft=250, design_cfm=cfm)
            z.internal_load = load
            z.outdoor_temp = 85.0
            zones.append(z)

        ahu = AhuModel()
        ahu.outdoor_air_temp = 85.0

        # --- Simulation loop ---
        tick = 0
        while True:
            await asyncio.sleep(SIM_INTERVAL)
            tick += 1

            # Propagate OAT from JACE to RTU
            oat = jace["OAT"].presentValue
            rtu["OA-T"].presentValue = oat
            ahu.outdoor_air_temp = oat

            # --- RTU simulation ---
            fan_on = rtu["SF-CMD"].presentValue
            fan_spd = rtu["SF-SPD"].presentValue or 0
            oa_dmpr = rtu["OA-DPR"].presentValue or 15
            htg_out = rtu["HTG-O"].presentValue or 0
            # Simulate cooling as CHW equivalent for the model
            clg = 50.0 if rtu["COMP1-STS"].presentValue else 0
            if rtu["COMP2-STS"].presentValue:
                clg = 100.0

            ahu.step(SIM_INTERVAL, oa_dmpr, clg, htg_out, fan_spd, fan_on)
            rtu["SA-T"].presentValue = round(ahu.get_sensed_sat(), 1)
            rtu["MA-T"].presentValue = round(ahu.get_sensed_mat(), 1)
            rtu["SA-SP"].presentValue = round(ahu.get_sensed_sp(), 2)
            rtu["SF-STS"].presentValue = fan_on and fan_spd > 5

            # --- VAV zone simulation ---
            for i, (zone, vav_dev) in enumerate(zip(zones, vav_devices)):
                dmpr_cmd = vav_dev["DPR-O"].presentValue or 0
                htg_vlv = vav_dev["HTG-O"].presentValue or 0

                zone.supply_air_temp = ahu.supply_air_temp
                airflow = zone.get_airflow(dmpr_cmd)
                zone.step(SIM_INTERVAL, airflow, htg_vlv)

                vav_dev["ZN-T"].presentValue = round(zone.get_sensed_temp(), 1)
                vav_dev["DA-CFM"].presentValue = round(airflow, 0)
                vav_dev["DA-T"].presentValue = round(zone.get_discharge_temp(htg_vlv), 1)

            # --- Misc controller simulation ---
            # EFs: status follows command
            for ef in [1, 2]:
                cmd = misc[f"EF{ef}-CMD"].presentValue
                misc[f"EF{ef}-STS"].presentValue = cmd
                misc[f"EF{ef}-AMPS"].presentValue = 3.2 if cmd else 0.0

            # CUHs: simple on/off based on zone temp vs setpoint
            for cuh in [1, 2]:
                zn_t = misc[f"CUH{cuh}-ZN-T"].presentValue
                sp = misc[f"CUH{cuh}-SP"].presentValue
                cmd = misc[f"CUH{cuh}-CMD"].presentValue
                misc[f"CUH{cuh}-STS"].presentValue = cmd
                if cmd and zn_t < sp:
                    misc[f"CUH{cuh}-VLV"].presentValue = min(100, (sp - zn_t) * 20)
                else:
                    misc[f"CUH{cuh}-VLV"].presentValue = 0.0

            # Building pressure: slight random variation
            import random
            misc["BLDG-SP"].presentValue = round(0.05 + random.gauss(0, 0.01), 3)

            # --- Periodic status ---
            if tick % 15 == 0:
                print(f"[t={tick * SIM_INTERVAL:.0f}s] "
                      f"OAT={oat:.0f}F  RTU: SAT={ahu.supply_air_temp:.1f}F  "
                      f"Fan={'ON' if fan_on else 'OFF'}@{fan_spd:.0f}%")
                for i, zone in enumerate(zones):
                    dmpr = vav_devices[i]["DPR-O"].presentValue or 0
                    htg = vav_devices[i]["HTG-O"].presentValue or 0
                    print(f"  VAV-{i+1} {zone.name:20s}  "
                          f"ZnT={zone.zone_temp:.1f}F  Dmpr={dmpr:.0f}%  Htg={htg:.0f}%")
                bldg_sp = misc["BLDG-SP"].presentValue
                print(f"  BLDG-SP={bldg_sp:.3f} in.WG  "
                      f"EF1={'ON' if misc['EF1-STS'].presentValue else 'OFF'}  "
                      f"EF2={'ON' if misc['EF2-STS'].presentValue else 'OFF'}")
                print()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean disconnect all devices
        for dev in reversed(devices):
            try:
                await dev.__aexit__(None, None, None)
            except Exception:
                pass
        print("All devices stopped.")


def main():
    asyncio.run(run_scenario())


if __name__ == "__main__":
    main()
