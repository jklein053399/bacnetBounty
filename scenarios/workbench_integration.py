"""
Workbench Integration Scenario — Phase 3

Single BACnet/IP device (instance 360) on port 47850 hosting all objects.
Instance offsets separate each logical sub-device:

  RTU:    offset 0    (AI 1-10, AO 1-3, BI 1-8, BO 1-4, AV 1-7, BV 1-6, MV 1)
  VAV-1:  offset 100  (AI 101-103, AO 101-102, AV 101-111, BV 101+, MV 101)
  VAV-2:  offset 200
  VAV-3:  offset 300
  VAV-4:  offset 400
  VAV-5:  offset 500
  EF:     offset 600  (BO 601-602, BI 601-602, AO 601-602, AI 601-602, BV 601+, AV 601+)

Run: python run_simulator.py workbench
"""
import asyncio
import random
import sys
import os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from BAC0.core.devices.local.factory import (
    analog_input, analog_value,
    binary_input, binary_value,
    multistate_value, make_state_text,
)
from simulation.zone_model import ZoneModel
from simulation.ahu_model import AhuModel

# Simulator on secondary IP (10.0.0.234) with standard BACnet port for Who-Is discovery
# Add secondary IP: netsh interface ipv4 set interface "Ethernet" dhcpstaticipcoexistence=enabled
#                   netsh interface ipv4 add address "Ethernet" 10.0.0.234 255.255.255.0
DEVICE_ID = 360
PORT = 47808
LOCAL_IP = "10.0.0.234"
SUBNET_MASK = 24

VAV_ZONES = [
    ("Interior-Office-1", 600,  2500),
    ("Interior-Office-2", 600,  2000),
    ("Perimeter-South",   900,  4000),
    ("Perimeter-North",   800,  1500),
    ("Conference-Room",   1200, 6000),
]

SIM_INTERVAL = 2.0


def create_rtu_points(offset=0):
    """AAON RTU points with instance offset."""
    # Analog Inputs
    analog_input(name="RTU-SA-T", instance=offset+1, description="RTU Supply air temp", properties={"units": "degreesFahrenheit"}, presentValue=55.0)
    analog_input(name="RTU-RA-T", instance=offset+2, description="RTU Return air temp", properties={"units": "degreesFahrenheit"}, presentValue=72.0)
    analog_input(name="RTU-MA-T", instance=offset+3, description="RTU Mixed air temp", properties={"units": "degreesFahrenheit"}, presentValue=65.0)
    analog_input(name="RTU-OA-T", instance=offset+4, description="RTU Outdoor air temp", properties={"units": "degreesFahrenheit"}, presentValue=85.0)
    analog_input(name="RTU-SA-SP", instance=offset+5, description="RTU Duct static pressure", properties={"units": "inchesOfWater"}, presentValue=1.0)
    analog_input(name="RTU-RA-RH", instance=offset+6, description="RTU Return air RH", properties={"units": "percentRelativeHumidity"}, presentValue=50.0)
    analog_input(name="RTU-FILT-DP", instance=offset+7, description="RTU Filter diff pressure", properties={"units": "inchesOfWater"}, presentValue=0.6)
    # Analog Commands (as AV to avoid BAC0 write issues with AO)
    analog_value(name="RTU-SF-SPD", instance=offset+50, description="RTU Supply fan speed cmd", properties={"units": "percent"}, presentValue=0.0)
    analog_value(name="RTU-OA-DPR", instance=offset+51, description="RTU OA damper cmd", properties={"units": "percent"}, presentValue=15.0)
    analog_value(name="RTU-HTG-O", instance=offset+52, description="RTU Heat output", properties={"units": "percent"}, presentValue=0.0)
    # Binary Inputs
    binary_input(name="RTU-SF-STS", instance=offset+1, description="RTU Supply fan status", presentValue=False)
    binary_input(name="RTU-COMP1-STS", instance=offset+2, description="RTU Compressor 1 status", presentValue=False)
    binary_input(name="RTU-COMP2-STS", instance=offset+3, description="RTU Compressor 2 status", presentValue=False)
    binary_input(name="RTU-SMOKE-DET", instance=offset+4, description="RTU Duct smoke detector", presentValue=False)
    binary_input(name="RTU-FREEZE-STAT", instance=offset+5, description="RTU Freeze stat", presentValue=False)
    # Binary Commands (as BV to avoid BAC0 write issues with BO)
    binary_value(name="RTU-SF-CMD", instance=offset+50, description="RTU Supply fan start/stop", presentValue=False)
    binary_value(name="RTU-COMP1-CMD", instance=offset+51, description="RTU Compressor 1 enable", presentValue=False)
    binary_value(name="RTU-COMP2-CMD", instance=offset+52, description="RTU Compressor 2 enable", presentValue=False)
    # Analog Values (setpoints)
    analog_value(name="RTU-SA-T-SP", instance=offset+1, description="RTU SAT setpoint", properties={"units": "degreesFahrenheit"}, presentValue=55.0)
    analog_value(name="RTU-SA-SP-SP", instance=offset+2, description="RTU Static pressure SP", properties={"units": "inchesOfWater"}, presentValue=1.5)
    analog_value(name="RTU-OCC-CLG-SP", instance=offset+3, description="RTU Occ cooling SP", properties={"units": "degreesFahrenheit"}, presentValue=75.0)
    analog_value(name="RTU-OCC-HTG-SP", instance=offset+4, description="RTU Occ heating SP", properties={"units": "degreesFahrenheit"}, presentValue=70.0)
    analog_value(name="RTU-MIN-OA-POS", instance=offset+5, description="RTU Min OA position", properties={"units": "percent"}, presentValue=15.0)
    # Mode
    modes = make_state_text(["Off", "Vent", "Economizer", "Mech-Clg-1", "Mech-Clg-2", "Heat", "Dehum", "Morning-WU"])
    multistate_value(name="RTU-UNIT-MODE", instance=offset+1, description="RTU Operating mode", presentValue=1, properties={"stateText": modes})
    # Alarms
    binary_value(name="RTU-SF-FAIL-ALM", instance=offset+1, description="RTU Fan fail alarm", presentValue=False)
    return binary_value(name="RTU-FREEZE-ALM", instance=offset+2, description="RTU Freeze alarm", presentValue=False)


