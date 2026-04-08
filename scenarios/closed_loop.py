"""
Closed-Loop G36 Scenario — G36 controllers drive simulated building.

The G36 VAV and AHU controllers read sensor values from the simulated
BACnet devices, compute control outputs, and write commands back.
Zones respond thermally. Faults can be injected at runtime.

This is the full integration test: G36 logic + BACnet devices + thermal sim + faults.

Network topology same as small_office.py (8 devices).

Usage:
    python run_simulator.py closed_loop

Fault injection: press keys during simulation
    1-5: inject stuck damper on VAV 1-5
    f:   inject RTU fan failure
    d:   inject sensor drift on VAV-1 zone temp
    c:   clear all faults
"""
import asyncio
import sys
import os
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from devices.jace8000 import create_jace_points
from devices.jci_fec_vav import create_fec_vav_points
from devices.aaon_rtu import create_aaon_rtu_points
from devices.jci_fec_misc import create_misc_controller_points
from simulation.zone_model import ZoneModel
from simulation.ahu_model import AhuModel
from simulation.faults import (
    FaultManager, StuckDamper, FanFailure, SensorDrift,
    LeakingValve, StuckValve,
)
from simulation.g36_controller import G36VavReheat, G36AhuController

VAV_ZONES = [
    ("Interior-1",  600,  2500, 250),
    ("Interior-2",  600,  2000, 250),
    ("Perim-South", 900,  4000, 300),
    ("Perim-North", 800,  1500, 300),
    ("Conf-Room",   1200, 6000, 400),
]

SIM_INTERVAL = 1.0  # 1 second ticks for tighter control


async def start_device(device_id, name, port, point_creator, *args):
    import BAC0
    bacnet = await BAC0.lite(deviceId=device_id, localObjName=name, port=port).__aenter__()
    obj = point_creator(*args)
    obj.add_objects_to_application(bacnet)
    return bacnet


