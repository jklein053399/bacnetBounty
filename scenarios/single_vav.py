"""
Single VAV Scenario — Minimal BACnet device for testing

One VAV reheat controller on the KM-TEST Loopback adapter (Ethernet 11).
Provides writable points for category mask testing and general Workbench exercises.

Setup (admin PowerShell):
    netsh interface ipv4 add address "Ethernet 11" 192.168.100.2 255.255.255.0

Run:
    cd tools/simulator
    py scenarios/single_vav.py
"""
import asyncio
import random
import sys
import os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from BAC0.core.devices.local.factory import (
    analog_input, analog_output, analog_value,
    binary_input, binary_value,
    multistate_value, make_state_text,
)
from simulation.zone_model import ZoneModel

# --- Config ---
DEVICE_ID = 5001
LOCAL_IP = "192.168.100.2"
SUBNET_MASK = 24
PORT = 47808

DESIGN_CFM = 800
SIM_INTERVAL = 2.0


def create_vav_points():
    """Single VAV-reheat controller point list. Mix of AI/AO/AV/BI/BV/MV."""
    # --- Analog Inputs (sensors) ---
    analog_input(name="ZN-T", instance=1, description="Zone temperature",
                 properties={"units": "degreesFahrenheit"}, presentValue=72.0)
    analog_input(name="DA-T", instance=2, description="Discharge air temperature",
                 properties={"units": "degreesFahrenheit"}, presentValue=72.0)
    analog_input(name="DA-CFM", instance=3, description="Discharge airflow",
                 properties={"units": "cubicFeetPerMinute"}, presentValue=DESIGN_CFM * 0.3)

    # --- Analog Outputs (commands — as AV to avoid BAC0 MRO issue) ---
    analog_value(name="DPR-O", instance=50, description="Damper position command",
                 properties={"units": "percent"}, presentValue=50.0)
    analog_value(name="HTG-O", instance=51, description="Reheat valve command",
                 properties={"units": "percent"}, presentValue=0.0)

    # --- Analog Values (setpoints) ---
    analog_value(name="OCC-CLG-SP", instance=1, description="Occupied cooling setpoint",
                 properties={"units": "degreesFahrenheit"}, presentValue=75.0)
    analog_value(name="OCC-HTG-SP", instance=2, description="Occupied heating setpoint",
                 properties={"units": "degreesFahrenheit"}, presentValue=70.0)
    analog_value(name="CFM-MAX", instance=3, description="Maximum airflow setpoint",
                 properties={"units": "cubicFeetPerMinute"}, presentValue=DESIGN_CFM)
    analog_value(name="CFM-MIN", instance=4, description="Minimum airflow setpoint",
                 properties={"units": "cubicFeetPerMinute"}, presentValue=DESIGN_CFM * 0.3)
    analog_value(name="CFM-SP", instance=5, description="Active airflow setpoint",
                 properties={"units": "cubicFeetPerMinute"}, presentValue=DESIGN_CFM * 0.3)
    analog_value(name="CLG-LOOP", instance=6, description="Cooling loop output",
                 properties={"units": "percent"}, presentValue=0.0)
    analog_value(name="HTG-LOOP", instance=7, description="Heating loop output",
                 properties={"units": "percent"}, presentValue=0.0)
    analog_value(name="DA-T-SP", instance=8, description="Discharge air temp setpoint",
                 properties={"units": "degreesFahrenheit"}, presentValue=90.0)

    # --- Binary ---
    binary_value(name="OCC-STS", instance=1, description="Zone occupancy status",
                 presentValue=True)
    binary_value(name="LOW-FLOW-ALM", instance=2, description="Low airflow alarm",
                 presentValue=False)
    binary_value(name="ZN-T-HI-ALM", instance=3, description="Zone temp high alarm",
                 presentValue=False)
    binary_value(name="ZN-T-LO-ALM", instance=4, description="Zone temp low alarm",
                 presentValue=False)

    # --- Zone State ---
    states = make_state_text(["Heating", "Deadband", "Cooling"])
    return multistate_value(name="ZN-STATE", instance=1, description="Current zone state",
                            presentValue=2, properties={"stateText": states})


async def run_scenario():
    import BAC0
    BAC0.log_level("error")

    print("=" * 60)
    print("  Single VAV — Category Test Device")
    print(f"  Device {DEVICE_ID} on {LOCAL_IP}:{PORT}")
    print("=" * 60)
    print()

    print(f"Starting device on {LOCAL_IP}...")
    dev = BAC0.lite(
        ip=f"{LOCAL_IP}/{SUBNET_MASK}",
        deviceId=DEVICE_ID,
        localObjName="VAV-TEST-1",
        port=PORT,
    )

    create_vav_points().add_objects_to_application(dev)
    print(f"  18 points registered")
    print(f"  Device {DEVICE_ID} online at {dev.localIPAddr}")
    print()
    print("Discover from Workbench: Drivers > BacnetNetwork > Discover")
    print("Press Ctrl+C to stop.")
    print("-" * 60)

    zone = ZoneModel("VAV-Test-Zone", area_sqft=250, design_cfm=DESIGN_CFM)
    zone.internal_load = 2500
    zone.outdoor_temp = 85.0
    zone.supply_air_temp = 55.0

    tick = 0
    try:
        while True:
            await asyncio.sleep(SIM_INTERVAL)
            tick += 1

            dmpr = dev["DPR-O"].presentValue or 0
            htg = dev["HTG-O"].presentValue or 0

            airflow = zone.get_airflow(dmpr)
            zone.step(SIM_INTERVAL, airflow, htg)

            dev["ZN-T"].presentValue = round(zone.get_sensed_temp(), 1)
            dev["DA-CFM"].presentValue = round(airflow, 0)
            dev["DA-T"].presentValue = round(zone.get_discharge_temp(htg), 1)

            # Update active setpoint based on loop outputs
            dev["CFM-SP"].presentValue = round(airflow, 0)

            if tick % 15 == 0:
                zn_t = dev["ZN-T"].presentValue
                print(f"[t={tick * SIM_INTERVAL:.0f}s] "
                      f"ZnT={zn_t:.1f}F  DA-CFM={airflow:.0f}  "
                      f"Dmpr={dmpr:.0f}%  Htg={htg:.0f}%")

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        dev.disconnect()
        print("Device stopped.")


def main():
    asyncio.run(run_scenario())


if __name__ == "__main__":
    main()