def create_vav_points(vav_num, zone_name, design_cfm, offset=100):
    """JCI VAV points with instance offset."""
    o = offset + (vav_num - 1) * 100
    pfx = f"VAV{vav_num}"
    # Analog Inputs
    analog_input(name=f"{pfx}-ZN-T", instance=o+1, description=f"{pfx} Zone temp - {zone_name}", properties={"units": "degreesFahrenheit"}, presentValue=72.0)
    analog_input(name=f"{pfx}-DA-T", instance=o+2, description=f"{pfx} Discharge air temp", properties={"units": "degreesFahrenheit"}, presentValue=72.0)
    analog_input(name=f"{pfx}-DA-CFM", instance=o+3, description=f"{pfx} Discharge airflow", properties={"units": "cubicFeetPerMinute"}, presentValue=design_cfm*0.3)
    # Analog Commands (as AV)
    analog_value(name=f"{pfx}-DPR-O", instance=o+50, description=f"{pfx} Damper output", properties={"units": "percent"}, presentValue=50.0)
    analog_value(name=f"{pfx}-HTG-O", instance=o+51, description=f"{pfx} Reheat valve output", properties={"units": "percent"}, presentValue=0.0)
    # Analog Values
    analog_value(name=f"{pfx}-ZN-SP", instance=o+1, description=f"{pfx} Zone temp SP", properties={"units": "degreesFahrenheit"}, presentValue=72.0)
    analog_value(name=f"{pfx}-OCC-CLG-SP", instance=o+2, description=f"{pfx} Occ cooling SP", properties={"units": "degreesFahrenheit"}, presentValue=75.0)
    analog_value(name=f"{pfx}-OCC-HTG-SP", instance=o+3, description=f"{pfx} Occ heating SP", properties={"units": "degreesFahrenheit"}, presentValue=70.0)
    analog_value(name=f"{pfx}-CFM-MAX", instance=o+4, description=f"{pfx} Max airflow SP", properties={"units": "cubicFeetPerMinute"}, presentValue=design_cfm)
    analog_value(name=f"{pfx}-CFM-MIN", instance=o+5, description=f"{pfx} Min airflow SP", properties={"units": "cubicFeetPerMinute"}, presentValue=design_cfm*0.3)
    analog_value(name=f"{pfx}-CFM-SP", instance=o+6, description=f"{pfx} Active airflow SP", properties={"units": "cubicFeetPerMinute"}, presentValue=design_cfm*0.3)
    analog_value(name=f"{pfx}-CLG-O", instance=o+7, description=f"{pfx} Cooling loop output", properties={"units": "percent"}, presentValue=0.0)
    analog_value(name=f"{pfx}-HTG-LOOP", instance=o+8, description=f"{pfx} Heating loop output", properties={"units": "percent"}, presentValue=0.0)
    # States
    states = make_state_text(["Heating", "Deadband", "Cooling", "Unocc-Htg", "Unocc-Clg"])
    multistate_value(name=f"{pfx}-ZN-STATE", instance=o+1, description=f"{pfx} Zone state", presentValue=2, properties={"stateText": states})
    binary_value(name=f"{pfx}-OCC-STS", instance=o+1, description=f"{pfx} Occupancy status", presentValue=True)
    # Alarms
    binary_value(name=f"{pfx}-ZN-T-HI-ALM", instance=o+2, description=f"{pfx} Zone temp high alarm", presentValue=False)
    return binary_value(name=f"{pfx}-ZN-T-LO-ALM", instance=o+3, description=f"{pfx} Zone temp low alarm", presentValue=False)