async def run_scenario():
    import BAC0
    BAC0.log_level("error")

    print("=" * 60)
    print("  G36 Closed-Loop Simulation")
    print("  G36 controllers + BACnet devices + thermal sim + faults")
    print("=" * 60)
    print()

    devices = []
    fault_mgr = FaultManager()

    try:
        # --- Start all BACnet devices ---
        jace = await start_device(1001, "JACE-8000", 47808, create_jace_points)
        devices.append(jace)

        vav_devs = []
        for i, (name, cfm, load, area) in enumerate(VAV_ZONES):
            dev = await start_device(2001 + i, f"FEC-VAV{i+1}", 47809 + i,
                                     create_fec_vav_points, name, cfm)
            vav_devs.append(dev)
            devices.append(dev)

        rtu = await start_device(3001, "AAON-RTU", 47814, create_aaon_rtu_points)
        devices.append(rtu)

        misc = await start_device(4001, "FEC-MISC", 47815, create_misc_controller_points)
        devices.append(misc)

        print(f"All {len(devices)} BACnet devices online.")

        # --- Initialize simulation models ---
        zones = []
        for name, cfm, load, area in VAV_ZONES:
            z = ZoneModel(name, area_sqft=area, design_cfm=cfm)
            z.internal_load = load
            z.outdoor_temp = 85.0
            zones.append(z)

        ahu_model = AhuModel()
        ahu_model.outdoor_air_temp = 85.0

        # --- Initialize G36 controllers ---
        vav_controllers = []
        for name, cfm, load, area in VAV_ZONES:
            ctrl = G36VavReheat(v_cool_max=cfm, v_min=cfm * 0.3, v_heat_max=cfm * 0.6)
            vav_controllers.append(ctrl)

        ahu_ctrl = G36AhuController(sp_max=2.0, min_clg_sat=55.0, max_clg_sat=65.0)
        ahu_ctrl.start(0)

        # Start RTU fan
        rtu["SF-CMD"].presentValue = "active"
        rtu["SF-SPD"].presentValue = 75.0

        print("G36 controllers running. Closed-loop simulation active.")
        print()
        print("Fault injection commands:")
        print("  (faults are injected via fault_mgr in code — see scenarios/closed_loop.py)")
        print()
        print("Press Ctrl+C to stop.")
        print("-" * 60)

        # --- Pre-programmed fault schedule ---
        # Inject faults at specific times to demonstrate detection
        fault_schedule = {
            60:  ("inject", StuckDamper("VAV-3", stuck_position=100.0)),
            180: ("clear", "stuck_damper_VAV-3"),
            240: ("inject", SensorDrift("VAV-1", "ZN-T", drift_rate_per_min=0.5, max_drift=8.0)),
            420: ("clear", "sensor_drift_VAV-1_ZN-T"),
            480: ("inject", LeakingValve("VAV-5", "HTG-VLV", leak_pct=20.0)),
            600: ("clear_all", None),
        }

        tick = 0
        sim_time = 0.0

        while True:
            await asyncio.sleep(SIM_INTERVAL)
            tick += 1
            sim_time += SIM_INTERVAL

            # --- Fault schedule ---
            int_time = int(sim_time)
            if int_time in fault_schedule:
                action, data = fault_schedule.pop(int_time)
                if action == "inject":
                    fault_mgr.inject(data)
                elif action == "clear":
                    fault_mgr.clear(data)
                elif action == "clear_all":
                    fault_mgr.clear_all()

            # --- Read OAT ---
            oat = jace["OAT"].presentValue
            ahu_model.outdoor_air_temp = oat

            # --- RTU / AHU model step ---
            fan_on = rtu["SF-CMD"].presentValue in ["active", True]
            fan_spd = rtu["SF-SPD"].presentValue or 0
            ahu_model.step(SIM_INTERVAL, float(ahu_ctrl.oa_dmpr),
                          float(ahu_ctrl.chw_vlv), float(ahu_ctrl.hw_vlv),
                          float(ahu_ctrl.fan_spd), ahu_ctrl.fan_cmd)

            # Update RTU sensor points
            rtu["SA-T"].presentValue = round(ahu_model.get_sensed_sat(), 1)
            rtu["MA-T"].presentValue = round(ahu_model.get_sensed_mat(), 1)
            rtu["SA-SP"].presentValue = round(ahu_model.get_sensed_sp(), 2)
            rtu["SF-STS"].presentValue = "active" if (ahu_ctrl.fan_cmd and ahu_ctrl.fan_spd > 5) else "inactive"

            # --- AHU G36 controller ---
            total_sp_req = sum(c.sp_reset_requests for c in vav_controllers)
            total_sat_req = sum(c.clg_sat_requests for c in vav_controllers)

            ahu_ctrl.execute(SIM_INTERVAL, sim_time,
                            ahu_model.supply_air_temp,
                            ahu_model.mixed_air_temp,
                            oat,
                            ahu_model.duct_static_pressure,
                            total_sp_req, total_sat_req)

            # Write AHU commands back to RTU device
            rtu["SF-SPD"].presentValue = round(ahu_ctrl.fan_spd, 1)
            rtu["OA-DPR"].presentValue = round(ahu_ctrl.oa_dmpr, 1)
            rtu["HTG-O"].presentValue = round(ahu_ctrl.hw_vlv, 1)

            # --- VAV zone simulation + G36 controllers ---
            for i, (zone, vav_dev, ctrl) in enumerate(zip(zones, vav_devs, vav_controllers)):
                device_name = f"VAV-{i+1}"
                zone.supply_air_temp = ahu_model.supply_air_temp

                # Read commands from G36 controller (not from BACnet — controller writes directly)
                dmpr_cmd = ctrl.dmpr_cmd
                htg_vlv = ctrl.htg_vlv

                # Apply faults
                faults = fault_mgr.get_faults_for_device(device_name)
                for fault in faults:
                    if isinstance(fault, StuckDamper):
                        dmpr_cmd = fault.apply(dmpr_cmd)
                    elif isinstance(fault, (StuckValve, LeakingValve)) and "HTG" in fault.point_name:
                        htg_vlv = fault.apply(htg_vlv)

                # Zone thermal model
                airflow = zone.get_airflow(dmpr_cmd)
                zone.step(SIM_INTERVAL, airflow, htg_vlv)

                # Sensor readings (with possible faults)
                zn_temp = zone.get_sensed_temp()
                for fault in faults:
                    if isinstance(fault, SensorDrift) and fault.point_name == "ZN-T":
                        zn_temp = fault.apply(zn_temp, SIM_INTERVAL)

                da_temp = zone.get_discharge_temp(htg_vlv)

                # Update BACnet sensor points
                vav_dev["ZN-T"].presentValue = round(zn_temp, 1)
                vav_dev["DA-CFM"].presentValue = round(airflow, 0)
                vav_dev["DA-T"].presentValue = round(da_temp, 1)

                # G36 controller reads sensors and computes new commands
                ctrl.execute(SIM_INTERVAL, sim_time, zn_temp, airflow, da_temp)

                # Write G36 outputs to BACnet device
                vav_dev["DPR-O"].presentValue = round(ctrl.dmpr_cmd, 1)
                vav_dev["HTG-O"].presentValue = round(ctrl.htg_vlv, 1)
                vav_dev["CFM-SP"].presentValue = round(ctrl.flow_sp, 0)
                vav_dev["CLG-O"].presentValue = round(ctrl.clg_loop.output, 1)
                vav_dev["HTG-LOOP"].presentValue = round(ctrl.htg_loop.output, 1)

                # Zone state
                state_map = {"heating-p1": 1, "heating-p2": 1, "deadband": 2, "cooling": 3}
                vav_dev["ZN-STATE"].presentValue = state_map.get(ctrl.zone_state, 2)

            # --- Misc controller ---
            for ef in [1, 2]:
                cmd = misc[f"EF{ef}-CMD"].presentValue
                is_on = cmd in ["active", True]
                misc[f"EF{ef}-STS"].presentValue = "active" if is_on else "inactive"
                misc[f"EF{ef}-AMPS"].presentValue = 3.2 if is_on else 0.0

            misc["BLDG-SP"].presentValue = round(0.05 + random.gauss(0, 0.008), 3)

            # --- Status print ---
            if tick % 30 == 0:
                print(f"[t={sim_time:.0f}s] SAT={ahu_model.supply_air_temp:.1f}F  "
                      f"SP-SP={ahu_ctrl.sp_sp:.2f}\"  SAT-SP={ahu_ctrl.sat_sp:.1f}F  "
                      f"Fan={ahu_ctrl.fan_spd:.0f}%  CHW={ahu_ctrl.chw_vlv:.0f}%  "
                      f"HW={ahu_ctrl.hw_vlv:.0f}%  OA={ahu_ctrl.oa_dmpr:.0f}%")
                for i, (zone, ctrl) in enumerate(zip(zones, vav_controllers)):
                    faults = fault_mgr.get_faults_for_device(f"VAV-{i+1}")
                    fault_str = f" **{faults[0].description}**" if faults else ""
                    print(f"  VAV-{i+1} {zone.name:14s}  "
                          f"ZnT={zone.zone_temp:.1f}F  [{ctrl.zone_state:11s}]  "
                          f"Dmpr={ctrl.dmpr_cmd:.0f}%  Htg={ctrl.htg_vlv:.0f}%  "
                          f"FlowSP={ctrl.flow_sp:.0f}{fault_str}")
                print()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
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