def create_ef_points(offset=600):
    """Exhaust fan controller points with instance offset."""
    for ef_id in [1, 2]:
        b = offset + (ef_id - 1) * 10
        binary_value(name=f"EF{ef_id}-CMD", instance=b+1, description=f"Exhaust fan {ef_id} start/stop", presentValue=False)
        binary_input(name=f"EF{ef_id}-STS", instance=b+2, description=f"Exhaust fan {ef_id} status", presentValue=False)
        analog_value(name=f"EF{ef_id}-SPD-CMD", instance=b+3, description=f"Exhaust fan {ef_id} speed cmd", properties={"units": "percent"}, presentValue=0.0)
        analog_input(name=f"EF{ef_id}-SPD-FBK", instance=b+4, description=f"Exhaust fan {ef_id} speed fbk", properties={"units": "percent"}, presentValue=0.0)
        binary_value(name=f"EF{ef_id}-FAIL-ALM", instance=b+5, description=f"Exhaust fan {ef_id} fail alarm", presentValue=False)
    return analog_value(name="EF1-RUN-HRS", instance=offset+20, description="EF1 runtime hours", properties={"units": "hours"}, presentValue=2600.0)


async def run_scenario():
    import BAC0
    BAC0.log_level("error")

    print("=" * 60)
    print("  Workbench Integration - Phase 3")
    print(f"  Single BACnet/IP Device {DEVICE_ID} on port {PORT}")
    print("  RTU + 5 VAVs + EF Controller (instance offsets)")
    print("=" * 60)
    print()

    print(f"Starting device {DEVICE_ID} on {LOCAL_IP}:{PORT}...")
    dev = BAC0.lite(
        ip=f"{LOCAL_IP}/{SUBNET_MASK}",
        deviceId=DEVICE_ID,
        localObjName="BldgController",
        port=PORT,
        maxAPDULengthAccepted=1476,
        maxSegmentsAccepted=1024,
        segmentationSupported="segmentedBoth",
    )

    # Register all point sets
    create_rtu_points(offset=0).add_objects_to_application(dev)
    print("  RTU points registered (offset 0)")

    for i, (zone_name, cfm, load) in enumerate(VAV_ZONES):
        create_vav_points(i+1, zone_name, cfm, offset=100).add_objects_to_application(dev)
        print(f"  VAV-{i+1} points registered (offset {100 + i*100})")

    create_ef_points(offset=600).add_objects_to_application(dev)
    print("  EF points registered (offset 600)")

    print()
    print(f"Device {DEVICE_ID} online at {dev.localIPAddr}")
    print("Discover from Workbench: Drivers > BacnetNetwork > Discover")
    print("Press Ctrl+C to stop.")
    print("-" * 60)

    # Simulation models
    zones = []
    for zone_name, cfm, load in VAV_ZONES:
        z = ZoneModel(zone_name, area_sqft=250, design_cfm=cfm)
        z.internal_load = load
        z.outdoor_temp = 85.0
        zones.append(z)

    ahu = AhuModel()
    ahu.outdoor_air_temp = 85.0

    tick = 0
    try:
        while True:
            await asyncio.sleep(SIM_INTERVAL)
            tick += 1

            # RTU simulation
            oat = 85.0 + random.gauss(0, 0.5)
            dev["RTU-OA-T"].presentValue = round(oat, 1)
            ahu.outdoor_air_temp = oat

            fan_on = dev["RTU-SF-CMD"].presentValue
            fan_spd = dev["RTU-SF-SPD"].presentValue or 0
            oa_dmpr = dev["RTU-OA-DPR"].presentValue or 15
            htg_out = dev["RTU-HTG-O"].presentValue or 0
            clg = 50.0 if dev["RTU-COMP1-STS"].presentValue else 0
            if dev["RTU-COMP2-STS"].presentValue:
                clg = 100.0

            ahu.step(SIM_INTERVAL, oa_dmpr, clg, htg_out, fan_spd, fan_on)
            dev["RTU-SA-T"].presentValue = round(ahu.get_sensed_sat(), 1)
            dev["RTU-MA-T"].presentValue = round(ahu.get_sensed_mat(), 1)
            dev["RTU-SA-SP"].presentValue = round(ahu.get_sensed_sp(), 2)
            dev["RTU-SF-STS"].presentValue = fan_on and fan_spd > 5

            # VAV zone simulation
            for i, (zone, (zone_name, cfm, load)) in enumerate(zip(zones, VAV_ZONES)):
                pfx = f"VAV{i+1}"
                dmpr_cmd = dev[f"{pfx}-DPR-O"].presentValue or 0
                htg_vlv = dev[f"{pfx}-HTG-O"].presentValue or 0

                zone.supply_air_temp = ahu.supply_air_temp
                airflow = zone.get_airflow(dmpr_cmd)
                zone.step(SIM_INTERVAL, airflow, htg_vlv)

                dev[f"{pfx}-ZN-T"].presentValue = round(zone.get_sensed_temp(), 1)
                dev[f"{pfx}-DA-CFM"].presentValue = round(airflow, 0)
                dev[f"{pfx}-DA-T"].presentValue = round(zone.get_discharge_temp(htg_vlv), 1)

            # EF simulation
            for ef_id in [1, 2]:
                cmd = dev[f"EF{ef_id}-CMD"].presentValue
                spd_cmd = dev[f"EF{ef_id}-SPD-CMD"].presentValue or 0
                dev[f"EF{ef_id}-STS"].presentValue = cmd and spd_cmd > 5
                dev[f"EF{ef_id}-SPD-FBK"].presentValue = round(spd_cmd * 0.98, 1) if cmd else 0.0

            # Periodic status
            if tick % 15 == 0:
                print(f"[t={tick * SIM_INTERVAL:.0f}s] "
                      f"OAT={oat:.0f}F  RTU: SAT={ahu.supply_air_temp:.1f}F  "
                      f"Fan={'ON' if fan_on else 'OFF'}@{fan_spd:.0f}%")
                for i, zone in enumerate(zones):
                    pfx = f"VAV{i+1}"
                    dmpr = dev[f"{pfx}-DPR-O"].presentValue or 0
                    htg = dev[f"{pfx}-HTG-O"].presentValue or 0
                    print(f"  {pfx} {zone.name:20s}  "
                          f"ZnT={zone.zone_temp:.1f}F  Dmpr={dmpr:.0f}%  Htg={htg:.0f}%")
                for ef_id in [1, 2]:
                    sts = dev[f"EF{ef_id}-STS"].presentValue
                    spd = dev[f"EF{ef_id}-SPD-FBK"].presentValue
                    print(f"  EF-{ef_id}: {'ON' if sts else 'OFF'}  Speed={spd:.0f}%")
                print()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        dev.disconnect()
        print("Device stopped.")


def main():
    asyncio.run(run_scenario())


if __name__ == "__main__":
    main()
